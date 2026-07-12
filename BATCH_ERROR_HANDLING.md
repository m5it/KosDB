
# Batch Execution Error Handling Guide

KosDB v2.3.0 introduces configurable error handling strategies for batch command execution. This guide explains the three error modes and provides recommendations for different use cases.

## Overview

When executing multiple commands in a batch, you can choose how the system should handle errors:

1. **CONTINUE** (default) - Execute all commands, report all results
2. **STOP_ON_ERROR** - Halt execution on first error
3. **ROLLBACK_ALL** - Rollback all changes if any command fails

## Error Modes

### 1. CONTINUE Mode (Default)

```json
{
  "batch": {
    "batch_error_mode": "continue"
  }
}
```

**Behavior:**
- All commands are executed regardless of individual failures
- Each command's success or failure is reported separately
- Failed commands don't affect other commands in the batch
- Partial success is allowed

**Use Cases:**
- Data import scripts where some rows may fail
- Bulk operations where individual failures are acceptable
- Reporting queries that should complete even if some fail
- Migration scripts with optional steps

**Example:**
```sql
-- All commands execute, errors reported individually
INSERT INTO users VALUES (1, 'Alice');  -- Success
INSERT INTO users VALUES (1, 'Bob');    -- Fails (duplicate)
INSERT INTO users VALUES (2, 'Charlie'); -- Success
-- Result: 2 succeeded, 1 failed
```

**Response Format:**
```
Batch Execution [abc123]: 3 commands (mode: continue)
--------------------------------------------------
[1/3] OK: INSERT INTO users VALUES (1, 'Alice')
OK: Inserted into 'users'

[2/3] ERROR: INSERT INTO users VALUES (1, 'Bob')
  Error: Duplicate key
ERROR: Duplicate key

[3/3] OK: INSERT INTO users VALUES (2, 'Charlie')
OK: Inserted into 'users'

==================================================
Batch Complete [abc123]:
  Commands: 3
  Succeeded: 2
  Failed: 1
  Time: 15.23ms
```

---

### 2. STOP_ON_ERROR Mode

```json
{
  "batch": {
    "batch_error_mode": "stop_on_error"
  }
}
```

**Behavior:**
- Execution stops immediately on first error
- Remaining commands are not executed
- Error details include which command failed
- Faster failure for critical operations

**Use Cases:**
- Critical data updates where partial success is unacceptable
- Transaction-like behavior without explicit transactions
- Validation batches where early failure is preferred
- CI/CD database migrations

**Example:**
```sql
-- Stops at second command
UPDATE accounts SET balance = balance - 100 WHERE id = 1;  -- Success
UPDATE accounts SET balance = balance + 100 WHERE id = 999; -- Fails (not found)
UPDATE accounts SET balance = balance + 100 WHERE id = 2;  -- Never executed
-- Result: Stopped at command 2
```

**Response Format:**
```
Batch Execution [def456]: 3 commands (mode: stop_on_error)
--------------------------------------------------
[1/3] OK: UPDATE accounts SET balance = balance - 100 WHERE id = 1
OK: Updated 1 row(s)

[2/3] ERROR: UPDATE accounts SET balance = balance + 100 WHERE id = 999
  Error: Row not found
ERROR: Row not found

--- STOPPED at command 2 due to error ---

==================================================
Batch Complete [def456]:
  Commands: 2
  Succeeded: 1
  Failed: 1
  Time: 8.45ms
```

---

### 3. ROLLBACK_ALL Mode

```json
{
  "batch": {
    "batch_error_mode": "rollback_all"
  }
}
```

**Behavior:**
- All changes are rolled back if any command fails
- Requires transaction support (BEGIN/COMMIT/ROLLBACK)
- Provides atomic batch execution
- Either all commands succeed or none do

**Use Cases:**
- Financial transactions requiring ACID compliance
- Multi-table updates that must succeed together
- Data consistency requirements
- Complex business logic operations

