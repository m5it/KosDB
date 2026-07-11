#!/usr/bin/env python3
"""Unit tests for the SQL parser."""

import unittest
from parser import CommandParser, BackupRestoreParser


class TestCommandParser(unittest.TestCase):
    def setUp(self):
        self.parser = CommandParser()

    def test_create_table(self):
        cmd, params = self.parser.parse("CREATE TABLE users (id INT PRIMARY KEY, name TEXT)")
        self.assertEqual(cmd, 'CREATE')
        self.assertEqual(params['table'], 'users')
        self.assertEqual(params['columns'], ['id INT PRIMARY KEY', 'name TEXT'])

    def test_create_table_without_columns(self):
        cmd, params = self.parser.parse("CREATE TABLE logs")
        self.assertEqual(cmd, 'CREATE')
        self.assertEqual(params['table'], 'logs')
        self.assertIsNone(params['columns'])

    def test_drop_table(self):
        cmd, params = self.parser.parse("DROP TABLE users")
        self.assertEqual(cmd, 'DROP')
        self.assertEqual(params['table'], 'users')

    def test_insert_int_and_text(self):
        cmd, params = self.parser.parse("INSERT INTO users VALUES (1, 'Alice')")
        self.assertEqual(cmd, 'INSERT')
        self.assertEqual(params['table'], 'users')
        self.assertEqual(params['values'], [1, 'Alice'])

    def test_insert_float(self):
        cmd, params = self.parser.parse("INSERT INTO readings VALUES (3.14, 42)")
        self.assertEqual(params['values'], [3.14, 42])

    def test_insert_quoted_values(self):
        cmd, params = self.parser.parse('INSERT INTO users VALUES (2, "Bob")')
        self.assertEqual(params['values'], [2, 'Bob'])

    def test_select_star(self):
        cmd, params = self.parser.parse("SELECT * FROM users")
        self.assertEqual(cmd, 'SELECT')
        self.assertEqual(params['table'], 'users')
        self.assertEqual(params['columns'], ['*'])

    def test_select_columns_with_where(self):
        cmd, params = self.parser.parse("SELECT id, name FROM users WHERE id=1")
        self.assertEqual(params['columns'], ['id', 'name'])
        self.assertEqual(params['where'], {'id': 1})

    def test_select_order_by_desc(self):
        cmd, params = self.parser.parse("SELECT * FROM users ORDER BY id DESC")
        self.assertEqual(params['order_by'], 'id')
        self.assertTrue(params['order_desc'])

    def test_update(self):
        cmd, params = self.parser.parse("UPDATE users SET name='Charlie' WHERE id=1")
        self.assertEqual(cmd, 'UPDATE')
        self.assertEqual(params['table'], 'users')
        self.assertEqual(params['set'], {'name': 'Charlie'})
        self.assertEqual(params['where'], {'id': 1})

    def test_delete_with_where(self):
        cmd, params = self.parser.parse("DELETE FROM users WHERE id=2")
        self.assertEqual(cmd, 'DELETE')
        self.assertEqual(params['table'], 'users')
        self.assertEqual(params['where'], {'id': 2})

    def test_delete_all(self):
        cmd, params = self.parser.parse("DELETE FROM users")
        self.assertEqual(params['where'], None)

    def test_use_database(self):
        cmd, params = self.parser.parse("USE testdb")
        self.assertEqual(cmd, 'USE')
        self.assertEqual(params['database'], 'testdb')

    def test_create_database(self):
        cmd, params = self.parser.parse("CREATE DATABASE testdb")
        self.assertEqual(cmd, 'CREATE_DB')
        self.assertEqual(params['database'], 'testdb')

    def test_drop_database(self):
        cmd, params = self.parser.parse("DROP DATABASE testdb")
        self.assertEqual(cmd, 'DROP_DB')
        self.assertEqual(params['database'], 'testdb')

    def test_show_commands(self):
        self.assertEqual(self.parser.parse("SHOW TABLES"), ('SHOW_TABLES', {}))
        self.assertEqual(self.parser.parse("SHOW DATABASES"), ('SHOW_DATABASES', {}))
        self.assertEqual(self.parser.parse("SHOW USERS"), ('SHOW_USERS', {}))
        self.assertEqual(self.parser.parse("SHOW MASTER STATUS"), ('SHOW_MASTER_STATUS', {}))
        self.assertEqual(self.parser.parse("SHOW SLAVE STATUS"), ('SHOW_SLAVE_STATUS', {}))

    def test_replication_commands(self):
        self.assertEqual(self.parser.parse("START SLAVE"), ('START_SLAVE', {}))
        self.assertEqual(self.parser.parse("STOP SLAVE"), ('STOP_SLAVE', {}))
        self.assertEqual(self.parser.parse("RESET SLAVE"), ('RESET_SLAVE', {}))

    def test_create_replication_user(self):
        cmd, params = self.parser.parse("CREATE REPLICATION USER repl IDENTIFIED BY replpass")
        self.assertEqual(cmd, 'CREATE_REPL_USER')
        self.assertEqual(params['username'], 'repl')
        self.assertEqual(params['password'], 'replpass')

    def test_help_quit(self):
        self.assertEqual(self.parser.parse("HELP"), ('HELP', {}))
        self.assertEqual(self.parser.parse("QUIT"), ('QUIT', {}))
        self.assertEqual(self.parser.parse("EXIT"), ('QUIT', {}))

    def test_unknown_command(self):
        cmd, params = self.parser.parse("FOOBAR")
        self.assertEqual(cmd, 'UNKNOWN')
        self.assertIsNone(params)


