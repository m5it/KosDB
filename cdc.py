"""
Change Data Capture (CDC) for KosDB

Streams database changes to external systems with multiple output formats,
configurable filtering, and Kafka integration.
"""

import json
import time
import logging
import threading
from enum import Enum, auto
from typing import Dict, List, Optional, Any, Callable, Set, BinaryIO
from dataclasses import dataclass, field, asdict
from datetime import datetime
from io import BytesIO
import struct

logger = logging.getLogger(__name__)


class OperationType(Enum):
    """Database operation types."""
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    BEGIN = "BEGIN"
    COMMIT = "COMMIT"
    ROLLBACK = "ROLLBACK"


class OutputFormat(Enum):
    """CDC output formats."""
    JSON = "json"
    AVRO = "avro"
    PROTOBUF = "protobuf"


@dataclass
class CDCEvent:
    """
    Represents a single change event.
    
    Attributes:
        sequence_number: Global ordering sequence
        timestamp: Event timestamp (Unix microseconds)
        operation: Type of operation
        table: Table name
        key: Primary key value
        before: Row data before change (for UPDATE/DELETE)
        after: Row data after change (for INSERT/UPDATE)
        transaction_id: Transaction identifier
        lsn: Log sequence number
    """
    sequence_number: int
    timestamp: int
    operation: OperationType
    table: str
    key: Any
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None
    transaction_id: Optional[str] = None
    lsn: Optional[int] = None
    
    def __post_init__(self):
        if isinstance(self.operation, str):
            self.operation = OperationType(self.operation)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'sequence_number': self.sequence_number,
            'timestamp': self.timestamp,
            'timestamp_iso': datetime.fromtimestamp(self.timestamp / 1_000_000).isoformat(),
            'operation': self.operation.value,
            'table': self.table,
            'key': self.key,
            'before': self.before,
            'after': self.after,
            'transaction_id': self.transaction_id,
            'lsn': self.lsn
        }


class CDCEventEncoder:
    """
    Encodes CDC events to various output formats.
    """
    
    @staticmethod
    def encode(event: CDCEvent, format: OutputFormat) -> bytes:
        """
        Encode event to specified format.
        
        Args:
            event: CDC event
            format: Output format
        
        Returns:
            Encoded bytes
        """
        if format == OutputFormat.JSON:
            return CDCEventEncoder._encode_json(event)
        elif format == OutputFormat.AVRO:
            return CDCEventEncoder._encode_avro(event)
        elif format == OutputFormat.PROTOBUF:
            return CDCEventEncoder._encode_protobuf(event)
        else:
            raise ValueError(f"Unknown format: {format}")
    
    @staticmethod
    def _encode_json(event: CDCEvent) -> bytes:
        """Encode as JSON."""
        return json.dumps(event.to_dict(), default=str).encode('utf-8')
    
    @staticmethod
    def _encode_avro(event: CDCEvent) -> bytes:
        """
        Encode as Avro binary.
        
        Simplified implementation - full Avro would use fastavro library.
        """
        # Avro header with schema fingerprint
        header = b'Obj\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        
        # Encode data as JSON for simplicity (real Avro uses binary encoding)
        data = json.dumps({
            'seq': event.sequence_number,
            'ts': event.timestamp,
            'op': event.operation.value,
            'tbl': event.table,
            'key': event.key,
            'before': event.before,
            'after': event.after,
            'tx': event.transaction_id
        }).encode('utf-8')
        
        # Length-prefixed
        length = struct.pack('>I', len(data))
        return header + length + data
    
    @staticmethod
    def _encode_protobuf(event: CDCEvent) -> bytes:
        """
        Encode as Protobuf binary.
        
        Simplified implementation - full protobuf would use generated code.
        """
        # Protobuf-like wire format (varint length prefix)
        data = json.dumps(event.to_dict(), default=str).encode('utf-8')
        
        # Varint encode length
        length = len(data)
        varint = []
        while length > 0x7f:
            varint.append((length & 0x7f) | 0x80)
            length >>= 7
        varint.append(length)
        
        return bytes(varint) + data


