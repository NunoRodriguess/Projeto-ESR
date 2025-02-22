import socket
import threading
import sys
import time
from control_protocol_pb2 import ControlMessage

class Node:
    """
    Classe Node que representa um nó em uma rede P2P.
    O nó registra-se em um Bootstrapper e mantém conexões com seus vizinhos.
    """
    
    def __init__(self, node_id, node_ip, node_type, control_port=50051, data_port=50052, bootstrapper_host='localhost', bootstrapper_port=5000):
        """
        Inicializa um nó com identificador e portas específicas.

        :node_id: Identificador único do nó.
        :control_port: Porta de controle para comunicação entre nós.
        :data_port: Porta para transmissão de dados.
        :bootstrapper_host: Endereço do Bootstrapper para o registro.
        :bootstrapper_port: Porta do Bootstrapper para o registro.
        """
        self.node_ip = node_ip
        self.node_id = node_id
        self.control_port = control_port
        self.data_port = data_port
        self.neighbors = {}  # Dicionário para armazenar informações dos vizinhos
        self.bootstrapper = (bootstrapper_host, bootstrapper_port)
        self.lock = threading.Lock()  # Lock para sincronizar o acesso aos vizinhos
        self.node_type = node_type

    ### Funcionalidades de registro com o Bootstrapper

    def register_with_bootstrapper(self):
        """
        Registra o nó com o Bootstrapper e recebe uma lista de vizinhos.
        Envia uma mensagem de controle para o Bootstrapper e processa a resposta.
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect(self.bootstrapper)  # Conecta ao Bootstrapper
            
            # Cria a mensagem de controle para registro
            control_message = ControlMessage()
            control_message.type = ControlMessage.REGISTER
            control_message.node_id = self.node_id
            control_message.node_ip = self.node_ip
            control_message.control_port = self.control_port
            control_message.data_port = self.data_port
            control_message.node_type = self.node_type
            
            # Envia a mensagem de registro
            s.send(control_message.SerializeToString())
            
            # Recebe e processa a resposta
            data = s.recv(1024)
            if data:
                response_message = ControlMessage()
                response_message.ParseFromString(data)
                
                if response_message.type == ControlMessage.REGISTER_RESPONSE:
                    print(f"Node {self.node_id} registered")
                    self.neighbors.clear()  # Limpa vizinhos antigos para o caso de ser uma reativação
                    for neighbor in response_message.neighbors:
                        with self.lock: 
                            self.neighbors[neighbor.node_ip] = {
                                "node_id": neighbor.node_id,
                                "control_port": neighbor.control_port,
                                "data_port": neighbor.data_port,
                                "node_type": neighbor.node_type,
                                "status": "active",
                                "failed-attempts": 0
                            }
                    print(f"Node {self.node_id} neighbors: {self.neighbors}")
                    # Após o registro, notifica os vizinhos sobre o registro
                    self.notify_neighbors_registration()
                else:
                    print(f"Unexpected response type: {response_message.type}")

    def notify_neighbors_registration(self):
        """
        Notifica os vizinhos que o nó está registrado e que pode haver atualizações.
        """
        for neighbor_ip, neighbor_info in self.neighbors.items():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((neighbor_ip, neighbor_info['control_port']))
                    notify_message = ControlMessage()
                    notify_message.type = ControlMessage.UPDATE_NEIGHBORS
                    notify_message.node_id = self.node_id
                    notify_message.node_ip = self.node_ip
                    notify_message.control_port = self.control_port
                    notify_message.data_port = self.data_port
                    notify_message.node_type = self.node_type
                    s.send(notify_message.SerializeToString())
                    print(f"Notified neighbor {neighbor_info['node_id']} of registration.")

            except Exception as e:
                print(f"Failed to notify neighbor {neighbor_info['node_id']}: {e}")

    ### Funcionalidades de inicialização do nó

    def start(self):
        """
        Inicia o nó, registrando-o com o Bootstrapper e iniciando os servidores
        de controle e dados em threads separadas.
        """
        self.register_with_bootstrapper()
        threading.Thread(target=self.control_server).start()  # Inicia o servidor de controle em uma thread separada
        threading.Thread(target=self.data_server).start()     # Inicia o servidor de dados em uma thread separada
        threading.Thread(target=self.send_ping_to_neighbors).start()  # Enviar PING aos vizinhos

    ### Funcionalidades de comunicação de controle

    def control_server(self):
        """
        Inicia o servidor de controle que escuta em uma porta específica para conexões de outros nós.
        Lida com mensagens de controle como PING e atualizações de vizinhos.
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', self.control_port))
            s.listen()
            print(f"Node {self.node_id} listening on control port {self.control_port}")
            while True:
                conn, addr = s.accept()
                threading.Thread(target=self.handle_control_connection, args=(conn, addr)).start()

    def handle_control_connection(self, conn, addr):
        """
        Lida com as conexões de controle de outros nós.
        Responde a mensagens de PING e processa atualizações de vizinhos.

        :conn: Conexão de socket com outro nó.
        :addr: Endereço do nó conectado.
        """
        print(f"Connection from {addr} established.")
        with conn:
            while True:
                data = conn.recv(1024)
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
                    
                    # Enviar ping aos vizinhos (só para os nodes)
                    if control_message.type == ControlMessage.PING:
                        self.handle_ping(control_message, conn)

    def handle_update_neighbors(self, control_message):
        print(f"Updating neighbors with {control_message.node_id}")
        neighbor_id = control_message.node_id
        neighbor_ip = control_message.node_ip
        control_port = control_message.control_port
        data_port = control_message.data_port
        node_type = control_message.node_type
    
        with self.lock: 
                # Se o vizinho já estiver na lista, atualiza o status
                if neighbor_ip in self.neighbors:
                    self.neighbors[neighbor_ip]["status"] = "active"
                    print(f"Updated status of existing neighbor {neighbor_id} to active.")
                else:
                    # Armazena as informações do vizinho se ele não estiver presente
                    self.neighbors[neighbor_ip] = {
                        "node_id": neighbor_id,
                        "control_port": control_port,
                        "data_port": data_port,
                        "node_type": node_type,
                        "failed-attempts": 0,
                        "status": "active"  # Define o status como ativo
                    }
                    print(f"Added new neighbor: {neighbor_id}")
                print(f"Node {self.node_id} neighbors: {self.neighbors}")
        
    def send_ping_to_neighbors(self):
        while True:
            time.sleep(10)
            
            for neighbor_ip, neighbor_info in list(self.neighbors.items()):
                # Verificar se o vizinho já está marcado como inativo
                if neighbor_info.get("status") == "inactive":
                    continue  # Ignora o envio de PING para vizinhos já considerados inativos

                # Verifica o número de tentativas
                if neighbor_info.get("failed-attempts", 0) >= 2:
                    print(f"Neighbor {neighbor_info['node_id']} considered inactive due to lack of PONG response.")
                    with self.lock: 
                        neighbor_info["status"] = "inactive"
                    continue  # Ignora o envio de PING para vizinhos já considerados inativos

                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.connect((neighbor_ip, neighbor_info['control_port']))
                        ping_message = ControlMessage()
                        ping_message.type = ControlMessage.PING
                        ping_message.node_ip = self.node_ip
                        ping_message.node_id = self.node_id
                        s.send(ping_message.SerializeToString())
                        print(f"Sent PING to neighbor {neighbor_info['node_id']}")

                        # Espera pela resposta PONG
                        data = s.recv(1024)
                        if data:
                            response_message = ControlMessage()
                            response_message.ParseFromString(data)
                            if response_message.type == ControlMessage.PONG:
                                print(f"Received PONG from neighbor {response_message.node_id}")
                                # Resetamos as tentativas falhas em caso de resposta
                                with self.lock: 
                                    neighbor_info["failed-attempts"] = 0
                                    neighbor_info["status"] = "active"

                except Exception as e:
                    # Incrementa o contador de tentativas falhas
                    print(f"Failed to send PING to neighbor {neighbor_info['node_id']}: {e}")
                    with self.lock: 
                        neighbor_info["failed-attempts"] = neighbor_info.get("failed-attempts", 0) + 1
                    
    # Responder a uma mensagem de ping
    def handle_ping(self, control_message, conn):
        print(f"Received PING from neighbor {control_message.node_id}")
        pong_message = ControlMessage()
        pong_message.type = ControlMessage.PONG
        pong_message.node_id = self.node_id
        conn.send(pong_message.SerializeToString())
        print(f"Sent PONG to neighbor {control_message.node_id}")
        
        # Reinicia as tentativas falhas do nó que enviou o PING
        with self.lock:
            if control_message.node_ip in self.neighbors:
                self.neighbors[control_message.node_ip]["failed-attempts"] = 0
                self.neighbors[control_message.node_ip]["status"] = "active"
    
    ### Funcionalidades de comunicação de dados

    def data_server(self):
        """
        Implementa a lógica do servidor de dados.
        """
        if self.node_type == "pop":
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.bind(('', self.data_port))
                while True:
                    self.listen_for_client(s)

    def listen_for_client(self, s):
        """ Escuta mensagens dos clientes e responde com ACK """
        while True:
            try:
                message, client_address = s.recvfrom(1024)
                print(f"Message received from client {client_address}: {message.decode('utf-8')}")

                # Enviar ACK de volta para o cliente
                s.sendto(b'ACK', client_address)
                print(f"ACK sent to client {client_address}")

            except Exception as e:
                print(f"Error in receiving message: {e}")                

### Função principal para iniciar o nó

def main():
    """
    Função principal para executar o nó.
    Recebe o endereço do Bootstrapper e o ID do nó como parâmetros de linha de comando.
    """
    if len(sys.argv) != 5:
        print("Usage: python Node.py <bootstrapper_ip> <node_id> <node_ip> <type(node/pop)>")
        sys.exit(1)

    bootstrapper = sys.argv[1]
    node_id = sys.argv[2]
    node_ip = sys.argv[3]
    node_type = sys.argv[4]
    control_port = 50051  # Porta de controle padrão
    data_port = 50052     # Porta de dados padrão

    node = Node(node_id, node_ip, node_type, control_port, data_port, bootstrapper)
    node.start()

if __name__ == "__main__":
    main()
