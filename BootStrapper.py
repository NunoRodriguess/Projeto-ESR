    # def ping_nodes(self, node_id, control_port, ip_address):
    #     """
    #     Função para enviar mensagens de PING para a porta de controle de um nó e receber o PONG.
    #     """
    #     while True:
    #         time.sleep(self.ping_interval)
    #         try:
    #             # Conectar à porta de controle do nó para enviar o PING
    #             with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    #                 s.connect((ip_address, control_port))  # Usar o IP e a porta de controle do nó

    #                 # Enviar o PING
    #                 ping_message = ControlMessage()
    #                 ping_message.type = ControlMessage.PING
    #                 ping_message.node_id = "Bootstrapper"
    #                 s.send(ping_message.SerializeToString())
    #                 print(f"Sent PING to {node_id} on control port {control_port}")

    #                 # Receber o PONG
    #                 s.settimeout(self.timeout)
    #                 data = s.recv(1024)
    #                 if data:
    #                     pong_message = ControlMessage()
    #                     pong_message.ParseFromString(data)
    #                     if pong_message.type == ControlMessage.PONG:
    #                         print(f"Received PONG from {node_id}")

    #                         # Atualizar o tempo do último PONG recebido
    #                         with self.lock:
    #                             if node_id in self.nodes:
    #                                 self.nodes[node_id] = (self.nodes[node_id][0], self.nodes[node_id][1],
    #                                                     self.nodes[node_id][2], time.time())

    #         except socket.timeout:
    #             print(f"Node {node_id} did not respond in time. Removing node.")
    #             with self.lock:
    #                 if node_id in self.nodes:
    #                     del self.nodes[node_id]
    #             break

    #         except Exception as e:
    #             print(f"Error sending PING to node {node_id}: {e}")
    #             with self.lock:
    #                 if node_id in self.nodes:
    #                     del self.nodes[node_id]
    #             break

import socket
import threading
from control_protocol_pb2 import ControlMessage, NeighborInfo

class Bootstrapper:
    def __init__(self, host='0.0.0.0', port=5000, config_file='config.txt'):
        self.host = host
        self.port = port
        self.nodes = {}  # Dicionário para armazenar informações dos nós registrados
        self.neighbors_config = self.load_neighbors(config_file)
<<<<<<< Updated upstream
=======
        self.ping_interval = ping_interval
        self.timeout = timeout
        self.lock = threading.Lock()
>>>>>>> Stashed changes

    def load_neighbors(self, config_file):
        neighbors = {}
        with open(config_file, 'r') as file:
            for line in file:
                parts = line.strip().split('|')
                main_node_info = parts[0].strip().split()  
                main_node_id, main_node_ip = main_node_info[0], main_node_info[1]
                
                neighbors_list = []
                for neighbor in parts[1:]:
                    neighbor_info = neighbor.strip().split()
                    neighbor_id, neighbor_ip = neighbor_info[0], neighbor_info[1]
                    neighbors_list.append((neighbor_id, neighbor_ip))  
                
                neighbors[main_node_ip] = {
                    "node_id": main_node_id,
                    "neighbors": neighbors_list
                }
        return neighbors

<<<<<<< Updated upstream
    def handle_client(self, conn, addr):
        print(f"Connected by {addr}")
        
        # Receber a mensagem de controle do node
        data = conn.recv(1024)
        control_message = ControlMessage()
        control_message.ParseFromString(data)
        
        if control_message.type == ControlMessage.REGISTER:
            node_id = control_message.node_id
            control_port = control_message.control_port
            data_port = control_message.data_port

            # Adicionar o node à lista de registrados
            self.nodes[node_id] = (addr[0], control_port, data_port)
            print(f"Registered node {node_id} at {addr[0]}:{control_port}")

            # Criar a mensagem de resposta com os vizinhos
            response = ControlMessage()
            response.type = ControlMessage.REGISTER_RESPONSE
            response.node_id = node_id

            # Adiciona os vizinhos à mensagem de resposta com base no arquivo de configuração
            if node_id in self.neighbors_config:
                for neighbor_id in self.neighbors_config[node_id]:
                    if neighbor_id in self.nodes:
                        _, cport, dport = self.nodes[neighbor_id]
                        neighbor = NeighborInfo()
                        neighbor.node_id = neighbor_id
                        neighbor.control_port = cport
                        neighbor.data_port = dport
                        response.neighbors.append(neighbor)

            # Envia a resposta com a lista de vizinhos
            conn.send(response.SerializeToString())
            
            # Atualizar vizinhos de todos os nós
            self.update_neighbors(node_id)

        conn.close()

    def update_neighbors(self, new_node_id):
        for nid in self.nodes:
            if nid != new_node_id:
                # Criar uma mensagem para atualizar vizinhos
                update_message = ControlMessage()
                update_message.type = ControlMessage.UPDATE_NEIGHBORS
                update_message.node_id = new_node_id

                # Adicionar vizinhos do novo nó
                if new_node_id in self.neighbors_config:
                    for neighbor_id in self.neighbors_config[new_node_id]:
                        if neighbor_id in self.nodes:
                            neighbor_info = NeighborInfo()
                            neighbor_info.node_id = neighbor_id
                            neighbor_info.ip, neighbor_info.control_port, neighbor_info.data_port = self.nodes[neighbor_id]
                            update_message.neighbors.append(neighbor_info)

                # Enviar a atualização para cada nó
                node_ip, node_control_port, _ = self.nodes[nid]
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((node_ip, node_control_port))
                    s.send(update_message.SerializeToString())
                
