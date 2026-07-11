"""
Tests for schema migration system.
"""

import unittest
import os
import tempfile
import shutil
from schema_migration import (
    MigrationStatus, MigrationType, MigrationStep, Migration,
    SchemaVersion, MigrationExecutor, MigrationHistory,
    SchemaMigrator, create_table_migration, create_index_migration
)


class MockDB:
    """Mock database connection."""
    def __init__(self):
        self.executed = []
    
    def execute(self, sql):
        self.executed.append(sql)


class TestSchemaVersion(unittest.TestCase):
    def test_parse_version(self):
        v = SchemaVersion.parse("1.2.3")
        self.assertEqual(v.major, 1)
        self.assertEqual(v.minor, 2)
        self.assertEqual(v.patch, 3)
    
    def test_parse_invalid(self):
        with self.assertRaises(ValueError):
            SchemaVersion.parse("invalid")
    
    def test_version_comparison(self):
        v1 = SchemaVersion(1, 0, 0)
        v2 = SchemaVersion(1, 1, 0)
        v3 = SchemaVersion(2, 0, 0)
        
        self.assertTrue(v1 < v2)
        self.assertTrue(v2 < v3)
        self.assertTrue(v1 < v3)
        self.assertEqual(v1, SchemaVersion(1, 0, 0))
    
    def test_version_string(self):
        v = SchemaVersion(1, 2, 3)
        self.assertEqual(str(v), "1.2.3")


class TestMigrationStep(unittest.TestCase):
    def test_step_creation(self):
        step = MigrationStep(
            step_id="step1",
            operation=MigrationType.CREATE_TABLE,
            description="Create users table",
            forward_sql="CREATE TABLE users (id INT);",
            rollback_sql="DROP TABLE users;"
        )
        
        self.assertEqual(step.step_id, "step1")
        self.assertEqual(step.operation, MigrationType.CREATE_TABLE)
        self.assertIsNotNone(step.checksum)
    
    def test_checksum_verification(self):
        step = MigrationStep(
            step_id="step1",
            operation=MigrationType.CREATE_TABLE,
            description="Create users table",
            forward_sql="CREATE TABLE users (id INT);",
            rollback_sql="DROP TABLE users;"
        )
        
        self.assertTrue(step.verify_checksum())
        
        # Tamper with SQL
        step.forward_sql = "ALTERED"
        self.assertFalse(step.verify_checksum())


class TestMigration(unittest.TestCase):
    def test_migration_creation(self):
        migration = Migration(
            migration_id="mig_1",
            version="1.0.0",
            description="Initial migration",
            author="test"
        )
        
        self.assertEqual(migration.status, MigrationStatus.PENDING)
        self.assertIsNone(migration.applied_at)
    
    def test_add_step(self):
        migration = Migration(
            migration_id="mig_1",
            version="1.0.0",
            description="Test",
            author="test"
        )
        
        step = MigrationStep(
            step_id="s1",
            operation=MigrationType.CREATE_TABLE,
            description="Create table",
            forward_sql="CREATE TABLE t (id INT);",
            rollback_sql="DROP TABLE t;"
        )
        
        migration.steps.append(step)
        self.assertEqual(len(migration.steps), 1)
    
    def test_to_dict(self):
        migration = Migration(
            migration_id="mig_1",
            version="1.0.0",
            description="Test",
            author="test"
        )
        
        d = migration.to_dict()
        self.assertEqual(d['migration_id'], "mig_1")
        self.assertEqual(d['status'], "PENDING")


