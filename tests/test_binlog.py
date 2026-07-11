#!/usr/bin/env python3
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
