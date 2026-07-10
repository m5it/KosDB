"""
Enhanced Backup utilities with encryption and compression for LevelDB Socket Server
"""

import json
import gzip
import hashlib
import os
import struct
import secrets
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, Union, BinaryIO
from enum import Enum

# Try to import optional compression libraries
try:
    import lz4.frame
    LZ4_AVAILABLE = True
except ImportError:
    LZ4_AVAILABLE = False

try:
    import zstandard as zstd
    ZSTD_AVAILABLE = True
except ImportError:
    ZSTD_AVAILABLE = False

# Try to import cryptography
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

logger = logging.getLogger(__name__)


class CompressionType(Enum):
    """Supported compression algorithms."""
    GZIP = "gzip"
    LZ4 = "lz4"
    ZSTD = "zstd"
    NONE = "none"


class BackupIntegrityError(Exception):
    """Raised when backup integrity check fails."""
    pass


class BackupEncryptionError(Exception):
    """Raised when encryption/decryption fails."""
    pass


def calculate_checksum(data: bytes) -> str:
    """Calculate SHA-256 checksum of data."""
    return hashlib.sha256(data).hexdigest()


def derive_key(passphrase: str, salt: Optional[bytes] = None) -> Tuple[bytes, bytes]:
    """
    Derive encryption key from passphrase using PBKDF2.
    
    Args:
        passphrase: User passphrase
        salt: Optional salt (generated if None)
    
    Returns:
        Tuple of (derived_key, salt)
    """
    if not CRYPTO_AVAILABLE:
        raise ImportError("cryptography library required for encryption")
    
    if salt is None:
        salt = secrets.token_bytes(32)
    
    kdf = PBKDF2(
        algorithm=hashes.SHA256(),
        length=32,  # 256-bit key
        salt=salt,
        iterations=100000,
        backend=default_backend()
    )
    
    key = kdf.derive(passphrase.encode('utf-8'))
    return key, salt


def encrypt_data(plaintext: bytes, passphrase: str) -> bytes:
    """
    Encrypt data with AES-256-GCM.
    
    Format: salt(32) + nonce(12) + ciphertext + tag(16)
    """
    if not CRYPTO_AVAILABLE:
        raise BackupEncryptionError("cryptography library not available")
    
    key, salt = derive_key(passphrase)
    nonce = secrets.token_bytes(12)
    cipher = AESGCM(key)
    
    ciphertext = cipher.encrypt(nonce, plaintext, None)
    
    # Combine: salt + nonce + ciphertext
    return salt + nonce + ciphertext


def decrypt_data(ciphertext: bytes, passphrase: str) -> bytes:
    """
    Decrypt data encrypted with AES-256-GCM.
    """
    if not CRYPTO_AVAILABLE:
        raise BackupEncryptionError("cryptography library not available")
    
    if len(ciphertext) < 60:  # salt(32) + nonce(12) + minimum tag(16)
        raise BackupEncryptionError("Invalid encrypted data")
    
    salt = ciphertext[:32]
    encrypted_data = ciphertext[32:]
    
    key, _ = derive_key(passphrase, salt)
    cipher = AESGCM(key)
    
    try:
        return cipher.decrypt(encrypted_data[:12], encrypted_data[12:], None)
    except Exception as e:
        raise BackupEncryptionError(f"Decryption failed: {e}")


def compress_data(data: bytes, compression: CompressionType = CompressionType.GZIP,
                  level: int = 6) -> bytes:
    """
    Compress data using specified algorithm.
    
    Args:
        data: Data to compress
        compression: Compression algorithm
        level: Compression level (1-9 for gzip, 1-12 for others)
    
    Returns:
        Compressed data
    """
    if compression == CompressionType.NONE:
        return data
    
    if compression == CompressionType.GZIP:
        import io
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode='wb', compresslevel=level) as f:
            f.write(data)
        return buf.getvalue()
    
    elif compression == CompressionType.LZ4:
        if not LZ4_AVAILABLE:
            logger.warning("LZ4 not available, falling back to gzip")
            return compress_data(data, CompressionType.GZIP, level)
        return lz4.frame.compress(data, compression_level=level)
    
    elif compression == CompressionType.ZSTD:
        if not ZSTD_AVAILABLE:
            logger.warning("Zstd not available, falling back to gzip")
            return compress_data(data, CompressionType.GZIP, level)
        cctx = zstd.ZstdCompressor(level=level)
        return cctx.compress(data)
    
    else:
        return data


