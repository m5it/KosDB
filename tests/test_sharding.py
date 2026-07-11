#!/usr/bin/env python3
"""Unit tests for the sharding module."""

import unittest
from unittest.mock import MagicMock
from sharding import ShardingCoordinator, ShardingError


class TestShardingCoordinator(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.coordinator = ShardingCoordinator(self.db)

    def test_create_shard(self):
        self.coordinator.manager.create_shard = MagicMock(return_value="OK: shard1 created")
        result = self.coordinator.create_shard('shard1', 'us-east', '127.0.0.1', 8001)
        self.assertIn("OK", result)
        self.coordinator.manager.create_shard.assert_called_once()

    def test_drop_shard(self):
        self.coordinator.manager.drop_shard = MagicMock(return_value="OK: shard1 dropped")
        result = self.coordinator.drop_shard('shard1')
        self.assertIn("OK", result)
        self.coordinator.manager.drop_shard.assert_called_once_with('shard1')

    def test_list_shards(self):
        self.coordinator.manager.list_shards = MagicMock(return_value=[{'shard_id': 'shard1'}])
        result = self.coordinator.list_shards()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['shard_id'], 'shard1')

    def test_add_read_replica(self):
        self.coordinator.manager.add_read_replica = MagicMock(return_value="OK: replica added")
        result = self.coordinator.add_read_replica('shard1', 'rep1', 'us-west', '127.0.0.1', 8002)
        self.assertIn("OK", result)

    def test_rebalance(self):
        self.coordinator.manager.rebalance_shards = MagicMock(return_value="OK: rebalanced")
        result = self.coordinator.rebalance()
        self.assertIn("OK", result)

    def test_route_key(self):
        self.coordinator.router.route_key = MagicMock(return_value={'shard_id': 'shard1'})
        result = self.coordinator.route_key('user-1')
        self.assertEqual(result['shard_id'], 'shard1')

    def test_route_query(self):
        self.coordinator.router.route_query = MagicMock(return_value=[{'shard_id': 'shard1'}])
        result = self.coordinator.route_query('users', where={'id': 1})
        self.assertEqual(len(result), 1)

    def test_is_local_shard_true(self):
        self.coordinator.manager.get_shard = MagicMock(return_value=MagicMock(host='127.0.0.1', port=1))
        self.assertTrue(self.coordinator.is_local_shard('shard1'))

    def test_is_local_shard_false(self):
        self.coordinator.manager.get_shard = MagicMock(return_value=MagicMock(host='10.0.0.1', port=1))
        self.assertFalse(self.coordinator.is_local_shard('shard1'))

    def test_get_stats(self):
        self.coordinator.manager.get_stats = MagicMock(return_value={'shards': 1})
        self.coordinator.router.get_stats = MagicMock(return_value={'routes': 1})
        result = self.coordinator.get_stats()
        self.assertIn('manager', result)
        self.assertIn('router', result)


if __name__ == '__main__':
    unittest.main()
