"""
TLS/SSL Wrapper for KosDB Socket Server

Provides encrypted socket communication with certificate-based authentication.
"""

import ssl
import socket
import os
from typing import Optional, Tuple


class TLSConfig:
    """Configuration for TLS/SSL connections."""
    
    def __init__(self, 
                 enabled: bool = False,
                 cert_file: Optional[str] = None,
                 key_file: Optional[str] = None,
                 ca_file: Optional[str] = None,
                 require_client_cert: bool = False,
                 ssl_version: str = 'TLS'):
        self.enabled = enabled
        self.cert_file = cert_file
        self.key_file = key_file
        self.ca_file = ca_file
        self.require_client_cert = require_client_cert
        self.ssl_version = ssl_version
    
    @classmethod
    def from_dict(cls, config: dict) -> 'TLSConfig':
        """Create TLSConfig from configuration dictionary."""
        return cls(
            enabled=config.get('enabled', False),
            cert_file=config.get('cert_file'),
            key_file=config.get('key_file'),
            ca_file=config.get('ca_file'),
            require_client_cert=config.get('require_client_cert', False),
            ssl_version=config.get('ssl_version', 'TLS')
        )
    
    def validate(self) -> Tuple[bool, str]:
        """Validate TLS configuration."""
        if not self.enabled:
            return True, "TLS disabled"
        
        if not self.cert_file or not os.path.exists(self.cert_file):
            return False, f"Certificate file not found: {self.cert_file}"
        
        if not self.key_file or not os.path.exists(self.key_file):
            return False, f"Key file not found: {self.key_file}"
        
        if self.ca_file and not os.path.exists(self.ca_file):
            return False, f"CA file not found: {self.ca_file}"
        
        return True, "TLS configuration valid"


class TLSSocketWrapper:
    """
    Wrapper for adding TLS encryption to socket connections.
    """
    
    def __init__(self, config: TLSConfig):
        self.config = config
        self._context: Optional[ssl.SSLContext] = None
    
    def _create_context(self, server_side: bool = True) -> ssl.SSLContext:
        """Create SSL context with configured settings."""
        # Use default TLS context which auto-negotiates version
        if server_side:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        else:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        
        if server_side:
            # Server configuration
            context.load_cert_chain(
                certfile=self.config.cert_file,
                keyfile=self.config.key_file
            )
            
            if self.config.ca_file:
                context.load_verify_locations(self.config.ca_file)
                context.verify_mode = ssl.CERT_REQUIRED if self.config.require_client_cert else ssl.CERT_OPTIONAL
            else:
                context.verify_mode = ssl.CERT_NONE
        else:
            # Client configuration
            context.load_cert_chain(
                certfile=self.config.cert_file,
                keyfile=self.config.key_file
            )
            
            if self.config.ca_file:
                context.load_verify_locations(self.config.ca_file)
                context.verify_mode = ssl.CERT_REQUIRED
            else:
                # Must set check_hostname before verify_mode for client
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
        
        # Security settings - disable insecure protocols
        context.options |= ssl.OP_NO_SSLv2
        context.options |= ssl.OP_NO_SSLv3
        context.options |= ssl.OP_NO_TLSv1
        context.options |= ssl.OP_NO_TLSv1_1
        
        # Disable insecure ciphers
        context.set_ciphers('HIGH:!aNULL:!MD5')
        
        return context
    
    def wrap_server_socket(self, sock: socket.socket) -> ssl.SSLSocket:
        """Wrap a server socket with TLS."""
        if not self.config.enabled:
            return sock
        
        if self._context is None:
            self._context = self._create_context(server_side=True)
        
        return self._context.wrap_socket(sock, server_side=True)
    
    def wrap_client_socket(self, sock: socket.socket, server_hostname: Optional[str] = None) -> ssl.SSLSocket:
        """Wrap a client socket with TLS."""
        if not self.config.enabled:
            return sock
        
        if self._context is None:
            self._context = self._create_context(server_side=False)
        
        return self._context.wrap_socket(sock, server_hostname=server_hostname)
    
    def get_cipher_info(self, sock: ssl.SSLSocket) -> dict:
        """Get cipher information from SSL socket."""
        if not isinstance(sock, ssl.SSLSocket):
            return {'encrypted': False}
        
        return {
            'encrypted': True,
            'version': sock.version(),
            'cipher': sock.cipher()[0] if sock.cipher() else 'unknown',
            'bits': sock.cipher()[2] if sock.cipher() else 0
        }


def generate_self_signed_cert(cert_path: str, key_path: str, 
                              hostname: str = 'localhost',
                              days_valid: int = 365) -> Tuple[bool, str]:
    """
    Generate self-signed certificate for testing.
    
    Requires OpenSSL to be installed.
    """
    import subprocess
    
    try:
        cmd = [
            'openssl', 'req', '-x509', '-newkey', 'rsa:4096',
            '-keyout', key_path, '-out', cert_path,
            '-days', str(days_valid), '-nodes', '-subj',
            f'/CN={hostname}'
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        # Set proper permissions
        os.chmod(key_path, 0o600)
        os.chmod(cert_path, 0o644)
        
        return True, f"Certificate generated: {cert_path}, Key: {key_path}"
    
    except subprocess.CalledProcessError as e:
        return False, f"Failed to generate certificate: {e.stderr}"
    except FileNotFoundError:
        return False, "OpenSSL not found. Install OpenSSL to generate certificates."


class TLSClientHandler:
    """
    Mixin for handling TLS-enabled client connections.
    """
    
    def __init__(self, tls_wrapper: Optional[TLSSocketWrapper] = None):
        self.tls_wrapper = tls_wrapper
        self.tls_enabled = tls_wrapper is not None and tls_wrapper.config.enabled
    
    def get_connection_info(self) -> dict:
        """Get connection security information."""
        if not self.tls_enabled:
            return {'encrypted': False, 'protocol': 'plain'}
        
        if hasattr(self, 'client_socket') and isinstance(self.client_socket, ssl.SSLSocket):
            return self.tls_wrapper.get_cipher_info(self.client_socket)
        
        return {'encrypted': False, 'protocol': 'unknown'}
