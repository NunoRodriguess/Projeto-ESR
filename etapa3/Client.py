from tkinter import *
import tkinter.messagebox
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os

from control_protocol_pb2 import ControlMessage
from control_protocol_pb2 import FloodingMessage
import time
from VideoSession import VideoSession


class Client:
    INIT = 0
    READY = 1
    PLAYING = 2
    state = INIT

    SETUP = 0
    PLAY = 1
    PAUSE = 2
    TEARDOWN = 3
    
    # Initiation..
    def __init__(self, master, rtp_port, filename, client_id, client_ip, bootstrapper_host='localhost', bootstrapper_port=5000):
        self.master = master
        self.rtp_port = int(rtp_port)
        self.filename = filename

        # Client details
        self.client_id = client_id
        self.client_ip = client_ip
  
        #Neighbor details
        self.dest_lock = threading.Lock()
        self.destination_ip = None
        self.destination_rtsp_port = None
        
        # Bootstrapper configuration
        self.bootstrapper = (bootstrapper_host, bootstrapper_port)
        
        # Networking and synchronization
        self.neighbors = {}
        self.neighbors_lock = threading.Lock()
        
        self.control_port = 5001
        self.data_port = 5002

        self.node_type = "client"

        self.video_session = None

        # Connect to server and perform background work
        self.background()  # Register with the bootstrapper and start background tasks
        
    def send_control_message_tcp(self, socket, control_message):
        header = b'\x01'
        socket.sendall(header + control_message.SerializeToString())

    def send_flooding_message_tcp(self, socket, flooding_message):
        header = b'\x02' 
        socket.sendall(header + flooding_message.SerializeToString())
    
    def send_control_message_udp(self, socket, address, control_message):
        header = b'\x01'  # Header para ControlMessage
        socket.sendto(header + control_message.SerializeToString(), address)

    def send_flooding_message_udp(self, socket, address, flooding_message):
        header = b'\x02'  # Header para FloodingMessage
        socket.sendto(header + flooding_message.SerializeToString(), address)
        
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
            control_message.node_id = self.client_id
            control_message.node_ip = self.client_ip
            control_message.control_port = self.control_port
            control_message.data_port = self.data_port
            control_message.node_type = self.node_type
            
            # Envia a mensagem de registro
            self.send_control_message_tcp(s, control_message)
            
            # Recebe e processa a resposta
            header = s.recv(1)  # Lê o primeiro byte
            data = s.recv(1024)  # Lê o restante da mensagem
            
            if header == b'\x01':  # ControlMessage
                response_message = ControlMessage()
                response_message.ParseFromString(data)
                
                if response_message.type == ControlMessage.REGISTER_RESPONSE:
                    print(f"Client {self.client_id} registered")
                    self.neighbors.clear()  # Limpa vizinhos antigos em caso de reativação
                    for neighbor in response_message.neighbors:
                        with self.neighbors_lock: 
                            self.neighbors[neighbor.node_ip] = {
                                "node_ip": neighbor.node_ip,
                                "node_id": neighbor.node_id,
                                "control_port": neighbor.control_port,
                                "data_port": neighbor.data_port,
                                "node_type": neighbor.node_type,
                                "rtsp_port": neighbor.rtsp_port,
                                "status": "active",
                                "stream": "inactive",
                                "failed-attempts": 0
                            }
                    print(f"Client {self.client_id} Pop's: {self.neighbors}")
                    # Após o registro, notifica os vizinhos sobre o registro
                    self.notify_neighbors_registration()
                else:
                    print(f"Unexpected response type: {response_message.type}")

    def notify_neighbors_registration(self):
        """
        Notifica os vizinhos que o nó está registrado e que pode haver atualizações.
        Utiliza UDP para enviar as mensagens.
        """
        with self.neighbors_lock:
            neighbors_snapshot =  self.neighbors.copy()
            
        for neighbor_ip, neighbor_info in neighbors_snapshot.items():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    notify_message = ControlMessage()
                    notify_message.type = ControlMessage.UPDATE_NEIGHBORS
                    notify_message.node_id = self.client_id
                    notify_message.node_ip = self.client_ip
                    notify_message.control_port = self.control_port
                    notify_message.data_port = self.data_port
                    notify_message.node_type = self.node_type

                    #Envia para o vizinho
                    neighbor_address = (neighbor_ip, neighbor_info['data_port'])
                    self.send_control_message_udp(s, neighbor_address, notify_message)
                    print(f"Notified neighbor {neighbor_info['node_id']} of registration.")

            except Exception as e:
                print(f"Failed to notify neighbor {neighbor_info['node_id']} via UDP: {e}")
                
    def background(self):
        """
        Função principal do cliente que inicia a solicitação de vizinhos.
        """
        self.register_with_bootstrapper()
        threading.Thread(target=self.data_server).start()     # Inicia o servidor de dados em uma thread separada
        threading.Thread(target=self.send_ack_to_neighbors).start()  # Enviar PING aos vizinhos
        threading.Thread(target=self.start_new_session).start()  # Thread da sessão de vídeo           

    def start_new_session(self):
        while True:
            best_route = self.activate_best_route(self.filename)
            if best_route:
                new_ip = best_route["node_ip"]
                new_rtsp_port = best_route["rtsp_port"]

                # Atualiza as informações de destino dentro de um bloco protegido
                with self.dest_lock:
                    dest_ip = self.destination_ip
                    dest_rtspport = self.destination_rtsp_port

                    # Verifica se a nova rota é a mesma que a atual
                    if dest_ip == new_ip and dest_rtspport == new_rtsp_port:
                        print("A rota não mudou. Sessão existente mantida.")
                    else:
                        # Atualiza as informações de destino
                        self.destination_ip = new_ip
                        self.destination_rtsp_port = new_rtsp_port

                        dest_ip = new_ip
                        dest_rtspport = new_rtsp_port

                        # Atualiza ou cria a sessão de vídeo
                        if hasattr(self, 'session_window') and self.session_window.winfo_exists():
                            print(f"Rota atualizada para o nó {best_route['node_id']}.")
                            if self.video_session:
                                self.video_session.update_route(dest_ip, dest_rtspport)
                                self.video_session.connectToNeighbor()
                        else:
                            # Cria uma nova janela para a sessão
                            print("Iniciando nova sessão de vídeo...")
                            self.session_window = Toplevel(self.master)
                            self.sessions_frame = Frame(self.master)
                            self.sessions_frame.pack()

                            # Inicia a sessão de vídeo
                            self.video_session = VideoSession(
                                self.session_window,
                                self.client_ip,
                                dest_ip,
                                dest_rtspport,
                                self.rtp_port,
                                self.filename
                            )

                            # Adiciona botão para fechar a sessão
                            self.close_button = Button(
                                self.sessions_frame, 
                                text=f'Fechar Sessão {best_route["node_id"]}', 
                                command=lambda: self.close_session(self.video_session)
                            )
                            self.close_button.pack()
            else:
                print("Nenhuma rota disponível. Tentando novamente em 10 segundos.")

            time.sleep(10)  # Aguarda antes de verificar novamente
        
    def activate_best_route(self, filename):
        """
        Analisa os ACKs recebidos com tempos acumulados, ativa a melhor rota,
        e desativa qualquer rota previamente ativa se um melhor tempo for encontrado.
        """
        best_route = None
        min_time = float('inf')  # Inicia com o maior valor possível
        destination = None

        # Procura a melhor rota na tabela de roteamento com base no menor tempo
        with self.neighbors_lock:
            neighbors_snapshot =  self.neighbors.copy()
            
        for neighbor_ip, neighbor_info in neighbors_snapshot.items():
            # Ignorar vizinhos sem informações de tempo ou não ativos
            if "best_time" not in neighbor_info or neighbor_info["status"] != "active":
                continue

            # Verificar o menor tempo acumulado
            if neighbor_info["best_time"] < min_time:
                min_time = neighbor_info["best_time"]
                best_route = neighbor_info
                destination = neighbor_ip

        if best_route is not None:
            self.deactivate_bad_routes(destination, filename)

            with self.neighbors_lock:
                if self.neighbors[destination]['stream'] != "active":
                    self.neighbors[destination]['stream'] = "active"   
                       
            print(f"Best route is {best_route['node_id']} at {destination} with {min_time} time.")
            activate_message = FloodingMessage()
            activate_message.type = FloodingMessage.ACTIVATE_ROUTE
            activate_message.stream_ids.append(filename)
            activate_message.source_ip = self.client_ip
            activate_message.rtp_port = self.rtp_port
            
            # Enviar mensagem de ativação para a melhor rota
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    address = (destination, best_route['data_port'])
                    self.send_flooding_message_udp(s, address, activate_message)
                    print(f"Sent route activation to {best_route['node_id']} at {destination}:{best_route['data_port']}.")
                    return self.neighbors[destination].copy()
                
            except Exception as e:
                print(f"Failed to activate route to destination {best_route['node_id']}: {e}")
                return None
        
        else:
            print("No active route available to activate.")
            return None

    def deactivate_bad_routes(self, destination, filename):
        # Desativa todas as rotas exceto a rota do destination
        """
        Desativa todas as rotas associadas a um fluxo específico identificado por filename.
        """        
        with self.neighbors_lock:
            neighbors_snapshot =  self.neighbors.copy()      
            
        # Verificar se o fluxo está presente na tabela de roteamento
        for route_ip, route_info in neighbors_snapshot.items():
            if route_info["stream"] == "active" and route_ip != destination: 
                with self.neighbors_lock:
                    self.neighbors[route_ip]["stream"] = "inactive"
                
                print(f"Deactivated route to {route_ip} for {filename}.")
                
                deactivate_message = FloodingMessage()
                deactivate_message.type = FloodingMessage.DEACTIVATE_ROUTE
                deactivate_message.stream_ids.append(filename)
                deactivate_message.source_ip = self.client_ip
            
                # Enviar mensagem de desativação
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                        address = (route_ip, route_info['data_port'])
                        self.send_flooding_message_udp(s, address, deactivate_message)
                        print(f"Sent route deactivation to {route_info['node_id']} at {destination}:{route_info['data_port']}.")
                except Exception as e:
                    print(f"Failed to deactivate route to destination {route_info['node_id']}: {e}") 

    def close_session(self, video_session):
        """
        Fecha a sessão de vídeo atual e remove a janela e o botão associados.
        """
        if not video_session.active:  # Verifica se a sessão já está inativa
            # Fecha a janela da sessão de vídeo, se existir
            if self.session_window:
                self.session_window.destroy()
                self.session_window = None  # Limpa a referência

            # Remove o botão de fechar sessão, se existir
            if self.close_button:
                self.close_button.destroy()
                self.close_button = None  # Limpa a referência
            print("Sessão de vídeo fechada.")
   
    def data_server(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.bind(('', self.data_port))
            print(f"Client {self.client_id} listening on data port {self.data_port}")
            while True:
                try:
                    # Recebe dados e o endereço de origem
                    data, addr = s.recvfrom(1024)
                    threading.Thread(target=self.handle_data_message, args=(data, addr, s)).start()
                except Exception as e:
                    print(f"Error receiving data: {e}")
    
    def handle_data_message(self, data, addr, socket):
        """
        Lida com mensagens recebidas via UDP.
        Processa mensagens de controle (PING, UPDATE_NEIGHBORS) e mensagens de flooding.

        :data: Dados recebidos.
        :addr: Endereço do nó que enviou os dados.
        :socket: Socket para enviar respostas.
        """
        print(f"Message received from {addr}")

        # Tenta interpretar a mensagem como ControlMessage
        if len(data) < 1:
            print("Invalid message: no header")
            return

        header = data[0:1]  # Primeiro byte é o header
        message_body = data[1:]  # Restante é a mensagem serializada

        try:
            if header == b'\x01':  # ControlMessage
                control_message = ControlMessage()
                control_message.ParseFromString(message_body)    
                if control_message.type == ControlMessage.UPDATE_NEIGHBORS:
                    self.handle_update_neighbors(control_message)
                    
                elif control_message.type == ControlMessage.ACK:
                    received_time = time.time()
                    self.handle_ack(control_message, socket, received_time)
                
                else:
                        print(f"Unknown ControlMessage type: {control_message.type}")

        except Exception as e:
            print(f"Failed to parse as ControlMessage: {e}")
         
    def handle_update_neighbors(self, control_message):
        print(f"Updating neighbors with {control_message.node_id}")
        neighbor_id = control_message.node_id
        neighbor_ip = control_message.node_ip
        control_port = control_message.control_port
        data_port = control_message.data_port
        node_type = control_message.node_type
        rtsp_port = control_message.rtsp_port
        
        with self.neighbors_lock:
            neighbors_snapshot = self.neighbors.copy()
             
        # Se o vizinho já estiver na lista, atualiza o status
        if neighbor_ip in neighbors_snapshot:
            with self.neighbors_lock:
                self.neighbors[neighbor_ip]["status"] = "active"
            print(f"Updated status of existing neighbor {neighbor_id} to active.")
        else:
            with self.neighbors_lock:
                # Armazena as informações do vizinho se ele não estiver presente
                self.neighbors[neighbor_ip] = {
                    "node_ip": neighbor_ip,
                    "node_id": neighbor_id,
                    "control_port": control_port,
                    "data_port": data_port,
                    "node_type": node_type,
                    "rtsp_port": rtsp_port,
                    "status": "active",  # Define o status como ativo
                    "stream": "inactive",
                    "failed-attempts": 0
                }
            print(f"Added new neighbor: {neighbor_id}") 
                     
        print(f"Client {self.client_id} neighbors: {self.neighbors}")
                    
    def send_ack_to_neighbors(self):
        while True:
            time.sleep(15)

            with self.neighbors_lock:
                neighbors_snapshot =  self.neighbors.copy()
                
            for neighbor_ip, neighbor_info in neighbors_snapshot.items():
                # Verificar se o vizinho já está marcado como inativo
                if neighbor_info["status"] == "inactive":
                    continue  

                # Verifica o número de tentativas
                if neighbor_info.get("failed-attempts", 0) >= 2:
                    print(f"Neighbor {neighbor_info['node_id']} considered inactive due to lack of ACK response.")
                    with self.neighbors_lock: 
                        self.neighbors[neighbor_ip]["status"] = "inactive"
                    continue  
                
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                        address = (neighbor_ip, neighbor_info['data_port'])
                        ack_message = ControlMessage()
                        ack_message.type = ControlMessage.ACK
                        ack_message.node_ip = self.client_ip
                        ack_message.node_id = self.client_id
                        ack_message.data_port = self.data_port  
                    
                        self.send_control_message_udp(s, address, ack_message)
                        print(f"Sent ACK to Pop {neighbor_info['node_id']}")
                        
                except Exception as e:
                    # Incrementa o contador de tentativas falhas
                    print(f"Failed to send ACK to neighbor {neighbor_info['node_id']}: {e}")
                    with self.neighbors_lock: 
                        self.neighbors[neighbor_ip]["failed-attempts"] = neighbor_info.get("failed-attempts", 0) + 1                 

    def handle_ack(self, response_message, s, received_time):
        """ Recebe os acks de volta dos PoP's """
        try: 
            print(f"Received ACK from Pop {response_message.node_id}")
            print(f"Updated best_time for {response_message.node_id}: {response_message.accumulated_time:.4f}s")

            # Resetamos as tentativas falhas em caso de resposta
            with self.neighbors_lock: 
                self.neighbors[response_message.node_ip]["best_time"] = response_message.accumulated_time
                self.neighbors[response_message.node_ip]["failed-attempts"] = 0
                self.neighbors[response_message.node_ip]["status"] = "active"

        except Exception as e:
            print(f"Error in receiving message: {e}") 
                
def main():
    
    if len(sys.argv) != 5:
        print("Usage: python Client.py <bootstrapper_ip> <client_id> <client_ip> <movie>")
        sys.exit(1)

    bootstrapper = sys.argv[1] # 10.0.1.10
    client_id = sys.argv[2]  # Client-1
    client_ip = sys.argv[3] # 10.0.0.20
    filename = sys.argv[4] 

    root = Tk()
    client = Client(root, 25000, filename, client_id, client_ip, bootstrapper)
    root.mainloop()
    
if __name__ == "__main__":
    main()
    