import socket
import threading
import sys
import time
import control_protocol_pb2 as ONode_pb2

class ONode:
    def __init__(self, node_id, control_port, data_port):
        self.node_id = node_id
        self.control_port = control_port
        self.data_port = data_port
        self.neighbors = {}
        self.bootstrapper = None
        self.lock = threading.Lock()

    def handle_control_connection(self, conn, addr):
        data = conn.recv(1024)
        if data:
            message = ONode_pb2.ControlMessage()
            message.ParseFromString(data)
            if message.type == ONode_pb2.ControlMessage.PING:
                self.handle_ping(conn)
            elif message.type == ONode_pb2.ControlMessage.UPDATE_NEIGHBORS:
                self.handle_update_neighbors(message)
        conn.close()

    def handle_ping(self, conn):
        response = ONode_pb2.ControlMessage()
        response.type = ONode_pb2.ControlMessage.PONG
        response.node_id = self.node_id
        conn.sendall(response.SerializeToString())

    def handle_update_neighbors(self, message):
        with self.lock:
            self.neighbors.clear()
            for neighbor in message.neighbors:
                self.neighbors[neighbor.node_id] = {
                    'ip': neighbor.ip,
                    'control_port': neighbor.control_port,
                    'data_port': neighbor.data_port
                }
        print(f"Updated neighbors: {self.neighbors}")

    def control_server(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', self.control_port))
            s.listen()
            print(f"Node {self.node_id} listening on control port {self.control_port}")
            while True:
                conn, addr = s.accept()
                threading.Thread(target=self.handle_control_connection, args=(conn, addr)).start()

    def data_server(self):
        # Placeholder for data server logic (QUIC or RTP)
        pass

    def register_with_bootstrapper(self, bootstrapper):
        self.bootstrapper = bootstrapper
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((bootstrapper, self.control_port))
            message = ONode_pb2.ControlMessage()
            message.type = ONode_pb2.ControlMessage.REGISTER
            message.node_id = self.node_id
            message.control_port = self.control_port
            message.data_port = self.data_port
            s.sendall(message.SerializeToString())
            data = s.recv(1024)
            if data:
                response = ONode_pb2.ControlMessage()
                response.ParseFromString(data)
                if response.type == ONode_pb2.ControlMessage.REGISTER_RESPONSE:
                    self.handle_update_neighbors(response)

    def send_ping(self):
        while True:
            time.sleep(300)  # Send ping every 5 minutes
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.connect((self.bootstrapper, self.control_port))
                    message = ONode_pb2.ControlMessage()
                    message.type = ONode_pb2.ControlMessage.PING
                    message.node_id = self.node_id
                    s.sendall(message.SerializeToString())
                    # Wait for PONG response
                    s.recv(1024)
                except Exception as e:
                    print(f"Failed to send ping: {e}")

    def start(self, bootstrapper):
        self.register_with_bootstrapper(bootstrapper)
        threading.Thread(target=self.control_server).start()
        threading.Thread(target=self.data_server).start()
        threading.Thread(target=self.send_ping).start()

def main():
    if len(sys.argv) != 2:
        print("Usage: python ONode.py <bootstrapper_ip>")
        sys.exit(1)

    bootstrapper = sys.argv[1]
    node_id = f"Node-{int(time.time())}"
    control_port = 50051
    data_port = 50052

    node = ONode(node_id, control_port, data_port)
    node.start(bootstrapper)

if __name__ == "__main__":
    main()