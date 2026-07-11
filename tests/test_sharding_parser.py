#!/usr/bin/env python3
"""Unit tests for sharding parser."""

import unittest
from sharding_parser import ShardingParser, get_sharding_parser


class TestShardingParser(unittest.TestCase):
    def setUp(self):
        self.parser = ShardingParser()

    def test_create_shard(self):
        result = self.parser.parse('CREATE SHARD s1 REGION us HOST 127.0.0.1 PORT 8001 ROLE primary WEIGHT 2')
        self.assertEqual(result['type'], 'CREATE_SHARD')
        self.assertEqual(result['weight'], '2')

    def test_drop_shard(self):
        result = self.parser.parse('DROP SHARD s1')
        self.assertEqual(result['type'], 'DROP_SHARD')

    def test_show_shards(self):
        result = self.parser.parse('SHOW SHARDS')
        self.assertEqual(result['type'], 'SHOW_SHARDS')

    def test_rebalance(self):
        result = self.parser.parse('REBALANCE SHARDS')
        self.assertEqual(result['type'], 'REBALANCE_SHARDS')

    def test_add_replica(self):
        result = self.parser.parse('ADD READ REPLICA r1 FOR SHARD s1 REGION eu HOST 127.0.0.1 PORT 8002')
        self.assertEqual(result['type'], 'ADD_READ_REPLICA')

    def test_route_key(self):
        result = self.parser.parse('ROUTE KEY user-1 OPERATION write')
        self.assertEqual(result['operation'], 'write')

    def test_unrelated(self):
        self.assertIsNone(self.parser.parse('SELECT 1'))

    def test_singleton(self):
        self.assertIs(get_sharding_parser(), get_sharding_parser())


if __name__ == '__main__':
    unittest.main()
