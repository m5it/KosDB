
# Batch Sharding Guide

This document describes how batch commands work with sharded databases in KosDB v2.3.0.

## Overview

When executing batches on sharded databases, KosDB:

1. **Analyzes** each command to determine target shard(s)
2. **Groups** commands by target shard for efficient execution
3. **Coordinates** cross-shard batches using distributed transactions
4. **Caches** routing decisions for performance
5. **Handles** shard failures gracefully

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────┐
│  Batch Commands  │────▶│ Shard Analyzer   │────▶│ Shard Groups │
└─────────────────┘     └──────────────────┘     └─────────────┘
                                                           │
                              ┌────────────────────────────┘
                              ▼
                    ┌─────────────────┐
                    │  Single Shard   │     ┌─────────────────┐
                    │    Execute      │────▶│  Direct Exec    │
                    └─────────────────┘     └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  Cross-Shard    │     ┌─────────────────┐
                    │  Coordinator    │────▶│  2-Phase Commit │
                    └─────────────────┘     └─────────────────┘
```

## Shard Analysis

### Routing Strategies

KosDB supports multiple sharding strategies:

| Strategy | Description | Use Case |
|----------|-------------|----------|
| `HASH` | Consistent hashing on key | Even distribution |
| `RANGE` | Key range-based | Time-series data |
| `LOOKUP` | Lookup table | Complex mappings |
| `CUSTOM` | User-defined function | Special requirements |

### Hash-Based Routing (Default)

```python
hash_val = MD5(f"{table}:{key}")
shard_idx = hash_val % num_shards
```

### Range-Based Routing

```python
# Configuration
shard_ranges = {
    "shard_1": (0, 1000),
    "shard_2": (1001, 2000),
    "shard_3": (2001, float('inf'))
}

# Routing
for shard_id, (min_val, max_val) in shard_ranges.items():
    if min_val <= key <= max_val:
        return shard_id
```

## Command Grouping

### Single-Shard Batch

When all commands target the same shard:

```python
commands = [
    {"table": "users", "key": 1, "op": "INSERT"},
    {"table": "users", "key": 2, "op": "INSERT"},  # Same shard
    {"table": "users", "key": 3, "op": "INSERT"},  # Same shard
]

# Result: 1 shard group
# { "shard_1": [cmd1, cmd2, cmd3] }
```

### Cross-Shard Batch

When commands target different shards:

```python
commands = [
    {"table": "users", "key": 1, "op": "INSERT"},   # shard_1
    {"table": "users", "key": 1500, "op": "INSERT"}, # shard_2
    {"table": "users", "key": 2500, "op": "INSERT"}, # shard_3
]

# Result: 3 shard groups
# {
#   "shard_1": [cmd1],
#   "shard_2": [cmd2],
#   "shard_3": [cmd3]
# }
```

## Cross-Shard Coordination

### Two-Phase Commit

For cross-shard batches, KosDB uses 2-phase commit:

```
Phase 1: PREPARE
  Coordinator ──PREPARE──▶ Shard 1
  Coordinator ──PREPARE──▶ Shard 2
  Coordinator ──PREPARE──▶ Shard 3

Phase 2: COMMIT (if all prepared)
  Coordinator ──COMMIT───▶ Shard 1
  Coordinator ──COMMIT───▶ Shard 2
  Coordinator ──COMMIT───▶ Shard 3
```

### State Tracking

```python
class CrossShardBatchState:
    batch_id: str
    coordinator_shard: str
    participant_shards: Set[str]
    prepared_shards: Set[str]
    committed_shards: Set[str]
    failed_shards: Dict[str, str]
```

## Shard Routing Cache

### Cache Configuration

```python
from batch_sharding import ShardRoutingCache

cache = ShardRoutingCache(
    max_size=10000,      # Maximum entries
    ttl_seconds=300.0   # Time-to-live
)
```

### Cache Operations

```python
# Get cached routing
target = cache.get("users:123")
if target:
    # Use cached routing
    pass
else:
    # Compute and cache
    target = compute_shard("users", 123)
    cache.put("users:123", target)

# Invalidate table
cache.invalidate_table("users")