class TestMigrationExecutor(unittest.TestCase):
    def setUp(self):
        self.db = MockDB()
        self.executor = MigrationExecutor(self.db)
    
    def test_execute_forward(self):
        migration = Migration(
            migration_id="mig_1",
            version="1.0.0",
            description="Test",
            author="test"
        )
        
        step = MigrationStep(
            step_id="s1",
            operation=MigrationType.CREATE_TABLE,
            description="Create table",
            forward_sql="CREATE TABLE t (id INT);",
            rollback_sql="DROP TABLE t;"
        )
        migration.steps.append(step)
        
        success = self.executor.execute_forward(migration)
        self.assertTrue(success)
        self.assertEqual(migration.status, MigrationStatus.APPLIED)
        self.assertEqual(len(self.db.executed), 1)
    
    def test_execute_rollback(self):
        migration = Migration(
            migration_id="mig_1",
            version="1.0.0",
            description="Test",
            author="test"
        )
        migration.status = MigrationStatus.APPLIED
        
        step = MigrationStep(
            step_id="s1",
            operation=MigrationType.CREATE_TABLE,
            description="Create table",
            forward_sql="CREATE TABLE t (id INT);",
            rollback_sql="DROP TABLE t;"
        )
        migration.steps.append(step)
        
        success = self.executor.execute_rollback(migration)
        self.assertTrue(success)
        self.assertEqual(migration.status, MigrationStatus.ROLLED_BACK)
    
    def test_checksum_failure(self):
        migration = Migration(
            migration_id="mig_1",
            version="1.0.0",
            description="Test",
            author="test"
        )
        
        step = MigrationStep(
            step_id="s1",
            operation=MigrationType.CREATE_TABLE,
            description="Create table",
            forward_sql="CREATE TABLE t (id INT);",
            rollback_sql="DROP TABLE t;"
        )
        # Tamper with checksum
        step.checksum = "invalid"
        migration.steps.append(step)
        
        success = self.executor.execute_forward(migration)
        self.assertFalse(success)
        self.assertEqual(migration.status, MigrationStatus.FAILED)
    
    def test_topological_sort(self):
        step1 = MigrationStep(
            step_id="s1",
            operation=MigrationType.CREATE_TABLE,
            description="Step 1",
            forward_sql="SQL1",
            rollback_sql="ROLLBACK1"
        )
        
        step2 = MigrationStep(
            step_id="s2",
            operation=MigrationType.CREATE_TABLE,
            description="Step 2",
            forward_sql="SQL2",
            rollback_sql="ROLLBACK2",
            dependencies=["s1"]
        )
        
        step3 = MigrationStep(
            step_id="s3",
            operation=MigrationType.CREATE_TABLE,
            description="Step 3",
            forward_sql="SQL3",
            rollback_sql="ROLLBACK3",
            dependencies=["s2"]
        )
        
        steps = [step3, step1, step2]  # Out of order
        sorted_steps = self.executor._topological_sort(steps)
        
        ids = [s.step_id for s in sorted_steps]
        self.assertEqual(ids, ["s1", "s2", "s3"])


class TestMigrationHistory(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.history = MigrationHistory(self.temp_dir)
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir)
    
    def test_record_and_get(self):
        migration = Migration(
            migration_id="mig_1",
            version="1.0.0",
            description="Test",
            author="test"
        )
        migration.status = MigrationStatus.APPLIED
        
        self.history.record_migration(migration)
        
        retrieved = self.history.get_migration("mig_1")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.migration_id, "mig_1")
    
    def test_get_applied(self):
        m1 = Migration("mig_1", "1.0.0", "Test", "test")
        m1.status = MigrationStatus.APPLIED
        
        m2 = Migration("mig_2", "1.0.1", "Test", "test")
        m2.status = MigrationStatus.PENDING
        
        self.history.record_migration(m1)
        self.history.record_migration(m2)
        
        applied = self.history.get_applied_migrations()
        self.assertEqual(len(applied), 1)
        self.assertEqual(applied[0].migration_id, "mig_1")
    
    def test_get_current_version(self):
        m1 = Migration("mig_1", "1.0.0", "Test", "test")
        m1.status = MigrationStatus.APPLIED
        
        m2 = Migration("mig_2", "1.1.0", "Test", "test")
        m2.status = MigrationStatus.APPLIED
        
        self.history.record_migration(m1)
        self.history.record_migration(m2)
        
        current = self.history.get_current_version()
        self.assertEqual(str(current), "1.1.0")


