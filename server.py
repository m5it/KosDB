
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


class ClientHandler(threading.Thread):
    def __init__(self, client_socket, address, db, authenticator, server_lock, replication_client=None, tls_wrapper=None):
        super().__init__(daemon=True)
        self.client_socket = client_socket
        self.address = address
        self.db = db  # Reference to shared Database instance
        self.authenticator = authenticator
        self.server_lock = server_lock
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
        self._read_buffer = b""
    
    def get_connection_info(self):
        if not self.tls_enabled:
            return {'encrypted': False, 'protocol': 'plain'}
        return {'encrypted': True}
    
    def send(self, message, use_framing=None):
        payload = message.encode()
        if use_framing is None:
            use_framing = self.client_state.get('framing', False)
        if use_framing:
            header = f"{len(payload)}\n".encode()
            self.client_socket.sendall(header + payload + b'\n')
        else:
            self.client_socket.sendall(payload + b'\n')
    
    def receive(self, use_framing=None):
        if use_framing is None:
            use_framing = self.client_state.get('framing', False)
        try:
            if use_framing:
                return self._receive_framed()
            return self._receive_line()
        except Exception as e:
            # TLS sockets can raise on connection close; treat as disconnect.
            print(f"[SERVER] Receive error: {e}")
            return None
    
    def _read_buffer_until(self, marker: bytes) -> bytes:
        """Return data up to (excluding) marker, leaving marker+rest buffered."""
        buffer = getattr(self, "_read_buffer", b"")
        self._read_buffer = b""
        while marker not in buffer:
            try:
                chunk = self.client_socket.recv(4096)
            except ssl.SSLWantReadError:
                # TLS handshake in progress; retry shortly.
                import time
                time.sleep(0.01)
                continue
            if not chunk:
                return buffer
            buffer += chunk
        result, _, leftover = buffer.partition(marker)
        if leftover:
            self._read_buffer = leftover
        return result

    def _receive_line(self):
        """Read a single newline-terminated line."""
        data = self._read_buffer_until(b"\n")
        if data is None:
            return None
        return data.decode().strip()

    def _receive_framed(self):
        """Read a length-prefixed framed message."""
        # Read header line containing the payload length.
        header = self._read_buffer_until(b"\n")
        if not header:
            return None
        try:
            length = int(header.decode().strip())
        except ValueError:
            return None
        if length < 0:
            return None

        # Read exactly length bytes.
        buffer = getattr(self, "_read_buffer", b"")
        self._read_buffer = b""
        while len(buffer) < length:
            try:
                chunk = self.client_socket.recv(max(4096, length - len(buffer)))
            except ssl.SSLWantReadError:
                import time
                time.sleep(0.01)
                continue
            if not chunk:
                return None
            buffer += chunk

        payload = buffer[:length]
        # The client terminates each framed payload with a newline. Consume it.
        leftover = buffer[length:]
        if leftover.startswith(b"\n"):
            leftover = leftover[1:]
        else:
            try:
                chunk = self.client_socket.recv(1)
            except ssl.SSLWantReadError:
                chunk = b""
            if chunk and chunk != b"\n":
                # Misbehaving client; keep the byte for the next read.
                leftover += chunk
        if leftover:
            self._read_buffer = leftover
        return payload.decode()
    
    def receive_pipeline(self, use_framing=None):
        """
        Receive multiple commands in pipeline mode.
        
        Returns:
            List of commands or None if connection closed
        """
        data = self.receive(use_framing=use_framing)
        if not data:
            return None
        
        # Split by delimiter for multiple commands
        # Commands can be separated by ;; or newlines
        commands_text = data.strip()
        if ';;' in commands_text:
            commands = [cmd.strip() for cmd in commands_text.split(';;') if cmd.strip()]
            return commands
        return [commands_text] if commands_text else None
    
    def run(self):
        print(f"[SERVER] Client {self.address} connected")
        
        try:
            # Send welcome. Framing is not yet enabled so send line-based.
            self.client_socket.sendall(f"KosDB v{__version__}\n".encode())
            self.client_socket.sendall("Commands: LOGIN <user> <pass> | HELP | QUIT | PIPELINE\n".encode())
            self._read_buffer = b""
            
            while self.running:
                # Read using the framing protocol currently in effect. Save the
                # state so the response is sent with the same protocol; this
                # makes SET FRAMING ON's own reply line-based and avoids a
                # protocol race during the transition.
                was_framing = self.client_state.get('framing', False)

                # Check for pipeline mode commands
                data = self.receive(use_framing=was_framing)
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
                        commands = self.receive_pipeline(use_framing=was_framing)
                        if not commands:
                            self.send("ERROR: Empty pipeline", use_framing=was_framing)
                            continue
                    
                    # Execute pipeline
                    if commands:
                        responses = self.handle_pipeline(commands)
                        # Send aggregated response
                        response_text = "\n".join([f"[{i+1}] {r}" for i, r in enumerate(responses)])
                        self.send(f"PIPELINE RESULTS ({len(responses)} commands):\n{response_text}", use_framing=was_framing)
                    else:
                        self.send("ERROR: No commands in pipeline", use_framing=was_framing)
                    continue
                
                # Regular single command
                response = self.handle_command(data)
                self.send(response, use_framing=was_framing)
                
                if data.upper() == 'QUIT':
                    break
                    
        except Exception as e:
            print(f"[SERVER] Client error: {e}")
        finally:
            self.client_socket.close()
            print(f"[SERVER] Client {self.address} disconnected")
    
    def handle_command(self, command):
        cmd_upper = command.upper()

        # Handle framing setup before authentication so it works for everyone.
        if cmd_upper.startswith('SET FRAMING '):
            parts = command.split()
            if len(parts) == 3 and parts[2].upper() == 'ON':
                self.client_state['framing'] = True
                return "OK: Framing enabled"
            if len(parts) == 3 and parts[2].upper() == 'OFF':
                self.client_state['framing'] = False
                return "OK: Framing disabled"
            return "ERROR: Usage: SET FRAMING ON|OFF"

        # Handle JSON setup before authentication so it works for everyone.
        if cmd_upper.startswith('SET JSON '):
            parts = command.split()
            if len(parts) == 3 and parts[2].upper() == 'ON':
                self.client_state['json_format'] = True
                return "OK: JSON format enabled"
            if len(parts) == 3 and parts[2].upper() == 'OFF':
                self.client_state['json_format'] = False
                return "OK: JSON format disabled"
            return "ERROR: Usage: SET JSON ON|OFF"

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
            parts = command.split()
            db_name = parts[1] if len(parts) > 1 else None
            if not db_name:
                return "ERROR: Usage: USE <database>"

            # Check if database exists
            if db_name not in self.db.list_databases():
                return f"ERROR: Database '{db_name}' does not exist"

            # Switch the engine to this database and track connection-level state.
            # NOTE: the Database instance is shared across connections; commands
            # operate on the engine's currently selected database.
            try:
                result = self.db.use_database(db_name)
            except Exception as e:
                return f"ERROR: Failed to open database: {e}"

            self.client_state['current_db'] = db_name
            return result

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

            # Execute command with connection-level state.
            # Serialize write commands through the server lock because the
            # Database instance is shared across threads.
            if cmd_type in ('CREATE', 'DROP', 'ALTER_TABLE', 'INSERT',
                            'UPDATE', 'UPSERT', 'DELETE', 'SET_TABLE',
                            'CREATE_DB', 'DROP_DB'):
                with self.server_lock:
                    response = self.commands.execute(cmd_type, params, self.client_state)
            else:
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
        self.lock = threading.Lock()
        
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
                
                # Wrap with TLS if enabled (server-side handshake on accepted socket)
                if self.tls_wrapper and self.tls_wrapper.config.enabled:
                    try:
                        client_socket = self.tls_wrapper.wrap_accepted_socket(client_socket)
                    except Exception as e:
                        print(f"[SERVER] TLS handshake failed: {e}")
                        client_socket.close()
                        continue
                
                handler = ClientHandler(
                    client_socket,
                    address,
                    self.db,
                    self.authenticator,
                    self.lock,
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
    parser.add_argument('--server-id', type=int, default=1, help='Server ID')
    parser.add_argument('--tls-cert', help='TLS certificate file')
    parser.add_argument('--tls-key', help='TLS key file')
    parser.add_argument('--prepare-admin', help='Create admin user')
    parser.add_argument('--prepare-password', help='Admin password')
    parser.add_argument('--export', help='Export database or database.table')
    parser.add_argument('--export-to', help='Output file for export')
    parser.add_argument('--import', dest='import_file', help='Import SQL dump file')
    
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
    
    # Handle export
    if args.export:
        from export_import import KosDBExporter
        exporter = KosDBExporter(args.data_dir)
        print(exporter.export(args.export, args.export_to))
        exporter.close()
        return
    
    # Handle import
    if args.import_file:
        from export_import import KosDBImporter
        importer = KosDBImporter(args.data_dir)
        print(importer.import_sql(args.import_file))
        importer.close()
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
