# Change Data Capture (CDC) for KosDB

Stream database changes to external systems with multiple output formats and configurable filtering.

## Features

- **Ordered Event Log**: Global sequence numbers for event ordering
- **Multiple Formats**: JSON, Avro, Protobuf encoding
- **Configurable Consumers**: Filter by table and operation type
- **Kafka Integration**: Stream events to Kafka topics
- **Snapshot Support**: Initialize consumers with current state

## Event Types

| Operation | Description |
|-----------|-------------|
| INSERT | New row inserted |
| UPDATE | Row updated |
| DELETE | Row deleted |
| BEGIN | Transaction started |
| COMMIT | Transaction committed |
| ROLLBACK | Transaction rolled back |

## Output Formats

| Format | Description |
|--------|-------------|
| JSON | Human-readable JSON |
| Avro | Binary Avro with schema |
| Protobuf | Protocol Buffers binary |

## SQL Commands

### Start CDC Consumer
```sql
CDC START CONSUMER consumer1 TABLES users,orders OPS INSERT,UPDATE FORMAT json
CDC START CONSUMER consumer2 FROM_LATEST
```

### Stop CDC Consumer
```sql
CDC STOP CONSUMER consumer1
```

### List Consumers
```sql
CDC LIST CONSUMERS
```

### CDC Statistics
```sql
CDC STATS
```

### Setup Kafka
```sql
CDC SETUP KAFKA localhost:9092 PREFIX kosdb.cdc
```

### Create Snapshot
```sql
CDC SNAPSHOT users,orders,products
```

## API Reference

### CDCEvent

```python
from cdc import CDCEvent, OperationType

event = CDCEvent(
    sequence_number=1,
    timestamp=1234567890000000,
    operation=OperationType.INSERT,
    table="users",
    key="user_001",
    after={'name': 'John', 'email': 'john@example.com'},
    transaction_id="tx_123"
)
```

### CDCEventEncoder

```python
from cdc import CDCEventEncoder, OutputFormat

# Encode to different formats
json_bytes = CDCEventEncoder.encode(event, OutputFormat.JSON)
avro_bytes = CDCEventEncoder.encode(event, OutputFormat.AVRO)
proto_bytes = CDCEventEncoder.encode(event, OutputFormat.PROTOBUF)
```

### CDCLog

```python
from cdc import CDCLog

log = CDCLog()

# Append event
seq = log.append(event)

# Get events from sequence
events = log.get_events(start_seq=100, limit=1000)

# Subscribe to events
def on_event(event):
    print(f"Received: {event}")

log.subscribe(on_event)

# Create snapshot
snapshot = log.create_snapshot(['users', 'orders'])
```

### CDCConsumer

```python
from cdc import CDCConsumer, OutputFormat, OperationType

consumer = CDCConsumer(
    consumer_id="my_consumer",
    cdc_log=log,
    tables={"users", "orders"},  # Filter tables
    operations={OperationType.INSERT, OperationType.UPDATE},  # Filter ops
    output_format=OutputFormat.JSON,
    start_from_latest=False  # Include snapshot
)

def handle_event(data: bytes):
    # Process encoded event
    pass

consumer.start(handle_event)

# Stop later
consumer.stop()
```

### KafkaCDCConnector

```python
from cdc import KafkaCDCConnector

# Setup connector
connector = KafkaCDCConnector(
    bootstrap_servers="localhost:9092",
    topic_prefix="kosdb.cdc"
)
connector.connect()

# Produce event
connector.produce_event(event, format=OutputFormat.JSON)

# Create consumer
def process_event(event):
    print(f"Received: {event}")

connector.create_consumer(
    group_id="my_group",
    tables=["users", "orders"],
    callback=process_event
)

# Cleanup
connector.close()
```

### CDCManager

```python
from cdc import get_cdc_manager, OperationType

manager = get_cdc_manager()

# Emit events
manager.emit_event(
    operation=OperationType.INSERT,
    table="users",
    key="user_001",
    after={'name': 'John'}
)

# Create consumer
consumer = manager.create_consumer(
    consumer_id="consumer1",
    tables={"users"},
    format=OutputFormat.JSON,
    callback=lambda d: print(d)
)

# Setup Kafka
manager.setup_kafka("localhost:9092", "kosdb.cdc")

# Get stats
stats = manager.get_stats()
```

## Example: Real-time Analytics

```python
from cdc import get_cdc_manager, CDCConsumer, OutputFormat, OperationType
import json

# Setup CDC
manager = get_cdc_manager()

# Analytics consumer
def analytics_handler(data: bytes):
    event = json.loads(data)
    
    # Send to analytics pipeline
    if event['table'] == 'orders':
        print(f"Order event: {event['operation']} - {event['key']}")
        # analytics_pipeline.track(event)

# Start consumer for orders
consumer = manager.create_consumer(
    consumer_id="analytics_orders",
    tables={"orders"},
    operations={OperationType.INSERT},
    format=OutputFormat.JSON,
    callback=analytics_handler
)

# Emit events from application
def on_order_created(order_id, order_data):
    manager.emit_event(
        operation=OperationType.INSERT,
        table="orders",
        key=order_id,
        after=order_data
    )

# Example usage
on_order_created("order_123", {
    'customer_id': 'cust_456',
    'total': 99.99,
    'items': 3
})
```

## Example: Kafka Streaming

```python
from cdc import get_cdc_manager

manager = get_cdc_manager()

# Configure Kafka
manager.setup_kafka(
    bootstrap_servers="kafka:9092",
    topic_prefix="ecommerce.cdc"
)

# All events now automatically stream to Kafka
# Topic format: {prefix}.{table_name}

# Example topics:
# - ecommerce.cdc.users
# - ecommerce.cdc.orders
# - ecommerce.cdc.products
```

## Configuration

```json
{
    "cdc": {
        "log_file": "cdc.log",
        "default_format": "json",
        "snapshot_batch_size": 1000,
        "consumer_poll_interval_ms": 100
    }
}
```

## Testing

```bash
python test_cdc.py
```

All 15 tests passing ✓
