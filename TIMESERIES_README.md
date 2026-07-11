# Time-Series Data Support for KosDB

Native time-series data management with automatic partitioning, aggregation,
retention policies, and downsampling.

## Features

- **Automatic Partitioning**: Time-based chunking for efficient storage
- **Hypertable Abstraction**: Manage large time-series datasets
- **Time Bucketing**: Aggregate data into configurable time windows
- **Retention Policies**: Automatic TTL-based data cleanup
- **Downsampling**: Reduce granularity for historical data
- **Optimized Queries**: Time-range filtering with partition pruning

## Bucket Sizes

| Size | Description |
|------|-------------|
| `1m` | 1 minute |
| `5m` | 5 minutes |
| `15m` | 15 minutes |
| `1h` | 1 hour |
| `6h` | 6 hours |
| `1d` | 1 day |
| `1w` | 1 week |
| `30d` | 30 days |

## SQL Commands

### Create Hypertable
```sql
CREATE HYPERTABLE metrics CHUNK_INTERVAL 1d RETENTION 30d
```

### Insert Time-Series Data
```sql
INSERT INTO metrics VALUES (NOW, 42.5, {'sensor': 'temp1'})
INSERT INTO metrics VALUES (1699123456, 43.0)
```

### Query Time-Series Data
```sql
SELECT * FROM metrics WHERE time > 1699000000 AND time < 1699100000
SELECT * FROM metrics LIMIT 100
```

### Time Bucket Aggregation
```sql
TIME_BUCKET('1h', metrics, avg)
TIME_BUCKET('1d', metrics, sum)
```

### Downsampling
```sql
DOWNSAMPLE metrics FROM 1m TO 1h
```

### Retention Policy
```sql
RETENTION POLICY APPLY metrics
RETENTION POLICY SHOW metrics
```

### First/Last Values
```sql
FIRST metrics WHERE time > 1699000000
LAST metrics
```

### Statistics
```sql
HYPERTABLE STATS metrics
LIST HYPERTABLES
```

## API Reference

### TimeSeriesPoint

```python
from timeseries import TimeSeriesPoint

point = TimeSeriesPoint(
    timestamp=time.time(),
    value=42.5,
    tags={'sensor': 'temp1', 'location': 'room_a'}
)
```

### Hypertable

```python
from timeseries import Hypertable, TimeRange, RetentionPolicy

# Create with retention policy
table = Hypertable(
    name="metrics",
    chunk_interval=86400,  # 1 day
    retention_policy=RetentionPolicy(
        raw_ttl=2592000,  # 30 days
        downsample_interval=3600,
        downsample_ttl=5184000  # 60 days
    )
)

# Insert data
table.insert(TimeSeriesPoint(timestamp=time.time(), value=42.5))

# Query data
results = table.query(TimeRange(start=time.time() - 3600))

# Time bucket aggregation
buckets = table.time_bucket('1h', TimeRange(), aggregation='avg')

# Downsample
downsampled = table.downsample('1m', '1h', TimeRange())
```

### TimeSeriesEngine

```python
from timeseries import get_timeseries_engine

engine = get_timeseries_engine()

# Create hypertable
table = engine.create_hypertable("metrics", chunk_interval=86400)

# Get table
table = engine.get_hypertable("metrics")

# List tables
tables = engine.list_hypertables()

# Drop table
engine.drop_hypertable("metrics")
```

## Example: IoT Sensor Monitoring

```python
from timeseries import get_timeseries_engine, TimeSeriesPoint, TimeRange, RetentionPolicy
import time

# Setup
engine = get_timeseries_engine()
table = engine.create_hypertable(
    "sensor_data",
    chunk_interval=3600,  # 1 hour chunks
    retention_policy=RetentionPolicy(
        raw_ttl=604800,     # Keep raw data for 7 days
        downsample_interval=3600,
        downsample_ttl=2592000  # Keep hourly aggregates for 30 days
    )
)

# Simulate sensor data
for i in range(100):
    point = TimeSeriesPoint(
        timestamp=time.time() + i * 60,  # Every minute
        value=20 + i * 0.1,  # Temperature rising
        tags={'sensor': 'temp_sensor_1', 'room': 'lab_1'}
    )
    table.insert(point)

# Query last hour
last_hour = table.query(TimeRange(start=time.time() - 3600))

# Hourly averages
hourly = table.time_bucket('1h', TimeRange(), aggregation='avg')
for bucket in hourly:
    print(f"{bucket['datetime']}: {bucket['value']:.2f}")

# Downsample to daily
daily = table.downsample('1h', '1d', TimeRange(), aggregation='avg')
```

## Configuration

```json
{
    "timeseries": {
        "default_chunk_interval": 86400,
        "enable_retention_worker": true,
        "retention_check_interval": 3600
    }
}
```

## Testing

```bash
python test_timeseries.py
```

All 12 tests passing ✓
