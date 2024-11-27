from random import randint
import sys, traceback, threading, socket, select, time

from VideoStream import VideoStream
from RtpPacket import RtpPacket

class ServerWorker:
	SETUP = 'SETUP'
	PLAY = 'PLAY'
	PAUSE = 'PAUSE'
	TEARDOWN = 'TEARDOWN'
	
	INIT = 0
	READY = 1
	PLAYING = 2
	state = INIT

	OK_200 = 0
	FILE_NOT_FOUND_404 = 1
	CON_ERR_500 = 2
	
	neighborInfo = {}
	
	def __init__(self, neighborInfo, server_ip):
		self.server_ip = server_ip
		self.neighborInfo = {} 
		self.neighborInfo = neighborInfo
		self.neighbor_lock = threading.Lock()
		self.active = True

	def update_neighborInfo(self, new_ip, rtspSocket, rtp_port):
		"""
		Atualiza o destino da sessão de vídeo para um novo IP e porta RTSP sem interromper a sessão.
		"""
		with self.neighbor_lock:
			self.neighborInfo["ip"] = new_ip
			self.neighborInfo["rtp_port"] = rtp_port
			self.neighborInfo["rtspSocket"] = rtspSocket
		print(f"Video session updated to new destination {new_ip}")

	def processRtspRequest(self, requestType, filename, seq):
		"""Process RTSP request sent from the client."""
		# Get the request type
		with self.neighbor_lock:
			if 'state' not in self.neighborInfo:
					self.neighborInfo['state'] = self.INIT
					self.neighborInfo['session'] = filename

		with self.neighbor_lock:
			neighbors_snapshot =  self.neighborInfo.copy()

		# Process SETUP request
		if requestType == self.SETUP:
			if neighbors_snapshot['state'] == self.INIT:
				# Update state
				print("processing SETUP\n")
				
				with self.neighbor_lock:
					try:
						self.neighborInfo['videoStream'] = VideoStream(filename)
						self.neighborInfo['state'] = self.READY
					except IOError:
						self.replyRtsp(self.FILE_NOT_FOUND_404, seq[1], self.neighborInfo['session'], filename)
					
					# Send RTSP reply
					self.replyRtsp(self.OK_200, seq[1], self.neighborInfo['session'], filename)

		# Process PLAY request 		
		elif requestType == self.PLAY:
			if neighbors_snapshot['state'] == self.READY:
				print("processing PLAY\n")
				with self.neighbor_lock:
					self.neighborInfo['state'] = self.PLAYING
				
					# Create a new socket for RTP/UDP
					self.neighborInfo['rtpSocket'] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
				
					self.replyRtsp(self.OK_200, seq[1], self.neighborInfo['session'], filename)
					
					# Create a new thread and start sending RTP packets
					self.neighborInfo['event'] = threading.Event()
					self.neighborInfo['worker']= threading.Thread(target=self.sendRtp, args=(filename,)) 
					self.neighborInfo['worker'].start()
		
		# Process PAUSE request
		elif requestType == self.PAUSE:
			if neighbors_snapshot['state'] == self.PLAYING:
				print("processing PAUSE\n")
				with self.neighbor_lock:
					self.neighborInfo['state'] = self.READY
					
					self.neighborInfo['event'].set()
				
					self.replyRtsp(self.OK_200, seq[1], self.neighborInfo['session'], filename)
		
		# Process TEARDOWN request
		elif requestType == self.TEARDOWN:
			print("processing TEARDOWN\n")
			with self.neighbor_lock:

				self.neighborInfo['event'].set()
				
				self.replyRtsp(self.OK_200, seq[1], self.neighborInfo['session'], filename)
				
				# Close the RTP socket
				self.neighborInfo['videoStream'].release() 
				self.neighborInfo['rtpSocket'].close()

	def sendRtp(self, filename):
		"""Send RTP packets over UDP."""
		current_ip = None
		current_port = None
		current_socket = None

		while True:
			with self.neighbor_lock:
				neighbors_snapshot =  self.neighborInfo.copy()
				
			# Verificar se o envio deve ser pausado ou interrompido
			neighbors_snapshot['event'].wait(0.05)

			if neighbors_snapshot['event'].isSet(): 
				break

			# Obter os dados do próximo frame
			data = neighbors_snapshot['videoStream'].nextFrame()

			if data:
				frameNumber = neighbors_snapshot['videoStream'].frameNbr()

				# Bloquear e verificar se há alterações nos dados do vizinho
				with self.neighbor_lock:
					neighbors_snapshot =  self.neighborInfo.copy()
				
				ip = neighbors_snapshot.get('ip')
				port = neighbors_snapshot.get('rtp_port', 0)
				if ip != current_ip:
					if current_socket:
						current_socket.close()
					current_ip = ip
					current_port = port
					current_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
					print(f"RTP destination updated to {current_ip}:{current_port}")

				# Enviar pacote RTP usando o socket atualizado
				if current_socket and current_ip and current_port and self.active:
					try:
						print(f"Sending frame {frameNumber} of video {filename} to {current_ip}:{current_port}")
						current_socket.sendto(self.makeRtp(data, frameNumber, filename, self.server_ip), (current_ip, current_port))
					except Exception as e:
						print(f"Error sending RTP packet: {e}")

	def makeRtp(self, payload, frameNbr, filename, sender_ip):
		"""RTP-packetize the video data."""
		version = 2
		padding = 0
		extension = 0
		cc = 0
		marker = 0
		pt = 26 # MJPEG type
		seqnum = frameNbr
		ssrc = 0 

		rtpPacket = RtpPacket()
		rtpPacket.encode(version, padding, extension, cc, seqnum, marker, pt, ssrc, payload, filename, sender_ip)
		
		return rtpPacket.getPacket()
		
	def replyRtsp(self, code, seq, session, filename):
		"""Send RTSP reply to the client."""
		if code == self.OK_200:
			#print("200 OK")
			reply = 'RTSP/1.0 200 OK\nCSeq: ' + seq + '\nSession: ' + session
			connSocket = self.neighborInfo['rtspSocket']
			connSocket.send(reply.encode())
		
		# Error messages
		elif code == self.FILE_NOT_FOUND_404:
			print("404 NOT FOUND")
		elif code == self.CON_ERR_500:
			print("500 CONNECTION ERROR")
