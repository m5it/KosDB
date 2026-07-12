
# Batch Backup/Restore Operations Guide

Version: 2.3.0  
Last Updated: 2024-01-15

## Overview

Batch Backup/Restore Operations enable efficient database backup and restore workflows within batch command sequences. Supports conditional backups, verification chains, and automated backup strategies.

## Features

- **Batch Backups**: Execute multiple backups in a single batch
- **Conditional Backups**: `BACKUP IF <condition>` for smart backup decisions
- **Restore Verification**: Built-in integrity checking before restore
- **Backup Chaining**: Sequence multiple operations (backup → verify → compress → upload)
- **Status Monitoring**: Real-time status callbacks and operation tracking

## Quick Start

```python
from batch_backup import BatchBackupManager, get_batch_backup_manager

# Create backup manager
manager = get_batch_backup_manager('./backups')

# Simple backup
result = manager.execute_backup(
    source_db='mydb',
    target_file='mydb_backup.json.gz'
)

print(f"Backup: {result.status.value}, File: {result.file_path}")
```

## SQL Commands

### BACKUP

```sql
-- Simple backup
BACKUP mydb;

-- Backup with target file
BACKUP mydb TO backup_2024.json.gz;

-- Backup specific tables
BACKUP mydb TABLES users, orders, products;

-- Conditional backup
BACKUP mydb IF size > 1000 TO conditional_backup.json.gz;
```

### RESTORE

```sql
-- Simple restore
RESTORE backup.json.gz TO mydb;

-- Restore with verification
RESTORE backup.json.gz TO mydb VERIFY;
```

### VERIFY

```sql
-- Verify backup integrity
VERIFY BACKUP backup.json.gz;
```

## Conditional Backups

### Supported Conditions

```python
from batch_backup import BatchBackupManager

manager = BatchBackupManager('./backups')

# Check database size
context = {'db_size': 1500}  # MB
should_backup = manager.check_condition('size > 1000', context)

# Check row count
context = {'row_count': 50000}
should_backup = manager.check_condition('count > 10000', context)

# Check time of day
should_backup = manager.check_condition('time > 02:00', {})

# Custom conditions
context = {'custom_metric': 42}
should_backup = manager.check_condition('custom_metric > 40', context)
```

### Use Case: Smart Daily Backups

```python
def smart_daily_backup(db_name, backup_dir='./backups'):
    """
    Only backup if database has grown significantly.
    """
    manager = BatchBackupManager(backup_dir)
    
    # Get database metrics (simulated)
    db_stats = {
        'db_size': get_db_size(db_name),
        'row_count': get_row_count(db_name),
        'last_backup_size': get_last_backup_size(db_name)
    }
    
    # Check if backup is warranted
    if manager.check_condition('size > 1000', db_stats):
        result = manager.execute_backup(
            source_db=db_name,
            target_file=f'{db_name}_daily.json.gz'
        )
        return result
    
    print("Backup skipped - no significant changes")
    return None
```

## Backup Chaining

### Execute Multiple Operations

```python
# Define a chain of operations
operations = [
    {'type': 'backup', 'source_db': 'prod_db', 'target_file': 'prod.json.gz'},
    {'type': 'verify', 'file_path': './backups/prod.json.gz'},
    {'type': 'backup', 'source_db': 'analytics_db', 'target_file': 'analytics.json.gz'},
]

result = manager.execute_chain(operations)

print(f"Chain: {result.successful}/{result.total_operations} successful")
print(f"Total time: {result.total_elapsed_ms:.2f}ms")
```

### Error Handling in Chains

```python
# Continue on error for non-critical operations
operations = [
    {'type': 'backup', 'source_db': 'critical_db', 'target_file': 'critical.json.gz'},
    {'type': 'backup', 'source_db': 'cache_db', 'target_file': 'cache.json.gz', 
     'continue_on_error': True},  # Non-critical
    {'type': 'verify', 'file_path': './backups/critical.json.gz'},
]

result = manager.execute_chain(operations)
# Chain continues even if cache backup fails
```

## Restore with Verification

### Basic Restore

```python
result = manager.execute_restore(
    source_file='backup.json.gz',
    target_db='restored_db',
    verify=True  # Verify before restore
)

if result.status == BackupStatus.COMPLETED:
    print(f"Restored to {result.metadata['target_database']}")
else:
    print(f"Restore failed: {result.error_message}")
```

### Pre-Restore Validation

```python
# Check backup validity before attempting restore
verify_result = manager.execute_verify('backup.json.gz')

if verify_result.status == BackupStatus.VERIFIED:
    print("Backup verified, safe to restore")
    # Proceed with restore...
else:
    print(f"Backup verification failed: {verify_result.error_message}")
```

## Status Monitoring

### Register Status Callbacks

```python
def on_backup_status(result):
    print(f"[{result.operation}] {result.status.value}: {result.file_path}")
    
    # Send alert on failure
    if result.status == BackupStatus.FAILED:
        send_alert(f"Backup failed: {result.error_message}")

manager.register_status_callback(on_backup_status)

# Now all operations will trigger the callback
manager.execute_backup('mydb', 'backup.json.gz')
```

### Operation History

```python
# Get all operations performed
operations = manager.get_operations()

for op in operations:
    print(f"{op.operation}: {op.status.value} in {op.elapsed_ms:.2f}ms")
    
# Clear history when needed
manager.clear_operations()
```

## Automated Backup Strategies

