import sys, socket, threading, time

from control_protocol_pb2 import ControlMessage
from control_protocol_pb2 import FloodingMessage
from ServerWorker import ServerWorker

class Server:	
    def __init__(self,server_ip, server_id, server_type, control_port=50051, data_port=50052, server_rtsp_port=30000, bootstrapper_host='localhost', bootstrapper_port=5000):
        self.server_id = server_id
        self.server_ip = server_ip
        self.control_port = control_port
        self.data_port = data_port
        self.neighbors = {}  # Dicionário para armazenar informações dos vizinhos
        self.bootstrapper = (bootstrapper_host, bootstrapper_port)
        self.lock = threading.Lock()  # Lock para sincronizar o acesso aos vizinhos
        self.server_type = server_type
        self.server_rtsp_port = server_rtsp_port
        self.neighbors_info = {}
        self.neighbors_rtsp = None
        self.movies = {
            "1" : "movie.Mjpeg"
        }
	
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
            control_message.node_type = self.server_type
            
            # Envia a mensagem de registro
            s.send(control_message.SerializeToString())
            
            # Recebe e processa a resposta
            data = s.recv(1024)
            if data:
                response_message = ControlMessage()
                response_message.ParseFromString(data)
                
                if response_message.type == ControlMessage.REGISTER_RESPONSE:
                    print(f"Server {self.server_id} registered")
                    self.neighbors.clear()  # Limpa vizinhos antigos para o caso de ser uma reativação
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
                    print(f"Server {self.server_id} neighbors: {self.neighbors}")
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
                    notify_message.node_id = self.server_id
                    notify_message.node_ip = self.server_ip
                    notify_message.control_port = self.control_port
                    notify_message.data_port = self.data_port
                    notify_message.node_type = self.server_type
                    s.send(notify_message.SerializeToString())
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

                        # Atualizar vizinhos
                        if control_message.type == ControlMessage.UPDATE_NEIGHBORS:
                            self.handle_update_neighbors(control_message)
                        
                        # Enviar ping aos vizinhos (só para os nodes)
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
                            
                            # Ativa a rota
                            if flooding_message.type == FloodingMessage.ACTIVATE_ROUTE:
                                print("Pronto para receber pedidos RTSP\n")
                                self.receive_neighbors_info(flooding_message)    
                            else:
                                raise ValueError(f"Unknown FloodingMessage type: {flooding_message.type}")
                        
                        except Exception as e:
                            # Se falhar novamente, ignora a mensagem
                            print(f"Failed to parse as FloodingMessage: {e}")
                            continue  # Ignora a mensagem se não conseguir analisá-la

    def receive_neighbors_info(self, flooding_message):
        self.neighbors_info.setdefault(flooding_message.source_ip, {})
        if 'rtsp_port' not in self.neighbors_info[flooding_message.source_ip]:
            self.neighbors_info[flooding_message.source_ip]['rtsp_port'] = flooding_message.rtsp_port
        if 'rtp_port' not in self.neighbors_info[flooding_message.source_ip]:
            self.neighbors_info[flooding_message.source_ip]['rtp_port'] = flooding_message.rtp_port
        print(f"INFRMAÇÂO DOS VIZINHSO : {self.neighbors_info}\n")
        threading.Thread(target=self.openRTSP_socket, args=(flooding_message.source_ip,)).start() # Abre socket rtsp    
        
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
                    "failed-attempts": 0,
                    "status": "active"  # Define o status como ativo
                }
                print(f"Added new neighbor: {neighbor_id}")
            print(f"Server {self.server_id} neighbors: {self.neighbors}")
        
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
                    continue  # Ignora o envio de PING para vizinhos já considerados inativos

                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.connect((neighbor_ip, neighbor_info['control_port']))
                        ping_message = ControlMessage()
                        ping_message.type = ControlMessage.PING
                        ping_message.node_ip = self.server_ip
                        ping_message.node_id = self.server_id
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
        pong_message.node_id = self.server_id
        conn.send(pong_message.SerializeToString())
        print(f"Sent PONG to neighbor {control_message.node_id}")
        
        # Reinicia as tentativas falhas do nó que enviou o PING
        with self.lock:
            if control_message.node_ip in self.neighbors:
                self.neighbors[control_message.node_ip]["failed-attempts"] = 0
                self.neighbors[control_message.node_ip]["status"] = "active"
                
    def send_flood_to_neighbors(self):
        while True:
            time.sleep(10)
            
            for neighbor_ip, neighbor_info in list(self.neighbors.items()):
                # Verificar se o vizinho já está marcado como inativo
                if neighbor_info.get("status") == "inactive":
                    continue  # Ignora o envio de flooding para vizinhos já considerados inativos
                self.send_flooding_message()
                
    def send_flooding_message(self):
        """
        Envia uma mensagem de flooding para todos os vizinhos.
        """
        flooding_message = FloodingMessage()
        flooding_message.type = FloodingMessage.FLOODING_UPDATE
        flooding_message.source_id = self.server_id
        flooding_message.source_ip = self.server_ip
        flooding_message.stream_ids.extend(self.movies.values())
        flooding_message.route_state = "inactive"
        flooding_message.hops = 0  # Inicie o contador de saltos
        flooding_message.control_port = self.control_port
        flooding_message.rtsp_port = self.server_rtsp_port

        for neighbor_ip, neighbor_info in self.neighbors.items():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((neighbor_ip, neighbor_info['control_port']))
                    s.send(flooding_message.SerializeToString())
                    print(f"Sent flooding message to {neighbor_info['node_id']}")

            except Exception as e:
                print(f"Failed to send flooding message to {neighbor_info['node_id']}: {e}")
            
    def openRTSP_socket(self, node_ip):   
 
        rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        rtspSocket.bind(('', self.server_rtsp_port))
        rtspSocket.listen(5) 
        print(f"Server RTSP escutando em :{self.server_rtsp_port}")

        # Receive client info (address,port) through RTSP/TCP session
        while True:
            neighborInfo = {}
            neighborInfo['rtspSocket'], neighbor_address = rtspSocket.accept()
            neighborInfo['rtp_port'] = self.neighbors_info[node_ip]['rtp_port']
            neighborInfo['ip'] = node_ip
            ServerWorker(neighborInfo).run()
                
def main():
    
    if len(sys.argv) != 6:
        print("Usage: python Server.py <server_rtsp_port> <bootstrapper_ip> <server_id> <server_ip> <server_type>")
        sys.exit(1)
    
    server_rtsp_port = int(sys.argv[1])
    bootstrapper = sys.argv[2] # 10.0.1.10
    server_id = sys.argv[3]  #  Server
    server_ip = sys.argv[4] # 10.0.0.1
    server_type = sys.argv[5] # pop/node/server
    control_port = 50051  # Porta de controle padrão
    data_port = 50052     # Porta de dados padrão

    server = Server(server_ip, server_id, server_type, server_rtsp_port, control_port, data_port, bootstrapper)
    server.start()
        
if __name__ == "__main__":
	main()



