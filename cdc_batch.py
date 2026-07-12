
"""
Change Data Capture (CDC) with Batch Support for KosDB v2.3.0

Extends CDC to handle batch operations with:
- Individual change events for each batch command
- Batch correlation via batch_id
- Batch sequence numbers
- Atomic batch notifications (begin/end markers)
- Rate limiting for large batches
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
import uuid

logger = logging.getLogger(__name__)


class BatchCDCEventType(Enum):
    """Extended CDC event types including batch markers."""
    # Standard operations
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    
    # Transaction operations
    BEGIN = "BEGIN"
    COMMIT = "COMMIT"
    ROLLBACK = "ROLLBACK"
    
    # Batch markers
    BATCH_START = "BATCH_START"
    BATCH_END = "BATCH_END"
    BATCH_COMMAND = "BATCH_COMMAND"


class OutputFormat(Enum):
    """CDC output formats."""
    JSON = "json"
    AVRO = "avro"
    PROTOBUF = "protobuf"


@dataclass
class BatchCDCEvent:
    """
    CDC event with batch support.
    
    Attributes:
        sequence_number: Global ordering sequence
        timestamp: Event timestamp (Unix microseconds)
        operation: Type of operation
        table: Table name
        key: Primary key value
        before: Row data before change
        after: Row data after change
        transaction_id: Transaction identifier
        lsn: Log sequence number
        
        # Batch-specific fields
        batch_id: Unique batch identifier (if part of batch)
        batch_sequence: Position within batch (1-based)
        batch_total: Total commands in batch
        batch_error_mode: Error handling mode for batch
    """
    sequence_number: int
    timestamp: int
    operation: BatchCDCEventType
    table: str
    key: Any
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None
    transaction_id: Optional[str] = None
    lsn: Optional[int] = None
    
    # Batch fields
    batch_id: Optional[str] = None
    batch_sequence: Optional[int] = None
    batch_total: Optional[int] = None
    batch_error_mode: Optional[str] = None
    
    def __post_init__(self):
        if isinstance(self.operation, str):
            self.operation = BatchCDCEventType(self.operation)
    
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
            'lsn': self.lsn,
            'batch_id': self.batch_id,
            'batch_sequence': self.batch_sequence,
            'batch_total': self.batch_total,
            'batch_error_mode': self.batch_error_mode
        }
    
    def is_batch_event(self) -> bool:
        """Check if this is part of a batch."""
        return self.batch_id is not None
    
    def is_batch_marker(self) -> bool:
        """Check if this is a batch marker (start/end)."""
        return self.operation in (BatchCDCEventType.BATCH_START, 
                                  BatchCDCEventType.BATCH_END)


class BatchCDCEventEncoder:
    """
    Encodes batch CDC events to various output formats.
    """
    
    @staticmethod
    def encode(event: BatchCDCEvent, format: OutputFormat) -> bytes:
        """
        Encode event to specified format.
        
        Args:
            event: CDC event
            format: Output format
        
        Returns:
            Encoded bytes
        """
        if format == OutputFormat.JSON:
            return BatchCDCEventEncoder._encode_json(event)
        elif format == OutputFormat.AVRO:
            return BatchCDCEventEncoder._encode_avro(event)
        elif format == OutputFormat.PROTOBUF:
            return BatchCDCEventEncoder._encode_protobuf(event)
        else:
            raise ValueError(f"Unknown format: {format}")
    
    @staticmethod
    def _encode_json(event: BatchCDCEvent) -> bytes:
        """Encode as JSON."""
        return json.dumps(event.to_dict(), default=str).encode('utf-8')
    
    @staticmethod
    def _encode_avro(event: BatchCDCEvent) -> bytes:
        """
        Encode as Avro binary.
        """
        # Avro header with schema fingerprint
        header = b'Obj\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        
        # Encode data as JSON for simplicity
        data = json.dumps({
            'seq': event.sequence_number,
            'ts': event.timestamp,
            'op': event.operation.value,
            'tbl': event.table,
            'key': event.key,
            'before': event.before,
            'after': event.after,
            'tx': event.transaction_id,
            'batch_id': event.batch_id,
            'batch_seq': event.batch_sequence,
            'batch_total': event.batch_total
        }).encode('utf-8')
        
        # Length-prefixed
        length = struct.pack('>I', len(data))
        return header + length + data
    
    @staticmethod
    def _encode_protobuf(event: BatchCDCEvent) -> bytes:
        """
        Encode as Protobuf binary.
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


