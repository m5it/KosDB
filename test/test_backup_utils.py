"""
Unit tests for Backup utilities with encryption and compression.
"""

import unittest
import tempfile
import os
import json
import gzip

from backup_utils import (
    BackupManager,
    CompressionType,
    calculate_checksum,
    compress_data,
    decompress_data,
    verify_backup_integrity,
    create_backup,
    restore_backup,
    get_backup_info,
    format_size,
    generate_backup_filename,
    detect_compression,
    CRYPTO_AVAILABLE
)


class TestChecksum(unittest.TestCase):
    """Test checksum calculation."""
    
    def test_calculate_checksum(self):
        """Test SHA-256 checksum."""
        data = b"test data"
        checksum = calculate_checksum(data)
        self.assertEqual(len(checksum), 64)  # SHA-256 hex string
        self.assertNotEqual(checksum, calculate_checksum(b"different data"))


class TestCompression(unittest.TestCase):
    """Test compression functions."""
    
    def test_gzip_compression(self):
        """Test gzip compression roundtrip."""
        original = b"Hello, World!" * 100
        compressed = compress_data(original, CompressionType.GZIP)
        decompressed = decompress_data(compressed, CompressionType.GZIP)
        
        self.assertEqual(original, decompressed)
        self.assertLess(len(compressed), len(original))
    
    def test_no_compression(self):
        """Test no compression."""
        original = b"test data"
        compressed = compress_data(original, CompressionType.NONE)
        self.assertEqual(original, compressed)
    
    def test_detect_compression(self):
        """Test compression detection."""
        gzip_data = compress_data(b"test", CompressionType.GZIP)
        self.assertEqual(detect_compression(gzip_data), CompressionType.GZIP)
        
        self.assertEqual(detect_compression(b"plain text"), CompressionType.NONE)


class TestBackupCreation(unittest.TestCase):
    """Test backup creation."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_create_backup_unencrypted(self):
        """Test creating unencrypted backup."""
        tables_data = {
            'users': {
                'schema': ['id INT', 'name TEXT'],
                'rows': [[1, 'Alice'], [2, 'Bob']]
            }
        }
        
        backup = create_backup(
            db_name='testdb',
            tables_data=tables_data,
            compression=CompressionType.GZIP
        )
        
        # Should be compressed data
        self.assertIsInstance(backup, bytes)
        self.assertGreater(len(backup), 0)
    
    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography not available")
    def test_create_backup_with_encryption(self):
        """Test creating encrypted backup."""
        tables_data = {
            'users': {
                'schema': ['id INT', 'name TEXT'],
                'rows': [[1, 'Alice']]
            }
        }
        
        backup = create_backup(
            db_name='testdb',
            tables_data=tables_data,
            passphrase='secret123'
        )
        
        # Should have encryption marker
        self.assertEqual(backup[0], 0xFF)
        self.assertGreater(len(backup), 100)  # Encrypted data + overhead
    
    def test_backup_integrity(self):
        """Test backup integrity verification."""
        tables_data = {
            'users': {
                'schema': ['id INT', 'name TEXT'],
                'rows': [[1, 'Alice'], [2, 'Bob']]
            }
        }
        
        backup = create_backup(
            db_name='testdb',
            tables_data=tables_data,
            compression=CompressionType.GZIP
        )
        
        # Save to file
        backup_path = os.path.join(self.temp_dir, 'test_backup.json.gz')
        with open(backup_path, 'wb') as f:
            f.write(backup)
        
        # Verify integrity
        valid, error = verify_backup_integrity(backup_path)
        self.assertTrue(valid, f"Integrity check failed: {error}")
        self.assertIsNone(error)
    
    def test_restore_backup(self):
        """Test backup restoration."""
        tables_data = {
            'users': {
                'schema': ['id INT', 'name TEXT'],
                'rows': [[1, 'Alice'], [2, 'Bob']]
            },
            'orders': {
                'schema': ['id INT', 'user_id INT', 'amount FLOAT'],
                'rows': [[1, 1, 100.50]]
            }
        }
        
        backup = create_backup(
            db_name='testdb',
            tables_data=tables_data,
            compression=CompressionType.GZIP
        )
        
        backup_path = os.path.join(self.temp_dir, 'test_backup.json.gz')
        with open(backup_path, 'wb') as f:
            f.write(backup)
        
        restored = restore_backup(backup_path)
        
        self.assertEqual(restored['database'], 'testdb')
        self.assertEqual(len(restored['tables']), 2)
        self.assertIn('users', restored['tables'])
        self.assertIn('orders', restored['tables'])
    
    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography not available")
    def test_encrypted_backup_restore(self):
        """Test encrypted backup and restore."""
        tables_data = {
            'sensitive': {
                'schema': ['id INT', 'ssn TEXT'],
                'rows': [[1, '123-45-6789']]
            }
        }
        
        passphrase = 'my_secret_key'
        
        backup = create_backup(
            db_name='secretdb',
            tables_data=tables_data,
            passphrase=passphrase
        )
        
        backup_path = os.path.join(self.temp_dir, 'encrypted_backup.enc')
        with open(backup_path, 'wb') as f:
            f.write(backup)
        
        # Verify with passphrase
        valid, error = verify_backup_integrity(backup_path, passphrase)
        self.assertTrue(valid)
        
        # Restore with passphrase
        restored = restore_backup(backup_path, passphrase)
        self.assertEqual(restored['database'], 'secretdb')
        self.assertTrue(restored['encrypted'])
    
    def test_get_backup_info(self):
        """Test getting backup info."""
        tables_data = {
            'test': {
                'schema': ['id INT'],
                'rows': [[1], [2], [3]]
            }
        }
        
        backup = create_backup(
            db_name='infodb',
            tables_data=tables_data,
            compression=CompressionType.GZIP
        )
        
        backup_path = os.path.join(self.temp_dir, 'info_backup.json.gz')
        with open(backup_path, 'wb') as f:
            f.write(backup)
        
        info = get_backup_info(backup_path)
        
        self.assertIsNotNone(info)
        self.assertEqual(info['database'], 'infodb')
        self.assertEqual(info['table_count'], 1)
        self.assertFalse(info['encrypted'])
        self.assertIn('size_human', info)


class TestBackupManager(unittest.TestCase):
    """Test BackupManager class."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.manager = BackupManager(self.temp_dir)
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_create_and_restore(self):
        """Test full create and restore cycle."""
        tables_data = {
            'users': {
                'schema': ['id INT', 'name TEXT'],
                'rows': [[1, 'Alice']]
            }
        }
        
        # Create backup
        backup_path = self.manager.create_backup(
            'mydb',
            tables_data,
            compression='gzip'
        )
        
        self.assertTrue(os.path.exists(backup_path))
        
        # Restore
        restored = self.manager.restore_backup(os.path.basename(backup_path))
        self.assertEqual(restored['database'], 'mydb')
    
    def test_list_backups(self):
        """Test listing backups."""
        tables_data = {'test': {'schema': ['id INT'], 'rows': []}}
        
        # Create multiple backups
        self.manager.create_backup('db1', tables_data)
        self.manager.create_backup('db2', tables_data)
        
        backups = self.manager.list_backups()
        self.assertEqual(len(backups), 2)
    
    def test_cleanup_old_backups(self):
        """Test cleanup of old backups."""
        tables_data = {'test': {'schema': ['id INT'], 'rows': []}}
        
        # Create 5 backups
        for i in range(5):
            self.manager.create_backup('testdb', tables_data)
        
        # Cleanup to keep only 2
        self.manager.cleanup_old_backups(keep_count=2)
        
        backups = self.manager.list_backups()
        self.assertEqual(len(backups), 2)


