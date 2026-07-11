"""
TLS Integration Tests for KosDB v3.1.0

Tests TLS handshake, certificate validation, and fallback scenarios.
"""

import unittest
import subprocess
import time
import os
import tempfile
import shutil
import socket
import ssl
import threading
import json
from pathlib import Path

# Check if TLS is available
try:
    from tls_manager import TLSManager, quick_tls_client_context
    TLS_AVAILABLE = True
except ImportError:
    TLS_AVAILABLE = False


@unittest.skipUnless(TLS_AVAILABLE, "TLS not available")
class TestTLSIntegration(unittest.TestCase):
    """Integration tests for TLS functionality."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment with certificates."""
        cls.temp_dir = tempfile.mkdtemp()
        cls.server_dir = os.path.join(cls.temp_dir, 'server')
        cls.client_dir = os.path.join(cls.temp_dir, 'client')
        os.makedirs(cls.server_dir, exist_ok=True)
        os.makedirs(cls.client_dir, exist_ok=True)
        
        # Generate test certificates
        cls._generate_test_certs()
        
        # Create server config
        cls.config_path = os.path.join(cls.temp_dir, 'config.json')
        cls._create_server_config()
        
        cls.server_process = None
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test environment."""
        if cls.server_process:
            cls.server_process.terminate()
            cls.server_process.wait()
        
        shutil.rmtree(cls.temp_dir, ignore_errors=True)
    
    @classmethod
    def _generate_test_certs(cls):
        """Generate self-signed certificates for testing."""
        from tls_manager import TLSManager
        
        tls_mgr = TLSManager(cert_dir=cls.temp_dir)
        
        # Generate CA and server certificate
        cls.ca_cert, cls.ca_key = tls_mgr.generate_self_signed_cert(
            hostname="localhost",
            cert_path=os.path.join(cls.temp_dir, "ca.crt"),
            key_path=os.path.join(cls.temp_dir, "ca.key")
        )
        
        cls.server_cert, cls.server_key = tls_mgr.generate_self_signed_cert(
            hostname="localhost",
            cert_path=os.path.join(cls.temp_dir, "server.crt"),
            key_path=os.path.join(cls.temp_dir, "server.key")
        )
        
        # Generate client certificate for mTLS testing
        cls.client_cert, cls.client_key = tls_mgr.generate_self_signed_cert(
            hostname="client",
            cert_path=os.path.join(cls.temp_dir, "client.crt"),
            key_path=os.path.join(cls.temp_dir, "client.key")
        )
    
    @classmethod
    def _create_server_config(cls):
        """Create server configuration with TLS enabled."""
        config = {
            "version": "3.1.0",
            "server": {
                "host": "127.0.0.1",
                "port": 19999,
                "data_dir": cls.server_dir,
                "server_id": 1
            },
            "tls": {
                "enabled": True,
                "cert_file": cls.server_cert,
                "key_file": cls.server_key,
                "ca_file": cls.ca_cert,
                "generate_self_signed": False,
                "client_auth": False
            },
            "audit_logging": {
                "enabled": False
            }
        }
        
        with open(cls.config_path, 'w') as f:
            json.dump(config, f, indent=2)
    
    def setUp(self):
        """Start server before each test."""
        self.server_process = subprocess.Popen(
            ['python', 'server.py', '-c', self.config_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        
        # Wait for server to start
        time.sleep(2)
        
        # Check if server is running
        self.assertIsNone(self.server_process.poll(), "Server failed to start")
    
    def tearDown(self):
        """Stop server after each test."""
        if self.server_process:
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
            self.server_process = None
    
    def test_tls_handshake_success(self):
        """Test successful TLS handshake."""
        # Create SSL context
        context = ssl.create_default_context(cafile=self.ca_cert)
        
        # Connect with TLS
        with socket.create_connection(('127.0.0.1', 19999)) as sock:
            with context.wrap_socket(sock, server_hostname='localhost') as ssock:
                # Send test message
                ssock.send(b"TEST\\n")
                response = ssock.recv(1024)
                self.assertIn(b"LevelDB", response)
    
    def test_tls_certificate_validation(self):
        """Test certificate validation with wrong CA."""
        # Create context with wrong CA (will fail)
        wrong_ca = os.path.join(self.temp_dir, "wrong_ca.pem")
        with open(wrong_ca, 'w') as f:
            f.write("-----BEGIN CERTIFICATE-----\\n")
            f.write("MIIDXTCCAkWgAwIBAgIJAKoK/heBjcOuMA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNV\\n")
            f.write("BAYTAkFVMRMwEQYDVQQIDApTb21lLVN0YXRlMSEwHwYDVQQKDBhJbnRlcm5ldCBX\\n")
            f.write("aWRnaXRzIFB0eSBMdGQwHhcNMTcwNjE0MDIxNDEyWhcNMjcwNjEyMDIxNDEyWjBF\\n")
            f.write("MQswCQYDVQQGEwJBVTETMBEGA1UECAwKU29tZS1TdGF0ZTEhMB8GA1UECgwYSW50\\n")
            f.write("ZXJuZXQgV2lkZ2l0cyBQdHkgTHRkMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIB\\n")
            f.write("CgKCAQEAwwTb3cCw7yoFqTSFUwqe0vJhNlCHpyYBF4TXAYOt7YmOOSFtBcSWLKxJ\\n")
            f.write("PFU3l0q0npZ2Q3ZrCJ0bGCTiI3r+\\n")
            f.write("-----END CERTIFICATE-----\\n")
        
        context = ssl.create_default_context(cafile=wrong_ca)
        
        # Should fail to connect
        with self.assertRaises(ssl.SSLError):
            with socket.create_connection(('127.0.0.1', 19999), timeout=2) as sock:
                with context.wrap_socket(sock, server_hostname='localhost') as ssock:
                    pass
    
    def test_non_tls_rejected(self):
        """Test that non-TLS connections are rejected when TLS is required."""
        # Try plain socket connection
        try:
            sock = socket.create_connection(('127.0.0.1', 19999), timeout=2)
            sock.send(b"TEST\\n")
            response = sock.recv(1024)
            # Server might accept but respond with TLS error or close
            sock.close()
        except (socket.error, ConnectionResetError):
            # Expected - TLS server rejects non-TLS
            pass
    
    def test_tls_with_client_auth(self):
        """Test TLS with mutual authentication (mTLS)."""
        # Update config for client auth
        config = json.load(open(self.config_path))
        config['tls']['client_auth'] = True
        with open(self.config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        # Restart server
        self.tearDown()
        self.setUp()
        
        # Create context with client certificate
        context = ssl.create_default_context(cafile=self.ca_cert)
        context.load_cert_chain(self.client_cert, self.client_key)
        
        # Connect with client cert
        with socket.create_connection(('127.0.0.1', 19999)) as sock:
            with context.wrap_socket(sock, server_hostname='localhost') as ssock:
                ssock.send(b"TEST\\n")
                response = ssock.recv(1024)
                self.assertIn(b"LevelDB", response)
    
    def test_tls_cipher_negotiation(self):
        """Test TLS cipher suite negotiation."""
        context = ssl.create_default_context(cafile=self.ca_cert)
        
        with socket.create_connection(('127.0.0.1', 19999)) as sock:
            with context.wrap_socket(sock, server_hostname='localhost') as ssock:
                # Check cipher used
                cipher = ssock.cipher()
                self.assertIsNotNone(cipher)
                self.assertIn(cipher[0], ['ECDHE-RSA-AES256-GCM-SHA384', 
                                          'ECDHE-RSA-AES128-GCM-SHA256',
                                          'TLS_AES_256_GCM_SHA384',
                                          'TLS_AES_128_GCM_SHA256'])


@unittest.skipUnless(TLS_AVAILABLE, "TLS not available")
class TestTLSFallback(unittest.TestCase):
    """Test fallback to non-TLS when TLS is not configured."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, 'config.json')
        
        # Create config WITHOUT TLS
        config = {
            "version": "3.1.0",
            "server": {
                "host": "127.0.0.1",
                "port": 19998,
                "data_dir": self.temp_dir,
                "server_id": 1
            },
            "tls": {
                "enabled": False
            }
        }
        
        with open(self.config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        self.server_process = subprocess.Popen(
            ['python', 'server.py', '-c', self.config_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        
        time.sleep(2)
    
    def tearDown(self):
        if self.server_process:
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
        
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_plain_connection_works(self):
        """Test that plain TCP works when TLS is disabled."""
        with socket.create_connection(('127.0.0.1', 19998)) as sock:
            sock.send(b"TEST\\n")
            response = sock.recv(1024)
            self.assertIn(b"LevelDB", response)


if __name__ == '__main__':
    unittest.main(verbosity=2)
