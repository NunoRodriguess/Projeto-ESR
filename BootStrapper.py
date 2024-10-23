import socket
import threading
from control_protocol_pb2 import ControlMessage, NeighborInfo

class Bootstrapper:
    def __init__(self, host='0.0.0.0', port=5000, config_file='config.txt'):
        self.host = host
        self.port = port
        self.nodes = {}
        self.neighbors_config = self.load_neighbors(config_file)

    def load_neighbors(self, config_file):
        neighbors = {}
        with open(config_file, 'r') as file:
            for line in file:
                parts = line.strip().split(':')
                if len(parts) == 2:
                    node = parts[0].strip()
                    neighbors_list = [n.strip() for n in parts[1].split(',')]
                    neighbors[node] = neighbors_list
        return neighbors

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
                
    def start(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.host, self.port))
            s.listen()
            print(f"Bootstrapper listening on {self.host}:{self.port}")
            
            while True:
                conn, addr = s.accept()
                threading.Thread(target=self.handle_client, args=(conn, addr)).start()

if __name__ == "__main__":
    bootstrapper = Bootstrapper()
    bootstrapper.start()
