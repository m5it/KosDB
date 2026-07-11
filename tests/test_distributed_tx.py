"""
Tests for distributed transaction coordinator.
"""

import unittest
import time
import sys
import os
from typing import Dict, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from distributed_tx import (
    TransactionState, ParticipantState,
    Participant, DistributedTransaction,
    TwoPhaseCommitCoordinator, ShardParticipant,
    DistributedTransactionManager,
    create_coordinator, create_participant
)


class MockConnection:
    """Mock database connection."""
    def __init__(self, shard_id: str):
        self.shard_id = shard_id
        self.data: Dict[Any, Any] = {}


class TestParticipant(unittest.TestCase):
    def test_participant_creation(self):
        conn = MockConnection('shard1')
        p = Participant('p1', 'shard1', conn)
        
        self.assertEqual(p.participant_id, 'p1')
        self.assertEqual(p.shard_id, 'shard1')
        self.assertEqual(p.state, ParticipantState.ACTIVE)


class TestDistributedTransaction(unittest.TestCase):
    def test_transaction_creation(self):
        txn = DistributedTransaction('txn1', 'coord1')
        
        self.assertEqual(txn.txn_id, 'txn1')
        self.assertEqual(txn.coordinator_id, 'coord1')
        self.assertEqual(txn.state, TransactionState.ACTIVE)
    
    def test_add_participant(self):
        txn = DistributedTransaction('txn1', 'coord1')
        conn = MockConnection('shard1')
        p = Participant('p1', 'shard1', conn)
        
        txn.add_participant(p)
        self.assertEqual(len(txn.participants), 1)
    
    def test_all_prepared(self):
        txn = DistributedTransaction('txn1', 'coord1')
        
        for i in range(3):
            conn = MockConnection(f'shard{i}')
            p = Participant(f'p{i}', f'shard{i}', conn)
            p.state = ParticipantState.PREPARED
            p.vote = True
            txn.add_participant(p)
        
        self.assertTrue(txn.all_prepared())
    
    def test_any_aborted(self):
        txn = DistributedTransaction('txn1', 'coord1')
        
        for i in range(3):
            conn = MockConnection(f'shard{i}')
            p = Participant(f'p{i}', f'shard{i}', conn)
            if i == 1:
                p.vote = False
            txn.add_participant(p)
        
        self.assertTrue(txn.any_aborted())


class TestTwoPhaseCommitCoordinator(unittest.TestCase):
    def setUp(self):
        self.coord = create_coordinator('coord1', timeout=2.0)
    
    def tearDown(self):
        self.coord.stop()
    
    def test_begin_transaction(self):
        shards = [
            ('shard1', MockConnection('shard1')),
            ('shard2', MockConnection('shard2')),
        ]
        
        txn_id = self.coord.begin_transaction(shards)
        self.assertIsNotNone(txn_id)
        
        txn = self.coord.get_transaction(txn_id)
        self.assertEqual(len(txn.participants), 2)
    
    def test_prepare_phase_success(self):
        shards = [
            ('shard1', MockConnection('shard1')),
            ('shard2', MockConnection('shard2')),
        ]
        
        txn_id = self.coord.begin_transaction(shards)
        success = self.coord.prepare_phase(txn_id)
        
        self.assertTrue(success)
        
        txn = self.coord.get_transaction(txn_id)
        self.assertEqual(txn.state, TransactionState.PREPARED)
    
    def test_full_commit(self):
        shards = [
            ('shard1', MockConnection('shard1')),
            ('shard2', MockConnection('shard2')),
        ]
        
        txn_id = self.coord.begin_transaction(shards)
        success = self.coord.execute_transaction(txn_id, [])
        
        self.assertTrue(success)
        
        txn = self.coord.get_transaction(txn_id)
        self.assertEqual(txn.state, TransactionState.COMMITTED)
    
    def test_abort_transaction(self):
        shards = [
            ('shard1', MockConnection('shard1')),
        ]
        
        txn_id = self.coord.begin_transaction(shards)
        success = self.coord.abort_transaction(txn_id)
        
        self.assertTrue(success)
        
        txn = self.coord.get_transaction(txn_id)
        self.assertEqual(txn.state, TransactionState.ABORTED)
    
    def test_get_active_transactions(self):
        shards = [
            ('shard1', MockConnection('shard1')),
        ]
        
        txn_id = self.coord.begin_transaction(shards)
        active = self.coord.get_active_transactions()
        
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]['txn_id'], txn_id)


