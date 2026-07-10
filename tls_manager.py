"""
TLS Certificate Management for KosDB

Provides certificate generation, loading, validation, and SSL context creation
for secure database connections.
"""

import os
import ssl
import logging
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Dict, Any, List
from pathlib import Path

# Cryptographic imports
try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.backends import default_backend
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False

# Configure logging
logger = logging.getLogger(__name__)


class TLSManagerError(Exception):
    """Base exception for TLS manager errors."""
    pass


class CertificateError(TLSManagerError):
    """Certificate-related errors."""
    pass


class TLSManager:
    """
    Manages TLS certificates for KosDB secure connections.
    """
    
    def __init__(self, cert_dir: Optional[str] = None):
        self.cert_dir = Path(cert_dir) if cert_dir else Path(tempfile.gettempdir()) / "kosdb_certs"
        self.cert_dir.mkdir(parents=True, exist_ok=True)
        
        self._cert_path: Optional[Path] = None
        self._key_path: Optional[Path] = None
        self._ca_cert_path: Optional[Path] = None
        self._cert_data = None
        self._key_data = None
        
        if not CRYPTOGRAPHY_AVAILABLE:
            logger.warning("cryptography library not available. TLS features limited.")
    
    def generate_self_signed_cert(
        self,
        hostname: str = "localhost",
        valid_days: int = 365,
        key_size: int = 2048,
        cert_path: Optional[str] = None,
        key_path: Optional[str] = None
    ) -> Tuple[str, str]:
        if not CRYPTOGRAPHY_AVAILABLE:
            raise CertificateError("cryptography library required. Install with: pip install cryptography")
        
        try:
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=key_size,
                backend=default_backend()
            )
            
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Local"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "Local"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "KosDB"),
                x509.NameAttribute(NameOID.COMMON_NAME, hostname),
            ])
            
            not_before = datetime.utcnow()
            not_after = not_before + timedelta(days=valid_days)
            
            import ipaddress
            try:
                ip = ipaddress.ip_address(hostname)
                san = [x509.IPAddress(ip), x509.DNSName("localhost")]
            except ValueError:
                san = [x509.DNSName(hostname), x509.DNSName(f"*.{hostname}")]
            
            cert = x509.CertificateBuilder().subject_name(
                subject
            ).issuer_name(
                issuer
            ).public_key(
                private_key.public_key()
            ).serial_number(
                x509.random_serial_number()
            ).not_valid_before(
                not_before
            ).not_valid_after(
                not_after
            ).add_extension(
                x509.SubjectAlternativeName(san),
                critical=False,
            ).add_extension(
                x509.BasicConstraints(ca=True, path_length=None),
                critical=True,
            ).sign(private_key, hashes.SHA256(), default_backend())
            
            cert_file = Path(cert_path) if cert_path else self.cert_dir / f"{hostname}.crt"
            key_file = Path(key_path) if key_path else self.cert_dir / f"{hostname}.key"
            
            cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
            key_file.write_bytes(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption()
                )
            )
            
            os.chmod(key_file, 0o600)
            
            self._cert_path = cert_file
            self._key_path = key_file
            self._cert_data = cert
            self._key_data = private_key
            
            logger.info(f"Generated self-signed certificate: {cert_file}")
            return str(cert_file), str(key_file)
            
        except Exception as e:
            raise CertificateError(f"Failed to generate certificate: {e}") from e
    
    def load_certificates(
        self,
        cert_path: str,
        key_path: str,
        ca_cert_path: Optional[str] = None,
        password: Optional[str] = None
    ) -> None:
        cert_file = Path(cert_path)
        key_file = Path(key_path)
        
        if not cert_file.exists():
            raise CertificateError(f"Certificate file not found: {cert_path}")
        if not key_file.exists():
            raise CertificateError(f"Private key file not found: {key_path}")
        
        try:
            cert_pem = cert_file.read_bytes()
            self._cert_data = x509.load_pem_x509_certificate(cert_pem, default_backend())
            
            key_pem = key_file.read_bytes()
            if password:
                self._key_data = serialization.load_pem_private_key(
                    key_pem, password=password.encode(), backend=default_backend()
                )
            else:
                self._key_data = serialization.load_pem_private_key(
                    key_pem, password=None, backend=default_backend()
                )
            
            if ca_cert_path:
                ca_file = Path(ca_cert_path)
                if not ca_file.exists():
                    raise CertificateError(f"CA certificate file not found: {ca_cert_path}")
                self._ca_cert_path = ca_file
            
            self._cert_path = cert_file
            self._key_path = key_file
            
            logger.info(f"Loaded certificate: {cert_path}")
                
        except Exception as e:
            raise CertificateError(f"Failed to load certificates: {e}") from e
    
    def validate_cert_chain(self, cert_path: Optional[str] = None) -> Dict[str, Any]:
        if not CRYPTOGRAPHY_AVAILABLE:
            return {
                'valid': False, 'expired': False, 'days_until_expiry': 0,
                'subject': 'unknown', 'issuer': 'unknown',
                'serial_number': 'unknown', 'fingerprint': 'unknown',
                'errors': ['cryptography library not available']
            }
        
        try:
            if cert_path:
                cert_pem = Path(cert_path).read_bytes()
                cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            elif self._cert_data:
                cert = self._cert_data
            else:
                raise CertificateError("No certificate loaded")
            
            now = datetime.utcnow()
            not_before = cert.not_valid_before
            not_after = cert.not_valid_after
            
            errors = []
            if now < not_before:
                errors.append(f"Certificate not yet valid (starts {not_before})")
            
            expired = now > not_after
            days_until_expiry = (not_after - now).days if not expired else 0
            
            if expired:
                errors.append(f"Certificate expired on {not_after}")
            
            subject = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
            subject_str = subject[0].value if subject else "Unknown"
            
            issuer = cert.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)
            issuer_str = issuer[0].value if issuer else "Unknown"
            
            fingerprint = cert.fingerprint(hashes.SHA256())
            fingerprint_str = ":".join(f"{b:02x}" for b in fingerprint)
            
            return {
                'valid': len(errors) == 0 and not expired,
                'expired': expired,
                'days_until_expiry': days_until_expiry,
                'subject': subject_str,
                'issuer': issuer_str,
                'serial_number': str(cert.serial_number),
                'fingerprint': fingerprint_str,
                'errors': errors
            }
            
        except Exception as e:
            raise CertificateError(f"Failed to validate certificate: {e}") from e
    
    def get_ssl_context(
        self,
        purpose: str = "server",
        verify_mode: Optional[int] = None,
        ca_file: Optional[str] = None
    ) -> ssl.SSLContext:
        if not self._cert_path or not self._key_path:
            raise CertificateError("Certificates not loaded.")
        
        if purpose == "server":
            context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        else:
            context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        
        context.load_cert_chain(
            certfile=str(self._cert_path),
            keyfile=str(self._key_path)
        )
        
        if verify_mode is not None:
            context.verify_mode = verify_mode
        
        if ca_file:
            context.load_verify_locations(cafile=ca_file)
        
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.options |= ssl.OP_NO_COMPRESSION
        
        context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:!aNULL:!MD5:!DSS')
        
        logger.info(f"Created SSL context for {purpose}")
        return context


def quick_tls_server_context(
    cert_path: Optional[str] = None,
    key_path: Optional[str] = None,
    generate_if_missing: bool = True
) -> ssl.SSLContext:
    manager = TLSManager()
    
    if cert_path and key_path:
        if Path(cert_path).exists() and Path(key_path).exists():
            manager.load_certificates(cert_path, key_path)
        elif not generate_if_missing:
            raise CertificateError(f"Certificate files not found: {cert_path}, {key_path}")
        else:
            logger.info("Generating self-signed certificate")
            manager.generate_self_signed_cert()
    else:
        manager.generate_self_signed_cert()
    
    return manager.get_ssl_context(purpose="server")