**Example:**
```sql
-- All rolled back if any fails
BEGIN;
UPDATE accounts SET balance = balance - 100 WHERE id = 1;
UPDATE accounts SET balance = balance + 100 WHERE id = 999; -- Fails
UPDATE accounts SET balance = balance + 100 WHERE id = 2;
COMMIT;
-- Result: ROLLED BACK - no changes applied
```

**Response Format:**
```
Batch Execution [ghi789]: 4 commands (mode: rollback_all)
--------------------------------------------------
[1/4] OK: BEGIN
OK: Transaction started

[2/4] OK: UPDATE accounts SET balance = balance - 100 WHERE id = 1
OK: Updated 1 row(s)

[3/4] ERROR: UPDATE accounts SET balance = balance + 100 WHERE id = 999
  Error: Row not found
ERROR: Row not found

[4/4] OK: ROLLBACK
OK: Transaction rolled back

==================================================
Batch Complete [ghi789]:
  Commands: 4
  Succeeded: 3
  Failed: 1
  Time: 12.67ms
  Status: ROLLED BACK
```

---

## Configuration

### Global Configuration

Set the default error mode in `config.json`:

```json
{
  "batch": {
    "enabled": true,
    "batch_error_mode": "continue",
    "continue_on_error": true,
    "transaction_support": true
  }
}
```

### Per-Batch Override

Error mode can be specified per batch execution:

```python
# Python client
result = client.execute_batch(
    commands,
    error_mode="rollback_all"  # Override global setting
)
```

### Environment Variable

```bash
export KOSDB_BATCH_ERROR_MODE=stop_on_error
```

---

## Error Context

Every error includes detailed context:

| Field | Description |
|-------|-------------|
| `index` | Command number in batch (1-based) |
| `command` | The actual SQL command that failed |
| `error_code` | Machine-readable error code |
| `error_message` | Human-readable error description |
| `execution_time_ms` | Time taken before failure |

**Example Error Context:**
```json
{
  "index": 3,
  "command": "INSERT INTO users VALUES (1, 'Bob')",
  "status": "ERROR",
  "error_code": "DUPLICATE_KEY",
  "error_message": "Duplicate entry '1' for key 'PRIMARY'",
  "execution_time_ms": 2.34
}
```

---

## Checking Batch Status

### BATCH STATUS Command

Check the status of the most recent batch:

```sql
BATCH STATUS;
```

Check a specific batch by ID:

```sql
BATCH STATUS abc123;
```

**Response:**
```
------------------------------------------------------------
Batch ID: abc123
Timestamp: 1705312800.123
User: admin
Commands: 3
Error Mode: continue
Total Time: 15.23ms
Success: 2
Errors: 1
Status: COMPLETED

Failed Commands:
  [2] INSERT INTO users VALUES (1, 'Bob')
      Error: Duplicate key
------------------------------------------------------------
```

### Programmatic Access

```python
# Get last batch status
status = client.execute("BATCH STATUS")

# Get specific batch
status = client.execute("BATCH STATUS abc123")
```

---

## Batch History

All batch executions are recorded in the `batch_history` table:

```sql
-- View recent batches
SELECT * FROM batch_history 
ORDER BY timestamp DESC 
LIMIT 10;
```

**Stored Information:**
- Batch ID and timestamp
- User who executed the batch
- Error mode used
- Command count and results
- Success/error counts
- Rollback status
- Execution time

---

## Recommendations

### When to Use CONTINUE

✅ **Recommended for:**
- Bulk data imports from external sources
- Migration scripts with optional steps
- Reporting queries with multiple metrics
- Data validation scripts
- Non-critical background tasks

❌ **Avoid for:**
- Financial transactions
- Critical data updates
- Operations requiring consistency

---

### When to Use STOP_ON_ERROR

✅ **Recommended for:**
- Database migrations in CI/CD
- Schema changes
- Critical configuration updates
- Validation before major operations
- Development and testing

❌ **Avoid for:**
- Production bulk operations
- Long-running data imports
- When partial success is acceptable

---

### When to Use ROLLBACK_ALL

