#!/usr/bin/env python3
"""
LevelDB Socket Server with Database-Driven Authentication, Replication, TLS, and Audit Logging
"""

import socket
import ssl
import threading
import sys
import os
import argparse
import getpass
import logging
import time
from typing import Dict, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import Database
from auth import Authenticator
from parser import BackupRestoreParser
from commands import CommandRegistry
from replication import ReplicationClient, ReplicationServer

# Import configuration loader
try:
    from config_loader import ConfigLoader, ConfigError, load_config
    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False

# Import TLS manager
try:
    from tls_manager import TLSManager, CertificateError
    TLS_AVAILABLE = True
except ImportError:
    TLS_AVAILABLE = False

# Import audit logger
try:
    from audit_logger import create_audit_logger
    AUDIT_AVAILABLE = True
except ImportError:
    AUDIT_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def setup_admin(db: Database, username: str, password: str):
    """Initialize admin user."""
    db._ensure_system_tables()
    result = db.create_user(username, password, is_admin=True)
    print(result)
    result = db.grant_privilege(username, "*", "*", ["ALL"])
    print(result)
    print(f"Admin user '{username}' created.")


class ClientHandler(threading.Thread):
    def __init__(self, client_socket, address, db, authenticator, 
                 replication_client=None, audit_logger=None):
        super().__init__(daemon=True)
        self.client_socket = client_socket
        self.address = address
        self.db = db
        self.authenticator = authenticator
        self.parser = BackupRestoreParser()
        self.commands = CommandRegistry(db, authenticator, replication_client)
        self.authenticated = False
        self.session_token = None
        self.user_info = None
        self.client_state = {
            'current_db': None, 
            'username': None, 
            'is_admin': False,
            'session_token': None
        }
        self.running = True
        self.audit_logger = audit_logger
        self.session_id = f"{address[0]}:{address[1]}:{time.time()}"
    
    def send(self, message):
        self.client_socket.sendall(message.encode() + b'\n')
    
    def receive(self):
        data = self.client_socket.recv(4096)
        return data.decode().strip() if data else None
    
    def run(self):
        print(f"[SERVER] Client {self.address} connected")
        
        if self.audit_logger:
            self.audit_logger.log(
                user="anonymous",
                client_ip=self.address[0],
                command="CONNECT",
                command_type="CONNECT",
                action="AUTHENTICATION",
                success=True,
                session_id=self.session_id
            )
        
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
                
                log_data = data
                if data.upper().startswith("PASS "):
                    log_data = "PASS *****"
                logger.info(f"[AUDIT] {self.address} -> {log_data}")
                
                if not self.authenticated:
                    response = self._handle_auth(data)
                    self.send(response)
                    if response.startswith("ERROR") or response == "BYE":
                        break
                    continue
                
                start_time = time.time()
                cmd_type, params = self.parser.parse(data)
                
                if not self._check_privileges(cmd_type, params):
                    self.send("ERROR: Permission denied")
                    if self.audit_logger:
                        self.audit_logger.log(
                            user=self.user_info.get('username', 'unknown'),
                            client_ip=self.address[0],
                            command=data,
                            command_type=cmd_type,
                            action=self._get_action_type(cmd_type),
                            success=False,
                            error_message="Permission denied",
                            execution_time_ms=(time.time() - start_time) * 1000,
                            session_id=self.session_id,
                            database=self.client_state.get('current_db')
                        )
                    continue
                
                response = self.commands.execute(cmd_type, params, self.client_state)
                self.send(response)
                
                if self.audit_logger:
                    execution_time = (time.time() - start_time) * 1000
                    self.audit_logger.log(
                        user=self.user_info.get('username', 'unknown'),
                        client_ip=self.address[0],
                        command=data,
                        command_type=cmd_type,
                        action=self._get_action_type(cmd_type),
                        success=not response.startswith("ERROR"),
                        error_message=response if response.startswith("ERROR") else None,
                        execution_time_ms=execution_time,
                        affected_tables=params.get('tables', []) if params else [],
                        session_id=self.session_id,
                        database=self.client_state.get('current_db')
                    )
                
                if response == "BYE":
                    break
        
        except Exception as e:
            print(f"[SERVER] Error: {e}")
            logger.error(f"[SERVER] Error handling client {self.address}: {e}")
        finally:
            if self.session_token:
                self.authenticator.end_session(self.session_token)
            self.client_socket.close()
            print(f"[SERVER] Client {self.address} disconnected")
            
            if self.audit_logger:
                self.audit_logger.log(
                    user=self.user_info.get('username', 'anonymous') if self.user_info else 'anonymous',
                    client_ip=self.address[0],
                    command="DISCONNECT",
                    command_type="DISCONNECT",
                    action="AUTHENTICATION",
                    success=True,
                    session_id=self.session_id
                )
    
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
                self.client_state['session_token'] = token
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
        if not self.session_token:
            return False
        
        if self.user_info.get('is_admin'):
            return True
        
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
    
    def _get_action_type(self, cmd_type):
        action_map = {
            'SELECT': 'DATA_READ',
            'INSERT': 'DATA_WRITE',
            'UPDATE': 'DATA_WRITE',
            'DELETE': 'DATA_DELETE',
            'CREATE': 'SCHEMA_CHANGE',
            'DROP': 'SCHEMA_CHANGE',
            'CREATE_DB': 'SCHEMA_CHANGE',
            'DROP_DB': 'SCHEMA_CHANGE',
            'USER': 'AUTHENTICATION',
            'PASS': 'AUTHENTICATION',
            'GRANT': 'ADMIN',
            'REVOKE': 'ADMIN',
        }
        return action_map.get(cmd_type, 'UNKNOWN')


