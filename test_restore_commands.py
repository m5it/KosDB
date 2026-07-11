#!/usr/bin/env python3
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
