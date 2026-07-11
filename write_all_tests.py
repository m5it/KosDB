#!/usr/bin/env python3
contents = {}

contents['test_parser.py'] = '''#!/usr/bin/env python3
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
'''

contents['test_commands.py'] = '''#!/usr/bin/env python3
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
'''

contents['test_database.py'] = '''#!/usr/bin/env python3
"""Unit tests for the database module."""

import os
import shutil
import tempfile
import unittest

import database as db_module


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db = db_module.Database(self.temp_dir)

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_use_database(self):
        self.db.create_database('testdb')
        result = self.db.use_database('testdb')
        self.assertIn('Switched', result)
        self.assertEqual(self.db.current_db, 'testdb')

    def test_create_database(self):
        result = self.db.create_database('newdb')
        self.assertIn('created', result)
        self.assertTrue(os.path.isdir(os.path.join(self.temp_dir, 'newdb')))

    def test_drop_database(self):
        self.db.create_database('olddb')
        result = self.db.drop_database('olddb')
        self.assertIn('dropped', result)
        self.assertFalse(os.path.isdir(os.path.join(self.temp_dir, 'olddb')))

    def test_create_table(self):
        self.db.create_database('testdb')
        self.db.use_database('testdb')
        result = self.db.create_table('users', ['id', 'name'])
        self.assertIn('created', result)
        self.assertIn('users', self.db.list_tables())

    def test_create_table_already_exists(self):
        self.db.create_database('testdb')
        self.db.use_database('testdb')
        self.db.create_table('users', ['id', 'name'])
        result = self.db.create_table('users', ['id', 'name'])
        self.assertIn('already exists', result)

    def test_drop_table(self):
        self.db.create_database('testdb')
        self.db.use_database('testdb')
        self.db.create_table('users', ['id', 'name'])
        result = self.db.drop_table('users')
        self.assertIn('dropped', result)
        self.assertNotIn('users', self.db.list_tables())

    def test_drop_table_missing(self):
        self.db.create_database('testdb')
        self.db.use_database('testdb')
        result = self.db.drop_table('users')
        self.assertIn('does not exist', result)

    def test_insert(self):
        self.db.create_database('testdb')
        self.db.use_database('testdb')
        self.db.create_table('users', ['id', 'name'])
        result = self.db.insert('users', [1, 'Alice'])
        self.assertIn('inserted', result)

    def test_insert_no_table(self):
        self.db.create_database('testdb')
        self.db.use_database('testdb')
        result = self.db.insert('users', [1, 'Alice'])
        self.assertIn('does not exist', result)

    def test_select_all(self):
        self.db.create_database('testdb')
        self.db.use_database('testdb')
        self.db.create_table('users', ['id', 'name'])
        self.db.insert('users', [1, 'Alice'])
        self.db.insert('users', [2, 'Bob'])
        rows = self.db.select('users', ['*'], raw=True)
        self.assertEqual(len(rows), 2)

    def test_select_columns(self):
        self.db.create_database('testdb')
        self.db.use_database('testdb')
        self.db.create_table('users', ['id', 'name'])
        self.db.insert('users', [1, 'Alice'])
        rows = self.db.select('users', ['id'], raw=True)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].get('id'), '1')

    def test_update(self):
        self.db.create_database('testdb')
        self.db.use_database('testdb')
        self.db.create_table('users', ['id', 'name'])
        self.db.insert('users', [1, 'Alice'])
        result = self.db.update('users', {'name': 'Charlie'}, {'id': 1})
        self.assertIn('Updated', result)
        rows = self.db.select('users', ['name'], raw=True)
        self.assertEqual(rows[0]['name'], 'Charlie')

    def test_delete(self):
        self.db.create_database('testdb')
        self.db.use_database('testdb')
        self.db.create_table('users', ['id', 'name'])
        self.db.insert('users', [1, 'Alice'])
        self.db.insert('users', [2, 'Bob'])
        result = self.db.delete('users', {'id': 1})
        self.assertIn('Deleted', result)
        rows = self.db.select('users', ['*'], raw=True)
        self.assertEqual(len(rows), 1)

    def test_list_tables(self):
        self.db.create_database('testdb')
        self.db.use_database('testdb')
        self.db.create_table('users', ['id'])
        self.db.create_table('orders', ['id'])
        tables = self.db.list_tables()
        self.assertIn('users', tables)
        self.assertIn('orders', tables)

    def test_list_databases(self):
        self.db.create_database('db1')
        self.db.create_database('db2')
        dbs = self.db.list_databases()
        self.assertIn('db1', dbs)
        self.assertIn('db2', dbs)

    def test_transaction_commit(self):
        self.db.create_database('testdb')
        self.db.use_database('testdb')
        self.db.create_table('users', ['id', 'name'])
        self.db.begin_transaction()
        self.db.insert('users', [1, 'Alice'])
        result = self.db.commit_transaction()
        self.assertIn('Committed', result)
        rows = self.db.select('users', ['*'], raw=True)
        self.assertEqual(len(rows), 1)

    def test_transaction_rollback(self):
        self.db.create_database('testdb')
        self.db.use_database('testdb')
        self.db.create_table('users', ['id', 'name'])
        self.db.insert('users', [1, 'Alice'])
        self.db.begin_transaction()
        self.db.insert('users', [2, 'Bob'])
        result = self.db.rollback_transaction()
        self.assertIn('Rolled back', result)
        rows = self.db.select('users', ['*'], raw=True)
        self.assertEqual(len(rows), 1)

    def test_create_user(self):
        result = self.db.create_user('alice', 'secret')
        self.assertIn('created', result)
        self.assertIn('alice', self.db.list_users())

    def test_authenticate_user(self):
        self.db.create_user('alice', 'secret')
        success, is_admin, privs = self.db.authenticate_user('alice', 'secret')
        self.assertTrue(success)
        self.assertFalse(self.db.authenticate_user('alice', 'wrong')[0])

    def test_grant_privilege(self):
        self.db.create_user('alice', 'secret')
        result = self.db.grant_privilege('alice', 'testdb', 'users', ['SELECT'])
        self.assertIn('Granted', result)
        self.assertTrue(self.db.check_privilege('alice', 'testdb', 'users', 'SELECT'))

    def test_backup_and_restore_database(self):
        self.db.create_database('testdb')
        self.db.use_database('testdb')
        self.db.create_table('users', ['id', 'name'])
        self.db.insert('users', [1, 'Alice'])
        backup_path = os.path.join(self.temp_dir, 'backup.json.gz')
        from commands import BackupDatabaseCommand
        cmd = BackupDatabaseCommand(self.db)
        result = cmd.execute({'database': 'testdb', 'file': backup_path}, {'current_db': 'testdb', 'is_admin': True})
        self.assertIn('Backup complete', result)

        self.db.drop_table('users')
        from restore_commands import RestoreCommands
        rc = RestoreCommands(self.db)
        result = rc.restore_database('testdb', backup_path)
        self.assertIn('Restored', result)
        rows = self.db.select('users', ['*'], raw=True)
        self.assertEqual(len(rows), 1)


if __name__ == '__main__':
    unittest.main()
'''

