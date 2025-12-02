import socket
import threading

class SocketClient:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
        self.sock = None
        self.lock = threading.Lock()
        self.connected = False

    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.ip, self.port))
            self.connected = True
            print("[SOCKET] Connected")
        except Exception as e:
            print("[SOCKET] Connection failed:", e)
            self.connected = False

    def send_command(self, cmd):
        if not self.connected:
            return

        try:
            with self.lock:
                self.sock.sendall((cmd + "\n").encode("utf-8"))
        except Exception as e:
            print("[SOCKET] Send error:", e)
            self.connected = False

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.connected = False