class TestShardParticipant(unittest.TestCase):
    def setUp(self):
        self.db = MockConnection('shard1')
        self.participant = create_participant('shard1', self.db)
    
    def test_prepare(self):
        operations = [
            {'type': 'insert', 'table': 'users', 'key': 1, 'data': {'name': 'Alice'}}
        ]
        
        success = self.participant.prepare('txn1', operations)
        self.assertTrue(success)
    
    def test_commit(self):
        operations = [
            {'type': 'insert', 'table': 'users', 'key': 1, 'data': {'name': 'Alice'}}
        ]
        
        self.participant.prepare('txn1', operations)
        success = self.participant.commit('txn1')
        
        self.assertTrue(success)
    
    def test_abort(self):
        operations = [
            {'type': 'insert', 'table': 'users', 'key': 1, 'data': {'name': 'Alice'}}
        ]
        
        self.participant.prepare('txn1', operations)
        success = self.participant.abort('txn1')
        
        self.assertTrue(success)
    
    def test_commit_without_prepare(self):
        success = self.participant.commit('txn_unknown')
        self.assertTrue(success)


class TestDistributedTransactionManager(unittest.TestCase):
    def setUp(self):
        self.manager = DistributedTransactionManager('node1', is_coordinator=True)
        self.manager.coordinator = create_coordinator('node1', timeout=2.0)
    
    def tearDown(self):
        self.manager.coordinator.stop()
    
    def test_register_shard(self):
        conn = MockConnection('shard1')
        self.manager.register_shard('shard1', conn)
        
        self.assertIn('shard1', self.manager._shards)
    
    def test_execute_cross_shard(self):
        self.manager.register_shard('shard1', MockConnection('shard1'))
        self.manager.register_shard('shard2', MockConnection('shard2'))
        
        operations = {
            'shard1': [{'type': 'insert', 'table': 'users', 'key': 1, 'data': {}}],
            'shard2': [{'type': 'insert', 'table': 'orders', 'key': 1, 'data': {}}]
        }
        
        txn_id, success = self.manager.execute_cross_shard(operations)
        
        self.assertIsNotNone(txn_id)
        self.assertTrue(success)


class TestIntegration(unittest.TestCase):
    def test_cross_shard_transfer(self):
        coord = create_coordinator('bank-coord', timeout=2.0)
        
        shard_a = MockConnection('accounts-a')
        shard_b = MockConnection('accounts-b')
        
        txn_id = coord.begin_transaction([
            ('accounts-a', shard_a),
            ('accounts-b', shard_b)
        ])
        
        success = coord.prepare_phase(txn_id)
        self.assertTrue(success)
        
        success = coord.commit_phase(txn_id)
        self.assertTrue(success)
        
        txn = coord.get_transaction(txn_id)
        self.assertEqual(txn.state, TransactionState.COMMITTED)
        
        coord.stop()
    
    def test_failure_recovery(self):
        coord = create_coordinator('recovery-coord', timeout=2.0)
        
        shard = MockConnection('shard1')
        txn_id = coord.begin_transaction([('shard1', shard)])
        
        coord.prepare_phase(txn_id)
        
        success = coord.recover_transaction(txn_id)
        self.assertTrue(success)
        
        txn = coord.get_transaction(txn_id)
        self.assertEqual(txn.state, TransactionState.COMMITTED)
        
        coord.stop()


if __name__ == '__main__':
    unittest.main(verbosity=2)
