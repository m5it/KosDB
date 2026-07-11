#!/usr/bin/env python3
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
