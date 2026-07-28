# Replication Testing Guide

## Overview

This document describes how to test the replication features of the LevelDB Socket Server.

## Test Files

- `tests/test_replication.py` - Automated replication test suite
- `tests/test_client.py` - Basic client functionality tests

## Running Automated Tests

### Prerequisites

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create admin users for test servers:
```bash
python server.py --prepare_admin admin --prepare_password admin --data_dir ./test_data_master
```

### Run Replication Tests

```bash
python tests/test_replication.py
```

This will:
1. Start a master server on port 9999
2. Start a slave server on port 9998
3. Test basic replication (insert on master, verify on slave)
4. Test slave recovery (stop slave, insert data, restart, verify catch-up)
5. Clean up test data

## Manual Testing

### Test 1: Master-Slave Setup

**Step 1: Start Master**
```bash
# Terminal 1
python server.py --server-id 1 --role master --replication-port 10999 --data_dir ./data_master
```

**Step 2: Create Replication User**
```bash
# Connect to master
nc localhost 9999
> USER admin
> PASS yourpassword
> CREATE REPLICATION USER repl IDENTIFIED BY replpass
```

**Step 3: Start Slave**
```bash
# Terminal 2
python server.py --server-id 2 --role slave --master-host localhost:9999 --data_dir ./data_slave
```

**Step 4: Test Replication**
```bash
# Connect to master
nc localhost 9999
> USER admin
> PASS yourpassword
> CREATE DATABASE testdb
> USE testdb
> CREATE TABLE users (id INT PRIMARY KEY, name TEXT)
> INSERT INTO users VALUES (1, 'Alice')

# Connect to slave (port 9998)
nc localhost 9998
> USER admin
> PASS yourpassword
> USE testdb
> SELECT * FROM users
# Should see: Alice
```

### Test 2: Master-Master Setup

**Step 1: Start Server A**
```bash
python server.py --server-id 1 --port 9999 --replication-port 10999 --peer-host localhost:9998 --data_dir ./data_a
```

**Step 2: Start Server B**
```bash
python server.py --server-id 2 --port 9998 --replication-port 10998 --peer-host localhost:9999 --data_dir ./data_b
```

**Step 3: Test Bi-Directional Replication**
```bash
# Connect to Server A, insert data
nc localhost 9999
> USER admin
> PASS admin
> CREATE DATABASE mmtest
> USE mmtest
> CREATE TABLE items (id INT PRIMARY KEY, name TEXT)
> INSERT INTO items VALUES (1, 'FromA')

# Connect to Server B, verify and insert
nc localhost 9998
> USER admin
> PASS admin
> USE mmtest
> SELECT * FROM items
# Should see: FromA
> INSERT INTO items VALUES (2, 'FromB')

# Back to Server A, verify
> SELECT * FROM items
# Should see both: FromA, FromB
```

### Test 3: Replication Commands

**SHOW MASTER STATUS**
```sql
> SHOW MASTER STATUS
--------------------
Master Status
--------------------
Binlog Position: 150
Server ID: 1
Connected Slaves: 1
--------------------
```

**SHOW SLAVE STATUS**
```sql
> SHOW SLAVE STATUS
--------------------
Slave Status
--------------------
Slave IO State: Connected
Master Host: localhost
Master Port: 9999
Last Applied Position: 150
Master Binlog Position: 150
--------------------
```

**RESET SLAVE**
```sql
> RESET SLAVE
OK: Slave reset - will start from beginning
```

## Troubleshooting

### Slave not connecting
- Check firewall settings
- Verify master is running with `--replication-port`
- Check replication user exists with correct password

### Data not replicating
- Check `SHOW MASTER STATUS` on master
- Check `SHOW SLAVE STATUS` on slave
- Look for errors in server logs
- Verify network connectivity

### Conflict in Master-Master
- Each server should have unique `--server-id`
- The replication protocol skips entries from same server-id
- Last-write-wins based on timestamp

## Expected Behavior

1. **Master-Slave**: All writes on master appear on slave within seconds
2. **Slave Recovery**: When slave reconnects, it catches up on missed entries
3. **Master-Master**: Writes on either server appear on the other
4. **Loop Prevention**: Entries are not re-applied to originating server

## Performance Notes

- Replication is asynchronous (not waiting for slave acknowledgment)
- Binlog entries are streamed in batches
- Position tracking ensures no duplicate processing
- Exponential backoff on connection failures