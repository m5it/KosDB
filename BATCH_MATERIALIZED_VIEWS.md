
# Batch Materialized View Operations Guide

Version: 2.3.0  
Last Updated: 2024-01-15

## Overview

Batch Materialized View Operations enable efficient management of materialized views within batch execution contexts. This guide covers refresh patterns, scheduling, dependency handling, and performance optimization.

## Features

- **Batch View Refresh**: Refresh multiple views in a single batch
- **Concurrent Refresh**: Non-blocking refresh using `REFRESH CONCURRENTLY`
- **Dependency Handling**: Automatic ordering based on view dependencies
- **Batch Scheduling**: Schedule automatic refreshes
- **Performance Metrics**: Track refresh performance and statistics

## Quick Start

```python
from batch_materialized_views import BatchMaterializedViewManager

# Create manager
manager = BatchMaterializedViewManager(mv_manager)

# Refresh single view
result = manager.refresh_view('daily_sales')

# Refresh all views in dependency order
result = manager.refresh_all_views()

# Schedule automatic refresh
manager.schedule_refresh('hourly_metrics', interval_minutes=60)
```

## SQL Commands

### REFRESH MATERIALIZED VIEW

```sql
-- Blocking refresh
REFRESH MATERIALIZED VIEW daily_sales;

-- Concurrent (non-blocking) refresh
REFRESH MATERIALIZED VIEW CONCURRENTLY daily_sales;
```

### REFRESH ALL MATERIALIZED VIEWS

```sql
-- Refresh all views in dependency order
REFRESH ALL MATERIALIZED VIEWS;

-- Concurrent refresh where possible
REFRESH ALL MATERIALIZED VIEWS CONCURRENTLY;
```

### REFRESH SCHEDULE

```sql
-- Schedule automatic refresh every 5 minutes
REFRESH SCHEDULE hourly_metrics EVERY 5 MINUTES;

-- Schedule daily refresh
REFRESH SCHEDULE daily_report EVERY 1440 MINUTES;
```

## View Refresh Patterns

### Pattern 1: Nightly Batch Refresh

```sql
-- Refresh all views at end of day
BEGIN;
  REFRESH MATERIALIZED VIEW daily_sales;
  REFRESH MATERIALIZED VIEW daily_customers;
  REFRESH MATERIALIZED VIEW daily_orders;
COMMIT;
```

### Pattern 2: Staged Refresh with Dependencies

```sql
-- Views with dependencies are refreshed in correct order
-- view_b depends on view_a
REFRESH ALL MATERIALIZED VIEWS;
-- Automatically refreshes view_a before view_b
```

### Pattern 3: Concurrent Refresh for Availability

```sql
-- Keep views available during refresh
REFRESH MATERIALIZED VIEW CONCURRENTLY active_users;
REFRESH MATERIALIZED VIEW CONCURRENTLY user_sessions;
```

### Pattern 4: Selective Refresh

```python
# Refresh only stale views
commands = [
    "REFRESH MATERIALIZED VIEW view1",
    "REFRESH MATERIALIZED VIEW view2",
]
for cmd in commands:
    if is_stale(cmd):
        execute(cmd)
```

## Dependency Handling

### Automatic Dependency Resolution

```python
from batch_materialized_views import BatchMaterializedViewManager

manager = BatchMaterializedViewManager(mv_manager)

# Views are automatically sorted by dependencies
# If view_b depends on view_a, view_a is refreshed first
result = manager.refresh_all_views(respect_dependencies=True)
```

### View Dependency Chain

```sql
-- Base view
CREATE MATERIALIZED VIEW raw_data AS SELECT * FROM source;

-- Aggregated view (depends on raw_data)
CREATE MATERIALIZED VIEW agg_data AS 
SELECT * FROM raw_data GROUP BY category;

-- Report view (depends on agg_data)
CREATE MATERIALIZED VIEW report AS 
SELECT * FROM agg_data WHERE value > 100;

-- Batch refresh respects dependencies
REFRESH ALL MATERIALIZED VIEWS;
-- Refreshes: raw_data -> agg_data -> report
```

## Concurrent Refresh

### Requirements

- Unique index on materialized view
- No long-running transactions on the view
- Sufficient system resources

### Usage

```sql
-- Check if concurrent refresh is possible
-- (System will fall back to blocking if not)

-- Attempt concurrent refresh
REFRESH MATERIALIZED VIEW CONCURRENTLY sales_summary;

-- If unique index missing, automatically falls back to blocking
```

### Performance Benefits

| Refresh Mode | Blocking Time | Read Availability |
|--------------|---------------|-------------------|
| Blocking | 100% | None during refresh |
| Concurrent | ~10% swap time | Always available |

## Scheduling

### Programmatic Scheduling

```python
from batch_materialized_views import get_batch_mv_manager

manager = get_batch_mv_manager()

# Schedule refresh every 5 minutes
manager.schedule_refresh('realtime_metrics', interval_minutes=5)

# Schedule hourly refresh
manager.schedule_refresh('hourly_report', interval_minutes=60)

# Schedule daily refresh
manager.schedule_refresh('daily_summary', interval_minutes=1440)
```

