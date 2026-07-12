
# Batch Replication Guide

This document describes how multi-command batches are replicated in KosDB v2.3.0.

## Overview

Batch commands (multiple SQL statements executed together) require special handling in replication to ensure:

1. **Atomicity**: All commands in a batch are replicated together
2. **Ordering**: Commands execute in the same order on slaves as on the master
3. **Consistency**: Batch boundaries are preserved across the replication topology
4. **Monitoring**: Replication lag for batches can be tracked and reported

## Binlog Format

### Single Commands

Non-batch commands are logged as individual entries:

```json
{
  "position": 100,
  "timestamp": 1705312800.123,
  "server_id": 1,
  "database": "mydb",
  "operation": "INSERT",
  "table": "users",
  "data": {"row": {"id": 1, "name": "Alice"}},
  "batch_marker": "single",
  "batch_id": null
}
```

### Batch Commands

Batch commands are logged with three types of markers:

#### 1. BATCH_START

Marks the beginning of a batch:

```json
{
  "position": 101,
  "timestamp": 1705312800.456,
  "server_id": 1,
  "database": "mydb",
  "operation": "BATCH_START",
  "table": null,
  "data": {"batch_id": "batch_001", "total_commands": 3},
  "batch_marker": "batch_start",
  "batch_id": "batch_001",
  "batch_total_commands": 3,
  "batch_error_mode": "continue"
}
```

#### 2. BATCH_COMMAND

Each individual command in the batch:

```json
{
  "position": 102,
  "timestamp": 1705312800.789,
  "server_id": 1,
  "database": "mydb",
  "operation": "INSERT",
  "table": "users",
  "data": {"row": {"id": 1, "name": "Alice"}},
  "batch_marker": "batch_command",
  "batch_id": "batch_001",
  "batch_command_index": 0,
  "batch_total_commands": 3,
  "batch_error_mode": "continue"
}
```

#### 3. BATCH_END

Marks the completion of a batch:

```json
{
  "position": 104,
  "timestamp": 1705312801.012,
  "server_id": 1,
  "database": "mydb",
  "operation": "BATCH_END",
  "table": null,
  "data": {
    "batch_id": "batch_001",
    "commands_executed": 3,
    "commands_failed": 0
  },
  "batch_marker": "batch_end",
  "batch_id": "batch_001"
}
```

## Replication Flow

### Master Side

1. **Batch Execution**: Client sends batch of commands
2. **Binlog Writing**: Master writes each command to binlog:
   - `BATCH_START` marker
   - `BATCH_COMMAND` for each command
   - `BATCH_END` marker
3. **Streaming**: Replication handler streams entries to connected slaves

### Slave Side

1. **Receive Entries**: Slave receives entries in order
2. **Apply Commands**: Each `BATCH_COMMAND` is applied individually
3. **Position Tracking**: Slave saves position after each entry
4. **Conflict Detection**: Vector clocks checked for multi-master setups

## Batch Ordering Guarantees

### Within a Batch

Commands within a batch are guaranteed to execute in the order they were written:

```sql
-- Batch executed on master
BEGIN;
UPDATE accounts SET balance = balance - 100 WHERE id = 1;
UPDATE accounts SET balance = balance + 100 WHERE id = 2;
COMMIT;

-- Replicated as:
-- [BATCH_START] -> [UPDATE id=1] -> [UPDATE id=2] -> [BATCH_END]
```

### Across Batches

Batches from the same master are applied in order:

```sql
-- Batch 1
INSERT INTO logs VALUES (1, 'event1');

-- Batch 2
INSERT INTO logs VALUES (2, 'event2');

-- Guaranteed order: Batch 1 complete before Batch 2 starts
```

### Interleaved Batches

Multiple concurrent batches are interleaved in binlog:

```sql
-- Thread A: Batch A
-- Thread B: Batch B (starts while A is running)

-- Binlog order:
-- [BATCH_START A] -> [BATCH_START B] -> [CMD A.1] -> [CMD B.1] -> ...
```

Slaves apply entries in binlog order, preserving causality.

## Replication Lag for Batches

### Lag Calculation

Replication lag for a batch is calculated as:

```
lag_entries = batch_end_position - slave_current_position
```

### Lag Reporting

```sql
-- Check batch lag
SHOW BATCH STATUS batch_001;
```

Response:
```
------------------------------------------------------------
Batch ID: batch_001
Status: lagging
Lag Entries: 150
Lag Time: ~1500ms
Master Position: 1000
Slave Position: 850
------------------------------------------------------------
```

### Lag Detection

The replication system automatically detects batch lag:

- **Current**: lag_entries < 100
- **Lagging**: lag_entries >= 100
- **Critical**: lag_entries >= 1000

## Failover Handling

### Incomplete Batch Detection

When a slave is promoted to master, it may have incomplete batches:

```sql
-- Original master had:
-- [BATCH_START] -> [CMD 1] -> [CMD 2] -> (crash before BATCH_END)

-- New master detects incomplete batch and can:
-- 1. Complete the batch if possible
-- 2. Rollback if batch_error_mode is 'rollback_all'
-- 3. Log warning for manual intervention
```

### Slave Promotion