contents['test_binlog.py'] = '''#!/usr/bin/env python3
"""Unit tests for the binary log module."""

import os
import shutil
import tempfile
import unittest
from binlog import Binlog


class TestBinlog(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_initial_position_is_zero(self):
        binlog = Binlog(self.data_dir)
        self.assertEqual(binlog.get_latest_position(), 0)
        binlog.close()

    def test_write_entry_increments_position(self):
        binlog = Binlog(self.data_dir)
        pos1 = binlog.write_entry(1, 'db1', 'INSERT', 'users', {'row': {'id': 1}})
        pos2 = binlog.write_entry(1, 'db1', 'INSERT', 'users', {'row': {'id': 2}})
        self.assertEqual(pos1, 1)
        self.assertEqual(pos2, 2)
        self.assertEqual(binlog.get_latest_position(), 2)
        binlog.close()

    def test_get_entry(self):
        binlog = Binlog(self.data_dir)
        binlog.write_entry(1, 'db1', 'INSERT', 'users', {'row': {'id': 1}})
        entry = binlog.get_entry(1)
        self.assertIsNotNone(entry)
        self.assertEqual(entry['operation'], 'INSERT')
        self.assertEqual(entry['database'], 'db1')
        self.assertEqual(entry['table'], 'users')
        binlog.close()

    def test_get_entries(self):
        binlog = Binlog(self.data_dir)
        for i in range(1, 6):
            binlog.write_entry(1, 'db1', 'INSERT', 'users', {'row': {'id': i}})
        entries = binlog.get_entries(2, limit=2)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]['position'], 3)
        self.assertEqual(entries[1]['position'], 4)
        binlog.close()

    def test_get_entries_limit(self):
        binlog = Binlog(self.data_dir)
        for i in range(1, 11):
            binlog.write_entry(1, 'db1', 'INSERT', 'users', {'row': {'id': i}})
        entries = binlog.get_entries(0, limit=5)
        self.assertEqual(len(entries), 5)
        binlog.close()

    def test_truncate_before(self):
        binlog = Binlog(self.data_dir)
        for i in range(1, 6):
            binlog.write_entry(1, 'db1', 'INSERT', 'users', {'row': {'id': i}})
        binlog.truncate_before(3)
        self.assertIsNone(binlog.get_entry(1))
        self.assertIsNone(binlog.get_entry(2))
        self.assertIsNotNone(binlog.get_entry(3))
        binlog.close()


if __name__ == '__main__':
    unittest.main()
'''

