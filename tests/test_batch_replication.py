
"""
Test cases for batch replication functionality.

Tests:
- Batch commands written to binlog individually
- Batch markers for atomic groups
- Replication lag detection for batches
- Failover during batch execution
- Binlog parsing for batch commands
"""

import unittest
import sys
import os
import time
import tempfile
import threading

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from binlog_batch import BatchBinlog, BatchMarker, BatchReplicationLagDetector


class TestBatchBinlog(unittest.TestCase):
    """Test suite for batch binlog functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.binlog = BatchBinlog(self.temp_dir)
    
    def tearDown(self):
        """Clean up test fixtures."""
        self.binlog.close()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_single_entry(self):
        """Test writing single (non-batch) entry."""
        pos = self.binlog.write_entry(
            server_id=1,
            database="test_db",
            operation="INSERT",
            table="users",
            data={"row": {"id": 1, "name": "Alice"}}
        )
        
        self.assertGreater(pos, 0)
        
        entry = self.binlog.get_entry(pos)
        self.assertIsNotNone(entry)
        self.assertEqual(entry['operation'], "INSERT")
        self.assertEqual(entry['batch_marker'], BatchMarker.SINGLE.value)
        self.assertIsNone(entry['batch_id'])
    
    def test_batch_start_marker(self):
        """Test batch start marker."""
        batch_id = "batch_001"
        pos = self.binlog.write_batch_start(
            server_id=1,
            database="test_db",
            batch_id=batch_id,
            total_commands=3,
            error_mode="continue"
        )
        
        entry = self.binlog.get_entry(pos)
        self.assertEqual(entry['operation'], "BATCH_START")
        self.assertEqual(entry['batch_marker'], BatchMarker.BATCH_START.value)
        self.assertEqual(entry['batch_id'], batch_id)
        self.assertEqual(entry['batch_total_commands'], 3)
        self.assertEqual(entry['batch_error_mode'], "continue")
    
    def test_batch_command_entry(self):
        """Test individual batch command entry."""
        batch_id = "batch_001"
        
        # Write batch start
        self.binlog.write_batch_start(
            server_id=1,
            database="test_db",
            batch_id=batch_id,
            total_commands=2
        )
        
        # Write batch command
        pos = self.binlog.write_batch_command(
            server_id=1,
            database="test_db",
            batch_id=batch_id,
            operation="INSERT",
            table="users",
            data={"row": {"id": 1}},
            command_index=0,
            total_commands=2,
            error_mode="continue"
        )
        
        entry = self.binlog.get_entry(pos)
        self.assertEqual(entry['batch_marker'], BatchMarker.BATCH_COMMAND.value)
        self.assertEqual(entry['batch_id'], batch_id)
        self.assertEqual(entry['batch_command_index'], 0)
        self.assertEqual(entry['operation'], "INSERT")
    
    def test_batch_end_marker(self):
        """Test batch end marker."""
        batch_id = "batch_001"
        
        # Write complete batch
        self.binlog.write_batch_start(
            server_id=1,
            database="test_db",
            batch_id=batch_id,
            total_commands=2
        )
        
        self.binlog.write_batch_command(
            server_id=1, database="test_db", batch_id=batch_id,
            operation="INSERT", table="users",
            data={"row": {"id": 1}}, command_index=0,
            total_commands=2, error_mode="continue"
        )
        
        pos = self.binlog.write_batch_end(
            server_id=1,
            database="test_db",
            batch_id=batch_id,
            commands_executed=2,
            commands_failed=0
        )
        
        entry = self.binlog.get_entry(pos)
        self.assertEqual(entry['operation'], "BATCH_END")
        self.assertEqual(entry['batch_marker'], BatchMarker.BATCH_END.value)
        self.assertEqual(entry['data']['commands_executed'], 2)
    
    def test_get_batch_entries(self):
        """Test retrieving all entries for a batch."""
        batch_id = "batch_002"
        
        # Write complete batch
        self.binlog.write_batch_start(
            server_id=1, database="test_db",
            batch_id=batch_id, total_commands=3
        )
        
        for i in range(3):
            self.binlog.write_batch_command(
                server_id=1, database="test_db", batch_id=batch_id,
                operation="INSERT", table="users",
                data={"row": {"id": i}}, command_index=i,
                total_commands=3, error_mode="continue"
            )
        
        self.binlog.write_batch_end(
            server_id=1, database="test_db",
            batch_id=batch_id, commands_executed=3, commands_failed=0
        )
        
        entries = self.binlog.get_batch_entries(batch_id)
        self.assertEqual(len(entries), 5)  # start + 3 commands + end
        
        # Verify order
        markers = [e['batch_marker'] for e in entries]
        self.assertEqual(markers[0], BatchMarker.BATCH_START.value)
        self.assertEqual(markers[-1], BatchMarker.BATCH_END.value)
    
    def test_batch_status(self):
        """Test batch status retrieval."""
        batch_id = "batch_003"
        
        # Write incomplete batch (no end)
        self.binlog.write_batch_start(
            server_id=1, database="test_db",
            batch_id=batch_id, total_commands=2
        )
        
        status = self.binlog.get_batch_status(batch_id)
        
        self.assertIsNotNone(status)
        self.assertTrue(status['started'])
        self.assertFalse(status['completed'])
        self.assertEqual(status['commands_logged'], 0)
        self.assertIsNone(status['end_position'])
    
    def test_list_active_batches(self):
        """Test listing active (incomplete) batches."""
        # Create active batch
        self.binlog.write_batch_start(
            server_id=1, database="test_db",
            batch_id="active_batch", total_commands=5
        )
        
        # Create completed batch
        self.binlog.write_batch_start(
            server_id=1, database="test_db",
            batch_id="completed_batch", total_commands=1
        )
        self.binlog.write_batch_end(
            server_id=1, database="test_db",
            batch_id="completed_batch", commands_executed=1, commands_failed=0
        )
        
        active = self.binlog.list_active_batches()
        
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]['batch_id'], "active_batch")
    
    def test_batch_lag_calculation(self):
        """Test batch lag calculation."""
        batch_id = "batch_004"
        
        # Write batch
        start_pos = self.binlog.write_batch_start(
            server_id=1, database="test_db",
            batch_id=batch_id, total_commands=2
        )
        
        for i in range(2):
            self.binlog.write_batch_command(
                server_id=1, database="test_db", batch_id=batch_id,
                operation="INSERT", table="users",
                data={"row": {"id": i}}, command_index=i,
                total_commands=2, error_mode="continue"
            )
        
        end_pos = self.binlog.write_batch_end(
            server_id=1, database="test_db",
            batch_id=batch_id, commands_executed=2, commands_failed=0
        )
        
        # Calculate lag from start position
        lag = self.binlog.get_batch_lag(batch_id, start_pos)
        self.assertEqual(lag, end_pos - start_pos)
        
        # No lag when at end position
        lag = self.binlog.get_batch_lag(batch_id, end_pos)
        self.assertEqual(lag, 0)
    
    def test_entry_ordering(self):
        """Test that entries are written in order."""
        positions = []
        
        for i in range(10):
            pos = self.binlog.write_entry(
                server_id=1, database="test_db",
                operation="INSERT", table="users",
                data={"row": {"id": i}}
            )
            positions.append(pos)
        
        # Positions should be increasing
        for i in range(1, len(positions)):
            self.assertGreater(positions[i], positions[i-1])
    
    def test_mixed_batch_and_single(self):
        """Test mixing batch and single entries."""
        # Single entry
        self.binlog.write_entry(
            server_id=1, database="test_db",
            operation="INSERT", table="users",
            data={"row": {"id": 1}}
        )
        
        # Batch
        self.binlog.write_batch_start(
            server_id=1, database="test_db",
            batch_id="batch_005", total_commands=1
        )
        self.binlog.write_batch_command(
            server_id=1, database="test_db", batch_id="batch_005",
            operation="UPDATE", table="users",
            data={"set": {"name": "Bob"}}, command_index=0,
            total_commands=1, error_mode="continue"
        )
        self.binlog.write_batch_end(
            server_id=1, database="test_db",
            batch_id="batch_005", commands_executed=1, commands_failed=0
        )
        
        # Single entry
        self.binlog.write_entry(
            server_id=1, database="test_db",
            operation="DELETE", table="users",
            data={"where": {"id": 1}}
        )
        
        # Get entries
        entries = self.binlog.get_entries(0, limit=10)
        
        # Should have 5 entries: single, batch_start, batch_cmd, batch_end, single
        self.assertEqual(len(entries), 5)
        
        # Check markers
        markers = [e['batch_marker'] for e in entries]
        self.assertEqual(markers[0], BatchMarker.SINGLE.value)
        self.assertEqual(markers[1], BatchMarker.BATCH_START.value)
        self.assertEqual(markers[2], BatchMarker.BATCH_COMMAND.value)
        self.assertEqual(markers[3], BatchMarker.BATCH_END.value)
        self.assertEqual(markers[4], BatchMarker.SINGLE.value)


class TestBatchReplicationLagDetector(unittest.TestCase):
    """Test suite for batch replication lag detection."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.binlog = BatchBinlog(self.temp_dir)
        self.detector = BatchReplicationLagDetector(
            self.binlog,
            lag_threshold_ms=100,
            check_interval=1
        )
    
    def tearDown(self):
        """Clean up test fixtures."""
        self.detector.stop()
        self.binlog.close()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_lag_report_generation(self):
        """Test lag report generation."""
        batch_id = "lag_test_001"
        
        # Write batch
        start_pos = self.binlog.write_batch_start(
            server_id=1, database="test_db",
            batch_id=batch_id, total_commands=2
        )
        
        for i in range(2):
            self.binlog.write_batch_command(
                server_id=1, database="test_db", batch_id=batch_id,
                operation="INSERT", table="users",
                data={"row": {"id": i}}, command_index=i,
                total_commands=2, error_mode="continue"
            )
        
        end_pos = self.binlog.write_batch_end(
            server_id=1, database="test_db",
            batch_id=batch_id, commands_executed=2, commands_failed=0
        )
        
        # Generate lag report
        report = self.detector.get_batch_lag_report(batch_id, start_pos)

        # Generate lag report
        report = self.detector.get_batch_lag_report(batch_id, start_pos)
        
        self.assertEqual(report['batch_id'], batch_id)
        self.assertEqual(report['status'], 'current')  # 4 entries is not considered lagging
        self.assertEqual(report['lag_entries'], end_pos - start_pos)
        self.assertEqual(report['batch_end_position'], end_pos)
        self.assertEqual(report['slave_position'], start_pos)
    
    def test_unknown_batch_lag_report(self):
        """Test lag report for unknown batch."""
        report = self.detector.get_batch_lag_report("unknown_batch", 0)
        
        self.assertEqual(report['batch_id'], "unknown_batch")
        self.assertEqual(report['status'], 'unknown')
        self.assertIsNone(report['lag_entries'])