class RateLimiter:
    """
    Rate limiter for CDC event emission.
    Prevents overwhelming consumers with large batches.
    """
    
    def __init__(
        self,
        max_events_per_second: float = 1000.0,
        burst_size: int = 100
    ):
        self.max_events_per_second = max_events_per_second
        self.burst_size = burst_size
        self._tokens = burst_size
        self._last_update = time.time()
        self._lock = threading.Lock()
    
    def acquire(self, tokens: int = 1) -> bool:
        """
        Acquire tokens for event emission.
        
        Args:
            tokens: Number of tokens to acquire
        
        Returns:
            True if tokens acquired, False if rate limited
        """
        with self._lock:
            now = time.time()
            elapsed = now - self._last_update
            
            # Add tokens based on elapsed time
            self._tokens = min(
                self.burst_size,
                self._tokens + elapsed * self.max_events_per_second
            )
            self._last_update = now
            
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            
            return False
    
    def acquire_blocking(self, tokens: int = 1, timeout: Optional[float] = None) -> bool:
        """
        Acquire tokens, blocking if necessary.
        
        Args:
            tokens: Number of tokens
            timeout: Maximum time to wait
        
        Returns:
            True if tokens acquired
        """
        start = time.time()
        
        while not self.acquire(tokens):
            if timeout and (time.time() - start) > timeout:
                return False
            time.sleep(0.001)  # 1ms sleep
        
        return True


