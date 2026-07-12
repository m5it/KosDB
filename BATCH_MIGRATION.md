
# Batch Migration Operations Guide

Version: 2.3.0  
Last Updated: 2024-01-15

## Overview

Batch Migration Operations enable schema migrations within batch command sequences, supporting conditional migrations, dry-runs, rollbacks, and comprehensive status reporting.

## Features

- **Batch Migrations**: Execute migrations as part of batch operations
- **Conditional Migrations**: `MIGRATE UP IF PENDING` for smart migration decisions
- **Dry-Run Mode**: Preview migrations without applying changes
- **Batch Rollbacks**: Rollback migrations in batch sequences
- **Status Reporting**: Comprehensive migration status and reporting

## Quick Start

```python
from batch_migration import BatchMigrationManager, get_batch_migration_manager

# Create migration manager
manager = get_batch_migration_manager(db_connection, './migrations')

# Check status
if manager.check_pending():
    # Run migrations with dry-run first
    dry_run = manager.migrate_up(dry_run=True)
    print(f"Dry-run: {dry_run.steps_executed} steps")
    
    # Apply migrations
    result = manager.migrate_up()
    print(f"Migrated: {result.status.value}")
```

## SQL Commands

### MIGRATE UP

```sql
-- Run all pending migrations
MIGRATE UP;

-- Run specific migration
MIGRATE UP migration_001;

-- Run with verification
MIGRATE UP VERIFY;

-- Dry-run (preview only)
MIGRATE UP DRY-RUN;
```

### MIGRATE UP IF

```sql
-- Only migrate if pending migrations exist
MIGRATE UP IF PENDING;

-- Migrate if version is behind
MIGRATE UP IF VERSION < 1.0.0;
```

### MIGRATE DOWN

```sql
-- Rollback specific migration
MIGRATE DOWN migration_001;

-- Rollback with dry-run
MIGRATE DOWN migration_001 DRY-RUN;
```

### MIGRATE DRY-RUN

```sql
-- Dry-run up migrations
MIGRATE DRY-RUN UP;

-- Dry-run specific migration
MIGRATE DRY-RUN UP migration_001;

-- Dry-run rollback
MIGRATE DRY-RUN DOWN migration_001;
```

### MIGRATE STATUS

```sql
-- Check migration status
MIGRATE STATUS;
```

## Dry-Run Migrations

### Preview Changes

```python
# Simulate migration without applying
result = manager.migrate_up(dry_run=True)

print(f"Would execute {result.steps_executed} steps")
print(f"Estimated time: {result.elapsed_ms:.2f}ms")

if result.error_message:
    print(f"Would fail: {result.error_message}")
```

### Use Case: Pre-Deployment Validation

```python
def validate_before_deploy():
    """
    Validate migrations before deployment.
    """
    manager = get_batch_migration_manager()
    
    # Dry-run first
    dry_run = manager.migrate_up(dry_run=True)
    
    if dry_run.status == BatchMigrationStatus.COMPLETED:
        print(f"✓ {dry_run.steps_executed} steps ready to apply")
        return True
    else:
        print(f"✗ Migration would fail: {dry_run.error_message}")
        return False
```

## Conditional Migrations

### Check Pending Status

```python
# Only migrate if needed
if manager.check_pending():
    result = manager.migrate_up()
    print(f"Applied {result.steps_executed} steps")
else:
    print("Schema is up to date")
```

### Version-Based Conditions

```python
current = manager.get_current_version()
print(f"Current version: {current}")

# Conditional logic
if current and current < "2.0.0":
    print("Need to upgrade to v2")
    manager.migrate_up()
```

## Batch Rollbacks

### Rollback Specific Migration

```python
# Rollback a migration
result = manager.migrate_down('migration_001')

if result.status == BatchMigrationStatus.ROLLED_BACK:
    print(f"Rolled back {result.steps_executed} steps")
else:
    print(f"Rollback failed: {result.error_message}")
```

### Dry-Run Rollback

```python
# Preview rollback
preview = manager.migrate_down('migration_001', dry_run=True)

print(f"Would rollback {preview.steps_executed} steps")
```

## Migration Verification

### Verify After Migration

```python
# Migrate with verification
result = manager.migrate_up(verify=True)

if result.verification_passed:
    print("✓ Migration verified")
else:
    print("✗ Verification failed")
```

### Standalone Verification

```python
# Verify a specific migration
# (Would need migration object reference)
```

## Status Reporting

### Generate Reports

```python
# Get comprehensive report
report = manager.generate_report()

print(f"Total migrations: {report.total_migrations}")
print(f"Successful: {report.successful}")
print(f"Failed: {report.failed}")
print(f"Rolled back: {report.rolled_back}")
```

