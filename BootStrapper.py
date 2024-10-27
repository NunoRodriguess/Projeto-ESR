import socket
import threading
import time
from control_protocol_pb2 import ControlMessage, NeighborInfo

class Bootstrapper:
    def __init__(self, host='0.0.0.0', port=5000, config_file='config.txt', ping_interval=10, timeout=20):
        self.host = host
        self.port = port
        self.nodes = {}  # Dicionário para armazenar informações dos nodes/clientes registrados
        self.neighbors_config = self.load_neighbors(config_file)
        self.ping_interval = ping_interval
        self.timeout = timeout
        self.lock = threading.Lock()

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

    def update_neighbors(self, new_node_ip):
        """
        Conecta-se à porta de controle do nó quando necessário para enviar uma atualização de vizinhos.
        """
        if new_node_ip in self.neighbors_config:
            new_node = self.nodes[new_node_ip]

            for neighbor_id, neighbor_ip in self.neighbors_config[new_node_ip]["neighbors"]:
                if neighbor_ip in self.nodes and self.nodes[neighbor_ip]['status'] == 'active':  # Apenas envia vizinhos registados ativos
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
                            new_neighbor_info.node_type = new_node["node_type"]
                            neighbor_update_message.neighbors.append(new_neighbor_info)

                            s.send(neighbor_update_message.SerializeToString())
                            print(f"Updated neighbor {neighbor_ip} with new node {new_node_ip}.")

                    except Exception as e:
                        print(f"Failed to update neighbor {neighbor_ip} with new node {new_node_ip}: {e}")
                        
    def notify_neighbor_inactive(self, neighbor_ip):
        """
        Atualiza o status do vizinho como inativo.

        :param node_ip: O IP do nó que está informando a inatividade.
        :param inactive_neighbor_ip: O IP do vizinho considerado inativo.
        """
        with self.lock:
            # Atualiza o status do vizinho como inativo
            if neighbor_ip in self.nodes:
                self.nodes[neighbor_ip]['status'] = "inactive"
                print(f"Node {self.nodes[neighbor_ip]['node_id']} is inactive.")


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
                    node_type = control_message.node_type

                    with self.lock:
                        if node_ip in self.nodes:
                            self.nodes[node_ip]['status'] = "active"
                            if node_type == "node":
                                print(f"Node {node_id} reactivated.")
                            else:
                                print(f"Client {node_id} reactivated.")
                        else:           
                            self.nodes[node_ip] = {
                                "node_id": node_id,
                                "control_port": control_port,
                                "data_port": data_port,
                                "node_type": node_type,
                                "status": "active" 
                            }
                            if node_type == "node":
                                print(f"Registered node {node_id} at {node_ip}:{control_port}")
                            else:
                                print(f"Registered client {node_id} at {node_ip}:{control_port}")

                    response = ControlMessage()
                    response.type = ControlMessage.REGISTER_RESPONSE
                    
                    # Adiciona os vizinhos à resposta se houver
                    if node_ip in self.neighbors_config:
                        for neighbor_id, neighbor_ip in self.neighbors_config[node_ip]["neighbors"]:
                            if neighbor_ip in self.nodes and self.nodes[neighbor_ip]['status'] == 'active':  # Apenas envia vizinhos registados ativos
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
                
                elif control_message.type == ControlMessage.INACTIVE_NODE:
                    # Lida com a notificação de nó inativo
                    inactive_neighbor_ip = control_message.node_ip  # IP do vizinho inativo
                    self.notify_neighbor_inactive(inactive_neighbor_ip)

        except Exception as e:
            print(f"Error handling connection from {node_ip}: {e}")
            if conn:
                conn.close()

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