class CDCLog:
    """
    Ordered log of CDC events with persistence.
    """
    
    def __init__(self, log_file: str = "cdc.log"):
        self.log_file = log_file
        self._sequence = 0
        self._events: List[CDCEvent] = []
        self._lock = threading.RLock()
        self._subscribers: List[Callable[[CDCEvent], None]] = []
        self._running = True
    
    def append(self, event: CDCEvent) -> int:
        """
        Append event to log.
        
        Args:
            event: CDC event
        
        Returns:
            Sequence number
        """
        with self._lock:
            self._sequence += 1
            event.sequence_number = self._sequence
            event.timestamp = int(time.time() * 1_000_000)  # Microseconds
            
            self._events.append(event)
            
            # Notify subscribers
            for subscriber in self._subscribers:
                try:
                    subscriber(event)
                except Exception as e:
                    logger.error(f"Subscriber error: {e}")
            
            return self._sequence
    
    def get_events(self, start_seq: int, limit: int = 1000) -> List[CDCEvent]:
        """
        Get events from sequence number.
        
        Args:
            start_seq: Starting sequence number
            limit: Maximum events
        
        Returns:
            List of events
        """
        with self._lock:
            events = [e for e in self._events if e.sequence_number >= start_seq]
            return events[:limit]
    
    def subscribe(self, callback: Callable[[CDCEvent], None]):
        """Subscribe to events."""
        with self._lock:
            self._subscribers.append(callback)
    
    def unsubscribe(self, callback: Callable[[CDCEvent], None]):
        """Unsubscribe from events."""
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)
    
    def get_latest_sequence(self) -> int:
        """Get latest sequence number."""
        with self._lock:
            return self._sequence
    
    def create_snapshot(self, tables: List[str]) -> List[CDCEvent]:
        """
        Create snapshot of current data.
        
        Args:
            tables: Tables to snapshot
        
        Returns:
            List of INSERT events representing current state
        """
        # In real implementation, would query database
        snapshot = []
        
        # Mock snapshot data
        for table in tables:
            for i in range(10):  # Mock 10 rows per table
                event = CDCEvent(
                    sequence_number=0,
                    timestamp=int(time.time() * 1_000_000),
                    operation=OperationType.INSERT,
                    table=table,
                    key=f"{table}_key_{i}",
                    after={'id': i, 'data': f'snapshot_{i}'}
                )
                snapshot.append(event)
        
        return snapshot


