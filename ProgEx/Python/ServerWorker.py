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
	
	clientInfo = {}
	
	def __init__(self, clientInfo):
		self.clientInfo = clientInfo
		self.sessions = {}
		
	def run(self):
		threading.Thread(target=self.recvRtspRequest).start()
	
	def recvRtspRequest(self):
		"""Receive RTSP request from the client."""
		connSocket = self.clientInfo['rtspSocket'][0]
		while True:            
			data = connSocket.recv(256)
			if data:
				print("Data received:\n" + data.decode("utf-8"))
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

		if indice not in self.sessions:
			self.sessions[indice] = {
				'state': self.INIT,
				'videoStream': None,
				'rtpSocket': None,
				'event': None,
				'worker': None,
				'session': randint(100000, 999999), # Generate a randomized RTSP session ID
				'nodeRtpPort': None,
				'nodeRtpIp': None
			}
		session = self.sessions[indice]
		
		# Get the media file name
		filename = line1[1]
		
		# Get the RTSP sequence number 
		seq = request[1].split(' ')
		
		# Process SETUP request
		if requestType == self.SETUP:
			if session['state'] == self.INIT:
				# Update state
				print("processing SETUP\n")
				
				try:
					session['videoStream'] = VideoStream(filename)
					session['state'] = self.READY
				except IOError:
					self.replyRtsp(self.FILE_NOT_FOUND_404, seq[1], session)
				
				# Send RTSP reply
				self.replyRtsp(self.OK_200, seq[1], session)
    
				# Extrai IP e porta UDP do Node
				for line in request:
					if "Node-RTP-Port:" in line:
						session['nodeRtpPort'] = int(line.split(' ')[1])
					if "Node-RTP-IP:" in line:
						session['nodeRtpIp'] = line.split(' ')[1]
	
		# Process PLAY request 		
		elif requestType == self.PLAY:
			if session['state'] == self.READY:
				print("processing PLAY\n")
				session['state'] = self.PLAYING
				
				# Create a new socket for RTP/UDP
				session['rtpSocket'] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
				
				self.replyRtsp(self.OK_200, seq[1], session)
				
				# Create a new thread and start sending RTP packets
				session['event'] = threading.Event()
				session['worker']= threading.Thread(target=self.sendRtp, args=(session,)) 
				session['worker'].start()
		
		# Process PAUSE request
		elif requestType == self.PAUSE:
			if session['state'] == self.PLAYING:
				print("processing PAUSE\n")
				session['state'] = self.READY
				
				session['event'].set()
			
				self.replyRtsp(self.OK_200, seq[1], session)
		
		# Process TEARDOWN request
		elif requestType == self.TEARDOWN:
			print("processing TEARDOWN\n")

			session['event'].set()
			
			self.replyRtsp(self.OK_200, seq[1], session)
			
			# Close the RTP socket
			session['videoStream'].release() 
			session['rtpSocket'].close()
   			
			
	def sendRtp(self, session):
		"""Send RTP packets over UDP."""
		while True:
			session['event'].wait(0.05) 
			
			# Stop sending if request is PAUSE or TEARDOWN
			if session['event'].isSet(): 
				break 
				
			data = session['videoStream'].nextFrame()
			if data: 
				frameNumber = session['videoStream'].frameNbr()
				try:
					address = session['nodeRtpIp']
					print("Enviar pacotes UDP para ADRESS :", address)
					port = int(session['nodeRtpPort'])
					session['rtpSocket'].sendto(self.makeRtp(data, frameNumber),(address, port))
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
			reply = 'RTSP/1.0 200 OK\nCSeq: ' + seq + '\nSession: ' + str(session['session'])
			connSocket = self.clientInfo['rtspSocket'][0]
			connSocket.send(reply.encode())
		
		# Error messages
		elif code == self.FILE_NOT_FOUND_404:
			print("404 NOT FOUND")
		elif code == self.CON_ERR_500:
			print("500 CONNECTION ERROR")
