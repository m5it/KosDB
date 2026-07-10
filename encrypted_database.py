"""
Transparent Encryption at Rest for LevelDB

Provides AES-256-GCM encryption wrapper around Database class.
Supports key derivation from passphrase, key rotation, and encryption metrics.
"""

import os
import json
import time
import struct
import hashlib
import secrets
import logging
from typing import Optional, Dict, Any, Union, Tuple, List
from dataclasses import dataclass, field
from pathlib import Path

# Try to import cryptography
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

from database import Database

logger = logging.getLogger(__name__)


@dataclass
class EncryptionMetrics:
    """Metrics for encryption operations."""
    total_encryptions: int = 0
    total_decryptions: int = 0
    total_bytes_encrypted: int = 0
    total_bytes_decrypted: int = 0
    encryption_time_ms: float = 0.0
    decryption_time_ms: float = 0.0
    key_rotations: int = 0
    
    def record_encryption(self, bytes_count: int, duration_ms: float):
        """Record encryption operation."""
        self.total_encryptions += 1
        self.total_bytes_encrypted += bytes_count
        self.encryption_time_ms += duration_ms
    
    def record_decryption(self, bytes_count: int, duration_ms: float):
        """Record decryption operation."""
        self.total_decryptions += 1
        self.total_bytes_decrypted += bytes_count
        self.decryption_time_ms += duration_ms
    
    def record_key_rotation(self):
        """Record key rotation."""
        self.key_rotations += 1
    
    def get_overhead_ratio(self) -> float:
        """Calculate encryption overhead ratio."""
        if self.total_bytes_encrypted == 0:
            return 0.0
        # AES-GCM adds 16 bytes tag + 12 bytes nonce
        overhead = self.total_encryptions * 28
        return overhead / (self.total_bytes_encrypted + overhead)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'total_encryptions': self.total_encryptions,
            'total_decryptions': self.total_decryptions,
            'total_bytes_encrypted': self.total_bytes_encrypted,
            'total_bytes_decrypted': self.total_bytes_decrypted,
            'encryption_time_ms': round(self.encryption_time_ms, 3),
            'decryption_time_ms': round(self.decryption_time_ms, 3),
            'key_rotations': self.key_rotations,
            'overhead_ratio': round(self.get_overhead_ratio() * 100, 2)
        }