class TestSchemaMigrator(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db = MockDB()
        self.migrator = SchemaMigrator(self.db, self.temp_dir)
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir)
    
    def test_create_migration(self):
        migration = self.migrator.create_migration("Add users table")
        
        self.assertIsNotNone(migration.migration_id)
        self.assertEqual(migration.description, "Add users table")
        self.assertIn(migration.migration_id, self.migrator._migrations)
    
    def test_add_step(self):
        migration = self.migrator.create_migration("Test")
        
        step = self.migrator.add_step(
            migration.migration_id,
            MigrationType.CREATE_TABLE,
            "Create users table",
            "CREATE TABLE users (id INT);",
            "DROP TABLE users;"
        )
        
        self.assertEqual(len(migration.steps), 1)
        self.assertEqual(step.operation, MigrationType.CREATE_TABLE)
    
    def test_migrate(self):
        migration = self.migrator.create_migration("Test")
        
        self.migrator.add_step(
            migration.migration_id,
            MigrationType.CREATE_TABLE,
            "Create table",
            "CREATE TABLE t (id INT);",
            "DROP TABLE t;"
        )
        
        applied = self.migrator.migrate()
        
        self.assertEqual(len(applied), 1)
        self.assertEqual(applied[0].status, MigrationStatus.APPLIED)
    
    def test_rollback(self):
        migration = self.migrator.create_migration("Test")
        
        self.migrator.add_step(
            migration.migration_id,
            MigrationType.CREATE_TABLE,
            "Create table",
            "CREATE TABLE t (id INT);",
            "DROP TABLE t;"
        )
        
        self.migrator.migrate()
        
        success = self.migrator.rollback(migration.migration_id)
        self.assertTrue(success)
        self.assertEqual(migration.status, MigrationStatus.ROLLED_BACK)
    
    def test_get_status(self):
        migration = self.migrator.create_migration("Test")
        self.migrator.add_step(
            migration.migration_id,
            MigrationType.CREATE_TABLE,
            "Create table",
            "CREATE TABLE t (id INT);",
            "DROP TABLE t;"
        )
        
        status = self.migrator.get_status()
        
        self.assertIsNone(status['current_version'])
        self.assertEqual(status['pending_count'], 1)
    
    def test_validate_migrations(self):
        migration = self.migrator.create_migration("Test")
        
        step = self.migrator.add_step(
            migration.migration_id,
            MigrationType.CREATE_TABLE,
            "Create table",
            "CREATE TABLE t (id INT);",
            "DROP TABLE t;"
        )
        
        # Valid migration
        errors = self.migrator.validate_migrations()
        self.assertEqual(len(errors), 0)
        
        # Tamper with step
        step.forward_sql = "ALTERED"
        errors = self.migrator.validate_migrations()
        self.assertEqual(len(errors), 1)


class TestMigrationTemplates(unittest.TestCase):
    def test_create_table_migration(self):
        columns = {"id": "INT", "name": "VARCHAR(255)"}
        forward, rollback = create_table_migration("users", columns)
        
        self.assertIn("CREATE TABLE users", forward)
        self.assertIn("id INT", forward)
        self.assertIn("DROP TABLE users", rollback)
    
    def test_create_index_migration(self):
        forward, rollback = create_index_migration(
            "idx_name", "users", ["name"]
        )
        
        self.assertIn("CREATE INDEX idx_name", forward)
        self.assertIn("ON users", forward)
        self.assertIn("DROP INDEX idx_name", rollback)


class TestIntegration(unittest.TestCase):
    def test_full_migration_workflow(self):
        temp_dir = tempfile.mkdtemp()
        db = MockDB()
        
        try:
            migrator = SchemaMigrator(db, temp_dir)
            
            # Create initial migration
            mig1 = migrator.create_migration("Initial schema", "developer1")
            migrator.add_step(
                mig1.migration_id,
                MigrationType.CREATE_TABLE,
                "Create users",
                "CREATE TABLE users (id INT PRIMARY KEY, name VARCHAR(255));",
                "DROP TABLE users;"
            )
            
            # Apply migration
            applied = migrator.migrate()
            self.assertEqual(len(applied), 1)
            self.assertEqual(applied[0].version, "0.0.1")
            
            # Create second migration
            mig2 = migrator.create_migration("Add index", "developer2")
            migrator.add_step(
                mig2.migration_id,
                MigrationType.CREATE_INDEX,
                "Create name index",
                "CREATE INDEX idx_name ON users(name);",
                "DROP INDEX idx_name;"
            )
            
            # Apply new migration
            applied = migrator.migrate()
            self.assertEqual(len(applied), 1)
            self.assertEqual(applied[0].version, "0.0.2")
            
            # Verify status
            status = migrator.get_status()
            self.assertEqual(status['applied_count'], 2)
            
            # Rollback last
            rolled = migrator.rollback_last()
            self.assertIsNotNone(rolled)
            self.assertEqual(rolled.migration_id, mig2.migration_id)
            
        finally:
            shutil.rmtree(temp_dir)


if __name__ == '__main__':
    unittest.main(verbosity=2)
