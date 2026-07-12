
"""
Batch Migration Operations Examples

Demonstrates batch migration operations:
- Dry-run migrations
- Conditional migrations
- Batch rollback
- Migration status reporting
"""

import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from batch_migration import (
    BatchMigrationManager,
    BatchMigrationStatus,
    get_batch_migration_manager,
    parse_migration_commands
)


def example_dry_run_migration():
    """Example: Dry-run migration to preview changes."""
    print("\n=== Dry-Run Migration Example ===\n")
    
    temp_dir = tempfile.mkdtemp()
    manager = BatchMigrationManager(None, temp_dir)
    
    try:
        # Dry-run migration (simulates without applying)
        result = manager.migrate_up(dry_run=True)
        
        print(f"Migration ID: {result.migration_id}")
        print(f"Status: {result.status.value}")
        print(f"Direction: {result.direction}")
        print(f"Dry Run: {result.dry_run}")
        print(f"Steps: {result.steps_executed}/{result.steps_total}")
        print(f"Time: {result.elapsed_ms:.2f}ms")
        
        if result.error_message:
            print(f"Error: {result.error_message}")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def example_conditional_migration():
    """Example: Conditional migration based on pending status."""
    print("\n=== Conditional Migration Example ===\n")
    
    temp_dir = tempfile.mkdtemp()
    manager = BatchMigrationManager(None, temp_dir)
    
    try:
        # Check if there are pending migrations
        has_pending = manager.check_pending()
        pending_count = manager.get_pending_count()
        
        print(f"Pending migrations: {pending_count}")
        print(f"Has pending: {has_pending}")
        
        # Only migrate if pending
        if has_pending:
            print("Running migrations...")
            result = manager.migrate_up()
            print(f"Migration result: {result.status.value}")
        else:
            print("No pending migrations - skipping")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def example_migration_rollback():
    """Example: Rollback a migration."""
    print("\n=== Migration Rollback Example ===\n")
    
    temp_dir = tempfile.mkdtemp()
    manager = BatchMigrationManager(None, temp_dir)
    
    try:
        # First do a dry-run up
        up_result = manager.migrate_up(dry_run=True)
        print(f"Up migration: {up_result.status.value}")
        
        # Then dry-run rollback
        down_result = manager.migrate_down(
            migration_id='test_migration',
            dry_run=True
        )
        
        print(f"Rollback: {down_result.status.value}")
        print(f"Direction: {down_result.direction}")
        print(f"Steps: {down_result.steps_executed}/{down_result.steps_total}")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def example_migration_report():
    """Example: Generate migration report."""
    print("\n=== Migration Report Example ===\n")
    
    temp_dir = tempfile.mkdtemp()
    manager = BatchMigrationManager(None, temp_dir)
    
    try:
        # Simulate some migrations
        manager.migrate_up(dry_run=True)
        manager.migrate_down('migration_001', dry_run=True)
        manager.migrate_up(dry_run=True)
        
        # Generate report
        report = manager.generate_report()
        
        print("Migration Report:")
        print(f"  Total migrations: {report.total_migrations}")
        print(f"  Successful: {report.successful}")
        print(f"  Failed: {report.failed}")
        print(f"  Rolled back: {report.rolled_back}")
        print(f"  Pending: {report.pending}")
        print(f"  Total time: {report.total_elapsed_ms:.2f}ms")
        
        print("\nDetailed Results:")
        for i, result in enumerate(report.results, 1):
            print(f"  {i}. {result.migration_id}: {result.status.value} "
                  f"({result.elapsed_ms:.2f}ms)")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def example_parse_migration_commands():
    """Example: Parse SQL-like migration commands."""
    print("\n=== Parse Migration Commands Example ===\n")
    
    commands = [
        "MIGRATE UP",
        "MIGRATE UP migration_001 VERIFY",
        "MIGRATE UP IF PENDING",
        "MIGRATE DOWN migration_001",
        "MIGRATE DRY-RUN UP",
        "MIGRATE STATUS"
    ]
    
    print("Parsing migration commands:")
    for cmd in commands:
        print(f"\n  Command: {cmd}")
        ops = parse_migration_commands([cmd])
        if ops:
            op = ops[0]
            print(f"  Parsed: {op['type']}")
            for key, value in op.items():
                if key != 'type':
                    print(f"    - {key}: {value}")
        else:
            print("  Could not parse")


def example_status_callback():
    """Example: Monitor migration status with callbacks."""
    print("\n=== Status Callback Example ===\n")
    
    temp_dir = tempfile.mkdtemp()
    manager = BatchMigrationManager(None, temp_dir)
    
    # Track migrations via callback
    migration_log = []
    
    def on_migration_status(result):
        migration_log.append({
            'id': result.migration_id,
            'status': result.status.value,
            'direction': result.direction
        })
        print(f"  [Callback] {result.migration_id}: {result.status.value}")
    
    manager.register_status_callback(on_migration_status)
    
    try:
        # Run migrations - callbacks will fire
        manager.migrate_up(dry_run=True)
        manager.migrate_down('test', dry_run=True)
        
        print(f"\nLogged {len(migration_log)} migration events")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def example_version_check():
    """Example: Check current schema version."""
    print("\n=== Version Check Example ===\n")
    
    temp_dir = tempfile.mkdtemp()
    manager = BatchMigrationManager(None, temp_dir)
    
    try:
        current_version = manager.get_current_version()
        
        print(f"Current schema version: {current_version}")
        
        # Check if we need to migrate
        if manager.check_pending():
            print("Pending migrations found")
        else:
            print("Schema is up to date")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def run_all_examples():
    """Run all migration examples."""
    examples = [
        example_dry_run_migration,
        example_conditional_migration,
        example_migration_rollback,
        example_migration_report,
        example_parse_migration_commands,
        example_status_callback,
        example_version_check,
    ]
    
    for example in examples:
        try:
            example()
        except Exception as e:
            print(f"\nError in {example.__name__}: {e}")
    
    print("\n" + "="*60)
    print("All migration examples completed!")
    print("="*60)


if __name__ == '__main__':
    run_all_examples()