class SocketServer:
    def __init__(self, host='0.0.0.0', port=9999, data_dir='./data',
                 server_id=1, role='master', master_host=None, 
                 replication_port=None, peer_host=None,
                 tls_cert=None, tls_key=None, tls_ca=None,
                 tls_generate_self_signed=False,
                 audit_log_dir=None):
        self.host = host
        self.port = port
        self.data_dir = data_dir
        self.server_id = server_id
        self.role = role
        self.master_host = master_host
        self.replication_port = replication_port
        self.peer_host = peer_host
        
        self.tls_cert = tls_cert
        self.tls_key = tls_key
        self.tls_ca = tls_ca
        self.tls_generate_self_signed = tls_generate_self_signed
        self.tls_enabled = False
        self.ssl_context = None
        self.tls_manager = None
        
        self.audit_log_dir = audit_log_dir
        self.audit_logger = None
        if audit_log_dir and AUDIT_AVAILABLE:
            try:
                self.audit_logger = create_audit_logger(log_dir=audit_log_dir)
                logger.info(f"[Audit] Audit logging enabled: {audit_log_dir}")
            except Exception as e:
                logger.error(f"[Audit] Failed to initialize audit logger: {e}")
        
        self.is_slave = (role == 'slave')
        self.is_master_master = (peer_host is not None)
        
        self.db = Database(data_dir, server_id)
        self.authenticator = Authenticator(self.db)
        self.server_socket = None
        self.running = False
        
        self.replication_server = None
        self.replication_client = None
        self.peer_replication_client = None
        
        self._initialize_tls()
    
    def _initialize_tls(self):
        if not TLS_AVAILABLE:
            if self.tls_cert or self.tls_key or self.tls_generate_self_signed:
                logger.warning("TLS requested but tls_manager module not available")
            return
        
        if self.tls_generate_self_signed:
            logger.info("[TLS] Generating self-signed certificate...")
            try:
                self.tls_manager = TLSManager()
                self.tls_cert, self.tls_key = self.tls_manager.generate_self_signed_cert(
                    hostname=self.host if self.host != '0.0.0.0' else 'localhost'
                )
                self.tls_enabled = True
                logger.info(f"[TLS] Generated certificate: {self.tls_cert}")
            except CertificateError as e:
                logger.error(f"[TLS] Failed to generate certificate: {e}")
                return
        
        elif self.tls_cert and self.tls_key:
            if not os.path.exists(self.tls_cert):
                logger.error(f"[TLS] Certificate file not found: {self.tls_cert}")
                return
            if not os.path.exists(self.tls_key):
                logger.error(f"[TLS] Private key file not found: {self.tls_key}")
                return
            
            self.tls_enabled = True
            logger.info(f"[TLS] Using certificate: {self.tls_cert}")
            
            try:
                self.tls_manager = TLSManager()
                self.tls_manager.load_certificates(
                    self.tls_cert, 
                    self.tls_key,
                    ca_cert_path=self.tls_ca
                )
                
                validation = self.tls_manager.validate_cert_chain()
                if not validation['valid']:
                    logger.warning(f"[TLS] Certificate validation warnings: {validation['errors']}")
                else:
                    logger.info(f"[TLS] Certificate valid for {validation['days_until_expiry']} days")
                    
            except CertificateError as e:
                logger.error(f"[TLS] Failed to load certificates: {e}")
                self.tls_enabled = False
                return
        
        if self.tls_enabled and self.tls_manager:
            try:
                self.ssl_context = self.tls_manager.get_ssl_context(
                    purpose="server",
                    ca_file=self.tls_ca
                )
                logger.info("[TLS] SSL context created successfully")
            except CertificateError as e:
                logger.error(f"[TLS] Failed to create SSL context: {e}")
                self.tls_enabled = False
    
    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.running = True
        
        if self.tls_enabled and self.ssl_context:
            try:
                self.server_socket = self.ssl_context.wrap_socket(
                    self.server_socket,
                    server_side=True
                )
                logger.info("[SERVER] TLS enabled - secure connections required")
            except ssl.SSLError as e:
                logger.error(f"[TLS] Failed to wrap socket: {e}")
                self.server_socket.close()
                return
        
        print(f"[SERVER] Started on {self.host}:{self.port}")
        print(f"[SERVER] Server ID: {self.server_id}")
        print(f"[SERVER] Role: {self.role}")
        if self.tls_enabled:
            print(f"[SERVER] TLS: Enabled")
        if self.audit_logger:
            print(f"[SERVER] Audit Logging: Enabled")
        if self.is_slave and self.master_host:
            print(f"[SERVER] Master: {self.master_host}")
        if self.is_master_master:
            print(f"[SERVER] Peer: {self.peer_host}")
        print(f"[SERVER] Data: {self.db.data_dir}")
        print("Press Ctrl+C to stop")
        
        self._start_replication()
        
        try:
            while self.running:
                try:
                    client_socket, address = self.server_socket.accept()
                    
                    if self.tls_enabled and hasattr(client_socket, 'cipher'):
                        cipher = client_socket.cipher()
                        version = client_socket.version()
                        logger.info(f"[TLS] Connection from {address} using {version} with {cipher[0]}")
                    else:
                        logger.info(f"[SERVER] Connection from {address}")
                    
                    handler = ClientHandler(
                        client_socket, address, self.db, self.authenticator,
                        self.replication_client,
                        audit_logger=self.audit_logger
                    )
                    handler.start()
                    
                except ssl.SSLError as e:
                    logger.error(f"[TLS] Handshake failed: {e}")
                except Exception as e:
                    if self.running:
                        logger.error(f"[SERVER] Accept error: {e}")
                        
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.stop()
    
    def _start_replication(self):
        if self.is_slave and self.master_host:
            print(f"[REPLICATION] Slave mode - connecting to master {self.master_host}")
            parts = self.master_host.split(':')
            master_host = parts[0]
            master_port = int(parts[1]) if len(parts) > 1 else 9999
            
            self.replication_client = ReplicationClient(
                master_host=master_host,
                master_port=master_port,
                username="repl",
                password="repl",
                db=self.db,
                server_id=self.server_id
            )
            self.replication_client.start()
        
        if self.peer_host:
            print(f"[REPLICATION] Master-Master mode - connecting to peer {self.peer_host}")
            parts = self.peer_host.split(':')
            peer_host = parts[0]
            peer_port = int(parts[1]) if len(parts) > 1 else 9999
            
            self.peer_replication_client = ReplicationClient(
                master_host=peer_host,
                master_port=peer_port,
                username="repl",
                password="repl",
                db=self.db,
                server_id=self.server_id
            )
            self.peer_replication_client.start()
        
        if self.replication_port:
            print(f"[REPLICATION] Starting replication server on port {self.replication_port}")
            self.replication_server = ReplicationServer(
                host=self.host,
                port=self.replication_port,
                db=self.db,
                authenticator=self.authenticator
            )
            self.replication_server.start()
    
    def stop(self):
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        
        if self.replication_client:
            print("[REPLICATION] Stopping replication client...")
            self.replication_client.stop()
        if self.peer_replication_client:
            print("[REPLICATION] Stopping peer replication client...")
            self.peer_replication_client.stop()
        if self.replication_server:
            print("[REPLICATION] Stopping replication server...")
            self.replication_server.stop()
        
        if self.audit_logger:
            print("[AUDIT] Closing audit logger...")
            self.audit_logger.close()
        
        self.db.close()
        print("[SERVER] Stopped")