class TestBackupRestoreParser(unittest.TestCase):
    def setUp(self):
        self.parser = BackupRestoreParser()

    def test_backup_database(self):
        cmd, params = self.parser.parse("BACKUP DATABASE testdb TO /tmp/backup")
        self.assertEqual(cmd, 'BACKUP_DB')
        self.assertEqual(params['database'], 'testdb')
        self.assertEqual(params['file'], '/tmp/backup')

    def test_restore_database(self):
        cmd, params = self.parser.parse("RESTORE DATABASE testdb FROM /tmp/backup")
        self.assertEqual(cmd, 'RESTORE_DB')
        self.assertEqual(params['database'], 'testdb')
        self.assertEqual(params['file'], '/tmp/backup')

    def test_backup_table(self):
        cmd, params = self.parser.parse("BACKUP TABLE users TO /tmp/users")
        self.assertEqual(cmd, 'BACKUP_TABLE')
        self.assertEqual(params['table'], 'users')
        self.assertEqual(params['file'], '/tmp/users')

    def test_show_backups(self):
        cmd, params = self.parser.parse("SHOW BACKUPS /tmp")
        self.assertEqual(cmd, 'SHOW_BACKUPS')
        self.assertEqual(params['path'], '/tmp')

    def test_verify_backup(self):
        cmd, params = self.parser.parse("VERIFY BACKUP /tmp/backup.json.gz")
        self.assertEqual(cmd, 'VERIFY_BACKUP')
        self.assertEqual(params['file'], '/tmp/backup.json.gz')

    def test_transaction_commands(self):
        self.assertEqual(self.parser.parse("BEGIN"), ('BEGIN', {}))
        self.assertEqual(self.parser.parse("COMMIT"), ('COMMIT', {}))
        self.assertEqual(self.parser.parse("ROLLBACK"), ('ROLLBACK', {}))

    def test_dist_tx_commands(self):
        cmd, params = self.parser.parse('DIST_TX_BEGIN [{"op":"insert"}]')
        self.assertEqual(cmd, 'DIST_TX_BEGIN')
        self.assertEqual(params['operations'], '[{"op":"insert"}]')

        cmd, params = self.parser.parse("DIST_TX_STATUS tx-123")
        self.assertEqual(cmd, 'DIST_TX_STATUS')
        self.assertEqual(params['tx_id'], 'tx-123')

        self.assertEqual(self.parser.parse("DIST_TX_LIST"), ('DIST_TX_LIST', {}))

    def test_failover_commands(self):
        self.assertEqual(self.parser.parse("FAILOVER STATUS"), ('FAILOVER_STATUS', {}))
        cmd, params = self.parser.parse('FAILOVER PROPOSE {"type":"INSERT"}')
        self.assertEqual(cmd, 'FAILOVER_PROPOSE')
        self.assertEqual(params['command'], '{"type":"INSERT"}')

    def test_monitoring_commands(self):
        self.assertEqual(self.parser.parse("METRICS"), ('METRICS', {}))
        self.assertEqual(self.parser.parse("HEALTH"), ('HEALTH', {}))
        self.assertEqual(self.parser.parse("PROMETHEUS"), ('PROMETHEUS', {}))


if __name__ == '__main__':
    unittest.main()
