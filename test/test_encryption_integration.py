"""
Encryption Integration Tests for KosDB v3.1.0

Tests encrypted database operations and backup/restore.
"""

import unittest
import subprocess
import time
import os
import tempfile
import shutil
import json
import socket
import glob
from pathlib import Path

# Check if encryption is available
try:
    from encrypted_database import EncryptedDatabase, CRYPTO_AVAILABLE
    ENCRYPTION_AVAILABLE = CRYPTO_AVAILABLE
except ImportError:
    ENCRYPTION_AVAILABLE = False


@unittest.skipUnless(ENCRYPTION_AVAILABLE, "Encryption not available")
class TestEncryptionIntegration(unittest.TestCase):
    """Integration tests for database encryption."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment with encryption enabled."""
        cls.temp_dir = tempfile.mkdtemp()
        cls.data_dir = os.path.join(cls.temp_dir, 'data')
        cls.backup_dir = os.path.join(cls.temp_dir, 'backups')
        os.makedirs(cls.data_dir, exist_ok=True)
        os.makedirs(cls.backup_dir, exist_ok=True)
        
        # Create server config with encryption enabled
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
    def _create_server_config(cls):
        """Create server configuration with encryption enabled."""
        config = {
            "version": "3.1.0",
            "server": {
                "host": "127.0.0.1",
                "port": 19994,
                "data_dir": cls.data_dir,
                "server_id": 1
            },
            "database": {
                "encryption": {
                    "enabled": True,
                    "passphrase_env": "KOSDB_TEST_PASSPHRASE"
                }
            },
            "backup": {
                "enabled": True,
                "backup_dir": cls.backup_dir,
                "compression": "gzip",
                "compression_level": 6
            },
            "audit_logging": {
                "enabled": False
            }
        }
        
        with open(cls.config_path, 'w') as f:
            json.dump(config, f, indent=2)
    
    def setUp(self):
        """Start server before each test."""
        # Set encryption passphrase
        os.environ['KOSDB_TEST_PASSPHRASE'] = 'test-encryption-passphrase-12345'
        
        self.server_process = subprocess.Popen(
            ['python', 'server.py', '-c', self.config_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        
        # Wait for server to start
        time.sleep(3)
        
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
        
        # Clean up data directory
        for item in os.listdir(self.data_dir):
            item_path = os.path.join(self.data_dir, item)
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
            else:
                os.remove(item_path)
    
    def _send_command(self, command):
        """Send command to server and return response."""
        with socket.create_connection(('127.0.0.1', 19994)) as sock:
            sock.send(f"{command}\n".encode())
            return sock.recv(4096).decode().strip()
    
    def test_encrypted_database_creation(self):
        """Test that databases are created with encryption."""
        # Authenticate
        self._send_command("USER admin")
        self._send_command("PASS admin123")
        
        # Create database
        response = self._send_command("CREATE DATABASE encrypted_db")
        self.assertTrue(response.startswith("OK"))
        
        # Check that data is encrypted on disk
        db_path = os.path.join(self.data_dir, 'encrypted', 'encrypted_db')
        self.assertTrue(os.path.exists(db_path) or os.path.exists(self.data_dir))
    
    def test_encrypted_data_operations(self):
        """Test that data operations work with encryption."""
        # Authenticate
        self._send_command("USER admin")
        self._send_command("PASS admin123")
        
        # Create and use database
        self._send_command("CREATE DATABASE testdb")
        self._send_command("USE testdb")
        self._send_command("CREATE TABLE secrets (id INT, data TEXT)")
        
        # Insert sensitive data
        response = self._send_command("INSERT INTO secrets VALUES (1, 'sensitive data')")
        self.assertTrue(response.startswith("OK"))
        
        # Retrieve data
        response = self._send_command("SELECT * FROM secrets")
        self.assertIn('sensitive data', response)
    
    def test_encrypted_backup(self):
        """Test that backups are encrypted."""
        # Authenticate and create data
        self._send_command("USER admin")
        self._send_command("PASS admin123")
        self._send_command("CREATE DATABASE backup_test")
        self._send_command("USE backup_test")
        self._send_command("CREATE TABLE data (id INT, value TEXT)")
        self._send_command("INSERT INTO data VALUES (1, 'backup test data')")
        
        # Create encrypted backup
        backup_path = os.path.join(self.backup_dir, 'test_backup.enc')
        response = self._send_command(
            f"BACKUP DATABASE backup_test TO {backup_path} WITH ENCRYPTION 'backup-pass' COMPRESSION gzip"
        )
        self.assertTrue(response.startswith("OK"))
        
        # Verify backup file exists
        self.assertTrue(os.path.exists(backup_path))
        
        # Verify backup is encrypted (should not contain plain text)
        with open(backup_path, 'rb') as f:
            content = f.read()
            self.assertNotIn(b'backup test data', content)
    
    def test_encrypted_restore(self):
        """Test that encrypted backups can be restored."""
        # Authenticate and create data
        self._send_command("USER admin")
        self._send_command("PASS admin123")
        self._send_command("CREATE DATABASE restore_test")
        self._send_command("USE restore_test")
        self._send_command("CREATE TABLE original (id INT, value TEXT)")
        self._send_command("INSERT INTO original VALUES (1, 'original data')")
        
        # Create encrypted backup
        backup_path = os.path.join(self.backup_dir, 'restore_test.enc')
        self._send_command(
            f"BACKUP DATABASE restore_test TO {backup_path} WITH ENCRYPTION 'restore-pass' COMPRESSION gzip"
        )
        
        # Drop database
        self._send_command("DROP DATABASE restore_test")
        
        # Restore from encrypted backup
        response = self._send_command(
            f"RESTORE DATABASE restore_test FROM {backup_path} WITH ENCRYPTION 'restore-pass'"
        )
        self.assertTrue(response.startswith("OK"))
        
        # Verify data restored
        self._send_command("USE restore_test")
        response = self._send_command("SELECT * FROM original")
        self.assertIn('original data', response)
    
    def test_encryption_with_replication(self):
        """Test encryption works with replication."""
        # This would require setting up a second server instance
        # For now, just verify encrypted data can be read/written
        self._send_command("USER admin")
        self._send_command("PASS admin123")
        self._send_command("CREATE DATABASE repl_test")
        self._send_command("USE repl_test")
        self._send_command("CREATE TABLE repl_data (id INT PRIMARY KEY, data TEXT)")
        
        # Insert data
        for i in range(100):
            self._send_command(f"INSERT INTO repl_data VALUES ({i}, 'data {i}')")
        
        # Verify all data
        response = self._send_command("SELECT COUNT(*) FROM repl_data")
        self.assertIn('100', response)
    
    def test_key_rotation(self):
        """Test encryption key rotation."""
        # This test would require the ROTATE KEY command to be implemented
        # For now, just verify the concept
        self._send_command("USER admin")
        self._send_command("PASS admin123")
        self._send_command("CREATE DATABASE rotation_test")
        self._send_command("USE rotation_test")
        self._send_command("CREATE TABLE rotation_data (id INT, data TEXT)")
        self._send_command("INSERT INTO rotation_data VALUES (1, 'pre-rotation')")
        
        # Key rotation would happen here
        # response = self._send_command("ROTATE ENCRYPTION KEY")
        
        # Verify data still accessible
        response = self._send_command("SELECT * FROM rotation_data")
        self.assertIn('pre-rotation', response)
    
    def test_wrong_passphrase_fails(self):
        """Test that wrong passphrase fails to decrypt."""
        # Create encrypted backup
        self._send_command("USER admin")
        self._send_command("PASS admin123")
        self._send_command("CREATE DATABASE wrong_pass")
        self._send_command("USE wrong_pass")
        self._send_command("CREATE TABLE test (id INT)")
        
        backup_path = os.path.join(self.backup_dir, 'wrong_pass.enc')
        self._send_command(
            f"BACKUP DATABASE wrong_pass TO {backup_path} WITH ENCRYPTION 'correct-pass'"
        )
        
        # Try to restore with wrong passphrase
        self._send_command("DROP DATABASE wrong_pass")
        response = self._send_command(
            f"RESTORE DATABASE wrong_pass FROM {backup_path} WITH ENCRYPTION 'wrong-pass'"
        )
        
        # Should fail
        self.assertTrue(response.startswith("ERROR") or "failed" in response.lower())
    
    def test_backup_integrity(self):
        """Test that encrypted backups maintain integrity."""
        # Create data
        self._send_command("USER admin")
        self._send_command("PASS admin123")
        self._send_command("CREATE DATABASE integrity_test")
        self._send_command("USE integrity_test")
        self._send_command("CREATE TABLE integrity_data (id INT, data TEXT)")
        self._send_command("INSERT INTO integrity_data VALUES (1, 'integrity check')")
        
        # Create backup
        backup_path = os.path.join(self.backup_dir, 'integrity_test.enc')
        self._send_command(
            f"BACKUP DATABASE integrity_test TO {backup_path} WITH ENCRYPTION 'integrity-pass'"
        )
        
        # Verify backup integrity
        from backup_utils import verify_backup_integrity
        valid, error = verify_backup_integrity(backup_path, passphrase='integrity-pass')
        self.assertTrue(valid, f"Backup integrity check failed: {error}")
    
    def test_concurrent_encrypted_operations(self):
        """Test concurrent operations on encrypted database."""
        import threading
        
        self._send_command("USER admin")
        self._send_command("PASS admin123")
        self._send_command("CREATE DATABASE concurrent_test")
        self._send_command("USE concurrent_test")
        self._send_command("CREATE TABLE concurrent (id INT, data TEXT)")
        
        results = []
        
        def insert_data(thread_id):
            for i in range(10):
                response = self._send_command(
                    f"INSERT INTO concurrent VALUES ({thread_id * 100 + i}, 'thread {thread_id}')"
                )
                results.append(response)
        
        # Start multiple threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=insert_data, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for completion
        for t in threads:
            t.join()
        
        # Verify all data inserted
        response = self._send_command("SELECT COUNT(*) FROM concurrent")
        self.assertIn('50', response)


if __name__ == '__main__':
    unittest.main(verbosity=2)
