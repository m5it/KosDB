#!/usr/bin/env python3
"""Unit tests for sharding command handlers."""

import unittest
from unittest.mock import MagicMock
from sharding_commands import (
    CreateShardCommand,
    DropShardCommand,
    ShowShardsCommand,
    RebalanceShardsCommand,
    AddReadReplicaCommand,
    RouteKeyCommand,
)


class TestShardingCommands(unittest.TestCase):
    def _db_with_coordinator(self):
        db = MagicMock()
        coordinator = MagicMock()
        db._sharding_coordinator = coordinator
        return db, coordinator

    def test_create_shard(self):
        db, coord = self._db_with_coordinator()
        coord.create_shard.return_value = 'OK: created'
        cmd = CreateShardCommand(db)
        result = cmd.execute({'shard_id': 's1', 'region': 'us', 'host': '127.0.0.1', 'port': '8001'}, {'is_admin': True})
        self.assertIn('OK', result)

    def test_create_shard_not_admin(self):
        db, _ = self._db_with_coordinator()
        cmd = CreateShardCommand(db)
        result = cmd.execute({}, {'is_admin': False})
        self.assertIn('Admin only', result)
    def test_create_shard_no_coordinator(self):
        db = MagicMock()
        db._sharding_coordinator = None
        cmd = CreateShardCommand(db)
        result = cmd.execute({'shard_id': 's1', 'region': 'us', 'host': '127.0.0.1', 'port': '8001'}, {'is_admin': True})
        self.assertIn('not available', result)
        db, coord = self._db_with_coordinator()
        coord.drop_shard.return_value = 'OK: dropped'
        cmd = DropShardCommand(db)
        result = cmd.execute({'shard_id': 's1'}, {'is_admin': True})
        self.assertIn('OK', result)

    def test_show_shards(self):
        db, coord = self._db_with_coordinator()
        coord.list_shards.return_value = [{'shard_id': 's1', 'region': 'us', 'host': '127.0.0.1', 'port': 8001, 'role': 'primary', 'status': 'active'}]
        cmd = ShowShardsCommand(db)
        result = cmd.execute({}, {})
        self.assertIn('s1', result)

    def test_rebalance(self):
        db, coord = self._db_with_coordinator()
        coord.rebalance.return_value = 'OK: rebalanced'
        coord.manager.get_rebalance_plan.return_value = [{'shard_id': 's1', 'region': 'us', 'weight': 1, 'key_range_count': 2, 'estimated_load_pct': 50.0}]
        cmd = RebalanceShardsCommand(db)
        result = cmd.execute({}, {'is_admin': True})
        self.assertIn('OK', result)

    def test_add_read_replica(self):
        db, coord = self._db_with_coordinator()
        coord.add_read_replica.return_value = 'OK: replica added'
        cmd = AddReadReplicaCommand(db)
        result = cmd.execute({'shard_id': 's1', 'replica_id': 'r1', 'region': 'us', 'host': '127.0.0.1', 'port': '8002'}, {'is_admin': True})
        self.assertIn('OK', result)

    def test_route_key(self):
        db, coord = self._db_with_coordinator()
        coord.route_key.return_value = {'shard_id': 's1', 'region': 'us'}
        cmd = RouteKeyCommand(db)
        result = cmd.execute({'key': 'user-1'}, {})
        self.assertIn('s1', result)


if __name__ == '__main__':
    unittest.main()