=======
    def update_neighbors(self, new_node_ip):
        """
        Conecta-se à porta de controle do nó quando necessário para enviar uma atualização de vizinhos.
        """
        if new_node_ip in self.neighbors_config:
            new_node = self.nodes[new_node_ip]

            for neighbor_id, neighbor_ip in self.neighbors_config[new_node_ip]["neighbors"]:
                if neighbor_ip in self.nodes:  # Verifica se o vizinho está registrado
                    neighbor_node = self.nodes[neighbor_ip]
                    
                    try:
                        # Conecta-se ao vizinho na porta de controle
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                            s.connect((neighbor_ip, neighbor_node["control_port"]))
                            
                            neighbor_update_message = ControlMessage()
                            neighbor_update_message.type = ControlMessage.UPDATE_NEIGHBORS
                            neighbor_update_message.node_ip = neighbor_ip
                            neighbor_update_message.node_id = neighbor_id

                            new_neighbor_info = NeighborInfo()
                            new_neighbor_info.node_id = new_node["node_id"]
                            new_neighbor_info.node_ip = new_node_ip
                            new_neighbor_info.control_port = new_node["control_port"]
                            new_neighbor_info.data_port = new_node["data_port"]
                            neighbor_update_message.neighbors.append(new_neighbor_info)

                            s.send(neighbor_update_message.SerializeToString())
                            print(f"Updated neighbor {neighbor_ip} with new node {new_node_ip}.")

                    except Exception as e:
                        print(f"Failed to update neighbor {neighbor_ip} with new node {new_node_ip}: {e}")

    def handle_client(self, conn):
        try:
            conn.settimeout(self.timeout)
            data = conn.recv(1024)

            if data:
                control_message = ControlMessage()
                control_message.ParseFromString(data)

                if control_message.type == ControlMessage.REGISTER:
                    node_id = control_message.node_id
                    node_ip = control_message.node_ip
                    control_port = control_message.control_port
                    data_port = control_message.data_port

                    with self.lock:
                        self.nodes[node_ip] = {
                            "node_id": node_id,
                            "control_port": control_port,
                            "data_port": data_port
                        }
                    print(f"Registered node {node_id} at {node_ip}:{control_port}")
                    
                    response = ControlMessage()
                    response.type = ControlMessage.REGISTER_RESPONSE
                    response.node_ip = node_ip
                    
                    # Adiciona os vizinhos à resposta se houver
                    if node_ip in self.neighbors_config:
                        for neighbor_id, neighbor_ip in self.neighbors_config[node_ip]["neighbors"]:
                            if neighbor_ip in self.nodes:  # Apenas envia vizinhos registrados
                                neighbor_info = NeighborInfo()
                                neighbor_info.node_id = neighbor_id
                                neighbor_info.node_ip = neighbor_ip
                                neighbor_info.control_port = self.nodes[neighbor_ip]["control_port"]
                                neighbor_info.data_port = self.nodes[neighbor_ip]["data_port"]
                                response.neighbors.append(neighbor_info) 
                            
                    conn.send(response.SerializeToString())
                    print(f"Sent registration confirmation to {node_ip}")

                    # Desconecta a conexão de registro
                    conn.close()

                    # Reestabelece a conexão para atualização de vizinhos
                    self.update_neighbors(node_ip)

        except Exception as e:
            print(f"Error handling connection from {node_ip}: {e}")
            if conn:
                conn.close()

>>>>>>> Stashed changes
    def start(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.host, self.port))
            s.listen()
            print(f"Bootstrapper listening on {self.host}:{self.port}")
            
            while True:
                conn, addr = s.accept()
                threading.Thread(target=self.handle_client, args=(conn,)).start()

if __name__ == "__main__":
    bootstrapper = Bootstrapper()
    bootstrapper.start()

