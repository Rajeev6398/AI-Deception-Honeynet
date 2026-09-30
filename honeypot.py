import socket
import paramiko
import threading
import docker
import json
import time
import traceback
import requests
import os

# -------------------------------------------------------------
# ⚙️ TELEGRAM CONFIGURATION
# -------------------------------------------------------------
TELEGRAM_BOT_TOKEN = "8907153904:AAGqZpd6WZ8bGlfaiaHNnjluv00FFZvtBsc"
TELEGRAM_CHAT_ID = "6554887188"

def send_telegram_alert(ip, username, password, timestamp):
    """Sends immediate attack alert to Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    message = (
        f"🚨 *HONEYPOT ATTACK DETECTED!*\n\n"
        f"🌐 *Attacker IP:* `{ip}`\n"
        f"👤 *Username:* `{username}`\n"
        f"🔑 *Password:* `{password}`\n"
        f"⏰ *Time:* `{timestamp}`\n\n"
        f"🐳 *Status:* Dynamic Container Sandbox Spawned!"
    )
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, data=payload, timeout=5)
    except Exception as e:
        print(f"[-] Telegram Alert Error: {e}")

# -------------------------------------------------------------
# 🔑 STATIC RSA HOST KEY MANAGEMENT (Fixes Remote Host Identification Changed Error)
# -------------------------------------------------------------
KEY_FILE = "server.key"
if not os.path.exists(KEY_FILE):
    # Auto-generate server.key if it doesn't exist
    key = paramiko.RSAKey.generate(2048)
    key.write_private_key_file(KEY_FILE)

HOST_KEY = paramiko.RSAKey(filename=KEY_FILE)

# Initialize Docker Client
try:
    docker_client = docker.from_env()
except Exception as e:
    print(f"[!] Docker Client Init Error: {e}")
    docker_client = None

class DockerSSHServer(paramiko.ServerInterface):
    def __init__(self, client_ip):
        self.event = threading.Event()
        self.client_ip = client_ip

    def check_channel_request(self, kind, chanid):
        if kind == 'session':
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_auth_password(self, username, password):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[🚨 ATTACK DETECTED] User: {username} | Pass: {password}")
        
        # Save Log to File
        log_data = {
            "timestamp": timestamp,
            "event": "login_attempt",
            "ip": self.client_ip,
            "username": username,
            "password": password
        }
        with open("attack_logs.json", "a") as f:
            f.write(json.dumps(log_data) + "\n")

        # Trigger Telegram Alert in Background Thread
        threading.Thread(
            target=send_telegram_alert, 
            args=(self.client_ip, username, password, timestamp)
        ).start()

        return paramiko.AUTH_SUCCESSFUL

    def get_allowed_auths(self, username):
        return "password"

    def check_channel_pty_request(self, channel, term, modes, width, height, pixelwidth, pixelheight):
        return True

    def check_channel_shell_request(self, channel):
        self.event.set()
        return True

def handle_client(client_socket, addr):
    print(f"[+] Connection from {addr[0]}:{addr[1]}")
    transport = paramiko.Transport(client_socket)
    transport.add_server_key(HOST_KEY)
    server = DockerSSHServer(client_ip=addr[0])

    container = None
    try:
        transport.start_server(server=server)
        chan = transport.accept(20)
        if not chan:
            print("[-] Transport accept timeout / failed.")
            return

        server.event.wait(10)
        if not server.event.is_set():
            print("[-] Client did not ask for a shell.")
            return

        print(f"[🐳 DOCKER] Launching isolated sandbox container for {addr[0]}...")
        
        # 1. Spawn isolated Ubuntu container
        container = docker_client.containers.run(
            "ubuntu:latest",
            command="/bin/bash",
            detach=True,
            tty=True,
            stdin_open=True,
            mem_limit="256m"
        )

        # 2. Attach container socket
        socket_stream = container.attach_socket(params={'stdin': 1, 'stdout': 1, 'stderr': 1, 'stream': 1})
        raw_socket = socket_stream._sock

        # Bridge thread: Attacker -> Docker Container
        def forward_to_container():
            while True:
                try:
                    data = chan.recv(1024)
                    if not data:
                        break
                    raw_socket.sendall(data)
                except Exception:
                    break

        # Bridge thread: Docker Container -> Attacker
        def forward_to_attacker():
            while True:
                try:
                    data = raw_socket.recv(1024)
                    if not data:
                        break
                    chan.send(data)
                except Exception:
                    break

        t1 = threading.Thread(target=forward_to_container)
        t2 = threading.Thread(target=forward_to_attacker)
        t1.daemon = True
        t2.daemon = True
        t1.start()
        t2.start()

        # Keep connection alive until threads end or channel closes
        while chan.active and t1.is_alive() and t2.is_alive():
            time.sleep(0.5)

    except Exception as e:
        print(f"[-] EXACT ERROR: {e}")
        traceback.print_exc()
    finally:
        if container:
            print(f"[🧹 CLEANUP] Destroying sandbox container {container.short_id}...")
            try:
                container.stop()
                container.remove(force=True)
            except Exception as ce:
                print(f"[-] Container cleanup error: {ce}")
        transport.close()

def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('0.0.0.0', 2222))
    server_socket.listen(100)
    print("[🚀 DOCKER-HONEYPOT ACTIVE] Listening on port 2222...")

    while True:
        client_socket, addr = server_socket.accept()
        t = threading.Thread(target=handle_client, args=(client_socket, addr))
        t.start()

if __name__ == "__main__":
    main()