class TestReplicationOrder(unittest.TestCase):
    """Test suite for replication order guarantees."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.binlog = BatchBinlog(self.temp_dir)
    
    def tearDown(self):
        """Clean up test fixtures."""
        self.binlog.close()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_batch_command_order(self):
        """Test that batch commands are in correct order."""
        batch_id = "order_test"
        
        self.binlog.write_batch_start(
            server_id=1, database="test_db",
            batch_id=batch_id, total_commands=5
        )
        
        # Write commands in order
        for i in range(5):
            self.binlog.write_batch_command(
                server_id=1, database="test_db", batch_id=batch_id,
                operation="INSERT", table="users",
                data={"row": {"id": i}}, command_index=i,
                total_commands=5, error_mode="continue"
            )
        
        self.binlog.write_batch_end(
            server_id=1, database="test_db",
            batch_id=batch_id, commands_executed=5, commands_failed=0
        )
        
        # Retrieve and verify order
        entries = self.binlog.get_batch_entries(batch_id)
        command_entries = [e for e in entries 
                         if e['batch_marker'] == BatchMarker.BATCH_COMMAND.value]
        
        indices = [e['batch_command_index'] for e in command_entries]
        self.assertEqual(indices, [0, 1, 2, 3, 4])
    
    def test_multiple_batches_interleaved(self):
        """Test multiple batches with interleaved entries."""
        # Batch 1
        self.binlog.write_batch_start(
            server_id=1, database="test_db",
            batch_id="batch_1", total_commands=2
        )
        
        # Batch 2 (starts before batch 1 completes)
        self.binlog.write_batch_start(
            server_id=1, database="test_db",
            batch_id="batch_2", total_commands=1
        )
        
        # Batch 1 command
        self.binlog.write_batch_command(
            server_id=1, database="test_db", batch_id="batch_1",
            operation="INSERT", table="users",
            data={"row": {"id": 1}}, command_index=0,
            total_commands=2, error_mode="continue"
        )
        
        # Batch 2 command
        self.binlog.write_batch_command(
            server_id=1, database="test_db", batch_id="batch_2",
            operation="INSERT", table="users",
            data={"row": {"id": 2}}, command_index=0,
            total_commands=1, error_mode="continue"
        )
        
        # Complete both batches
        self.binlog.write_batch_end(
            server_id=1, database="test_db",
            batch_id="batch_2", commands_executed=1, commands_failed=0
        )
        
        self.binlog.write_batch_command(
            server_id=1, database="test_db", batch_id="batch_1",
            operation="INSERT", table="users",
            data={"row": {"id": 3}}, command_index=1,
            total_commands=2, error_mode="continue"
        )
        
        self.binlog.write_batch_end(
            server_id=1, database="test_db",
            batch_id="batch_1", commands_executed=2, commands_failed=0
        )
        
        # Verify each batch has correct entries
        batch1_entries = self.binlog.get_batch_entries("batch_1")
        batch2_entries = self.binlog.get_batch_entries("batch_2")
        
        self.assertEqual(len(batch1_entries), 4)  # start + 2 commands + end
        self.assertEqual(len(batch2_entries), 3)  # start + 1 command + end


class TestFailoverScenarios(unittest.TestCase):
    """Test suite for failover scenarios with batches."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.binlog = BatchBinlog(self.temp_dir)
    
    def tearDown(self):
        """Clean up test fixtures."""
        self.binlog.close()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_incomplete_batch_detection(self):
        """Test detection of incomplete batch during failover."""
        batch_id = "failover_test"
        
        # Start batch but don't complete
        self.binlog.write_batch_start(
            server_id=1, database="test_db",
            batch_id=batch_id, total_commands=5
        )
        
        # Write only 2 commands
        for i in range(2):
            self.binlog.write_batch_command(
                server_id=1, database="test_db", batch_id=batch_id,
                operation="INSERT", table="users",
                data={"row": {"id": i}}, command_index=i,
                total_commands=5, error_mode="continue"
            )
        
        # Check status - should be incomplete
        status = self.binlog.get_batch_status(batch_id)
        
        self.assertTrue(status['started'])
        self.assertFalse(status['completed'])
        self.assertEqual(status['commands_logged'], 2)
        self.assertEqual(status['total_commands'], 5)
    
    def test_slave_promotion_with_batch(self):
        """Test slave promotion with incomplete batch."""
        batch_id = "promotion_test"
        
        # Simulate batch in progress
        self.binlog.write_batch_start(
            server_id=1, database="test_db",
            batch_id=batch_id, total_commands=3
        )
        
        self.binlog.write_batch_command(
            server_id=1, database="test_db", batch_id=batch_id,
            operation="INSERT", table="users",
            data={"row": {"id": 1}}, command_index=0,
            total_commands=3, error_mode="continue"
        )
        
        # Get current position (simulating slave position)
        slave_pos = self.binlog.get_latest_position()
        
        # Complete batch
        self.binlog.write_batch_command(
            server_id=1, database="test_db", batch_id=batch_id,
            operation="INSERT", table="users",
            data={"row": {"id": 2}}, command_index=1,
            total_commands=3, error_mode="continue"
        )
        
        self.binlog.write_batch_end(
            server_id=1, database="test_db",
            batch_id=batch_id, commands_executed=2, commands_failed=0
        )
        
        # Slave should see batch as incomplete
        status = self.binlog.get_batch_status(batch_id)

        # At slave's position, batch should appear incomplete
        entries = self.binlog.get_entries(slave_pos, limit=10)
        batch_entries = [e for e in entries if e.get('batch_id') == batch_id]
        
        # Should only have start + first command at slave position
        self.assertEqual(len(batch_entries), 2)
