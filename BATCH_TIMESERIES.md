
# Batch Time-Series Operations Guide

Version: 2.3.0  
Last Updated: 2024-01-15

## Overview

Batch Time-Series Operations optimize performance for time-series data workloads, including bulk inserts, optimized time_bucket queries, batch downsampling, and retention policy management.

## Features

- **Bulk Hypertable Inserts**: High-performance batch inserts into hypertables
- **Optimized time_bucket()**: Partition pruning for faster aggregations
- **Batch Downsampling**: Efficient data reduction across time ranges
- **Retention Policies**: Automated data lifecycle management
- **Partition Pruning**: Skip irrelevant partitions for faster queries

## Quick Start

```python
from batch_timeseries import BatchTimeSeriesManager
from timeseries import Hypertable, TimeSeriesPoint

# Create manager
hypertables = {'metrics': Hypertable('metrics')}
manager = BatchTimeSeriesManager(hypertables)

# Bulk insert
points = [
    TimeSeriesPoint(timestamp=1234567890, value=100.0, tags={'host': 'server1'}),
    TimeSeriesPoint(timestamp=1234567891, value=101.0, tags={'host': 'server1'}),
]
result = manager.bulk_insert('metrics', points)
print(f"Inserted {result.inserted} points in {result.elapsed_ms:.2f}ms")
```

## SQL Commands

### BULK INSERT

```sql
-- Bulk insert multiple values
BULK INSERT INTO metrics VALUES
    (1234567890, 100.0, {'host': 'server1', 'region': 'us-east'}),
    (1234567891, 101.0, {'host': 'server1', 'region': 'us-east'}),
    (1234567892, 99.5, {'host': 'server2', 'region': 'us-west'});

-- Insert with automatic timestamp parsing
BULK INSERT INTO logs VALUES
    ('2024-01-15T10:00:00', 'INFO', {'service': 'api'}),
    ('2024-01-15T10:00:01', 'ERROR', {'service': 'db'});
```

### Optimized time_bucket Queries

```sql
-- Standard time_bucket (scans all partitions)
SELECT time_bucket('1h', timestamp), avg(value)
FROM metrics
WHERE timestamp > now() - interval '1 day';

-- Optimized with partition pruning
SELECT time_bucket('1h', timestamp), avg(value)
FROM metrics
WHERE timestamp BETWEEN '2024-01-14' AND '2024-01-15'
GROUP BY 1;
```

## Bulk Insert Operations

### Basic Bulk Insert

```python
from batch_timeseries import BatchTimeSeriesManager
from timeseries import TimeSeriesPoint
import time

manager = BatchTimeSeriesManager(hypertables)

# Prepare points
points = []
for i in range(10000):
    point = TimeSeriesPoint(
        timestamp=time.time() + i,
        value=float(i),
        tags={'metric': 'cpu', 'host': f'server{i % 10}'}
    )
    points.append(point)

# Bulk insert with batching
result = manager.bulk_insert('metrics', points, batch_size=1000)

print(f"Inserted: {result.inserted}")
print(f"Failed: {result.failed}")
print(f"Time: {result.elapsed_ms:.2f}ms")
print(f"Rate: {result.inserted / result.elapsed_ms * 1000:.0f} points/sec")
```

### Bulk Insert from SQL

```python
# Parse SQL bulk insert command
command = """
BULK INSERT INTO metrics VALUES
    (1234567890, 100.0, {'host': 'server1'}),
    (1234567891, 101.0, {'host': 'server1'}),
    (1234567892, 102.0, {'host': 'server2'})
"""

table_name, values = parse_bulk_insert_sql(command)
result = manager.bulk_insert_sql(table_name, values)
```

### Performance Comparison

| Method | Points/sec | Memory Usage |
|--------|-----------|--------------|
| Individual INSERT | ~500 | Low |
| Bulk INSERT (batch=100) | ~5,000 | Medium |
| Bulk INSERT (batch=1000) | ~50,000 | Medium |
| Bulk INSERT (batch=10000) | ~100,000 | High |

## time_bucket() Optimization

### Partition Pruning

```python
from timeseries import TimeRange
import time

# Query with partition pruning
time_range = TimeRange(
    start=time.time() - 86400,  # Last 24 hours
    end=time.time()
)

result = manager.optimize_time_bucket_query(
    hypertable_name='metrics',
    bucket_size='1h',
    time_range=time_range,
    aggregation='avg'
)

print(f"Partitions scanned: {result['partitions_scanned']}")
print(f"Partitions total: {result['partitions_total']}")
print(f"Pruning efficiency: {result['pruning_efficiency']:.1%}")
print(f"Buckets returned: {result['buckets_returned']}")
```

### Batch time_bucket Queries