### Track Individual Results

```python
# Access individual results
for result in manager._results:
    print(f"{result.migration_id}: {result.status.value}")
    print(f"  Steps: {result.steps_executed}/{result.steps_total}")
    print(f"  Time: {result.elapsed_ms:.2f}ms")
```

### Status Callbacks

```python
def on_migration_complete(result):
    print(f"[{result.migration_id}] {result.status.value}")

manager.register_status_callback(on_migration_complete)

# Now all migrations trigger the callback
manager.migrate_up()
```

## Integration with Batch Executor

```python
from batch_executor import BatchExecutor
from batch_migration import parse_migration_commands

# Parse batch commands
commands = [
    "MIGRATE UP IF PENDING",
    "MIGRATE STATUS",
]

operations = parse_migration_commands(commands)

# Execute via batch executor
executor = BatchExecutor(parser, registry)
result = executor.execute_batch(commands, client_state={})
```

## Migration Automation Patterns

### Pattern 1: Safe Deployment

```python
def safe_deploy():
    """
    Deploy with dry-run validation.
    """
    manager = get_batch_migration_manager()
    
    # Step 1: Dry-run
    dry_run = manager.migrate_up(dry_run=True)
    if dry_run.status != BatchMigrationStatus.COMPLETED:
        print("Dry-run failed, aborting")
        return False
    
    # Step 2: Backup (if implemented)
    # backup_result = manager.execute_backup()
    
    # Step 3: Apply migrations
    result = manager.migrate_up(verify=True)
    
    if result.status == BatchMigrationStatus.COMPLETED:
        print("Deployment successful")
        return True
    else:
        print(f"Deployment failed: {result.error_message}")
        # Could trigger rollback here
        return False
```

### Pattern 2: CI/CD Integration

```python
def ci_migration_check():
    """
    Check migrations in CI/CD pipeline.
    """
    manager = get_batch_migration_manager()
    
    # Check for pending migrations
    if manager.check_pending():
        # Dry-run to validate
        result = manager.migrate_up(dry_run=True)
        
        if result.status == BatchMigrationStatus.COMPLETED:
            print(f"✓ {result.steps_executed} migrations ready")
            return 0
        else:
            print(f"✗ Migration errors: {result.error_message}")
            return 1
    else:
        print("✓ No pending migrations")
        return 0
```

### Pattern 3: Blue-Green Deployment

```python
def blue_green_migration():
    """
    Support blue-green deployment with migrations.
    """
    manager = get_batch_migration_manager()
    
    # Phase 1: Backward-compatible migrations
    # These don't break old code
    compatible = manager.migrate_up(dry_run=True)
    
    # Phase 2: Deploy new code
    # deploy_code()
    
    # Phase 3: Forward-only migrations
    # These require new code
    forward = manager.migrate_up(dry_run=True)
    
    return compatible, forward
```

## Best Practices

### 1. Always Dry-Run First

```python
# Preview before applying
dry_run = manager.migrate_up(dry_run=True)
if dry_run.status == BatchMigrationStatus.COMPLETED:
    manager.migrate_up()  # Now apply
```

### 2. Verify Critical Migrations

```python
# Always verify production migrations
result = manager.migrate_up(verify=True)
assert result.verification_passed
```

### 3. Monitor Status

```python
# Register callback for monitoring
manager.register_status_callback(lambda r: 
    logger.info(f"Migration {r.migration_id}: {r.status.value}")
)
```

### 4. Handle Failures Gracefully

```python
result = manager.migrate_up()

if result.status == BatchMigrationStatus.FAILED:
    # Log detailed error
    logger.error(f"Migration failed: {result.error_message}")
    
    # Notify team
    send_alert(f"Migration {result.migration_id} failed")
    
    # Consider rollback if needed
    # manager.migrate_down(result.migration_id)
```

### 5. Clear History Periodically

```python
# Clear old results to free memory
manager.clear_results()
```

## Troubleshooting

### Migration Not Found

**Cause**: Migration ID doesn't exist in history  
**Solution**: Check migration ID or list pending migrations

```python
pending = manager.get_pending_count()
print(f"{pending} pending migrations")
```

### Verification Failed

**Cause**: Checksum mismatch or manual schema changes  
**Solution**: Recreate migration or investigate changes

### Rollback Failed

**Cause**: Dependencies or data constraints  
**Solution**: Check rollback SQL and dependencies

## See Also

- [Schema Migration](schema_migration.py)
- [Batch Operations](OPERATIONS.md)
- [Database Administration](ADMIN.md)
