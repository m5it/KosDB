
# Change Data Capture (CDC) with Batch Support

KosDB v2.3.0 introduces comprehensive Change Data Capture (CDC) with full support for batch operations. This document describes the CDC architecture, batch handling, and consumer APIs.

## Overview

CDC captures all database changes and streams them to external systems with:
- **Individual Events**: Each database change is captured as a separate event
- **Batch Correlation**: Batch operations include metadata for grouping
- **Multiple Formats**: JSON, Avro, and Protobuf output formats
- **Rate Limiting**: Protection against overwhelming consumers
- **Kafka Integration**: Native Kafka producer support

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   KosDB     │────▶│  CDC Log    │────▶│  Consumers  │
│  (Database) │     │             │     │             │
└─────────────┘     └─────────────┘     └─────────────┘
                                              │
                                              ▼
                                        ┌─────────────┐
                                        │   Kafka     │
                                        │  (Optional) │
                                        └─────────────┘
```

## Event Types

### Standard Operations

| Operation | Description |
|-----------|-------------|
| `INSERT` | New row inserted |
| `UPDATE` | Existing row modified |
| `DELETE` | Row deleted |
| `BEGIN` | Transaction started |
| `COMMIT` | Transaction committed |
| `ROLLBACK` | Transaction rolled back |

### Batch Markers

| Marker | Description |
|--------|-------------|
| `BATCH_START` | Beginning of batch operation |
| `BATCH_END` | Completion of batch operation |
| `BATCH_COMMAND` | Individual command within batch |

## Batch CDC Events

### Single Event (Non-Batch)

```json
{
  "sequence_number": 100,
  "timestamp": 1705312800123456,
  "timestamp_iso": "2024-01-15T10:00:00.123456",
  "operation": "INSERT",
  "table": "users",
  "key": 1,
  "before": null,
  "after": {
    "id": 1,
    "name": "Alice",
    "email": "alice@example.com"
  },
  "transaction_id": null,
  "lsn": null,
  "batch_id": null,
  "batch_sequence": null,
  "batch_total": null,
  "batch_error_mode": null
}
```

### Batch Start Marker

```json
{
  "sequence_number": 101,
  "timestamp": 1705312800123457,
  "operation": "BATCH_START",
  "table": "",
  "key": null,
  "batch_id": "batch_001",
  "batch_sequence": 0,
  "batch_total": 3,
  "batch_error_mode": "continue"
}
```

### Batch Command Event

```json
{
  "sequence_number": 102,
  "timestamp": 1705312800123458,
  "operation": "INSERT",
  "table": "users",
  "key": 1,
  "after": {
    "id": 1,
    "name": "Alice"
  },
  "batch_id": "batch_001",
  "batch_sequence": 1,
  "batch_total": 3,
  "batch_error_mode": "continue"
}
```

### Batch End Marker

```json
{
  "sequence_number": 104,
  "timestamp": 1705312800123460,
  "operation": "BATCH_END",
  "table": "",
  "key": null,
  "batch_id": "batch_001",
  "batch_sequence": 0,
  "batch_total": 3,
  "batch_error_mode": null
}
```

## Batch Correlation

All events from the same batch share the same `batch_id`:

```python
# Batch execution generates events with shared batch_id
batch_id = "batch_001"

# Events:
# 1. BATCH_START (batch_id="batch_001")
# 2. INSERT (batch_id="batch_001", batch_sequence=1)
# 3. INSERT (batch_id="batch_001", batch_sequence=2)
# 4. INSERT (batch_id="batch_001", batch_sequence=3)
# 5. BATCH_END (batch_id="batch_001")
```

## Consumer API

### Basic Consumer

```python
from cdc_batch import BatchCDCManager, BatchCDCEventType

# Get CDC manager
manager = get_batch_cdc_manager()