class BatchCDCLog:
    """
    Ordered log of CDC events with batch support and persistence.
    """
    
    def __init__(
        self,
        log_file: str = "cdc.log",
        rate_limit: bool = True,
        max_events_per_second: float = 10000.0
    ):
        self.log_file = log_file
        self._sequence = 0
        self._events: List[BatchCDCEvent] = []
        self._lock = threading.RLock()
        self._subscribers: List[Callable[[BatchCDCEvent], None]] = []
        self._running = True
        
        # Rate limiting
        self._rate_limiter = RateLimiter(max_events_per_second) if rate_limit else None
        
        # Batch tracking
        self._active_batches: Dict[str, Dict] = {}
    
    def append(self, event: BatchCDCEvent) -> int:
        """
        Append event to log.
        
        Args:
            event: CDC event
        
        Returns:
            Sequence number
        """
        # Apply rate limiting if enabled
        if self._rate_limiter:
            if not self._rate_limiter.acquire_blocking(1, timeout=1.0):
                logger.warning("Rate limit exceeded, dropping event")
                return -1
        
        with self._lock:
            self._sequence += 1
            event.sequence_number = self._sequence
            event.timestamp = int(time.time() * 1_000_000)  # Microseconds
            
            self._events.append(event)
            
            # Track batch state
            if event.batch_id:
                if event.operation == BatchCDCEventType.BATCH_START:
                    self._active_batches[event.batch_id] = {
                        'start_time': time.time(),
                        'command_count': 0
                    }
                elif event.operation == BatchCDCEventType.BATCH_COMMAND:
                    if event.batch_id in self._active_batches:
                        self._active_batches[event.batch_id]['command_count'] += 1
                elif event.operation == BatchCDCEventType.BATCH_END:
                    self._active_batches.pop(event.batch_id, None)
            
            # Notify subscribers
            for subscriber in self._subscribers:
                try:
                    subscriber(event)
                except Exception as e:
                    logger.error(f"Subscriber error: {e}")
            
            return self._sequence
    
    def emit_batch_start(
        self,
        batch_id: str,
        database: str,
        total_commands: int,
        error_mode: str = "continue"
    ) -> int:
        """
        Emit batch start marker.
        
        Args:
            batch_id: Unique batch identifier
            database: Database name
            total_commands: Expected number of commands
            error_mode: Error handling mode
        
        Returns:
            Sequence number
        """
        event = BatchCDCEvent(
            sequence_number=0,
            timestamp=0,
            operation=BatchCDCEventType.BATCH_START,
            table="",
            key=None,
            batch_id=batch_id,
            batch_sequence=0,
            batch_total=total_commands,
            batch_error_mode=error_mode
        )
        return self.append(event)
    
    def emit_batch_command(
        self,
        batch_id: str,
        sequence: int,
        total: int,
        operation: BatchCDCEventType,
        table: str,
        key: Any,
        before: Optional[Dict] = None,
        after: Optional[Dict] = None,
        error_mode: str = "continue"
    ) -> int:
        """
        Emit individual batch command event.
        
        Args:
            batch_id: Batch identifier
            sequence: Position within batch (1-based)
            total: Total commands in batch
            operation: Command operation type
            table: Table name
            key: Primary key
            before: Before state
            after: After state
            error_mode: Error handling mode
        
        Returns:
            Sequence number
        """
        event = BatchCDCEvent(
            sequence_number=0,
            timestamp=0,
            operation=operation,
            table=table,
            key=key,
            before=before,
            after=after,
            batch_id=batch_id,
            batch_sequence=sequence,
            batch_total=total,
            batch_error_mode=error_mode
        )
        return self.append(event)
    
    def emit_batch_end(
        self,
        batch_id: str,
        commands_executed: int,
        commands_failed: int
    ) -> int:
        """
        Emit batch end marker.
        
        Args:
            batch_id: Batch identifier
            commands_executed: Number executed
            commands_failed: Number failed
        
        Returns:
            Sequence number
        """
        event = BatchCDCEvent(
            sequence_number=0,
            timestamp=0,
            operation=BatchCDCEventType.BATCH_END,
            table="",
            key=None,
            batch_id=batch_id,
            batch_sequence=0,
            batch_total=commands_executed,
            batch_error_mode=None
        )
        return self.append(event)
    
    def get_events(self, start_seq: int, limit: int = 1000) -> List[BatchCDCEvent]:
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
    
    def get_batch_events(self, batch_id: str) -> List[BatchCDCEvent]:
        """
        Get all events for a specific batch.
        
        Args:
            batch_id: Batch identifier
        
        Returns:
            List of batch events
        """
        with self._lock:
            return [e for e in self._events if e.batch_id == batch_id]
    
    def subscribe(self, callback: Callable[[BatchCDCEvent], None]):
        """Subscribe to events."""
        with self._lock:
            self._subscribers.append(callback)
    
    def unsubscribe(self, callback: Callable[[BatchCDCEvent], None]):
        """Unsubscribe from events."""
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)
    
    def get_latest_sequence(self) -> int:
        """Get latest sequence number."""
        with self._lock:
            return self._sequence
    
    def get_active_batches(self) -> List[Dict]:
        """Get list of active (incomplete) batches."""
        with self._lock:
            return [
                {
                    'batch_id': bid,
                    'info': info
                }
                for bid, info in self._active_batches.items()
            ]