class KeyManager:
    """Manages encryption keys with key derivation and rotation."""
    
    # AES-256 requires 32-byte key
    KEY_SIZE = 32
    # PBKDF2 iterations
    PBKDF2_ITERATIONS = 100000
    # Salt size for key derivation
    SALT_SIZE = 32
    
    def __init__(self, key_file: Optional[str] = None):
        """
        Initialize key manager.
        
        Args:
            key_file: Path to store/load master key
        """
        if not CRYPTO_AVAILABLE:
            raise ImportError("cryptography library required")
        
        self.key_file = key_file
        self._master_key: Optional[bytes] = None
        self._salt: Optional[bytes] = None
        self._key_id: str = ""
    
    def generate_key(self) -> bytes:
        """Generate a random 256-bit key."""
        return secrets.token_bytes(self.KEY_SIZE)
    
    def derive_key(self, passphrase: str, salt: Optional[bytes] = None) -> Tuple[bytes, bytes]:
        """
        Derive key from passphrase using PBKDF2.
        
        Args:
            passphrase: User passphrase
            salt: Optional salt (generated if None)
        
        Returns:
            Tuple of (derived_key, salt)
        """
        if salt is None:
            salt = secrets.token_bytes(self.SALT_SIZE)
        
        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=self.KEY_SIZE,
            salt=salt,
            iterations=self.PBKDF2_ITERATIONS,
            backend=default_backend()
        )
        
        key = kdf.derive(passphrase.encode('utf-8'))
        return key, salt
    
    def load_or_create_key(self, passphrase: Optional[str] = None) -> bytes:
        """
        Load existing key or create new one.
        
        Args:
            passphrase: Optional passphrase for key derivation
        
        Returns:
            Master key bytes
        """
        if self.key_file and os.path.exists(self.key_file):
            return self._load_key_file(passphrase)
        
        # Generate new key
        if passphrase:
            key, salt = self.derive_key(passphrase)
            self._salt = salt
        else:
            key = self.generate_key()
            self._salt = None
        
        self._master_key = key
        self._key_id = hashlib.sha256(key).hexdigest()[:16]
        
        if self.key_file:
            self._save_key_file(passphrase)
        
        return key
    
    def _load_key_file(self, passphrase: Optional[str] = None) -> bytes:
        """Load key from file."""
        with open(self.key_file, 'rb') as f:
            data = f.read()
        
        # Check if it's a derived key (has salt) or raw key
        if len(data) > self.KEY_SIZE:
            # Has salt - derived key
            salt = data[:self.SALT_SIZE]
            stored_key_hash = data[self.SALT_SIZE:]
            
            if not passphrase:
                raise ValueError("Passphrase required to unlock key file")
            
            key, _ = self.derive_key(passphrase, salt)
            key_hash = hashlib.sha256(key).digest()
            
            if key_hash != stored_key_hash:
                raise ValueError("Invalid passphrase")
            
            self._salt = salt
            self._master_key = key
        else:
            # Raw key
            self._master_key = data
            self._salt = None
        
        self._key_id = hashlib.sha256(self._master_key).hexdigest()[:16]
        return self._master_key
    
    def _save_key_file(self, passphrase: Optional[str] = None):
        """Save key to file."""
        os.makedirs(os.path.dirname(self.key_file), exist_ok=True)
        
        if self._salt:
            # Store salt + hash of derived key
            key_hash = hashlib.sha256(self._master_key).digest()
            data = self._salt + key_hash
        else:
            # Store raw key
            data = self._master_key
        
        with open(self.key_file, 'wb') as f:
            f.write(data)
        
        # Restrict permissions
        os.chmod(self.key_file, 0o600)
    
    def rotate_key(self, new_passphrase: Optional[str] = None) -> Tuple[bytes, bytes]:
        """
        Generate new key for key rotation.
        
        Returns:
            Tuple of (old_key, new_key)
        """
        old_key = self._master_key
        
        if new_passphrase:
            new_key, new_salt = self.derive_key(new_passphrase)
            self._salt = new_salt
        else:
            new_key = self.generate_key()
        
        self._master_key = new_key
        self._key_id = hashlib.sha256(new_key).hexdigest()[:16]
        
        if self.key_file:
            self._save_key_file(new_passphrase if new_passphrase else None)
        
        return old_key, new_key
    
    @property
    def master_key(self) -> Optional[bytes]:
        """Get current master key."""
        return self._master_key
    
    @property
    def key_id(self) -> str:
        """Get current key ID."""
        return self._key_id