contents['test_failover.py'] = '''#!/usr/bin/env python3
"""Unit tests for the failover / Raft module."""

import unittest
from failover import RaftConsensus, LogEntry, NodeState, FailoverManager, FailoverCommands


class TestLogEntry(unittest.TestCase):
    def test_to_dict(self):
        entry = LogEntry(term=1, index=1, command={'type': 'INSERT'})
        d = entry.to_dict()
        self.assertEqual(d['term'], 1)
        self.assertEqual(d['index'], 1)
        self.assertEqual(d['command'], {'type': 'INSERT'})
        self.assertFalse(d['committed'])


class TestRaftConsensus(unittest.TestCase):
    def test_initial_state(self):
        raft = RaftConsensus('node1', '127.0.0.1', 9000, [])
        self.assertEqual(raft.state, NodeState.FOLLOWER)
        self.assertEqual(raft.current_term, 0)
        raft.stop()

    def test_last_log_term_empty(self):
        raft = RaftConsensus('node1', '127.0.0.1', 9000, [])
        self.assertEqual(raft._last_log_term(), 0)
        raft.stop()

    def test_handle_request_vote_rejects_lower_term(self):
        raft = RaftConsensus('node1', '127.0.0.1', 9000, [])
        raft.current_term = 5
        response = raft._handle_request_vote({
            'type': 'RequestVote',
            'term': 3,
            'candidate_id': 'node2',
            'last_log_index': 0,
            'last_log_term': 0
        })
        self.assertFalse(response['vote_granted'])
        self.assertEqual(response['term'], 5)
        raft.stop()

    def test_handle_request_vote_grants_vote(self):
        raft = RaftConsensus('node1', '127.0.0.1', 9000, [])
        response = raft._handle_request_vote({
            'type': 'RequestVote',
            'term': 1,
            'candidate_id': 'node2',
            'last_log_index': 0,
            'last_log_term': 0
        })
        self.assertTrue(response['vote_granted'])
        self.assertEqual(raft.voted_for, 'node2')
        raft.stop()

    def test_handle_append_entries_rejects_lower_term(self):
        raft = RaftConsensus('node1', '127.0.0.1', 9000, [])
        raft.current_term = 5
        response = raft._handle_append_entries({
            'type': 'AppendEntries',
            'term': 3,
            'leader_id': 'node2',
            'prev_log_index': 0,
            'prev_log_term': 0,
            'entries': [],
            'leader_commit': 0
        })
        self.assertFalse(response['success'])
        raft.stop()

    def test_handle_append_entries_appends(self):
        raft = RaftConsensus('node1', '127.0.0.1', 9000, [])
        response = raft._handle_append_entries({
            'type': 'AppendEntries',
            'term': 1,
            'leader_id': 'node2',
            'prev_log_index': 0,
            'prev_log_term': 0,
            'entries': [{'term': 1, 'index': 1, 'command': {'type': 'INSERT'}}],
            'leader_commit': 0
        })
        self.assertTrue(response['success'])
        self.assertEqual(len(raft.log), 1)
        self.assertEqual(raft.log[0].term, 1)
        raft.stop()

    def test_handle_heartbeat(self):
        raft = RaftConsensus('node1', '127.0.0.1', 9000, [])
        response = raft._handle_heartbeat({
            'type': 'Heartbeat',
            'term': 2,
            'leader_id': 'node2'
        })
        self.assertTrue(response['success'])
        self.assertEqual(raft.current_term, 2)
        self.assertEqual(raft.leader_id, 'node2')
        raft.stop()

    def test_propose_not_leader(self):
        raft = RaftConsensus('node1', '127.0.0.1', 9000, [])
        success, error = raft.propose({'type': 'INSERT'})
        self.assertFalse(success)
        self.assertIn('No leader', error)
        raft.stop()

    def test_get_status(self):
        raft = RaftConsensus('node1', '127.0.0.1', 9000, [])
        status = raft.get_status()
        self.assertEqual(status['node_id'], 'node1')
        self.assertEqual(status['state'], 'follower')
        self.assertIn('peers', status)
        raft.stop()


class TestFailoverManager(unittest.TestCase):
    def test_initial_status(self):
        fm = FailoverManager('node1', '127.0.0.1', 9000, [])
        status = fm.get_cluster_status()
        self.assertEqual(status['node_id'], 'node1')
        self.assertFalse(status['is_primary'])
        fm.stop()

    def test_execute_command_not_leader(self):
        fm = FailoverManager('node1', '127.0.0.1', 9000, [])
        success, msg = fm.execute_command({'type': 'INSERT', 'table': 'users', 'values': [1]})
        self.assertFalse(success)
        self.assertIn('No leader', msg)
        fm.stop()


class TestFailoverCommands(unittest.TestCase):
    def test_failover_status_no_manager(self):
        fc = FailoverCommands()
        result = fc.failover_status()
        self.assertIn('not available', result)

    def test_propose_command_no_manager(self):
        fc = FailoverCommands()
        result = fc.propose_command('{"type":"INSERT"}')
        self.assertIn('not available', result)

    def test_propose_command_invalid_json(self):
        fc = FailoverCommands()
        result = fc.propose_command('not json')
        self.assertIn('Invalid JSON', result)

    def test_failover_status_with_manager(self):
        fm = FailoverManager('node1', '127.0.0.1', 9000, [])
        fc = FailoverCommands(fm)
        result = fc.failover_status()
        self.assertIn('node1', result)
        fm.stop()


if __name__ == '__main__':
    unittest.main()
'''

