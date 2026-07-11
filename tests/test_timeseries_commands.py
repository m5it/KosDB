#!/usr/bin/env python3
"""Unit tests for timeseries command handlers."""

import unittest
from unittest.mock import MagicMock, patch
from timeseries_commands import (
    CreateHypertableCommand,
    DropHypertableCommand,
    InsertTimeSeriesCommand,
    SelectTimeSeriesCommand,
    TimeBucketCommand,
    DownsampleCommand,
    RetentionPolicyCommand,
    HypertableStatsCommand,
    ListHypertablesCommand,
    FirstLastCommand,
)


class TestTimeseriesCommands(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.auth = MagicMock()

    @patch('timeseries_commands.get_timeseries_engine')
    def test_create_hypertable(self, mock_get):
        engine = MagicMock()
        engine.create_hypertable.return_value = MagicMock()
        mock_get.return_value = engine
        cmd = CreateHypertableCommand(self.db, self.auth)
        result = cmd.execute('metrics', chunk_interval='1h', retention='7d')
        self.assertEqual(result['status'], 'success')

    @patch('timeseries_commands.get_timeseries_engine')
    def test_create_hypertable_error(self, mock_get):
        engine = MagicMock()
        engine.create_hypertable.side_effect = Exception('fail')
        mock_get.return_value = engine
        cmd = CreateHypertableCommand(self.db, self.auth)
        result = cmd.execute('metrics')
        self.assertEqual(result['status'], 'error')

    @patch('timeseries_commands.get_timeseries_engine')
    def test_drop_hypertable(self, mock_get):
        engine = MagicMock()
        engine.drop_hypertable.return_value = True
        mock_get.return_value = engine
        cmd = DropHypertableCommand(self.db, self.auth)
        result = cmd.execute('metrics')
        self.assertEqual(result['status'], 'success')

    @patch('timeseries_commands.get_timeseries_engine')
    def test_insert(self, mock_get):
        table = MagicMock()
        table.insert.return_value = True
        engine = MagicMock()
        engine.get_hypertable.return_value = table
        mock_get.return_value = engine
        cmd = InsertTimeSeriesCommand(self.db, self.auth)
        result = cmd.execute('metrics', 1234567890.0, 42.0, {'host': 'a'})
        self.assertEqual(result['status'], 'success')

    @patch('timeseries_commands.get_timeseries_engine')
    def test_insert_no_table(self, mock_get):
        engine = MagicMock()
        engine.get_hypertable.return_value = None
        mock_get.return_value = engine
        cmd = InsertTimeSeriesCommand(self.db, self.auth)
        result = cmd.execute('metrics', 1234567890.0, 42.0)
        self.assertEqual(result['status'], 'error')

    @patch('timeseries_commands.get_timeseries_engine')
    def test_select(self, mock_get):
        table = MagicMock()
        table.query.return_value = []
        engine = MagicMock()
        engine.get_hypertable.return_value = table
        mock_get.return_value = engine
        cmd = SelectTimeSeriesCommand(self.db, self.auth)
        result = cmd.execute('metrics', start=0.0, end=1.0)
        self.assertEqual(result['status'], 'success')

    @patch('timeseries_commands.get_timeseries_engine')
    def test_time_bucket(self, mock_get):
        table = MagicMock()
        table.time_bucket.return_value = []
        engine = MagicMock()
        engine.get_hypertable.return_value = table
        mock_get.return_value = engine
        cmd = TimeBucketCommand(self.db, self.auth)
        result = cmd.execute('metrics', '1h')
        self.assertEqual(result['status'], 'success')

    @patch('timeseries_commands.get_timeseries_engine')
    def test_downsample(self, mock_get):
        table = MagicMock()
        table.downsample.return_value = []
        engine = MagicMock()
        engine.get_hypertable.return_value = table
        mock_get.return_value = engine
        cmd = DownsampleCommand(self.db, self.auth)
        result = cmd.execute('metrics', '1h', '1d')
        self.assertEqual(result['status'], 'success')

    @patch('timeseries_commands.get_timeseries_engine')
    def test_retention_apply(self, mock_get):
        table = MagicMock()
        table.apply_retention_policy.return_value = 5
        engine = MagicMock()
        engine.get_hypertable.return_value = table
        mock_get.return_value = engine
        cmd = RetentionPolicyCommand(self.db, self.auth)
        result = cmd.execute('apply', 'metrics')
        self.assertEqual(result['deleted_points'], 5)

    @patch('timeseries_commands.get_timeseries_engine')
    def test_retention_unknown_action(self, mock_get):
        table = MagicMock()
        engine = MagicMock()
        engine.get_hypertable.return_value = table
        mock_get.return_value = engine
        cmd = RetentionPolicyCommand(self.db, self.auth)
        result = cmd.execute('unknown', 'metrics')
        self.assertEqual(result['status'], 'error')

    @patch('timeseries_commands.get_timeseries_engine')
    def test_hypertable_stats(self, mock_get):
        table = MagicMock()
        table.get_stats.return_value = {}
        engine = MagicMock()
        engine.get_hypertable.return_value = table
        mock_get.return_value = engine
        cmd = HypertableStatsCommand(self.db, self.auth)
        result = cmd.execute('metrics')
        self.assertEqual(result['status'], 'success')

    @patch('timeseries_commands.get_timeseries_engine')
    def test_list_hypertables(self, mock_get):
        engine = MagicMock()
        engine.list_hypertables.return_value = ['metrics']
        mock_get.return_value = engine
        cmd = ListHypertablesCommand(self.db, self.auth)
        result = cmd.execute()
        self.assertEqual(result['count'], 1)

    @patch('timeseries_commands.get_timeseries_engine')
    def test_first(self, mock_get):
        point = MagicMock()
        point.timestamp = 1.0
        point.value = 42.0
        table = MagicMock()
        table.query.return_value = [point]
        engine = MagicMock()
        engine.get_hypertable.return_value = table
        mock_get.return_value = engine
        cmd = FirstLastCommand(self.db, self.auth)
        result = cmd.execute('metrics', 'first')
        self.assertEqual(result['value'], 42.0)


if __name__ == '__main__':
    unittest.main()
