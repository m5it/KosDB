# LevelDB Socket Server - Client Examples

This directory contains official client libraries and usage examples for connecting to the LevelDB Socket Server from PHP and Python applications.

## Directory Structure

```
examples/
├── README.md              # This file
├── php/
│   ├── LevelDBClient.php  # PHP client library
│   ├── basic_example.php  # Basic CRUD operations
│   └── replication_example.php  # Replication features
└── python/
    ├── leveldb_client.py  # Python client library
    ├── basic_example.py   # Basic CRUD operations
    └── replication_example.py   # Replication features
```

## PHP Examples

### Prerequisites

- PHP 7.4+ with sockets extension enabled
- LevelDB server running (see main README)

### Files

- **LevelDBClient.php** - Full-featured client library with:
  - Connection management
  - Authentication
  - CRUD operations
  - Result parsing
  - Replication support

### Usage

```php
<?php
require_once 'LevelDBClient.php';

// Simple usage
$client = new LevelDBClient('localhost', 9999);
$client->connect();
$client->authenticate('admin', 'admin');

// Create database and table
$client->createDatabase('myapp');
$client->useDatabase('myapp');
$client->createTable('users', ['id INT PRIMARY KEY', 'name TEXT']);

// Insert data
$client->insert('users', [1, 'John Doe']);

// Query data
$users = $client->select('users');
foreach ($users as $user) {
    echo $user['name'];
}

$client->close();
?>
```

### Run Examples

```bash
cd examples/php
php basic_example.php
php replication_example.php
```

## Python Examples

### Prerequisites

- Python 3.7+
- LevelDB server running (see main README)

### Files

- **leveldb_client.py** - Full-featured client library with:
  - Synchronous and async support
  - Context managers for easy resource management
  - Type hints for better IDE support
  - Result parsing
  - Connection pooling ready

### Usage

```python
from leveldb_client import LevelDBClient, connect

# Method 1: Context manager (recommended)
with connect('localhost', 9999, 'admin', 'admin') as db:
    db.create_database('myapp')
    db.use('myapp')
    db.create_table('users', ['id INT', 'name TEXT'])
    db.insert('users', [1, 'John'])
    result = db.select('users')
    print(result)

# Method 2: Direct usage
client = LevelDBClient('localhost', 9999)
client.connect()
client.auth('admin', 'admin')
result = client.query("SELECT * FROM users")
client.close()
```

### Run Examples

```bash
cd examples/python
python basic_example.py
python replication_example.py
```

## Quick Reference

### Connection

| Language | Code |
|----------|------|
| PHP | `$client = new LevelDBClient('localhost', 9999);` |
| Python | `client = LevelDBClient('localhost', 9999)` |

### Authentication

| Language | Code |
|----------|------|
| PHP | `$client->authenticate('admin', 'admin');` |
| Python | `client.auth('admin', 'admin')` |

### Create Database

| Language | Code |
|----------|------|
| PHP | `$client->createDatabase('mydb');` |
| Python | `client.create_database('mydb')` |

### Insert

| Language | Code |
|----------|------|
| PHP | `$client->insert('users', [1, 'John']);` |
| Python | `client.insert('users', [1, 'John'])` |

### Select

| Language | Code |
|----------|------|
| PHP | `$users = $client->select('users', 'age>18');` |
| Python | `users = client.select('users', 'age>18')` |

## Advanced Features

### PHP Advanced

```php
// Replication status
$status = $client->showMasterStatus();
$status = $client->showSlaveStatus();

// List databases/tables
$databases = $client->listDatabases();
$tables = $client->listTables();

// Raw query
$result = $client->execute("SELECT * FROM users WHERE id=1");
```

### Python Advanced

```python
# Async client for high performance
from leveldb_client import AsyncLevelDBClient
import asyncio

async def main():
    async with AsyncLevelDBClient() as db:
        await db.auth('admin', 'admin')
        result = await db.execute("SELECT * FROM users")

asyncio.run(main())

# Context manager
from leveldb_client import connect

with connect('localhost', 9999, 'admin', 'admin') as db:
    result = db.select('users')
```

## Error Handling

### PHP

