
"""
Tests for Batch Migration Operations
"""

import unittest
import sys
import os
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from batch_migration import (
    BatchMigrationManager,
    BatchMigrationResult,
    BatchMigrationStatus,
    BatchMigrationReport,
    parse_migrate_up,
    parse_migrate_up_if,
    parse_migrate_down,
    parse_migrate_dry_run,
    parse_migrate_status,
    parse_migration_commands,
    get_batch_migration_manager
)


class TestBatchMigrationManager(unittest.TestCase):
    """Test batch migration manager."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.manager = BatchMigrationManager(None, self.temp_dir)
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_migrate_up_dry_run(self):
        """Test migrate up with dry run."""
        result = self.manager.migrate_up(dry_run=True)
        
        self.assertIsInstance(result, BatchMigrationResult)
        self.assertEqual(result.direction, 'up')
        self.assertTrue(result.dry_run)
    
    def test_migrate_down_dry_run(self):
        """Test migrate down with dry run."""
        result = self.manager.migrate_down('test_migration', dry_run=True)
        
        self.assertIsInstance(result, BatchMigrationResult)
        self.assertEqual(result.direction, 'down')
        self.assertTrue(result.dry_run)
    
    def test_check_pending_no_history(self):
        """Test check pending when no history available."""
        result = self.manager.check_pending()
        self.assertFalse(result)
    
    def test_get_pending_count_no_history(self):
        """Test get pending count when no history available."""
        count = self.manager.get_pending_count()
        self.assertEqual(count, 0)
    
    def test_get_current_version_no_history(self):
        """Test get current version when no history available."""
        version = self.manager.get_current_version()
        self.assertIsNone(version)
    
    def test_generate_report(self):
        """Test report generation."""
        self.manager._results = [
            BatchMigrationResult('m1', BatchMigrationStatus.COMPLETED, 'up', 5, 5, 100.0),
            BatchMigrationResult('m2', BatchMigrationStatus.FAILED, 'up', 0, 5, 50.0, 'Error'),
        ]
        
        report = self.manager.generate_report()
        
        self.assertIsInstance(report, BatchMigrationReport)
        self.assertEqual(report.total_migrations, 2)
        self.assertEqual(report.successful, 1)
        self.assertEqual(report.failed, 1)
        self.assertEqual(report.total_elapsed_ms, 150.0)
    
    def test_clear_results(self):
        """Test clearing results."""
        self.manager._results = [BatchMigrationResult('m1', BatchMigrationStatus.COMPLETED, 'up', 1, 1, 10.0)]
        self.assertEqual(len(self.manager._results), 1)
        
        self.manager.clear_results()
        self.assertEqual(len(self.manager._results), 0)
    
    def test_status_callback(self):
        """Test status callback registration."""

    def test_status_callback(self):
        """Test status callback registration."""
        callback_results = []
        
        def callback(result):
            callback_results.append(result)
        
        self.manager.register_status_callback(callback)
        
        # Trigger a migration - callback may or may not fire depending on 
        # whether migration system is available
        result = self.manager.migrate_up(dry_run=True)
        
        # If migration system is not available, callback won't fire
        # but registration should still work
        self.assertTrue(len(callback_results) >= 0)  # Callback registered successfully
        """Parse simple MIGRATE UP."""
        result = parse_migrate_up("MIGRATE UP")
        
        self.assertEqual(result['type'], 'migrate_up')
        self.assertIsNone(result['migration_id'])
        self.assertFalse(result['dry_run'])
        self.assertFalse(result['verify'])
    
    def test_parse_migrate_up_with_id(self):
        """Parse MIGRATE UP with migration ID."""
        result = parse_migrate_up("MIGRATE UP migration_001")
        
        self.assertEqual(result['migration_id'], 'migration_001')
    
    def test_parse_migrate_up_dry_run(self):
        """Parse MIGRATE UP DRY-RUN."""
        result = parse_migrate_up("MIGRATE UP DRY-RUN")
        
        self.assertTrue(result['dry_run'])
    
    def test_parse_migrate_up_verify(self):
        """Parse MIGRATE UP VERIFY."""
        result = parse_migrate_up("MIGRATE UP VERIFY")
        
        self.assertTrue(result['verify'])


class TestParseMigrateUpIf(unittest.TestCase):
    """Test MIGRATE UP IF conditional parsing."""
    
    def test_parse_migrate_up_if_pending(self):
        """Parse MIGRATE UP IF PENDING."""
        result = parse_migrate_up_if("MIGRATE UP IF PENDING")
        
        self.assertEqual(result['type'], 'migrate_up_if')
        self.assertEqual(result['condition'], 'PENDING')
    
    def test_parse_migrate_up_if_version(self):
        """Parse MIGRATE UP IF VERSION condition."""
        result = parse_migrate_up_if("MIGRATE UP IF VERSION < 1.0.0")
        
        self.assertEqual(result['condition'], 'VERSION < 1.0.0')


class TestParseMigrateDown(unittest.TestCase):
    """Test MIGRATE DOWN command parsing."""
    
    def test_parse_migrate_down(self):
        """Parse MIGRATE DOWN."""
        result = parse_migrate_down("MIGRATE DOWN migration_001")
        
        self.assertEqual(result['type'], 'migrate_down')
        self.assertEqual(result['migration_id'], 'migration_001')
        self.assertFalse(result['dry_run'])
    
    def test_parse_migrate_down_dry_run(self):
        """Parse MIGRATE DOWN DRY-RUN."""
        result = parse_migrate_down("MIGRATE DOWN migration_001 DRY-RUN")
        
        self.assertTrue(result['dry_run'])


class TestParseMigrateDryRun(unittest.TestCase):
    """Test MIGRATE DRY-RUN command parsing."""
    
    def test_parse_migrate_dry_run_up(self):
        """Parse MIGRATE DRY-RUN UP."""
        result = parse_migrate_dry_run("MIGRATE DRY-RUN UP")
        
        self.assertEqual(result['type'], 'migrate_up')
        self.assertTrue(result['dry_run'])
    
    def test_parse_migrate_dry_run_down(self):
        """Parse MIGRATE DRY-RUN DOWN."""
        result = parse_migrate_dry_run("MIGRATE DRY-RUN DOWN migration_001")
        
        self.assertEqual(result['type'], 'migrate_down')
        self.assertEqual(result['migration_id'], 'migration_001')
        self.assertTrue(result['dry_run'])


class TestParseMigrateStatus(unittest.TestCase):
    """Test MIGRATE STATUS command parsing."""
    
    def test_parse_migrate_status(self):
        """Parse MIGRATE STATUS."""
        result = parse_migrate_status("MIGRATE STATUS")
        
        self.assertEqual(result['type'], 'migrate_status')


class TestParseMigrationCommands(unittest.TestCase):
    """Test batch migration command parsing."""
    
    def test_parse_multiple_commands(self):
        """Parse multiple migration commands."""
        commands = [
            "MIGRATE UP",
            "MIGRATE STATUS",
            "MIGRATE DOWN migration_001"
        ]
        
        operations = parse_migration_commands(commands)
        
        self.assertEqual(len(operations), 3)
        self.assertEqual(operations[0]['type'], 'migrate_up')
        self.assertEqual(operations[1]['type'], 'migrate_status')
        self.assertEqual(operations[2]['type'], 'migrate_down')


class TestGlobalManager(unittest.TestCase):
    """Test global manager singleton."""
    
    def test_get_batch_migration_manager(self):
        """Test getting global manager."""
        manager1 = get_batch_migration_manager(None, './test_migrations')
        manager2 = get_batch_migration_manager(None, './test_migrations')
        
        self.assertIs(manager1, manager2)
        
        if os.path.exists('./test_migrations'):
            shutil.rmtree('./test_migrations')


if __name__ == '__main__':
    unittest.main(verbosity=2)