def load_server_config(config_path: Optional[str] = None,
                        args: Optional[argparse.Namespace] = None) -> Dict[str, Any]:
    """Load server configuration from file and command line arguments."""
    config = {}
    
    if config_path and CONFIG_AVAILABLE:
        try:
            loader = ConfigLoader(config_path)
            config = loader.load(validate=True, substitute_env=True)
            logger.info(f"Loaded configuration from {config_path}")
        except ConfigError as e:
            logger.error(f"Failed to load config: {e}")
            raise
    elif CONFIG_AVAILABLE and os.path.exists('config.json'):
        try:
            config = load_config('config.json')
            logger.info("Loaded configuration from config.json")
        except ConfigError as e:
            logger.warning(f"Could not load config.json: {e}")
    
    if args:
        if 'server' not in config:
            config['server'] = {}
        
        if args.host:
            config['server']['host'] = args.host
        if args.port:
            config['server']['port'] = args.port
        if args.data_dir:
            config['server']['data_dir'] = args.data_dir
        if args.server_id:
            config['server']['server_id'] = args.server_id
        
        if args.tls_cert or args.tls_key or args.tls_generate_self_signed:
            if 'tls' not in config:
                config['tls'] = {}
            config['tls']['enabled'] = True
            if args.tls_cert:
                config['tls']['cert_file'] = args.tls_cert
            if args.tls_key:
                config['tls']['key_file'] = args.tls_key
            if args.tls_ca:
                config['tls']['ca_file'] = args.tls_ca
            if args.tls_generate_self_signed:
                config['tls']['generate_self_signed'] = True
        
        if args.audit_log_dir:
            if 'audit_logging' not in config:
                config['audit_logging'] = {}
            config['audit_logging']['enabled'] = True
            config['audit_logging']['log_dir'] = args.audit_log_dir
        
        if 'replication' not in config:
            config['replication'] = {}
        if args.role:
            config['replication']['role'] = args.role
        if args.master_host:
            config['replication']['master_host'] = args.master_host
        if args.replication_port:
            config['replication']['replication_port'] = args.replication_port
        if args.peer_host:
            config['replication']['peer_host'] = args.peer_host
    
    return config


