import socket
from overlay_pb2 import ControlMessage, NeighborInfo

class Node:
    def __init__(self, node_id, ip_address, control_port=5001, data_port=5002, bootstrapper_host='localhost', bootstrapper_port=5000):
        self.node_id = node_id
        self.ip_address = ip_address
        self.control_port = control_port
        self.data_port = data_port
        self.bootstrapper_host = bootstrapper_host
        self.bootstrapper_port = bootstrapper_port
        self.neighbors = []

    def register_with_bootstrapper(self):
        # Conectar-se ao Bootstrapper
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((self.bootstrapper_host, self.bootstrapper_port))
            
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
            response_message = ControlMessage()
            response_message.ParseFromString(data)
            
            # Processar a resposta
            if response_message.type == ControlMessage.REGISTER_RESPONSE:
                self.neighbors = [NeighborInfo(node_id=n.node_id, ip=n.ip, control_port=n.control_port, data_port=n.data_port) for n in response_message.neighbors]
                print(f"Node {self.node_id} registered with neighbors: {self.neighbors}")
            else:
                print(f"Unexpected response type: {response_message.type}")

if __name__ == "__main__":
    node = Node(node_id="node1", ip_address="192.168.0.1")
    node.register_with_bootstrapper()
