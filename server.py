
#!/usr/bin/env python3
"""
LevelDB Socket Server with Database-Driven Authentication, Replication, and TLS Encryption
KosDB - Multi-Command Batch Execution Support
"""

# Auto-version - increments automatically via git pre-commit hook
try:
    from AUTOVERSION import VERSION as __version__
except ImportError:
    __version__ = "2.3.0"

import sys
import os
import socket
import threading
import json
import logging
import hashlib
import ssl
import re
import time
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tls_wrapper import TLSConfig, TLSSocketWrapper, generate_self_signed_cert
from parser import BackupRestoreParser
from commands import CommandRegistry
from database import Database
from auth import Authenticator
import os
import socket
import threading
import json
import logging
import hashlib
import ssl
import re
import time
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tls_wrapper import TLSConfig, TLSSocketWrapper, generate_self_signed_cert
from parser import BackupRestoreParser
from commands import CommandRegistry
from database import Database
from auth import Authenticator


class ClientHandler(threading.Thread):
    def __init__(self, client_socket, address, db, authenticator, replication_client=None, tls_wrapper=None):
        super().__init__(daemon=True)
        self.client_socket = client_socket
        self.address = address
        self.db = db
        self.authenticator = authenticator
        self.parser = BackupRestoreParser()
        self.commands = CommandRegistry(db, replication_client)
        self.authenticated = False
        self.session_token = None
        self.user_info = None
        self.client_state = {'current_db': None, 'username': None, 'is_admin': False}
        self.running = True
        self.tls_wrapper = tls_wrapper
        self.tls_enabled = tls_wrapper is not None and tls_wrapper.config.enabled
    
    def get_connection_info(self):
        if not self.tls_enabled:
            return {'encrypted': False, 'protocol': 'plain'}
        return {'encrypted': True}
    
    def send(self, message):
        self.client_socket.sendall(message.encode() + b'\n')
    
    def receive(self):
        data = self.client_socket.recv(4096)
        return data.decode().strip() if data else None
    
    def run(self):
        print(f"[SERVER] Client {self.address} connected")
        
        try:
            # Send welcome
            self.send(f"KosDB v{__version__}")
            self.send("Commands: LOGIN <user> <pass> | HELP | QUIT")
            
            while self.running:
                data = self.receive()
                if not data:
                    break
                
                response = self.handle_command(data)
                self.send(response)
                
                if data.upper() == 'QUIT':
                    break
                    
        except Exception as e:
            print(f"[SERVER] Client error: {e}")
        finally:
            self.client_socket.close()
            print(f"[SERVER] Client {self.address} disconnected")
    
    def handle_command(self, command):
        cmd_upper = command.upper()
        
        # Handle login
        if cmd_upper.startswith('LOGIN '):
            parts = command.split()
            if len(parts) != 3:
                return "ERROR: Usage: LOGIN <username> <password>"
            username, password = parts[1], parts[2]
            success, token, user_info = self.authenticator.authenticate(username, password)
            if success:
                self.authenticated = True
                self.session_token = token
                self.client_state['username'] = username
                self.client_state['is_admin'] = user_info.get('is_admin', False)
                return f"OK: Welcome {username}"
            return "ERROR: Authentication failed"
        
        # Require authentication
        if not self.authenticated:
            return "ERROR: Please login first"
        
        # Parse and execute
        try:
            cmd_type, params = self.parser.parse(command)
            
            if cmd_type == 'QUIT':
                return "OK: Goodbye"
            
            if cmd_type == 'HELP':
                return self._get_help()
            
            if cmd_type == 'UNKNOWN':
                return "ERROR: Unknown command"
            
            # Execute command
            response = self.commands.execute(cmd_type, params, self.client_state)
            return response
            
        except Exception as e:
            return f"ERROR: {str(e)}"
    
    def _get_help(self):
        lines = [
            "Available Commands:",
            "  LOGIN <user> <pass>  - Authenticate",
            "  USE <database>       - Select database",
            "  SHOW DATABASES       - List databases",
            "  SHOW TABLES          - List tables",
            "  CREATE TABLE <name>  - Create table",
            "  INSERT INTO <table>    - Insert data",
            "  SELECT ...           - Query data",
            "  HELP                 - Show this help",
            "  QUIT                 - Disconnect"
        ]
        return "\n".join(lines)