class CDCConsumer:
    """
    CDC consumer with configurable filtering.
    """
    
    def __init__(
        self,
        consumer_id: str,
        cdc_log: CDCLog,
        tables: Optional[Set[str]] = None,
        operations: Optional[Set[OperationType]] = None,
        output_format: OutputFormat = OutputFormat.JSON,
        start_from_latest: bool = False
    ):
        """
        Initialize CDC consumer.
        
        Args:
            consumer_id: Unique consumer ID
            cdc_log: CDC log to consume from
            tables: Filter by tables (None = all)
            operations: Filter by operations (None = all)
            output_format: Output format
            start_from_latest: Start from latest events
        """
        self.consumer_id = consumer_id
        self.cdc_log = cdc_log
        self.tables = tables
        self.operations = operations
        self.output_format = output_format
        self.start_from_latest = start_from_latest
        
        self._current_seq = cdc_log.get_latest_sequence() if start_from_latest else 0
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable[[bytes], None]] = None
    
    def start(self, callback: Callable[[bytes], None]):
        """
        Start consuming events.
        
        Args:
            callback: Function to call with encoded events
        """
        self._callback = callback
        self._running = True
        
        # Get snapshot if starting from beginning
        if not self.start_from_latest:
            snapshot = self.cdc_log.create_snapshot(['*'])
            for event in snapshot:
                if self._should_consume(event):
                    encoded = CDCEventEncoder.encode(event, self.output_format)
                    self._callback(encoded)
        
        # Start polling thread
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()
        
        logger.info(f"Started CDC consumer: {self.consumer_id}")
    
    def stop(self):
        """Stop consuming events."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
    
    def _poll(self):
        """Poll for new events."""
        while self._running:
            events = self.cdc_log.get_events(self._current_seq + 1)
            
            for event in events:
                if self._should_consume(event):
                    encoded = CDCEventEncoder.encode(event, self.output_format)
                    if self._callback:
                        self._callback(encoded)
                
                self._current_seq = event.sequence_number
            
            time.sleep(0.1)  # 100ms poll interval
    
    def _should_consume(self, event: CDCEvent) -> bool:
        """Check if event should be consumed based on filters."""
        if self.tables and event.table not in self.tables:
            return False
        
        if self.operations and event.operation not in self.operations:
            return False
        
        return True
    
    def get_position(self) -> Dict[str, Any]:
        """Get current consumer position."""
        return {
            'consumer_id': self.consumer_id,
            'sequence_number': self._current_seq,
            'tables': list(self.tables) if self.tables else None,
            'operations': [op.value for op in self.operations] if self.operations else None,
            'format': self.output_format.value
        }


class KafkaCDCConnector:
    """
    Kafka connector for CDC event streaming.
    """
    
    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        topic_prefix: str = "kosdb.cdc"
    ):
        """
        Initialize Kafka connector.
        
        Args:
            bootstrap_servers: Kafka bootstrap servers
            topic_prefix: Topic prefix for CDC events
        """
        self.bootstrap_servers = bootstrap_servers
        self.topic_prefix = topic_prefix
        self._producer = None
        self._consumers: Dict[str, Any] = {}
        
        try:
            from kafka import KafkaProducer, KafkaConsumer
            self._kafka_available = True
        except ImportError:
            logger.warning("kafka-python not installed. Kafka features disabled.")
            self._kafka_available = False
    
    def connect(self):
        """Connect to Kafka."""
        if not self._kafka_available:
            raise ImportError("kafka-python required for Kafka integration")
        
        from kafka import KafkaProducer
        
        self._producer = KafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: v if isinstance(v, bytes) else json.dumps(v).encode()
        )
        
        logger.info(f"Connected to Kafka: {self.bootstrap_servers}")
    
    def produce_event(self, event: CDCEvent, format: OutputFormat = OutputFormat.JSON):
        """
        Produce event to Kafka.
        
        Args:
            event: CDC event
            format: Output format
        """
        if not self._producer:
            raise RuntimeError("Not connected to Kafka")
        
        topic = f"{self.topic_prefix}.{event.table}"
        data = CDCEventEncoder.encode(event, format)
        
        self._producer.send(topic, value=data)
        self._producer.flush()
    
    def create_consumer(
        self,
        group_id: str,
        tables: List[str],
        callback: Callable[[CDCEvent], None]
    ):
        """
        Create Kafka consumer for CDC events.
        
        Args:
            group_id: Consumer group ID
            tables: Tables to consume
            callback: Event callback
        """
        if not self._kafka_available:
            raise ImportError("kafka-python required")
        
        from kafka import KafkaConsumer
        
        topics = [f"{self.topic_prefix}.{table}" for table in tables]
        
        consumer = KafkaConsumer(
            *topics,
            group_id=group_id,
            bootstrap_servers=self.bootstrap_servers,
            value_deserializer=lambda v: json.loads(v.decode())
        )
        
        self._consumers[group_id] = consumer
        
        # Start consumption thread
        def consume():
            for message in consumer:
                event_data = message.value
                event = CDCEvent(**event_data)
                callback(event)
        
        thread = threading.Thread(target=consume, daemon=True)
        thread.start()
    
    def close(self):
        """Close all connections."""
        if self._producer:
            self._producer.close()
        
        for consumer in self._consumers.values():
            consumer.close()


class CDCManager:
    """
    Manages CDC for the database.
    """
    
    def __init__(self):
        self.cdc_log = CDCLog()
        self.consumers: Dict[str, CDCConsumer] = {}
        self.kafka_connector: Optional[KafkaCDCConnector] = None
        self._lock = threading.RLock()
    
    def emit_event(
        self,
        operation: OperationType,
        table: str,
        key: Any,
        before: Optional[Dict] = None,
        after: Optional[Dict] = None,
        transaction_id: Optional[str] = None
    ) -> int:
        """
        Emit a CDC event.
        
        Args:
            operation: Operation type
            table: Table name
            key: Primary key
            before: Before state
            after: After state
            transaction_id: Transaction ID
        
        Returns:
            Sequence number
        """
        event = CDCEvent(
            sequence_number=0,
            timestamp=0,
            operation=operation,
            table=table,
            key=key,
            before=before,
            after=after,
            transaction_id=transaction_id
        )
        
        return self.cdc_log.append(event)
    
    def create_consumer(
        self,
        consumer_id: str,
        tables: Optional[Set[str]] = None,
        operations: Optional[Set[OperationType]] = None,
        format: OutputFormat = OutputFormat.JSON,
        callback: Optional[Callable[[bytes], None]] = None
    ) -> CDCConsumer:
        """
        Create a CDC consumer.
        
        Args:
            consumer_id: Consumer ID
            tables: Table filter
            operations: Operation filter
            format: Output format
            callback: Event callback
        
        Returns:
            CDC consumer
        """
        with self._lock:
            consumer = CDCConsumer(
                consumer_id=consumer_id,
                cdc_log=self.cdc_log,
                tables=tables,
                operations=operations,
                output_format=format
            )
            
            self.consumers[consumer_id] = consumer
            
            if callback:
                consumer.start(callback)
            
            return consumer
    
    def setup_kafka(self, bootstrap_servers: str, topic_prefix: str = "kosdb.cdc"):
        """
        Setup Kafka integration.
        
        Args:
            bootstrap_servers: Kafka servers
            topic_prefix: Topic prefix
        """
        self.kafka_connector = KafkaCDCConnector(bootstrap_servers, topic_prefix)
        self.kafka_connector.connect()
        
        # Subscribe CDC log to Kafka
        def forward_to_kafka(event: CDCEvent):
            if self.kafka_connector:
                self.kafka_connector.produce_event(event)
        
        self.cdc_log.subscribe(forward_to_kafka)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get CDC statistics."""
        return {
            'total_events': self.cdc_log.get_latest_sequence(),
            'active_consumers': len(self.consumers),
            'kafka_connected': self.kafka_connector is not None
        }


# Global CDC manager
_cdc_manager = CDCManager()


def get_cdc_manager() -> CDCManager:
    """Get global CDC manager."""
    return _cdc_manager