def main():
    parser = argparse.ArgumentParser(
        description='LevelDB Socket Server with Replication, TLS, and Audit Logging'
    )
    
    parser.add_argument('-c', '--config', metavar='PATH',
                       help='Path to configuration file (default: config.json)')
    parser.add_argument('--prepare_admin', metavar='USER', help='Create admin user')
    parser.add_argument('--prepare_password', metavar='PASS', help='Admin password')
    parser.add_argument('--host', help='Client host (overrides config)')
    parser.add_argument('--port', type=int, help='Client port (overrides config)')
    parser.add_argument('--data_dir', help='Data directory (overrides config)')
    parser.add_argument('--server-id', type=int, help='Unique server ID')
    
    tls_group = parser.add_argument_group('TLS/SSL Options')
    tls_group.add_argument('--tls-cert', metavar='PATH', help='Path to TLS certificate')
    tls_group.add_argument('--tls-key', metavar='PATH', help='Path to TLS private key')
    tls_group.add_argument('--tls-ca', metavar='PATH', help='Path to CA certificate')
    tls_group.add_argument('--tls-generate-self-signed', action='store_true',
                          help='Generate self-signed certificate')
    
    audit_group = parser.add_argument_group('Audit Logging Options')
    audit_group.add_argument('--audit-log-dir', metavar='PATH', help='Enable audit logging')
    
    parser.add_argument('--role', choices=['master', 'slave'], help='Server role')
    parser.add_argument('--master-host', metavar='HOST:PORT', help='Master host:port')
    parser.add_argument('--replication-port', type=int, help='Replication port')
    parser.add_argument('--peer-host', metavar='HOST:PORT', help='Peer host:port')
    
    args = parser.parse_args()
    
    try:
        config = load_server_config(args.config, args)
    except ConfigError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    
    server_config = config.get('server', {})
    host = server_config.get('host', '0.0.0.0')
    port = server_config.get('port', 9999)
    data_dir = server_config.get('data_dir', './data')
    server_id = server_config.get('server_id', 1)
    
    repl_config = config.get('replication', {})
    role = repl_config.get('role', 'master')
    master_host = repl_config.get('master_host')
    replication_port = repl_config.get('replication_port')
    peer_host = repl_config.get('peer_host')
    
    tls_config = config.get('tls', {})
    tls_cert = tls_config.get('cert_file')
    tls_key = tls_config.get('key_file')
    tls_ca = tls_config.get('ca_file')
    tls_generate_self_signed = tls_config.get('generate_self_signed', False)
    
    audit_config = config.get('audit_logging', {})
    audit_log_dir = audit_config.get('log_dir') if audit_config.get('enabled') else None
    
    if args.prepare_admin:
        password = args.prepare_password
        if not password:
            password = getpass.getpass(f"Password for '{args.prepare_admin}': ")
            confirm = getpass.getpass("Confirm: ")
            if password != confirm:
                print("ERROR: Passwords don't match!")
                sys.exit(1)
        
        db = Database(data_dir)
        setup_admin(db, args.prepare_admin, password)
        db.close()
        sys.exit(0)
    
    print("=" * 50)
    print("LevelDB Socket Server v3.1.0")
    print("=" * 50)
    print(f"Host: {host}")
    print(f"Port: {port}")
    print(f"Data: {data_dir}")
    print(f"Server ID: {server_id}")
    print(f"Role: {role}")
    print("-" * 50)
    
    server = SocketServer(
        host=host,
        port=port,
        data_dir=data_dir,
        server_id=server_id,
        role=role,
        master_host=master_host,
        replication_port=replication_port,
        peer_host=peer_host,
        tls_cert=tls_cert,
        tls_key=tls_key,
        tls_ca=tls_ca,
        tls_generate_self_signed=tls_generate_self_signed,
        audit_log_dir=audit_log_dir
    )
    server.start()


if __name__ == '__main__':
    main()
