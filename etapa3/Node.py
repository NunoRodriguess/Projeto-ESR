import socket
import threading
from control_protocol_pb2 import ControlMessage
from control_protocol_pb2 import FloodingMessage
from RtpPacket import RtpPacket
import time
import sys

class Node:
    def __init__(self, node_ip, rtsp_port, rtp_port, node_id, node_type, control_port=50051, data_port=50052, bootstrapper_host='localhost', bootstrapper_port=5000):
        self.node_ip = node_ip
        self.rtsp_port = rtsp_port
        self.rtp_port = rtp_port
        self.node_type = node_type
        
        self.node_id = node_id
        self.control_port = control_port
        self.data_port = data_port
        self.bootstrapper = (bootstrapper_host, bootstrapper_port)
        
        self.neighbors = {}  # Dicionário para armazenar informações dos vizinhos
        self.neighbors_lock = threading.Lock()
        
        self.routing_table = {}
        self.routing_lock = threading.Lock()  # Lock para sincronizar o acesso aos vizinhos
        
        self.sessions = {} # Vizinhos armazenados por sessões
        self.sessions_lock = threading.Lock()
        
        self.neighbors_rtsp = {}  # Para comunicar com os seus vizinhos até ao servidor
        self.neighbors_rtsp_lock = threading.Lock()

        # Criação do socket RTSP (TCP)
        self.rtsp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.rtsp_socket.bind((self.node_ip, self.rtsp_port))
        self.rtsp_socket.listen(5)
        print(f"Node RTSP escutando em {self.node_ip}:{self.rtsp_port}")
        
        # Criação do socket RTP (UDP)
        self.rtp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rtp_socket.bind((self.node_ip, self.rtp_port))
      
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
            control_message.node_id = self.node_id
            control_message.node_ip = self.node_ip
            control_message.control_port = self.control_port
            control_message.data_port = self.data_port
            control_message.node_type = self.node_type
            control_message.rtsp_port = self.rtsp_port
            
            # Envia a mensagem de registro
            self.send_control_message_tcp(s, control_message)
            
            # Recebe e processa a resposta
            header = s.recv(1)  # Lê o primeiro byte
            data = s.recv(1024)  # Lê o restante da mensagem
            
            if header == b'\x01':  # ControlMessage
                response_message = ControlMessage()
                response_message.ParseFromString(data)
                
                if response_message.type == ControlMessage.REGISTER_RESPONSE:
                    print(f"Node {self.node_id} registered")
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
                                "accumulated_time": float('inf'),
                                "rtsp_port": neighbor.rtsp_port
                            }
                        
                    print(f"Node {self.node_id} neighbors: {self.neighbors}")
                    # Após o registro, notifica os vizinhos sobre o registro
                    self.notify_neighbors_registration()
                   
                else:
                    print(f"Unexpected response type: {response_message.type}")

    def notify_neighbors_registration(self):
        """
        Notifica os vizinhos que o nó está registrado e que pode haver atualizações.
        """
        with self.neighbors_lock:
            neighbors_snapshot =  self.neighbors.copy()
            
        for neighbor_ip, neighbor_info in neighbors_snapshot.items():
            try:
                #Enviar em udp para clientes
                if neighbor_info["node_id"].startswith("client"):
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                        notify_message = ControlMessage()
                        notify_message.type = ControlMessage.UPDATE_NEIGHBORS
                        notify_message.node_id = self.node_id
                        notify_message.node_ip = self.node_ip
                        notify_message.control_port = self.control_port
                        notify_message.data_port = self.data_port
                        notify_message.node_type = self.node_type
                        notify_message.rtsp_port = self.rtsp_port
                        
                        address = (neighbor_ip, neighbor_info['data_port'])
                        self.send_control_message_udp(s, address, notify_message)
                        print(f"Notified client {neighbor_info['node_id']} of registration.")
                    
                #Enviar em tcp para clientes
                else:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.connect((neighbor_ip, neighbor_info['control_port']))
                        notify_message = ControlMessage()
                        notify_message.type = ControlMessage.UPDATE_NEIGHBORS
                        notify_message.node_id = self.node_id
                        notify_message.node_ip = self.node_ip
                        notify_message.control_port = self.control_port
                        notify_message.data_port = self.data_port
                        notify_message.node_type = self.node_type
                        notify_message.rtsp_port = self.rtsp_port
                        
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
        threading.Thread(target=self.accept_connections).start()
        threading.Thread(target=self.control_server).start()  # Inicia o servidor de controle em uma thread separada
        if self.node_type == "pop":
            threading.Thread(target=self.data_server).start()     # Inicia o servidor de dados em uma thread separada
        threading.Thread(target=self.send_ping_to_neighbors).start()  # Enviar PING aos vizinhos
        
    def control_server(self):
        """
        Inicia o servidor de controle que escuta em uma porta específica para conexões de outros nós.
        Lida com mensagens de controle como PING e atualizações de vizinhos.
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', self.control_port))
            s.listen()
            print(f"Node {self.node_id} listening on control port {self.control_port}")
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
                        if flooding_message.type == FloodingMessage.FLOODING_UPDATE:
                            self.handle_flooding_message(flooding_message)
                            
                        elif flooding_message.type == FloodingMessage.ACTIVATE_ROUTE:
                            self.activate_best_route(flooding_message, "node")
                            self.handle_rtp_forwarding()
                            
                        elif flooding_message.type == FloodingMessage.DEACTIVATE_ROUTE:
                            filename = flooding_message.stream_ids[0]
                            with self.sessions_lock:
                                del self.sessions[filename][flooding_message.source_ip]  # Desativa o envio de pacotes para a rota de onde veio a mensagem
                                sessions_snapshot = self.sessions[filename].copy()

                            print(f"DESATIVAÇÃO DA SESSÃO PARA {flooding_message.source_ip}")
                            
                            # Se o node não estiver a enviar dados para mais nenhuma rota, chama a função fornecida
                            if len(sessions_snapshot) == 0:
                                self.deactivate_routes(flooding_message.source_ip, filename)
                                
                        else:
                            raise ValueError(f"Unknown FloodingMessage type: {flooding_message.type}")
                    except Exception as e:
                        print(f"Failed to parse as FloodingMessage: {e}")
                else:
                    print("Unknown message header received. Ignoring.")
                    continue

    def handle_update_neighbors(self, control_message):
        print(f"Updating neighbors with {control_message.node_id}")
        neighbor_id = control_message.node_id
        neighbor_ip = control_message.node_ip
        control_port = control_message.control_port
        data_port = control_message.data_port
        node_type = control_message.node_type
        rtsp_port = control_message.rtsp_port
    
        with self.neighbors_lock:
            neighbors_snapshot =  self.neighbors.copy()
            
        # Se o vizinho já estiver na lista, atualiza o status
        if neighbor_ip in neighbors_snapshot:
            with self.neighbors_lock:
                self.neighbors[neighbor_ip]["status"] = "active"
            print(f"Updated status of existing neighbor {neighbor_id} to active.")
        else:
            with self.neighbors_lock:
                # Armazena as informações do vizinho se ele não estiver presente
                self.neighbors[neighbor_ip] = {
                    "node_id": neighbor_id,
                    "control_port": control_port,
                    "data_port": data_port,
                    "node_type": node_type,
                    "failed-attempts": 0,
                    "status": "active",  # Define o status como ativo
                    "best_time": float('inf'),
                    "accumulated_time": float('inf'),
                    "rtsp_port": rtsp_port
                }
            print(f"Added new neighbor: {neighbor_id}")
      
        print(f"Node {self.node_id} neighbors: {self.neighbors}")
        
    def send_ping_to_neighbors(self):
        """Inicia uma thread para gerenciar o PING para cada vizinho ativo."""
        while True:
            with self.neighbors_lock:
                neighbors_snapshot =  self.neighbors.copy()
                
            for neighbor_ip, neighbor_info in neighbors_snapshot.items():
                # Ignora vizinhos inativos ou clientes
                if neighbor_info.get("status") == "inactive" or neighbor_info["node_id"].startswith("client"):
                    continue

                # Verifica se o vizinho já atingiu o limite de tentativas falhas
                if neighbor_info.get("failed-attempts", 0) >= 2:
                    print(f"Neighbor {neighbor_info['node_id']} considered inactive due to lack of PONG response.")
                    with self.neighbors_lock:
                        self.neighbors[neighbor_ip]["status"] = "inactive"
                        self.neighbors[neighbor_ip]["accumulated_time"] = float('inf')
                        
                    # Remover vizinho da tabela de routing
                    with self.routing_lock:
                        for destination, streams in list(self.routing_table.items()):
                            if destination == neighbor_ip:
                                print(f"Neighbor {neighbor_ip} removido da tabela de routing ")
                                del self.routing_table[destination]

                    # Remover vizinho das sessões
                    with self.sessions_lock:
                        for filename, session_data in list(self.sessions.items()):
                            if neighbor_ip in session_data:
                                print(f"Sessão {filename} removida para {neighbor_ip} ")
                                del self.sessions[filename][neighbor_ip]
                                                        
                            # Se o node nao tiver a enviar dados para mais nenhuma rota, reencaminha para o seu sucessor
                            if len(self.sessions[filename]) == 0:   
                                self.deactivate_routes(neighbor_ip, filename)

                    continue

                # Cria uma thread para gerenciar o PING/PONG para o vizinho
                neighbor_thread = threading.Thread(
                    target=self.manage_neighbor_communication,
                    args=(neighbor_ip, neighbor_info),
                    daemon=True
                )
                neighbor_thread.start()
            time.sleep(15)

    def manage_neighbor_communication(self, neighbor_ip, neighbor_info):
        """Envia PING, recebe PONG e atualiza informações do vizinho."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((neighbor_ip, neighbor_info['control_port']))

                # Prepara mensagem de PING
                ping_message = ControlMessage()
                ping_message.type = ControlMessage.PING
                ping_message.node_ip = self.node_ip
                ping_message.node_id = self.node_id

                # Calcula o menor RTT local e soma ao menor tempo acumulado recebido
                rtt_vizinho = neighbor_info.get("best_time", float('inf'))
                print(f"Melhor rtt para os vizinhos: {rtt_vizinho:.4f}")
                
                best_received_neighbor = None
                best_received_accumulated_time = float('inf')

                with self.neighbors_lock:
                    neighbors_snapshot =  self.neighbors.copy()
                    
                for n_ip, n_info in neighbors_snapshot.items():
                    accumulated_time = n_info.get("accumulated_time", float('inf'))
                    if accumulated_time < best_received_accumulated_time:
                        best_received_accumulated_time = accumulated_time
                        best_received_neighbor = n_info["node_id"]

                if best_received_neighbor is not None:
                    print(f"Melhor tempo acumulado até ao servidor: {best_received_accumulated_time:.4f} é do vizinho {best_received_neighbor}")
                else:
                    print("Nenhum tempo acumulado válido encontrado nos vizinhos.")

                new_accumulated_time = best_received_accumulated_time + rtt_vizinho
                # Envia o tempo acumulado calculado
                send_time = time.time()
                ping_message.timestamp = send_time
                ping_message.accumulated_time = new_accumulated_time
                self.send_control_message_tcp(s, ping_message)
                print(f"Sent PING to {neighbor_info['node_id']} with accumulated time: {new_accumulated_time:.4f}")

                # Espera pelo PONG
                header = s.recv(1)  # Lê o primeiro byte
                data = s.recv(1024)  # Lê o restante da mensagem
                if data:
                    if header == b'\x01':  # ControlMessage
                        response_message = ControlMessage()
                        response_message.ParseFromString(data)
                        if response_message.type == ControlMessage.PONG:
                            print(f"Received PONG from {response_message.node_id}")
                            receive_time = time.time()

                            # Calcula o RTT
                            rtt = receive_time - send_time
                            with self.neighbors_lock:
                                self.neighbors[neighbor_ip]["best_time"] = rtt
                                self.neighbors[neighbor_ip]["failed-attempts"] = 0
                                self.neighbors[neighbor_ip]["status"] = "active"

        except Exception as e:
            # Incrementa contador de falhas
            print(f"Failed to communicate with {neighbor_info['node_id']}: {e}")
            with self.neighbors_lock:
                self.neighbors[neighbor_ip]["failed-attempts"] = neighbor_info.get("failed-attempts", 0) + 1
             
    def handle_ping(self, control_message, conn):
        # Processa PING recebido
        print(f"Received PING from {control_message.node_id} with : {control_message.accumulated_time:.4f} time ")

        # Atualiza tempo acumulado recebido
        received_accumulated_time = control_message.accumulated_time

        with self.neighbors_lock:
            neighbors_snapshot =  self.neighbors.copy()
            
        if control_message.node_ip in neighbors_snapshot:
            # Atualiza o tempo acumulado vindo do vizinho
            with self.neighbors_lock:
                self.neighbors[control_message.node_ip]["accumulated_time"] = received_accumulated_time

        # Responde com PONG
        pong_message = ControlMessage()
        pong_message.type = ControlMessage.PONG
        pong_message.node_id = self.node_id
        self.send_control_message_tcp(conn, pong_message)
        print(f"Sent PONG to {control_message.node_id}")
                    
    def handle_flooding_message(self, flooding_message):
        print(f"Received flooding message from {flooding_message.source_ip}")

        # Atualiza a tabela de rotas
        self.update_route_table(flooding_message)
        
        with self.neighbors_lock:
            neighbors_snapshot =  self.neighbors.copy()
            
        # Reencaminha a mensagem para todos os vizinhos, exceto o remetente com a atualização da métrica
        for neighbor_ip, neighbor_info in neighbors_snapshot.items():
            if neighbor_ip != flooding_message.source_ip and neighbor_ip not in self.routing_table and neighbor_info["status"] == "active":  # Não reencaminhe de volta para quem enviou
                if not neighbor_info["node_id"].startswith("client"): # nao enviar flooding para cliente
                    try:
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                            s.connect((neighbor_ip, neighbor_info['control_port']))
                            flooding_message.source_ip = self.node_ip
                            flooding_message.source_id = self.node_id
                            flooding_message.control_port = self.control_port
                            flooding_message.rtsp_port = self.rtsp_port
                            self.send_flooding_message_tcp(s,flooding_message)
                            print(f"Re-sent flooding message to {neighbor_info['node_id']}")
                    except Exception as e:
                        print(f"Failed to re-send flooding message to {neighbor_info['node_id']}: {e}")
                    
    def update_route_table(self, flooding_message):
        """
        Atualiza a tabela de rotas com base na mensagem de flooding recebida,
        agora levando em consideração múltiplos fluxos de vídeo.
        """
        destination = flooding_message.source_ip
                
        # Iterar sobre os fluxos de vídeo (stream_ids) recebidos
        for stream_id in flooding_message.stream_ids:
            with self.routing_lock:
                if destination not in self.routing_table:
                    self.routing_table[destination] = {}
            
                # Se a rota para o destino e o fluxo não existirem
                if (stream_id not in self.routing_table[destination]):
                    self.routing_table[destination][stream_id] = {
                        "source_ip": flooding_message.source_ip,
                        "source_id": flooding_message.source_id,
                        "status": flooding_message.route_state,
                        "control_port": flooding_message.control_port,
                        "rtsp_port": flooding_message.rtsp_port,
                        "stream": "inactive", #Se pode receber stream ou nao
                        "flow": "inactive" #Se está a receber stream ou nao
                    }        
        print(f"Routing table is updated for streams: {list(flooding_message.stream_ids)}")  
                    
    def activate_best_route(self, flooding_message, sender): # Sender diz se é uma ativação do cliente ou se é do node
        """
        Ativa a melhor rota disponível na tabela de rotas com base no tempo
        para um fluxo específico (filename) contido na mensagem de flooding.
        """
        best_route = None
        min_time = float('inf')  # Define o maior valor possível para comparar
        destination = None  
        filename = None
        forward_activation = False 

        # Acessa os stream_ids da mensagem de flooding
        stream_ids = flooding_message.stream_ids

        # Procura a melhor rota na tabela de roteamento com base no tempo
        with self.routing_lock:
            routing_snapshot =  self.routing_table.copy()
            
        for dest, route_info in routing_snapshot.items():
            for stream_id in stream_ids:
                if stream_id in route_info:
                    # Verificar o menor tempo acumulado
                    with self.neighbors_lock:
                        if self.neighbors[dest]["accumulated_time"] < min_time:
                            min_time = self.neighbors[dest]["accumulated_time"]
                            best_route = route_info[stream_id]
                            filename = stream_id
                            destination = dest
                            
        if best_route is not None:
            with self.routing_lock:
                if self.routing_table[destination][filename]['stream'] == "active":
                    print(f"Route {best_route['source_id']} at {destination} with {min_time:.4f} time, already active.")
                
                else:   
                    # Ativar a nova melhor rota para este fluxo
                    self.routing_table[destination][filename]['stream'] = "active"
                    self.routing_table[destination][filename]['flow'] = "active"
                    forward_activation = True
            
            with self.sessions_lock:
                # Ativa a sessão para a rota
                self.sessions.setdefault(filename, {}).setdefault(flooding_message.source_ip, {
                    'rtp_port': flooding_message.rtp_port,
                })
                if sender == "client" and 'flow' not in self.sessions[filename][flooding_message.source_ip]:
                    self.sessions[filename][flooding_message.source_ip]['flow'] = "deactive"

                # Adiciona o 'rtsp_port' apenas se for fornecido
                if flooding_message.rtsp_port:
                    self.sessions[filename][flooding_message.source_ip]['rtsp_port'] = flooding_message.rtsp_port
                      
            self.deactivate_routes(destination, filename)
                
            if forward_activation:
                print(f"Activating best route to {best_route['source_id']} at {destination} with {min_time:.4f} time.")
                # Enviar mensagem de ativação para a melhor rota
                activate_message = FloodingMessage()  # Criação de uma nova mensagem de ativação
                activate_message.type = FloodingMessage.ACTIVATE_ROUTE
                activate_message.stream_ids.append(filename)
                activate_message.source_ip = self.node_ip
                activate_message.rtp_port = self.rtp_port
                activate_message.rtsp_port = self.rtsp_port
                    
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.connect((destination, best_route['control_port']))
                        self.send_flooding_message_tcp(s, activate_message)
                        print(f"Sent route activation to destination {best_route['source_id']} for stream {filename}.")
                            
                except Exception as e:
                    print(f"Failed to activate route to destination {best_route['source_id']}: {e}")
            
            if best_route["source_id"].startswith("server"):
                time.sleep(2)
                rtsp_socket = self.create_rtsp_connection(filename, destination, best_route['rtsp_port']) # Para se conectar ao servidor 
                request = f"ACTIVE {filename}\nIP {self.node_ip}\nRTP_PORT {self.rtp_port}\n"
                rtsp_socket.send(request.encode())
                print("ACTIVE ENVIDADO AO SERVIDOR")
                
        else:
            print("No active route available to activate.")
        
    def deactivate_routes(self, dest_ip, filename):
        """
        Desativa todas as rotas associadas a um fluxo específico identificado por filename,
        exceto a rota do dest_ip.
        """
        with self.routing_lock:
            routing_snapshot = self.routing_table.copy()
            
        for route_ip, route_info in routing_snapshot.items():
            if route_ip != dest_ip and filename in route_info:
                # Verifica se a rota está ativa
                if route_info[filename]["stream"] == "active" or route_info[filename]["flow"] == "active":
                    # Atualiza a rota para inativa
                    with self.routing_lock:
                        self.routing_table[route_ip][filename]["stream"] = "inactive"
                        self.routing_table[route_ip][filename]["flow"] = "inactive"
                        
                    with self.neighbors_rtsp_lock:
                        with self.sessions_lock:
                            sessions_snapshot = self.sessions[filename].copy()
                        if len(sessions_snapshot) == 0:
                            self.neighbors_rtsp[route_ip]['rtsp_socket'].close()
                            del self.neighbors_rtsp[route_ip]['rtsp_socket']
                        

                    print(f"Deactivated route to {route_ip} for stream {filename}.")

                    deactivate_message = FloodingMessage()  # Criação de uma nova mensagem de desativação
                    deactivate_message.type = FloodingMessage.DEACTIVATE_ROUTE
                    deactivate_message.stream_ids.append(filename)
                    deactivate_message.source_ip = self.node_ip
                    deactivate_message.rtp_port = self.rtp_port
                    deactivate_message.rtsp_port = self.rtsp_port

                    try:
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                            s.connect((route_ip, route_info[filename]["control_port"]))
                            self.send_flooding_message_tcp(s, deactivate_message)
                            print(f"Sent route deactivation to {route_info[filename]['source_id']} for stream {filename}.")
                    except Exception as e:
                        print(f"Failed to deactivate route to {route_info[filename]['source_id']}: {e}")

    def accept_connections(self):
        # Recebe pedidos do vizinho
        while True:
            neighbor_socket, neighbor_address = self.rtsp_socket.accept()
            print(f"Conexão recebida de {neighbor_address}")
            threading.Thread(target=self.handle_neighbor, args=(neighbor_socket, neighbor_address)).start()
    
    def get_client_ip_from_request(self, request):
        """Extrai o IP de uma requisição RTSP."""
        lines = request.splitlines()
        for line in lines:
            if "IP" in line:
                return line.split(": ")[1]
        return None
    
    def replace_client_ip_in_request(self, request, new_ip):
        """Substitui o IP na requisição por um novo IP."""
        lines = request.splitlines()
        updated_request = []
        for line in lines:
            if "IP" in line:
                updated_request.append(f"IP: {new_ip}")
            else:
                updated_request.append(line)
        return "\n".join(updated_request)

    def handle_neighbor(self, neighbor_socket, neighbor_address):
        """Função principal para lidar com as mensagens do vizinho."""
        filename = None
        dest = None
        while True:
            try:
                request = neighbor_socket.recv(1024).decode()
                if not request:
                    break
                print(f"Requisição recebida do vizinho {neighbor_address}:\n{request}\n")

                # Retira as informações necessárias da requisição
                lines = request.splitlines()
                line1 = lines[0].split(' ')
                filename = line1[1]
                request_ip = self.get_client_ip_from_request(request)                 
                
                # Preparação para a receção de pacotes do video requisitado
                if "SETUP" in request:  
                    if self.route_with_SETUP(filename) or self.at_least_one_receiving_rtp(filename, None): # Caso já tenha recebido algum setup ou já esteja a enviar dados a alguem
                        seq = lines[1].split(' ')[1]
                        self.replyRtsp(seq, filename, neighbor_socket) # Responde logo ao node com a confirmação
                        
                    else: # Caso contrário
                        modified_request = self.replace_client_ip_in_request(request, self.node_ip)     
                        dest = self.forward_request(filename, modified_request, neighbor_socket) 
                        with self.routing_lock: 
                            self.routing_table[dest][filename]['flow'] = "active"
                            self.routing_table[dest][filename]['request'] = "SETUP"
                    
                # Inicialização da receção dos pacotes do video requisitos      
                elif "PLAY" in request:      
                    with self.sessions_lock:
                        if request_ip not in self.sessions[filename]:
                            return
                        self.sessions[filename][request_ip]["flow"] = "active" 
 
                    if self.at_least_one_receiving_rtp(filename, request_ip): # Se o node está a receber dados e já estou a enviar a pelo menos um vizinho
                        seq = lines[1].split()[1]
                        self.replyRtsp(seq, filename, neighbor_socket) # Responde ao node com a confirmação
                
                    else:  
                        modified_request = self.replace_client_ip_in_request(request, self.node_ip)
                        dest = self.forward_request(filename, modified_request, neighbor_socket)
                        with self.routing_lock:
                            self.routing_table[dest][filename]['request'] = "PLAY"

                # Interrupção da receção dos pacotes do video requisitado   
                elif "PAUSE" in request: 
                    with self.sessions_lock:
                        if request_ip not in self.sessions[filename]:
                            return
                        self.sessions[filename][request_ip]["flow"] = "deactive"    
                            
                    if self.at_least_two_receiving_rtp(filename) : # Caso onde há mais que 1 vizinho a receber dados
                        seq = lines[1].split(' ')[1]
                        self.replyRtsp(seq, filename, neighbor_socket) # Responde ao node com a confirmação
                                        
                    else:  # Caso contrário  
                        modified_request = self.replace_client_ip_in_request(request, self.node_ip)
                        dest = self.forward_request(filename, modified_request, neighbor_socket)     
                        with self.routing_lock: 
                            self.routing_table[dest][filename]['request'] = "PAUSE"          
                                  
                # Encerrar a comunicação com o node que fez a requisição do video
                elif "TEARDOWN" in request:   
                    self.remove_connection(filename, request_ip, request, neighbor_socket)
                    
            except Exception as e:
                print(f"Ocorreu um erro: {e}")
                break
            
    def forward_request(self, filename, request, neighbor_socket):
        active_route = self.get_active_route(filename)
        rtsp_port = active_route['route_info']['rtsp_port']
        dest = active_route['destination']
        rtsp_socket = self.create_rtsp_connection(filename, dest, rtsp_port) # Conecta se com o vizinho ativo
        self.send_rtsp_request(rtsp_socket, request, neighbor_socket)  # Reencaminha lhe o pedido 
        return dest 
                
    def at_least_one_receiving_rtp(self, filename, sender_ip):
        with self.sessions_lock:
            sessions_snapshot =  self.sessions[filename].copy()
            
        for client_ip, client_info in sessions_snapshot.items():
            if client_info.get('flow') == "active" and client_ip != sender_ip:
                return True
        return False
    
    def at_least_two_receiving_rtp(self, filename):
        count = 1 # O que enviou o pause conta como 1 na receção de rtp
        with self.sessions_lock:
            sessions_snapshot =  self.sessions[filename].copy()
            
        for client_ip, client_info in sessions_snapshot.items():
                if client_info.get('flow') == "active":
                    count += 1
                if count > 1:
                    return True
        return False
            
    def get_active_route(self, stream_id):
        """
        Verifica se há uma rota ativa para o fluxo (stream_id) na tabela de roteamento
        e retorna a rota se encontrada.
        """
        with self.routing_lock:
            routing_snapshot =  self.routing_table.copy()
            
        for route_ip, route_info in routing_snapshot.items():
            # Verifica se a stream_id existe na rota e está ativa
            if stream_id in route_info and route_info[stream_id]['stream'] == "active":
                return {
                    "destination": route_ip,
                    "route_info": route_info[stream_id]
                }
        return None
    
    def route_with_SETUP(self, stream_id):
        """
        Verifica se há uma rota ativa para o fluxo (stream_id) na tabela de roteamento
        e retorna a rota se encontrada.
        """
        with self.routing_lock:
            routing_snapshot =  self.routing_table.copy()
            
        for route_ip, route_info in routing_snapshot.items():
            # Verifica se a stream_id existe na rota e está ativa
            if stream_id in route_info and 'request' in route_info[stream_id]:
                if route_info[stream_id]['request'] == "SETUP":
                    return True
        return False
    
    def create_rtsp_connection(self, filename, destination_ip, rtsp_port):
        """Verifica se uma conexão RTSP persistente existe, e a cria se não existir.""" 
        with self.neighbors_lock:
            self.neighbors_rtsp.setdefault(destination_ip, {}) 
            try:
                rtsp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                rtsp_socket.connect((destination_ip, rtsp_port))
                self.neighbors_rtsp[destination_ip]['rtsp_socket'] = rtsp_socket
                print(f"Conexão RTSP persistente criada para {destination_ip}:{rtsp_port}")
                return self.neighbors_rtsp[destination_ip]['rtsp_socket']
            except Exception as e:
                print(f"Erro ao criar conexão RTSP para {destination_ip}:{rtsp_port}: {e}")
                return None

    def send_rtsp_request(self, rtsp_socket, request, neighbor_socket):
        """Envia a requisição RTSP e encaminha a resposta ao vizinho."""
        try:
            rtsp_socket.send(request.encode())
            print(f"Requisição RTSP enviada")

            # Receber a resposta do vizinho RTSP
            response = rtsp_socket.recv(1024).decode()
            if response:
                print(f"RECEBEU A RESPOSTA DO VIZINHO:\n{response}")
                
                # Enviar a resposta de volta ao vizinho
                neighbor_socket.send(response.encode())
                print(f"Reencaminhou a resposta recebida")
                           
        except Exception as e:
            print(f"Falha ao enviar requisição RTSP: {e}")

    def handle_rtp_forwarding(self):
        """Inicia o encaminhamento dos pacotes RTP para o vizinho após a requisição SETUP."""
        threading.Thread(target=self.forward_rtp, args=()).start()

    def forward_rtp(self):               
        while True:
            data, addr = self.rtp_socket.recvfrom(20480)
            if data:
                rtp_packet = RtpPacket()
                stream_id, sender_ip = rtp_packet.decode(data) # Extrai o nome do video do pacote recebido para saber para quem tem que o reencaminhar
                rtp_packet.updateSenderIp(data, self.node_ip) # Atualiza o sender_ip do pacote
                
                with self.sessions_lock:
                    session_info =  self.sessions[stream_id].copy()
                                
                for neighbor_ip, neighbor_info in session_info.items():
                    # Inicializa o socket RTP, se necessário
                    if "rtpSocket" not in neighbor_info:
                        with self.sessions_lock:
                            self.sessions[stream_id][neighbor_ip]["rtpSocket"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    
                    # Verifica condições para encaminhar o pacote
                    if "rtpSocket" in neighbor_info and "rtp_port" in neighbor_info:
                        with self.routing_lock:
                            routing_info =  self.routing_table[sender_ip][stream_id].copy()
                        
                        if routing_info['flow'] == "active":
                            if 'flow' not in neighbor_info:
                                with self.sessions_lock:
                                    self.sessions[stream_id][neighbor_ip]['flow'] = "active"
                                    
                            with self.sessions_lock:
                                session_info =  self.sessions[stream_id][neighbor_ip].copy()
                                
                            if session_info['flow'] == "active":
                                if "request" not in routing_info or routing_info['request'] == "PLAY":
                                    print(f"Pacote {rtp_packet.seqNum()} - {stream_id} recebido de {sender_ip}, enviando a {neighbor_ip}")
                                    updated_data = rtp_packet.getPacket()
                                    session_info["rtpSocket"].sendto(updated_data, (neighbor_ip, session_info['rtp_port']))                     
             
    def remove_connection(self, filename, neighbor_address, request, neighbor_socket): 
        # Como o node nao tem mais clientes para enviar, avisa o vizinho que o está a enviar pacotes para parar de o fazer
        active_route = self.get_active_route(filename)
        rtsp_port = active_route['route_info']['rtsp_port']
        dest = active_route['destination']
        rtsp_socket = self.create_rtsp_connection(filename, dest, rtsp_port) # Conecta se com o vizinho ativo
        # Reencaminha lhe o pedido 
        self.send_rtsp_request(rtsp_socket, request, neighbor_socket, filename)     
                    
        # Verifique se o filename e o cliente existem na sessão
        with self.sessions_lock: 
            sessions_snapshot =  self.sessions.copy()
            
        if filename in sessions_snapshot and neighbor_address in sessions_snapshot[filename]:
            # Fecha o socket RTP se ele existir
            if "rtpSocket" in sessions_snapshot[filename][neighbor_address]:
                try:
                    with self.sessions_lock: 
                        self.sessions[filename][neighbor_address]["rtpSocket"].close()
                    print(f"RTP socket para {neighbor_address} fechado.")
                except Exception as e:
                    print(f"Erro ao fechar RTP socket para {neighbor_address}: {e}")
            
            with self.sessions_lock: 
                # Remove o cliente do dicionário
                self.sessions[filename].pop(neighbor_address)
                print(f"Cliente {neighbor_address} removido de {filename}")

                # Se o dicionário do filename está vazio, remova também
                if not self.sessions[filename]:  # Verifica se não há mais clientes
                    self.sessions.pop(filename)    
                    print(f"Removido {filename} do dicionário pois não há mais clientes.")
        else:
            print(f"Cliente {neighbor_address} não encontrado em {filename}")
           
    def replyRtsp(self, seq, session, neighbor_socket):
        """Send RTSP reply to the client."""
        reply = 'RTSP/1.0 200 OK\nCSeq: ' + seq + '\nSession: ' + session
        neighbor_socket.send(reply.encode())
     
    def data_server(self):
        """
        Inicia o servidor de controle que escuta em uma porta específica para conexões de outros nós.
        Lida com mensagens de controle como PING e atualizações de vizinhos.
        """
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.bind(('', self.data_port))
            print(f"Node {self.node_id} listening on data port {self.data_port}")
            while True:
                data, addr = s.recvfrom(1024)
                threading.Thread(target=self.handle_data_message, args=(data, addr, s)).start()

    def handle_data_message(self, data, addr, socket):
        """
        Lida com mensagens recebidas via UDP.
        Processa mensagens de controle (PING, UPDATE_NEIGHBORS) e mensagens de flooding.

        :data: Dados recebidos.
        :addr: Endereço do nó que enviou os dados.
        :socket: Socket para enviar respostas.
        """
        print(f"Message received from {addr}")
        # Tenta interpretar a mensagem como ControlMessage
                
        if len(data) < 1:
            print("Invalid message: no header")
            return

        header = data[0:1]  # Primeiro byte é o header
        message_body = data[1:]  # Restante é a mensagem serializada

        try:
            if header == b'\x01':  # ControlMessage
                control_message = ControlMessage()
                control_message.ParseFromString(message_body)

                if control_message.type == ControlMessage.UPDATE_NEIGHBORS:
                    self.handle_update_neighbors(control_message)
                    
                elif control_message.type == ControlMessage.ACK:
                    self.handle_ack(socket, control_message)
                    
                else:
                    print(f"Unknown ControlMessage type: {control_message.type}")

            elif header == b'\x02':  # FloodingMessage
                flooding_message = FloodingMessage()
                flooding_message.ParseFromString(message_body)

                if flooding_message.type == FloodingMessage.ACTIVATE_ROUTE:
                    self.activate_best_route(flooding_message, "client")
                    self.handle_rtp_forwarding()

                elif flooding_message.type == FloodingMessage.FLOODING_UPDATE:
                    self.handle_flooding_message(flooding_message)
                    
                elif flooding_message.type == FloodingMessage.DEACTIVATE_ROUTE:
                    filename = flooding_message.stream_ids[0]
                    with self.sessions_lock:
                        del self.sessions[filename][flooding_message.source_ip] # desativa o envio de pacotes para a rota de onde veio a mensagem de desativação
                        sessions_snapshot = self.sessions[filename].copy()
                        
                    print(f"DESATIVAÇÃO DA SESSÃO PARA {flooding_message.source_ip}")
                    # Se o node nao tiver a enviar dados para mais nenhuma rota, reencaminha para o seu sucessor
                    if len(sessions_snapshot) == 0:   
                        self.deactivate_routes(flooding_message.source_ip, filename)
                        
                else:
                    print(f"Unknown FloodingMessage type: {flooding_message.type}")

            else:
                print("Unknown message header received. Ignoring.")

        except Exception as e:
            print(f"Failed to process message: {e}")
            
    def handle_ack(self, s, control_message):
        """ Escuta mensagens dos clientes e responde com ACK """
        try:
            with self.neighbors_lock:
                neighbors_snapshot =  self.neighbors.copy()
                
            best_time = min([n.get("accumulated_time", float('inf')) for n in neighbors_snapshot.values()])
            ack_message = ControlMessage()
            ack_message.type = ControlMessage.ACK
            ack_message.node_ip = self.node_ip
            ack_message.node_id = self.node_id
            ack_message.accumulated_time = best_time  
                         
            # Enviar ACK de volta para o cliente
            address = (control_message.node_ip, control_message.data_port)
            self.send_control_message_udp(s, address, ack_message)
            print(f"ACK sent to client {control_message.node_id} with {best_time:.4f} time")

        except Exception as e:
            print(f"Error in receiving message: {e}") 
    
def main():
    
    if len(sys.argv) != 5:
        print("Usage: python Node.py <bootstrapper_ip> <node_id> <node_ip> <node_type>")
        sys.exit(1)
        
    bootstrapper = sys.argv[1] # 10.0.1.10
    node_id = sys.argv[2]  #  Node-1
    node_ip = sys.argv[3] # 10.0.0.1
    node_type = sys.argv[4] # pop/node
    control_port = 50051  # Porta de controle padrão
    data_port = 50052     # Porta de dados padrão

    node = Node(node_ip, 30001, 25001, node_id, node_type, control_port, data_port, bootstrapper)
    node.start()

if __name__ == "__main__":
    main()