class TestFormatSize(unittest.TestCase):
    """Test size formatting."""
    
    def test_bytes(self):
        self.assertEqual(format_size(500), "500 B")
    
    def test_kilobytes(self):
        self.assertEqual(format_size(1024), "1.0 KB")
        self.assertEqual(format_size(1536), "1.5 KB")
    
    def test_megabytes(self):
        self.assertEqual(format_size(1024 * 1024), "1.0 MB")
    
    def test_gigabytes(self):
        self.assertEqual(format_size(1024 * 1024 * 1024), "1.0 GB")


class TestGenerateFilename(unittest.TestCase):
    """Test filename generation."""
    
    def test_unencrypted(self):
        filename = generate_backup_filename('mydb', encrypted=False)
        self.assertTrue(filename.startswith('mydb_'))
        self.assertTrue(filename.endswith('.json.gz'))
    
    def test_encrypted(self):
        filename = generate_backup_filename('mydb', encrypted=True)
        self.assertTrue(filename.endswith('.enc'))
    
    def test_with_suffix(self):
        filename = generate_backup_filename('mydb', suffix='weekly', encrypted=False)
        self.assertIn('weekly', filename)


class TestCompressionLevels(unittest.TestCase):
    """Test different compression levels."""
    
    def test_gzip_levels(self):
        """Test gzip compression at different levels."""
        data = b"Test data for compression " * 100
        
        compressed_1 = compress_data(data, CompressionType.GZIP, level=1)
        compressed_9 = compress_data(data, CompressionType.GZIP, level=9)
        
        # Level 9 should produce smaller or equal output
        self.assertLessEqual(len(compressed_9), len(compressed_1))
        
        # Both should decompress to original
        self.assertEqual(decompress_data(compressed_1, CompressionType.GZIP), data)
        self.assertEqual(decompress_data(compressed_9, CompressionType.GZIP), data)


class TestBackwardCompatibility(unittest.TestCase):
    """Test backward compatibility with old backups."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_old_unencrypted_backup(self):
        """Test reading old-style unencrypted backup."""
        # Create old-style backup (just gzip compressed JSON)
        old_backup = {
            'version': '1.0',
            'database': 'olddb',
            'tables': {
                'users': {
                    'schema': ['id INT'],
                    'rows': [[1], [2]]
                }
            }
        }
        
        backup_path = os.path.join(self.temp_dir, 'old_backup.json.gz')
        with gzip.open(backup_path, 'wt') as f:
            json.dump(old_backup, f)
        
        # Should be able to verify and restore
        valid, error = verify_backup_integrity(backup_path)
        self.assertTrue(valid, f"Failed to verify old backup: {error}")
        
        restored = restore_backup(backup_path)
        self.assertEqual(restored['version'], '1.0')
        self.assertEqual(restored['database'], 'olddb')


if __name__ == '__main__':
    unittest.main(verbosity=2)
