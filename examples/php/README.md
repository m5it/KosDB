
# KosDB PHP Client Examples

This directory contains PHP client examples for KosDB, including support for the multi-command batch feature introduced in v2.3.0.

## Requirements

- PHP 7.0 or higher
- PHP sockets extension (`php-sockets`)
- KosDB server v2.3.0+ (for batch command support)

## Files

- `LevelDBClient.php` - Main client library with batch support
- `basic_example.php` - Basic CRUD operations
- `batch_example.php` - **New in v2.3.0** - Multi-command batch execution
- `replication_example.php` - Replication monitoring

## Quick Start

### Basic Usage

```php
require_once 'LevelDBClient.php';

$client = new LevelDBClient('localhost', 9999);
$client->connect();
$client->authenticate('admin', 'admin');

// Single command
$result = $client->execute("SELECT * FROM users");
echo $result;

// Query with results
$users = $client->query("SELECT * FROM users WHERE id > 5");
foreach ($users as $user) {
    echo $user['name'] . "\n";
}

$client->close();
```

## Batch Commands (v2.3.0+)

### What are Batch Commands?

Batch commands allow you to send multiple SQL statements in a single network request, separated by semicolons. This significantly reduces network overhead for bulk operations.

### Benefits

- **Reduced Network Latency**: 1 round-trip instead of N
- **Better Performance**: Server-side command caching
- **Transaction Support**: Atomic execution with BEGIN/COMMIT
- **Error Handling**: Continue on partial failures or stop

### Basic Batch Example

```php
$commands = [
    "INSERT INTO users VALUES (1, 'Alice')",
    "INSERT INTO users VALUES (2, 'Bob')",
    "SELECT * FROM users"
];

$result = $client->sendBatch($commands);

echo $result['summary']; // "3 command(s): 3 succeeded, 0 failed"
echo "Total: " . $result['total'];
echo "Succeeded: " . $result['succeeded'];
echo "Failed: " . $result['failed'];

// Iterate individual results
foreach ($result['commands'] as $cmd) {
    echo "Command {$cmd['index']}: {$cmd['status']}\n";
    echo "SQL: {$cmd['command']}\n";
    echo "Response: {$cmd['response']}\n";
}
```

### Transaction Batch

```php
// Atomic transaction - all succeed or all fail
$result = $client->sendTransactionBatch([
    "INSERT INTO orders VALUES (100, 'Laptop')",
    "INSERT INTO orders VALUES (101, 'Mouse')",
    "INSERT INTO orders VALUES (102, 'Keyboard')"
]);

if ($result['success']) {
    echo "Transaction committed successfully!";
} else {
    echo "Transaction failed: " . $result['failed'] . " errors";
}
```

### Error Handling

```php
$commands = [
    "SELECT * FROM users",                          // OK
    "INSERT INTO bad_table VALUES (1)",             // ERROR
    "SELECT COUNT(*) FROM users"                    // OK (continues)
];

$result = $client->sendBatch($commands);

// Check overall success
if (!$result['success']) {
    echo "Partial failures occurred\n";
    
    // Find failed commands
    foreach ($result['commands'] as $cmd) {
        if (!$cmd['success']) {
            echo "Failed: {$cmd['command']}\n";
            echo "Error: {$cmd['response']}\n";
        }
    }
}
```

### Quoted Semicolons

Semicolons inside quoted strings are NOT command separators:

```php
// This is a SINGLE command with a semicolon in the value
$result = $client->sendBatch([
    "INSERT INTO logs VALUES ('Error: timeout; retrying')"
]);

// The semicolon inside quotes doesn't split the command
```

## Running Examples

### Basic Example

```bash
php basic_example.php
```

### Batch Example (v2.3.0+)

```bash
php batch_example.php
```

This runs 5 demos:
1. Basic batch execution
2. Transaction batch
3. Partial failure handling
4. Quoted semicolons
5. Bulk insert performance

## API Reference

### LevelDBClient Methods

| Method | Description |
|--------|-------------|
| `connect()` | Establish connection to server |
| `authenticate($user, $pass)` | Authenticate with credentials |
| `execute($sql)` | Execute single command |
| `query($sql)` | Execute SELECT and return parsed results |
| `sendBatch($commands)` | **v2.3.0** Execute multiple commands |
| `sendTransactionBatch($commands)` | **v2.3.0** Execute with BEGIN/COMMIT |
| `close()` | Close connection |

### Batch Result Structure

```php
[
    'success' => true|false,        // All commands succeeded?
    'total' => 3,                    // Total commands
    'succeeded' => 3,                // Successful commands
    'failed' => 0,                   // Failed commands
    'summary' => '3 command(s): 3 succeeded, 0 failed',
    'commands' => [
        [
            'index' => 1,
            'command' => 'INSERT INTO...',
            'status' => 'OK',        // or 'ERROR'
            'response' => 'OK: Inserted',
            'success' => true
        ],
        // ...
    ]
]
```

## Troubleshooting

### "Batch commands are disabled"

Check server configuration:
```json
{
  "batch": {
    "enabled": true
  }
}
```

### "Not authenticated"

Ensure you call `authenticate()` before `sendBatch()`.

### Timeout on large batches

Large batches may timeout. Consider:
- Splitting into smaller batches (100-500 commands)
- Using streaming mode (server-side configuration)
- Increasing PHP's `max_execution_time`

## Performance Tips

1. **Use batches for bulk inserts**: 10-100x faster than individual inserts
2. **Cache-friendly commands**: Reuse similar SQL patterns for better server-side caching
3. **Transaction batches**: Wrap related operations for data consistency
4. **Error handling**: Check individual results for partial failure scenarios

## Version Compatibility

| Feature | Server Version | Client Version |
|---------|---------------|----------------|
| Basic commands | v1.0+ | v1.0+ |
| Batch commands | v2.3.0+ | v2.3.0+ |
| Transactions | v2.3.0+ | v2.3.0+ |
| Quoted semicolons | v2.3.0+ | v2.3.0+ |

## See Also

- [Python Examples](../python/) - Python client examples
- [Main README](../../README.md) - KosDB documentation
- [SECURITY_README](../../SECURITY_README.md) - Security features
