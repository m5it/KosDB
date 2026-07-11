"""
Unit tests for Encrypted Database module.

Tests AES-256-GCM encryption, key derivation, and key rotation.
"""

import unittest
import tempfile
import os
import json
import time
from pathlib import Path

from encrypted_database import (
    EncryptedDatabase,
    KeyManager,
    EncryptionMetrics,
    create_encrypted_database,
    CRYPTO_AVAILABLE
)


@unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography library not available")
class TestKeyManager(unittest.TestCase):
    """Test KeyManager class."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.key_file = os.path.join(self.temp_dir, 'test.key')
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_generate_key(self):
        """Test key generation."""
        km = KeyManager()
        key = km.generate_key()
        self.assertEqual(len(key), 32)  # 256 bits
    
    def test_derive_key(self):
        """Test key derivation from passphrase."""
        km = KeyManager()
        key1, salt1 = km.derive_key("password123")
        key2, salt2 = km.derive_key("password123", salt1)
        
        self.assertEqual(len(key1), 32)
        self.assertEqual(key1, key2)  # Same password + salt = same key
    
    def test_key_file_roundtrip(self):
        """Test saving and loading key file."""
        km1 = KeyManager(self.key_file)
        key1 = km1.load_or_create_key("mypassphrase")
        
        km2 = KeyManager(self.key_file)
        key2 = km2.load_or_create_key("mypassphrase")
        
        self.assertEqual(key1, key2)
    
    def test_key_rotation(self):
        """Test key rotation."""
        km = KeyManager()
        km._master_key = km.generate_key()
        km._key_id = "test"
        
        old_key, new_key = km.rotate_key()
        self.assertNotEqual(old_key, new_key)
        self.assertEqual(km.master_key, new_key)


@unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography library not available")
class TestEncryptionMetrics(unittest.TestCase):
    """Test EncryptionMetrics class."""
    
    def test_record_encryption(self):
        """Test recording encryption metrics."""
        metrics = EncryptionMetrics()
        metrics.record_encryption(1000, 5.5)
        
        self.assertEqual(metrics.total_encryptions, 1)
        self.assertEqual(metrics.total_bytes_encrypted, 1000)
        self.assertEqual(metrics.encryption_time_ms, 5.5)
    
    def test_overhead_ratio(self):
        """Test overhead calculation."""
        metrics = EncryptionMetrics()
        metrics.record_encryption(1000, 1.0)
        
        # 28 bytes overhead per encryption
        ratio = metrics.get_overhead_ratio()
        self.assertGreater(ratio, 0)
        self.assertLess(ratio, 0.1)  # Should be small for 1000 bytes
    
    def test_to_dict(self):
        """Test metrics export."""
        metrics = EncryptionMetrics()
        metrics.record_encryption(100, 1.0)
        metrics.record_decryption(100, 2.0)
        
        data = metrics.to_dict()
        self.assertEqual(data['total_encryptions'], 1)
        self.assertEqual(data['total_decryptions'], 1)


@unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography library not available")
class TestEncryptedDatabase(unittest.TestCase):
    """Test EncryptedDatabase class."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_encrypt_decrypt(self):
        """Test basic encryption and decryption."""
        db = EncryptedDatabase(
            self.temp_dir,
            passphrase="testpassphrase"
        )
        
        plaintext = b"Hello, World!"
        encrypted = db._encrypt(plaintext)
        decrypted = db._decrypt(encrypted)
        
        self.assertEqual(plaintext, decrypted)
        self.assertNotEqual(plaintext, encrypted)
        
        db.close()
    
    def test_put_get_string(self):
        """Test storing and retrieving string."""
        db = EncryptedDatabase(
            self.temp_dir,
            passphrase="testpassphrase"
        )
        
        db.put("key1", "value1")
        result = db.get("key1")
        
        self.assertEqual(result, "value1")
        db.close()
    
    def test_put_get_dict(self):
        """Test storing and retrieving dictionary."""
        db = EncryptedDatabase(
            self.temp_dir,
            passphrase="testpassphrase"
        )
        
        data = {"name": "Alice", "age": 30}
        db.put("user1", data)
        result = db.get("user1")
        
        self.assertEqual(result, data)
        db.close()
    
    def test_delete(self):
        """Test delete operation."""
        db = EncryptedDatabase(
            self.temp_dir,
            passphrase="testpassphrase"
        )
        
        db.put("key1", "value1")
        db.delete("key1")
        result = db.get("key1")
        
        self.assertIsNone(result)
        db.close()
    
    def test_get_metrics(self):
        """Test metrics collection."""
        db = EncryptedDatabase(
            self.temp_dir,
            passphrase="testpassphrase"
        )
        
        db.put("key1", "value1")
        db.get("key1")
        
        metrics = db.get_metrics()
        self.assertEqual(metrics['total_encryptions'], 1)
        self.assertEqual(metrics['total_decryptions'], 1)
        
        db.close()
    
    def test_with_hex_key(self):
        """Test with hex-encoded key."""
        import secrets
        key = secrets.token_hex(32)
        
        db = EncryptedDatabase(
            self.temp_dir,
            encryption_key=key
        )
        
        db.put("key1", "value1")
        result = db.get("key1")
        
        self.assertEqual(result, "value1")
        db.close()


@unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography library not available")
class TestKeyRotation(unittest.TestCase):
    """Test key rotation functionality."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_key_rotation(self):
        """Test rotating encryption key."""
        db = EncryptedDatabase(
            self.temp_dir,
            passphrase="oldpassphrase"
        )
        
        # Store some data
        db.put("key1", "value1")
        db.put("key2", "value2")
        
        # Rotate key
        result = db.rotate_key(new_passphrase="newpassphrase")
        self.assertTrue(result)
        
        # Verify data still accessible
        self.assertEqual(db.get("key1"), "value1")
        self.assertEqual(db.get("key2"), "value2")
        
        # Check metrics
        metrics = db.get_metrics()
        self.assertEqual(metrics['key_rotations'], 1)
        
        db.close()


@unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography library not available")
class TestFactoryFunction(unittest.TestCase):
    """Test factory function."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_create_with_passphrase(self):
        """Test factory with passphrase."""
        db = create_encrypted_database(
            self.temp_dir,
            passphrase="mypassphrase"
        )
        
        db.put("key1", "value1")
        self.assertEqual(db.get("key1"), "value1")
        db.close()


@unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography library not available")
class TestCoexistence(unittest.TestCase):
    """Test encrypted and non-encrypted databases coexist."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.encrypted_dir = os.path.join(self.temp_dir, 'encrypted')
        self.regular_dir = os.path.join(self.temp_dir, 'regular')
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_coexistence(self):
        """Test that encrypted and regular DB can coexist."""
        from database import Database
        
        # Create encrypted database
        enc_db = EncryptedDatabase(
            self.encrypted_dir,
            passphrase="testpass"
        )
        enc_db.put("key1", "encrypted_value")
        
        # Create regular database
        reg_db = Database(self.regular_dir)
        reg_db.put("key1", b"regular_value")
        
        # Verify both work
        self.assertEqual(enc_db.get("key1"), "encrypted_value")
        self.assertEqual(reg_db.get("key1"), b"regular_value")
        
        enc_db.close()
        reg_db.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
