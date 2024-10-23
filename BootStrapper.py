import socket
import threading
from control_protocol_pb2 import ControlMessage, NeighborInfo

class Bootstrapper:
    def __init__(self, host='0.0.0.0', port=5000):
        self.host = host
        self.port = port
        self.nodes = {}

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

            # Adiciona os vizinhos à mensagem de resposta
            for nid, (nip, cport, dport) in self.nodes.items():
                if nid != node_id:
                    neighbor = NeighborInfo()
                    neighbor.node_id = nid
                    neighbor.ip = nip
                    neighbor.control_port = cport
                    neighbor.data_port = dport
                    response.neighbors.append(neighbor)
            
            # Envia a resposta com a lista de vizinhos
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