class EncryptedDatabase:
    """
    Transparent encryption wrapper around Database class.
    
    Encrypts all data using AES-256-GCM before storing in LevelDB.
    """
    
    # Version marker for encrypted data
    ENCRYPTION_VERSION = 1
    # Header size: version(1) + key_id_len(1) + key_id + nonce(12) + tag(16)
    HEADER_OVERHEAD = 30
    
    def __init__(self, data_dir: str, server_id: int = 1,
                 encryption_key: Optional[Union[str, bytes]] = None,
                 key_file: Optional[str] = None,
                 passphrase: Optional[str] = None):
        """
        Initialize encrypted database.
        
        Args:
            data_dir: Directory for database files
            server_id: Unique server ID
            encryption_key: Raw encryption key (32 bytes) or hex string
            key_file: Path to key file
            passphrase: Passphrase for key derivation
        """
        if not CRYPTO_AVAILABLE:
            raise ImportError("cryptography library required")
        
        self.data_dir = data_dir
        self.server_id = server_id
        self.metrics = EncryptionMetrics()
        
        # Initialize key manager
        self.key_manager = KeyManager(key_file)
        
        if encryption_key:
            # Use provided key
            if isinstance(encryption_key, str):
                encryption_key = bytes.fromhex(encryption_key)
            self.key_manager._master_key = encryption_key
            self.key_manager._key_id = hashlib.sha256(encryption_key).hexdigest()[:16]
        elif passphrase:
            # Derive key from passphrase
            self.key_manager.load_or_create_key(passphrase)
        elif key_file:
            # Load from file
            self.key_manager.load_or_create_key()
        else:
            raise ValueError("Must provide encryption_key, key_file, or passphrase")
        
        # Initialize underlying database
        # Use subdirectory for encrypted data to coexist with regular databases
        encrypted_dir = os.path.join(data_dir, 'encrypted')
        self.db = Database(encrypted_dir, server_id)
        
        # Initialize AES-GCM
        self._init_cipher()
        
        logger.info(f"[EncryptedDB] Initialized with key_id={self.key_manager.key_id}")
    
    def _init_cipher(self):
        """Initialize AES-GCM cipher."""
        self.cipher = AESGCM(self.key_manager.master_key)
    
    def _encrypt(self, plaintext: bytes) -> bytes:
        """
        Encrypt data with AES-256-GCM.
        
        Format: version(1) | key_id_len(1) | key_id | nonce(12) | ciphertext | tag(16)
        """
        start_time = time.time()
        
        # Generate random nonce
        nonce = secrets.token_bytes(12)
        
        # Encrypt
        ciphertext = self.cipher.encrypt(nonce, plaintext, None)
        
        # Build header
        key_id_bytes = self.key_manager.key_id.encode('utf-8')
        header = struct.pack(
            '!BB',
            self.ENCRYPTION_VERSION,
            len(key_id_bytes)
        ) + key_id_bytes + nonce
        
        # Combine
        result = header + ciphertext
        
        # Record metrics
        duration_ms = (time.time() - start_time) * 1000
        self.metrics.record_encryption(len(plaintext), duration_ms)
        
        return result
    
    def _decrypt(self, ciphertext: bytes) -> bytes:
        """
        Decrypt data with AES-256-GCM.
        """
        start_time = time.time()
        
        # Parse header
        version = ciphertext[0]
        if version != self.ENCRYPTION_VERSION:
            raise ValueError(f"Unsupported encryption version: {version}")
        
        key_id_len = ciphertext[1]
        header_len = 2 + key_id_len + 12  # version + len + key_id + nonce
        
        key_id = ciphertext[2:2+key_id_len].decode('utf-8')
        nonce = ciphertext[2+key_id_len:header_len]
        encrypted_data = ciphertext[header_len:]
        
        # Check key ID (for key rotation support)
        if key_id != self.key_manager.key_id:
            logger.warning(f"[EncryptedDB] Data encrypted with different key: {key_id}")
        
        # Decrypt
        plaintext = self.cipher.decrypt(nonce, encrypted_data, None)
        
        # Record metrics
        duration_ms = (time.time() - start_time) * 1000
        self.metrics.record_decryption(len(plaintext), duration_ms)
        
        return plaintext
    
    def _encode_value(self, value: Any) -> bytes:
        """Encode value to bytes."""
        if isinstance(value, bytes):
            return value
        return json.dumps(value).encode('utf-8')
    
    def _decode_value(self, data: bytes) -> Any:
        """Decode bytes to value."""
        try:
            return json.loads(data.decode('utf-8'))
        except:
            return data
    
    def put(self, key: str, value: Any) -> bool:
        """
        Store encrypted value.
        
        Args:
            key: Plaintext key
            value: Value to encrypt and store
        
        Returns:
            True if successful
        """
        try:
            value_bytes = self._encode_value(value)
            encrypted = self._encrypt(value_bytes)
            self.db.put(key, encrypted)
            return True
        except Exception as e:
            logger.error(f"[EncryptedDB] Encryption failed: {e}")
            return False
    
    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve and decrypt value.
        
        Args:
            key: Plaintext key
        
        Returns:
            Decrypted value or None
        """
        try:
            encrypted = self.db.get(key)
            if encrypted is None:
                return None
            
            # Handle non-encrypted data (migration support)
            if isinstance(encrypted, bytes) and len(encrypted) > 0:
                if encrypted[0] != self.ENCRYPTION_VERSION:
                    # Assume unencrypted
                    return self._decode_value(encrypted)
            
            decrypted = self._decrypt(encrypted)
            return self._decode_value(decrypted)
        except Exception as e:
            logger.error(f"[EncryptedDB] Decryption failed: {e}")
            return None
    
    def delete(self, key: str) -> bool:
        """Delete key."""
        return self.db.delete(key)
    
    def rotate_key(self, new_key: Optional[bytes] = None,
                   new_passphrase: Optional[str] = None) -> bool:
        """
        Rotate encryption key and re-encrypt all data.
        
        Args:
            new_key: New encryption key (optional)
            new_passphrase: New passphrase (optional)
        
        Returns:
            True if successful
        """
        try:
            logger.info("[EncryptedDB] Starting key rotation...")
            start_time = time.time()
            
            # Generate new key
            if new_key:
                old_key, new_key = self.key_manager._master_key, new_key
                self.key_manager._master_key = new_key
                self.key_manager._key_id = hashlib.sha256(new_key).hexdigest()[:16]
            else:
                old_key, new_key = self.key_manager.rotate_key(new_passphrase)
            
            # Re-encrypt all data
            old_cipher = AESGCM(old_key)
            new_cipher = AESGCM(new_key)
            
            # Scan all keys
            all_keys = self.db.keys()
            rotated_count = 0
            
            for key in all_keys:
                try:
                    encrypted = self.db.get(key)
                    if encrypted is None:
                        continue
                    
                    # Parse header
                    version = encrypted[0]
                    if version != self.ENCRYPTION_VERSION:
                        continue  # Skip non-encrypted
                    
                    key_id_len = encrypted[1]
                    header_len = 2 + key_id_len + 12
                    
                    old_nonce = encrypted[2+key_id_len:header_len]
                    old_ciphertext = encrypted[header_len:]
                    
                    # Decrypt with old key
                    plaintext = old_cipher.decrypt(old_nonce, old_ciphertext, None)
                    
                    # Re-encrypt with new key
                    new_nonce = secrets.token_bytes(12)
                    new_ciphertext = new_cipher.encrypt(new_nonce, plaintext, None)
                    
                    # Build new header
                    new_key_id = self.key_manager.key_id.encode('utf-8')
                    new_header = struct.pack(
                        '!BB',
                        self.ENCRYPTION_VERSION,
                        len(new_key_id)
                    ) + new_key_id + new_nonce
                    
                    new_encrypted = new_header + new_ciphertext
                    self.db.put(key, new_encrypted)
                    rotated_count += 1
                    
                except Exception as e:
                    logger.error(f"[EncryptedDB] Failed to rotate key for {key}: {e}")
            
            # Update cipher
            self.cipher = new_cipher
            
            duration = time.time() - start_time
            self.metrics.record_key_rotation()
            
            logger.info(f"[EncryptedDB] Key rotation complete: {rotated_count} items in {duration:.2f}s")
            return True
            
        except Exception as e:
            logger.error(f"[EncryptedDB] Key rotation failed: {e}")
            return False
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get encryption metrics."""
        return self.metrics.to_dict()
    
    def close(self):
        """Close database."""
        self.db.close()
    
    # Delegate other methods to underlying database
    def __getattr__(self, name):
        """Delegate unknown methods to underlying database."""
        return getattr(self.db, name)


def create_encrypted_database(
    data_dir: str,
    encryption_key: Optional[str] = None,
    passphrase: Optional[str] = None,
    key_file: Optional[str] = None,
    server_id: int = 1
) -> EncryptedDatabase:
    """
    Factory function to create encrypted database.
    
    Args:
        data_dir: Database directory
        encryption_key: Hex-encoded encryption key
        passphrase: Passphrase for key derivation
        key_file: Path to key file
        server_id: Server ID
    
    Returns:
        EncryptedDatabase instance
    """
    return EncryptedDatabase(
        data_dir=data_dir,
        server_id=server_id,
        encryption_key=encryption_key,
        key_file=key_file,
        passphrase=passphrase
    )
