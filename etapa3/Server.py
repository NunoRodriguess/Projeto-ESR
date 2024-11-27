import sys, socket, threading, time

from control_protocol_pb2 import ControlMessage
from control_protocol_pb2 import FloodingMessage
from ServerWorker import ServerWorker

class Server:	
    def __init__(self,server_ip, server_id, control_port=50051, data_port=50052, server_rtsp_port=30000, bootstrapper_host='localhost', bootstrapper_port=5000):
        self.server_id = server_id
        self.server_ip = server_ip
        self.control_port = control_port
        self.data_port = data_port
        self.bootstrapper = (bootstrapper_host, bootstrapper_port)
        
        self.neighbors = {}  # Dicionário para armazenar informações dos vizinhos
        self.neighbors_lock = threading.Lock()  # Lock para sincronizar o acesso aos vizinhos
        
        self.server_rtsp_port = server_rtsp_port
        self.rtspSocket = None
        
        self.active_workers = {}
        self.active_workers_lock = threading.Lock() 
        
        self.latest_flooding_message = {}
        self.flooding_lock = threading.Lock()
        
        self.movies = {
            "movie.Mjpeg",
            "movie-copy.Mjpeg",
            "output.avi"
        }
        
        self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.rtspSocket.bind(('', self.server_rtsp_port))
        self.rtspSocket.listen(10)
        print(f"Server RTSP escutando em :{self.server_rtsp_port}")

	
    def send_control_message_tcp(self, socket, control_message):
        header = b'\x01'
        socket.sendall(header + control_message.SerializeToString())

    def send_flooding_message_tcp(self, socket, flooding_message):
        header = b'\x02' 
        socket.sendall(header + flooding_message.SerializeToString())
    
    def send_control_message_udp(self, socket, address, control_message):
        header = b'\x01'  # Header para ControlMessage
        socket.sendto(header + control_message.SerializeToString(), address)

    def send_flooding_message_udp(self, socket, address, flooding_message):
        header = b'\x02'  # Header para FloodingMessage
        socket.sendto(header + flooding_message.SerializeToString(), address)
        
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
            control_message.node_id = self.server_id
            control_message.node_ip = self.server_ip
            control_message.control_port = self.control_port
            control_message.data_port = self.data_port
            control_message.node_type = "server"
            control_message.rtsp_port = self.server_rtsp_port
            
            # Envia a mensagem de registro
            self.send_control_message_tcp(s, control_message)
            
            # Recebe e processa a resposta
            header = s.recv(1)  # Lê o primeiro byte
            data = s.recv(1024)  # Lê o restante da mensagem
            
            if header == b'\x01':  # ControlMessage
                response_message = ControlMessage()
                response_message.ParseFromString(data)
                
                if response_message.type == ControlMessage.REGISTER_RESPONSE:
                    print(f"Server {self.server_id} registered")
                    with self.neighbors_lock:
                        self.neighbors.clear()  # Limpa vizinhos antigos para o caso de ser uma reativação
                        for neighbor in response_message.neighbors:
                            self.neighbors[neighbor.node_ip] = {
                                "node_id": neighbor.node_id,
                                "control_port": neighbor.control_port,
                                "data_port": neighbor.data_port,
                                "node_type": neighbor.node_type,
                                "status": "active",
                                "failed-attempts": 0,
                                "rtsp_port": neighbor.rtsp_port
                            }
                    print(f"Server {self.server_id} neighbors: {self.neighbors}")
                    # Após o registro, notifica os vizinhos sobre o registro
                    self.notify_neighbors_registration()
                else:
                    print(f"Unexpected response type: {response_message.type}")
                    
    def notify_neighbors_registration(self):
        """
        Notifica os vizinhos que o nó está registrado e que pode haver atualizações.
        """
        with self.neighbors_lock:
            neighbors_snapshot = self.neighbors.copy()
            
        for neighbor_ip, neighbor_info in neighbors_snapshot.items():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((neighbor_ip, neighbor_info['control_port']))
                    notify_message = ControlMessage()
                    notify_message.type = ControlMessage.UPDATE_NEIGHBORS
                    notify_message.node_id = self.server_id
                    notify_message.node_ip = self.server_ip
                    notify_message.control_port = self.control_port
                    notify_message.data_port = self.data_port
                    notify_message.node_type = "server"
                    notify_message.rtsp_port = self.server_rtsp_port
                    
                    self.send_control_message_tcp(s,notify_message)
                    print(f"Notified neighbor {neighbor_info['node_id']} of registration.")

            except Exception as e:
                print(f"Failed to notify neighbor {neighbor_info['node_id']}: {e}")
                
    def start(self):
        """
        Inicia o nó, registrando-o com o Bootstrapper e iniciando os servidores
        de controle e dados em threads separadas.
        """
        
        self.register_with_bootstrapper()
        threading.Thread(target=self.control_server).start()  # Inicia o servidor de controle em uma thread separada
        threading.Thread(target=self.send_ping_to_neighbors).start()  # Enviar PING aos vizinhos
        threading.Thread(target=self.send_flood_to_neighbors).start() # Enviar FLOODING aos vizinhos

    def control_server(self):
        """
        Inicia o servidor de controle que escuta em uma porta específica para conexões de outros nós.
        Lida com mensagens de controle como PING e atualizações de vizinhos.
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', self.control_port))
            s.listen()
            print(f"Server {self.server_id} listening on control port {self.control_port}")
            while True:
                conn, addr = s.accept()
                threading.Thread(target=self.handle_control_connection, args=(conn, addr)).start()

    def handle_control_connection(self, conn, addr):
        print(f"Connection from {addr} established.")
        with conn:
            while True:
                # Lê o header para determinar o tipo de mensagem
                header = conn.recv(1)  # Lê o primeiro byte
                if not header:
                    break  # Conexão fechada pelo cliente
                
                data = conn.recv(1024)  # Lê o restante da mensagem
                if not data:
                    break
                
                if header == b'\x01':  # ControlMessage
                    control_message = ControlMessage()
                    try:
                        control_message.ParseFromString(data)
                        if control_message.type == ControlMessage.UPDATE_NEIGHBORS:
                            self.handle_update_neighbors(control_message)
                        elif control_message.type == ControlMessage.PING:
                            self.handle_ping(control_message, conn)
                        else:
                            raise ValueError(f"Unknown ControlMessage type: {control_message.type}")
                    except Exception as e:
                        print(f"Failed to parse as ControlMessage: {e}")
                        
                elif header == b'\x02':  # FloodingMessage
                    flooding_message = FloodingMessage()
                    try:
                        flooding_message.ParseFromString(data)
                            
                        if flooding_message.type == FloodingMessage.ACTIVATE_ROUTE:
                            print("ATIVAÇÃO DO NODE RECEBIDA")
                            self.receive_neighbors_info(flooding_message, flooding_message.stream_ids[0])
                            
                        elif flooding_message.type == FloodingMessage.DEACTIVATE_ROUTE:
                            print("DESATIVAÇÃO DO NODE RECEBIDA")

                        else:
                            raise ValueError(f"Unknown FloodingMessage type: {flooding_message.type}")
                    except Exception as e:
                        print(f"Failed to parse as FloodingMessage: {e}")
                else:
                    print("Unknown message header received. Ignoring.")
                    continue

    def receive_neighbors_info(self, flooding_message, filename):
        # Atualiza o flooding_message mais recente
        with self.neighbors_lock:
            if 'rtp_port' not in self.neighbors[flooding_message.source_ip]:
                self.neighbors[flooding_message.source_ip]['rtp_port'] = flooding_message.rtp_port

        threading.Thread(target=self.openRTSP_socket, args=(filename, )).start()  # Chama a função para iniciar o socket 
                        
    def handle_update_neighbors(self, control_message):
        print(f"Updating neighbors with {control_message.node_id}")
        neighbor_id = control_message.node_id
        neighbor_ip = control_message.node_ip
        control_port = control_message.control_port
        data_port = control_message.data_port
        node_type = control_message.node_type
        rtsp_port = control_message.rtsp_port

        with self.neighbors_lock: 
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
                    "failed-attempts": 0,
                    "status": "active",  # Define o status como ativo,
                    "rtsp_port": rtsp_port
                }
                print(f"Added new neighbor: {neighbor_id}")
                
        print(f"Server {self.server_id} neighbors: {self.neighbors}")
        
    def send_ping_to_neighbors(self):
        while True:
            print("Waiting for 15 seconds...")
            time.sleep(15)

            # Criação de uma cópia dos vizinhos para evitar o lock por longos períodos
            with self.neighbors_lock:
                neighbors_snapshot =  self.neighbors.copy()

            for neighbor_ip, neighbor_info in neighbors_snapshot.items():
                # Verificar status do vizinho e tentativas falhas (não precisa de lock, já capturado no snapshot)
                if neighbor_info.get("status") == "inactive":
                    continue  # Ignora vizinhos inativos

                if neighbor_info.get("failed-attempts", 0) >= 2:
                    print(f"Neighbor {neighbor_info['node_id']} considered inactive due to lack of PONG response.")
                    with self.neighbors_lock:  # Atualiza o status do vizinho de forma segura
                        self.neighbors[neighbor_ip]["status"] = "inactive"
                    continue

                try:
                    # Envia o PING ao vizinho
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.connect((neighbor_ip, neighbor_info['control_port']))
                        
                        # Criação e envio da mensagem de PING
                        ping_message = ControlMessage()
                        ping_message.type = ControlMessage.PING
                        ping_message.node_ip = self.server_ip
                        ping_message.node_id = self.server_id
                        ping_message.accumulated_time = 0
                        self.send_control_message_tcp(s, ping_message)
                        print(f"Sent PING to neighbor {neighbor_info['node_id']}")

                        # Espera pela resposta PONG
                        header = s.recv(1)  # Lê o primeiro byte
                        data = s.recv(1024)  # Lê o restante da mensagem
                        if data:
                            if header == b'\x01':  # ControlMessage
                                response_message = ControlMessage()
                                response_message.ParseFromString(data)
                                if response_message.type == ControlMessage.PONG:
                                    print(f"Received PONG from neighbor {response_message.node_id}")

                                    # Atualiza o status do vizinho de forma segura
                                    with self.neighbors_lock:
                                        self.neighbors[neighbor_ip]["failed-attempts"] = 0
                                        self.neighbors[neighbor_ip]["status"] = "active"

                except Exception as e:
                    print(f"Failed to send PING to neighbor {neighbor_info['node_id']}: {e}")
                    # Incrementa tentativas falhas de forma segura
                    with self.neighbors_lock:
                        if neighbor_ip in self.neighbors:  # Verifica se o vizinho ainda existe
                            self.neighbors[neighbor_ip]["failed-attempts"] = self.neighbors[neighbor_ip].get("failed-attempts", 0) + 1

    def handle_ping(self, control_message, conn):
        # Responder a uma mensagem de ping
        print(f"Received PING from neighbor {control_message.node_id}")
        pong_message = ControlMessage()
        pong_message.type = ControlMessage.PONG
        pong_message.node_id = self.server_id
        self.send_control_message_tcp(conn, pong_message)
        print(f"Sent PONG to neighbor {control_message.node_id}")
                
    def send_flood_to_neighbors(self):
        while True:
            with self.neighbors_lock:
                neighbors_snapshot =  self.neighbors.copy()
                
            for neighbor_ip, neighbor_info in neighbors_snapshot.items():
                # Verificar se o vizinho já está marcado como inativo
                if neighbor_info.get("status") == "active":
                    self.send_flooding_message(neighbor_ip, neighbor_info)    
            time.sleep(15)
                
    def send_flooding_message(self, neighbor_ip, neighbor_info):
        """
        Envia uma mensagem de flooding para todos os vizinhos.
        """
        flooding_message = FloodingMessage()
        flooding_message.type = FloodingMessage.FLOODING_UPDATE
        flooding_message.source_id = self.server_id
        flooding_message.source_ip = self.server_ip
        flooding_message.stream_ids.extend(self.movies)
        flooding_message.route_state = "active"
        flooding_message.control_port = self.control_port
        flooding_message.rtsp_port = self.server_rtsp_port
        
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((neighbor_ip, neighbor_info['control_port']))
                self.send_flooding_message_tcp(s, flooding_message)
                print(f"Sent flooding message to {neighbor_info['node_id']}")

        except Exception as e:
            print(f"Failed to send flooding message to {neighbor_info['node_id']}: {e}")
          
    def openRTSP_socket(self, filename):
        """
        Abre o socket RTSP, aceita conexões e gerencia sessões de vídeo para cada fluxo.
        """
        # Chama o método para aceitar conexões em loop
        while True:
            try:
                rtsp_socket, neighbor_address = self.rtspSocket.accept()
                print(f"Conexão aceita de {neighbor_address}")
                
                data = rtsp_socket.recv(256)
                if data:
                    decoded_data = data.decode("utf-8")
                    print("Data received:\n" + decoded_data + "\n")
                    if not decoded_data.startswith("ACTIVE"):
                        request = decoded_data.splitlines()
                        line1 = request[0].split(' ')
                        requestType = line1[0]
                        filename = line1[1]
                        seq = request[1].split(' ')
                        if requestType != "SETUP": # Ver melhor isto
                            ip = request[3].split(' ')[1]
                        else:
                            ip = request[2].split(' ')[1]
                            
                        # Iniciar thread para lidar com a conexão
                        threading.Thread(
                            target=self.handle_rtsp_connection,
                            args=(rtsp_socket, requestType, filename, ip, seq),
                            daemon=True
                        ).start()
                
                    else:
                        request = decoded_data.splitlines()
                        filename = request[0].split(' ')[1]
                        ip = request[1].split(' ')[1]
                        rtp_port = request[2].split(' ')[1]
                            
                        # Iniciar thread para lidar com a conexão
                        threading.Thread(
                            target=self.handle_rtsp_connection2,
                            args=(rtsp_socket, filename, ip, int(rtp_port)),
                            daemon=True
                        ).start()
                        
            except Exception as e:
                print(f"Erro no loop de aceitação: {e}")
    
    def handle_rtsp_connection(self, rtsp_socket, requestType, filename, sender_ip, seq):
        """
        Lida com a conexão RTSP recebida.
        """
        try:
            # Informações do cliente (vizinho)
            with self.neighbors_lock:
                new_rtp_port = self.neighbors[sender_ip]["rtp_port"]

            # Processar a conexão
            print(f"Gerindo a conexão para {sender_ip}:{new_rtp_port}, fluxo {filename}")

            # Verifica se já existe um ServerWorker para o fluxo
            with self.active_workers_lock:
                existing_worker = self.active_workers.get(filename, None)
                    
            if existing_worker:
                # Atualiza o ServerWorker existente para o novo vizinho
                existing_worker.update_neighborInfo(sender_ip, rtsp_socket, new_rtp_port)
                print(f"Atualizada sessão existente para o fluxo {filename} com o vizinho {sender_ip}:{new_rtp_port}")
                existing_worker.processRtspRequest(requestType, filename, seq)
            else:
                # Cria um novo ServerWorker para o fluxo
                neighborInfo = {
                    "ip": sender_ip,
                    "rtp_port": new_rtp_port,
                    "rtspSocket": rtsp_socket
                }
                print(f"Criando nova sessão para o fluxo {filename} com o vizinho {sender_ip}:{new_rtp_port}")
                worker = ServerWorker(neighborInfo, self.server_ip)
                with self.active_workers_lock:
                    self.active_workers[filename] = worker
                worker.processRtspRequest(requestType, filename, seq)
        except Exception as e:
            print(f"Erro ao processar a conexão RTSP: {e}")
       
    def handle_rtsp_connection2(self, rtsp_socket, filename, sender_ip, rtp_port):
        """
        Lida com a conexão RTSP recebida.
        """
        try:
            # Processar a conexão
            print(f"Gerindo a conexão para {sender_ip}:{rtp_port}, fluxo {filename}")

            # Verifica se já existe um ServerWorker para o fluxo
            with self.active_workers_lock:
                existing_worker = self.active_workers.get(filename, None)
                    
            if existing_worker:
                # Atualiza o ServerWorker existente para o novo vizinho
                existing_worker.update_neighborInfo(sender_ip, rtsp_socket, rtp_port)
                print(f"Atualizada sessão existente para o fluxo {filename} com o vizinho {sender_ip}:{rtp_port}")
            else:
                # Cria um novo ServerWorker para o fluxo
                neighborInfo = {
                    "ip": sender_ip,
                    "rtp_port": rtp_port,
                    "rtspSocket": rtsp_socket
                }
                print(f"Criando nova sessão para o fluxo {filename} com o vizinho {sender_ip}:{rtp_port}")
                worker = ServerWorker(neighborInfo, self.server_ip)
                with self.active_workers_lock:
                    self.active_workers[filename] = worker
        except Exception as e:
            print(f"Erro ao processar a conexão RTSP: {e}")
            
def main():
    
    if len(sys.argv) != 5:
        print("Usage: python Server.py <server_rtsp_port> <bootstrapper_ip> <server_id> <server_ip>")
        sys.exit(1)
    
    server_rtsp_port = int(sys.argv[1])
    bootstrapper = sys.argv[2] # 10.0.1.10
    server_id = sys.argv[3]  #  Server
    server_ip = sys.argv[4] # 10.0.0.1
    control_port = 50051  # Porta de controle padrão
    data_port = 50052     # Porta de dados padrão

    server = Server(server_ip, server_id, server_rtsp_port, control_port, data_port, bootstrapper)
    server.start()
        
if __name__ == "__main__":
	main()



