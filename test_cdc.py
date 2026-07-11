"""
Tests for CDC module.
"""

import unittest
import time
import json
from cdc import (
    CDCEvent,
    CDCLog,
    CDCConsumer,
    CDCEventEncoder,
    OutputFormat,
    OperationType,
    CDCManager,
    get_cdc_manager
)


class TestCDCEvent(unittest.TestCase):
    
    def test_create_event(self):
        """Test creating CDC event."""
        event = CDCEvent(
            sequence_number=1,
            timestamp=1234567890000000,
            operation=OperationType.INSERT,
            table="users",
            key="user_001",
            after={'name': 'John', 'email': 'john@example.com'}
        )
        
        self.assertEqual(event.sequence_number, 1)
        self.assertEqual(event.operation, OperationType.INSERT)
        self.assertEqual(event.table, "users")
    
    def test_to_dict(self):
        """Test event serialization."""
        event = CDCEvent(
            sequence_number=1,
            timestamp=1234567890000000,
            operation=OperationType.UPDATE,
            table="users",
            key="user_001",
            before={'name': 'Old'},
            after={'name': 'New'}
        )
        
        d = event.to_dict()
        self.assertEqual(d['operation'], 'UPDATE')
        self.assertEqual(d['table'], 'users')
        self.assertIn('before', d)
        self.assertIn('after', d)


class TestCDCEventEncoder(unittest.TestCase):
    
    def test_encode_json(self):
        """Test JSON encoding."""
        event = CDCEvent(
            sequence_number=1,
            timestamp=1234567890000000,
            operation=OperationType.INSERT,
            table="users",
            key="user_001",
            after={'data': 'test'}
        )
        
        encoded = CDCEventEncoder.encode(event, OutputFormat.JSON)
        data = json.loads(encoded)
        
        self.assertEqual(data['table'], 'users')
        self.assertEqual(data['operation'], 'INSERT')
    
    def test_encode_avro(self):
        """Test Avro encoding."""
        event = CDCEvent(
            sequence_number=1,
            timestamp=1234567890000000,
            operation=OperationType.INSERT,
            table="users",
            key="user_001"
        )
        
        encoded = CDCEventEncoder.encode(event, OutputFormat.AVRO)
        self.assertTrue(len(encoded) > 0)
    
    def test_encode_protobuf(self):
        """Test Protobuf encoding."""
        event = CDCEvent(
            sequence_number=1,
            timestamp=1234567890000000,
            operation=OperationType.INSERT,
            table="users",
            key="user_001"
        )
        
        encoded = CDCEventEncoder.encode(event, OutputFormat.PROTOBUF)
        self.assertTrue(len(encoded) > 0)


class TestCDCLog(unittest.TestCase):
    
    def setUp(self):
        self.log = CDCLog()
    
    def test_append_event(self):
        """Test appending event."""
        event = CDCEvent(
            sequence_number=0,
            timestamp=0,
            operation=OperationType.INSERT,
            table="users",
            key="user_001"
        )
        
        seq = self.log.append(event)
        
        self.assertEqual(seq, 1)
        self.assertEqual(event.sequence_number, 1)
        self.assertGreater(event.timestamp, 0)
    
    def test_get_events(self):
        """Test retrieving events."""
        for i in range(5):
            event = CDCEvent(
                sequence_number=0,
                timestamp=0,
                operation=OperationType.INSERT,
                table="users",
                key=f"user_{i}"
            )
            self.log.append(event)
        
        events = self.log.get_events(3)
        self.assertEqual(len(events), 3)
    
    def test_subscribe(self):
        """Test event subscription."""
        received = []
        
        def callback(event):
            received.append(event.sequence_number)
        
        self.log.subscribe(callback)
        
        event = CDCEvent(
            sequence_number=0,
            timestamp=0,
            operation=OperationType.INSERT,
            table="users",
            key="user_001"
        )
        self.log.append(event)
        
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0], 1)
    
    def test_create_snapshot(self):
        """Test snapshot creation."""
        tables = ["users", "orders"]
        snapshot = self.log.create_snapshot(tables)
        
        self.assertGreater(len(snapshot), 0)
        
        for event in snapshot:
            self.assertEqual(event.operation, OperationType.INSERT)


class TestCDCConsumer(unittest.TestCase):
    
    def setUp(self):
        self.log = CDCLog()
        self.received = []
        
        def callback(data):
            self.received.append(data)
        
        self.callback = callback
    
    def test_consumer_filtering(self):
        """Test consumer with filters."""
        consumer = CDCConsumer(
            consumer_id="test_consumer",
            cdc_log=self.log,
            tables={"users"},
            operations={OperationType.INSERT},
            output_format=OutputFormat.JSON
        )
        
        event1 = CDCEvent(
            sequence_number=0,
            timestamp=0,
            operation=OperationType.INSERT,
            table="users",
            key="user_001"
        )
        self.log.append(event1)
        
        event2 = CDCEvent(
            sequence_number=0,
            timestamp=0,
            operation=OperationType.INSERT,
            table="orders",
            key="order_001"
        )
        self.log.append(event2)
        
        event3 = CDCEvent(
            sequence_number=0,
            timestamp=0,
            operation=OperationType.DELETE,
            table="users",
            key="user_002"
        )
        self.log.append(event3)
        
        consumer.start(self.callback)
        time.sleep(0.2)
        
        self.assertEqual(len(self.received), 1)
        
        consumer.stop()
    
    def test_consumer_position(self):
        """Test consumer position tracking."""
        consumer = CDCConsumer(
            consumer_id="pos_test",
            cdc_log=self.log,
            output_format=OutputFormat.JSON
        )
        
        for i in range(3):
            event = CDCEvent(
                sequence_number=0,
                timestamp=0,
                operation=OperationType.INSERT,
                table="users",
                key=f"user_{i}"
            )
            self.log.append(event)
        
        pos = consumer.get_position()
        
        self.assertEqual(pos['consumer_id'], 'pos_test')
        self.assertEqual(pos['format'], 'json')


class TestCDCManager(unittest.TestCase):
    
    def setUp(self):
        self.manager = CDCManager()
    
    def test_emit_event(self):
        """Test emitting events."""
        seq = self.manager.emit_event(
            operation=OperationType.INSERT,
            table="users",
            key="user_001",
            after={'name': 'John'}
        )
        
        self.assertEqual(seq, 1)
        
        events = self.manager.cdc_log.get_events(1)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].after['name'], 'John')
    
    def test_create_consumer(self):
        """Test creating consumers."""
        received = []
        
        def callback(data):
            received.append(data)
        
        consumer = self.manager.create_consumer(
            consumer_id="test_consumer",
            tables={"users"},
            format=OutputFormat.JSON,
            callback=callback
        )
        
        self.assertIn("test_consumer", self.manager.consumers)
        
        self.manager.emit_event(
            operation=OperationType.INSERT,
            table="users",
            key="user_001",
            after={'name': 'John'}
        )
        
        time.sleep(0.2)
        self.assertGreater(len(received), 0)
        
        consumer.stop()
    
    def test_get_stats(self):
        """Test statistics."""
        for i in range(5):
            self.manager.emit_event(
                operation=OperationType.INSERT,
                table="users",
                key=f"user_{i}"
            )
        
        stats = self.manager.get_stats()
        
        self.assertEqual(stats['total_events'], 5)
        self.assertEqual(stats['active_consumers'], 0)


class TestGlobalCDCManager(unittest.TestCase):
    
    def test_singleton(self):
        """Test global manager is singleton."""
        manager1 = get_cdc_manager()
        manager2 = get_cdc_manager()
        
        self.assertIs(manager1, manager2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
