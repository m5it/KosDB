#!/usr/bin/env python3
"""
LevelDB Socket Server - Main Entry Point
A threaded socket server providing MySQL-like interface over LevelDB
"""

import socket
import threading
import sys
import os

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import Database
from auth import Authenticator
from parser import CommandParser
from commands import CommandRegistry


class ClientHandler(threading.Thread):
    """Handle individual client connections"""
    
    def __init__(self, client_socket, address, db, authenticator):
        super().__init__(daemon=True)
        self.client_socket = client_socket
        self.address = address
        self.db = db
        self.authenticator = authenticator
        self.parser = CommandParser()
        self.commands = CommandRegistry(db)
        self.authenticated = False
        self.username = None
        self.client_state = {
            'current_db': None
        }
        self.running = True
    
    def send(self, message):
        """Send message to client"""
        self.client_socket.sendall(message.encode() + b'\n')
    
    def receive(self):
        """Receive message from client"""
        data = self.client_socket.recv(4096)
        if not data:
            return None
        return data.decode().strip()
    
    def run(self):
        """Main client handling loop"""
        print(f"[SERVER] Client connected from {self.address}")
        
        try:
            # Send welcome message
            self.send("=" * 50)
            self.send("LevelDB Socket Server")
            self.send("=" * 50)
            self.send("Authentication required")
            self.send("Format: USER <username>, then PASS <password>")
            self.send("-" * 50)
            
            while self.running:
                # Receive command
                data = self.receive()
                if data is None:
                    break
                
                print(f"[SERVER] {self.address} -> {data}")
                
                # Handle authentication
                if not self.authenticated:
                    response = self._handle_auth(data)
                    self.send(response)
                    if response.startswith("ERROR") or response == "BYE":
                        break
                    continue
                
                # Parse and execute command
                cmd_type, params = self.parser.parse(data)
                response = self.commands.execute(cmd_type, params, self.client_state)
                self.send(response)
                
                if response == "BYE":
                    break
        
        except Exception as e:
            print(f"[SERVER] Error handling client {self.address}: {e}")
        
        finally:
            self.client_socket.close()
            print(f"[SERVER] Client {self.address} disconnected")
    
    def _handle_auth(self, data):
        """Handle authentication flow"""
        parts = data.split(None, 1)
        
        if not parts:
            return "ERROR: Invalid input"
        
        command = parts[0].upper()
        
        if command == "USER":
            if len(parts) < 2:
                return "ERROR: Username required"
            self.username = parts[1].strip()
            return "OK: Username received. Send PASS <password>"
        
        elif command == "PASS":
            if len(parts) < 2:
                return "ERROR: Password required"
            if not self.username:
                return "ERROR: USER required first"
            
            password = parts[1].strip()
            if self.authenticator.authenticate(self.username, password):
                self.authenticated = True
                return f"OK: Welcome {self.username}. Authentication successful."
            else:
                return "ERROR: Authentication failed"
        
        elif command in ('QUIT', 'EXIT'):
            return "BYE"
        
        else:
            return "ERROR: Authentication required. Use USER <username>"


class SocketServer:
    """Threaded TCP Socket Server"""
    
    def __init__(self, host='0.0.0.0', port=9999, db_path='./data.db'):
        self.host = host
        self.port = port
        self.db = Database(db_path)
        self.authenticator = Authenticator()
        self.server_socket = None
        self.running = False
    
    def start(self):
        """Start the server"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.running = True
        
        print(f"[SERVER] Started on {self.host}:{self.port}")
        print(f"[SERVER] Database: {self.db.db_path}")
        print(f"[SERVER] Waiting for connections...")
        print(f"[SERVER] Press Ctrl+C to stop")
        
        try:
            while self.running:
                client_socket, address = self.server_socket.accept()
                handler = ClientHandler(
                    client_socket, address, self.db, self.authenticator
                )
                handler.start()
        
        except KeyboardInterrupt:
            print("\n[SERVER] Shutting down...")
        
        finally:
            self.stop()
    
    def stop(self):
        """Stop the server"""
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        self.db.close()
        print("[SERVER] Stopped")


def main():
    """Main entry point"""
    print("=" * 50)
    print("LevelDB Socket Server")
    print("=" * 50)
    print()
    print("Configuration:")
    print("  Host: 0.0.0.0")
    print("  Port: 9999")
    print("  Database: ./data.db")
    print("  Auth: admin / skrlat")
    print()
    print("-" * 50)
    print()
    
    server = SocketServer(host='0.0.0.0', port=9999, db_path='./data.db')
    server.start()


if __name__ == '__main__':
    main()