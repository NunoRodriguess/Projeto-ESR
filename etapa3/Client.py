from tkinter import *
import tkinter.messagebox
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os

from control_protocol_pb2 import ControlMessage
import time
from VideoSession import VideoSession


class Client:
	INIT = 0
	READY = 1
	PLAYING = 2
	state = INIT

	SETUP = 0
	PLAY = 1
	PAUSE = 2
	TEARDOWN = 3
	
	# Initiation..
	def __init__(self, master, nodeaddr, nodeport, rtpport, filename, client_id, client_ip, bootstrapper_host='localhost', bootstrapper_port=5000):
		self.master = master
		self.nodeAddr = nodeaddr
		self.nodePort = int(nodeport)
		self.rtpPort = int(rtpport)
		self.fileName = filename

		# Client details
		self.client_id = client_id
		self.client_ip = client_ip
		
		# Bootstrapper configuration
		self.bootstrapper = (bootstrapper_host, bootstrapper_port)
		
		# Networking and synchronization
		self.neighbors = {}
		self.control_port = 5001
		self.data_port = 5002
		self.lock = threading.Lock()
		self.node_type = "client"

		# Connect to server and perform background work
		self.background()  # Register with the bootstrapper and start background tasks
		
		# Initialize GUI
		self.create_main_widgets()  # Initialize the UI
		self.sessions = {}
		self.session_count = 0
		
	def register_with_bootstrapper(self):
			"""
			Registra o nó com o Bootstrapper e recebe uma lista de vizinhos.
			Envia uma mensagem de controle para o Bootstrapper e processa a resposta.
			"""
			with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
				s.connect(self.bootstrapper)  # Conecta ao Bootstrapper
				
				# Cria a mensagem de controle para registro
				control_message = ControlMessage()
				control_message.type = ControlMessage.REGISTER
				control_message.node_id = self.client_id
				control_message.node_ip = self.client_ip
				control_message.control_port = self.control_port
				control_message.data_port = self.data_port
				control_message.node_type = self.node_type
				
				# Envia a mensagem de registro
				s.send(control_message.SerializeToString())
				
				# Recebe e processa a resposta
				data = s.recv(1024)
				if data:
					response_message = ControlMessage()
					response_message.ParseFromString(data)
					
					if response_message.type == ControlMessage.REGISTER_RESPONSE:
						print(f"Client {self.client_id} registered")
						self.neighbors.clear()  # Limpa vizinhos antigos em caso de reativação
						for neighbor in response_message.neighbors:
							with self.lock: 
								self.neighbors[neighbor.node_ip] = {
									"node_id": neighbor.node_id,
									"control_port": neighbor.control_port,
									"data_port": neighbor.data_port,
         							"node_type": neighbor.node_type,
									"status": "active",
									"failed-attempts": 0
								}
						print(f"Client {self.client_id} Pop's: {self.neighbors}")
						# Após o registro, notifica os vizinhos sobre o registro
						self.notify_neighbors_registration()
					else:
						print(f"Unexpected response type: {response_message.type}")

	def notify_neighbors_registration(self):
		"""
		Notifica os vizinhos que o nó está registrado e que pode haver atualizações.
		"""
		for neighbor_ip, neighbor_info in self.neighbors.items():
			try:
				with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
					s.connect((neighbor_ip, neighbor_info['control_port']))
					notify_message = ControlMessage()
					notify_message.type = ControlMessage.UPDATE_NEIGHBORS
					notify_message.node_id = self.client_id
					notify_message.node_ip = self.client_ip
					notify_message.control_port = self.control_port
					notify_message.data_port = self.data_port
					notify_message.node_type = self.node_type
					s.send(notify_message.SerializeToString())
					print(f"Notified neighbor {neighbor_info['node_id']} of registration.")

			except Exception as e:
				print(f"Failed to notify neighbor {neighbor_info['node_id']}: {e}")
				
	def background(self):
		"""
		Função principal do cliente que inicia a solicitação de vizinhos.
		"""
		self.register_with_bootstrapper()
		threading.Thread(target=self.control_server).start()  # Inicia o servidor de controle em uma thread separada
		threading.Thread(target=self.send_ping_to_neighbors).start()  # Enviar PING aos vizinhos
	
	def control_server(self):
		"""
		Inicia o servidor de controle que escuta em uma porta específica para conexões de outros nós.
		Lida com mensagens de controle como PING e atualizações de vizinhos.
		"""
		with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
			s.bind(('', self.control_port))
			s.listen()
			print(f"Client {self.client_id} listening on control port {self.control_port}")
			while True:
				conn, addr = s.accept()
				threading.Thread(target=self.handle_control_connection, args=(conn, addr)).start()

	def handle_control_connection(self, conn, addr):
		"""
		Lida com as conexões de controle de outros nós.
		Responde a mensagens de PING e processa atualizações de vizinhos.

		:conn: Conexão de socket com outro nó.
		:addr: Endereço do nó conectado.
		"""
		print(f"Connection from {addr} established.")
		with conn:
			while True:
				data = conn.recv(1024)
				if data:
					control_message = ControlMessage()
					try:
						control_message.ParseFromString(data)
					except Exception as e:
						print(f"Failed to parse control message: {e}")
						continue  # Ignora a mensagem se não conseguir analisá-la

					# Atualizar vizinhos
					if control_message.type == ControlMessage.UPDATE_NEIGHBORS:
						self.handle_update_neighbors(control_message)
					
					# Enviar ping aos vizinhos (só para os nodes)
					if control_message.type == ControlMessage.PING:
						self.handle_ping(control_message, conn)
						
	def handle_update_neighbors(self, control_message):
		print(f"Updating neighbors with {control_message.node_id}")
		neighbor_id = control_message.node_id
		neighbor_ip = control_message.node_ip
		control_port = control_message.control_port
		data_port = control_message.data_port
		node_type = control_message.node_type
		
		with self.lock: 
				# Se o vizinho já estiver na lista, atualiza o status
				if neighbor_ip in self.neighbors:
					self.neighbors[neighbor_ip]["status"] = "active"
					print(f"Updated status of existing neighbor {neighbor_id} to active.")
				else:
					# Armazena as informações do vizinho se ele não estiver presente
					self.neighbors[neighbor_ip] = {
						"node_id": neighbor_id,
						"control_port": control_port,
						"data_port": data_port,
						"node_type": node_type,
						"tentativas": 0,
						"status": "active"  # Define o status como ativo
					}
					print(f"Added new neighbor: {neighbor_id}")
		
	def send_ping_to_neighbors(self):
		while True:
			time.sleep(10)
			
			for neighbor_ip, neighbor_info in list(self.neighbors.items()):
				# Verificar se o vizinho já está marcado como inativo
				if neighbor_info.get("status") == "inactive":
					continue  # Ignora o envio de PING para vizinhos já considerados inativos

				# Verifica o número de tentativas
				if neighbor_info.get("failed-attempts", 0) >= 2:
					print(f"Neighbor {neighbor_info['node_id']} considered inactive due to lack of PONG response.")
					with self.lock:
						neighbor_info["status"] = "inactive"
					#self.notify_bootstrapper_inactive(neighbor_ip)  # Notifica o Bootstrapper
					continue  # Ignora o envio de PING para vizinhos já considerados inativos

				try:
					with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
						s.connect((neighbor_ip, neighbor_info['control_port']))
						ping_message = ControlMessage()
						ping_message.type = ControlMessage.PING
						ping_message.node_ip = self.client_ip
						ping_message.node_id = self.client_id
						s.send(ping_message.SerializeToString())
						print(f"Sent PING to neighbor {neighbor_info['node_id']}")

						# Espera pela resposta PONG
						data = s.recv(1024)
						if data:
							response_message = ControlMessage()
							response_message.ParseFromString(data)
							if response_message.type == ControlMessage.PONG:
								print(f"Received PONG from neighbor {response_message.node_id}")
								# Resetamos as tentativas falhas em caso de resposta
								with self.lock:
									neighbor_info["failed-attempts"] = 0
									neighbor_info["status"] = "active"

				except Exception as e:
					# Incrementa o contador de tentativas falhas
					print(f"Failed to send PING to neighbor {neighbor_info['node_id']}: {e}")
					with self.lock:
						neighbor_info["failed-attempts"] = neighbor_info.get("failed-attempts", 0) + 1			
	
	def handle_ping(self, control_message, conn):
     	# Responder a uma mensagem de ping
		print(f"Received PING from neighbor {control_message.node_id}")
		pong_message = ControlMessage()
		pong_message.type = ControlMessage.PONG
		pong_message.node_id = self.client_id
		conn.send(pong_message.SerializeToString())
		print(f"Sent PONG to neighbor {control_message.node_id}")
		
		# Reinicia as tentativas falhas do nó que enviou o PING
		with self.lock:
			if control_message.node_ip in self.neighbors:
					self.neighbors[control_message.node_ip]["failed-attempts"] = 0
					self.neighbors[control_message.node_ip]["status"] = "active"
				
	def create_main_widgets(self):
		self.new_session_button = Button(self.master, text="Nova Sessão de Vídeo", command=self.start_new_session)
		self.new_session_button.pack()

		self.sessions_frame = Frame(self.master)
		self.sessions_frame.pack()

	def start_new_session(self):
		self.session_count += 1
		session_id = self.session_count
		session_window = Toplevel(self.master)
		video_session = VideoSession(session_window, self.nodeAddr, self.nodePort, self.rtpPort, self.fileName, session_id)
		
		# Adiciona um botão para fechar a sessão
		close_button = Button(self.sessions_frame, text=f"Fechar Sessão {session_id}", command=lambda: self.close_session(session_id))
		close_button.pack()

		self.sessions[session_id] = (video_session, session_window, close_button)

	def close_session(self, session_id):
		if session_id in self.sessions:
			video_session, session_window, close_button = self.sessions[session_id]
			if video_session.active == False:
				session_window.destroy()  # Fecha a janela da sessão
				close_button.destroy() # Apaga o botão da interface
				del self.sessions[session_id]  # Remove a sessão do dicionário

	def handler(self):
		"""Handler on explicitly closing the GUI window."""
		self.pauseMovie()
		if tkinter.messagebox.askokcancel("Quit?", "Are you sure you want to quit?"):
			self.exitClient()
		else: # When the user presses cancel, resume playing.
			self.playMovie()

def main():
    
    if len(sys.argv) != 4:
        print("Usage: python Client.py <bootstrapper_ip> <client_id> <client_ip>")
        sys.exit(1)

    bootstrapper = sys.argv[1] # 10.0.1.10
    client_id = sys.argv[2]  # Client-1
    client_ip = sys.argv[3] # 10.0.0.20
    
    root = Tk()
    client = Client(root, '10.0.0.1', 30001, 25000, 'movie.Mjpeg', client_id, client_ip, bootstrapper)
    root.mainloop()
    
if __name__ == "__main__":
    main()
    