class BatchCDCConsumer:
    """
    CDC consumer with batch grouping support.
    """
    
    def __init__(
        self,
        consumer_id: str,
        cdc_log: BatchCDCLog,
        tables: Optional[Set[str]] = None,
        operations: Optional[Set[BatchCDCEventType]] = None,
        output_format: OutputFormat = OutputFormat.JSON,
        start_from_latest: bool = False,
        group_batches: bool = True  # New: Group events by batch
    ):
        """
        Initialize batch CDC consumer.
        
        Args:
            consumer_id: Unique consumer ID
            cdc_log: CDC log to consume from
            tables: Filter by tables
            operations: Filter by operations
            output_format: Output format
            start_from_latest: Start from latest events
            group_batches: Group events by batch ID
        """
        self.consumer_id = consumer_id
        self.cdc_log = cdc_log
        self.tables = tables
        self.operations = operations
        self.output_format = output_format
        self.start_from_latest = start_from_latest
        self.group_batches = group_batches
        
        self._current_seq = cdc_log.get_latest_sequence() if start_from_latest else 0
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable[[bytes], None]] = None
        self._batch_callback: Optional[Callable[[str, List[bytes]], None]] = None
        
        # Batch grouping buffer
        self._batch_buffer: Dict[str, List[BatchCDCEvent]] = {}
        self._batch_lock = threading.Lock()
    
    def start(
        self,
        callback: Optional[Callable[[bytes], None]] = None,
        batch_callback: Optional[Callable[[str, List[bytes]], None]] = None
    ):
        """
        Start consuming events.
        
        Args:
            callback: Function for individual events
            batch_callback: Function for complete batches (batch_id, events)
        """
        self._callback = callback
        self._batch_callback = batch_callback
        self._running = True
        
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()
        
        logger.info(f"Started batch CDC consumer: {self.consumer_id}")
    
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
                    self._process_event(event)
                
                self._current_seq = event.sequence_number
            
            time.sleep(0.01)  # 10ms poll interval
    
    def _process_event(self, event: BatchCDCEvent):
        """Process a CDC event."""
        if self.group_batches and event.batch_id:
            self._process_batch_event(event)
        else:
            # Individual event processing
            if self._callback:
                encoded = BatchCDCEventEncoder.encode(event, self.output_format)
                self._callback(encoded)
    
    def _process_batch_event(self, event: BatchCDCEvent):
        """Process event as part of batch grouping."""
        with self._batch_lock:
            if event.operation == BatchCDCEventType.BATCH_START:
                # Initialize batch buffer
                self._batch_buffer[event.batch_id] = []
                
                # Also emit start marker if callback provided
                if self._callback:
                    encoded = BatchCDCEventEncoder.encode(event, self.output_format)
                    self._callback(encoded)
            
            elif event.operation == BatchCDCEventType.BATCH_END:
                # Complete batch
                batch_events = self._batch_buffer.pop(event.batch_id, [])
                
                if self._batch_callback:
                    # Encode all events
                    encoded_events = [
                        BatchCDCEventEncoder.encode(e, self.output_format)
                        for e in batch_events
                    ]
                    self._batch_callback(event.batch_id, encoded_events)
                
                # Also emit end marker if callback provided
                if self._callback:
                    encoded = BatchCDCEventEncoder.encode(event, self.output_format)
                    self._callback(encoded)
            
            else:
                # Regular batch command
                if event.batch_id in self._batch_buffer:
                    self._batch_buffer[event.batch_id].append(event)
                
                # Also emit if callback provided
                if self._callback:
                    encoded = BatchCDCEventEncoder.encode(event, self.output_format)
                    self._callback(encoded)
    
    def _should_consume(self, event: BatchCDCEvent) -> bool:
        """Check if event should be consumed."""
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
            'format': self.output_format.value,
            'group_batches': self.group_batches
        }


class BatchKafkaCDCConnector:
    """
    Kafka connector for batch CDC event streaming.
    """
    
    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        topic_prefix: str = "kosdb.cdc"
    ):
        self.bootstrap_servers = bootstrap_servers
        self.topic_prefix = topic_prefix
        self._producer = None
        
        try:
            from kafka import KafkaProducer
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
    
    def produce_event(self, event: BatchCDCEvent, format: OutputFormat = OutputFormat.JSON):
        """
        Produce event to Kafka.
        
        Args:
            event: CDC event
            format: Output format
        """
        if not self._producer:
            raise RuntimeError("Not connected to Kafka")
        
        # Use batch-specific topic if part of batch
        if event.batch_id:
            topic = f"{self.topic_prefix}.batch.{event.table}"
        else:
            topic = f"{self.topic_prefix}.{event.table}"
        
        data = BatchCDCEventEncoder.encode(event, format)
        
        # Add headers for batch correlation
        headers = []
        if event.batch_id:
            headers.append(('batch_id', event.batch_id.encode()))
            headers.append(('batch_seq', str(event.batch_sequence).encode()))
        
        self._producer.send(topic, value=data, headers=headers)
    
    def produce_batch_complete(self, batch_id: str, events: List[bytes], table: str):
        """
        Produce complete batch to Kafka.
        
        Args:
            batch_id: Batch identifier
            events: List of encoded events
            table: Table name
        """
        if not self._producer:
            raise RuntimeError("Not connected to Kafka")
        
        topic = f"{self.topic_prefix}.batch.complete.{table}"
        
        # Send batch summary
        summary = {
            'batch_id': batch_id,
            'event_count': len(events),
            'table': table,
            'timestamp': time.time()
        }
        
        self._producer.send(topic, value=json.dumps(summary).encode())
    
    def close(self):
        """Close connection."""
        if self._producer:
            self._producer.close()


