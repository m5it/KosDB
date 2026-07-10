"""
Tests for concurrent index operations.
"""

import unittest
import time
import threading
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from concurrent_index import (
    IndexState, IndexType, ConcurrentIndex, IndexManager,
    OnlineIndexBuilder, IndexBuildProgress,
    create_index_manager, build_index_online
)


class MockTable:
    """Mock table for testing."""
    def __init__(self, data):
        self.data = data
        self._lock = threading.RLock()


class TestConcurrentIndex(unittest.TestCase):
    def setUp(self):
        self.table_data = [
            {'id': 1, 'name': 'Alice', 'age': 30},
            {'id': 2, 'name': 'Bob', 'age': 25},
            {'id': 3, 'name': 'Charlie', 'age': 35},
        ]
        self.table = MockTable(self.table_data)
    
    def test_index_creation(self):
        index = ConcurrentIndex("idx_name", "users", ["name"])
        self.assertEqual(index.name, "idx_name")
        self.assertEqual(index.columns, ["name"])
        self.assertEqual(index.state, IndexState.PENDING)
    
    def test_build_index(self):
        index = ConcurrentIndex("idx_name", "users", ["name"])
        index.start_build(self.table)
        
        ready = index.wait_for_ready(timeout=5.0)
        self.assertTrue(ready)
        self.assertEqual(index.state, IndexState.READY)
    
    def test_lookup(self):
        index = ConcurrentIndex("idx_name", "users", ["name"])
        index.start_build(self.table)
        index.wait_for_ready(timeout=5.0)
        index.activate()
        
        row_ids = index.lookup("Alice")
        self.assertEqual(row_ids, [0])
    
    def test_unique_constraint(self):
        index = ConcurrentIndex("idx_id", "users", ["id"], unique=True)
        index.start_build(self.table)
        index.wait_for_ready(timeout=5.0)
        index.activate()
        
        with self.assertRaises(ValueError):
            index.insert(1, 999)
    
    def test_range_scan(self):
        index = ConcurrentIndex("idx_age", "users", ["age"], IndexType.BTREE)
        index.start_build(self.table)
        index.wait_for_ready(timeout=5.0)
        index.activate()
        
        row_ids = index.range_scan(25, 30)
        self.assertIn(0, row_ids)
        self.assertIn(1, row_ids)
    
    def test_concurrent_writes_during_build(self):
        index = ConcurrentIndex("idx_name", "users", ["name"])
        index.start_build(self.table)
        
        time.sleep(0.01)
        index.insert("David", 3)
        
        index.wait_for_ready(timeout=5.0)
        index.activate()
        
        row_ids = index.lookup("David")
        self.assertEqual(row_ids, [3])
    
    def test_progress_tracking(self):
        index = ConcurrentIndex("idx_name", "users", ["name"])
        index.start_build(self.table)
        
        time.sleep(0.1)
        progress = index.get_progress()
        self.assertIsNotNone(progress)
        
        index.wait_for_ready(timeout=5.0)
        
        final_progress = index.get_progress()
        self.assertEqual(final_progress.processed_rows, 3)