class SocketServer:
    def __init__(self, host='0.0.0.0', port=5555, data_dir='./data', server_id=1, tls_config=None):
        self.host = host
        self.port = port
        self.data_dir = data_dir
        self.server_id = server_id
        self.tls_config = tls_config or TLSConfig()
        self.tls_wrapper = TLSSocketWrapper(self.tls_config) if self.tls_config.enabled else None
        
        # Initialize database
        self.db = Database(data_dir, server_id)
        self.authenticator = Authenticator(self.db)
        self.running = False
        self.socket = None
        
        # Initialize replication client if configured
        self.replication_client = None
        
        print("=" * 50)
        print("LevelDB Socket Server")
        print("=" * 50)
        print(f"Host: {host}")
        print(f"Port: {port}")
        print(f"TLS: {'Enabled' if self.tls_config.enabled else 'Disabled'}")
        print(f"Server ID: {server_id}")
        print(f"Data: {data_dir}")
        print("-" * 50)
    
    def start(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.host, self.port))
        self.socket.listen(5)
        self.running = True
        
        print(f"[SERVER] Listening on {self.host}:{self.port}")
        
        try:
            while self.running:
                client_socket, address = self.socket.accept()
                
                # Wrap with TLS if enabled
                if self.tls_wrapper and self.tls_wrapper.config.enabled:
                    try:
                        client_socket = self.tls_wrapper.wrap_client_socket(client_socket)
                    except Exception as e:
                        print(f"[SERVER] TLS handshake failed: {e}")
                        client_socket.close()
                        continue
                
                handler = ClientHandler(
                    client_socket, 
                    address, 
                    self.db, 
                    self.authenticator,
                    self.replication_client,
                    self.tls_wrapper
                )
                handler.start()
                
        except KeyboardInterrupt:
            print("\n[SERVER] Shutting down...")
        finally:
            self.stop()
    
    def stop(self):
        self.running = False
        if self.socket:
            self.socket.close()
        print("[SERVER] Stopped")


def main():
    parser = argparse.ArgumentParser(description='KosDB Socket Server')
    parser.add_argument('--host', default='0.0.0.0', help='Bind host')
    parser.add_argument('--port', type=int, default=5555, help='Bind port')
    parser.add_argument('--data-dir', default='./data', help='Data directory')

def main():
    parser = argparse.ArgumentParser(description='KosDB Socket Server')
    parser.add_argument('--host', default='0.0.0.0', help='Bind host')
    parser.add_argument('--port', type=int, default=5555, help='Bind port')
    parser.add_argument('--data-dir', default='./data', help='Data directory')
    parser.add_argument('--server-id', type=int, default=1, help='Server ID')
    parser.add_argument('--tls-cert', help='TLS certificate file')
    parser.add_argument('--tls-key', help='TLS key file')
    parser.add_argument('--prepare-admin', help='Create admin user')
    parser.add_argument('--prepare-password', help='Admin password')
    
    args = parser.parse_args()
    
    # Handle admin creation
    if args.prepare_admin:
        db = Database(args.data_dir)
        result = db.create_user(args.prepare_admin, args.prepare_password or 'admin', is_admin=True)
        if "already exists" in result:
            print(f"User '{args.prepare_admin}' already exists")
        else:
            print(f"User '{args.prepare_admin}' created")
        return
    
    # Setup TLS
    tls_config = TLSConfig()
    if args.tls_cert and args.tls_key:
        tls_config.enabled = True
        tls_config.cert_file = args.tls_cert
        tls_config.key_file = args.tls_key
    
    # Create and start server
    server = SocketServer(
        host=args.host,
        port=args.port,
        data_dir=args.data_dir,
        server_id=args.server_id,
        tls_config=tls_config
    )
    server.start()


if __name__ == '__main__':
    main()
if __name__ == '__main__':
    main()
