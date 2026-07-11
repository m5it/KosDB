#!/usr/bin/env python3
"""Unit tests for compression command handlers."""

import unittest
from unittest.mock import MagicMock, patch
from compression_commands import (
    CompressionEnableCommand,
    CompressionDisableCommand,
    CompressionStatsCommand,
    CompressionAlgorithmsCommand,
    CompressionBenchmarkCommand,
    CompressionTestCommand,
    CompressionCacheStatsCommand,
)


class TestCompressionCommands(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.auth = MagicMock()

    def test_enable_success(self):
        cmd = CompressionEnableCommand(self.db, self.auth)
        result = cmd.execute('users', algorithm='zlib', level=6, min_size=100)
        self.assertEqual(result['status'], 'success')

    def test_enable_invalid_algorithm(self):
        cmd = CompressionEnableCommand(self.db, self.auth)
        result = cmd.execute('users', algorithm='invalid')
        self.assertEqual(result['status'], 'error')

    def test_disable(self):
        cmd = CompressionDisableCommand(self.db, self.auth)
        result = cmd.execute('users')
        self.assertEqual(result['status'], 'success')

    @patch('compression_commands.CompressionManager')
    def test_stats(self, mock_mgr):
        mock_mgr.get_stats.return_value = {}
        cmd = CompressionStatsCommand(self.db, self.auth)
        result = cmd.execute('users')
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['table'], 'users')

    def test_algorithms(self):
        cmd = CompressionAlgorithmsCommand(self.db, self.auth)
        result = cmd.execute()
        self.assertEqual(result['status'], 'success')
        self.assertGreater(len(result['algorithms']), 0)

    def test_benchmark(self):
        cmd = CompressionBenchmarkCommand(self.db, self.auth)
        result = cmd.execute(data_size=1000)
        self.assertEqual(result['status'], 'success')

    def test_test_command(self):
        cmd = CompressionTestCommand(self.db, self.auth)
        result = cmd.execute('users', sample_size=50)
        self.assertEqual(result['status'], 'success')

    def test_cache_stats(self):
        cmd = CompressionCacheStatsCommand(self.db, self.auth)
        result = cmd.execute('users')
        self.assertEqual(result['status'], 'success')


if __name__ == '__main__':
    unittest.main()
