
"""
KosDB v2.3.0 Schema Migration

Upgrades database from v2.2.0 to v2.3.0, adding support for:
- Batch command audit logging
- Batch execution metrics
- Configuration versioning

This migration is idempotent - it can be run multiple times safely.
"""

import sys
import os
import json
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Migration metadata
MIGRATION_VERSION = "2.3.0"
MIGRATION_NAME = "batch_commands_support"
MIGRATION_DESCRIPTION = "Add batch command support with audit logging and metrics"
MIGRATION_AUTHOR = "KosDB Team"
MIGRATION_CREATED = "2024-01-15"


class V2_3_0_Migration:
    """
    Migration from v2.2.0 to v2.3.0.
    
    Changes:
    1. Update version marker from 2.2.0 to 2.3.0
    2. Add batch_audit_log table for batch command auditing
    3. Add batch_metrics table for execution statistics
    4. Add configuration table for version tracking
    5. Update existing audit_log table with batch support
    """
    
    def __init__(self, db_connection=None):
        self.db = db_connection
        self.version_key = "schema_version"
        self.errors = []
        self.warnings = []
    
    def is_applicable(self) -> bool:
        """
        Check if migration should be applied.
        
        Returns:
            True if current version is < 2.3.0
        """
        current_version = self._get_current_version()
        
        if current_version is None:
            # No version marker - assume fresh install or very old
            return True
        
        # Parse versions
        current = self._parse_version(current_version)
        target = self._parse_version(MIGRATION_VERSION)
        
        return current < target
    
    def is_idempotent(self) -> bool:
        """
        Check if migration has already been applied (idempotent check).
        
        Returns:
            True if migration can be safely re-run
        """
        current_version = self._get_current_version()
        
        if current_version == MIGRATION_VERSION:
            # Check if all tables exist
            required_tables = [
                'batch_audit_log',
                'batch_metrics',
                'schema_migrations'
            ]
            
            for table in required_tables:
                if not self._table_exists(table):
                    return False
            
            return True
        
        return False
    
    def migrate(self) -> bool:
        """
        Execute forward migration.
        
        Returns:
            True if successful
        """
        print(f"Starting migration to v{MIGRATION_VERSION}...")
        
        try:
            # Step 1: Create schema migrations tracking table
            if not self._step_create_migrations_table():
                return False
            
            # Step 2: Create batch audit log table
            if not self._step_create_batch_audit_table():
                return False
            
            # Step 3: Create batch metrics table
            if not self._step_create_batch_metrics_table():
                return False
            
            # Step 4: Update existing audit log table
            if not self._step_update_audit_log():
                return False
            
            # Step 5: Update version marker
            if not self._step_update_version():
                return False
            
            # Step 6: Record migration
            if not self._step_record_migration():
                return False
            
            print(f"✓ Migration to v{MIGRATION_VERSION} completed successfully")
            return True
            
        except Exception as e:
            self.errors.append(f"Migration failed: {e}")
            print(f"✗ Migration failed: {e}")
            return False
    
    def rollback(self) -> bool:
        """
        Rollback migration (downgrade to v2.2.0).
        
        Returns:
            True if successful
        """
        print(f"Starting rollback from v{MIGRATION_VERSION} to v2.2.0...")
        
        try:
            # Step 1: Drop batch metrics table
            if not self._step_rollback_batch_metrics():
                return False
            
            # Step 2: Drop batch audit log table
            if not self._step_rollback_batch_audit():
                return False
            
            # Step 3: Revert audit log changes
            if not self._step_rollback_audit_log():
                return False
            
            # Step 4: Update version marker
            if not self._step_rollback_version():
                return False
            
            print(f"✓ Rollback to v2.2.0 completed successfully")
            return True
            
        except Exception as e:
            self.errors.append(f"Rollback failed: {e}")
            print(f"✗ Rollback failed: {e}")
            return False
    
    def verify(self) -> bool:
        """
        Verify migration was applied correctly.
        
        Returns:
            True if verification passes
        """
        print("Verifying migration...")
        
        checks = [
            ("Version marker", self._get_current_version() == MIGRATION_VERSION),
            ("Migrations table", self._table_exists("schema_migrations")),
            ("Batch audit table", self._table_exists("batch_audit_log")),
            ("Batch metrics table", self._table_exists("batch_metrics")),
        ]
        
        all_passed = True
        for name, passed in checks:
            status = "✓" if passed else "✗"
            print(f"  {status} {name}")
            if not passed:
                all_passed = False
        
        return all_passed
    
    # ============ Forward Migration Steps ============
    
    def _step_create_migrations_table(self) -> bool:
        """Create schema migrations tracking table."""
        sql = """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_id TEXT PRIMARY KEY,
            version TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            author TEXT,
            created_at REAL,
            applied_at REAL DEFAULT (strftime('%s', 'now')),
            execution_time_ms REAL,
            checksum TEXT,
            status TEXT DEFAULT 'APPLIED'
        );
        """
        
        try:
            self._execute(sql)
            print("  ✓ Created schema_migrations table")
            return True
        except Exception as e:
            self.errors.append(f"Failed to create migrations table: {e}")
            return False
    
    def _step_create_batch_audit_table(self) -> bool:
        """Create batch audit log table."""
        sql = """
        CREATE TABLE IF NOT EXISTS batch_audit_log (
            event_id TEXT PRIMARY KEY,
            timestamp REAL DEFAULT (strftime('%s', 'now')),
            user_id TEXT NOT NULL,
            client_ip TEXT,
            batch_id TEXT,
            command_count INTEGER,
            commands TEXT,  -- JSON array of commands
            results TEXT,   -- JSON array of results
            success_count INTEGER,
            error_count INTEGER,
            execution_time_ms REAL,
            risk_score INTEGER DEFAULT 0,
            metadata TEXT   -- JSON metadata
        );
        
        CREATE INDEX IF NOT EXISTS idx_batch_audit_user 
            ON batch_audit_log(user_id);
        CREATE INDEX IF NOT EXISTS idx_batch_audit_time 
            ON batch_audit_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_batch_audit_batch 
            ON batch_audit_log(batch_id);
        """
        
        try:
            self._execute(sql)
            print("  ✓ Created batch_audit_log table")
            return True
        except Exception as e:
            self.errors.append(f"Failed to create batch audit table: {e}")
            return False
    
    def _step_create_batch_metrics_table(self) -> bool:
        """Create batch metrics table."""
        sql = """
        CREATE TABLE IF NOT EXISTS batch_metrics (
            metric_id TEXT PRIMARY KEY,
            timestamp REAL DEFAULT (strftime('%s', 'now')),
            batch_size INTEGER,
            avg_command_time_ms REAL,
            total_time_ms REAL,
            cache_hit_rate REAL,
            commands_per_second REAL,
            user_id TEXT,
            metadata TEXT   -- JSON metadata
        );
        
        CREATE INDEX IF NOT EXISTS idx_batch_metrics_time 
            ON batch_metrics(timestamp);
        CREATE INDEX IF NOT EXISTS idx_batch_metrics_user 
            ON batch_metrics(user_id);
        """
        
        try:
            self._execute(sql)
            print("  ✓ Created batch_metrics table")
            return True
        except Exception as e:
            self.errors.append(f"Failed to create batch metrics table: {e}")
            return False
    
    def _step_update_audit_log(self) -> bool:
        """Update existing audit log table with batch support."""
        # Check if audit_log table exists
        if not self._table_exists("audit_log"):
            print("  ℹ No existing audit_log table to update")
            return True
        
        # Add batch-related columns if they don't exist
        alter_statements = []
        
        # Check columns and add if missing
        columns = self._get_table_columns("audit_log")
        
        if "batch_id" not in columns:
            alter_statements.append(
                "ALTER TABLE audit_log ADD COLUMN batch_id TEXT;"
            )
        
        if "is_batch_command" not in columns:
            alter_statements.append(
                "ALTER TABLE audit_log ADD COLUMN is_batch_command INTEGER DEFAULT 0;"
            )
        
        if "batch_index" not in columns:
            alter_statements.append(
                "ALTER TABLE audit_log ADD COLUMN batch_index INTEGER;"
            )
        
        try:
            for sql in alter_statements:
                self._execute(sql)
            
            if alter_statements:
                print(f"  ✓ Updated audit_log table ({len(alter_statements)} changes)")
            else:
                print("  ℹ audit_log table already up to date")
            
            return True
            
        except Exception as e:
            self.errors.append(f"Failed to update audit log: {e}")
            return False
    
    def _step_update_version(self) -> bool:
        """Update version marker in database."""
        # Store version in a special system table or config
        sql = """
        INSERT OR REPLACE INTO schema_migrations (
            migration_id, version, name, description, author, created_at, applied_at
        ) VALUES (
            'version_marker', ?, 'version', 'Schema version marker', 'system', ?, ?
        );
        """
        
        try:
            self._execute(sql, (
                MIGRATION_VERSION,
                time.time(),
                time.time()
            ))
            print(f"  ✓ Updated version marker to v{MIGRATION_VERSION}")
            return True
        except Exception as e:
            # Fallback: try simpler approach
            try:
                self._execute(f"""
                    CREATE TABLE IF NOT EXISTS db_version (
                        version TEXT PRIMARY KEY,
                        updated_at REAL
                    );
                    INSERT OR REPLACE INTO db_version VALUES (?, ?);
                """, (MIGRATION_VERSION, time.time()))
                print(f"  ✓ Updated version marker (fallback) to v{MIGRATION_VERSION}")
                return True
            except Exception as e2:
                self.errors.append(f"Failed to update version: {e}, {e2}")
                return False
    
    def _step_record_migration(self) -> bool:
        """Record this migration in the migrations table."""
        sql = """
        INSERT OR REPLACE INTO schema_migrations (
            migration_id, version, name, description, author, 
            created_at, applied_at, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """
        
        try:
            self._execute(sql, (
                f"mig_v{MIGRATION_VERSION.replace('.', '_')}",
                MIGRATION_VERSION,
                MIGRATION_NAME,
                MIGRATION_DESCRIPTION,
                MIGRATION_AUTHOR,
                MIGRATION_CREATED,
                time.time(),
                'APPLIED'
            ))
            print("  ✓ Recorded migration")
            return True
        except Exception as e:
            self.warnings.append(f"Could not record migration: {e}")
            return True  # Non-fatal
    
    # ============ Rollback Steps ============
    
    def _step_rollback_batch_metrics(self) -> bool:
        """Drop batch metrics table."""
        try:
            self._execute("DROP TABLE IF EXISTS batch_metrics;")
            print("  ✓ Dropped batch_metrics table")
            return True
        except Exception as e:
            self.errors.append(f"Failed to drop batch metrics: {e}")
            return False
    
    def _step_rollback_batch_audit(self) -> bool:
        """Drop batch audit log table."""
        try:
            self._execute("DROP TABLE IF EXISTS batch_audit_log;")
            print("  ✓ Dropped batch_audit_log table")
            return True
        except Exception as e:
            self.errors.append(f"Failed to drop batch audit: {e}")
            return False
    
    def _step_rollback_audit_log(self) -> bool:
        """Revert audit log changes."""
        try:
            # Note: SQLite doesn't support DROP COLUMN
            # We would need to recreate the table or just leave columns
            print("  ℹ audit_log columns preserved (SQLite limitation)")
            return True
        except Exception as e:
            self.warnings.append(f"Could not fully rollback audit log: {e}")
            return True
    
    def _step_rollback_version(self) -> bool:
        """Revert version marker."""
        try:
            self._execute(
                "INSERT OR REPLACE INTO db_version VALUES (?, ?);",
                ("2.2.0", time.time())
            )
            print("  ✓ Reverted version marker to v2.2.0")
            return True
        except Exception as e:
            self.errors.append(f"Failed to rollback version: {e}")
            return False
    
    # ============ Helper Methods ============
    
    def _get_current_version(self) -> str:
        """Get current database version."""
        try:
            # Try migrations table first
            result = self._query(
                "SELECT version FROM schema_migrations WHERE migration_id = 'version_marker';"
            )
            if result:
                return result[0][0]
            
            # Try fallback table
            result = self._query("SELECT version FROM db_version LIMIT 1;")
            if result:
                return result[0][0]
                
        except Exception:
            pass
        
        return None
    
    def _parse_version(self, version_str: str) -> tuple:
        """Parse version string to tuple."""
        parts = version_str.split('.')
        return tuple(int(p) for p in parts)
    
    def _table_exists(self, table_name: str) -> bool:
        """Check if table exists."""
        try:
            result = self._query(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?;",
                (table_name,)
            )
            return len(result) > 0
        except Exception:
            return False
    
    def _get_table_columns(self, table_name: str) -> list:
        """Get list of table columns."""
        try:
            result = self._query(f"PRAGMA table_info({table_name});")
            return [row[1] for row in result]
        except Exception:
            return []
    
    def _execute(self, sql: str, params: tuple = None):
        """Execute SQL statement."""
        if self.db is None:
            # For testing without real DB
            print(f"  [MOCK] Would execute: {sql[:50]}...")
            return
        
        cursor = self.db.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        self.db.commit()
    
    def _query(self, sql: str, params: tuple = None):
        """Execute query and return results."""
        if self.db is None:
            return []
        
        cursor = self.db.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        return cursor.fetchall()


