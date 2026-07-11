#!/usr/bin/env python3
"""Unit tests for pool command handlers."""

import unittest
from unittest.mock import MagicMock, patch
from pool_commands import (
    PoolCreateCommand,
    PoolStatusCommand,
    PoolListCommand,
    PoolShutdownCommand,
    PoolAcquireCommand,
    PoolHealthCommand,
)


class TestPoolCommands(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.auth = MagicMock()

    @patch('pool_commands.create_pool')
    def test_create(self, mock_create):
        mock_create.return_value = MagicMock()
        cmd = PoolCreateCommand(self.db, self.auth)
        result = cmd.execute('pool1', min_connections=2, max_connections=5)
        self.assertEqual(result['status'], 'success')

    @patch('pool_commands.get_pool')
    @patch('pool_commands.get_all_stats')
    def test_status_all(self, mock_stats, mock_get):
        mock_stats.return_value = {'pool1': {}}
        cmd = PoolStatusCommand(self.db, self.auth)
        result = cmd.execute()
        self.assertEqual(result['status'], 'success')

    @patch('pool_commands.get_pool')
    def test_status_single(self, mock_get):
        mock_get.return_value = MagicMock()
        mock_get.return_value.get_stats.return_value = {}
        cmd = PoolStatusCommand(self.db, self.auth)
        result = cmd.execute('pool1')
        self.assertEqual(result['status'], 'success')

    @patch('pool_commands.list_pools')
    def test_list(self, mock_list):
        mock_list.return_value = ['pool1']
        cmd = PoolListCommand(self.db, self.auth)
        result = cmd.execute()
        self.assertEqual(result['count'], 1)

    @patch('pool_commands.list_pools')
    @patch('pool_commands.shutdown_pool')
    def test_shutdown(self, mock_shutdown, mock_list):
        mock_list.return_value = ['pool1']
        cmd = PoolShutdownCommand(self.db, self.auth)
        result = cmd.execute('pool1', wait=True)
        self.assertEqual(result['status'], 'success')

    @patch('pool_commands.list_pools')
    def test_shutdown_missing(self, mock_list):
        mock_list.return_value = []
        cmd = PoolShutdownCommand(self.db, self.auth)
        result = cmd.execute('pool1')
        self.assertEqual(result['status'], 'error')

    @patch('pool_commands.get_pool')
    def test_acquire(self, mock_get):
        pool = MagicMock()
        pool.get_connection.return_value = 'conn1'
        mock_get.return_value = pool
        cmd = PoolAcquireCommand(self.db, self.auth)
        result = cmd.execute('pool1')
        self.assertEqual(result['status'], 'success')

    @patch('pool_commands.get_pool')
    def test_acquire_missing(self, mock_get):
        mock_get.return_value = None
        cmd = PoolAcquireCommand(self.db, self.auth)
        result = cmd.execute('pool1')
        self.assertEqual(result['status'], 'error')

    @patch('pool_commands.list_pools')
    @patch('pool_commands.get_pool')
    def test_health(self, mock_get, mock_list):
        pool = MagicMock()
        pool.get_stats.return_value = {
            'active_connections': 1,
            'max_connections': 10,
            'total_borrowed': 100,
            'total_timeout': 1,
            'health_check_failures': 0
        }
        mock_get.return_value = pool
        mock_list.return_value = ['pool1']
        cmd = PoolHealthCommand(self.db, self.auth)
        result = cmd.execute('pool1')
        self.assertEqual(result['status'], 'healthy')


if __name__ == '__main__':
    unittest.main()
