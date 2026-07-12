
# Connection Pool Sizing for Batch Workloads

Version: 2.3.0  
Last Updated: 2024-01-15

## Overview

Proper connection pool sizing is critical for batch operation performance. This guide provides formulas, recommendations, and best practices for sizing connection pools in KosDB.

## Sizing Formula

### Basic Formula

```
Pool Size = (Number of Concurrent Batches × Commands per Batch × Processing Time) 
            + (Number of Shards × Minimum per Shard)
            + Safety Margin
```

### Detailed Calculation

```python
def calculate_pool_size(
    concurrent_batches: int,
    avg_commands_per_batch: int,
    avg_command_time_ms: float,
    num_shards: int = 1,
    safety_margin: float = 0.2
) -> int:
    """
    Calculate optimal connection pool size.
    
    Args:
        concurrent_batches: Maximum concurrent batches
        avg_commands_per_batch: Average commands per batch
        avg_command_time_ms: Average time per command
        num_shards: Number of database shards
        safety_margin: Safety margin (0.2 = 20%)
    
    Returns:
        Recommended pool size
    """
    # Base calculation
    base_size = concurrent_batches * num_shards
    
    # Add capacity for command execution overlap
    overlap_factor = min(avg_commands_per_batch / 10, 5)
    adjusted_size = base_size * overlap_factor
    
    # Add safety margin
    final_size = int(adjusted_size * (1 + safety_margin))
    
    # Ensure minimums
    final_size = max(final_size, num_shards * 2)
    
    return final_size
```

## Recommended Configurations

### Small Workloads

**Profile:**
- Up to 10 concurrent batches
- 100-1000 commands per batch
- Single shard

```python
config = {
    'min_connections': 5,
    'max_connections': 20,
    'max_batch_connections': 10,
    'pool_wait_timeout_ms': 5000,
}
```

**Characteristics:**
- Low memory footprint
- Fast startup
- Suitable for development/testing

### Medium Workloads

**Profile:**
- 10-50 concurrent batches
- 1000-10000 commands per batch
- 2-5 shards

```python
config = {
    'min_connections': 10,
    'max_connections': 100,
    'max_batch_connections': 40,
    'pool_wait_timeout_ms': 10000,
}
```

**Characteristics:**
- Balanced resource usage
- Good throughput
- Suitable for production (small-medium)

### Large Workloads

**Profile:**
- 50-200 concurrent batches
- 10000+ commands per batch
- 5+ shards

```python
config = {
    'min_connections': 20,
    'max_connections': 500,
    'max_batch_connections': 150,
    'pool_wait_timeout_ms': 30000,
}
```

**Characteristics:**
- High throughput
- Higher memory usage
- Requires tuning

## Batch-Specific Considerations

### Connection Affinity

Batch operations benefit from connection affinity:

```python
# Enable connection affinity for batches
pool_config = {
    'connection_affinity': True,
    'affinity_timeout_ms': 300000,  # 5 minutes
}
```

**Benefits:**
- Reduced connection overhead
- Better transaction consistency
- Improved performance (10-20%)

### Cross-Shard Batches

For cross-shard batches, size pool by:

```python
def calculate_cross_shard_pool_size(
    max_concurrent_batches: int,
    num_shards: int,
    coordinator_connections: int = 5
) -> Dict[str, int]:
    """
    Calculate pool sizes for cross-shard batches.
    """
    return {
        'per_shard': {
            'min': 5,
            'max': max(20, max_concurrent_batches * 2),
        },
        'coordinator': {
            'min': 2,
            'max': coordinator_connections,
        }
    }
```

### Streaming Batches

For large streaming batches:

```python
streaming_config = {
    'max_connections': 10,  # Lower for streaming
    'streaming_chunk_size': 1000,
    'connection_hold_time_ms': 60000,  # Hold longer
}
```

## Monitoring-Based Sizing

### Key Metrics

| Metric | Target | Action if Exceeded |
|--------|--------|-------------------|
| Pool Utilization | < 70% | Increase max_connections |
| Wait Time | < 100ms | Increase pool size |
| Exhaustion Events | 0 | Increase pool size |
| Connection Lifetime | < 1 hour | Check for leaks |

### Auto-Tuning

