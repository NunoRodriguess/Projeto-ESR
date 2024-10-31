from tkinter import *
import tkinter.messagebox
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os

from RtpPacket import RtpPacket
from control_protocol_pb2 import ControlMessage
import time

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"

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
		self.rtspSeq = 0
		self.sessionId = 0
		self.requestSent = -1
		self.teardownAcked = 0
		self.frameNbr = 0
		
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
		
		# Initialize GUI
		self.createWidgets()  # Initialize the UI
		
		# Connect to server and perform background work
		self.connectToServer()
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
					
	# Responder a uma mensagem de ping
	def handle_ping(self, control_message, conn):
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
				
	def createWidgets(self):
     
		

		self.setup = Button(self.master, width=20, padx=3, pady=3, text="Setup", command=self.setupMovie)
		self.setup.grid(row=1, column=0, padx=2, pady=2)

		self.start = Button(self.master, width=20, padx=3, pady=3, text="Play", command=self.playMovie)
		self.start.grid(row=1, column=1, padx=2, pady=2)

		self.pause = Button(self.master, width=20, padx=3, pady=3, text="Pause", command=self.pauseMovie)
		self.pause.grid(row=1, column=2, padx=2, pady=2)

		self.teardown = Button(self.master, width=20, padx=3, pady=3, text="Teardown", command=self.exitClient)
		self.teardown.grid(row=1, column=3, padx=2, pady=2)

		self.label = Label(self.master, height=19)
		self.label.grid(row=0, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5)
  
		self.background() # Registar com o bootstraper
	
	def setupMovie(self):
		"""Setup button handler."""
		if self.state == self.INIT:
			self.sendRtspRequest(self.SETUP)
	
	def exitClient(self):
		"""Teardown button handler."""
		self.sendRtspRequest(self.TEARDOWN)		
		self.master.destroy() # Close the gui window
		os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT) # Delete the cache image from video

	def pauseMovie(self):
		"""Pause button handler."""
		if self.state == self.PLAYING:
			self.sendRtspRequest(self.PAUSE)
	
	def playMovie(self):
		"""Play button handler."""
		if self.state == self.READY:
			# Create a new thread to listen for RTP packets
			threading.Thread(target=self.listenRtp).start()
			self.playEvent = threading.Event()
			self.playEvent.clear()
			self.sendRtspRequest(self.PLAY)
	
	def listenRtp(self):		
		"""Listen for RTP packets."""
		while True:
			try:
				data = self.rtpSocket.recv(20480)
				if data:
					rtpPacket = RtpPacket()
					rtpPacket.decode(data)
					
					currFrameNbr = rtpPacket.seqNum()
					print("Current Seq Num: " + str(currFrameNbr))
										
					if currFrameNbr > self.frameNbr: # Discard the late packet
						self.frameNbr = currFrameNbr
						self.updateMovie(self.writeFrame(rtpPacket.getPayload()))
			except:
				# Stop listening upon requesting PAUSE or TEARDOWN
				if self.playEvent.isSet(): 
					break
				
				# Upon receiving ACK for TEARDOWN request,
				# close the RTP socket
				if self.teardownAcked == 1:
					self.rtpSocket.shutdown(socket.SHUT_RDWR)
					self.rtpSocket.close()
					break
					
	def writeFrame(self, data):
		"""Write the received frame to a temp image file. Return the image file."""
		cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
		with open(cachename, "wb") as file:
			file.write(data)
		return cachename
	
	def updateMovie(self, imageFile):
		"""Update the image file as video frame in the GUI."""
		photo = ImageTk.PhotoImage(Image.open(imageFile))
		self.label.configure(image = photo, height=288) 
		self.label.image = photo
		
	def connectToServer(self):
		"""Connect to the Server. Start a new RTSP/TCP session."""
		self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		try:
			self.rtspSocket.connect((self.nodeAddr, self.nodePort))
		except:
			tkinter.messagebox.showwarning('Connection Failed', 'Connection to \'%s\' failed.' %self.nodeAddr)
	
	def sendRtspRequest(self, requestCode):
		"""Send RTSP request to the server."""    
        # Setup request
		if requestCode == self.SETUP and self.state == self.INIT:
			threading.Thread(target=self.recvRtspReply).start()
			self.rtspSeq += 1
			#request = f"SETUP {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\n"
			request = f"SETUP {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nTransport: RTP/UDP; client_port= {self.rtpPort}\n"
			self.requestSent = self.SETUP
        
        # Play request
		elif requestCode == self.PLAY and self.state == self.READY:
			self.rtspSeq += 1
			request = f"PLAY {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nSession: {self.sessionId}\n"
			self.requestSent = self.PLAY
            
		# Pause request
		elif requestCode == self.PAUSE and self.state == self.PLAYING:
			self.rtspSeq += 1
			request = f"PAUSE {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nSession: {self.sessionId}\n"
			self.requestSent = self.PAUSE
            
		# Teardown request
		elif requestCode == self.TEARDOWN and not self.state == self.INIT:
			self.rtspSeq += 1
			request = f"TEARDOWN {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nSession: {self.sessionId}\n"
			self.requestSent = self.TEARDOWN
		else:
			return
        
		# Send the RTSP request using rtspSocket.
		self.rtspSocket.send(request.encode())

		print('\nData sent:\n' + request)
	
	def recvRtspReply(self):
		"""Receive RTSP reply from the server."""
		while True:
			reply = self.rtspSocket.recv(1024)
			
			if reply: 
				self.parseRtspReply(reply.decode("utf-8"))
			
			# Close the RTSP socket upon requesting Teardown
			if self.requestSent == self.TEARDOWN:
				self.rtspSocket.shutdown(socket.SHUT_RDWR)
				self.rtspSocket.close()
				break
	
	def parseRtspReply(self, data):
		"""Parse the RTSP reply from the server."""
		lines = data.split('\n')
		seqNum = int(lines[1].split(' ')[1])
		
		# Process only if the server reply's sequence number is the same as the request's
		if seqNum == self.rtspSeq:
			session = int(lines[2].split(' ')[1])
			# New RTSP session ID
			if self.sessionId == 0:
				self.sessionId = session
			
			# Process only if the session ID is the same
			if self.sessionId == session:
				if int(lines[0].split(' ')[1]) == 200: 
					if self.requestSent == self.SETUP:
						self.state = self.READY	

						# Open RTP port.
						self.openRtpPort() 
      
					elif self.requestSent == self.PLAY:
						self.state = self.PLAYING
						print('\nPLAY sent\n')

					elif self.requestSent == self.PAUSE:
						self.state = self.READY

						# The play thread exits. A new thread is created on resume.
						self.playEvent.set()

					elif self.requestSent == self.TEARDOWN:
						self.state = self.INIT

						# Flag the teardownAcked to close the socket.
						self.teardownAcked = 1 
	
	def openRtpPort(self):
		"""Open RTP socket binded to a specified port."""
		# Create a new datagram socket to receive RTP packets from the server
		self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		
		# Set the timeout value of the socket to 0.5sec
		self.rtpSocket.settimeout(0.5)
		
		try:
			# Bind the socket to the address using the RTP port given by the client user
			self.rtpSocket.bind(('', self.rtpPort))
			print('\nBind to RTP port\n')
		except:
			tkinter.messagebox.showwarning('Unable to Bind', 'Unable to bind PORT=%d' %self.rtpPort)


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

    bootstrapper = sys.argv[1] # 10.0.5.10
    client_id = sys.argv[2]  # Client-1
    client_ip = sys.argv[3] # 10.0.3.20
    
    root = Tk()
    client = Client(root, '10.0.5.1', 30001, 25000, 'movie.Mjpeg', client_id, client_ip, bootstrapper)
    root.mainloop()
    
if __name__ == "__main__":
    main()