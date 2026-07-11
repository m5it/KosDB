#!/usr/bin/env python3
"""Unit tests for the failover / Raft module."""

import unittest
from failover import RaftConsensus, LogEntry, NodeState, FailoverManager, FailoverCommands


class TestLogEntry(unittest.TestCase):
    def test_to_dict(self):
        entry = LogEntry(term=1, index=1, command={'type': 'INSERT'})
        d = entry.to_dict()
        self.assertEqual(d['term'], 1)
        self.assertEqual(d['index'], 1)
        self.assertEqual(d['command'], {'type': 'INSERT'})
        self.assertFalse(d['committed'])


class TestRaftConsensus(unittest.TestCase):
    def test_initial_state(self):
        raft = RaftConsensus('node1', '127.0.0.1', 9000, [])
        self.assertEqual(raft.state, NodeState.FOLLOWER)
        self.assertEqual(raft.current_term, 0)
        raft.stop()

    def test_last_log_term_empty(self):
        raft = RaftConsensus('node1', '127.0.0.1', 9000, [])
        self.assertEqual(raft._last_log_term(), 0)
        raft.stop()

    def test_handle_request_vote_rejects_lower_term(self):
        raft = RaftConsensus('node1', '127.0.0.1', 9000, [])
        raft.current_term = 5
        response = raft._handle_request_vote({
            'type': 'RequestVote',
            'term': 3,
            'candidate_id': 'node2',
            'last_log_index': 0,
            'last_log_term': 0
        })
        self.assertFalse(response['vote_granted'])
        self.assertEqual(response['term'], 5)
        raft.stop()

    def test_handle_request_vote_grants_vote(self):
        raft = RaftConsensus('node1', '127.0.0.1', 9000, [])
        response = raft._handle_request_vote({
            'type': 'RequestVote',
            'term': 1,
            'candidate_id': 'node2',
            'last_log_index': 0,
            'last_log_term': 0
        })
        self.assertTrue(response['vote_granted'])
        self.assertEqual(raft.voted_for, 'node2')
        raft.stop()

    def test_handle_append_entries_rejects_lower_term(self):
        raft = RaftConsensus('node1', '127.0.0.1', 9000, [])
        raft.current_term = 5
        response = raft._handle_append_entries({
            'type': 'AppendEntries',
            'term': 3,
            'leader_id': 'node2',
            'prev_log_index': 0,
            'prev_log_term': 0,
            'entries': [],
            'leader_commit': 0
        })
        self.assertFalse(response['success'])
        raft.stop()

    def test_handle_append_entries_appends(self):
        raft = RaftConsensus('node1', '127.0.0.1', 9000, [])
        response = raft._handle_append_entries({
            'type': 'AppendEntries',
            'term': 1,
            'leader_id': 'node2',
            'prev_log_index': 0,
            'prev_log_term': 0,
            'entries': [{'term': 1, 'index': 1, 'command': {'type': 'INSERT'}}],
            'leader_commit': 0
        })
        self.assertTrue(response['success'])
        self.assertEqual(len(raft.log), 1)
        self.assertEqual(raft.log[0].term, 1)
        raft.stop()

    def test_handle_heartbeat(self):
        raft = RaftConsensus('node1', '127.0.0.1', 9000, [])
        response = raft._handle_heartbeat({
            'type': 'Heartbeat',
            'term': 2,
            'leader_id': 'node2'
        })
        self.assertTrue(response['success'])
        self.assertEqual(raft.current_term, 2)
        self.assertEqual(raft.leader_id, 'node2')
        raft.stop()

    def test_propose_not_leader(self):
        raft = RaftConsensus('node1', '127.0.0.1', 9000, [])
        success, error = raft.propose({'type': 'INSERT'})
        self.assertFalse(success)
        self.assertIn('No leader', error)
        raft.stop()

    def test_get_status(self):
        raft = RaftConsensus('node1', '127.0.0.1', 9000, [])
        status = raft.get_status()
        self.assertEqual(status['node_id'], 'node1')
        self.assertEqual(status['state'], 'follower')
        self.assertIn('peers', status)
        raft.stop()


class TestFailoverManager(unittest.TestCase):
    def test_initial_status(self):
        fm = FailoverManager('node1', '127.0.0.1', 9000, [])
        status = fm.get_cluster_status()
        self.assertEqual(status['node_id'], 'node1')
        self.assertFalse(status['is_primary'])
        fm.stop()

    def test_execute_command_not_leader(self):
        fm = FailoverManager('node1', '127.0.0.1', 9000, [])
        success, msg = fm.execute_command({'type': 'INSERT', 'table': 'users', 'values': [1]})
        self.assertFalse(success)
        self.assertIn('No leader', msg)
        fm.stop()


class TestFailoverCommands(unittest.TestCase):
    def test_failover_status_no_manager(self):
        fc = FailoverCommands()
        result = fc.failover_status()
        self.assertIn('not available', result)

    def test_propose_command_no_manager(self):
        fc = FailoverCommands()
        result = fc.propose_command('{"type":"INSERT"}')
        self.assertIn('not available', result)
    def test_propose_command_invalid_json(self):
        fm = FailoverManager('node1', '127.0.0.1', 9000, [])
        fc = FailoverCommands(fm)
        result = fc.propose_command('not json')
        self.assertIn('Invalid JSON', result)
        fm.stop()
        result = fc.failover_status()
        self.assertIn('node1', result)
        fm.stop()


if __name__ == '__main__':
    unittest.main()
