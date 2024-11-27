import sys
from time import time
HEADER_SIZE = 12

class RtpPacket:	
	header = bytearray(HEADER_SIZE)
	
	def __init__(self):
		pass
		
	def encode(self, version, padding, extension, cc, seqnum, marker, pt, ssrc, payload, filename, sender_ip):
		"""Encode the RTP packet with header fields and payload."""
		timestamp = int(time())
		header = bytearray(HEADER_SIZE) 
		header[0] = (header[0] | version << 6) & 0xC0; # 2 bits
		header[0] = (header[0] | padding << 5); # 1 bit
		header[0] = (header[0] | extension << 4); # 1 bit
		header[0] = (header[0] | (cc & 0x0F)); # 4 bits
		header[1] = (header[1] | marker << 7); # 1 bit
		header[1] = (header[1] | (pt & 0x7f)); # 7 bits
		header[2] = (seqnum >> 8); 
		header[3] = (seqnum & 0xFF);
		header[4] = (timestamp >> 24);
		header[5] = (timestamp >> 16) & 0xFF;
		header[6] = (timestamp >> 8) & 0xFF;
		header[7] = (timestamp & 0xFF);
		header[8] = (ssrc >> 24);
		header[9] = (ssrc >> 16) & 0xFF;
		header[10] = (ssrc >> 8) & 0xFF;
		header[11] = ssrc & 0xFF
		# set header and  payload
		self.header = header
		
		filename_bytes = filename.encode('utf-8')
		sender_ip_bytes = sender_ip.encode('utf-8')
		# Incluindo o nome do arquivo e o ip de quem envia o pacote no payload antes do vídeo
		payload = filename_bytes + b'\0' + sender_ip_bytes + b'\0' + payload  # Adicionando um terminador null para o filename e para o sender_ip

		self.payload = payload
  
	def decode(self, byteStream):
		"""Decode the RTP packet and extract filename and sender IP if present."""
		self.header = bytearray(byteStream[:HEADER_SIZE])
		self.payload = byteStream[HEADER_SIZE:]

		filename = None
		sender_ip = None
		try:
			# Extract filename by looking for the first null terminator
			filename_end_index = self.payload.index(0)  # Null byte
			filename = self.payload[:filename_end_index].decode('utf-8')
			remaining_payload = self.payload[filename_end_index + 1:]

			# Extract sender IP by looking for the next null terminator
			sender_ip_end_index = remaining_payload.index(0)
			sender_ip = remaining_payload[:sender_ip_end_index].decode('utf-8')

			# Update the payload to exclude filename and sender_ip
			self.payload = remaining_payload[sender_ip_end_index + 1:]
		except ValueError:
			# Handle the case where filename or sender_ip is not present
			pass

		return filename, sender_ip

	def updateSenderIp(self, byteStream, new_sender_ip):
		"""Update the sender_ip in the RTP packet."""
		try:
			self.header = bytearray(byteStream[:HEADER_SIZE])
			self.payload = byteStream[HEADER_SIZE:]
   
			# Extrair o nome do arquivo do início do payload
			filename_end_index = self.payload.index(0)  # Null byte
			filename = self.payload[:filename_end_index].decode('utf-8')
			remaining_payload = self.payload[filename_end_index + 1:]

			# Extrair o sender_ip existente
			sender_ip_end_index = remaining_payload.index(0)  # Próximo null byte
			remaining_payload = remaining_payload[sender_ip_end_index + 1:]  # Atualizar para ignorar o sender_ip antigo

			# Codificar o novo sender_ip
			new_sender_ip_bytes = new_sender_ip.encode('utf-8') 

			# Reconstruir o payload com o novo sender_ip
			self.payload = filename.encode('utf-8') + b'\0' + new_sender_ip_bytes + b'\0' + remaining_payload

		except ValueError:
			print("Erro ao atualizar o sender_ip: Payload malformado.")
	
	def version(self):
		"""Return RTP version."""
		return int(self.header[0] >> 6)
	
	def seqNum(self):
		"""Return sequence (frame) number."""
		seqNum = self.header[2] << 8 | self.header[3]
		return int(seqNum)
	
	def timestamp(self):
		"""Return timestamp."""
		timestamp = self.header[4] << 24 | self.header[5] << 16 | self.header[6] << 8 | self.header[7]
		return int(timestamp)
	
	def payloadType(self):
		"""Return payload type."""
		pt = self.header[1] & 127
		return int(pt)
	
	def getPayload(self):
		"""Return payload."""
		return self.payload
		
	def getPacket(self):
		"""Return RTP packet."""
		return self.header + self.payload

	def printheader(self):
		print("[RTP Packet] Version: ...")