#!/usr/bin/env python3
"""
LevelDB Socket Server with Database-Driven Authentication, Replication, and TLS Encryption
"""

import socket
import threading
import ssl
import sys
import os
import argparse
import getpass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import Database
from auth import Authenticator
from parser import BackupRestoreParser
from commands import CommandRegistry
from replication import ReplicationClient, ReplicationServer
from tls_wrapper import TLSConfig, TLSSocketWrapper, generate_self_signed_cert


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
        """Get connection security information."""
        if not self.tls_enabled:
            return {'encrypted': False, 'protocol': 'plain'}
        if hasattr(self, 'client_socket') and hasattr(self.client_socket, 'version'):
            return {
                'encrypted': True,
                'version': self.client_socket.version(),
                'cipher': self.client_socket.cipher()[0] if self.client_socket.cipher() else 'unknown'
            }
        return {'encrypted': False}
    
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
                return "ERROR: USER requires username"
            self.username = parts[1]
            return "OK: Send PASS <password>"
        
        elif cmd == "PASS":
            if len(parts) < 2:
                return "ERROR: PASS requires password"
            if not hasattr(self, 'username'):
                return "ERROR: Send USER first"
            
            password = parts[1]
            success, result = self.authenticator.authenticate(self.username, password)
            
            if success:
                self.authenticated = True
                self.session_token = result
                self.user_info = self.authenticator.get_user_info(self.username)
                self.client_state['username'] = self.username
                self.client_state['is_admin'] = self.user_info.get('is_admin', False)
                return f"OK: Welcome {self.username}"
            else:
                return f"ERROR: {result}"
        
        elif cmd == "QUIT":
            return "BYE"
        
        else:
            return "ERROR: Authentication required"
    
    def _check_privileges(self, cmd_type, params):
        """Check if user has privileges for command."""
        if not self.user_info:
            return False
        
        is_admin = self.user_info.get('is_admin', False)
        
        # Admin-only commands
        admin_commands = {
            'CREATE_USER', 'DROP_USER', 'GRANT_ADMIN', 'REVOKE_ADMIN',
            'BACKUP_DATABASE', 'BACKUP_TABLE', 'RESTORE_DATABASE',
            'FAILOVER_STATUS', 'FAILOVER_PROPOSE'
        }
        
        if cmd_type in admin_commands and not is_admin:
            return False
        
        return True


class SocketServer:
    def __init__(self, host='0.0.0.0', port=9999, data_dir='./data',
                 server_id=1, role='master', master_host=None, 
                 replication_port=None, peer_host=None,
                 tls_config=None):
        self.host = host
        self.port = port
        self.data_dir = data_dir
        self.server_id = server_id
        self.role = role
        self.master_host = master_host
        self.replication_port = replication_port
        self.peer_host = peer_host
        
        # TLS configuration
        self.tls_config = tls_config or TLSConfig(enabled=False)
        self.tls_wrapper = TLSSocketWrapper(self.tls_config) if self.tls_config.enabled else None
        
        # Replication state
        self.is_slave = (role == 'slave')
        self.is_master_master = (peer_host is not None)
        
        self.db = Database(data_dir, server_id)
        self.authenticator = Authenticator(self.db)
        self.server_socket = None
        self.running = False
        
        # Replication components (initialized later)
        self.replication_server = None
        self.replication_client = None
        self.peer_replication_client = None
    
    def start(self):
        # Start client socket server
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.running = True
        
        print(f"[SERVER] Started on {self.host}:{self.port}")
        if self.tls_wrapper and self.tls_wrapper.config.enabled:
            print(f"[SERVER] TLS encryption enabled")
            print(f"[SERVER] Certificate: {self.tls_wrapper.config.cert_file}")
        else:
            print(f"[SERVER] Warning: Running without TLS encryption")
        print(f"[SERVER] Server ID: {self.server_id}")
        print(f"[SERVER] Role: {self.role}")
        if self.is_slave and self.master_host:
            print(f"[SERVER] Master: {self.master_host}")
        if self.is_master_master:
            print(f"[SERVER] Peer: {self.peer_host}")
        print(f"[SERVER] Data: {self.db.data_dir}")
        print("Press Ctrl+C to stop")
        
        # Start replication components if configured
        self._start_replication()
        
        try:
            while self.running:
                client_socket, address = self.server_socket.accept()
                
                # Wrap with TLS if enabled
                if self.tls_wrapper:
                    try:
                        client_socket = self.tls_wrapper.wrap_server_socket(client_socket)
                    except ssl.SSLError as e:
                        print(f"[SERVER] TLS handshake failed for {address}: {e}")
                        client_socket.close()
                        continue
                
                handler = ClientHandler(
                    client_socket, address, self.db, self.authenticator,
                    self.replication_client, self.tls_wrapper
                )
                handler.start()
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.stop()
    
    def _start_replication(self):
        """Initialize replication components based on role."""
        if self.replication_port:
            self.replication_server = ReplicationServer(
                self.db, self.replication_port
            )
            self.replication_server.start()
            print(f"[REPLICATION] Server listening on port {self.replication_port}")
        
        if self.is_slave and self.master_host:
            self.replication_client = ReplicationClient(
                self.db, self.master_host, self.server_id
            )
            self.replication_client.start()
            print(f"[REPLICATION] Connected to master {self.master_host}")
        
        if self.is_master_master and self.peer_host:
            parts = self.peer_host.split(':')
            peer_host = parts[0]
            peer_port = int(parts[1]) if len(parts) > 1 else 9999
            
            self.peer_replication_client = ReplicationClient(
                self.db, self.peer_host, self.server_id
            )
            self.peer_replication_client.start()
            print(f"[REPLICATION] Connected to peer {self.peer_host}")
    
    def stop(self):
        """Stop server and cleanup resources."""
        self.running = False
        
        # Stop replication components
        if self.replication_client:
            print("[REPLICATION] Stopping replication client...")
            self.replication_client.stop()
        if self.peer_replication_client:
            print("[REPLICATION] Stopping peer replication client...")
            self.peer_replication_client.stop()
        if self.replication_server:
            print("[REPLICATION] Stopping replication server...")
            self.replication_server.stop()
        
        if self.server_socket:
            self.server_socket.close()
        self.db.close()