```python
# Query multiple time ranges efficiently
time_ranges = [
    TimeRange(start=start_of_day, end=midday),
    TimeRange(start=midday, end=end_of_day),
    TimeRange(start=yesterday, end=today),
]

results = manager.time_bucket_batch(
    hypertable_name='metrics',
    bucket_size='1h',
    time_ranges=time_ranges,
    aggregation='avg',
    parallel=True  # Execute in parallel
)

for i, result in enumerate(results):
    print(f"Range {i}: {len(result.buckets)} buckets, "
          f"{result.total_points} points in {result.elapsed_ms:.2f}ms")
```

### Optimization Benefits

```
Without partition pruning:
  - Scans: 365 partitions (1 year of data)
  - Time: 5000ms

With partition pruning (1 day query):
  - Scans: 1 partition
  - Time: 50ms
  
Speedup: 100x
```

## Batch Downsampling

### Downsampling Operations

```python
from timeseries import TimeRange

# Downsample 1-minute data to 1-hour buckets
time_ranges = [
    TimeRange(start=week_ago, end=day_ago),
    TimeRange(start=day_ago, end=now),
]

results = manager.batch_downsample(
    hypertable_name='metrics',
    source_bucket='1m',      # 1-minute resolution
    target_bucket='1h',      # 1-hour resolution
    time_ranges=time_ranges,
    aggregation='avg'
)

for result in results:
    print(f"Source buckets: {result.source_buckets}")
    print(f"Target buckets: {result.target_buckets}")
    print(f"Compression ratio: {result.source_buckets / result.target_buckets:.1f}x")
    print(f"Time: {result.elapsed_ms:.2f}ms")
```

### Downsampling Ratios

| Source | Target | Compression | Use Case |
|--------|--------|-------------|----------|
| 1m | 1h | 60x | Long-term storage |
| 1m | 1d | 1440x | Historical analysis |
| 1s | 1m | 60x | Metrics aggregation |
| 1h | 1d | 24x | Daily reports |

## Retention Policies

### Batch Retention Application

```python
# Apply retention to specific hypertables
result = manager.apply_retention_batch(
    hypertable_names=['metrics', 'logs'],
    dry_run=False
)

print(f"Hypertables processed: {result.hypertables_processed}")
print(f"Points deleted: {result.points_deleted}")
print(f"Partitions dropped: {result.partitions_dropped}")
print(f"Time: {result.elapsed_ms:.2f}ms")

# Apply to all hypertables
result = manager.apply_retention_batch()  # No names = all
```

### Dry Run Mode

```python
# Preview what would be deleted
result = manager.apply_retention_batch(
    hypertable_names=['metrics'],\n    dry_run=True\n)\n\n# Check logs for preview output\n# [DRY RUN] Would delete 1000000 points from metrics\n```

### Retention Configuration

```python
from timeseries import RetentionPolicy\n\n# Create hypertable with retention\npolicy = RetentionPolicy(\n    raw_ttl=7 * 24 * 3600,      # Keep raw data 7 days\n    downsample_interval=3600,    # Downsample to hourly\n    downsample_ttl=365 * 24 * 3600  # Keep downsampled 1 year\n)\n\nhypertable = Hypertable(\n    name='metrics',\n    retention_policy=policy\n)\n```

## Performance Benchmarks

### Bulk Insert Benchmark

```python
import time\n\ndef benchmark_bulk_insert():\n    sizes = [100, 1000, 10000, 100000]\n    results = []\n    \n    for size in sizes:\n        points = generate_test_points(size)\n        \n        start = time.time()\n        result = manager.bulk_insert('metrics', points, batch_size=1000)\n        elapsed = time.time() - start\n        \n        results.append({\n            'size': size,\n            'elapsed_ms': elapsed * 1000,\n            'rate': size / elapsed\n        })\n    \n    return results\n\n# Example results:\n# Size    Time (ms)   Rate (pts/sec)\n# 100     5          20,000\n# 1,000   20         50,000\n# 10,000  150        66,667\n# 100,000 1200       83,333\n```

### Query Benchmark

```python\ndef benchmark_time_bucket():\n    # Test partition pruning effectiveness\n    scenarios = [\n        ('1 hour', TimeRange(start=now-3600, end=now)),\n        ('1 day', TimeRange(start=now-86400, end=now)),\n        ('1 week', TimeRange(start=now-604800, end=now)),\n    ]\n    \n    for name, time_range in scenarios:\n        result = manager.optimize_time_bucket_query(\n            'metrics', '1h', time_range\n        )\n        \n        print(f\"{name}: {result['elapsed_ms']:.2f}ms, \"\n              f\"pruned {result['pruning_efficiency']:.1%}\")\n```

## Best Practices

### 1. Use Appropriate Batch Sizes

