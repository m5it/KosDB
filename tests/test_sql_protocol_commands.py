#!/usr/bin/env python3
"""Unit tests for SQL protocol command handlers."""

import unittest
from unittest.mock import MagicMock
from sql_protocol_commands import (
    ShowProtocolStatusCommand,
    SetProtocolPortCommand,
    EnableProtocolCommand,
    DisableProtocolCommand,
)


class TestSQLProtocolCommands(unittest.TestCase):
    def _make_db(self):
        db = MagicMock()
        db._sql_protocol_status = {
            'postgres_enabled': False,
            'postgres_port': 5432,
            'mysql_enabled': False,
            'mysql_port': 3306,
            'tls_enabled': False,
        }
        return db

    def test_show_status(self):
        db = self._make_db()
        cmd = ShowProtocolStatusCommand(db)
        result = cmd.execute({}, {})
        self.assertIn('PostgreSQL', result)

    def test_set_port_postgres(self):
        db = self._make_db()
        cmd = SetProtocolPortCommand(db)
        result = cmd.execute({'protocol': 'postgres', 'port': '5433'}, {'is_admin': True})
        self.assertIn('OK', result)
        self.assertEqual(db._sql_protocol_status['postgres_port'], 5433)

    def test_set_port_not_admin(self):
        db = self._make_db()
        cmd = SetProtocolPortCommand(db)
        result = cmd.execute({'protocol': 'postgres', 'port': '5433'}, {'is_admin': False})
        self.assertIn('Admin only', result)

    def test_set_port_invalid_protocol(self):
        db = self._make_db()
        cmd = SetProtocolPortCommand(db)
        result = cmd.execute({'protocol': 'redis', 'port': '5433'}, {'is_admin': True})
        self.assertIn('ERROR', result)

    def test_set_port_invalid_port(self):
        db = self._make_db()
        cmd = SetProtocolPortCommand(db)
        result = cmd.execute({'protocol': 'postgres', 'port': 'abc'}, {'is_admin': True})
        self.assertIn('ERROR', result)

    def test_enable_protocol(self):
        db = self._make_db()
        cmd = EnableProtocolCommand(db)
        result = cmd.execute({'protocol': 'postgres'}, {'is_admin': True})
        self.assertIn('OK', result)
        self.assertTrue(db._sql_protocol_status['postgres_enabled'])

    def test_disable_protocol(self):
        db = self._make_db()
        cmd = DisableProtocolCommand(db)
        result = cmd.execute({'protocol': 'mysql'}, {'is_admin': True})
        self.assertIn('OK', result)
        self.assertFalse(db._sql_protocol_status['mysql_enabled'])


if __name__ == '__main__':
    unittest.main()
