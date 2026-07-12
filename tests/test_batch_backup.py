
"""
Tests for Batch Backup/Restore Operations
"""

import unittest
import sys
import os
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from batch_backup import (
    BatchBackupManager,
    BackupOperationResult,
    BatchBackupResult,
    BackupStatus,
    parse_backup_command,
    parse_backup_if_command,
    parse_restore_command,
    parse_verify_command,
    parse_backup_chain,
    get_batch_backup_manager
)


class TestBatchBackupManager(unittest.TestCase):
    """Test batch backup manager."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.manager = BatchBackupManager(self.temp_dir)
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_execute_backup(self):
        """Test backup execution."""
        result = self.manager.execute_backup(
            source_db='test_db',
            target_file='test_backup.json.gz'
        )
        
        self.assertIsInstance(result, BackupOperationResult)
        self.assertEqual(result.operation, 'backup')
        self.assertEqual(result.status, BackupStatus.COMPLETED)
        self.assertIsNotNone(result.file_path)
        self.assertTrue(os.path.exists(result.file_path))

    def test_execute_restore(self):
        """Test restore execution."""
        # First create a backup
        backup_result = self.manager.execute_backup(
            source_db='test_db',
            target_file='test_backup.json.gz'
        )
        
        # Then restore it using full path
        result = self.manager.execute_restore(
            source_file=backup_result.file_path,
            target_db='test_db',
            verify=False
        )
        
        self.assertEqual(result.operation, 'restore')
        self.assertEqual(result.status, BackupStatus.COMPLETED)
    
    def test_execute_verify(self):
        """Test verification execution."""
        # Create a backup first
        backup_result = self.manager.execute_backup(
            source_db='test_db',
            target_file='test_verify.json.gz'
        )
        
        self.assertEqual(backup_result.status, BackupStatus.COMPLETED)
        
        # Verify it using the returned file path
        result = self.manager.execute_verify(
            file_path=backup_result.file_path
        )
        
        # Check that verification was attempted
        self.assertEqual(result.operation, 'verify')
        self.assertIsNotNone(result.status)
    
    def test_execute_chain(self):
        """Test chain execution."""
        # First create a backup
        backup_result = self.manager.execute_backup(
            source_db='db1',
            target_file='backup1.json.gz'
        )
        
        self.assertEqual(backup_result.status, BackupStatus.COMPLETED)
        
        operations = [
            {'type': 'backup', 'source_db': 'db1', 'target_file': 'backup2.json.gz'},
            {'type': 'verify', 'file_path': backup_result.file_path},
        ]
        
        result = self.manager.execute_chain(operations)
        
        self.assertIsInstance(result, BatchBackupResult)
        self.assertGreaterEqual(result.successful, 1)
    
    def test_check_condition_size(self):
        """Test size condition checking."""
        context = {'db_size': 1500}
        self.assertTrue(self.manager.check_condition('size > 1000', context))
        self.assertFalse(self.manager.check_condition('size > 2000', context))
    
    def test_check_condition_count(self):
        """Test count condition checking."""
        context = {'row_count': 500}
        self.assertTrue(self.manager.check_condition('count > 100', context))
        self.assertFalse(self.manager.check_condition('count > 1000', context))
    
    def test_get_operations(self):
        """Test getting operations history."""
        self.manager.execute_backup(source_db='db1', target_file='b1.json.gz')
        self.manager.execute_backup(source_db='db2', target_file='b2.json.gz')
        
        operations = self.manager.get_operations()
        self.assertEqual(len(operations), 2)
    
    def test_status_callback(self):
        """Test status callback registration."""
        callback_results = []
        
        def callback(result):
            callback_results.append(result)
        
        self.manager.register_status_callback(callback)
        
        self.manager.execute_backup(source_db='db1', target_file='cb_test.json.gz')
        
        self.assertEqual(len(callback_results), 1)


class TestParseBackupCommand(unittest.TestCase):
    """Test BACKUP command parsing."""
    
    def test_parse_simple_backup(self):
        """Parse simple BACKUP command."""
        command = "BACKUP mydb"
        result = parse_backup_command(command)
        
        self.assertEqual(result['type'], 'backup')
        self.assertEqual(result['source_db'], 'mydb')
        self.assertIsNone(result['target_file'])
    
    def test_parse_backup_with_target(self):
        """Parse BACKUP with target file."""
        command = "BACKUP mydb TO backup.json.gz"
        result = parse_backup_command(command)
        
        self.assertEqual(result['target_file'], 'backup.json.gz')
    
    def test_parse_backup_with_tables(self):
        """Parse BACKUP with specific tables."""
        command = "BACKUP mydb TABLES users, orders, products"
        result = parse_backup_command(command)
        
        self.assertEqual(result['tables'], ['users', 'orders', 'products'])


class TestParseBackupIfCommand(unittest.TestCase):
    """Test BACKUP IF command parsing."""
    
    def test_parse_backup_if(self):
        """Parse conditional backup."""
        command = "BACKUP mydb IF size > 1000"
        result = parse_backup_if_command(command)
        
        self.assertEqual(result['type'], 'backup_if')
        self.assertEqual(result['source_db'], 'mydb')
        self.assertEqual(result['condition'], 'size > 1000')
    
    def test_parse_backup_if_with_target(self):
        """Parse conditional backup with target."""
        command = "BACKUP mydb IF count > 500 TO conditional_backup.json.gz"
        result = parse_backup_if_command(command)
        
        self.assertEqual(result['condition'], 'count > 500')
        self.assertEqual(result['target_file'], 'conditional_backup.json.gz')


class TestParseRestoreCommand(unittest.TestCase):
    """Test RESTORE command parsing."""
    
    def test_parse_simple_restore(self):
        """Parse simple RESTORE."""
        command = "RESTORE backup.json.gz TO mydb"
        result = parse_restore_command(command)
        
        self.assertEqual(result['type'], 'restore')
        self.assertEqual(result['source_file'], 'backup.json.gz')
        self.assertEqual(result['target_db'], 'mydb')
    
    def test_parse_restore_with_verify(self):
        """Parse RESTORE with verification."""
        command = "RESTORE backup.json.gz TO mydb VERIFY"
        result = parse_restore_command(command)
        
        self.assertTrue(result['verify'])


class TestParseVerifyCommand(unittest.TestCase):
    """Test VERIFY command parsing."""
    
    def test_parse_verify_backup(self):
        """Parse VERIFY BACKUP command."""
        command = "VERIFY BACKUP mybackup.json.gz"
        result = parse_verify_command(command)
        
        self.assertEqual(result['type'], 'verify')
        self.assertEqual(result['file_path'], 'mybackup.json.gz')


class TestParseBackupChain(unittest.TestCase):
    """Test backup chain parsing."""
    
    def test_parse_chain(self):
        """Parse chain of commands."""
        commands = [
            "BACKUP mydb TO backup.json.gz",
            "VERIFY BACKUP backup.json.gz",
            "RESTORE backup.json.gz TO newdb VERIFY"
        ]
        
        operations = parse_backup_chain(commands)
        
        self.assertEqual(len(operations), 3)
        self.assertEqual(operations[0]['type'], 'backup')
        self.assertEqual(operations[1]['type'], 'verify')
        self.assertEqual(operations[2]['type'], 'restore')


class TestGlobalManager(unittest.TestCase):
    """Test global manager singleton."""
    
    def test_get_batch_backup_manager(self):
        """Test getting global manager."""
        manager1 = get_batch_backup_manager('./test_backups')
        manager2 = get_batch_backup_manager('./test_backups')
        
        self.assertIs(manager1, manager2)
        
        if os.path.exists('./test_backups'):
            shutil.rmtree('./test_backups')


if __name__ == '__main__':
    unittest.main(verbosity=2)