class BatchCDCManager:
    """
    Manages batch CDC for the database.
    """
    
    def __init__(self, rate_limit: bool = True):
        self.cdc_log = BatchCDCLog(rate_limit=rate_limit)
        self.consumers: Dict[str, BatchCDCConsumer] = {}
        self.kafka_connector: Optional[BatchKafkaCDCConnector] = None
        self._lock = threading.RLock()
    
    def emit_event(
        self,
        operation: BatchCDCEventType,
        table: str,
        key: Any,
        before: Optional[Dict] = None,
        after: Optional[Dict] = None,
        transaction_id: Optional[str] = None
    ) -> int:
        """Emit a CDC event."""
        event = BatchCDCEvent(
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
    
    def emit_batch_start(self, database: str, total_commands: int, 
                         error_mode: str = "continue") -> str:
        """
        Emit batch start and return batch ID.
        
        Returns:
            batch_id: Unique batch identifier
        """
        batch_id = str(uuid.uuid4())[:16]
        
        self.cdc_log.emit_batch_start(
            batch_id=batch_id,
            database=database,
            total_commands=total_commands,
            error_mode=error_mode
        )
        
        return batch_id
    
    def emit_batch_command(
        self,
        batch_id: str,
        sequence: int,
        total: int,
        operation: BatchCDCEventType,
        table: str,
        key: Any,
        before: Optional[Dict] = None,
        after: Optional[Dict] = None,
        error_mode: str = "continue"
    ) -> int:
        """Emit batch command event."""
        return self.cdc_log.emit_batch_command(
            batch_id=batch_id,
            sequence=sequence,
            total=total,
            operation=operation,
            table=table,
            key=key,
            before=before,
            after=after,
            error_mode=error_mode
        )
    
    def emit_batch_end(self, batch_id: str, commands_executed: int,
                       commands_failed: int) -> int:
        """Emit batch end marker."""
        return self.cdc_log.emit_batch_end(
            batch_id=batch_id,
            commands_executed=commands_executed,
            commands_failed=commands_failed
        )
    
    def create_consumer(
        self,
        consumer_id: str,
        tables: Optional[Set[str]] = None,
        operations: Optional[Set[BatchCDCEventType]] = None,
        format: OutputFormat = OutputFormat.JSON,
        group_batches: bool = True
    ) -> BatchCDCConsumer:
        """Create a CDC consumer."""
        with self._lock:
            consumer = BatchCDCConsumer(
                consumer_id=consumer_id,
                cdc_log=self.cdc_log,
                tables=tables,
                operations=operations,
                output_format=format,
                group_batches=group_batches
            )
            self.consumers[consumer_id] = consumer
            return consumer
    
    def setup_kafka(self, bootstrap_servers: str, topic_prefix: str = "kosdb.cdc"):
        """Setup Kafka integration."""
        self.kafka_connector = BatchKafkaCDCConnector(bootstrap_servers, topic_prefix)
        self.kafka_connector.connect()
        
        # Subscribe CDC log to Kafka
        def forward_to_kafka(event: BatchCDCEvent):
            if self.kafka_connector:
                self.kafka_connector.produce_event(event)
        
        self.cdc_log.subscribe(forward_to_kafka)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get CDC statistics."""
        return {
            'total_events': self.cdc_log.get_latest_sequence(),
            'active_consumers': len(self.consumers),
            'active_batches': len(self.cdc_log.get_active_batches()),
            'kafka_connected': self.kafka_connector is not None
        }


# Global batch CDC manager
_batch_cdc_manager = BatchCDCManager()


def get_batch_cdc_manager() -> BatchCDCManager:
    """Get global batch CDC manager."""
    return _batch_cdc_manager