```php
try {
    $client = new LevelDBClient('localhost', 9999);
    $client->connect();
    $client->authenticate('admin', 'wrongpass');
} catch (Exception $e) {
    echo "Error: " . $e->getMessage();
}
```

### Python

```python
from leveldb_client import LevelDBClient, AuthenticationError

try:
    client = LevelDBClient('localhost', 9999)
    client.connect()
    client.auth('admin', 'wrongpass')
except AuthenticationError as e:
    print(f"Auth failed: {e}")
except ConnectionError as e:
    print(f"Connection failed: {e}")
```

## Best Practices

1. **Always use context managers** (Python) or **try-finally** (PHP) to ensure connections close
2. **Reuse connections** when making multiple queries
3. **Handle exceptions** properly in production code
4. **Use prepared statements** concept - validate inputs before sending
5. **Set appropriate timeouts** based on your network latency

## Troubleshooting

### Connection Refused
- Check if server is running: `python server.py`
- Verify host and port are correct
- Check firewall settings

### Authentication Failed
- Verify username and password
- Check if user exists: `SHOW USERS` as admin
- Create user if needed: `CREATE REPLICATION USER`

### Timeout
- Increase timeout in client constructor
- Check network connectivity
- Verify server is responsive

## Contributing

When adding new examples:
1. Follow existing code style
2. Include error handling
3. Add comments explaining complex operations
4. Update this README

## License

Same as main project (MIT)# LevelDB Socket Server - Client Examples

This directory contains official client libraries and usage examples for connecting to the LevelDB Socket Server from PHP and Python applications.

## Directory Structure

```
examples/
├── README.md              # This file
├── php/
│   ├── LevelDBClient.php  # PHP client library
│   ├── basic_example.php  # Basic CRUD operations
│   └── replication_example.php  # Replication features
└── python/
    ├── leveldb_client.py  # Python client library
    ├── basic_example.py   # Basic CRUD operations
    └── replication_example.py   # Replication features
```

## PHP Examples

### Prerequisites

- PHP 7.4+ with sockets extension enabled
- LevelDB server running (see main README)

### Files

- **LevelDBClient.php** - Full-featured client library with:
  - Connection management
  - Authentication
  - CRUD operations
  - Result parsing
  - Replication support

### Usage

```php
<?php
require_once 'LevelDBClient.php';

// Simple usage
$client = new LevelDBClient('localhost', 9999);
$client->connect();
$client->authenticate('admin', 'admin');

// Create database and table
$client->createDatabase('myapp');
$client->useDatabase('myapp');
$client->createTable('users', ['id INT PRIMARY KEY', 'name TEXT']);

// Insert data
$client->insert('users', [1, 'John Doe']);

// Query data
$users = $client->select('users');
foreach ($users as $user) {
    echo $user['name'];
}

$client->close();
?>
```

### Run Examples

```bash
cd examples/php
php basic_example.php
php replication_example.php
```

## Python Examples

### Prerequisites

- Python 3.7+
- LevelDB server running (see main README)

### Files

- **leveldb_client.py** - Full-featured client library with:
  - Synchronous and async support
  - Context managers for easy resource management
  - Type hints for better IDE support
  - Result parsing
  - Connection pooling ready

### Usage

```python
from leveldb_client import LevelDBClient, connect

# Method 1: Context manager (recommended)
with connect('localhost', 9999, 'admin', 'admin') as db:
    db.create_database('myapp')
    db.use('myapp')
    db.create_table('users', ['id INT', 'name TEXT'])
    db.insert('users', [1, 'John'])
    result = db.select('users')
    print(result)

# Method 2: Direct usage
client = LevelDBClient('localhost', 9999)
client.connect()
client.auth('admin', 'admin')
result = client.query("SELECT * FROM users")
client.close()
```

### Run Examples

```bash
cd examples/python
python basic_example.py
python replication_example.py
```

## Quick Reference

### Connection

| Language | Code |
|----------|------|
| PHP | `$client = new LevelDBClient('localhost', 9999);` |
| Python | `client = LevelDBClient('localhost', 9999)` |

### Authentication

| Language | Code |
|----------|------|
| PHP | `$client->authenticate('admin', 'admin');` |
| Python | `client.auth('admin', 'admin')` |

