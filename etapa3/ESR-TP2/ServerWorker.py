from random import randint
import sys, traceback, threading, socket

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
	
	def __init__(self, neighborInfo):
		self.neighborInfo = neighborInfo
		self.neighborInfo['state'] = self.INIT 		 # Inicializa o estado
  		
	def run(self):
		threading.Thread(target=self.recvRtspRequest).start()
	
	def recvRtspRequest(self):
		"""Receive RTSP request from the client."""
		connSocket = self.neighborInfo['rtspSocket']
		while True:            
			data = connSocket.recv(256)
			if data:
				print("Data received:\n" + data.decode("utf-8") + "\n")
				self.processRtspRequest(data.decode("utf-8"))
	
	def processRtspRequest(self, data):
		"""Process RTSP request sent from the client."""
		# Get the request type
		request = data.split('\n')
		line1 = request[0].split(' ')
		requestType = line1[0]
		for line in request:
			if "Indice:" in line:
				# Extrair o valor do índice
				indice = int(line.split(':')[1].strip())
				break

		# Get the media file name
		filename = line1[1]
		self.neighborInfo['session'] = filename
		
		# Get the RTSP sequence number 
		seq = request[1].split(' ')
		
		# Process SETUP request
		if requestType == self.SETUP:
			if self.neighborInfo['state'] == self.INIT:
				# Update state
				print("processing SETUP\n")
				
				try:
					self.neighborInfo['videoStream'] = VideoStream(filename)
					self.neighborInfo['state'] = self.READY
				except IOError:
					self.replyRtsp(self.FILE_NOT_FOUND_404, seq[1], self.neighborInfo['session'])
				
				# Send RTSP reply
				self.replyRtsp(self.OK_200, seq[1], self.neighborInfo['session'])

		# Process PLAY request 		
		elif requestType == self.PLAY:
			if self.neighborInfo['state'] == self.READY:
				print("processing PLAY\n")
				self.neighborInfo['state'] = self.PLAYING
				
				# Create a new socket for RTP/UDP
				self.neighborInfo['rtpSocket'] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
				
				self.replyRtsp(self.OK_200, seq[1], self.neighborInfo['session'])
				
				# Create a new thread and start sending RTP packets
				self.neighborInfo['event'] = threading.Event()
				self.neighborInfo['worker']= threading.Thread(target=self.sendRtp) 
				self.neighborInfo['worker'].start()
		
		# Process PAUSE request
		elif requestType == self.PAUSE:
			if self.neighborInfo['state'] == self.PLAYING:
				print("processing PAUSE\n")
				self.neighborInfo['state'] = self.READY
				
				self.neighborInfo['event'].set()
			
				self.replyRtsp(self.OK_200, seq[1], self.neighborInfo['session'])
		
		# Process TEARDOWN request
		elif requestType == self.TEARDOWN:
			print("processing TEARDOWN\n")

			self.neighborInfo['event'].set()
			
			self.replyRtsp(self.OK_200, seq[1], self.neighborInfo['session'])
			
			# Close the RTP socket
			self.neighborInfo['videoStream'].release() 
			self.neighborInfo['rtpSocket'].close()
   					
	def sendRtp(self):
		"""Send RTP packets over UDP."""
		while True:
			self.neighborInfo['event'].wait(0.05) 
			
			# Stop sending if request is PAUSE or TEARDOWN
			if self.neighborInfo['event'].isSet(): 
				break 
				
			data = self.neighborInfo['videoStream'].nextFrame()
			if data: 
				frameNumber = self.neighborInfo['videoStream'].frameNbr()
				try:
					address = self.neighborInfo['ip']
					print("Enviar pacotes UDP para ADRESS :", address)
					port = int(self.neighborInfo['rtp_port'])
					self.neighborInfo['rtpSocket'].sendto(self.makeRtp(data, frameNumber),(address, port))
				except:
					print("Connection Error")
					#print('-'*60)
					#traceback.print_exc(file=sys.stdout)
					#print('-'*60)

	def makeRtp(self, payload, frameNbr):
		"""RTP-packetize the video data."""
		version = 2
		padding = 0
		extension = 0
		cc = 0
		marker = 0
		#pt = 26 # MJPEG type
		pt = 98
		seqnum = frameNbr
		ssrc = 0 
		
		rtpPacket = RtpPacket()
		
		rtpPacket.encode(version, padding, extension, cc, seqnum, marker, pt, ssrc, payload)
		
		return rtpPacket.getPacket()
		
	def replyRtsp(self, code, seq, session):
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
