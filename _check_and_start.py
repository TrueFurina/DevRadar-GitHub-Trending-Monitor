"""Check if DevRadar is running, then start it"""
import socket, sys

try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    s.connect(("127.0.0.1", 9876))
    s.sendall(b'{"type":"heartbeat"}\n')
    data = s.recv(1024)
    s.close()
    print("DevRadar is already running!")
    sys.exit(0)
except (socket.timeout, ConnectionRefusedError):
    print("DevRadar is not running. Starting now...")
    sys.exit(1)
