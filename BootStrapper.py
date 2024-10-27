import socket
import threading
from control_protocol_pb2 import ControlMessage, NeighborInfo

class Bootstrapper:
    def __init__(self, host='0.0.0.0', port=5000, config_file='config.txt'):
        self.host = host
        self.port = port
        self.nodes = {}  # Dicionário para armazenar informações dos nós/clientes registrados
        self.neighbors_config = self.load_neighbors(config_file)

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

    def handle_client(self, conn):
        try:
            data = conn.recv(1024)

            if data:
                control_message = ControlMessage()
                control_message.ParseFromString(data)

                if control_message.type == ControlMessage.REGISTER:
                    self.handle_register(control_message, conn)

        except Exception as e:
            print(f"Error handling connection: {e}")
        finally:
            conn.close()
            
    def handle_register(self, control_message, conn):
        node_id = control_message.node_id
        node_ip = control_message.node_ip
        control_port = control_message.control_port
        data_port = control_message.data_port
        node_type = control_message.node_type

        # Registra o nó
        self.nodes[node_ip] = {
            "node_id": node_id,
            "control_port": control_port,
            "data_port": data_port,
            "node_type": node_type,
        }
        print(f"Registered node {node_id} at {node_ip}:{control_port}")

        # Resposta de registro
        response = ControlMessage()
        response.type = ControlMessage.REGISTER_RESPONSE
        
        # Adiciona os vizinhos ativos à resposta
        if node_ip in self.neighbors_config:
            for neighbor_id, neighbor_ip in self.neighbors_config[node_ip]["neighbors"]:
                if neighbor_ip in self.nodes:
                    neighbor_info = NeighborInfo()
                    neighbor_info.node_id = neighbor_id
                    neighbor_info.node_ip = neighbor_ip
                    neighbor_info.control_port = self.nodes[neighbor_ip]["control_port"]
                    neighbor_info.data_port = self.nodes[neighbor_ip]["data_port"]
                    response.neighbors.append(neighbor_info) 
                
        conn.send(response.SerializeToString())
        print(f"Sent registration confirmation to {node_ip}")

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