contents['test_monitoring.py'] = '''#!/usr/bin/env python3
"""Unit tests for the monitoring module."""

import unittest
from monitoring import (
    MetricsRegistry,
    HealthChecker,
    MonitoringCommands,
    MetricType
)


class TestMetricsRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = MetricsRegistry()

    def test_counter(self):
        self.registry.increment_counter('queries.total', 1, {'type': 'SELECT'})
        self.assertEqual(self.registry.get_counter('queries.total', {'type': 'SELECT'}), 1)
        self.registry.increment_counter('queries.total', 2, {'type': 'SELECT'})
        self.assertEqual(self.registry.get_counter('queries.total', {'type': 'SELECT'}), 3)

    def test_gauge(self):
        self.registry.set_gauge('connections.active', 5)
        self.assertEqual(self.registry.get_gauge('connections.active'), 5)

    def test_histogram_stats(self):
        for v in [1, 2, 3, 4, 5]:
            self.registry.record_histogram('latency', v)
        stats = self.registry.get_histogram_stats('latency')
        self.assertEqual(stats['count'], 5)
        self.assertEqual(stats['min'], 1)
        self.assertEqual(stats['max'], 5)

    def test_record_timer(self):
        self.registry.record_timer('query_time', 0.123)
        stats = self.registry.get_histogram_stats('query_time')
        self.assertEqual(stats['count'], 1)

    def test_get_all_metrics(self):
        self.registry.increment_counter('c', 1)
        self.registry.set_gauge('g', 2)
        self.registry.record_histogram('h', 3)
        all_metrics = self.registry.get_all_metrics()
        self.assertIn('c', all_metrics['counters'])
        self.assertIn('g', all_metrics['gauges'])
        self.assertIn('h', all_metrics['histograms'])

    def test_export_prometheus(self):
        self.registry.increment_counter('queries_total', 5)
        self.registry.set_gauge('active', 3)
        self.registry.record_histogram('latency', 0.1)
        output = self.registry.export_prometheus()
        self.assertIn('queries_total{', output)
        self.assertIn('active{', output)
        self.assertIn('latency_count', output)

    def test_callback(self):
        received = []
        def cb(metric):
            received.append(metric)
        self.registry.register_callback(cb)
        self.registry.set_gauge('x', 1)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].name, 'x')


class TestHealthChecker(unittest.TestCase):
    def setUp(self):
        self.checker = HealthChecker()

    def test_unknown_check(self):
        result = self.checker.run_check('missing')
        self.assertEqual(result['status'], 'unknown')

    def test_healthy_check(self):
        self.checker.add_check('db', lambda: (True, 'connected'))
        result = self.checker.run_check('db')
        self.assertEqual(result['status'], 'healthy')
        self.assertEqual(result['message'], 'connected')

    def test_unhealthy_check(self):
        self.checker.add_check('db', lambda: (False, 'down'))
        result = self.checker.run_check('db')
        self.assertEqual(result['status'], 'unhealthy')

    def test_run_all_checks(self):
        self.checker.add_check('a', lambda: (True, 'ok'))
        self.checker.add_check('b', lambda: (False, 'bad'))
        result = self.checker.run_all_checks()
        self.assertEqual(result['status'], 'unhealthy')
        self.assertEqual(result['checks']['a']['status'], 'healthy')
        self.assertEqual(result['checks']['b']['status'], 'unhealthy')


class TestMonitoringCommands(unittest.TestCase):
    def test_metrics_show_no_registry(self):
        mc = MonitoringCommands()
        result = mc.metrics_show()
        self.assertIn('not available', result)

    def test_health_check_no_checker(self):
        mc = MonitoringCommands()
        result = mc.health_check()
        self.assertIn('not available', result)

    def test_prometheus_no_registry(self):
        mc = MonitoringCommands()
        result = mc.metrics_prometheus()
        self.assertIn('not available', result)

    def test_metrics_show_with_registry(self):
        registry = MetricsRegistry()
        registry.set_gauge('active', 5)
        mc = MonitoringCommands(registry=registry)
        result = mc.metrics_show()
        self.assertIn('active', result)

    def test_health_check_with_checker(self):
        checker = HealthChecker()
        checker.add_check('db', lambda: (True, 'ok'))
        mc = MonitoringCommands(health_checker=checker)
        result = mc.health_check()
        self.assertIn('healthy', result)

    def test_prometheus_with_registry(self):
        registry = MetricsRegistry()
        registry.increment_counter('c', 1)
        mc = MonitoringCommands(registry=registry)
        result = mc.metrics_prometheus()
        self.assertIn('c{', result)


if __name__ == '__main__':
    unittest.main()
'''