# Get statistics
stats = cache.get_stats()
# {
#   'size': 5234,
#   'hits': 10000,
#   'misses': 1000,
#   'hit_rate': 0.91
# }
```

## Failure Handling

### Single-Shard Failures

```python
# Error modes
error_mode = "continue"      # Skip failed, continue others
error_mode = "rollback_all"  # Rollback all on any failure
error_mode = "stop"          # Stop on first failure
```

### Cross-Shard Failures

```python
# If a shard fails during PREPARE
if failed_shards:
    if error_mode == "rollback_all":
        coordinator.rollback_batch(batch_id)
    else:
        # Continue with remaining shards
        coordinator.commit_batch(batch_id)
```

### Retry Logic

```python
max_retries = 3
backoff = 0.1 * (2 ** attempt)  # Exponential backoff

for attempt in range(max_retries):
    try:
        execute_on_shard(shard_id, command)
        break
    except ShardUnavailable:
        if attempt == max_retries - 1:
            raise
        time.sleep(backoff)
```

## Usage Examples

### Basic Usage

```python
from batch_sharding import ShardedBatchManager

# Initialize with shard manager
manager = ShardedBatchManager(shard_manager)

# Execute batch
commands = [
    {"table": "users", "key": 1, "op": "INSERT", "data": {...}},
    {"table": "users", "key": 2, "op": "INSERT", "data": {...}},
]

result = manager.execute_batch(commands)
```

### With Error Handling

```python
result = manager.execute_batch(
    commands=commands,
    error_mode="continue",  # or "rollback_all"
    timeout_ms=30000
)

if result['success']:
    print(f"Executed {result['executed']} commands")
else:
    print(f"Failed: {result.get('errors', [])}")
```

### Cross-Shard Batch

```python
# Commands targeting different shards
commands = [
    {"table": "users", "key": 1, "op": "INSERT"},      # shard_1
    {"table": "orders", "key": 1000, "op": "INSERT"},  # shard_2
]

result = manager.execute_batch(commands)

if result.get('is_cross_shard'):
    print(f"Cross-shard batch: {result['shards']} shards")
    print(f"Results per shard: {result['shard_results']}")
```

## Metrics

### Routing Cache Metrics

```python
metrics = manager.get_routing_cache_stats()

print(f"""
Cache Size: {metrics['size']}
Hit Rate: {metrics['hit_rate']:.2%}
Hits: {metrics['hits']}
Misses: {metrics['misses']}
""")
```

### Coordinator Metrics

```python
metrics = manager.get_coordinator_metrics()

print(f"""
Cross-Shard Batches: {metrics['total_cross_shard_batches']}
Successful Commits: {metrics['successful_commits']}
Failed Commits: {metrics['failed_commits']}
Timeouts: {metrics['timeouts']}
""")
```

### Executor Metrics

```python
metrics = manager.get_executor_metrics()

print(f"""
Total Batches: {metrics['total_batches']}
Single-Shard: {metrics['single_shard_batches']}
Cross-Shard: {metrics['cross_shard_batches']}
Failed Commands: {metrics['failed_commands']}
Retry Attempts: {metrics['retry_attempts']}
""")
```

## Limitations

### 1. Cross-Shard Consistency

Cross-shard batches use 2-phase commit, which provides atomicity but with caveats:

- **Network partitions** can leave transactions in prepared state
- **Coordinator failure** requires manual intervention
- **Timeout handling** may cause partial commits

### 2. Performance Considerations

| Scenario | Latency Impact |
|----------|---------------|
| Single-shard batch | Minimal overhead |
| Cross-shard (2 shards) | 2-3x latency |
| Cross-shard (3+ shards) | 3-5x latency |

### 3. Transaction Isolation

Cross-shard transactions may have different isolation guarantees:

```
Shard A: BEGIN → UPDATE → PREPARE → COMMIT
Shard B: BEGIN → UPDATE → PREPARE → COMMIT
                              ↑
                    Visibility gap here
```

### 4. Broadcast Operations

Commands without keys broadcast to all shards:

```python
# Broadcasts to ALL shards
{"table": "users", "key": None, "op": "SELECT"}
```

Use sparingly - O(n) shard calls.

### 5. Cache Coherence

Routing cache may become stale during:

- Shard rebalancing
- Schema changes
- Manual shard assignment

**Recommendation**: Invalidate cache after topology changes.

## Best Practices

### 1. Design for Single-Shard Operations

```python
# Good: All commands on same shard
commands = [
    {"table": "users", "key": "user_1", ...},
    {"table": "users", "key": "user_1_profile", ...},
]

