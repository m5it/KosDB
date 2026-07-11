#!/usr/bin/env python3
"""Unit tests for materialized view command handlers."""

import unittest
from unittest.mock import MagicMock, patch
from mv_commands import (
    CreateMaterializedViewCommand,
    DropMaterializedViewCommand,
    RefreshMaterializedViewCommand,
    RefreshAllCommand,
    ListMaterializedViewsCommand,
    QueryMaterializedViewCommand,
    SetRefreshScheduleCommand,
    MVStatsCommand,
)


class TestMVCommands(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.auth = MagicMock()

    @patch('mv_commands.get_materialized_view_manager')
    def test_create_view(self, mock_mgr):
        mock_mgr.return_value.create_view.return_value = MagicMock()
        cmd = CreateMaterializedViewCommand(self.db, self.auth)
        result = cmd.execute('mv1', 'SELECT * FROM users')
        self.assertEqual(result['status'], 'success')

    @patch('mv_commands.get_materialized_view_manager')
    def test_create_view_error(self, mock_mgr):
        mock_mgr.return_value.create_view.side_effect = ValueError('bad query')
        cmd = CreateMaterializedViewCommand(self.db, self.auth)
        result = cmd.execute('mv1', 'bad')
        self.assertEqual(result['status'], 'error')

    @patch('mv_commands.get_materialized_view_manager')
    def test_drop_view(self, mock_mgr):
        mock_mgr.return_value.drop_view.return_value = True
        cmd = DropMaterializedViewCommand(self.db, self.auth)
        result = cmd.execute('mv1')
        self.assertEqual(result['status'], 'success')

    @patch('mv_commands.get_materialized_view_manager')
    def test_drop_view_missing(self, mock_mgr):
        mock_mgr.return_value.drop_view.return_value = False
        cmd = DropMaterializedViewCommand(self.db, self.auth)
        result = cmd.execute('mv1')
        self.assertEqual(result['status'], 'error')

    @patch('mv_commands.get_materialized_view_manager')
    def test_refresh_view(self, mock_mgr):
        mock_mgr.return_value.refresh_view.return_value = {'rows': 1}
        cmd = RefreshMaterializedViewCommand(self.db, self.auth)
        result = cmd.execute('mv1')
        self.assertEqual(result['status'], 'success')

    @patch('mv_commands.get_materialized_view_manager')
    def test_refresh_all(self, mock_mgr):
        mock_mgr.return_value.list_views.return_value = ['mv1']
        mock_mgr.return_value.refresh_view.return_value = {}
        cmd = RefreshAllCommand(self.db, self.auth)
        result = cmd.execute()
        self.assertEqual(result['status'], 'success')

    @patch('mv_commands.get_materialized_view_manager')
    def test_list_views(self, mock_mgr):
        view = MagicMock()
        view.get_stats.return_value = {'name': 'mv1'}
        mock_mgr.return_value.list_views.return_value = ['mv1']
        mock_mgr.return_value.get_view.return_value = view
        cmd = ListMaterializedViewsCommand(self.db, self.auth)
        result = cmd.execute()
        self.assertEqual(result['count'], 1)

    @patch('mv_commands.get_materialized_view_manager')
    def test_query_view(self, mock_mgr):
        mock_mgr.return_value.query_view.return_value = ([], None)
        cmd = QueryMaterializedViewCommand(self.db, self.auth)
        result = cmd.execute('mv1')
        self.assertEqual(result['status'], 'success')

    @patch('mv_commands.get_materialized_view_manager')
    def test_set_schedule(self, mock_mgr):
        view = MagicMock()
        mock_mgr.return_value.get_view.return_value = view
        cmd = SetRefreshScheduleCommand(self.db, self.auth)
        result = cmd.execute('mv1', 'every_n_minutes', 5)
        self.assertEqual(result['status'], 'success')

    @patch('mv_commands.get_materialized_view_manager')
    def test_stats(self, mock_mgr):
        mock_mgr.return_value.get_stats.return_value = {'views': 1}
        cmd = MVStatsCommand(self.db, self.auth)
        result = cmd.execute()
        self.assertEqual(result['status'], 'success')


if __name__ == '__main__':
    unittest.main()