contents['test_sharding.py'] = '''#!/usr/bin/env python3
"""Unit tests for the sharding module."""

import unittest
from unittest.mock import MagicMock
from sharding import ShardingCoordinator, ShardingError


class TestShardingCoordinator(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.coordinator = ShardingCoordinator(self.db)

    def test_create_shard(self):
        self.coordinator.manager.create_shard = MagicMock(return_value="OK: shard1 created")
        result = self.coordinator.create_shard('shard1', 'us-east', '127.0.0.1', 8001)
        self.assertIn("OK", result)
        self.coordinator.manager.create_shard.assert_called_once()

    def test_drop_shard(self):
        self.coordinator.manager.drop_shard = MagicMock(return_value="OK: shard1 dropped")
        result = self.coordinator.drop_shard('shard1')
        self.assertIn("OK", result)
        self.coordinator.manager.drop_shard.assert_called_once_with('shard1')

    def test_list_shards(self):
        self.coordinator.manager.list_shards = MagicMock(return_value=[{'shard_id': 'shard1'}])
        result = self.coordinator.list_shards()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['shard_id'], 'shard1')

    def test_add_read_replica(self):
        self.coordinator.manager.add_read_replica = MagicMock(return_value="OK: replica added")
        result = self.coordinator.add_read_replica('shard1', 'rep1', 'us-west', '127.0.0.1', 8002)
        self.assertIn("OK", result)

    def test_rebalance(self):
        self.coordinator.manager.rebalance_shards = MagicMock(return_value="OK: rebalanced")
        result = self.coordinator.rebalance()
        self.assertIn("OK", result)

    def test_route_key(self):
        self.coordinator.router.route_key = MagicMock(return_value={'shard_id': 'shard1'})
        result = self.coordinator.route_key('user-1')
        self.assertEqual(result['shard_id'], 'shard1')

    def test_route_query(self):
        self.coordinator.router.route_query = MagicMock(return_value=[{'shard_id': 'shard1'}])
        result = self.coordinator.route_query('users', where={'id': 1})
        self.assertEqual(len(result), 1)

    def test_is_local_shard_true(self):
        self.coordinator.manager.get_shard = MagicMock(return_value=MagicMock(host='127.0.0.1', port=1))
        self.assertTrue(self.coordinator.is_local_shard('shard1'))

    def test_is_local_shard_false(self):
        self.coordinator.manager.get_shard = MagicMock(return_value=MagicMock(host='10.0.0.1', port=1))
        self.assertFalse(self.coordinator.is_local_shard('shard1'))

    def test_get_stats(self):
        self.coordinator.manager.get_stats = MagicMock(return_value={'shards': 1})
        self.coordinator.router.get_stats = MagicMock(return_value={'routes': 1})
        result = self.coordinator.get_stats()
        self.assertIn('manager', result)
        self.assertIn('router', result)


if __name__ == '__main__':
    unittest.main()
'''

