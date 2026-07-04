#!/usr/bin/env python3
"""
LevelDB Socket Server with Database-Driven Authentication
"""

import socket
import threading
import sys
import os
import argparse
import getpass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import Database
from auth import Authenticator
from parser import CommandParser
from commands import CommandRegistry


def setup_admin(db: Database, username: str, password: str):
    """Initialize admin user."""
    db._ensure_system_tables()
    result = db.create_user(username, password, is_admin=True)
    print(result)
    result = db.grant_privilege(username, "*", "*", ["ALL"])
    print(result)
    print(f"Admin user '{username}' created.")


class ClientHandler(threading.Thread):
    def __init__(self, client_socket, address, db, authenticator):
        super().__init__(daemon=True)
        self.client_socket = client_socket
        self.address = address
        self.db = db
        self.authenticator = authenticator
        self.parser = CommandParser()
        self.commands = CommandRegistry(db)
        self.authenticated = False
        self.session_token = None
        self.user_info = None
        self.client_state = {'current_db': None, 'username': None, 'is_admin': False}
        self.running = True
    
    def send(self, message):
        self.client_socket.sendall(message.encode() + b'\n')
    
    def receive(self):
        data = self.client_socket.recv(4096)
        return data.decode().strip() if data else None
    
    def run(self):
        print(f"[SERVER] Client {self.address} connected")
        
        try:
            self.send("=" * 50)
            self.send("LevelDB Socket Server")
            self.send("=" * 50)
            self.send("Authentication required")
            self.send("USER <username> then PASS <password>")
            self.send("-" * 50)
            
            while self.running:
                data = self.receive()
                if data is None:
                    break
                
                print(f"[SERVER] {self.address} -> {data}")
                
                if not self.authenticated:
                    response = self._handle_auth(data)
                    self.send(response)
                    if response.startswith("ERROR") or response == "BYE":
                        break
                    continue
                
                cmd_type, params = self.parser.parse(data)
                
                # Check privileges
                if not self._check_privileges(cmd_type, params):
                    self.send("ERROR: Permission denied")
                    continue
                
                response = self.commands.execute(cmd_type, params, self.client_state)
                self.send(response)
                
                if response == "BYE":
                    break
        
        except Exception as e:
            print(f"[SERVER] Error: {e}")
        finally:
            if self.session_token:
                self.authenticator.end_session(self.session_token)
            self.client_socket.close()
            print(f"[SERVER] Client {self.address} disconnected")
    
    def _handle_auth(self, data):
        parts = data.split(None, 1)
        if not parts:
            return "ERROR: Invalid input"
        
        cmd = parts[0].upper()
        
        if cmd == "USER":
            if len(parts) < 2:
                return "ERROR: Username required"
            self.pending_username = parts[1].strip()
            return "OK: Send PASS <password>"
        
        elif cmd == "PASS":
            if len(parts) < 2:
                return "ERROR: Password required"
            if not hasattr(self, 'pending_username'):
                return "ERROR: USER first"
            
            password = parts[1].strip()
            success, token, user_info = self.authenticator.authenticate(
                self.pending_username, password
            )
            
            if success:
                self.authenticated = True
                self.session_token = token
                self.user_info = user_info
                self.client_state['username'] = user_info['username']
                self.client_state['is_admin'] = user_info['is_admin']
                msg = f"OK: Welcome {user_info['username']}"
                if user_info['is_admin']:
                    msg += " (admin)"
                return msg + "."
            else:
                return "ERROR: Auth failed"
        
        elif cmd in ('QUIT', 'EXIT'):
            return "BYE"
        
        return "ERROR: Auth required"
    
    def _check_privileges(self, cmd_type, params):
        """Check if user has permission for command."""
        if not self.session_token:
            return False
        
        if self.user_info.get('is_admin'):
            return True
        
        # Check specific privileges
        db_name = self.client_state.get('current_db', '')
        table_name = params.get('table', '*')
        
        priv_map = {
            'CREATE_DB': 'CREATE', 'DROP_DB': 'DROP',
            'CREATE': 'CREATE', 'DROP': 'DROP',
            'INSERT': 'INSERT', 'SELECT': 'SELECT',
            'UPDATE': 'UPDATE', 'DELETE': 'DELETE'
        }
        
        if cmd_type in priv_map:
            return self.authenticator.check_privilege(
                self.session_token, db_name, table_name, priv_map[cmd_type]
            )
        
        return True


class SocketServer:
    def __init__(self, host='0.0.0.0', port=9999, data_dir='./data'):
        self.host = host
        self.port = port
        self.db = Database(data_dir)
        self.authenticator = Authenticator(self.db)
        self.server_socket = None
        self.running = False
    
    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.running = True
        
        print(f"[SERVER] Started on {self.host}:{self.port}")
        print(f"[SERVER] Data: {self.db.data_dir}")
        print("Press Ctrl+C to stop")
        
        try:
            while self.running:
                client_socket, address = self.server_socket.accept()
                handler = ClientHandler(client_socket, address, self.db, self.authenticator)
                handler.start()
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.stop()
    
    def stop(self):
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        self.db.close()
        print("[SERVER] Stopped")


def main():
    parser = argparse.ArgumentParser(description='LevelDB Socket Server')
    parser.add_argument('--prepare_admin', metavar='USER', help='Create admin user')
    parser.add_argument('--prepare_password', metavar='PASS', help='Admin password')
    parser.add_argument('--host', default='0.0.0.0', help='Host (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=9999, help='Port (default: 9999)')
    parser.add_argument('--data_dir', default='./data', help='Data dir (default: ./data)')
    
    args = parser.parse_args()
    
    if args.prepare_admin:
        password = args.prepare_password
        if not password:
            password = getpass.getpass(f"Password for '{args.prepare_admin}': ")
            confirm = getpass.getpass("Confirm: ")
            if password != confirm:
                print("ERROR: Passwords don't match!")
                sys.exit(1)
        
        db = Database(args.data_dir)
        setup_admin(db, args.prepare_admin, password)
        db.close()
        sys.exit(0)
    
    print("=" * 50)
    print("LevelDB Socket Server")
    print("=" * 50)
    print(f"Host: {args.host}")
    print(f"Port: {args.port}")
    print(f"Data: {args.data_dir}")
    print("\nSetup admin:")
    print(f"  python server.py --prepare_admin admin --prepare_password <pass>")
    print("-" * 50)
    
    server = SocketServer(args.host, args.port, args.data_dir)
    server.start()


if __name__ == '__main__':
    main()