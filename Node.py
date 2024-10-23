import socket
import threading
import sys
import time
from control_protocol_pb2 import ControlMessage, NeighborInfo

class Node:
    def __init__(self, node_id, control_port=5001, data_port=5002, bootstrapper_host='localhost', bootstrapper_port=5000):
        self.node_id = node_id
        self.control_port = control_port
        self.data_port = data_port
        self.neighbors = {}  # Dicionário para armazenar vizinhos
        self.bootstrapper = (bootstrapper_host, bootstrapper_port)
        self.lock = threading.Lock()

    def register_with_bootstrapper(self):
        # Conectar-se ao Bootstrapper
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect(self.bootstrapper)  # Conectar usando o endereço do bootstrapper
            
            # Criar a mensagem de controle para registro
            control_message = ControlMessage()
            control_message.type = ControlMessage.REGISTER
            control_message.node_id = self.node_id
            control_message.control_port = self.control_port
            control_message.data_port = self.data_port
            
            # Enviar a mensagem para o Bootstrapper
            s.send(control_message.SerializeToString())
            
            # Receber a resposta do Bootstrapper
            data = s.recv(1024)
            if data:
                response_message = ControlMessage()
                response_message.ParseFromString(data)
            
                # Processar a resposta
                if response_message.type == ControlMessage.REGISTER_RESPONSE:
                    # Atualizar vizinhos como um dicionário
                    for n in response_message.neighbors:
                        self.neighbors[n.node_id] = NeighborInfo(
                            node_id=n.node_id,
                            ip=n.ip,
                            control_port=n.control_port,
                            data_port=n.data_port
                        )
                    print(f"Node {self.node_id} registered with neighbors: {self.neighbors}")
                else:
                    print(f"Unexpected response type: {response_message.type}")

    def start(self):
        self.register_with_bootstrapper()
        threading.Thread(target=self.control_server).start()
        threading.Thread(target=self.data_server).start()
        threading.Thread(target=self.send_ping).start()

    #Lidar com as mensagens de controlo 
    def control_server(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', self.control_port))
            s.listen()
            print(f"Node {self.node_id} listening on control port {self.control_port}")
            while True:
                conn, addr = s.accept()
                threading.Thread(target=self.handle_control_connection, args=(conn, addr)).start()

    #Processar mensagens de controlo
    def handle_control_connection(self, conn, addr):
        print(f"Connection from {addr} established.")
        with conn:
            while True:
                data = conn.recv(1024)
                if not data:
                    break
                
                control_message = ControlMessage()
                control_message.ParseFromString(data)

                if control_message.type == ControlMessage.PING:
                    self.handle_ping(control_message, conn)
                    
    def data_server(self):
        # Implementar lógica do servidor de dados
        pass

    # Responder a uma mensagem de ping
    def handle_ping(self, control_message, conn):
        print(f"Received PING from {control_message.node_id}")
        pong_message = ControlMessage()
        pong_message.type = ControlMessage.PONG
        pong_message.node_id = control_message.node_id
        conn.send(pong_message.SerializeToString())
        print(f"Sent PONG to {control_message.node_id}")

    # Enviar mensagens de ping ao bootstrapper
    def send_ping(self):
        while True:
            time.sleep(300)  # Envia ping a cada 5 minutos
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.connect(self.bootstrapper)
                    message = ControlMessage()
                    message.type = ControlMessage.PING
                    message.node_id = self.node_id
                    s.send(message.SerializeToString())
                    
                    # Espera pela resposta PONG
                    data = s.recv(1024)
                    if data:
                        response_message = ControlMessage()
                        response_message.ParseFromString(data)
                        if response_message.type == ControlMessage.PONG:
                            print(f"Received PONG from {response_message.node_id}")
                except Exception as e:
                    print(f"Failed to send ping: {e}")

def main():
    if len(sys.argv) != 2:
        print("Usage: python Node.py <bootstrapper_ip>")
        sys.exit(1)

    bootstrapper = sys.argv[1]
    node_id = f"Node-{int(time.time())}"
    control_port = 50051
    data_port = 50052

    node = Node(node_id, control_port, data_port, bootstrapper)
    node.start()
    
if __name__ == "__main__":
    main()