```python
# Check for incomplete batches before promotion
active_batches = binlog.list_active_batches()

for batch in active_batches:
    if not batch['completed']:
        # Handle incomplete batch
        if batch['error_mode'] == 'rollback_all':
            rollback_batch(batch['batch_id'])
        else:
            log_warning(f"Incomplete batch: {batch['batch_id']}")
```

## Master-Master Replication

### Conflict Detection

In multi-master setups, batch commands may conflict:

```sql
-- Master A executes:
UPDATE users SET name = 'Alice' WHERE id = 1;

-- Master B executes (concurrently):
UPDATE users SET name = 'Bob' WHERE id = 1;

-- Conflict detected via vector clocks
-- Resolution strategy applied (default: server_id_priority)
```

### Vector Clocks

Each batch entry includes vector clock information:

```json
{
  "vector_clock": {
    "1": 100,  // Master A's timestamp
    "2": 95    // Master B's timestamp
  }
}
```

### Batch Consistency

Batches are treated as atomic units for conflict resolution:

- If any command in a batch conflicts, the entire batch may be rejected
- `BATCH_START` and `BATCH_END` markers help identify batch boundaries
- Conflict resolver can choose to apply winning batch in its entirety

## Monitoring

### SHOW SLAVE STATUS

Extended to show batch replication info:

```sql
SHOW SLAVE STATUS;
```

Response includes:
```
Slave_IO_State: Waiting for master to send event
Master_Log_File: binlog.001
Read_Master_Log_Pos: 1000
Exec_Master_Log_Pos: 950
Relay_Log_Space: 2048
Active_Batches: 2
Completed_Batches: 150
Batch_Conflicts: 0
```

### SHOW BATCH STATUS

New command for batch-specific status:

```sql
SHOW BATCH STATUS;
```

Response:
```
------------------------------------------------------------
Active Batches: 2
Completed Batches: 150
Failed Batches: 0

Batch Details:
  batch_151: 3/5 commands (60% complete)
  batch_152: 1/10 commands (10% complete)
------------------------------------------------------------
```

## Performance Considerations

### Batch Size

- **Small batches** (< 10 commands): Minimal overhead
- **Medium batches** (10-100 commands): Good balance
- **Large batches** (100+ commands): May cause replication lag spikes

### Replication Lag

Large batches can cause temporary lag:

```
Master: [BATCH_START] -> ...100 commands... -> [BATCH_END]
Slave:  Applies commands one at a time

Lag during batch: ~100 entries
Lag after batch: 0 entries
```

### Recommendations

1. **Keep batches reasonable**: 100-1000 commands per batch
2. **Use appropriate error modes**: 'continue' for non-critical data
3. **Monitor lag**: Set alerts for batch lag > 1000 entries
4. **Failover planning**: Document batch handling procedures

## Troubleshooting

### Incomplete Batch

**Symptom**: Slave shows incomplete batch in `SHOW BATCH STATUS`

**Resolution**:
```sql
-- Check batch details
SHOW BATCH STATUS batch_001;

-- If safe to complete:
COMPLETE BATCH batch_001;

-- Or rollback:
ROLLBACK BATCH batch_001;
```

### Batch Lag

**Symptom**: Replication lag spikes during batch execution

**Resolution**:
1. Check batch size: `SHOW BATCH STATUS`
2. Increase slave resources
3. Consider batch splitting for very large operations

### Conflict Resolution

**Symptom**: Batch conflicts in multi-master setup

**Resolution**:
```sql
-- Check conflict log
SHOW CONFLICT LOG;

-- Adjust resolution strategy if needed
SET GLOBAL conflict_resolution = 'last_write_wins';
```

## API Reference

### BatchBinlog

```python
from binlog_batch import BatchBinlog

# Initialize
binlog = BatchBinlog(data_dir="/var/lib/kosdb")

# Write batch start
pos = binlog.write_batch_start(
    server_id=1,
    database="mydb",
    batch_id="batch_001",
    total_commands=5,
    error_mode="continue"
)

# Write batch command
pos = binlog.write_batch_command(
    server_id=1,
    database="mydb",
    batch_id="batch_001",
    operation="INSERT",
    table="users",
    data={"row": {"id": 1}},
    command_index=0,
    total_commands=5,
    error_mode="continue"
)

# Write batch end
pos = binlog.write_batch_end(
    server_id=1,
    database="mydb",
    batch_id="batch_001",
    commands_executed=5,
    commands_failed=0
)

# Get batch status
status = binlog.get_batch_status("batch_001")

# List active batches
active = binlog.list_active_batches()

# Calculate lag
lag = binlog.get_batch_lag("batch_001", slave_position=900)
```

### BatchReplicationLagDetector

```python
from binlog_batch import BatchReplicationLagDetector

# Initialize
detector = BatchReplicationLagDetector(
    binlog=binlog,
    lag_threshold_ms=1000,
    check_interval=5
)

# Start monitoring
detector.start()

# Get lag report
report = detector.get_batch_lag_report(
    batch_id="batch_001",
    slave_position=900
)

# Stop monitoring
detector.stop()
```

## See Also

- [Replication Protocol](replication.py)
- [Binary Log](binlog.py)
- [Batch Error Handling](BATCH_ERROR_HANDLING.md)
- [Security Considerations](SECURITY_README.md)