# Create consumer
consumer = manager.create_consumer(
    consumer_id="my_consumer",
    tables={"users", "orders"},
    operations={BatchCDCEventType.INSERT, BatchCDCEventType.UPDATE},
    format=OutputFormat.JSON,
    group_batches=False  # Individual events
)

# Start consuming
def on_event(event_bytes):
    event = json.loads(event_bytes)
    print(f"Received: {event['operation']} on {event['table']}")

consumer.start(callback=on_event)
```

### Batch Grouping Consumer

```python
# Create consumer with batch grouping
consumer = manager.create_consumer(
    consumer_id="batch_consumer",
    group_batches=True  # Group events by batch
)

def on_individual_event(event_bytes):
    # Called for every event (including markers)
    event = json.loads(event_bytes)
    print(f"Event: {event['operation']}")

def on_complete_batch(batch_id, events):
    # Called when BATCH_END is received
    # events: list of all batch command events
    print(f"Complete batch {batch_id}: {len(events)} events")
    for event_bytes in events:
        event = json.loads(event_bytes)
        process_event(event)

consumer.start(
    callback=on_individual_event,
    batch_callback=on_complete_batch
)
```

## Rate Limiting

Protect consumers from being overwhelmed by large batches:

```python
from cdc_batch import BatchCDCManager

# Create manager with rate limiting
manager = BatchCDCManager(
    rate_limit=True,
    max_events_per_second=10000.0,
    burst_size=100
)

# Events will be throttled if they exceed the rate limit
```

### Rate Limiter Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_events_per_second` | 10000.0 | Maximum sustained rate |
| `burst_size` | 100 | Maximum burst allowed |

## Kafka Integration

### Setup

```python
from cdc_batch import BatchCDCManager

manager = BatchCDCManager()

# Configure Kafka
manager.setup_kafka(
    bootstrap_servers="localhost:9092",
    topic_prefix="kosdb.cdc"
)
```

### Topic Naming

| Event Type | Topic Pattern | Example |
|------------|---------------|---------|
| Single Event | `{prefix}.{table}` | `kosdb.cdc.users` |
| Batch Event | `{prefix}.batch.{table}` | `kosdb.cdc.batch.users` |
| Batch Complete | `{prefix}.batch.complete.{table}` | `kosdb.cdc.batch.complete.users` |

### Kafka Headers

Batch events include headers for correlation:

```python
headers = [
    ('batch_id', 'batch_001'),
    ('batch_seq', '1'),
    ('batch_total', '3')
]
```

## Filtering

### Table Filtering

```python
consumer = manager.create_consumer(
    consumer_id="filtered",
    tables={"users", "accounts"}  # Only these tables
)
```

### Operation Filtering

```python
consumer = manager.create_consumer(
    consumer_id="inserts_only",
    operations={BatchCDCEventType.INSERT}  # Only INSERTs
)
```

### Batch Event Filtering

```python
# Include batch markers
consumer = manager.create_consumer(
    consumer_id="with_markers",
    operations={
        BatchCDCEventType.INSERT,
        BatchCDCEventType.BATCH_START,
        BatchCDCEventType.BATCH_END
    }
)
```

## Output Formats

### JSON (Default)

```json
{
  "sequence_number": 102,
  "timestamp": 1705312800123458,
  "operation": "INSERT",
  "table": "users",
  "key": 1,
  "after": {"id": 1, "name": "Alice"},
  "batch_id": "batch_001",
  "batch_sequence": 1,
  "batch_total": 3
}
```

### Avro

Binary format with schema:
```python
consumer = manager.create_consumer(
    consumer_id="avro_consumer",
    format=OutputFormat.AVRO
)
```

### Protobuf

Binary format:
```python
consumer = manager.create_consumer(
    consumer_id="proto_consumer",
    format=OutputFormat.PROTOBUF
)
```

## Monitoring

### CDC Statistics