def decompress_data(data: bytes, compression: CompressionType = CompressionType.GZIP) -> bytes:
    """
    Decompress data using specified algorithm.
    """
    if compression == CompressionType.NONE:
        return data
    
    if compression == CompressionType.GZIP:
        import io
        buf = io.BytesIO(data)
        with gzip.GzipFile(fileobj=buf, mode='rb') as f:
            return f.read()
    
    elif compression == CompressionType.LZ4:
        if not LZ4_AVAILABLE:
            raise BackupIntegrityError("LZ4 not available for decompression")
        return lz4.frame.decompress(data)
    
    elif compression == CompressionType.ZSTD:
        if not ZSTD_AVAILABLE:
            raise BackupIntegrityError("Zstd not available for decompression")
        dctx = zstd.ZstdDecompressor()
        return dctx.decompress(data)
    
    else:
        return data


def detect_compression(data: bytes) -> CompressionType:
    """Detect compression type from data magic bytes."""
    if len(data) < 4:
        return CompressionType.NONE
    
    # Gzip magic: 1f 8b
    if data[:2] == b'\x1f\x8b':
        return CompressionType.GZIP
    
    # LZ4 magic: 04 22 4d 18
    if data[:4] == b'\x04\x22\x4d\x18':
        return CompressionType.LZ4
    
    # Zstd magic: 28 b5 2f fd
    if data[:4] == b'\x28\xb5\x2f\xfd':
        return CompressionType.ZSTD
    
    return CompressionType.NONE


def verify_backup_integrity(file_path: str, passphrase: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """
    Verify backup file integrity.
    
    Args:
        file_path: Path to backup file
        passphrase: Optional passphrase for encrypted backups
    
    Returns:
        Tuple of (success, error_message)
    """
    try:
        # Check file exists and is readable
        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}"
        
        if not os.access(file_path, os.R_OK):
            return False, f"File not readable: {file_path}"
        
        # Read raw file
        with open(file_path, 'rb') as f:
            raw_data = f.read()
        
        # Check for encryption marker (first byte 0xFF)
        is_encrypted = len(raw_data) > 0 and raw_data[0] == 0xFF
        
        if is_encrypted:
            if not passphrase:
                return False, "Backup is encrypted but no passphrase provided"
            if not CRYPTO_AVAILABLE:
                return False, "Encryption library not available"
            
            # Remove encryption marker and decrypt
            encrypted_data = raw_data[1:]
            try:
                decrypted = decrypt_data(encrypted_data, passphrase)
                raw_data = decrypted
            except BackupEncryptionError as e:
                return False, f"Decryption failed: {e}"
        
        # Detect and decompress
        compression = detect_compression(raw_data)
        try:
            decompressed = decompress_data(raw_data, compression)
        except Exception as e:
            return False, f"Decompression failed: {e}"
        
        # Parse JSON
        try:
            backup_data = json.loads(decompressed.decode('utf-8'))
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON: {e}"
        
        # Verify required fields
        if 'version' not in backup_data:
            return False, "Missing 'version' field"
        
        if 'tables' not in backup_data and 'table' not in backup_data:
            return False, "Missing 'tables' or 'table' field"
        
        # Verify checksum if present
        if 'checksum' in backup_data:
            stored_checksum = backup_data['checksum']
            verification_data = {k: v for k, v in backup_data.items() if k != 'checksum'}
            expected = calculate_checksum(json.dumps(verification_data, sort_keys=True).encode())
            if stored_checksum != expected:
                return False, "Checksum mismatch - file may be corrupted"
        
        # Verify table data integrity
        if 'tables' in backup_data:
            for table_name, table_info in backup_data['tables'].items():
                if 'schema' not in table_info:
                    return False, f"Table '{table_name}' missing schema"
                if 'rows' not in table_info:
                    return False, f"Table '{table_name}' missing rows"
        elif 'table' in backup_data:
            if 'schema' not in backup_data:
                return False, "Single table backup missing schema"
            if 'rows' not in backup_data:
                return False, "Single table backup missing rows"
        
        return True, None
        
    except Exception as e:
        return False, f"Integrity check failed: {e}"


