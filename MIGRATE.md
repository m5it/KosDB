
# KosDB Schema Migration Guide

This guide covers database schema migrations for KosDB, including the v2.3.0 batch commands migration.

## Overview

KosDB uses a versioned schema migration system that allows:
- Safe upgrades between versions
- Rollback support for downgrades
- Idempotent migrations (can run multiple times safely)
- Migration history tracking

## Migration Files

Migrations are stored in the `migrations/` directory:

```
migrations/
├── v2_3_0_batch_commands.py  # v2.3.0 - Batch commands support
└── README.md                 # Migration documentation
```

## Current Migrations

### v2.3.0 - Batch Commands Support

**Version:** 2.3.0  
**Date:** 2024-01-15  
**Description:** Adds batch command execution support with audit logging

#### Changes

1. **New Tables:**
   - `batch_audit_log` - Audit log for batch command execution
   - `batch_metrics` - Performance metrics for batches
   - `schema_migrations` - Migration history tracking

2. **Updated Tables:**
   - `audit_log` - Added batch_id, is_batch_command, batch_index columns

3. **Version Marker:**
   - Updates version from 2.2.0 to 2.3.0

## Running Migrations

### Python API

```python
from migrations.v2_3_0_batch_commands import run_migration, run_rollback

# Run migration
success = run_migration('kosdb.db')

# Rollback
success = run_rollback('kosdb.db')
```

### Command Line

```bash
# Run migration
python migrations/v2_3_0_batch_commands.py --db kosdb.db

# Verify migration
python migrations/v2_3_0_batch_commands.py --db kosdb.db --verify

# Rollback
python migrations/v2_3_0_batch_commands.py --db kosdb.db --rollback
```

## Migration Process

### 1. Pre-Migration Check

Before running migrations:

```python
from migrations.v2_3_0_batch_commands import V2_3_0_Migration

migration = V2_3_0_Migration(db_connection)

# Check if applicable
if migration.is_applicable():
    print("Migration can be applied")
    
# Check if already applied (idempotent)
if migration.is_idempotent():
    print("Migration already applied")
```

### 2. Running Migration

```python
# Execute migration
success = migration.migrate()

if success:
    print("Migration completed")
    # Verify
    migration.verify()
else:
    print("Migration failed")
    print(migration.errors)
```

### 3. Rollback (If Needed)

```python
# Rollback to previous version
success = migration.rollback()

if success:
    print("Rollback completed")
else:
    print("Rollback failed")
```

## Idempotent Migrations

All KosDB migrations are designed to be idempotent - they can be run multiple times without causing errors.

```python
# Safe to run multiple times
migration.migrate()  # First run - applies changes
migration.migrate()  # Second run - detects already applied, skips
```

## Migration Verification

After running a migration, verify it was applied correctly:

```python
checks = [
    ("Version marker", migration._get_current_version() == "2.3.0"),
    ("Migrations table", migration._table_exists("schema_migrations")),
    ("Batch audit table", migration._table_exists("batch_audit_log")),
    ("Batch metrics table", migration._table_exists("batch_metrics")),
]

for name, passed in checks:
    status = "✓" if passed else "✗"
    print(f"{status} {name}")
```

## Schema Version Tracking

KosDB tracks schema versions in multiple ways:

### 1. Database Version Table

```sql
SELECT * FROM db_version;
-- version | updated_at
-- 2.3.0   | 1705312800.0
```

### 2. Schema Migrations Table

```sql
SELECT migration_id, version, applied_at, status 
FROM schema_migrations;
-- mig_v2_3_0 | 2.3.0 | 1705312800.0 | APPLIED
```

### 3. Application Check

```python
from leveldb_client import LevelDBClient

client = LevelDBClient()
client.connect()
client.auth('admin', 'admin')

# Check server version
result = client.execute("MIGRATE STATUS")
print(result)
```

## Batch Command Tables

### batch_audit_log

Stores audit information for batch command execution:

| Column | Type | Description |
|--------|------|-------------|
| event_id | TEXT | Unique event identifier |
| timestamp | REAL | Event timestamp |
| user_id | TEXT | User who executed batch |
| client_ip | TEXT | Client IP address |
| batch_id | TEXT | Batch identifier |
| command_count | INTEGER | Number of commands |
| commands | TEXT | JSON array of commands |
| results | TEXT | JSON array of results |
| success_count | INTEGER | Successful commands |
| error_count | INTEGER | Failed commands |
| execution_time_ms | REAL | Execution time |
| risk_score | INTEGER | Security risk score |
| metadata | TEXT | JSON metadata |

### batch_metrics

Stores performance metrics:

| Column | Type | Description |
|--------|------|-------------|
| metric_id | TEXT | Unique metric identifier |
| timestamp | REAL | Metric timestamp |
| batch_size | INTEGER | Number of commands |
| avg_command_time_ms | REAL | Average command time |
| total_time_ms | REAL | Total execution time |
| cache_hit_rate | REAL | Command cache hit rate |
| commands_per_second | REAL | Throughput |
| user_id | TEXT | User identifier |
| metadata | TEXT | JSON metadata |

## Troubleshooting

### Migration Already Applied

```
Migration v2.3.0 already applied (idempotent)
```

This is expected behavior. Migrations can be run multiple times safely.

### Migration Not Applicable

```
Migration not applicable (current version: 2.3.0)
```

The migration is for an older version. Check if you're trying to run the right migration.

### Rollback Limitations

Some migrations have limitations on rollback due to SQLite constraints:

- **DROP COLUMN**: SQLite doesn't support DROP COLUMN, so added columns remain
- **Data Loss**: Rollback may lose data added since migration

### Manual Recovery

If migration fails:

1. Check error messages in `migration.errors`
2. Verify database connection
3. Check disk space
4. Try running with `--verify` to check state
5. Consider manual rollback if needed

## Best Practices

1. **Backup First**: Always backup database before migration
2. **Test in Staging**: Test migrations in staging environment first
3. **Monitor**: Monitor application during and after migration
4. **Idempotent**: Design migrations to be idempotent
5. **Document**: Document all schema changes
6. **Version Control**: Keep migrations in version control

## Migration Checklist

Before running migration:

- [ ] Backup database
- [ ] Check current version
- [ ] Verify migration applicability
- [ ] Ensure sufficient disk space
- [ ] Schedule maintenance window
- [ ] Notify stakeholders

After migration:

- [ ] Verify migration success
- [ ] Check application functionality
- [ ] Monitor error logs
- [ ] Update documentation
- [ ] Notify stakeholders

## See Also

- [Schema Migration API](schema_migration.py)
- [Batch Commands](BATCH_README.md)
- [Security Features](SECURITY_README.md)
