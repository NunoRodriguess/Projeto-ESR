import socket
import threading
from control_protocol_pb2 import ControlMessage
from control_protocol_pb2 import FloodingMessage
import time
import sys

class Node:
    def __init__(self, node_ip, rtsp_port, rtp_port, node_id, node_type, control_port=50051, data_port=50052, bootstrapper_host='localhost', bootstrapper_port=5000):
        self.node_ip = node_ip
        self.rtsp_port = rtsp_port
        self.rtp_port = rtp_port
        
        self.node_id = node_id
        self.control_port = control_port
        self.data_port = data_port
        self.neighbors = {}  # Dicionário para armazenar informações dos vizinhos
        self.bootstrapper = (bootstrapper_host, bootstrapper_port)
        self.lock = threading.Lock()  # Lock para sincronizar o acesso aos vizinhos
        self.node_type = node_type
        
        self.routing_table = {}
        self.client_session = {}
        self.OK_200 = 0

        # Criação do socket RTSP (TCP)
        self.rtsp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.rtsp_socket.bind((self.node_ip, self.rtsp_port))
        self.rtsp_socket.listen(5)
        print(f"Node RTSP escutando em {self.node_ip}:{self.rtsp_port}")
        
        # Inicializar vizinhos
        self.neighbors_rtp = {}  # Para armazenar informações da scoket rtp dos vizinhos que vao receber pacotes
        self.neighbors_rtsp = {}  # Para armazenar informações da scoket rtsp dos cliente
        
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
            
            # Envia a mensagem de registro
            s.send(control_message.SerializeToString())
            
            # Recebe e processa a resposta
            data = s.recv(1024)
            if data:
                response_message = ControlMessage()
                response_message.ParseFromString(data)
                
                if response_message.type == ControlMessage.REGISTER_RESPONSE:
                    print(f"Node {self.node_id} registered")
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
                        
                    print(f"Node {self.node_id} neighbors: {self.neighbors}")
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
                    notify_message.node_id = self.node_id
                    notify_message.node_ip = self.node_ip
                    notify_message.control_port = self.control_port
                    notify_message.data_port = self.data_port
                    notify_message.node_type = self.node_type
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
        threading.Thread(target=self.accept_connections).start()
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
            print(f"Node {self.node_id} listening on control port {self.control_port}")
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
                            
                            # Verifica se é uma mensagem de flooding
                            if flooding_message.type == FloodingMessage.FLOODING_UPDATE:
                                self.handle_flooding_message(flooding_message)
                            
                            # Ativa a rota
                            elif flooding_message.type == FloodingMessage.ACTIVATE_ROUTE:
                                self.activate_best_route(flooding_message)    
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
                        "failed-attempts": 0,
                        "status": "active"  # Define o status como ativo
                    }
                    print(f"Added new neighbor: {neighbor_id}")
      
        print(f"Node {self.node_id} neighbors: {self.neighbors}")
        
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
                        ping_message.node_ip = self.node_ip
                        ping_message.node_id = self.node_id
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
        pong_message.node_id = self.node_id
        conn.send(pong_message.SerializeToString())
        print(f"Sent PONG to neighbor {control_message.node_id}")
        
        # Reinicia as tentativas falhas do nó que enviou o PING
        with self.lock:
            if control_message.node_ip in self.neighbors:
                self.neighbors[control_message.node_ip]["failed-attempts"] = 0
                self.neighbors[control_message.node_ip]["status"] = "active"
                    
    def handle_flooding_message(self, flooding_message):
        print(f"Received flooding message from {flooding_message.source_ip}")

        # Atualiza a tabela de rotas
        self.update_route_table(flooding_message)
        
        # Reencaminha a mensagem para todos os vizinhos, exceto o remetente com a atualização da métrica
        new_hops = flooding_message.hops + 1
        for neighbor_ip, neighbor_info in self.neighbors.items():
            if neighbor_ip != flooding_message.source_ip and neighbor_ip not in self.routing_table :  # Não reencaminhe de volta para quem enviou
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.connect((neighbor_ip, neighbor_info['control_port']))
                        flooding_message.source_ip = self.node_ip
                        flooding_message.source_id = self.node_id
                        flooding_message.hops = new_hops 
                        flooding_message.control_port = self.control_port
                        flooding_message.rtsp_port = self.rtsp_port
                        s.send(flooding_message.SerializeToString())
                        print(f"Re-sent flooding message to {neighbor_info['node_id']} with hops={flooding_message.hops}")
                except Exception as e:
                    print(f"Failed to re-send flooding message to {neighbor_info['node_id']}: {e}")
                    
    def update_route_table(self, flooding_message):
        """
        Atualiza a tabela de rotas com base na mensagem de flooding recebida,
        agora levando em consideração múltiplos fluxos de vídeo.
        """
        destination = flooding_message.source_ip
        metric = flooding_message.hops
        
        # Iterar sobre os fluxos de vídeo (stream_ids) recebidos
        for stream_id in flooding_message.stream_ids:

            with self.lock:
                if destination not in self.routing_table:
                    self.routing_table[destination] = {}
                
                # Se a rota para o destino e o fluxo não existirem ou se a métrica for melhor (menor número de hops)
                if (stream_id not in self.routing_table[destination] or 
                    metric < self.routing_table[destination][stream_id]['hops']):

                    self.routing_table[destination][stream_id] = {
                        "source_ip": flooding_message.source_ip,
                        "source_id": flooding_message.source_id,
                        "hops": metric,
                        "status": flooding_message.route_state,
                        "control_port": flooding_message.control_port,
                        "rtsp_port": flooding_message.rtsp_port,
                        "flow": "inactive"
                    }
                    
                    print(f"Route updated for stream {stream_id} to {self.routing_table[destination][stream_id]['source_id']} with hops={metric}")
        
        print(f"Routing table is updated for streams: {list(flooding_message.stream_ids)}")  

    def activate_best_route(self, flooding_message):
        """
        Ativa a melhor rota disponível na tabela de rotas com base no número de hops
        para um fluxo específico (filename) contido na mensagem de flooding.
        """
        best_route = None
        min_hops = float('inf')  # Define o maior valor possível para comparar
        destination = None  
        filename = None 

        # Acessa os stream_ids da mensagem de flooding
        stream_ids = flooding_message.stream_ids

        # Procura a melhor rota na tabela de roteamento com base no número de hops
        with self.lock:
            for dest, route_info in self.routing_table.items():
                for stream_id in stream_ids:
                    if stream_id in route_info:
                        if route_info[stream_id]['status'] == "active":
                            if filename not in self.client_session:
                                self.client_session[filename] = {} 
                            if flooding_message.source_ip not in self.client_session[stream_id]:
                                self.client_session[stream_id][flooding_message.source_ip] = {}
                            # Adiciona o novo recetor dos videos há sessão
                            self.client_session[stream_id][flooding_message.source_ip]['rtp_port'] = flooding_message.rtp_port
                            # O cliente nao manda a sua porta rtsp
                            if flooding_message.rtsp_port:
                                self.client_session[stream_id][flooding_message.source_ip]['rtsp_port'] = flooding_message.rtsp_port
                            self.client_session[stream_id][flooding_message.source_ip]['session'] = stream_id
                            print(f"Rota já ativa para o fluxo {stream_id} em {dest}. Reutilizando.")
                            return
                        # Caso contrário, encontre a melhor rota
                        if route_info[stream_id]['hops'] < min_hops:
                            min_hops = route_info[stream_id]['hops']
                            best_route = route_info[stream_id]
                            filename = stream_id
                            destination = dest

        if best_route:
            with self.lock:
                self.routing_table[destination][filename]['status'] = "active"
                if filename not in self.client_session:
                    self.client_session[filename] = {} 
                if flooding_message.source_ip not in self.client_session[stream_id]:
                    self.client_session[stream_id][flooding_message.source_ip] = {}
                # Adiciona o novo recetor dos videos há sessão
                self.client_session[stream_id][flooding_message.source_ip]['rtp_port'] = flooding_message.rtp_port
                # O cliente nao manda a sua porta rtsp
                if flooding_message.rtsp_port:
                    self.client_session[stream_id][flooding_message.source_ip]['rtsp_port'] = flooding_message.rtsp_port
                self.client_session[stream_id][flooding_message.source_ip]['session'] = stream_id

            print(f"Activating best route to {best_route['source_id']} at {destination} with {min_hops} hops.")
            # Enviar mensagem de ativação para a melhor rota
            try:
                activate_message = FloodingMessage()  # Criação de uma nova mensagem de ativação
                activate_message.type = FloodingMessage.ACTIVATE_ROUTE
                activate_message.stream_ids.append(filename)
                activate_message.source_ip = self.node_ip
                activate_message.rtp_port = self.rtp_port
                activate_message.rtsp_port = self.rtsp_port

                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((destination, best_route['control_port']))
                    s.send(activate_message.SerializeToString())
                    print(f"Sent route activation to destination {best_route['source_id']} for stream {filename}.")
                    return
            except Exception as e:
                print(f"Failed to activate route to destination {best_route['source_id']}: {e}")
                return None
        else:
            print("No active route available to activate.")
            return None

    def accept_connections(self):
        # Recebe pedidos do vizinho
        while True:
            neighbor_socket, neighbor_address = self.rtsp_socket.accept()
            print(f"Conexão recebida de {neighbor_address}")
            threading.Thread(target=self.handle_neighbor, args=(neighbor_socket, neighbor_address)).start()

        for key, value in self.routing_table.items():
            if value[filename]["source_id"] == search_value[filename]["source_id"] and value[filename]["hops"] == search_value[filename]["hops"]:
                return key
        return None

    def handle_neighbor(self, neighbor_socket, neighbor_address):
        """Função principal para lidar com as mensagens do vizinho."""
        filename = None
        while True:
            try:
                # Receber a requisição do vizinho
                request = neighbor_socket.recv(1024).decode()

                if not request:
                    break
                print(f"Requisição recebida do vizinho {neighbor_address}:\n{request}")

                # Gerencia a conexão RTSP persistente e envia a requisição
                lines = request.splitlines()
                print(f"LINES: {lines}\n")
                line1 = lines[0].split(' ')
                filename = line1[1]
                self.client_session.setdefault(filename, {})
                self.client_session[filename].setdefault(neighbor_address[0], {})
                if 'status' not in self.client_session[filename][neighbor_address[0]]:  
                    self.client_session[filename][neighbor_address[0]]['status'] = "INIT"
                   
                neighbor_status = self.client_session[filename][neighbor_address[0]]['status']
                # Caso o node já esteja a receber os pacotes pedidos
                route = self.get_route_with_stream(filename)
                if "SETUP" in request and neighbor_status == "INIT":
                    if route:
                        self.client_session[filename][neighbor_address[0]]["session"] = filename
                        seq = lines[1].split(' ')[1]
                        
                        # Responde ao node com a confirmação
                        self.replyRtsp(self.OK_200, seq[1], self.client_session[filename][neighbor_address[0]]['session'], neighbor_socket)
                        self.client_session[filename][neighbor_address[0]]['status'] = "READY"
                        
                    else: 
                        active_route = self.get_active_route(filename)
                        rtsp_port = active_route['route_info']['rtsp_port']
                        dest = active_route['destination']
                        rtsp_socket = self.get_or_create_rtsp_connection(filename, dest, rtsp_port) # Conecta se com o vizinho ativo
                        # Reencaminha lhe o pedido 
                        self.send_rtsp_request(rtsp_socket, request, neighbor_socket, filename)
                        self.client_session[filename][neighbor_address[0]]['status'] = "READY"
                           
                elif "PLAY" in request and neighbor_status == "READY":   
                    self.client_session[filename][neighbor_address[0]]['status'] = "PLAYING"
                    seq = lines[1].split(' ')[1]
                    # Responde ao node com a confirmação
                    self.replyRtsp(self.OK_200, seq[1], self.client_session[filename][neighbor_address[0]]['session'], neighbor_socket)
                    # Começa a enviar os pacotes rtp
                    self.handle_rtp_forwarding(request, neighbor_address[0], self.client_session[filename][neighbor_address[0]]['session']) 
                
                elif "PAUSE" in request and neighbor_status == "PLAYING":   
                    self.client_session[filename][neighbor_address[0]]['status'] = "READY"
                    seq = lines[1].split(' ')[1]
                    # Responde ao node com a confirmação
                    self.replyRtsp(self.OK_200, seq[1], self.client_session[filename][neighbor_address[0]]['session'], neighbor_socket)
                
                elif "TEARDOWN" in request:   
                    self.remove_connection(filename, neighbor_address[0])
                
                else:
                    active_route = self.get_active_route(filename)
                    rtsp_port = active_route['route_info']['rtsp_port']
                    dest = active_route['destination']
                    rtsp_socket = self.get_or_create_rtsp_connection(filename, dest, rtsp_port) # Conecta se com o vizinho ativo
                    self.send_rtsp_request(rtsp_socket, request, neighbor_socket, filename)
                    
            except Exception as e:
                print(f"Ocorreu um erro: {e}")
                break
            
    def get_route_with_stream(self, stream_id):
        """
        Verifica se há uma rota ativa para o fluxo (stream_id) na tabela de roteamento
        e retorna a rota se encontrada.
        """
        with self.lock:
            for destination, routes in self.routing_table.items():
                # Verifica se a stream_id existe na rota e está ativa
                if stream_id in routes and routes[stream_id].get("flow") == "active":
                    return {
                        "destination": destination,
                        "route_info": routes[stream_id]
                    }
        return None
    
    def get_active_route(self, stream_id):
        """
        Verifica se há uma rota ativa para o fluxo (stream_id) na tabela de roteamento
        e retorna a rota se encontrada.
        """
        with self.lock:
            for destination, routes in self.routing_table.items():
                # Verifica se a stream_id existe na rota e está ativa
                if stream_id in routes and routes[stream_id].get("status") == "active":
                    return {
                        "destination": destination,
                        "route_info": routes[stream_id]
                    }
        return None

    def get_or_create_rtsp_connection(self, filename, destination_ip, rtsp_port):
        """Verifica se uma conexão RTSP persistente existe, e a cria se não existir."""
        self.neighbors_rtsp.setdefault(destination_ip, {})
               
        if 'rtsp_socket' not in self.neighbors_rtsp[destination_ip]:  
            try:
                rtsp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                rtsp_socket.connect((destination_ip, rtsp_port))
                self.neighbors_rtsp[destination_ip]['rtsp_socket'] = rtsp_socket
                print(f"Conexão RTSP persistente criada para {destination_ip}:{rtsp_port}")
            except Exception as e:
                print(f"Erro ao criar conexão RTSP para {destination_ip}:{rtsp_port}: {e}")
                return None
        else:
            print(f"Reutilizando conexão RTSP existente para {destination_ip}:{rtsp_port}")
        return self.neighbors_rtsp[destination_ip]['rtsp_socket']

    def send_rtsp_request(self, rtsp_socket, request, neighbor_socket, filename):
        """Envia a requisição RTSP e encaminha a resposta ao vizinho."""
        try:
            rtsp_socket.send(request.encode())
            print(f"Requisição RTSP enviada")

            # Receber a resposta do vizinho RTSP
            response = rtsp_socket.recv(1024).decode()
            print(f"RECEBEU A RESPOSTA DO VIZINHO : {response}")

            # Enviar a resposta de volta ao vizinho
            neighbor_socket.send(response.encode())
            print(f"Enviou para o vizinho a resposta pela socket  : {neighbor_socket}")
                
        except Exception as e:
            print(f"Falha ao enviar requisição RTSP: {e}")

    def handle_rtp_forwarding(self, request, neighbor_ip, neighbor_rtp_port):
        """Inicia o encaminhamento dos pacotes RTP para o vizinho após a requisição SETUP."""
        threading.Thread(target=self.forward_rtp, args=(neighbor_ip, neighbor_rtp_port)).start()

    def forward_rtp(self, client_ip, client_rtp_port):
        # Criar um socket UDP para receber os pacotes RTP do vizinho
        rtp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        rtp_socket.bind((self.node_ip, self.rtp_port))  # Porta do proxy

        print(f"Encaminhando RTP para o cliente {client_ip}:{client_rtp_port}")
        
        for filename, client_info in self.client_session[filename].items():
            if "rtpSocket" not in client_info:
                client_info["rtpSocket"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        
        while True:
            data, addr = rtp_socket.recvfrom(20480)
            if data:

                for filename, client_info in self.client_session[filename].items():
                    if "rtpSocket" in client_info:  # Verifica se o socket está configurado
                        client_socket = client_info["rtpSocket"]
                        client_rtp_port = client_info['rtp_port']
                        print(f"Pacote RTP recebido do vizinho, enviando ao cliente {client_info['source_ip']}:{client_rtp_port}")
                        client_socket.sendto(data, (client_info['source_ip'], client_rtp_port))
                    else:
                        print(f"Socket RTP não configurado para o cliente {client_info['source_ip']}, ignorando.")
             
    def remove_connection(filename, neighbor_address):
        # Verifique se o filename e o cliente existem na sessão
        if filename in self.client_session and neighbor_address in self.client_session[filename]:
            # Fecha o socket RTP se ele existir
            if "rtpSocket" in self.client_session[filename][neighbor_address]:
                try:
                    self.client_session[filename][neighbor_address]["rtpSocket"].close()
                    print(f"RTP socket para {neighbor_address} fechado.")
                except Exception as e:
                    print(f"Erro ao fechar RTP socket para {neighbor_address}: {e}")
            
            # Fecha o socket RTSP se ele existir
            if "rtspSocket" in self.client_session[filename][neighbor_address]:
                try:
                    self.client_session[filename][neighbor_address]["rtspSocket"].close()
                    print(f"RTSP socket para {neighbor_address} fechado.")
                except Exception as e:
                    print(f"Erro ao fechar RTSP socket para {neighbor_address}: {e}")

            # Remove o cliente do dicionário
            self.client_session[filename].pop(neighbor_address)
            print(f"Cliente {neighbor_address} removido de {filename}")

            # Se o dicionário do filename está vazio, remova também
            if not self.client_session[filename]:  # Verifica se não há mais clientes
                self.client_session.pop(filename)
                
                # Como o node nao tem mais clientes para enviar, avisa o vizinho que o está a enviar pacotes para parar de o fazer
                active_route = self.get_active_route(filename)
                rtsp_port = active_route['route_info']['rtsp_port']
                dest = active_route['destination']
                rtsp_socket = self.get_or_create_rtsp_connection(filename, dest, rtsp_port) # Conecta se com o vizinho ativo
                # Reencaminha lhe o pedido 
                self.send_rtsp_request(rtsp_socket, request, neighbor_socket, filename)         
                print(f"Removido {filename} do dicionário pois não há mais clientes.")
        else:
            print(f"Cliente {neighbor_address} não encontrado em {filename}")
           
    def replyRtsp(self, code, seq, session, neighbor_socket):
        """Send RTSP reply to the client."""
        if code == self.OK_200:
            #print("200 OK")
            reply = 'RTSP/1.0 200 OK\nCSeq: ' + seq + '\nSession: ' + session
            neighbor_socket.send(reply.encode())
        
        # Error messages
        elif code == self.FILE_NOT_FOUND_404:
            print("404 NOT FOUND")
        elif code == self.CON_ERR_500:
            print("500 CONNECTION ERROR")
   
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
