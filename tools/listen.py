"""UDP listener - run this before launching the game.

Prints any packet received on port 12345 and exits on Ctrl-C.
"""
import socket
import sys

PORT = 12345
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("127.0.0.1", PORT))
sock.settimeout(60)
print(f"Listening on 127.0.0.1:{PORT} - launch the game now ...")
try:
    while True:
        data, addr = sock.recvfrom(65535)
        print(f"RECEIVED from {addr}: {repr(data)}")
except socket.timeout:
    print("Timed out after 60s - no packet received.")
    sys.exit(1)
except KeyboardInterrupt:
    print("Stopped.")
finally:
    sock.close()
