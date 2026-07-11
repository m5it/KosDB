#!/usr/bin/env python3
"""Unit tests for prepared statement command handlers."""

import unittest
from unittest.mock import MagicMock, patch
from prepared_statement_commands import (
    PrepareCommand,
    ExecuteCommand,
    DeallocateCommand,
    DeallocateAllCommand,
    ListPreparedCommand,
    CacheStatsCommand,
    CacheInvalidateCommand,
)


class TestPreparedStatementCommands(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.auth = MagicMock()

    @patch('prepared_statement_commands.get_session_manager')
    def test_prepare(self, mock_get):
        manager = MagicMock()
        stmt = MagicMock()
        stmt.parameter_names = ['id']
        stmt.parameter_positions = []
        manager.prepare.return_value = 'stmt-1'
        manager.get_statement.return_value = stmt
        mock_get.return_value = manager

        cmd = PrepareCommand(self.db, self.auth)
        result = cmd.execute('s1', 'SELECT * FROM users WHERE id = :id', 'session-1')
        self.assertEqual(result['status'], 'success')

    @patch('prepared_statement_commands.get_session_manager')
    @patch('prepared_statement_commands.get_query_plan_cache')
    def test_execute_found(self, mock_cache, mock_get):
        manager = MagicMock()
        stmt = MagicMock()
        stmt.statement_id = 'stmt-1'
        stmt.sql = 'SELECT * FROM users WHERE id = :id'
        manager.list_statements.return_value = [{'id': 'stmt-1', 'sql': stmt.sql}]
        manager.get_statement.return_value = stmt
        manager.execute.return_value = ('SELECT * FROM users WHERE id = 1', [])
        mock_get.return_value = manager
        cache = MagicMock()
        cache.get.return_value = None
        mock_cache.return_value = cache

        cmd = ExecuteCommand(self.db, self.auth)
        result = cmd.execute('s1', {'id': 1}, session_id='session-1')
        self.assertEqual(result['status'], 'success')

    @patch('prepared_statement_commands.get_session_manager')
    def test_execute_not_found(self, mock_get):
        manager = MagicMock()
        manager.list_statements.return_value = []
        mock_get.return_value = manager
        cmd = ExecuteCommand(self.db, self.auth)
        result = cmd.execute('missing', session_id='session-1')
        self.assertEqual(result['status'], 'error')

    @patch('prepared_statement_commands.get_session_manager')
    def test_deallocate(self, mock_get):
        manager = MagicMock()
        manager.list_statements.return_value = [{'id': 's1', 'sql': 'SELECT 1'}]
        manager.deallocate.return_value = True
        mock_get.return_value = manager
        cmd = DeallocateCommand(self.db, self.auth)
        result = cmd.execute('s1', 'session-1')
        self.assertEqual(result['status'], 'success')

    @patch('prepared_statement_commands.get_session_manager')
    def test_deallocate_all(self, mock_get):
        manager = MagicMock()
        manager.list_statements.return_value = [{'id': 's1'}]
        mock_get.return_value = manager
        cmd = DeallocateAllCommand(self.db, self.auth)
        result = cmd.execute('session-1')
        self.assertEqual(result['status'], 'success')

    @patch('prepared_statement_commands.get_session_manager')
    def test_list(self, mock_get):
        manager = MagicMock()
        manager.list_statements.return_value = []
        mock_get.return_value = manager
        cmd = ListPreparedCommand(self.db, self.auth)
        result = cmd.execute('session-1')
        self.assertEqual(result['status'], 'success')

    @patch('prepared_statement_commands.get_query_plan_cache')
    def test_cache_stats(self, mock_cache):
        mock_cache.return_value.get_stats.return_value = {}
        cmd = CacheStatsCommand(self.db, self.auth)
        result = cmd.execute()
        self.assertEqual(result['status'], 'success')

    @patch('prepared_statement_commands.get_query_plan_cache')
    def test_cache_invalidate_table(self, mock_cache):
        cmd = CacheInvalidateCommand(self.db, self.auth)
        result = cmd.execute('users')
        self.assertEqual(result['status'], 'success')

    @patch('prepared_statement_commands.get_query_plan_cache')
    def test_cache_invalidate_all(self, mock_cache):
        cmd = CacheInvalidateCommand(self.db, self.auth)
        result = cmd.execute()
        self.assertEqual(result['status'], 'success')


if __name__ == '__main__':
    unittest.main()
