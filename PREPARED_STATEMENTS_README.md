# Prepared Statements & Query Plan Cache

This module implements prepared statement support and query plan caching for KosDB v2.2.0.

## Features

### Query Plan Cache (`query_plan_cache.py`)
- **LRU Eviction**: Automatically evicts least recently used plans when capacity exceeded
- **TTL Support**: Optional time-to-live for cached plans
- **Table-based Invalidation**: Automatically invalidates cached plans when dependent tables change
- **Thread-safe**: All operations are thread-safe with RLock
- **Statistics**: Hit rate, miss rate, eviction count tracking

### Prepared Statements (`prepared_statements.py`)
- **Named Parameters**: `:param_name` syntax
- **Positional Parameters**: `?` syntax
- **Session Management**: Per-session prepared statement storage
- **Parameter Validation**: Type checking and SQL injection prevention
- **Automatic Cleanup**: Expired statement cleanup

### Parser Extensions (`prepared_statement_parser.py`)
- `PREPARE name AS 'SELECT * FROM users WHERE id = :user_id'`
- `EXECUTE name(user_id => 123)` - Named parameters
- `EXECUTE name USING 123, 'value'` - Positional parameters
- `DEALLOCATE name` - Remove single statement
- `DEALLOCATE ALL` - Remove all statements
- `SHOW PREPARED` - List prepared statements
- `SHOW CACHE STATS` - Display cache statistics
- `CACHE INVALIDATE [TABLE name]` - Manual cache invalidation

## Usage Examples

### Basic Prepared Statement
```sql
-- Prepare a statement
PREPARE get_user AS SELECT * FROM users WHERE id = :user_id

-- Execute with parameters
EXECUTE get_user(user_id => 123)

-- Deallocate when done
DEALLOCATE get_user
```

### Positional Parameters
```sql
PREPARE insert_user AS INSERT INTO users (name, email) VALUES (?, ?)

EXECUTE insert_user USING 'John', 'john@example.com'
```

### Query Plan Cache
```sql
-- Check cache statistics
SHOW CACHE STATS

-- Invalidate cache for specific table
CACHE INVALIDATE TABLE users

-- Invalidate all cached plans
CACHE INVALIDATE
```

## API Reference

### QueryPlanCache
```python
from query_plan_cache import QueryPlanCache, configure_query_plan_cache

# Configure global cache
configure_query_plan_cache(capacity=1000, ttl=300)

# Get cache instance
cache = get_query_plan_cache()

# Store plan
cache.put(query, parsed_plan, table_dependencies)

# Retrieve plan
cached = cache.get(query)

# Invalidate by table
cache.invalidate_table('users')

# Get statistics
stats = cache.get_stats()
```

### PreparedStatementManager
```python
from prepared_statements import PreparedStatementManager

manager = PreparedStatementManager(max_statements=100)

# Prepare statement
stmt_id = manager.prepare("SELECT * FROM users WHERE id = ?")

# Execute with parameters
sql, params = manager.execute(stmt_id, [123])

# Deallocate
manager.deallocate(stmt_id)
```

## Configuration

```python
# In config.json
{
    "query_plan_cache": {
        "enabled": true,
        "capacity": 1000,
        "ttl": 300
    },
    "prepared_statements": {
        "enabled": true,
        "max_per_session": 100,
        "ttl": 3600
    }
}
```

## Testing

Run the test suite:
```bash
python test_query_plan_cache.py
python test_prepared_statements.py
```

All tests pass successfully:
- Query Plan Cache: 10 tests ✓
- Prepared Statements: 17 tests ✓