```python
stats = manager.get_stats()

print(f"""
Total Events: {stats['total_events']}
Active Consumers: {stats['active_consumers']}
Active Batches: {stats['active_batches']}
Kafka Connected: {stats['kafka_connected']}
""")
```

### Consumer Position

```python
position = consumer.get_position()

print(f"""
Consumer: {position['consumer_id']}
Sequence: {position['sequence_number']}
Tables: {position['tables']}
Format: {position['format']}
Group Batches: {position['group_batches']}
""")
```

## Best Practices

### 1. Use Batch Grouping for Transactional Processing

```python
def on_batch_complete(batch_id, events):
    # Process entire batch as a unit
    with database.transaction():
        for event_bytes in events:
            event = json.loads(event_bytes)
            apply_change(event)
```

### 2. Implement Backpressure with Rate Limiting

```python
# Protect downstream systems
manager = BatchCDCManager(
    rate_limit=True,
    max_events_per_second=1000.0  # Adjust based on consumer capacity
)
```

### 3. Filter Early to Reduce Load

```python
# Filter at the consumer level
consumer = manager.create_consumer(
    tables={"important_table"},
    operations={BatchCDCEventType.INSERT, BatchCDCEventType.UPDATE}
)
```

### 4. Handle Batch Markers for State Tracking

```python
active_batches = set()

def on_event(event_bytes):
    event = json.loads(event_bytes)
    
    if event['operation'] == 'BATCH_START':
        active_batches.add(event['batch_id'])
    elif event['operation'] == 'BATCH_END':
        active_batches.discard(event['batch_id'])
```

## Troubleshooting

### High Memory Usage

**Cause**: Large batches buffering in memory

**Solution**:
```python
# Use rate limiting
manager = BatchCDCManager(rate_limit=True)

# Or consume without batch grouping
consumer = manager.create_consumer(group_batches=False)
```

### Missing Batch Events

**Cause**: Consumer filtering out batch markers

**Solution**:
```python
# Include batch markers in operations
operations={
    BatchCDCEventType.INSERT,
    BatchCDCEventType.BATCH_START,
    BatchCDCEventType.BATCH_END
}
```

### Kafka Lag

**Cause**: Large batches overwhelming Kafka

**Solution**:
```python
# Reduce batch size or add rate limiting
manager = BatchCDCManager(
    rate_limit=True,
    max_events_per_second=5000.0
)
```

## API Reference

### BatchCDCManager

```python
class BatchCDCManager:
    def __init__(self, rate_limit: bool = True)
    def emit_event(self, ...) -> int
    def emit_batch_start(self, ...) -> str
    def emit_batch_command(self, ...) -> int
    def emit_batch_end(self, ...) -> int
    def create_consumer(self, ...) -> BatchCDCConsumer
    def setup_kafka(self, ...)
    def get_stats(self) -> Dict[str, Any]
```

### BatchCDCEvent

```python
@dataclass
class BatchCDCEvent:
    sequence_number: int
    timestamp: int
    operation: BatchCDCEventType
    table: str
    key: Any
    before: Optional[Dict]
    after: Optional[Dict]
    transaction_id: Optional[str]
    lsn: Optional[int]
    batch_id: Optional[str]
    batch_sequence: Optional[int]
    batch_total: Optional[int]
    batch_error_mode: Optional[str]
    
    def is_batch_event(self) -> bool
    def is_batch_marker(self) -> bool
    def to_dict(self) -> Dict[str, Any]
```

### BatchCDCConsumer

```python
class BatchCDCConsumer:
    def start(
        self,
        callback: Optional[Callable[[bytes], None]] = None,
        batch_callback: Optional[Callable[[str, List[bytes]], None]] = None
    )
    def stop()
    def get_position() -> Dict[str, Any]
```

## See Also

- [Batch Error Handling](BATCH_ERROR_HANDLING.md)
- [Replication Batch Guide](REPLICATION_BATCH.md)
- [Security Considerations](SECURITY_README.md)
