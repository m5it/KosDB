"""
Tests for write-ahead logging.
"""

import unittest
import tempfile
import shutil
import time
import threading
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from write_ahead_log import (
    LogRecordType, LogRecord, WriteAheadLog,
    WALRecovery, TransactionManager,
    create_wal, recover_database
)


class TestLogRecord(unittest.TestCase):
    def test_record_creation(self):
        record = LogRecord(
            lsn=1,
            txn_id=100,
            record_type=LogRecordType.INSERT,
            table='users',
            key=1,
            new_data={'name': 'Alice'}
        )
        
        self.assertEqual(record.lsn, 1)
        self.assertEqual(record.txn_id, 100)
        self.assertEqual(record.record_type, LogRecordType.INSERT)
    
    def test_checksum(self):
        record = LogRecord(
            lsn=1,
            txn_id=100,
            record_type=LogRecordType.INSERT,
            table='users',
            key=1,
            new_data={'name': 'Alice'}
        )
        
        checksum = record.compute_checksum()
        record.checksum = checksum
        
        self.assertTrue(record.verify())
    
    def test_serialization(self):
        record = LogRecord(
            lsn=42,
            txn_id=100,
            record_type=LogRecordType.UPDATE,
            table='users',
            key=1,
            old_data={'name': 'Alice'},
            new_data={'name': 'Bob'}
        )
        
        # Serialize and deserialize
        data = record.to_bytes()
        restored = LogRecord.from_bytes(data)
        
        self.assertEqual(restored.lsn, record.lsn)
        self.assertEqual(restored.txn_id, record.txn_id)
        self.assertEqual(restored.record_type, record.record_type)
        self.assertEqual(restored.table, record.table)
        self.assertEqual(restored.key, record.key)
        self.assertEqual(restored.old_data, record.old_data)
        self.assertEqual(restored.new_data, record.new_data)


class TestWriteAheadLog(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.wal = WriteAheadLog(self.temp_dir, max_log_size=1024 * 1024)
    
    def tearDown(self):
        self.wal.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_begin_transaction(self):
        txn_id = self.wal.begin_transaction()
        self.assertGreater(txn_id, 0)
        
        # Verify record written
        records = list(self.wal.read_log())
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].record_type, LogRecordType.BEGIN)
        self.assertEqual(records[0].txn_id, txn_id)
    
    def test_log_operations(self):
        txn_id = self.wal.begin_transaction()
        
        self.wal.log_insert(txn_id, 'users', 1, {'name': 'Alice'})
        self.wal.log_update(txn_id, 'users', 1, {'name': 'Alice'}, {'name': 'Bob'})
        self.wal.log_delete(txn_id, 'users', 1, {'name': 'Bob'})
        
        self.wal.commit_transaction(txn_id)
        
        records = list(self.wal.read_log())
        self.assertEqual(len(records), 5)  # BEGIN, INSERT, UPDATE, DELETE, COMMIT
        
        types = [r.record_type for r in records]
        self.assertEqual(types[0], LogRecordType.BEGIN)
        self.assertEqual(types[1], LogRecordType.INSERT)
        self.assertEqual(types[2], LogRecordType.UPDATE)
        self.assertEqual(types[3], LogRecordType.DELETE)
        self.assertEqual(types[4], LogRecordType.COMMIT)
    
    def test_abort_transaction(self):
        txn_id = self.wal.begin_transaction()
        self.wal.log_insert(txn_id, 'users', 1, {'name': 'Alice'})
        self.wal.abort_transaction(txn_id)
        
        records = list(self.wal.read_log())
        self.assertEqual(records[-1].record_type, LogRecordType.ABORT)
    
    def test_read_from_lsn(self):
        # Create several transactions
        for i in range(5):
            txn_id = self.wal.begin_transaction()
            self.wal.log_insert(txn_id, 'users', i, {'name': f'user_{i}'})
            self.wal.commit_transaction(txn_id)
        
        # Read from LSN 3
        records = list(self.wal.read_log(start_lsn=3))
        lsns = [r.lsn for r in records]
        self.assertTrue(all(l >= 3 for l in lsns))
    
    def test_checkpoint(self):
        txn1 = self.wal.begin_transaction()
        txn2 = self.wal.begin_transaction()
        
        self.wal.log_checkpoint([txn1, txn2])
        
        records = list(self.wal.read_log())
        checkpoint = [r for r in records if r.record_type == LogRecordType.CHECKPOINT]
        self.assertEqual(len(checkpoint), 1)
        self.assertEqual(checkpoint[0].new_data['active_transactions'], [txn1, txn2])
    
    def test_log_rotation(self):
        # Create WAL with small max size
        small_wal = WriteAheadLog(self.temp_dir, max_log_size=500)
        
        # Write enough to trigger rotation
        for i in range(20):
            txn_id = small_wal.begin_transaction()
            small_wal.log_insert(txn_id, 'users', i, {'data': 'x' * 100})
            small_wal.commit_transaction(txn_id)
        
        small_wal.close()
        
        # Should have multiple log files
        log_files = list(Path(self.temp_dir).glob('wal-*.log'))
        self.assertGreater(len(log_files), 1)
    
    def test_durability(self):
        txn_id = self.wal.begin_transaction()
        self.wal.log_insert(txn_id, 'users', 1, {'name': 'Alice'})
        self.wal.commit_transaction(txn_id)
        self.wal.flush()
        
        # Reopen WAL
        self.wal.close()
        new_wal = WriteAheadLog(self.temp_dir)
        
        records = list(new_wal.read_log())
        self.assertEqual(len(records), 3)  # BEGIN, INSERT, COMMIT
        
        new_wal.close()


