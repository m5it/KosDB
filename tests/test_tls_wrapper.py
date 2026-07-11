"""
Tests for TLS/SSL Wrapper
"""

import unittest
import os
import tempfile
import shutil
import socket
import threading
import time
from tls_wrapper import TLSConfig, TLSSocketWrapper, generate_self_signed_cert


class TestTLSConfig(unittest.TestCase):
    def test_default_config(self):
        config = TLSConfig()
        self.assertFalse(config.enabled)
        self.assertIsNone(config.cert_file)
        self.assertIsNone(config.key_file)
        self.assertIsNone(config.ca_file)
        self.assertFalse(config.require_client_cert)
    
    def test_from_dict(self):
        config_dict = {
            'enabled': True,
            'cert_file': '/path/to/cert.pem',
            'key_file': '/path/to/key.pem',
            'ca_file': '/path/to/ca.pem',
            'require_client_cert': True,
            'ssl_version': 'TLSv1_2'
        }
        config = TLSConfig.from_dict(config_dict)
        self.assertTrue(config.enabled)
        self.assertEqual(config.cert_file, '/path/to/cert.pem')
        self.assertEqual(config.key_file, '/path/to/key.pem')
        self.assertEqual(config.ca_file, '/path/to/ca.pem')
        self.assertTrue(config.require_client_cert)
    
    def test_validate_disabled(self):
        config = TLSConfig(enabled=False)
        valid, msg = config.validate()
        self.assertTrue(valid)
        self.assertEqual(msg, "TLS disabled")
    
    def test_validate_missing_cert(self):
        config = TLSConfig(enabled=True, cert_file='/nonexistent/cert.pem')
        valid, msg = config.validate()
        self.assertFalse(valid)
        self.assertIn("Certificate file not found", msg)
    
    def test_validate_missing_key(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            cert_path = f.name
        
        config = TLSConfig(enabled=True, cert_file=cert_path, key_file='/nonexistent/key.pem')
        valid, msg = config.validate()
        self.assertFalse(valid)
        self.assertIn("Key file not found", msg)
        
        os.unlink(cert_path)


class TestTLSSocketWrapper(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.cert_path = os.path.join(self.temp_dir, 'test.crt')
        self.key_path = os.path.join(self.temp_dir, 'test.key')
        
        # Generate test certificate
        success, msg = generate_self_signed_cert(self.cert_path, self.key_path)
        if not success:
            self.skipTest(f"Cannot generate test certificate: {msg}")
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_wrapper_disabled(self):
        config = TLSConfig(enabled=False)
        wrapper = TLSSocketWrapper(config)
        self.assertIsNone(wrapper._context)
    
    def test_wrap_server_socket_disabled(self):
        config = TLSConfig(enabled=False)
        wrapper = TLSSocketWrapper(config)
        
        # Create a dummy socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        wrapped = wrapper.wrap_server_socket(sock)
        
        # Should return original socket when TLS disabled
        self.assertEqual(wrapped, sock)
        sock.close()


class TestSelfSignedCertGeneration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.cert_path = os.path.join(self.temp_dir, 'test.crt')
        self.key_path = os.path.join(self.temp_dir, 'test.key')
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_generate_cert(self):
        success, msg = generate_self_signed_cert(self.cert_path, self.key_path)
        
        # Skip if OpenSSL not available
        if not success and "OpenSSL not found" in msg:
            self.skipTest("OpenSSL not installed")
        
        self.assertTrue(success)
        self.assertTrue(os.path.exists(self.cert_path))
        self.assertTrue(os.path.exists(self.key_path))
        
        # Check permissions
        key_mode = os.stat(self.key_path).st_mode
        self.assertEqual(key_mode & 0o777, 0o600)


class TestTLSIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.cert_path = os.path.join(self.temp_dir, 'server.crt')
        self.key_path = os.path.join(self.temp_dir, 'server.key')
        
        success, msg = generate_self_signed_cert(self.cert_path, self.key_path)
        if not success:
            self.skipTest(f"Cannot generate test certificate: {msg}")
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_tls_server_client_connection(self):
        """Test TLS-encrypted server-client communication."""
        # Server setup
        server_config = TLSConfig(
            enabled=True,
            cert_file=self.cert_path,
            key_file=self.key_path
        )
        server_wrapper = TLSSocketWrapper(server_config)
        
        # Client setup (using same cert for testing)
        client_config = TLSConfig(
            enabled=True,
            cert_file=self.cert_path,
            key_file=self.key_path
        )
        client_wrapper = TLSSocketWrapper(client_config)
        
        # Create server socket
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(('127.0.0.1', 0))
        port = server_sock.getsockname()[1]
        server_sock.listen(1)
        
        received_data = []
        server_ready = threading.Event()
        
        def server_thread():
            server_ready.set()
            conn, addr = server_sock.accept()
            try:
                tls_conn = server_wrapper.wrap_server_socket(conn)
                data = tls_conn.recv(1024)
                received_data.append(data.decode())
                tls_conn.send(b"Hello secure client")
            except Exception as e:
                received_data.append(f"Error: {e}")
            finally:
                server_sock.close()
        
        # Start server
        srv = threading.Thread(target=server_thread)
        srv.start()
        server_ready.wait()
        
        # Connect client
        client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_sock.connect(('127.0.0.1', port))
        
        try:
            tls_client = client_wrapper.wrap_client_socket(
                client_sock, 
                server_hostname='localhost'
            )
            tls_client.send(b"Hello secure server")
            response = tls_client.recv(1024)
            self.assertEqual(response.decode(), "Hello secure client")
        finally:
            client_sock.close()
        
        srv.join(timeout=5)
        self.assertEqual(received_data, ["Hello secure server"])


if __name__ == '__main__':
    unittest.main(verbosity=2)