def create_backup(db_name: str, tables_data: Dict[str, Any],
                  compression: CompressionType = CompressionType.GZIP,
                  compression_level: int = 6,
                  passphrase: Optional[str] = None) -> bytes:
    """
    Create backup with optional compression and encryption.
    
    Args:
        db_name: Database name
        tables_data: Table data to backup
        compression: Compression algorithm
        compression_level: Compression level
        passphrase: Optional passphrase for encryption
    
    Returns:
        Backup data as bytes
    """
    # Create backup structure
    backup_data = {
        'version': '2.0',
        'created_at': datetime.now().isoformat(),
        'database': db_name,
        'table_count': len(tables_data),
        'compression': compression.value,
        'encrypted': passphrase is not None,
        'tables': tables_data
    }
    
    # Calculate row count
    row_count = 0
    for table_info in tables_data.values():
        row_count += len(table_info.get('rows', []))
    backup_data['row_count'] = row_count
    
    # Add integrity checksum
    data_for_hash = {k: v for k, v in backup_data.items() if k != 'checksum'}
    backup_data['checksum'] = calculate_checksum(json.dumps(data_for_hash, sort_keys=True).encode())
    
    # Serialize to JSON
    json_data = json.dumps(backup_data, sort_keys=True).encode('utf-8')
    
    # Compress
    compressed = compress_data(json_data, compression, compression_level)
    
    # Encrypt if passphrase provided
    if passphrase:
        if not CRYPTO_AVAILABLE:
            raise BackupEncryptionError("cryptography library not available")
        encrypted = encrypt_data(compressed, passphrase)
        # Add encryption marker
        return b'\xff' + encrypted
    
    return compressed


def restore_backup(file_path: str, passphrase: Optional[str] = None) -> Dict[str, Any]:
    """
    Restore backup from file.
    
    Args:
        file_path: Path to backup file
        passphrase: Optional passphrase for encrypted backups
    
    Returns:
        Restored backup data
    """
    # Read file
    with open(file_path, 'rb') as f:
        raw_data = f.read()
    
    # Check for encryption
    is_encrypted = len(raw_data) > 0 and raw_data[0] == 0xFF
    
    if is_encrypted:
        if not passphrase:
            raise BackupEncryptionError("Backup is encrypted but no passphrase provided")
        if not CRYPTO_AVAILABLE:
            raise BackupEncryptionError("Encryption library not available")
        
        encrypted_data = raw_data[1:]
        raw_data = decrypt_data(encrypted_data, passphrase)
    
    # Detect and decompress
    compression = detect_compression(raw_data)
    decompressed = decompress_data(raw_data, compression)
    
    # Parse JSON
    backup_data = json.loads(decompressed.decode('utf-8'))
    
    # Verify checksum
    if 'checksum' in backup_data:
        stored_checksum = backup_data['checksum']
        verification_data = {k: v for k, v in backup_data.items() if k != 'checksum'}
        expected = calculate_checksum(json.dumps(verification_data, sort_keys=True).encode())
        if stored_checksum != expected:
            raise BackupIntegrityError("Checksum mismatch - backup may be corrupted")
    
    return backup_data


def create_backup_metadata(db_name: str, tables: list, rows_count: int,
                           compression: CompressionType = CompressionType.GZIP,
                           encrypted: bool = False) -> Dict[str, Any]:
    """Create metadata for backup file."""
    return {
        'version': '2.0',
        'created_at': datetime.now().isoformat(),
        'database': db_name,
        'table_count': len(tables),
        'row_count': rows_count,
        'tables': tables,
        'compression': compression.value,
        'encrypted': encrypted
    }


def add_integrity_check(backup_data: Dict[str, Any]) -> Dict[str, Any]:
    """Add checksum to backup data for integrity verification."""
    data_for_hash = {k: v for k, v in backup_data.items() if k != 'checksum'}
    data_bytes = json.dumps(data_for_hash, sort_keys=True).encode()
    backup_data['checksum'] = calculate_checksum(data_bytes)
    return backup_data