class TestWALRecovery(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.wal = WriteAheadLog(self.temp_dir)
        self.db = {'users': {}}  # Mock database
        
        self.redo_ops = []
        self.undo_ops = []
    
    def tearDown(self):
        self.wal.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def redo_callback(self, record):
        self.redo_ops.append(record)
    
    def undo_callback(self, record):
        self.undo_ops.append(record)
    
    def test_analyze(self):
        # Create committed and uncommitted transactions
        txn1 = self.wal.begin_transaction()
        self.wal.log_insert(txn1, 'users', 1, {'name': 'Alice'})
        self.wal.commit_transaction(txn1)
        
        txn2 = self.wal.begin_transaction()
        self.wal.log_insert(txn2, 'users', 2, {'name': 'Bob'})
        # Not committed - will be active
        
        recovery = WALRecovery(self.wal, self.db)
        active = recovery.analyze()
        
        self.assertEqual(len(active), 1)
        self.assertIn(txn2, active)
        self.assertNotIn(txn1, active)
    
    def test_recovery(self):
        # Create scenario: one committed, one aborted, one active
        txn1 = self.wal.begin_transaction()
        self.wal.log_insert(txn1, 'users', 1, {'name': 'Alice'})
        self.wal.commit_transaction(txn1)
        
        txn2 = self.wal.begin_transaction()
        self.wal.log_insert(txn2, 'users', 2, {'name': 'Bob'})
        self.wal.abort_transaction(txn2)
        
        txn3 = self.wal.begin_transaction()
        self.wal.log_insert(txn3, 'users', 3, {'name': 'Charlie'})
        # Not committed
        
        recovery = WALRecovery(self.wal, self.db)
        recovery.recover(self.redo_callback, self.undo_callback)
        
        # Should redo txn1 (committed)
        self.assertEqual(len(self.redo_ops), 1)
        self.assertEqual(self.redo_ops[0].txn_id, txn1)
        
        # Should undo txn3 (active)
        self.assertEqual(len(self.undo_ops), 1)
        self.assertEqual(self.undo_ops[0].txn_id, txn3)


class TestTransactionManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.wal = WriteAheadLog(self.temp_dir)
        self.db = {}
        self.tm = TransactionManager(self.wal, self.db)
    
    def tearDown(self):
        self.wal.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_transaction_lifecycle(self):
        txn_id = self.tm.begin()
        self.tm.insert(txn_id, 'users', 1, {'name': 'Alice'})
        self.tm.commit(txn_id)
        
        records = list(self.wal.read_log())
        types = [r.record_type for r in records]
        self.assertEqual(types, [LogRecordType.BEGIN, LogRecordType.INSERT, LogRecordType.COMMIT])
    
    def test_abort(self):
        txn_id = self.tm.begin()
        self.tm.insert(txn_id, 'users', 1, {'name': 'Alice'})
        self.tm.abort(txn_id)
        
        records = list(self.wal.read_log())
        self.assertEqual(records[-1].record_type, LogRecordType.ABORT)
    
    def test_checkpoint(self):
        txn1 = self.tm.begin()
        txn2 = self.tm.begin()
        
        self.tm.checkpoint()
        
        records = list(self.wal.read_log())
        checkpoint = [r for r in records if r.record_type == LogRecordType.CHECKPOINT]
        self.assertEqual(len(checkpoint), 1)


class TestIntegration(unittest.TestCase):
    def test_full_recovery_scenario(self):
        """Test complete crash recovery scenario."""
        temp_dir = tempfile.mkdtemp()
        
        try:
            # Phase 1: Create WAL and perform operations
            wal = WriteAheadLog(temp_dir)
            
            # Transaction 1: Complete
            txn1 = wal.begin_transaction()
            wal.log_insert(txn1, 'accounts', 1, {'balance': 100})
            wal.commit_transaction(txn1)
            
            # Transaction 2: In progress (simulates crash)
            txn2 = wal.begin_transaction()
            wal.log_insert(txn2, 'accounts', 2, {'balance': 200})
            # Crash here - no commit
            
            wal.close()
            
            # Phase 2: Recovery
            new_wal = WriteAheadLog(temp_dir)
            db = {'accounts': {}}
            
            redo_ops = []
            undo_ops = []
            
            def redo_fn(record):
                if record.record_type == LogRecordType.INSERT:
                    db['accounts'][record.key] = record.new_data
                    redo_ops.append(record)
            
            def undo_fn(record):
                if record.record_type == LogRecordType.INSERT:
                    db['accounts'].pop(record.key, None)
                    undo_ops.append(record)
            
            recover_database(new_wal, db, redo_fn, undo_fn)
            
            # Verify recovery
            self.assertEqual(len(db['accounts']), 1)  # Only txn1 committed
            self.assertIn(1, db['accounts'])
            self.assertNotIn(2, db['accounts'])
            
            new_wal.close()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
