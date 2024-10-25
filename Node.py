import socket
import threading
import sys
import time
from control_protocol_pb2 import ControlMessage

class Node:
<<<<<<< Updated upstream
    def __init__(self, node_id, control_port=5001, data_port=5002, bootstrapper_host='localhost', bootstrapper_port=5000):
=======
    """
    Classe Node que representa um nó em uma rede P2P.
    O nó registra-se em um Bootstrapper e mantém conexões com seus vizinhos.
    """
    
    def __init__(self, node_id, node_ip, control_port=5001, data_port=5002, bootstrapper_host='localhost', bootstrapper_port=5000):
        """
        Inicializa um nó com identificador e portas específicas.

        :node_id: Identificador único do nó.
        :control_port: Porta de controle para comunicação entre nós.
        :data_port: Porta para transmissão de dados.
        :bootstrapper_host: Endereço do Bootstrapper para o registro.
        :bootstrapper_port: Porta do Bootstrapper para o registro.
        """
        self.node_ip = node_ip
>>>>>>> Stashed changes
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
            control_message.node_ip = self.node_ip
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
<<<<<<< Updated upstream
                    # Atualizar vizinhos como um dicionário
                    for n in response_message.neighbors:
                        self.neighbors[n.node_id] = NeighborInfo(
                            node_id=n.node_id,
                            control_port=n.control_port,
                            data_port=n.data_port
                        )
                    print(f"Node {self.node_id} registered with neighbors: {self.neighbors}")
=======
                    print(f"Node {self.node_id} registered")
                    for neighbor in response_message.neighbors:
                        self.neighbors[neighbor.node_ip] = {
                            "node_id": neighbor.node_id,
                            "control_port": neighbor.control_port,
                            "data_port": neighbor.data_port
                        }
                    print(f"Node {self.node_id} neighbors: {self.neighbors}")
                    
>>>>>>> Stashed changes
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
<<<<<<< Updated upstream
                if not data:
                    break
                
                control_message = ControlMessage()
                control_message.ParseFromString(data)
=======
                if data:
                    control_message = ControlMessage()
                    try:
                        control_message.ParseFromString(data)
                    except Exception as e:
                        print(f"Failed to parse control message: {e}")
                        continue  # Ignora a mensagem se não conseguir analisá-la

                    # Atualizar vizinhos
                    if control_message.type == ControlMessage.UPDATE_NEIGHBORS:
                        self.handle_update_neighbors(control_message)
>>>>>>> Stashed changes

                if control_message.type == ControlMessage.PING:
                    self.handle_ping(control_message, conn)
                if control_message.type == ControlMessage.UPDATE_NEIGHBORS:
                    self.handle_update_neighbors(control_message)
                    
    def handle_update_neighbors(self, control_message):
        print(f"Updating neighbors with {control_message.node_id}")
        for neighbor in control_message.neighbors:
            neighbor_id = neighbor.node_id
            neighbor_ip = neighbor.node_ip
            control_port = neighbor.control_port
            data_port = neighbor.data_port
            # Armazena as informações do vizinho na estrutura do nó
            self.neighbors[neighbor_ip] = {
                "node_id": neighbor_id,
                "control_port": control_port,
                "data_port": data_port
            }
        print(f"Updated neighbors: {self.neighbors}")
<<<<<<< Updated upstream
        
    def data_server(self):
        # Implementar lógica do servidor de dados
=======
    
    ### Funcionalidades de comunicação de dados

    def data_server(self):
        """
        Implementa a lógica do servidor de dados.
        """
        # print(f"Data server running on port {self.data_port}")
        # with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        #     s.bind(('', self.data_port))
        #     s.listen()
        #     while True:
        #         conn, addr = s.accept()
        #         print(f"Data connection from {addr} established.")
        #         conn.close()
>>>>>>> Stashed changes
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
<<<<<<< Updated upstream
    if len(sys.argv) != 3:
        print("Usage: python Node.py <bootstrapper_ip> <node_id>")
=======
    """
    Função principal para executar o nó.
    Recebe o endereço do Bootstrapper e o ID do nó como parâmetros de linha de comando.
    """
    if len(sys.argv) != 4:
        print("Usage: python Node.py <bootstrapper_ip> <node_id> <node_ip>")
>>>>>>> Stashed changes
        sys.exit(1)

    bootstrapper = sys.argv[1]
    node_id = sys.argv[2]
<<<<<<< Updated upstream
    control_port = 50051
    data_port = 50052
=======
    node_ip = sys.argv[3]
    control_port = 50051  # Porta de controle padrão
    data_port = 50052     # Porta de dados padrão
>>>>>>> Stashed changes

    node = Node(node_id, node_ip, control_port, data_port, bootstrapper)
    node.start()
    
if __name__ == "__main__":
    main()
    