```python
class AutoTunedPool:
    """Connection pool with auto-tuning."""
    
    def __init__(self, initial_size: int):
        self.size = initial_size
        self.metrics_history = []
    
    def adjust_size(self):
        """Adjust pool size based on metrics."""
        metrics = self.get_metrics()
        
        # Increase if high utilization
        if metrics['utilization_percent'] > 80:
            self.size = int(self.size * 1.2)
        
        # Decrease if low utilization (save resources)
        elif metrics['utilization_percent'] < 30:
            self.size = max(int(self.size * 0.9), self.min_size)
        
        return self.size
```

## Resource Requirements

### Memory per Connection

| Database | Memory per Connection |
|----------|----------------------|
| PostgreSQL | ~10 MB |
| MySQL | ~5 MB |
| SQLite | ~1 MB |

### Total Memory Formula

```
Total Memory = Pool Size × Memory per Connection × Safety Factor
```

Example for PostgreSQL with 100 connections:
```
100 × 10 MB × 1.5 = 1.5 GB
```

## Troubleshooting Sizing Issues

### Issue: Pool Exhaustion

**Symptoms:**
- `TimeoutError: Could not acquire connection`
- High wait times
- Exhaustion events > 0

**Solutions:**
1. Increase `max_connections`
2. Reduce `max_batch_connections`
3. Add connection timeout alerts

### Issue: High Memory Usage

**Symptoms:**
- OOM errors
- High memory usage
- Slow performance

**Solutions:**
1. Decrease `max_connections`
2. Reduce `idle_timeout_ms`
3. Enable connection recycling

### Issue: Poor Performance

**Symptoms:**
- Low throughput
- High latency
- Low CPU utilization

**Solutions:**
1. Increase `min_connections`
2. Enable connection affinity
3. Check for network latency

## POOL STATUS Enhancements

### Enhanced Status Command

```sql
SHOW POOL STATUS;
```

**Output:**
```
========================================
BATCH CONNECTION POOL STATUS
========================================
Pool Name:            default
Total Connections:    50
Active Connections:   35
Idle Connections:     15
Waiting Requests:     0

Batch Connections:    12
  - Active Batches:   8
  - Avg Commands:     500

Performance Metrics:
  Total Requests:     15000
  Timeouts:           2
  Avg Wait Time:      5.2 ms
  Exhaustion Events:  0
  
Utilization:          70.0%
Health:               HEALTHY
========================================
```

### Batch-Specific Status

```sql
SHOW BATCH POOL STATUS;
```

**Output:**
```
========================================
BATCH POOL STATUS
========================================
Active Batch Connections: 12

Batch Details:
  batch_001: 1500 commands, conn_id=45, time=2.3s
  batch_002: 800 commands, conn_id=46, time=1.1s
  batch_003: 2000 commands, conn_id=47, time=3.5s

Pool Efficiency:
  Connection Reuse: 85%
  Avg Batch Time: 2.3s
  Commands/sec: 652
========================================
```

## Best Practices

### 1. Start Conservative

Begin with smaller pools and increase based on metrics:

```python
# Start with
initial_config = {
    'min_connections': 5,
    'max_connections': 20,
}

# Scale up based on:
# - Monitor utilization
# - Check wait times
# - Review exhaustion events
```

### 2. Monitor and Adjust

```python
# Weekly review
def review_pool_performance():
    metrics = pool.get_metrics()
    
    if metrics['utilization_percent'] > 80:
        print("Consider increasing pool size")
    
    if metrics['pool_exhaustion_events'] > 0:
        print("Urgent: Pool exhaustion detected")
```

### 3. Use Connection Affinity

```python
# Enable for batch-heavy workloads
pool = BatchConnectionPool(
    connection_affinity=True,
    affinity_timeout_ms=300000,
)
```

### 4. Separate Pools

Consider separate pools for different workloads:

```python
# Batch pool
batch_pool = create_batch_pool(
    name="batch_pool",
    max_connections=100,
)

# Query pool
query_pool = create_pool(
    name="query_pool",
    max_connections=50,
)
```

### 5. Document Your Sizing

```yaml
# pool-sizing.yml
production:
  default:
    max_connections: 100
    max_batch_connections: 40
    reason: "Based on 50 concurrent batches, 2s avg processing"
  
  shard_1:
    max_connections: 30
    reason: "Shard-specific tuning based on load"
```

## See Also

- [Operations Guide](OPERATIONS.md)
- [Load Testing](LOAD_TESTING.md)
- [Performance Tuning](performance.md)