contents['test_backup_utils.py'] = '''#!/usr/bin/env python3
"""Unit tests for backup utilities."""

import gzip
import json
import os
import shutil
import tempfile
import unittest
from backup_utils import (
    calculate_checksum,
    verify_backup_integrity,
    create_backup_metadata,
    add_integrity_check,
    validate_before_restore,
    get_backup_info,
    BackupManager,
    generate_backup_filename,
)


class TestBackupUtils(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def _write_backup(self, filename, data, with_checksum=True):
        path = os.path.join(self.temp_dir, filename)
        if with_checksum:
            data = add_integrity_check(data)
        with gzip.open(path, 'wt', encoding='utf-8') as f:
            json.dump(data, f)
        return path

    def test_calculate_checksum(self):
        data = b'hello world'
        self.assertEqual(len(calculate_checksum(data)), 64)
        self.assertNotEqual(calculate_checksum(data), calculate_checksum(b'hello'))

    def test_verify_backup_integrity_success(self):
        data = {
            'version': '1.0',
            'database': 'testdb',
            'tables': {
                'users': {'schema': {'columns': ['id', 'name']}, 'rows': [{'id': 1, 'name': 'Alice'}]}
            }
        }
        path = self._write_backup('valid.json.gz', data)
        valid, error = verify_backup_integrity(path)
        self.assertTrue(valid)
        self.assertIsNone(error)

    def test_verify_backup_integrity_missing_version(self):
        data = {'tables': {}}
        path = self._write_backup('no_version.json.gz', data)
        valid, error = verify_backup_integrity(path)
        self.assertFalse(valid)
        self.assertIn('version', error)

    def test_verify_backup_integrity_missing_tables(self):
        data = {'version': '1.0'}
        path = self._write_backup('no_tables.json.gz', data)
        valid, error = verify_backup_integrity(path)
        self.assertFalse(valid)
        self.assertIn('tables', error)

    def test_verify_backup_integrity_checksum_mismatch(self):
        data = {
            'version': '1.0',
            'database': 'testdb',
            'tables': {},
            'checksum': 'invalid'
        }
        path = self._write_backup('bad_checksum.json.gz', data, with_checksum=False)
        valid, error = verify_backup_integrity(path)
        self.assertFalse(valid)
        self.assertIn('Checksum mismatch', error)

    def test_verify_backup_integrity_file_not_found(self):
        valid, error = verify_backup_integrity('/nonexistent/path.json.gz')
        self.assertFalse(valid)
        self.assertIn('File not found', error)

    def test_verify_backup_integrity_bad_gzip(self):
        path = os.path.join(self.temp_dir, 'bad.json.gz')
        with open(path, 'w') as f:
            f.write('not gzip')
        valid, error = verify_backup_integrity(path)
        self.assertFalse(valid)
        self.assertIn('Invalid gzip', error)

    def test_create_backup_metadata(self):
        meta = create_backup_metadata('db1', ['users'], 5)
        self.assertEqual(meta['database'], 'db1')
        self.assertEqual(meta['table_count'], 1)
        self.assertEqual(meta['row_count'], 5)

    def test_add_integrity_check(self):
        data = {'version': '1.0'}
        result = add_integrity_check(data)
        self.assertIn('checksum', result)
        self.assertEqual(len(result['checksum']), 64)

    def test_validate_before_restore_success(self):
        data = {'version': '1.0', 'database': 'db1', 'tables': {}}
        path = self._write_backup('restore.json.gz', data)
        valid, error = validate_before_restore(path, 'db1')
        self.assertTrue(valid)
        self.assertIsNone(error)

    def test_get_backup_info(self):
        data = {'version': '1.0', 'database': 'db1', 'tables': {}, 'row_count': 0}
        path = self._write_backup('info.json.gz', data)
        info = get_backup_info(path)
        self.assertIsNotNone(info)
        self.assertEqual(info['database'], 'db1')
        self.assertTrue(info['has_checksum'])

    def test_backup_manager_list_and_cleanup(self):
        manager = BackupManager(self.temp_dir)
        for i in range(3):
            path = os.path.join(self.temp_dir, f'backup_{i}.json.gz')
            with gzip.open(path, 'wt', encoding='utf-8') as f:
                json.dump({'version': '1.0'}, f)
            os.utime(path, (i, i))
        backups = manager.list_backups()
        self.assertEqual(len(backups), 3)
        manager.cleanup_old_backups(keep_count=1)
        self.assertEqual(len(manager.list_backups()), 1)

    def test_generate_backup_filename(self):
        fn = generate_backup_filename('db1')
        self.assertTrue(fn.startswith('db1_'))
        self.assertTrue(fn.endswith('.json.gz'))


if __name__ == '__main__':
    unittest.main()
'''