class TestIndexManager(unittest.TestCase):
    def setUp(self):
        self.manager = IndexManager()
        self.manager.start()
        
        self.table_data = [
            {'id': 1, 'name': 'Alice'},
            {'id': 2, 'name': 'Bob'},
        ]
        self.table = MockTable(self.table_data)
    
    def tearDown(self):
        self.manager.stop()
    
    def test_create_index(self):
        index = self.manager.create_index(
            "idx_name", "users", ["name"],
            self.table, online=False
        )
        
        self.assertIsNotNone(index)
        self.assertEqual(index.state, IndexState.ACTIVE)
    
    def test_get_index(self):
        self.manager.create_index(
            "idx_id", "users", ["id"],
            self.table, online=False
        )
        
        retrieved = self.manager.get_index("idx_id")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "idx_id")
    
    def test_get_table_indexes(self):
        self.manager.create_index(
            "idx1", "users", ["id"], self.table, online=False
        )
        self.manager.create_index(
            "idx2", "users", ["name"], self.table, online=False
        )
        
        indexes = self.manager.get_table_indexes("users")
        self.assertEqual(len(indexes), 2)
    
    def test_drop_index(self):
        self.manager.create_index(
            "idx_temp", "users", ["id"], self.table, online=False
        )
        
        result = self.manager.drop_index("idx_temp")
        self.assertTrue(result)
        
        self.assertIsNone(self.manager.get_index("idx_temp"))
    
    def test_update_indexes_for_insert(self):
        self.manager.create_index(
            "idx_name", "users", ["name"], self.table, online=False
        )
        
        new_row = {'id': 3, 'name': 'Charlie'}
        self.manager.update_indexes_for_insert("users", new_row, 2)
        
        index = self.manager.get_index("idx_name")
        row_ids = index.lookup("Charlie")
        self.assertEqual(row_ids, [2])
    
    def test_update_indexes_for_delete(self):
        self.manager.create_index(
            "idx_name", "users", ["name"], self.table, online=False
        )
        
        old_row = {'id': 1, 'name': 'Alice'}
        self.manager.update_indexes_for_delete("users", old_row, 0)
        
        index = self.manager.get_index("idx_name")
        row_ids = index.lookup("Alice")
        self.assertEqual(row_ids, [])
    
    def test_update_indexes_for_update(self):
        self.manager.create_index(
            "idx_name", "users", ["name"], self.table, online=False
        )
        
        old_row = {'id': 1, 'name': 'Alice'}
        new_row = {'id': 1, 'name': 'Alicia'}
        self.manager.update_indexes_for_update("users", old_row, new_row, 0)
        
        index = self.manager.get_index("idx_name")
        self.assertEqual(index.lookup("Alice"), [])
        self.assertEqual(index.lookup("Alicia"), [0])
    
    def test_list_indexes(self):
        self.manager.create_index(
            "idx1", "users", ["id"], self.table, online=False
        )
        
        indexes = self.manager.list_indexes()
        self.assertEqual(len(indexes), 1)
        self.assertEqual(indexes[0]['name'], 'idx1')
    
    def test_get_stats(self):
        self.manager.create_index(
            "idx1", "users", ["id"], self.table, online=False
        )
        
        stats = self.manager.get_stats()
        self.assertEqual(stats['total_indexes'], 1)


class TestOnlineIndexBuilder(unittest.TestCase):
    def setUp(self):
        self.manager = IndexManager()
        self.manager.start()
        self.builder = OnlineIndexBuilder(self.manager)
        
        self.table_data = [
            {'id': i, 'name': f'User{i}'} 
            for i in range(100)
        ]
        self.table = MockTable(self.table_data)
    
    def tearDown(self):
        self.manager.stop()
    
    def test_create_index_online(self):
        op_id = self.builder.create_index_online(
            "idx_online", "users", ["name"],
            self.table
        )
        
        self.assertIsNotNone(op_id)
        self.assertEqual(len(op_id), 8)
    
    def test_get_operation_status(self):
        op_id = self.builder.create_index_online(
            "idx_status", "users", ["name"],
            self.table
        )
        
        status = self.builder.get_operation_status(op_id)
        self.assertIsNotNone(status)
        self.assertEqual(status['index_name'], 'idx_status')
    
    def test_wait_for_completion(self):
        op_id = self.builder.create_index_online(
            "idx_wait", "users", ["name"],
            self.table
        )
        
        completed = self.builder.wait_for_completion(op_id, timeout=10.0)
        self.assertTrue(completed)
        
        index = self.manager.get_index("idx_wait")
        self.assertEqual(index.state, IndexState.ACTIVE)


class TestIntegration(unittest.TestCase):
    def test_full_workflow(self):
        table_data = [
            {'id': i, 'email': f'user{i}@example.com'}
            for i in range(50)
        ]
        table = MockTable(table_data)
        
        manager = create_index_manager()
        
        try:
            # Create index online (auto-activates via callback)
            index = manager.create_index(
                "idx_email", "users", ["email"],
                table, unique=True, online=True
            )
            
            # Wait for ready (already ACTIVE via callback)
            ready = index.wait_for_ready(timeout=10.0)
            self.assertTrue(ready)
            self.assertEqual(index.state, IndexState.ACTIVE)
            
            # Verify lookups work
            row_ids = index.lookup("user10@example.com")
            self.assertEqual(row_ids, [10])
            
            # Test concurrent insert
            manager.update_indexes_for_insert(
                "users", 
                {'id': 999, 'email': 'new@example.com'},
                999
            )
            
            row_ids = index.lookup("new@example.com")
            self.assertEqual(row_ids, [999])
            
        finally:
            manager.stop()


if __name__ == '__main__':
    unittest.main(verbosity=2)
