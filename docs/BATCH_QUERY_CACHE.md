
# Batch Query Cache Documentation

Version: 2.3.0  
Last Updated: 2024-01-15

## Overview

The Batch Query Cache optimizes batch execution by caching SELECT results within a batch, automatically invalidating on DML operations. It integrates with the existing `query_cache.py` for system-wide caching while providing batch-specific optimizations.

## Features

- **Query Result Caching**: Cache SELECT results within batch execution
- **Cache Hints**: Control caching with SQL hints (`/*+ CACHE */`, `/*+ NOCACHE */`)
- **Auto-Invalidation**: Automatically invalidate on INSERT/UPDATE/DELETE/TRUNCATE
- **Cache Warming**: Pre-populate cache before execution
- **Integration**: Works with `query_cache.py` for unified caching
- **Metrics**: Track hit ratios and performance (`batch_cache_hit_ratio`)

## Quick Start

```python
from batch_executor import BatchExecutor
from batch_query_cache import BatchCacheManager

# Enable query caching in batch executor
config = {
    'batch_query_cache_enabled': True,
    'batch_query_cache_ttl': 300.0,
    'batch_query_cache_size': 1000
}

executor = BatchExecutor(parser, registry, config=config)

# Execute batch with automatic caching
commands = [
    "SELECT /*+ CACHE */ * FROM users WHERE status = 'active'",
    "SELECT * FROM users WHERE status = 'active',"  # Uses cache
    "UPDATE users SET last_seen = NOW()",
    "SELECT * FROM users WHERE status = 'active'"  # Cache invalidated
]
result = executor.execute_batch(commands, client_state={})
```

## Cache Hints

### Force Caching

```sql
-- Always cache this query
SELECT /*+ CACHE */ * FROM large_table WHERE complex_condition = 1;
```

### Skip Caching

```sql
-- Never cache real-time data
SELECT /*+ NOCACHE */ * FROM sensor_readings WHERE timestamp > NOW() - INTERVAL 1 MINUTE;
```

### Default Behavior

```sql
-- Uses system default (caches if enabled and conditions met)
SELECT * FROM users WHERE id = 1;
```

## Cache Warming

### SQL Syntax

```sql
-- Pre-execute and cache a query
WARM CACHE FOR SELECT * FROM reports WHERE date = '2024-01-15';

-- Then use normally (will hit cache)
SELECT * FROM reports WHERE date = '2024-01-15';
```

### Programmatic Usage

```python
from batch_query_cache import BatchCacheManager

manager = BatchCacheManager()

# Warm cache
manager.warm_cache("SELECT * FROM users", executor)
```

## Auto-Invalidation

Cache entries are automatically invalidated when DML operations affect cached tables:

```python
# These commands trigger invalidation for 'users' table
"INSERT INTO users VALUES (...)"
"UPDATE users SET ..."
"DELETE FROM users WHERE ..."
"TRUNCATE TABLE users"
```

## Cache Status

### CLI Command

```sql
CACHE STATUS;
```

Output:
```
========================================
BATCH QUERY CACHE STATUS
========================================
Cache Size:        45 / 1000
Hit Ratio:         78.50%
Total Hits:        157
Total Misses:      43
Invalidations:     12
Evictions:         0
Warm Operations:   5
========================================
```

### Programmatic Access

```python
stats = executor.cache_manager.get_stats()
print(f"Hit ratio: {stats['hit_ratio']:.2%}")
print(f"Hits: {stats['hits']}, Misses: {stats['misses']}")
```

## Integration with query_cache.py

The batch query cache integrates with the system-wide `query_cache.py`:

```python
from query_cache import QueryCache, get_global_cache
from batch_query_cache import BatchQueryCache

# System-wide cache
global_cache = get_global_cache()

# Batch-specific cache (can share with global)
batch_cache = BatchQueryCache(
    default_ttl_seconds=300,
    max_size=1000
)

# Batch cache can invalidate global cache on DML
def on_dml(table_name):
    global_cache.invalidate_on_modify(table_name)
    batch_cache.invalidate({table_name})
```

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `batch_query_cache_enabled` | True | Enable batch query caching |
| `batch_query_cache_ttl` | 300.0 | Cache entry lifetime in seconds |
| `batch_query_cache_size` | 1000 | Maximum cache entries |

## Metrics

- `batch_cache_hit_ratio`: Percentage of cache hits (0.0-1.0)
- `cache_invalidations`: Number of invalidation events
- `cache_evictions`: Number of evictions due to size

## Best Practices

1. Use `/*+ CACHE */` for expensive queries
2. Use `/*+ NOCACHE */` for real-time data
3. Warm cache for predictable workloads
4. Monitor hit ratio to tune cache size
5. Keep TTL short for frequently changing data
6. Use larger cache sizes for analytical workloads

## Performance

Typical performance improvements:

| Scenario | Improvement |
|----------|-------------|
| Repeated identical SELECTs | 10-100x faster |
| Warm cache hits | Near-instant |
| Cache miss | ~1ms overhead |
| DML invalidation | <1ms |

## Troubleshooting

### Low Hit Ratio

- Check if queries are identical (whitespace matters)
- Verify cache is enabled
- Check if DML is invalidating too frequently
- Consider increasing TTL

### Cache Not Working

- Verify `batch_query_cache_enabled` is True
- Check query starts with SELECT
- Ensure no `/*+ NOCACHE */` hint
- Verify response size < threshold

### Memory Issues

- Reduce `batch_query_cache_size`
- Lower `batch_query_cache_ttl`
- Monitor `memory_usage_estimate` in stats

## See Also

- [Batch Operations Guide](OPERATIONS.md)
- [Performance Tuning](performance.md)
- [query_cache.py](query_cache.py)
| `max_size` | 1000 | Maximum cache entries |

## Metrics

- `batch_cache_hit_ratio`: Percentage of cache hits
- `cache_invalidations`: Number of invalidation events
- `cache_evictions`: Number of evictions due to size

## Best Practices

1. Use `/*+ CACHE */` for expensive queries
2. Use `/*+ NOCACHE */` for real-time data
3. Warm cache for predictable workloads
4. Monitor hit ratio to tune cache size
