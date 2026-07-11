#!/usr/bin/env python3
"""
Integration tests for LevelDB Socket Server
"""

import unittest
import tempfile
import os
import sys
import json
import threading
import time
import socket

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import Database
from parser import BackupRestoreParser
from commands import CommandRegistry


class TestDatabaseOperations(unittest.TestCase):
    """Test basic database operations."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db = Database(self.temp_dir)
        self.db.create_database("test_db")
        self.db.use_database("test_db")
    
    def tearDown(self):
        self.db.close()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_create_table(self):
        """Test table creation."""
        self.db.create_table("users", ["id", "name", "email"])
        tables = self.db.list_tables()
        self.assertIn("users", tables)
    
    def test_insert_and_select(self):
        """Test insert and select operations."""
        self.db.create_table("users", ["id", "name"])
        self.db.insert("users", [1, "Alice"])
        
        result = self.db.select("users", ["*"])
        self.assertIn("Alice", result)
    
    def test_transaction_commit(self):
        """Test transaction commit."""
        self.db.create_table("users", ["id", "name"])
        
        self.db.begin_transaction()
        self.db.insert("users", [1, "Alice"])
        result = self.db.commit_transaction()
        
        self.assertIn("committed", result.lower())
        
        data = self.db.select("users", ["*"])
        self.assertIn("Alice", data)
    
    def test_transaction_rollback(self):
        """Test transaction rollback."""
        self.db.create_table("users", ["id", "name"])
        
        self.db.begin_transaction()
        self.db.insert("users", [1, "Bob"])
        self.db.rollback_transaction()
        
        data = self.db.select("users", ["*"])
        self.assertNotIn("Bob", data)


class TestParser(unittest.TestCase):
    """Test command parser."""
    
    def setUp(self):
        self.parser = BackupRestoreParser()
    
    def test_parse_create_table(self):
        """Test CREATE TABLE parsing."""
        cmd_type, params = self.parser.parse("CREATE TABLE users (id, name)")
        self.assertEqual(cmd_type, "CREATE")
        self.assertEqual(params["table"], "users")
        self.assertEqual(params["columns"], ["id", "name"])
    
    def test_parse_insert(self):
        """Test INSERT parsing."""
        cmd_type, params = self.parser.parse("INSERT INTO users VALUES (1, 'Alice')")
        self.assertEqual(cmd_type, "INSERT")
        self.assertEqual(params["table"], "users")
    
    def test_parse_select(self):
        """Test SELECT parsing."""
        cmd_type, params = self.parser.parse("SELECT * FROM users WHERE id=1")
        self.assertEqual(cmd_type, "SELECT")
        self.assertEqual(params["table"], "users")
    
    def test_parse_backup(self):
        """Test BACKUP parsing."""
        cmd_type, params = self.parser.parse("BACKUP DATABASE test TO backup.json.gz")
        self.assertEqual(cmd_type, "BACKUP_DB")
        self.assertEqual(params["database"], "test")
    
    def test_parse_transaction(self):
        """Test transaction commands."""
        cmd_type, _ = self.parser.parse("BEGIN")
        self.assertEqual(cmd_type, "BEGIN")
        
        cmd_type, _ = self.parser.parse("COMMIT")
        self.assertEqual(cmd_type, "COMMIT")


class TestCommands(unittest.TestCase):
    """Test command execution."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db = Database(self.temp_dir)
        self.registry = CommandRegistry(self.db)
        self.client_state = {
            'is_admin': True,
            'current_db': None,
            'username': 'test'
        }
    
    def tearDown(self):
        self.db.close()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_create_database(self):
        """Test CREATE DATABASE command."""
        result = self.registry.execute('CREATE_DB', 
                                       {'database': 'test_db'}, 
                                       self.client_state)
        self.assertIn("created", result)
    
    def test_show_databases(self):
        """Test SHOW DATABASES command."""
        self.db.create_database("db1")
        self.db.create_database("db2")
        
        result = self.registry.execute('SHOW_DATABASES', {}, self.client_state)
        self.assertIn("db1", result)
        self.assertIn("db2", result)


class TestBackupRestore(unittest.TestCase):
    """Test backup and restore functionality."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.backup_dir = tempfile.mkdtemp()
        self.db = Database(self.temp_dir)
        self.db.create_database("test_db")
        self.db.use_database("test_db")
        self.registry = CommandRegistry(self.db)
        self.client_state = {
            'is_admin': True,
            'current_db': 'test_db',
            'username': 'test'
        }
    
    def tearDown(self):
        self.db.close()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        shutil.rmtree(self.backup_dir, ignore_errors=True)
    
    def test_backup_and_restore(self):
        """Test full backup and restore cycle."""
        # Create table and insert data
        self.db.create_table("users", ["id", "name"])
        self.db.insert("users", [1, "Alice"])
        self.db.insert("users", [2, "Bob"])
        
        # Backup
        backup_file = os.path.join(self.backup_dir, "test_backup.json.gz")
        result = self.registry.execute('BACKUP_DB', 
                                       {'database': 'test_db', 'file': backup_file}, 
                                       self.client_state)
        self.assertIn("Backup complete", result)
        
        # Verify backup file exists
        self.assertTrue(os.path.exists(backup_file))
        
        # Restore to new database
        result = self.registry.execute('RESTORE_DB',
                                       {'database': 'restored_db', 'file': backup_file},
                                       self.client_state)
        self.assertIn("Restored", result)
        
        # Verify data in restored database
        self.db.use_database("restored_db")
        data = self.db.select("users", ["*"])
        self.assertIn("Alice", data)
        self.assertIn("Bob", data)


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestDatabaseOperations))
    suite.addTests(loader.loadTestsFromTestCase(TestParser))
    suite.addTests(loader.loadTestsFromTestCase(TestCommands))
    suite.addTests(loader.loadTestsFromTestCase(TestBackupRestore))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
