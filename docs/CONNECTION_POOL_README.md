# Connection Pooling for KosDB

This module implements database connection pooling for efficient resource utilization.

## Features

- **Configurable Limits**: Min/max connections with automatic scaling
- **Connection Timeout**: Configurable wait time for connection acquisition
- **Idle Timeout**: Automatic cleanup of idle connections
- **Health Checking**: Background validation of pooled connections
- **Statistics**: Active, idle, total connection tracking
- **Thread Safety**: All operations are thread-safe
- **Async Support**: Full async/await support with context managers

## Usage

### Basic Usage

```python
from connection_pool import ConnectionPool

def connection_factory():
    # Create actual database connection
    return create_database_connection()

pool = ConnectionPool(
    min_connections=5,
    max_connections=20,
    connection_timeout=30.0,
    idle_timeout=300.0,
    connection_factory=connection_factory,
    pool_name="main_pool"
)

# Get connection
conn_id = pool.get_connection()
try:
    # Use connection
    pass
finally:
    pool.return_connection(conn_id)
```

### Context Manager

```python
# Automatic connection management
with pool.connection() as conn_id:
    # Use connection
    pass  # Automatically returned
```

### Async Usage

```python
# Async connection acquisition
async with pool.connection_async() as conn_id:
    # Use connection
    pass
```

## Pool Commands

- `POOL CREATE name MIN 5 MAX 20` - Create a new pool
- `POOL STATUS [name]` - Show pool statistics
- `POOL LIST` - List all pools
- `POOL SHUTDOWN name` - Shutdown a pool
- `POOL HEALTH [name]` - Check pool health

## Statistics

```python
stats = pool.get_stats()
# {
#     'pool_name': 'main_pool',
#     'total_connections': 10,
#     'active_connections': 3,
#     'idle_connections': 7,
#     'total_created': 15,
#     'total_destroyed': 5,
#     'total_borrowed': 100,
#     'total_returned': 97,
#     'hit_rate': 0.97
# }
```

## Configuration

```json
{
    "connection_pool": {
        "min_connections": 5,
        "max_connections": 20,
        "connection_timeout": 30,
        "idle_timeout": 300,
        "health_check_interval": 60
    }
}
```

## Testing

```bash
python test_connection_pool.py
```

All 22 tests passing ✓
