#!/usr/bin/env python3
"""Unit tests for CDC command handlers."""

import unittest
from unittest.mock import MagicMock, patch
from cdc_commands import (
    CDCStartConsumerCommand,
    CDCStopConsumerCommand,
    CDCListConsumersCommand,
    CDCStatsCommand,
    CDCSetupKafkaCommand,
    CDCCreateSnapshotCommand,
)


class TestCDCStartConsumerCommand(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.auth = MagicMock()
        self.cmd = CDCStartConsumerCommand(self.db, self.auth)

    @patch('cdc_commands.get_cdc_manager')
    def test_execute_defaults(self, mock_get):
        manager = MagicMock()
        consumer = MagicMock()
        consumer.get_position.return_value = {'position': 0}
        manager.create_consumer.return_value = consumer
        mock_get.return_value = manager

        result = self.cmd.execute('c1')
        self.assertEqual(result['status'], 'success')
        self.assertIn('c1', result['message'])

    @patch('cdc_commands.get_cdc_manager')
    def test_execute_with_options(self, mock_get):
        manager = MagicMock()
        consumer = MagicMock()
        consumer.get_position.return_value = {'position': 5}
        manager.create_consumer.return_value = consumer
        mock_get.return_value = manager

        result = self.cmd.execute('c2', tables='t1,t2', operations='INSERT,UPDATE', format='protobuf', from_latest=True)
        self.assertEqual(result['status'], 'success')


class TestCDCStopConsumerCommand(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.auth = MagicMock()
        self.cmd = CDCStopConsumerCommand(self.db, self.auth)

    @patch('cdc_commands.get_cdc_manager')
    def test_stop_existing(self, mock_get):
        manager = MagicMock()
        manager.consumers = {'c1': MagicMock()}
        mock_get.return_value = manager

        result = self.cmd.execute('c1')
        self.assertEqual(result['status'], 'success')

    @patch('cdc_commands.get_cdc_manager')
    def test_stop_missing(self, mock_get):
        manager = MagicMock()
        manager.consumers = {}
        mock_get.return_value = manager

        result = self.cmd.execute('c1')
        self.assertEqual(result['status'], 'error')


class TestCDCListConsumersCommand(unittest.TestCase):
    @patch('cdc_commands.get_cdc_manager')
    def test_list(self, mock_get):
        manager = MagicMock()
        manager.consumers = {'c1': MagicMock()}
        mock_get.return_value = manager
        cmd = CDCListConsumersCommand(MagicMock(), MagicMock())
        result = cmd.execute()
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['count'], 1)


class TestCDCStatsCommand(unittest.TestCase):
    @patch('cdc_commands.get_cdc_manager')
    def test_stats(self, mock_get):
        manager = MagicMock()
        manager.get_stats.return_value = {'events': 1}
        mock_get.return_value = manager
        cmd = CDCStatsCommand(MagicMock(), MagicMock())
        result = cmd.execute()
        self.assertEqual(result['stats']['events'], 1)


class TestCDCSetupKafkaCommand(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.auth = MagicMock()
        self.cmd = CDCSetupKafkaCommand(self.db, self.auth)

    @patch('cdc_commands.get_cdc_manager')
    def test_setup_success(self, mock_get):
        manager = MagicMock()
        mock_get.return_value = manager
        result = self.cmd.execute('localhost:9092')
        self.assertEqual(result['status'], 'success')

    @patch('cdc_commands.get_cdc_manager')
    def test_setup_import_error(self, mock_get):
        manager = MagicMock()
        manager.setup_kafka.side_effect = ImportError('no kafka')
        mock_get.return_value = manager
        result = self.cmd.execute('localhost:9092')
        self.assertEqual(result['status'], 'error')


class TestCDCCreateSnapshotCommand(unittest.TestCase):
    @patch('cdc_commands.get_cdc_manager')
    def test_snapshot(self, mock_get):
        manager = MagicMock()
        event = MagicMock()
        event.to_dict.return_value = {'table': 't1'}
        manager.cdc_log.create_snapshot.return_value = [event]
        mock_get.return_value = manager
        cmd = CDCCreateSnapshotCommand(MagicMock(), MagicMock())
        result = cmd.execute('t1,t2')
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['snapshot_size'], 1)


if __name__ == '__main__':
    unittest.main()
