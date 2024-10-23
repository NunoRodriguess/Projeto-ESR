import socket
import threading
from control_protocol_pb2 import ControlMessage, NeighborInfo

class Bootstrapper:
    def __init__(self, host='0.0.0.0', port=5000):
        self.host = host
        self.port = port
        self.nodes = {}  # Dicionário que guarda os nós e suas conexões

    def add_neighbor(self, node_a, node_b):
        """Adiciona a relação de vizinhança entre dois nós."""
        if node_a not in self.nodes:
            self.nodes[node_a] = []  # Cria a chave se não existir
        if node_b not in self.nodes[node_a]:
            self.nodes[node_a].append(node_b)  # Adiciona node_b à lista de node_a

        if node_b not in self.nodes:
            self.nodes[node_b] = []  # Cria a chave se não existir
        if node_a not in self.nodes[node_b]:
            self.nodes[node_b].append(node_a)  # Adiciona node_a à lista de node_b

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

            # Se o nó que acabou de se registrar não tem nenhum vizinho
            # ele será adicionado como uma nova chave no dicionário
            print(f"Registered node {node_id} at {addr[0]}:{control_port}")

            # Vamos ver quem já está na rede, para decidir a relação de vizinhos
            if len(self.nodes) == 0:
                # Primeiro nó a se conectar, não terá vizinhos
                self.nodes[node_id] = []
            else:
                # Enviar os vizinhos do nó anterior (o último nó registrado)
                previous_node_id = list(self.nodes.keys())[-1]  # O último nó registrado
                self.add_neighbor(previous_node_id, node_id)  # Adiciona a relação mútua

            # Criar a resposta contendo apenas os vizinhos diretos do nó atual
            response = ControlMessage()
            response.type = ControlMessage.REGISTER_RESPONSE
            response.node_id = node_id

            # Adiciona os vizinhos diretos à mensagem de resposta
            for neighbor_id in self.nodes[node_id]:
                neighbor_ip, neighbor_cport, neighbor_dport = addr[0], control_port, data_port  # Mesmo IP para exemplo
                neighbor_info = NeighborInfo()
                neighbor_info.node_id = neighbor_id
                neighbor_info.ip = neighbor_ip  # Usando o IP do atual para fins de exemplo
                neighbor_info.control_port = neighbor_cport
                neighbor_info.data_port = neighbor_dport
                response.neighbors.append(neighbor_info)

            # Enviar a lista de vizinhos diretos ao nó que acabou de se registrar
            conn.send(response.SerializeToString())

        conn.close()

    def start(self):
        # Iniciar o servidor para aceitar conexões
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
