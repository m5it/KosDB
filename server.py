
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
        self.db = db  # Reference to shared Database instance
        self.authenticator = authenticator
        self.parser = BackupRestoreParser()
        self.commands = CommandRegistry(db, replication_client)
        self.authenticated = False
        self.session_token = None
        self.user_info = None
        # Connection-level state - each handler has its own database context
        self.client_state = {
            'current_db': None,      # Per-connection current database
            'username': None, 
            'is_admin': False,
            'connection_db': None     # Per-connection database handle
        }
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
        # Increased from 4096 to 65536 for better handling of large result sets
        # Reduces round-trips for large responses and prevents fragmentation
        data = self.client_socket.recv(65536)
        return data.decode().strip() if data else None
    
    def receive_pipeline(self):
        """
        Receive multiple commands in pipeline mode.
        
        Returns:
            List of commands or None if connection closed
        """
        data = self.client_socket.recv(65536)
        if not data:
            return None
        
        # Split by delimiter for multiple commands
        # Commands can be separated by ;; or newlines
        commands_text = data.decode().strip()
        if ';;' in commands_text:
            commands = [cmd.strip() for cmd in commands_text.split(';;') if cmd.strip()]
            return commands
        return [commands_text] if commands_text else None
    
    def run(self):
        print(f"[SERVER] Client {self.address} connected")
        
        try:
            # Send welcome
            self.send(f"KosDB v{__version__}")
            self.send("Commands: LOGIN <user> <pass> | HELP | QUIT | PIPELINE")
            
            while self.running:
                # Check for pipeline mode commands
                data = self.receive()
                if not data:
                    break
                
                # Check if this is a pipeline request
                if data.upper().startswith('PIPELINE'):
                    # Parse pipeline commands
                    if ';;' in data:
                        # Inline pipeline: PIPELINE command1;;command2;;...
                        pipeline_part = data[data.find(' ')+1:] if ' ' in data else ''
                        commands = [cmd.strip() for cmd in pipeline_part.split(';;') if cmd.strip()]
                    else:
                        # Multi-line pipeline follows
                        commands = self.receive_pipeline()
                        if not commands:
                            self.send("ERROR: Empty pipeline")
                            continue
                    
                    # Execute pipeline
                    if commands:
                        responses = self.handle_pipeline(commands)
                        # Send aggregated response
                        response_text = "\n".join([f"[{i+1}] {r}" for i, r in enumerate(responses)])
                        self.send(f"PIPELINE RESULTS ({len(responses)} commands):\n{response_text}")
                    else:
                        self.send("ERROR: No commands in pipeline")
                    continue
                
                # Regular single command
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
        
        # Handle USE command with connection-level state
        if cmd_upper.startswith('USE '):
            db_name = command.split()[1] if len(command.split()) > 1 else None
            if not db_name:
                return "ERROR: Usage: USE <database>"
            
            # Check if database exists
            if db_name not in self.db.list_databases():
                return f"ERROR: Database '{db_name}' does not exist"
            
            # Set connection-level database state
            self.client_state['current_db'] = db_name
            
            # Open per-connection database handle if not already open
            if self.client_state['connection_db'] is None:
                import plyvel
                db_path = os.path.join(self.db.data_dir, db_name)
                try:
                    self.client_state['connection_db'] = plyvel.DB(db_path, create_if_missing=False)
                except Exception as e:
                    return f"ERROR: Failed to open database: {e}"
            else:
                # Close current and open new
                self.client_state['connection_db'].close()
                import plyvel
                db_path = os.path.join(self.db.data_dir, db_name)
                try:
                    self.client_state['connection_db'] = plyvel.DB(db_path, create_if_missing=False)
                except Exception as e:
                    return f"ERROR: Failed to open database: {e}"
            
            return f"Switched to database '{db_name}'"
        
        # Parse and execute other commands
        try:
            cmd_type, params = self.parser.parse(command)
            
            if cmd_type == 'QUIT':
                # Clean up connection-level database handle
                if self.client_state.get('connection_db'):
                    self.client_state['connection_db'].close()
                    self.client_state['connection_db'] = None
                return "OK: Goodbye"
            
            if cmd_type == 'HELP':
                return self._get_help()
            
            if cmd_type == 'UNKNOWN':
                return "ERROR: Unknown command"
            
            # Execute command with connection-level state
            response = self.commands.execute(cmd_type, params, self.client_state)
            return response
            
        except Exception as e:
            return f"ERROR: {str(e)}"
    
    def handle_pipeline(self, commands):
        """
        Execute multiple commands in pipeline mode.
        
        Args:
            commands: List of command strings
        
        Returns:
            List of responses for each command
        """
        responses = []
        
        for command in commands:
            response = self.handle_command(command)
            responses.append(response)
        
        return responses
    
    def _get_help(self):
        lines = [
            "Available Commands:",
            "  LOGIN <user> <pass>  - Authenticate",
            "  USE <database>       - Select database",
            "  SHOW DATABASES       - List databases",
            "  SHOW TABLES          - List tables",
            "  CREATE TABLE <name>  - Create table",
            "  INSERT INTO <table>  - Insert data",
            "  SELECT ...           - Query data",
            "  PIPELINE cmd1;;cmd2  - Execute multiple commands",
            "  HELP                 - Show this help",
            "  QUIT                 - Disconnect",
            "",
            "Pipeline Mode:",
            "  Send multiple commands separated by ;;",
            "  Example: INSERT INTO t VALUES (1);;INSERT INTO t VALUES (2)",
            "  Reduces round-trip latency for bulk operations"
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