def run_migration(db_path: str = None, db_connection=None) -> bool:
    """
    Run v2.3.0 migration.
    
    Args:
        db_path: Path to database file
        db_connection: Existing database connection
    
    Returns:
        True if successful
    """
    print(f"KosDB Migration to v{MIGRATION_VERSION}")
    print("=" * 50)
    
    # Get database connection
    if db_connection is None and db_path:
        import sqlite3
        db_connection = sqlite3.connect(db_path)
    
    migration = V2_3_0_Migration(db_connection)
    
    # Check if already applied
    if migration.is_idempotent():
        print(f"Migration v{MIGRATION_VERSION} already applied (idempotent)")
        return True
    
    # Check applicability
    if not migration.is_applicable():
        current = migration._get_current_version()
        print(f"Migration not applicable (current version: {current})")
        return False
    
    # Run migration
    success = migration.migrate()
    
    if success:
        # Verify
        migration.verify()
    
    return success


def run_rollback(db_path: str = None, db_connection=None) -> bool:
    """
    Rollback v2.3.0 migration.
    
    Args:
        db_path: Path to database file
        db_connection: Existing database connection
    
    Returns:
        True if successful
    """
    print(f"KosDB Rollback from v{MIGRATION_VERSION}")
    print("=" * 50)
    
    if db_connection is None and db_path:
        import sqlite3
        db_connection = sqlite3.connect(db_path)
    
    migration = V2_3_0_Migration(db_connection)
    return migration.rollback()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='KosDB v2.3.0 Migration')
    parser.add_argument('--db', default='kosdb.db', help='Database path')
    parser.add_argument('--rollback', action='store_true', help='Rollback migration')
    parser.add_argument('--verify', action='store_true', help='Verify migration')
    
    args = parser.parse_args()
    
    if args.rollback:
        success = run_rollback(args.db)
    elif args.verify:
        migration = V2_3_0_Migration()
        success = migration.verify()
    else:
        success = run_migration(args.db)
    
    sys.exit(0 if success else 1)