def validate_before_restore(file_path: str, target_db: str,
                           passphrase: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """
    Validate backup before restore.
    
    Returns:
        Tuple of (success, error_message)
    """
    valid, error = verify_backup_integrity(file_path, passphrase)
    if not valid:
        return False, error
    
    try:
        backup_data = restore_backup(file_path, passphrase)
        
        # Check if target database matches (warning only)
        source_db = backup_data.get('database')
        if source_db and source_db != target_db:
            logger.warning(f"Restoring from '{source_db}' to '{target_db}'")
        
        return True, None
        
    except Exception as e:
        return False, f"Validation failed: {e}"


def get_backup_info(file_path: str) -> Optional[Dict[str, Any]]:
    """Get information about a backup file."""
    try:
        stat = os.stat(file_path)
        
        # Read first few bytes to detect encryption and compression
        with open(file_path, 'rb') as f:
            header = f.read(100)
        
        is_encrypted = len(header) > 0 and header[0] == 0xFF
        compression = detect_compression(header[1:] if is_encrypted else header)
        
        info = {
            'file': os.path.basename(file_path),
            'path': file_path,
            'size': stat.st_size,
            'size_human': format_size(stat.st_size),
            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'encrypted': is_encrypted,
            'compression': compression.value
        }
        
        # Try to read metadata
        try:
            backup_data = restore_backup(file_path) if not is_encrypted else None
            if backup_data:
                info.update({
                    'version': backup_data.get('version', 'unknown'),
                    'database': backup_data.get('database', 'unknown'),
                    'table_count': backup_data.get('table_count', 0),
                    'row_count': backup_data.get('row_count', 0),
                    'has_checksum': 'checksum' in backup_data
                })
        except:
            pass
        
        return info
        
    except Exception:
        return None


def format_size(size_bytes: int) -> str:
    """Format byte size to human readable."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


class BackupManager:
    """Manage backup operations with integrity checking."""
    
    def __init__(self, backup_dir: str = './backups'):
        self.backup_dir = backup_dir
        os.makedirs(backup_dir, exist_ok=True)
    
    def create_backup(self, db_name: str, tables_data: Dict[str, Any],
                     compression: str = 'gzip',
                     compression_level: int = 6,
                     passphrase: Optional[str] = None) -> str:
        """
        Create backup and save to file.
        
        Returns:
            Path to backup file
        """
        comp_type = CompressionType(compression) if compression else CompressionType.GZIP
        
        backup_data = create_backup(
            db_name, tables_data,
            compression=comp_type,
            compression_level=compression_level,
            passphrase=passphrase
        )
        
        filename = generate_backup_filename(db_name, encrypted=passphrase is not None)
        file_path = os.path.join(self.backup_dir, filename)
        
        with open(file_path, 'wb') as f:
            f.write(backup_data)
        
        return file_path
    
    def restore_backup(self, filename: str, passphrase: Optional[str] = None) -> Dict[str, Any]:
        """Restore backup from file."""
        file_path = os.path.join(self.backup_dir, filename)
        return restore_backup(file_path, passphrase)
    
    def list_backups(self) -> list:
        """List all backup files with info."""
        backups = []
        for filename in os.listdir(self.backup_dir):
            if filename.endswith('.json.gz') or filename.endswith('.enc'):
                file_path = os.path.join(self.backup_dir, filename)
                info = get_backup_info(file_path)
                if info:
                    backups.append(info)
        return sorted(backups, key=lambda x: x['modified'], reverse=True)
    
    def cleanup_old_backups(self, keep_count: int = 10):
        """Remove old backups keeping only the most recent."""
        backups = self.list_backups()
        if len(backups) > keep_count:
            for backup in backups[keep_count:]:
                try:
                    os.remove(backup['path'])
                except:
                    pass


def generate_backup_filename(db_name: str, suffix: str = '',
                            encrypted: bool = False) -> str:
    """Generate standardized backup filename."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    ext = '.enc' if encrypted else '.json.gz'
    if suffix:
        return f"{db_name}_{suffix}_{timestamp}{ext}"
    return f"{db_name}_{timestamp}{ext}"


# Backward compatibility
__all__ = [
    'BackupIntegrityError',
    'BackupEncryptionError',
    'CompressionType',
    'BackupManager',
    'calculate_checksum',
    'verify_backup_integrity',
    'create_backup',
    'restore_backup',
    'create_backup_metadata',
    'add_integrity_check',
    'validate_before_restore',
    'get_backup_info',
    'format_size',
    'generate_backup_filename',
    'compress_data',
    'decompress_data',
    'encrypt_data',
    'decrypt_data'
]