contents['test_restore_commands.py'] = '''#!/usr/bin/env python3
"""Unit tests for restore command handlers."""

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock
from restore_commands import RestoreCommands


class TestRestoreCommands(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.commands = RestoreCommands()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def _make_backup(self, filename, data):
        import gzip
        import json
        path = os.path.join(self.temp_dir, filename)
        with gzip.open(path, 'wt', encoding='utf-8') as f:
            json.dump(data, f)
        return path

    def test_restore_database_no_db(self):
        result = self.commands.restore_database('testdb', '/tmp/backup.json.gz', None)
        self.assertIn('Database not available', result)

    def test_restore_database_file_not_found(self):
        db = MagicMock()
        result = self.commands.restore_database('testdb', '/nonexistent.json.gz', db)
        self.assertIn('not found', result)

    def test_restore_database_success(self):
        db = MagicMock()
        db.list_tables.return_value = []
        path = self._make_backup('testdb.json.gz', {
            'version': '1.0',
            'database': 'testdb',
            'tables': {
                'users': {
                    'schema': {'columns': ['id', 'name']},
                    'rows': [{'id': 1, 'name': 'Alice'}]
                }
            }
        })
        result = self.commands.restore_database('testdb', path, db)
        self.assertIn('Restored', result)
        self.assertEqual(db.create_table.call_count, 1)
        self.assertEqual(db.insert.call_count, 1)

    def test_restore_database_wrong_database(self):
        db = MagicMock()
        path = self._make_backup('other.json.gz', {
            'version': '1.0',
            'database': 'otherdb',
            'tables': {}
        })
        result = self.commands.restore_database('testdb', path, db)
        self.assertIn('does not match', result)

    def test_restore_table_success(self):
        db = MagicMock()
        path = self._make_backup('users.json.gz', {
            'version': '1.0',
            'database': 'testdb',
            'tables': {
                'users': {
                    'schema': {'columns': ['id', 'name']},
                    'rows': [{'id': 1, 'name': 'Alice'}]
                }
            }
        })
        result = self.commands.restore_table('testdb', 'users', path, db)
        self.assertIn('Restored table', result)
        self.assertEqual(db.create_table.call_count, 1)
        self.assertEqual(db.insert.call_count, 1)

    def test_restore_table_not_in_backup(self):
        db = MagicMock()
        path = self._make_backup('users.json.gz', {
            'version': '1.0',
            'database': 'testdb',
            'tables': {}
        })
        result = self.commands.restore_table('testdb', 'users', path, db)
        self.assertIn('not found', result)

    def test_list_backups(self):
        path = self._make_backup('b1.json.gz', {'version': '1.0'})
        result = self.commands.list_backups(self.temp_dir)
        self.assertIn('b1.json.gz', result)

    def test_verify_backup_command_valid(self):
        path = self._make_backup('valid.json.gz', {
            'version': '1.0',
            'database': 'testdb',
            'tables': {}
        })
        result = self.commands.verify_backup(path)
        self.assertIn('valid', result)

    def test_verify_backup_command_invalid(self):
        path = self._make_backup('bad.json.gz', {'version': '1.0'})
        result = self.commands.verify_backup(path)
        self.assertIn('invalid', result)


if __name__ == '__main__':
    unittest.main()
'''

for name, content in contents.items():
    with open(name, 'w') as f:
        f.write(content)
    print('Wrote', name)
