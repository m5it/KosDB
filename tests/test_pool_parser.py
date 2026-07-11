#!/usr/bin/env python3
"""Unit tests for pool parser."""

import unittest
from pool_parser import PoolCommandParser, get_pool_parser


class TestPoolParser(unittest.TestCase):
    def setUp(self):
        self.parser = PoolCommandParser()

    def test_create(self):
        result = self.parser.parse('POOL CREATE pool1 MIN 2 MAX 10 TIMEOUT 5.0 IDLE 60.0')
        self.assertEqual(result['type'], 'POOL_CREATE')
        self.assertEqual(result['min_connections'], 2)

    def test_status(self):
        result = self.parser.parse('POOL STATUS pool1')
        self.assertEqual(result['type'], 'POOL_STATUS')

    def test_list(self):
        result = self.parser.parse('POOL LIST')
        self.assertEqual(result['type'], 'POOL_LIST')

    def test_shutdown_nowait(self):
        result = self.parser.parse('POOL SHUTDOWN pool1 NOWAIT')
        self.assertFalse(result['wait'])

    def test_health(self):
        result = self.parser.parse('POOL HEALTH pool1')
        self.assertEqual(result['type'], 'POOL_HEALTH')

    def test_acquire(self):
        result = self.parser.parse('POOL ACQUIRE pool1 TIMEOUT 2.5')
        self.assertEqual(result['timeout'], 2.5)

    def test_unrelated(self):
        self.assertIsNone(self.parser.parse('SELECT 1'))

    def test_singleton(self):
        self.assertIs(get_pool_parser(), get_pool_parser())


if __name__ == '__main__':
    unittest.main()