### Create Database

| Language | Code |
|----------|------|
| PHP | `$client->createDatabase('mydb');` |
| Python | `client.create_database('mydb')` |

### Insert

| Language | Code |
|----------|------|
| PHP | `$client->insert('users', [1, 'John']);` |
| Python | `client.insert('users', [1, 'John'])` |

### Select

| Language | Code |
|----------|------|
| PHP | `$users = $client->select('users', 'age>18');` |
| Python | `users = client.select('users', 'age>18')` |

## Advanced Features

### PHP Advanced

```php
// Replication status
$status = $client->showMasterStatus();
$status = $client->showSlaveStatus();

// List databases/tables
$databases = $client->listDatabases();
$tables = $client->listTables();

// Raw query
$result = $client->execute("SELECT * FROM users WHERE id=1");
```

### Python Advanced

```python
# Async client for high performance
from leveldb_client import AsyncLevelDBClient
import asyncio

async def main():
    async with AsyncLevelDBClient() as db:
        await db.auth('admin', 'admin')
        result = await db.execute("SELECT * FROM users")

asyncio.run(main())

# Context manager
from leveldb_client import connect

with connect('localhost', 9999, 'admin', 'admin') as db:
    result = db.select('users')
```

## Error Handling

### PHP

```php
try {
    $client = new LevelDBClient('localhost', 9999);
    $client->connect();
    $client->authenticate('admin', 'wrongpass');
} catch (Exception $e) {
    echo "Error: " . $e->getMessage();
}
```

### Python

```python
from leveldb_client import LevelDBClient, AuthenticationError

try:
    client = LevelDBClient('localhost', 9999)
    client.connect()
    client.auth('admin', 'wrongpass')
except AuthenticationError as e:
    print(f"Auth failed: {e}")
except ConnectionError as e:
    print(f"Connection failed: {e}")
```

## Best Practices

1. **Always use context managers** (Python) or **try-finally** (PHP) to ensure connections close
2. **Reuse connections** when making multiple queries
3. **Handle exceptions** properly in production code
4. **Use prepared statements** concept - validate inputs before sending
5. **Set appropriate timeouts** based on your network latency

## Troubleshooting

### Connection Refused
- Check if server is running: `python server.py`
- Verify host and port are correct
- Check firewall settings

### Authentication Failed
- Verify username and password
- Check if user exists: `SHOW USERS` as admin
- Create user if needed: `CREATE REPLICATION USER`

### Timeout
- Increase timeout in client constructor
- Check network connectivity
- Verify server is responsive

## Contributing

When adding new examples:
1. Follow existing code style
2. Include error handling
3. Add comments explaining complex operations
4. Update this README

## License

Same as main project (MIT)
---

## Summary

All example files have been created successfully!

### PHP Examples (`examples/php/`)

| File | Description |
|------|-------------|
| `LevelDBClient.php` | Full-featured PHP client library (11KB) |
| `basic_example.php` | CRUD operations demo |
| `replication_example.php` | Master-slave replication demo |

**Features:**
- Connection management with timeout support
- Authentication with error handling
- All CRUD operations (Create, Read, Update, Delete)
- Result parsing for SELECT queries
- Replication commands (SHOW MASTER STATUS, SHOW SLAVE STATUS)
- List databases/tables
- Proper resource cleanup with destructor

### Python Examples (`examples/python/`)

| File | Description |
|------|-------------|
| `leveldb_client.py` | Full-featured Python client library (16KB) |
| `basic_example.py` | CRUD operations demo |
| `replication_example.php` | Master-slave replication demo |

**Features:**
- Synchronous client with full type hints
- Async client for high-performance applications
- Context managers for easy resource management
- Connection pooling ready
- Comprehensive result parsing
- Exception hierarchy (AuthenticationError, ConnectionError)
- Method chaining support

## Usage

### PHP
```bash
cd examples/php
php basic_example.php
php replication_example.php
```

### Python
```bash
cd examples/python
python basic_example.py
python replication_example.py
```

The client libraries provide a clean, object-oriented interface that abstracts the socket protocol, making it easy to integrate LevelDB into any PHP or Python application!