✅ **Recommended for:**
- Financial transactions
- Multi-table updates
- Inventory management
- User account operations
- Any operation requiring atomicity

❌ **Avoid for:**
- Read-only queries (unnecessary overhead)
- Very large batches (memory implications)
- When partial success is acceptable

---

## Best Practices

### 1. Choose Appropriate Mode

```python
# Data import - use CONTINUE
if operation_type == 'import':
    mode = 'continue'

# Critical update - use ROLLBACK_ALL
if operation_type == 'payment':
    mode = 'rollback_all'

# Migration - use STOP_ON_ERROR
if operation_type == 'migration':
    mode = 'stop_on_error'
```

### 2. Always Check Results

```python
result = client.execute_batch(commands)

# Check summary
if result.error_count > 0:
    logger.warning(f"Batch had {result.error_count} errors")
    
    # Examine individual errors
    for cmd in result.commands:
        if cmd.status == 'ERROR':
            logger.error(f"Command {cmd.index} failed: {cmd.error_message}")
```

### 3. Use BATCH STATUS for Debugging

```python
# After batch execution
status = client.execute("BATCH STATUS")

# Log for debugging
logger.info(f"Batch {status['batch_id']}: "
            f"{status['success_count']}/{status['command_count']} succeeded")
```

### 4. Handle Rollback Scenarios

```python
result = client.execute_batch(commands, error_mode='rollback_all')

if 'ROLLED BACK' in result:
    logger.info("Batch was rolled back due to errors")
    # Notify user, retry, or handle as needed
```

### 5. Monitor Batch History

```sql
-- Find batches with high error rates
SELECT 
    user_id,
    COUNT(*) as batch_count,
    SUM(error_count) as total_errors
FROM batch_history
WHERE timestamp > datetime('now', '-1 day')
GROUP BY user_id
HAVING total_errors > 10;
```

---

## Error Code Reference

| Code | Description | Typical Cause |
|------|-------------|---------------|
| `PARSE_ERROR` | SQL syntax error | Invalid SQL syntax |
| `PERMISSION_DENIED` | Insufficient privileges | User lacks required permissions |
| `DUPLICATE_KEY` | Unique constraint violation | Inserting duplicate primary key |
| `FOREIGN_KEY_VIOLATION` | Referential integrity error | Referenced row doesn't exist |
| `TABLE_NOT_FOUND` | Table doesn't exist | Typo or missing table |
| `DATABASE_NOT_FOUND` | Database doesn't exist | Wrong database name |
| `TIMEOUT` | Execution timeout | Query too slow or deadlock |
| `ROLLBACK_TRIGGERED` | Automatic rollback | Error in ROLLBACK_ALL mode |
| `EXECUTION_ERROR` | General execution error | Unexpected runtime error |

---

## Troubleshooting

### "ROLLBACK_ALL requires transaction support"

**Cause:** Database doesn't support transactions or transaction commands not available.

**Solution:**
- Ensure `transaction_support: true` in config
- Verify database supports BEGIN/COMMIT/ROLLBACK
- Check that transaction commands are registered

### "Batch stopped unexpectedly"

**Cause:** STOP_ON_ERROR mode encountered an error.

**Solution:**
- Check BATCH STATUS for details
- Review error message and command
- Consider using CONTINUE mode if partial success is acceptable

### "No batch execution found"

**Cause:** BATCH STATUS called before any batch execution.

**Solution:**
- Execute a batch first
- Check correct user context
- Verify batch history is enabled

---

## Migration from v2.2.0

If upgrading from v2.2.0:

1. Update `config.json` with batch settings
2. Run database migration: `python migrations/v2_3_0_batch_commands.py`
3. Default error mode is CONTINUE (backward compatible)
4. Existing batch behavior unchanged

---

## See Also

- [Batch Commands Guide](BATCH_README.md)
- [Command Splitting](COMMAND_SPLITTING.md)
- [Security Considerations](SECURITY_README.md)
- [Migration Guide](MIGRATE.md)