def setup_admin(db, username, password):
    """Create or update admin user."""
    auth = Authenticator(db)
    success, message = auth.create_user(username, password, is_admin=True)
    print(message)
    return success


def main():
    parser = argparse.ArgumentParser(description='LevelDB Socket Server with Replication and TLS')
    
    # Basic server options
    parser.add_argument('--prepare_admin', metavar='USER', help='Create admin user')
    parser.add_argument('--prepare_password', metavar='PASS', help='Admin password')
    parser.add_argument('--host', default='0.0.0.0', help='Client host (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=9999, help='Client port (default: 9999)')
    parser.add_argument('--data_dir', default='./data', help='Data directory (default: ./data)')
    
    # TLS options
    parser.add_argument('--tls', action='store_true', help='Enable TLS encryption')
    parser.add_argument('--tls-cert', metavar='FILE', help='TLS certificate file')
    parser.add_argument('--tls-key', metavar='FILE', help='TLS private key file')
    parser.add_argument('--tls-ca', metavar='FILE', help='TLS CA certificate file')
    parser.add_argument('--tls-client-cert', action='store_true', help='Require client certificates')
    parser.add_argument('--generate-cert', action='store_true', help='Generate self-signed certificate')
    
    # Replication options
    parser.add_argument('--server-id', type=int, default=1, 
                       help='Unique server ID (default: 1)')
    parser.add_argument('--role', choices=['master', 'slave'], default='master',
                       help='Server role: master or slave (default: master)')
    parser.add_argument('--master-host', metavar='HOST:PORT',
                       help='Master host:port for slave replication')
    parser.add_argument('--replication-port', type=int,
                       help='Port for replication connections (optional)')
    parser.add_argument('--peer-host', metavar='HOST:PORT',
                       help='Peer host:port for master-master replication')
    
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
    
    # Generate self-signed certificate if requested
    if args.generate_cert:
        cert_path = args.tls_cert or './server.crt'
        key_path = args.tls_key or './server.key'
        success, msg = generate_self_signed_cert(cert_path, key_path)
        print(msg)
        if not success:
            sys.exit(1)
        print(f"\nTo use the certificate, run with:")
        print(f"  python server.py --tls --tls-cert {cert_path} --tls-key {key_path}")
        sys.exit(0)
    
    # Setup TLS configuration
    tls_config = TLSConfig(enabled=False)
    if args.tls:
        tls_config = TLSConfig(
            enabled=True,
            cert_file=args.tls_cert,
            key_file=args.tls_key,
            ca_file=args.tls_ca,
            require_client_cert=args.tls_client_cert
        )
        
        valid, msg = tls_config.validate()
        if not valid:
            print(f"ERROR: {msg}")
            print("\nTo generate a self-signed certificate, run:")
            print("  python server.py --generate-cert")
            sys.exit(1)
    
    print("=" * 50)
    print("LevelDB Socket Server")
    print("=" * 50)
    print(f"Host: {args.host}")
    print(f"Port: {args.port}")
    if args.tls:
        print(f"TLS: Enabled")
        print(f"Cert: {args.tls_cert}")
    else:
        print(f"TLS: Disabled")
    print(f"Server ID: {args.server_id}")
    print(f"Role: {args.role}")
    print(f"Data: {args.data_dir}")
    if args.master_host:
        print(f"Master: {args.master_host}")
    if args.peer_host:
        print(f"Peer: {args.peer_host}")
    print("\nSetup admin:")
    print(f"  python server.py --prepare_admin admin --prepare_password <pass>")
    print("-" * 50)
    
    server = SocketServer(
        host=args.host,
        port=args.port,
        data_dir=args.data_dir,
        server_id=args.server_id,
        role=args.role,
        master_host=args.master_host,
        replication_port=args.replication_port,
        peer_host=args.peer_host,
        tls_config=tls_config
    )
    server.start()


if __name__ == '__main__':
    main()
