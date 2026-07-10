"""
Unit tests for TLS Certificate Management module.

Tests certificate generation, loading, validation, and SSL context creation.
"""

import os
import ssl
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Skip all tests if cryptography not available
try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.backends import default_backend
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

from tls_manager import (
    TLSManager, 
    TLSManagerError, 
    CertificateError,
    create_self_signed_tls_config,
    quick_tls_server_context
)


@unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography library not installed")
class TestTLSManager(unittest.TestCase):
    """Test cases for TLSManager class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.manager = TLSManager(cert_dir=self.temp_dir)
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_init_creates_cert_dir(self):
        """Test that initialization creates certificate directory."""
        self.assertTrue(Path(self.temp_dir).exists())
        self.assertTrue(Path(self.temp_dir).is_dir())
    
    def test_generate_self_signed_cert(self):
        """Test self-signed certificate generation."""
        cert_path, key_path = self.manager.generate_self_signed_cert(
            hostname="test.local",
            valid_days=30,
            key_size=2048
        )
        
        # Verify files exist
        self.assertTrue(Path(cert_path).exists())
        self.assertTrue(Path(key_path).exists())
        
        # Verify file sizes (cert should be non-empty)
        self.assertGreater(Path(cert_path).stat().st_size, 0)
        self.assertGreater(Path(key_path).stat().st_size, 0)
        
        # Verify private key has secure permissions
        key_stat = Path(key_path).stat()
        # Check that others don't have read permission (0o044 mask)
        self.assertEqual(key_stat.st_mode & 0o077, 0)
    
    def test_generate_self_signed_cert_with_custom_paths(self):
        """Test certificate generation with custom paths."""
        custom_cert = Path(self.temp_dir) / "custom.crt"
        custom_key = Path(self.temp_dir) / "custom.key"
        
        cert_path, key_path = self.manager.generate_self_signed_cert(
            hostname="custom.local",
            cert_path=str(custom_cert),
            key_path=str(custom_key)
        )
        
        self.assertEqual(cert_path, str(custom_cert))
        self.assertEqual(key_path, str(custom_key))
    
    def test_load_certificates(self):
        """Test loading certificates from files."""
        # First generate certificates
        cert_path, key_path = self.manager.generate_self_signed_cert(
            hostname="loadtest.local"
        )
        
        # Create new manager and load the certificates
        new_manager = TLSManager(cert_dir=self.temp_dir)
        new_manager.load_certificates(cert_path, key_path)
        
        # Verify certificates loaded
        self.assertIsNotNone(new_manager._cert_data)
        self.assertIsNotNone(new_manager._key_data)
    
    def test_load_certificates_with_ca(self):
        """Test loading certificates with CA bundle."""
        # Generate certificates
        cert_path, key_path = self.manager.generate_self_signed_cert(
            hostname="catest.local"
        )
        
        # Use the same cert as CA for testing
        new_manager = TLSManager(cert_dir=self.temp_dir)
        new_manager.load_certificates(cert_path, key_path, ca_cert_path=cert_path)
        
        self.assertIsNotNone(new_manager._ca_cert_path)
    
    def test_load_nonexistent_certificates(self):
        """Test loading non-existent certificate files."""
        with self.assertRaises(CertificateError) as context:
            self.manager.load_certificates(
                "/nonexistent/cert.pem",
                "/nonexistent/key.pem"
            )
        self.assertIn("Certificate file not found", str(context.exception))
    
    def test_validate_cert_chain(self):
        """Test certificate validation."""
        # Generate a valid certificate
        self.manager.generate_self_signed_cert(
            hostname="valid.local",
            valid_days=30
        )
        
        result = self.manager.validate_cert_chain()
        
        self.assertIsInstance(result, dict)
        self.assertIn('valid', result)
        self.assertIn('expired', result)
        self.assertIn('days_until_expiry', result)
        self.assertIn('subject', result)
        self.assertIn('issuer', result)
        
        # Should be valid and not expired
        self.assertTrue(result['valid'])
        self.assertFalse(result['expired'])
        self.assertGreater(result['days_until_expiry'], 25)  # Should be ~30 days
    
    def test_validate_expired_certificate(self):
        """Test validation of expired certificate."""
        # Generate certificate with negative validity (already expired)
        cert_path, key_path = self.manager.generate_self_signed_cert(
            hostname="expired.local",
            valid_days=1
        )
        
        # Mock the certificate to be expired
        import datetime
        with patch('tls_manager.datetime') as mock_datetime:
            # Set "now" to be 10 days in the future
            future = datetime.datetime.utcnow() + datetime.timedelta(days=10)
            mock_datetime.utcnow.return_value = future
            
            result = self.manager.validate_cert_chain()
            
            self.assertFalse(result['valid'])
            self.assertTrue(result['expired'])
            self.assertEqual(result['days_until_expiry'], 0)
            self.assertTrue(any('expired' in err for err in result['errors']))
    
    def test_get_ssl_context_server(self):
        """Test SSL context creation for server."""
        self.manager.generate_self_signed_cert(hostname="server.local")
        
        context = self.manager.get_ssl_context(purpose="server")
        
        self.assertIsInstance(context, ssl.SSLContext)
        self.assertEqual(context.protocol, ssl.PROTOCOL_TLS_SERVER)
    
    def test_get_ssl_context_client(self):
        """Test SSL context creation for client."""
        self.manager.generate_self_signed_cert(hostname="client.local")
        
        context = self.manager.get_ssl_context(purpose="client")
        
        self.assertIsInstance(context, ssl.SSLContext)
        self.assertEqual(context.protocol, ssl.PROTOCOL_TLS_CLIENT)
    
    def test_get_ssl_context_without_certs(self):
        """Test SSL context creation without loaded certificates."""
        with self.assertRaises(CertificateError) as context:
            self.manager.get_ssl_context()
        self.assertIn("Certificates not loaded", str(context.exception))
    
    def test_generate_csr(self):
        """Test CSR generation."""
        csr_pem, key_pem = self.manager.generate_csr(
            hostname="csr.local",
            country="US",
            state="California",
            locality="San Francisco",
            organization="TestOrg",
            key_size=2048
        )
        
        # Verify CSR format
        self.assertIn("BEGIN CERTIFICATE REQUEST", csr_pem)
        self.assertIn("END CERTIFICATE REQUEST", csr_pem)
        
        # Verify key format
        self.assertIn("BEGIN RSA PRIVATE KEY", key_pem)
        self.assertIn("END RSA PRIVATE KEY", key_pem)
        
        # Verify CSR can be parsed
        csr_bytes = csr_pem.encode('utf-8')
        csr = x509.load_pem_x509_csr(csr_bytes, default_backend())
        self.assertIsInstance(csr, x509.CertificateSigningRequest)
    
    def test_get_cert_info(self):
        """Test getting certificate information."""
        self.manager.generate_self_signed_cert(hostname="info.local")
        
        info = self.manager.get_cert_info()
        
        self.assertIsNotNone(info)
        self.assertIn('cert_path', info)
        self.assertIn('key_path', info)
        self.assertIn('subject', info)
        self.assertIn('issuer', info)
        self.assertIn('serial_number', info)
        self.assertIn('not_valid_before', info)
        self.assertIn('not_valid_after', info)
    
    def test_get_cert_info_not_loaded(self):
        """Test getting certificate info when none loaded."""
        info = self.manager.get_cert_info()
        self.assertIsNone(info)
    
    def test_cleanup(self):
        """Test certificate cleanup."""
        self.manager.generate_self_signed_cert(hostname="cleanup.local")
        
        # Verify files exist
        self.assertTrue(self.manager.cert_dir.exists())
        
        # Cleanup
        self.manager.cleanup()
        
        # Verify cleanup (only if using temp dir)
        if str(self.manager.cert_dir).startswith(tempfile.gettempdir()):
            self.assertFalse(self.manager.cert_dir.exists())
    
    def test_check_key_permissions_warning(self):
        """Test warning for insecure key permissions."""
        # Create a key with insecure permissions
        cert_path, key_path = self.manager.generate_self_signed_cert(
            hostname="perms.local"
        )
        
        # Change permissions to be insecure (readable by others)
        os.chmod(key_path, 0o644)
        
        # Create new manager and load (should warn)
        new_manager = TLSManager(cert_dir=self.temp_dir)
        
        with self.assertLogs('tls_manager', level='WARNING') as log_context:
            new_manager.load_certificates(cert_path, key_path)
            
            # Check that warning was logged
            self.assertTrue(
                any('Insecure permissions' in msg for msg in log_context.output)
            )


class TestConvenienceFunctions(unittest.TestCase):
    """Test convenience functions."""
    
    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography library not installed")
    def test_create_self_signed_tls_config(self):
        """Test quick TLS config creation."""
        config = create_self_signed_tls_config(hostname="quick.local")
        
        self.assertIn('cert_path', config)
        self.assertIn('key_path', config)
        self.assertIn('ssl_context', config)
        self.assertIn('manager', config)
        
        self.assertTrue(Path(config['cert_path']).exists())
        self.assertTrue(Path(config['key_path']).exists())
        self.assertIsInstance(config['ssl_context'], ssl.SSLContext)
        self.assertIsInstance(config['manager'], TLSManager)
        
        # Cleanup
        config['manager'].cleanup()
    
    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography library not installed")
    def test_quick_tls_server_context(self):
        """Test quick server context creation."""
        context = quick_tls_server_context()
        
        self.assertIsInstance(context, ssl.SSLContext)
    
    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography library not installed")
    def test_quick_tls_server_context_with_existing_certs(self):
        """Test quick context with existing certificates."""
        # First generate certificates
        temp_dir = tempfile.mkdtemp()
        manager = TLSManager(cert_dir=temp_dir)
        cert_path, key_path = manager.generate_self_signed_cert(
            hostname="existing.local"
        )
        
        try:
            # Use existing certificates
            context = quick_tls_server_context(
                cert_path=cert_path,
                key_path=key_path,
                generate_if_missing=False
            )
            
            self.assertIsInstance(context, ssl.SSLContext)
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            manager.cleanup()
    
    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography library not installed")
    def test_quick_tls_server_context_missing_certs_no_generate(self):
        """Test quick context with missing certs and no generation."""
        with self.assertRaises(CertificateError):
            quick_tls_server_context(
                cert_path="/nonexistent/cert.pem",
                key_path="/nonexistent/key.pem",
                generate_if_missing=False
            )


@unittest.skipIf(CRYPTO_AVAILABLE, "cryptography library is installed")
class TestWithoutCryptography(unittest.TestCase):
    """Test behavior when cryptography is not available."""
    
    def test_generate_self_signed_cert_raises(self):
        """Test that cert generation raises error without cryptography."""
        manager = TLSManager()
        
        with self.assertRaises(CertificateError) as context:
            manager.generate_self_signed_cert()
        
        self.assertIn("cryptography library required", str(context.exception))
    
    def test_generate_csr_raises(self):
        """Test that CSR generation raises error without cryptography."""
        manager = TLSManager()
        
        with self.assertRaises(CertificateError) as context:
            manager.generate_csr(hostname="test.local")
        
        self.assertIn("cryptography library required", str(context.exception))


class TestTLSManagerError(unittest.TestCase):
    """Test custom exception classes."""
    
    def test_tls_manager_error_is_exception(self):
        """Test TLSManagerError is an Exception."""
        self.assertTrue(issubclass(TLSManagerError, Exception))
    
    def test_certificate_error_is_tls_manager_error(self):
        """Test CertificateError is a TLSManagerError."""
        self.assertTrue(issubclass(CertificateError, TLSManagerError))


if __name__ == '__main__':
    unittest.main(verbosity=2)