# Avoid: Commands scattered across shards
commands = [
    {"table": "users", "key": "user_1", ...},
    {"table": "users", "key": "user_999999", ...},  # Different shard
]
```

### 2. Use Appropriate Error Modes

| Mode | When to Use |
|------|-------------|
| `continue` | Best-effort, logging |
| `rollback_all` | Financial transactions |
| `stop` | Critical operations |

### 3. Monitor Cross-Shard Ratio

```python
metrics = manager.get_all_metrics()

cross_shard_ratio = (
    metrics['executor']['cross_shard_batches'] /
    metrics['executor']['total_batches']
)

if cross_shard_ratio > 0.1:
    logger.warning("High cross-shard ratio: %s", cross_shard_ratio)
```

### 4. Handle Timeouts Gracefully

```python
try:
    result = manager.execute_batch(commands, timeout_ms=30000)
except TimeoutError:
    # Check batch status
    status = coordinator.get_batch_status(batch_id)
    if status['state'] == 'prepared':
        # Can retry commit
        coordinator.commit_batch(batch_id)
```

### 5. Cache Management

```python
# After shard topology changes
manager.invalidate_routing_cache()

# After specific table changes
manager.invalidate_routing_cache("users")
```

## Troubleshooting

### "No shards available"

**Cause**: Shard manager not configured or no shards registered

**Solution**:
```python
# Verify shard manager
assert hasattr(shard_manager, 'get_shards')
assert len(shard_manager.get_shards()) > 0
```

### "Cross-shard coordinator not configured"

**Cause**: Attempting cross-shard batch without coordinator

**Solution**: Use ShardedBatchManager which includes coordinator

### High cache miss rate

**Cause**: Cache too small or TTL too short

**Solution**:
```python
cache = ShardRoutingCache(
    max_size=50000,      # Increase size
    ttl_seconds=600.0    # Increase TTL
)
```

### Partial commits in cross-shard batches

**Cause**: Network issues or shard failures during commit

**Solution**:
```python
# Check for incomplete batches
incomplete = coordinator.get_incomplete_batches()
for batch in incomplete:
    if batch['state'] == 'prepared':
        # Retry commit
        coordinator.commit_batch(batch['id'])
```

## API Reference

### ShardedBatchManager

```python
class ShardedBatchManager:
    def __init__(self, shard_manager: Any)
    def execute_batch(
        self,
        commands: List[Any],
        error_mode: str = "continue",
        timeout_ms: int = 30000
    ) -> Dict[str, Any]
    def get_routing_cache_stats() -> Dict[str, Any]
    def get_coordinator_metrics() -> Dict[str, Any]
    def get_executor_metrics() -> Dict[str, Any]
    def get_all_metrics() -> Dict[str, Any]
    def invalidate_routing_cache(table: Optional[str] = None)
```

### BatchShardAnalyzer

```python
class BatchShardAnalyzer:
    def __init__(
        self,
        shard_manager: Any,
        routing_strategy: ShardRoutingStrategy = ShardRoutingStrategy.HASH,
        routing_cache: Optional[ShardRoutingCache] = None
    )
    def analyze_batch(commands: List[Any]) -> Dict[str, BatchShardGroup]
    def set_custom_router(router: Callable[[Any], List[ShardTarget]])
```

### CrossShardCoordinator

```python
class CrossShardCoordinator:
    def __init__(self, shard_manager: Any)
    def begin_cross_shard_batch(
        batch_id: str,
        participant_shards: Set[str],
        timeout_ms: int = 30000
    ) -> CrossShardBatchState
    def prepare_shard(batch_id: str, shard_id: str)
    def commit_batch(batch_id: str) -> bool
    def get_metrics() -> Dict[str, Any]
```

## See Also

- [Sharding Architecture](sharding.md)
- [Batch Error Handling](BATCH_ERROR_HANDLING.md)
- [Replication Batch Guide](REPLICATION_BATCH.md)
- [Performance Tuning](performance.md)
