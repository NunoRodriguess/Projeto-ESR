import socket
import threading
from control_protocol_pb2 import ControlMessage, NeighborInfo

class Bootstrapper:
    def __init__(self, host='0.0.0.0', port=5000):
        self.host = host
        self.port = port
        self.nodes = {}  # Dicionário de nós registrados
        self.neighbors = {}  # Dicionário de vizinhos para cada nó

    def handle_client(self, conn, addr):
        print(f"Connected by {addr}")
        
        # Receber a mensagem de controle do nó
        data = conn.recv(1024)
        control_message = ControlMessage()
        control_message.ParseFromString(data)
        
        if control_message.type == ControlMessage.REGISTER:
            node_id = control_message.node_id
            control_port = control_message.control_port
            data_port = control_message.data_port

            # Registrar o nó na lista de nós
            self.nodes[node_id] = (addr[0], control_port, data_port)
            print(f"Registered node {node_id} at {addr[0]}:{control_port}")

            # Definir manualmente os vizinhos (ou gerar dinamicamente conforme necessário)
            if node_id not in self.neighbors:
                self.neighbors[node_id] = []  # Inicializa a lista de vizinhos

            # Exemplo de como adicionar vizinhos manualmente
            # Isso pode ser modificado para uma estratégia dinâmica
            for existing_node in self.nodes:
                if existing_node != node_id:
                    self.neighbors[node_id].append(existing_node)
                    self.neighbors[existing_node].append(node_id)  # Conexão bidirecional

            # Criar a mensagem de resposta com os vizinhos diretos do nó
            response = ControlMessage()
            response.type = ControlMessage.REGISTER_RESPONSE
            response.node_id = node_id

            # Adiciona os vizinhos à mensagem de resposta
            for neighbor_id in self.neighbors[node_id]:
                nip, cport, dport = self.nodes[neighbor_id]
                neighbor_info = NeighborInfo()
                neighbor_info.node_id = neighbor_id
                neighbor_info.ip = nip
                neighbor_info.control_port = cport
                neighbor_info.data_port = dport
                response.neighbors.append(neighbor_info)
            
            # Envia a resposta com a lista de vizinhos diretos
            conn.send(response.SerializeToString())

        conn.close()

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