```python\n# Too small: High overhead\nresult = manager.bulk_insert(points, batch_size=10)  # Inefficient\n\n# Optimal: Balance memory and speed\nresult = manager.bulk_insert(points, batch_size=1000)  # Good\n\n# Too large: Memory pressure\nresult = manager.bulk_insert(points, batch_size=100000)  # Risky\n```\n\n### 2. Leverage Partition Pruning\n\n```python\n# Good: Specific time range enables pruning\nSELECT * FROM metrics\nWHERE timestamp BETWEEN '2024-01-01' AND '2024-01-02'\n\n# Less efficient: Open-ended query\nSELECT * FROM metrics WHERE timestamp > '2024-01-01'\n```\n\n### 3. Schedule Retention During Off-Peak\n\n```python\n# Apply retention during low-traffic hours\nscheduler.schedule(\n    lambda: manager.apply_retention_batch(),\n    hour=2,  # 2 AM\n    minute=0\n)\n```\n\n### 4. Monitor Downsampling Quality\n\n```python\n# Compare original vs downsampled\ndef check_downsampling_quality(source, downsampled):\n    orig_avg = sum(p['value'] for p in source) / len(source)\n    down_avg = sum(p['value'] for p in downsampled) / len(downsampled)\n    \n    error_pct = abs(orig_avg - down_avg) / orig_avg * 100\n    assert error_pct < 1.0, f\"High error: {error_pct:.2f}%\"\n```\n\n### 5. Use Parallel Processing for Multiple Ranges\n\n```python\n# Process multiple time ranges in parallel\nresults = manager.time_bucket_batch(\n    hypertable_name='metrics',\n    bucket_size='1h',\n    time_ranges=ranges,\n    parallel=True  # Uses ThreadPoolExecutor\n)\n```\n\n## Integration with Batch Executor\n\n```python\nfrom batch_executor import BatchExecutor\nfrom batch_timeseries import get_batch_ts_manager\n\n# Create executor with time-series support\nts_manager = get_batch_ts_manager(hypertables)\nexecutor = BatchExecutor(parser, registry)\n\n# Execute time-series batch\ncommands = [\n    \"BULK INSERT INTO metrics VALUES (...), (...), (...)\",\n    \"SELECT time_bucket('1h', timestamp), avg(value) FROM metrics WHERE ...\",\n    \"APPLY RETENTION POLICY TO metrics\",\n]\n\nresult = executor.execute_batch(commands, client_state={})\n```\n\n## Error Handling\n\n### Bulk Insert Errors\n\n```python\nresult = manager.bulk_insert('metrics', points)\n\nif result.failed > 0:\n    failure_rate = result.failed / (result.inserted + result.failed)\n    \n    if failure_rate > 0.1:  # >10% failed\n        logger.error(f\"High failure rate: {failure_rate:.1%}\")\n        # Investigate and retry\n    else:\n        logger.warning(f\"{result.failed} points failed to insert\")\n```\n\n### Query Timeout\n\n```python\nimport signal\n\ndef timeout_handler(signum, frame):\n    raise TimeoutError(\"Query exceeded time limit\")\n\nsignal.signal(signal.SIGALRM, timeout_handler)\nsignal.alarm(30)  # 30 second timeout\n\ntry:\n    result = manager.time_bucket_batch(...)\nfinally:\n    signal.alarm(0)\n```\n\n## Metrics and Monitoring\n\n### Key Metrics\n\n```python\nmetrics = manager.get_metrics()\n\nprint(f\"Bulk inserts: {metrics['bulk_inserts']}\")\nprint(f\"Time bucket queries: {metrics['time_bucket_queries']}\")\nprint(f\"Downsample ops: {metrics['downsample_ops']}\")\nprint(f\"Points inserted: {metrics['total_points_inserted']}\")\nprint(f\"Points deleted: {metrics['total_points_deleted']}\")\n```\n\n### Hypertable Stats\n\n```python\nstats = manager.get_hypertable_stats('metrics')\n\nprint(f\"Total inserts: {stats['total_inserts']}\")\nprint(f\"Total queries: {stats['total_queries']}\")\nprint(f\"Total points: {stats['total_points']}\")\n```\n\n## Troubleshooting\n\n### Slow Bulk Inserts\n\n**Symptoms**: Insert rate lower than expected\n\n**Solutions**:\n1. Increase batch_size (try 1000-10000)\n2. Check disk I/O capacity\n3. Verify no lock contention\n4. Disable synchronous_commit temporarily\n\n### High Memory Usage\n\n**Symptoms**: OOM during bulk operations\n\n**Solutions**:\n1. Reduce batch_size\n2. Process in smaller chunks\n3. Monitor memory growth\n4. Use streaming for very large datasets\n\n### Partition Pruning Not Working\n\n**Symptoms**: All partitions scanned for time-range query\n\n**Check**:\n1. Time range is explicit (not open-ended)\n2. Timestamp column is indexed\n3. Query uses timestamp in WHERE clause\n4. Hypertable has time-based partitioning\n\n## See Also\n\n- [Time-Series Data](timeseries.py)\n- [Batch Operations](OPERATIONS.md)\n- [Performance Tuning](performance.md)\n