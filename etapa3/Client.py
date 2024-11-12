from tkinter import *
import tkinter.messagebox
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os

from control_protocol_pb2 import ControlMessage
from control_protocol_pb2 import FloodingMessage
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
	def __init__(self, master, rtp_port, filename, client_id, client_ip, bootstrapper_host='localhost', bootstrapper_port=5000):
		self.master = master
		self.rtp_port = int(rtp_port)
		self.filename = filename

		# Client details
		self.client_id = client_id
		self.client_ip = client_ip
  
		#Neighbor details
		self.destination_ip = None
		self.destination_rtsp_port = None
		
		# Bootstrapper configuration
		self.bootstrapper = (bootstrapper_host, bootstrapper_port)
		
		# Networking and synchronization
		self.neighbors = {}
		self.control_port = 5001
		self.data_port = 5002
		self.lock = threading.Lock()
		self.node_type = "client"

		self.routing_table = {}
		self.video_session = None

		# Connect to server and perform background work
		self.background()  # Register with the bootstrapper and start background tasks
		
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
		threading.Thread(target=self.start_new_session).start()  # Thread da sessão de vídeo
		threading.Thread(target=self.monitor_routes).start()  # Monitor de rotas

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
					# Tenta parsear como ControlMessage
					control_message = ControlMessage()
					try:
						control_message.ParseFromString(data)
						# Verifica o tipo da mensagem de controle
						if control_message.type == ControlMessage.UPDATE_NEIGHBORS:
							self.handle_update_neighbors(control_message)
						
						elif control_message.type == ControlMessage.PING:
							self.handle_ping(control_message, conn)
						
						else:
							raise ValueError(f"Unknown ControlMessage type: {control_message.type}")

					except Exception as e:
						print(f"Failed to parse as ControlMessage: {e}")
						
						# Se falhar, tenta interpretar como FloodingMessage
						flooding_message = FloodingMessage()
						try:
							flooding_message.ParseFromString(data)
							
							if flooding_message.type == FloodingMessage.FLOODING_UPDATE:
								self.update_route_table(flooding_message)
			
							else:
								raise ValueError(f"Unknown FloodingMessage type: {flooding_message.type}")
						
						except Exception as e:
							# Se falhar novamente, ignora a mensagem
							print(f"Failed to parse as FloodingMessage: {e}")
							continue  # Ignora a mensagem se não conseguir analisá-la

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
			time.sleep(15)
			
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
	
	def update_route_table(self, flooding_message):
		"""
		Atualiza a tabela de rotas com base na mensagem de flooding recebida,
		agora levando em consideração múltiplos fluxos de vídeo.
		"""
		destination = flooding_message.source_ip
		metric = flooding_message.metric
		
		# Iterar sobre os fluxos de vídeo (stream_ids) recebidos
		for stream_id in flooding_message.stream_ids:

			with self.lock:
				if destination not in self.routing_table:
					self.routing_table[destination] = {}
				
				# Se a rota para o destino e o fluxo não existirem ou se a métrica for melhor (menor número de metric)
				if (stream_id not in self.routing_table[destination] or 
					metric < self.routing_table[destination][stream_id]['metric']):

					self.routing_table[destination][stream_id] = {
						"source_ip": flooding_message.source_ip,
						"source_id": flooding_message.source_id,
						"metric": metric,
						"status": flooding_message.route_state,
						"control_port": flooding_message.control_port,
						"rtsp_port": flooding_message.rtsp_port,
						"flow": "inactive"
					}
					
					print(f"Route updated for stream {stream_id} to {self.routing_table[destination][stream_id]['source_id']} with metric={metric}")
     
		print(f"Routing table is updated for streams: {list(flooding_message.stream_ids)}")  
  
	def monitor_routes(self):
		"""
		Monitor de rotas para verificar e ativar a melhor rota continuamente.
		"""
		while True:
			best_route = self.activate_best_route(self.filename)
			
			# Caso encontre uma nova rota, atualiza a sessão de vídeo em execução
			if best_route and self.video_session is not None and best_route["source_ip"] != self.destination_ip :
				print("Nova rota ativa encontrada! Atualizando a sessão de vídeo.")
				self.destination_ip = best_route["source_ip"]
				self.destination_rtsp_port = best_route["rtsp_port"]
				
				# Atualiza a sessão de vídeo com o novo destino
				self.video_session.update_destination(self.destination_ip, self.destination_rtsp_port)
			else:
				print("Nova tentativa de ativação de rotas em 10 segundos.")	
			time.sleep(10)  # Verifica a cada 10 segundos

	def start_new_session(self):
		"""
		Inicializa a sessão de vídeo com a melhor rota disponível no momento.
		"""
		while True:
			best_route = self.activate_best_route(self.filename)
			if best_route:
				self.destination_ip = best_route["source_ip"]
				self.destination_rtsp_port = best_route["rtsp_port"]
				print("Iniciando sessão com a melhor rota inicial.")
				
				# Cria a janela da sessão de vídeo
				self.session_window = Toplevel(self.master)
				self.sessions_frame = Frame(self.master)
				self.sessions_frame.pack()
				
				# Inicia uma nova sessão de vídeo
				self.video_session = VideoSession(self.session_window, self.client_ip, self.destination_ip, self.destination_rtsp_port, self.rtp_port, self.filename)
				
				# Adiciona um botão para fechar a sessão
				self.close_button = Button(self.sessions_frame, text=f'Fechar Sessão {best_route["source_id"]}', command=lambda: self.close_session(self.video_session))
				self.close_button.pack()
				break # sair do ciclo 
			else:
				print("Nova tentativa de inicar sessão em 10 segundos.")	
				time.sleep(10)  # Verifica a cada 10 segundos

	def activate_best_route(self, filename):
		"""
		Ativa a melhor rota disponível na tabela de rotas com base no número de metric
		para um fluxo específico (filename).
		"""
		best_route = None
		min_metric = float('inf')  # Define o maior valor possível para comparar
		destination = None   
			
		# Procura a melhor rota na tabela de roteamento com base no número de metric
		with self.lock:
			for dest, route_info in self.routing_table.items():
				if filename in route_info:  # Verifica se o fluxo existe na tabela
					if route_info[filename]['metric'] < min_metric:
						min_metric = route_info[filename]['metric']
						best_route = route_info[filename]
						destination = dest

		if best_route:
			with self.lock:
				self.routing_table[destination][filename]['status'] = "active"
			print(f"Activating best route to {best_route['source_id']} at {destination} with {min_metric} metric.")
			activate_message = FloodingMessage()
			activate_message.type = FloodingMessage.ACTIVATE_ROUTE
			activate_message.stream_ids.append(filename)
			activate_message.source_ip = self.client_ip
			activate_message.rtp_port = self.rtp_port
			
			# Enviar mensagem de ativação para a melhor rota
			try:
				with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
					s.connect((destination, best_route['control_port']))
					s.send(activate_message.SerializeToString())
					print(f"Sent route activation to destination {best_route['source_id']}.")
					return self.routing_table[destination][filename]
			except Exception as e:
				print(f"Failed to activate route to destination {best_route['source_id']}: {e}")
				return None
		else:
			print("No active route available to activate.")
			return None

	def close_session(self, video_session):
		"""
		Fecha a sessão de vídeo atual e remove a janela e o botão associados.
		"""
		if not video_session.active:  # Verifica se a sessão já está inativa
			# Fecha a janela da sessão de vídeo, se existir
			if self.session_window:
				self.session_window.destroy()
				self.session_window = None  # Limpa a referência

			# Remove o botão de fechar sessão, se existir
			if self.close_button:
				self.close_button.destroy()
				self.close_button = None  # Limpa a referência
			print("Sessão de vídeo fechada.")


	def handler(self):
		"""Handler on explicitly closing the GUI window."""
		self.pauseMovie()
		if tkinter.messagebox.askokcancel("Quit?", "Are you sure you want to quit?"):
			self.exitClient()
		else: # When the user presses cancel, resume playing.
			self.playMovie()

def main():
    
	if len(sys.argv) != 5:
		print("Usage: python Client.py <bootstrapper_ip> <client_id> <client_ip> <movie>")
		sys.exit(1)

	bootstrapper = sys.argv[1] # 10.0.1.10
	client_id = sys.argv[2]  # Client-1
	client_ip = sys.argv[3] # 10.0.0.20
	filename = sys.argv[4] 

	root = Tk()
	client = Client(root, 25000, filename, client_id, client_ip, bootstrapper)
	root.mainloop()
    
if __name__ == "__main__":
    main()
    