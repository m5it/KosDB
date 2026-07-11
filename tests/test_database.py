#!/usr/bin/env python3
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
        self.assertIn('Inserted', result)
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
        rows = self.db.select('users', ['id'], raw=True)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].get('id'), 1)
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
