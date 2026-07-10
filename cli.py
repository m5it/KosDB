#!/usr/bin/env python3
"""
LevelDB Socket Server - Interactive CLI Client with TLS and Pooling Support
"""

import socket
import ssl
import sys
import os
import argparse
import getpass
import json
import re
import logging
from typing import Optional, List, Tuple, Any

# Try to import connection pool
try:
    from connection_pool import PooledClient, create_connection_pool
    POOL_AVAILABLE = True
except ImportError:
    POOL_AVAILABLE = False

# Try to import TLS manager
try:
    from tls_manager import TLSManager, CertificateError
    TLS_AVAILABLE = True
except ImportError:
    TLS_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'


class LevelDBClient:
    """Client for connecting to LevelDB Socket Server."""
    
    def __init__(self, host: str = 'localhost', port: int = 9999,
                 username: Optional[str] = None, password: Optional[str] = None,
                 use_tls: bool = False, ca_cert: Optional[str] = None,
                 tls_insecure: bool = False,
                 use_pool: bool = False, pool_size: int = 5):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.socket: Optional[socket.socket] = None
        self.authenticated = False
        self.current_db: Optional[str] = None
        self.use_colors = sys.stdout.isatty()
        
        self.use_tls = use_tls
        self.ca_cert = ca_cert
        self.tls_insecure = tls_insecure
        self.ssl_context: Optional[ssl.SSLContext] = None
        
        self.use_pool = use_pool and POOL_AVAILABLE
        self.pool_size = pool_size
        self._pool: Optional[Any] = None
    
    def _create_ssl_context(self) -> ssl.SSLContext:
        if self.tls_insecure:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            return context
        
        context = ssl.create_default_context()
        if self.ca_cert:
            context.load_verify_locations(cafile=self.ca_cert)
        return context
    
    def connect(self) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(30)
            
            if self.use_tls:
                self.ssl_context = self._create_ssl_context()
                self.socket = self.ssl_context.wrap_socket(sock, server_hostname=self.host)
                logger.info(f"[TLS] Connection established")
            else:
                self.socket = sock
            
            self.socket.connect((self.host, self.port))
            return True
        except Exception as e:
            print(f"ERROR: Failed to connect: {e}")
            return False
    
    def disconnect(self):
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
    
    def send(self, message: str) -> bool:
        if not self.socket:
            return False
        try:
            self.socket.sendall(message.encode() + b'\n')
            return True
        except Exception as e:
            print(f"ERROR: Send failed: {e}")
            return False
    
    def receive(self) -> Optional[str]:
        if not self.socket:
            return None
        try:
            data = self.socket.recv(16384)
            return data.decode().strip() if data else None
        except Exception as e:
            print(f"ERROR: Receive failed: {e}")
            return None
    
    def authenticate(self) -> bool:
        if not self.username:
            self.username = input("Username: ")
        if not self.password:
            self.password = getpass.getpass("Password: ")
        
        self.send(f"USER {self.username}")
        response = self.receive()
        if not response or not response.startswith("OK"):
            print(f"ERROR: {response}")
            return False
        
        self.send(f"PASS {self.password}")
        response = self.receive()
        if response and response.startswith("OK"):
            self.authenticated = True
            print(f"\n✓ {response}")
            return True
        else:
            print(f"ERROR: {response}")
            return False
    
    def execute(self, command: str) -> str:
        if self.use_pool and self._pool:
            return self._execute_pooled(command)
        
        if not self.send(command):
            return "ERROR: Not connected"
        
        response = self.receive()
        if response is None:
            return "ERROR: Connection lost"
        
        if command.upper().startswith("USE "):
            if response.startswith("OK"):
                self.current_db = command.split()[1].strip()
        
        return response
    
    def _execute_pooled(self, command: str) -> str:
        """Execute using connection pool."""
        try:
            def send_and_receive(sock):
                sock.sendall(command.encode() + b'\n')
                return sock.recv(16384).decode().strip()
            
            return self._pool.execute_with_connection(send_and_receive)
        except Exception as e:
            return f"ERROR: Pool execution failed: {e}"
    
    def _colorize(self, text: str, color: str) -> str:
        if self.use_colors:
            return f"{color}{text}{Colors.RESET}"
        return text
    
    def format_response(self, response: str) -> str:
        if response.startswith("OK"):
            return self._colorize(response, Colors.GREEN)
        elif response.startswith("ERROR"):
            return self._colorize(response, Colors.RED)
        elif "row(s) in set" in response:
            return self._colorize(response, Colors.CYAN)
        return response


def execute_script(client, script_file: str) -> int:
    try:
        with open(script_file, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"ERROR: Cannot read script file: {e}")
        return 1
    
    print(f"Executing script: {script_file}")
    print("-" * 40)
    
    exit_code = 0
    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('--'):
            continue
        
        print(f"[{i:3d}] {line}")
        response = client.execute(line)
        print(client.format_response(response))
        print()
        
        if response.startswith("ERROR"):
            exit_code = 1
    
    return exit_code


def main():
    parser = argparse.ArgumentParser(
        description='LevelDB Socket Server CLI Client',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('-H', '--host', default='localhost', help='Server host')
    parser.add_argument('-p', '--port', type=int, default=9999, help='Server port')
    parser.add_argument('-u', '--user', help='Username')
    parser.add_argument('-P', '--password', help='Password')
    parser.add_argument('--tls', action='store_true', help='Enable TLS')
    parser.add_argument('--ca-cert', help='CA certificate path')
    parser.add_argument('--tls-insecure', action='store_true', help='Skip cert verification')
    parser.add_argument('--pool', action='store_true', help='Use connection pooling')
    parser.add_argument('--pool-size', type=int, default=5, help='Pool size')
    parser.add_argument('-f', '--file', dest='script_file', help='Execute script file')
    parser.add_argument('-c', '--command', help='Execute single command')
    parser.add_argument('--no-color', action='store_true', help='Disable colors')
    
    args = parser.parse_args()
    
    client = LevelDBClient(
        host=args.host,
        port=args.port,
        username=args.user,
        password=args.password,
        use_tls=args.tls,
        ca_cert=args.ca_cert,
        tls_insecure=args.tls_insecure,
        use_pool=args.pool,
        pool_size=args.pool_size
    )
    
    if args.no_color:
        client.use_colors = False
    
    # Setup pool if requested
    if client.use_pool:
        try:
            client._pool = create_connection_pool(
                host=args.host,
                port=args.port,
                size=args.pool_size,
                use_tls=args.tls
            )
            logger.info(f"[Pool] Using connection pool (size={args.pool_size})")
        except Exception as e:
            logger.warning(f"[Pool] Failed to create pool: {e}")
            client.use_pool = False
    
    # Connect if not using pool
    if not client.use_pool:
        if not client.connect():
            return 1
    
    # Authenticate
    if not client.authenticate():
        if not client.use_pool:
            client.disconnect()
        return 1
    
    # Execute
    exit_code = 0
    try:
        if args.command:
            response = client.execute(args.command)
            print(client.format_response(response))
            if response.startswith("ERROR"):
                exit_code = 1
        elif args.script_file:
            if client.use_pool:
                logger.info("[Pool] Using pooled connections for batch execution")
            exit_code = execute_script(client, args.script_file)
        else:
            print("Interactive mode - use -c for commands or -f for scripts")
    finally:
        if client.use_pool and client._pool:
            client._pool.stop()
        elif not client.use_pool:
            client.disconnect()
    
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