### View All Schedules

```python
schedules = manager.get_schedules()
for s in schedules:
    print(f"{s['view_name']}: every {s['interval_minutes']} min")
    print(f"  Next run: {s['next_run']}")
```

### Cancel Schedule

```python
manager.cancel_schedule('realtime_metrics')
```

## Performance Metrics

### Available Metrics

```python
metrics = manager.get_metrics()

print(f"Total refreshes: {metrics['total_refreshes']}")
print(f"Concurrent: {metrics['concurrent_refreshes']}")
print(f"Blocking: {metrics['blocking_refreshes']}")
print(f"Failed: {metrics['failed_refreshes']}")
print(f"Scheduled: {metrics['scheduled_refreshes']}")
print(f"Avg time: {metrics['avg_refresh_time_ms']:.2f} ms")
print(f"Active schedules: {metrics['active_schedules']}")
```

### View Status

```python
# Single view status
status = manager.get_view_status('daily_sales')
print(f"Stale: {status['is_stale']}")
print(f"Last refresh: {status['last_refresh']}")
print(f"Rows: {status['row_count']}")

# All views status
all_status = manager.get_view_status()
print(f"Total views: {all_status['total_views']}")
print(f"Stale views: {all_status['stale_views']}")
```

## Integration with Batch Executor

```python
from batch_executor import BatchExecutor
from batch_materialized_views import get_batch_mv_manager

# Create executor with MV support
config = {
    'batch_query_cache_enabled': True,
    'materialized_views_enabled': True
}

executor = BatchExecutor(parser, registry, config=config)

# Execute batch with MV commands
commands = [
    "REFRESH MATERIALIZED VIEW view1",
    "REFRESH MATERIALIZED VIEW CONCURRENTLY view2",
    "REFRESH ALL MATERIALIZED VIEWS",
]

result = executor.execute_batch(commands, client_state={})
```

## Best Practices

### 1. Use Concurrent Refresh for High Availability

```sql
-- For views that must remain available
REFRESH MATERIALIZED VIEW CONCURRENTLY critical_view;
```

### 2. Schedule During Low Traffic

```python
# Schedule intensive refreshes during off-peak hours
manager.schedule_refresh('heavy_report', interval_minutes=1440)
# Set up to run at 2 AM via external scheduler
```

### 3. Respect Dependencies

```python
# Always use respect_dependencies=True
result = manager.refresh_all_views(respect_dependencies=True)
```

### 4. Monitor Stale Views

```python
status = manager.get_view_status()
if status['stale_views'] > 0:
    logger.warning(f"{status['stale_views']} views are stale")
```

### 5. Handle Failures Gracefully

```python
result = manager.refresh_view('important_view')
if not result['success']:
    logger.error(f"Refresh failed: {result['error']}")
    # Alert or retry logic
```

## Performance Optimization

### Refresh Timing

| Scenario | Recommended Approach |
|----------|-------------------|
| Small views (< 10K rows) | Blocking refresh |
| Large views (> 1M rows) | Concurrent refresh |
| Many small views | Batch refresh all |
| View chains | Dependency-aware refresh |

### Concurrent Refresh Overhead

```
Concurrent refresh adds ~10-20ms overhead for:
- Creating new snapshot
- Swapping data atomically
- Cleanup of old version

Benefit: Zero downtime for readers
```

### Batch Size Recommendations

```python
# Small batches (1-10 views): Use refresh_all_views()
# Large batches (10+ views): Consider concurrent refresh

# For very large numbers of views, refresh in chunks:
views = list(manager.mv_manager.views.keys())
chunk_size = 5
for i in range(0, len(views), chunk_size):
    chunk = views[i:i + chunk_size]
    for view in chunk:
        manager.refresh_view(view, concurrently=True)
```

## Troubleshooting

### Refresh Too Slow

**Symptoms**: Refresh takes longer than expected

**Solutions**:
1. Use concurrent refresh for large views
2. Check for missing indexes on base tables
3. Reduce view complexity
4. Refresh during off-peak hours

### Concurrent Refresh Fails

**Symptoms**: Falls back to blocking refresh

**Check**:
1. Unique index exists on view
2. No long-running transactions
3. Sufficient disk space for temporary copy

### Dependency Issues

**Symptoms**: Views refreshed in wrong order

**Solutions**:
1. Verify view queries reference correct tables
2. Check for circular dependencies
3. Use explicit refresh order if needed

## Error Handling

```python
result = manager.refresh_view('my_view')

if not result['success']:
    error_code = result.get('error_code', 'UNKNOWN')
    
    if error_code == 'VIEW_NOT_FOUND':
        logger.error("View does not exist")
    elif error_code == 'CONCURRENT_NOT_AVAILABLE':
        logger.warning("Falling back to blocking refresh")
        # Retry with blocking
        result = manager.refresh_view('my_view', concurrently=False)
```

## See Also

- [Materialized Views](materialized_views.py)
- [Batch Operations](OPERATIONS.md)
- [Performance Tuning](performance.md)
