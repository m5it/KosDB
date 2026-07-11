#!/usr/bin/env python3
"""Unit tests for the command registry."""

import unittest
from unittest.mock import MagicMock
from commands import CommandRegistry, Command


class MockDB:
    def __init__(self):
        self._binlog = MagicMock()
        self._binlog.get_latest_position.return_value = 0
        self.server_id = 1


class TestCommandRegistry(unittest.TestCase):
    def setUp(self):
        self.db = MockDB()
        self.registry = CommandRegistry(self.db)
        self.client_state = {'current_db': 'testdb', 'is_admin': True}

    def test_create_table(self):
        self.db.create_table = MagicMock(return_value="Table created")
        result = self.registry.execute('CREATE', {'table': 'users', 'columns': ['id', 'name']}, self.client_state)
        self.assertIn("OK", result)

    def test_create_table_no_db(self):
        result = self.registry.execute('CREATE', {'table': 'users', 'columns': ['id', 'name']}, {})
        self.assertIn("No database selected", result)

    def test_drop_table(self):
        self.db.drop_table = MagicMock(return_value="Table dropped")
        result = self.registry.execute('DROP', {'table': 'users'}, self.client_state)
        self.assertIn("OK", result)

    def test_insert(self):
        self.db.insert = MagicMock(return_value="Inserted")
        result = self.registry.execute('INSERT', {'table': 'users', 'values': [1, 'Alice']}, self.client_state)
        self.assertIn("OK", result)

    def test_select(self):
        self.db.select = MagicMock(return_value="1 row(s) in set")
        result = self.registry.execute('SELECT', {'table': 'users', 'columns': ['*']}, self.client_state)
        self.assertIn("row(s) in set", result)

    def test_update(self):
        self.db.update = MagicMock(return_value="Updated 1 row(s)")
        result = self.registry.execute('UPDATE', {'table': 'users', 'set': {'name': 'Bob'}, 'where': {'id': 1}}, self.client_state)
        self.assertIn("OK", result)

    def test_delete(self):
        self.db.delete = MagicMock(return_value="Deleted 1 row(s)")
        result = self.registry.execute('DELETE', {'table': 'users', 'where': {'id': 1}}, self.client_state)
        self.assertIn("OK", result)

    def test_use_database(self):
        self.db.use_database = MagicMock(return_value="Switched")
        result = self.registry.execute('USE', {'database': 'testdb'}, {})
        self.assertIn("Switched", result)

    def test_create_database(self):
        self.db.create_database = MagicMock(return_value="Created")
        result = self.registry.execute('CREATE_DB', {'database': 'testdb'}, {})
        self.assertIn("OK", result)

    def test_drop_database(self):
        self.db.drop_database = MagicMock(return_value="Dropped")
        result = self.registry.execute('DROP_DB', {'database': 'testdb'}, self.client_state)
        self.assertIn("OK", result)

    def test_show_tables(self):
        self.db.list_tables = MagicMock(return_value=['users'])
        result = self.registry.execute('SHOW_TABLES', {}, self.client_state)
        self.assertIn("users", result)

    def test_show_databases(self):
        self.db.list_databases = MagicMock(return_value=['db1'])
        result = self.registry.execute('SHOW_DATABASES', {}, {})
        self.assertIn("db1", result)

    def test_show_users_admin(self):
        self.db.list_users = MagicMock(return_value=['alice'])
        result = self.registry.execute('SHOW_USERS', {}, self.client_state)
        self.assertIn("alice", result)

    def test_show_users_not_admin(self):
        result = self.registry.execute('SHOW_USERS', {}, {'current_db': 'testdb'})
        self.assertIn("Admin only", result)

    def test_begin_commit_rollback(self):
        self.db.begin_transaction = MagicMock(return_value="Transaction started")
        self.db.commit_transaction = MagicMock(return_value="Committed")
        self.db.rollback_transaction = MagicMock(return_value="Rolled back")
        self.assertIn("started", self.registry.execute('BEGIN', {}, self.client_state))
        self.assertIn("Committed", self.registry.execute('COMMIT', {}, {}))
        self.assertIn("Rolled back", self.registry.execute('ROLLBACK', {}, {}))

    def test_replication_commands(self):
        result = self.registry.execute('START_SLAVE', {}, self.client_state)
        self.assertIn("started", result)
        result = self.registry.execute('STOP_SLAVE', {}, self.client_state)
        self.assertIn("stopped", result)
        result = self.registry.execute('RESET_SLAVE', {}, self.client_state)
        self.assertIn("reset", result)

    def test_help(self):
        result = self.registry.execute('HELP', {}, {})
        self.assertIn("Available commands", result)

    def test_quit(self):
        result = self.registry.execute('QUIT', {}, {})
        self.assertEqual(result, "BYE")

    def test_unknown_command(self):
        result = self.registry.execute('FOOBAR', {}, {})
        self.assertIn("not implemented", result)

    def test_unknown_type(self):
        result = self.registry.execute('UNKNOWN', {}, {})
        self.assertIn("Unknown command", result)

    def test_missing_params(self):
        result = self.registry.execute('CREATE', {}, self.client_state)
        self.assertIn("ERROR", result)

    def test_command_validate_params(self):
        cmd = Command(self.db)
        self.assertTrue(cmd.validate_params({'a': 1}, ['a']))
        self.assertFalse(cmd.validate_params({'a': None}, ['a']))
        self.assertFalse(cmd.validate_params({}, ['a']))


if __name__ == '__main__':
    unittest.main()
