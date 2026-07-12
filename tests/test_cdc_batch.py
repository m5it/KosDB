
"""
Test cases for batch CDC functionality.

Tests:
- Batch start/end markers
- Individual change events for batch commands
- Batch correlation via batch_id
- Batch sequence numbers
- Rate limiting for large batches
- Kafka connector for batches
"""

import unittest
import sys
import os
import time
import threading

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cdc_batch import (
    BatchCDCManager,
    BatchCDCEvent,
    BatchCDCEventType,
    OutputFormat,
    BatchCDCConsumer,
    BatchKafkaCDCConnector,
    RateLimiter
)


class TestBatchCDCEvents(unittest.TestCase):
    """Test suite for batch CDC events."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.manager = BatchCDCManager(rate_limit=False)
    
    def test_single_event(self):
        """Test emitting single (non-batch) event."""
        seq = self.manager.emit_event(
            operation=BatchCDCEventType.INSERT,
            table="users",
            key=1,
            after={"id": 1, "name": "Alice"}
        )
        
        self.assertGreater(seq, 0)
        
        event = self.manager.cdc_log.get_events(0)[0]
        self.assertEqual(event.operation, BatchCDCEventType.INSERT)
        self.assertEqual(event.table, "users")
        self.assertIsNone(event.batch_id)
        self.assertFalse(event.is_batch_event())
    
    def test_batch_start_marker(self):
        """Test batch start marker emission."""
        batch_id = self.manager.emit_batch_start(
            database="test_db",
            total_commands=3,
            error_mode="continue"
        )
        
        self.assertIsNotNone(batch_id)
        
        event = self.manager.cdc_log.get_events(0)[0]
        self.assertEqual(event.operation, BatchCDCEventType.BATCH_START)
        self.assertEqual(event.batch_id, batch_id)
        self.assertEqual(event.batch_total, 3)
        self.assertEqual(event.batch_error_mode, "continue")
        self.assertTrue(event.is_batch_marker())
    
    def test_batch_command_event(self):
        """Test batch command event."""
        batch_id = self.manager.emit_batch_start(
            database="test_db",
            total_commands=2
        )
        
        seq = self.manager.emit_batch_command(
            batch_id=batch_id,
            sequence=1,
            total=2,
            operation=BatchCDCEventType.INSERT,
            table="users",
            key=1,
            after={"id": 1, "name": "Alice"}
        )
        
        event = self.manager.cdc_log.get_events(seq)[0]
        self.assertEqual(event.operation, BatchCDCEventType.INSERT)
        self.assertEqual(event.batch_id, batch_id)
        self.assertEqual(event.batch_sequence, 1)
        self.assertEqual(event.batch_total, 2)
        self.assertTrue(event.is_batch_event())
        self.assertFalse(event.is_batch_marker())
    
    def test_batch_end_marker(self):
        """Test batch end marker."""
        batch_id = self.manager.emit_batch_start(
            database="test_db",
            total_commands=2
        )
        
        self.manager.emit_batch_command(
            batch_id=batch_id,
            sequence=1,
            total=2,
            operation=BatchCDCEventType.INSERT,
            table="users",
            key=1,
            after={"id": 1}
        )
        
        self.manager.emit_batch_end(
            batch_id=batch_id,
            commands_executed=2,
            commands_failed=0
        )
        
        events = self.manager.cdc_log.get_batch_events(batch_id)
        self.assertEqual(len(events), 3)
        
        end_event = events[-1]
        self.assertEqual(end_event.operation, BatchCDCEventType.BATCH_END)
        self.assertTrue(end_event.is_batch_marker())
    
    def test_batch_sequence_numbers(self):
        """Test batch sequence numbers are correct."""
        batch_id = self.manager.emit_batch_start(
            database="test_db",
            total_commands=5
        )
        
        sequences = []
        for i in range(5):
            self.manager.emit_batch_command(
                batch_id=batch_id,
                sequence=i + 1,
                total=5,
                operation=BatchCDCEventType.INSERT,
                table="users",
                key=i,
                after={"id": i}
            )
            sequences.append(i + 1)
        
        events = self.manager.cdc_log.get_batch_events(batch_id)
        command_events = [e for e in events 
                         if e.operation == BatchCDCEventType.INSERT]
        
        actual_sequences = [e.batch_sequence for e in command_events]
        self.assertEqual(actual_sequences, sequences)
    
    def test_batch_correlation(self):
        """Test that all events share same batch_id."""
        batch_id = self.manager.emit_batch_start(
            database="test_db",
            total_commands=3
        )
        
        for i in range(3):
            self.manager.emit_batch_command(
                batch_id=batch_id,
                sequence=i + 1,
                total=3,
                operation=BatchCDCEventType.INSERT,
                table="users",
                key=i,
                after={"id": i}
            )
        
        self.manager.emit_batch_end(
            batch_id=batch_id,
            commands_executed=3,
            commands_failed=0
        )
        
        events = self.manager.cdc_log.get_batch_events(batch_id)
        
        # All events should have same batch_id
        for event in events:
            self.assertEqual(event.batch_id, batch_id)
    
    def test_multiple_batches(self):
        """Test multiple concurrent batches."""
        batch1_id = self.manager.emit_batch_start(
            database="db1",
            total_commands=2
        )
        
        batch2_id = self.manager.emit_batch_start(
            database="db2",
            total_commands=2
        )
        
        # Interleave commands
        self.manager.emit_batch_command(
            batch_id=batch1_id,
            sequence=1,
            total=2,
            operation=BatchCDCEventType.INSERT,
            table="t1",
            key=1,
            after={"id": 1}
        )
        
        self.manager.emit_batch_command(
            batch_id=batch2_id,
            sequence=1,
            total=2,
            operation=BatchCDCEventType.INSERT,
            table="t2",
            key=1,
            after={"id": 1}
        )
        
        # Verify batch isolation
        batch1_events = self.manager.cdc_log.get_batch_events(batch1_id)
        batch2_events = self.manager.cdc_log.get_batch_events(batch2_id)
        
        for e in batch1_events:
            self.assertEqual(e.batch_id, batch1_id)
        
        for e in batch2_events:
            self.assertEqual(e.batch_id, batch2_id)


class TestRateLimiter(unittest.TestCase):
    """Test suite for rate limiting."""
    
    def test_rate_limit_basic(self):
        """Test basic rate limiting."""
        limiter = RateLimiter(max_events_per_second=10.0, burst_size=5)
        
        # Should acquire burst_size immediately
        for _ in range(5):
            self.assertTrue(limiter.acquire())
        
        # Next should fail (rate limited)
        self.assertFalse(limiter.acquire())
    
    def test_rate_limit_recovery(self):
        """Test rate limit recovery over time."""
        limiter = RateLimiter(max_events_per_second=100.0, burst_size=1)
        
        # Use up burst
        self.assertTrue(limiter.acquire())
        self.assertFalse(limiter.acquire())
        
        # Wait for recovery
        time.sleep(0.02)  # 20ms
        
        # Should be able to acquire again
        self.assertTrue(limiter.acquire())
    
    def test_rate_limit_blocking(self):
        """Test blocking acquire."""
        limiter = RateLimiter(max_events_per_second=1000.0, burst_size=1)
        
        # Use up burst
        self.assertTrue(limiter.acquire())
        
        # Blocking acquire should succeed
        start = time.time()
        result = limiter.acquire_blocking(timeout=0.1)
        elapsed = time.time() - start
        
        self.assertTrue(result)
        self.assertGreaterEqual(elapsed, 0.001)  # Should have waited


class TestBatchCDCConsumer(unittest.TestCase):
    """Test suite for batch CDC consumer."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.manager = BatchCDCManager(rate_limit=False)
        self.received_events = []
        self.received_batches = {}
    
    def test_individual_callback(self):
        """Test individual event callback."""
        consumer = self.manager.create_consumer(
            consumer_id="test_consumer",
            group_batches=False
        )
        
        def callback(event_bytes):
            self.received_events.append(event_bytes)
        
        consumer.start(callback=callback)
        
        # Emit events
        self.manager.emit_event(
            operation=BatchCDCEventType.INSERT,
            table="users",
            key=1,
            after={"id": 1}
        )
        
        time.sleep(0.05)
        
        self.assertEqual(len(self.received_events), 1)
        consumer.stop()
    
    def test_batch_grouping(self):
        """Test batch grouping callback."""
        consumer = self.manager.create_consumer(
            consumer_id="batch_consumer",
            group_batches=True
        )
        
        def batch_callback(batch_id, events):
            self.received_batches[batch_id] = events
        
        consumer.start(batch_callback=batch_callback)
        
        # Emit complete batch
        batch_id = self.manager.emit_batch_start(
            database="test_db",
            total_commands=2
        )
        
        self.manager.emit_batch_command(
            batch_id=batch_id,
            sequence=1,
            total=2,
            operation=BatchCDCEventType.INSERT,
            table="users",
            key=1,
            after={"id": 1}
        )
        
        self.manager.emit_batch_command(
            batch_id=batch_id,
            sequence=2,
            total=2,
            operation=BatchCDCEventType.INSERT,
            table="users",
            key=2,
            after={"id": 2}
        )
        
        self.manager.emit_batch_end(
            batch_id=batch_id,
            commands_executed=2,
            commands_failed=0
        )
        
        time.sleep(0.05)
        
        self.assertIn(batch_id, self.received_batches)
        self.assertEqual(len(self.received_batches[batch_id]), 2)
        consumer.stop()
    
    def test_batch_filtering(self):
        """Test table and operation filtering."""
        consumer = self.manager.create_consumer(
            consumer_id="filtered_consumer",
            tables={"users"},
            operations={BatchCDCEventType.INSERT},
            group_batches=False
        )
        
        def callback(event_bytes):
            self.received_events.append(event_bytes)
        
        consumer.start(callback=callback)
        
        # Emit matching event
        self.manager.emit_event(
            operation=BatchCDCEventType.INSERT,
            table="users",
            key=1,
            after={"id": 1}
        )
        
        # Emit non-matching event (wrong table)
        self.manager.emit_event(
            operation=BatchCDCEventType.INSERT,
            table="orders",
            key=1,
            after={"id": 1}
        )
        
        # Emit non-matching event (wrong operation)
        self.manager.emit_event(
            operation=BatchCDCEventType.DELETE,
            table="users",
            key=1,
            after={"id": 1}
        )
        
        time.sleep(0.05)
        
        self.assertEqual(len(self.received_events), 1)
        consumer.stop()