### Strategy 1: Tiered Backups

```python
def tiered_backup_strategy(databases, backup_dir='./backups'):
    """
    Different backup frequencies based on database criticality.
    """
    manager = BatchBackupManager(backup_dir)
    
    tiers = {
        'critical': ['production_db', 'user_data'],
        'daily': ['analytics', 'reports'],
        'weekly': ['logs', 'archives']
    }
    
    results = {}
    
    for tier, dbs in tiers.items():
        for db in dbs:
            if db in databases:
                result = manager.execute_backup(
                    source_db=db,\n                    target_file=f'{db}_{tier}.json.gz'
                )
                results[db] = result
    
    return results
```

### Strategy 2: Incremental with Verification

```python
def verified_incremental_backup(db_name, backup_dir='./backups'):
    """
    Backup with immediate verification.
    """
    manager = BatchBackupManager(backup_dir)
    
    # Step 1: Backup
    backup_result = manager.execute_backup(
        source_db=db_name,\n        target_file=f'{db_name}_incremental.json.gz'
    )
    
    if backup_result.status != BackupStatus.COMPLETED:
        return backup_result
    
    # Step 2: Verify
    verify_result = manager.execute_verify(backup_result.file_path)
    
    if verify_result.status != BackupStatus.VERIFIED:
        # Mark backup as suspect
        logger.warning(f"Backup verification failed for {db_name}")
    
    return backup_result
```

### Strategy 3: Conditional Chain

```python
def conditional_backup_chain(backup_dir='./backups'):
    """
    Execute different chains based on conditions.
    """
    manager = BatchBackupManager(backup_dir)
    
    # Check if it's time for full backup
    if datetime.now().hour == 2:  # 2 AM\n        # Full backup chain
        operations = [\n            {'type': 'backup', 'source_db': 'main', 'target_file': 'main_full.json.gz'},
            {'type': 'verify', 'file_path': './backups/main_full.json.gz'},
            {'type': 'backup', 'source_db': 'analytics', 'target_file': 'analytics.json.gz'},
        ]
n    else:\n        # Quick backup chain\n        operations = [\n            {'type': 'backup', 'source_db': 'main', 'target_file': 'main_quick.json.gz'},
n        ]\n    \n    return manager.execute_chain(operations)
```

## Integration with Batch Executor

```python
from batch_executor import BatchExecutor\nfrom batch_backup import parse_backup_chain

# Parse batch commands\ncommands = [
    \"BACKUP production_db TO prod_backup.json.gz\",\n    \"VERIFY BACKUP prod_backup.json.gz\",\n    \"BACKUP analytics_db TO analytics_backup.json.gz\",\n]

# Parse to operations\noperations = parse_backup_chain(commands)

# Execute via batch executor\nexecutor = BatchExecutor(parser, registry)\nresult = executor.execute_batch(commands, client_state={})
```

## Best Practices

### 1. Always Verify Critical Backups

```python
# Verify before considering backup complete\nresult = manager.execute_backup('critical_db', 'critical.json.gz')
nif result.status == BackupStatus.COMPLETED:
n    verify = manager.execute_verify(result.file_path)
n    if verify.status != BackupStatus.VERIFIED:
n        logger.error(\"Backup verification failed!\")
```

### 2. Use Conditional Backups for Efficiency

```python
# Only backup if there's significant change\ncontext = {'db_size': current_size, 'last_size': previous_size}\nif manager.check_condition('db_size > last_size * 1.1', context):  # 10% growth
n    manager.execute_backup('mydb', 'incremental.json.gz')
```

### 3. Handle Errors Gracefully

```python
result = manager.execute_backup('mydb', 'backup.json.gz')

if result.status == BackupStatus.FAILED:
n    # Log error\n    logger.error(f\"Backup failed: {result.error_message}\")\n    \n    # Notify administrators\n    send_alert(f\"Backup failure: {result.error_message}\")\n    \n    # Attempt retry or fallback\n    retry_backup_with_fallback(manager, 'mydb')
```

### 4. Monitor Backup Metrics

```python
# Track backup performance over time\nmetrics = []\nfor op in manager.get_operations():\n    if op.operation == 'backup':\n        metrics.append({\n            'time': op.elapsed_ms,\n            'size': op.size_bytes,\n            'throughput': op.size_bytes / (op.elapsed_ms / 1000)\n        })

# Analyze trends\navg_time = sum(m['time'] for m in metrics) / len(metrics)
print(f\"Average backup time: {avg_time:.2f}ms\")
```

## Troubleshooting

### Backup Fails with Permission Error

**Cause**: Insufficient permissions for backup directory  
**Solution**: Ensure backup directory is writable

```python
import os
backup_dir = './backups'
os.makedirs(backup_dir, exist_ok=True, mode=0o755)
```

### Verification Fails on Valid Backup

**Cause**: Checksum mismatch or format version difference  
**Solution**: Re-create backup with current format

```python
# Force new backup format\nresult = manager.execute_backup('mydb', 'backup.json.gz', compress=True)
```

### Chain Stops on First Error

**Cause**: Default behavior stops on failure  
**Solution**: Use `continue_on_error: True` for non-critical operations

```python
operations = [
    {'type': 'backup', 'source_db': 'db1', 'continue_on_error': True},
]
```

## See Also

- [Backup Utilities](backup_utils.py)
- [Batch Operations](OPERATIONS.md)
- [Database Administration](ADMIN.md)