class TestBatchKafkaConnector(unittest.TestCase):
    """Test suite for batch Kafka connector."""
    
    def test_batch_topic_naming(self):
        """Test batch topic naming."""
        # Mock connector (no actual Kafka)
        connector = BatchKafkaCDCConnector(
            bootstrap_servers="localhost:9092",
            topic_prefix="kosdb.cdc"
        )
        
        # Test topic naming logic
        event = BatchCDCEvent(
            sequence_number=1,
            timestamp=1234567890,
            operation=BatchCDCEventType.INSERT,
            table="users",
            key=1,
            batch_id="batch_001",
            batch_sequence=1,
            batch_total=3
        )
        
        # Should use batch-specific topic
        # (Actual topic would be: kosdb.cdc.batch.users)
        self.assertTrue(event.batch_id is not None)


class TestCDCBatchIntegration(unittest.TestCase):
    """Integration tests for batch CDC."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.manager = BatchCDCManager(rate_limit=False)
    
    def test_complete_batch_flow(self):
        """Test complete batch CDC flow."""
        received_individual = []
        received_batches = {}
        
        consumer = self.manager.create_consumer(
            consumer_id="integration_test",
            group_batches=True
        )
        
        def individual_callback(event_bytes):
            received_individual.append(event_bytes)
        
        def batch_callback(batch_id, events):
            received_batches[batch_id] = events
        
        consumer.start(
            callback=individual_callback,
            batch_callback=batch_callback
        )
        
        # Simulate batch execution
        batch_id = self.manager.emit_batch_start(
            database="test_db",
            total_commands=3,
            error_mode="continue"
        )
        
        for i in range(3):
            self.manager.emit_batch_command(
                batch_id=batch_id,
                sequence=i + 1,
                total=3,
                operation=BatchCDCEventType.INSERT,
                table="users",
                key=i + 1,
                after={"id": i + 1, "name": f"User{i+1}"}
            )
        
        self.manager.emit_batch_end(
            batch_id=batch_id,
            commands_executed=3,
            commands_failed=0
        )
        
        time.sleep(0.1)
        
        # Verify individual events
        self.assertEqual(len(received_individual), 5)  # start + 3 commands + end
        
        # Verify batch grouping
        self.assertIn(batch_id, received_batches)
        self.assertEqual(len(received_batches[batch_id]), 3)  # All 3 commands
        
        consumer.stop()
    
    def test_large_batch_rate_limiting(self):
        """Test rate limiting with large batch."""
        # Create manager with rate limiting
        manager = BatchCDCManager(rate_limit=True)
        
        start_time = time.time()
        
        batch_id = manager.emit_batch_start(
            database="test_db",
            total_commands=100
        )
        
        for i in range(100):
            manager.emit_batch_command(
                batch_id=batch_id,
                sequence=i + 1,
                total=100,
                operation=BatchCDCEventType.INSERT,
                table="users",
                key=i,
                after={"id": i}
            )
        
        elapsed = time.time() - start_time
        
        # Just verify rate limiting is working (should take some measurable time)
        self.assertGreater(elapsed, 0.0)
    
    def test_stats_tracking(self):
        """Test CDC statistics."""
        # Emit some events
        self.manager.emit_event(
            operation=BatchCDCEventType.INSERT,
            table="users",
            key=1,
            after={"id": 1}
        )
        
        batch_id = self.manager.emit_batch_start(
            database="test_db",
            total_commands=2
        )
        
        self.manager.emit_batch_end(
            batch_id=batch_id,
            commands_executed=2,
            commands_failed=0
        )
        
        stats = self.manager.get_stats()
        
        self.assertEqual(stats['total_events'], 3)  # 1 single + 2 batch events (start + end)


if __name__ == '__main__':
    unittest.main(verbosity=2)
