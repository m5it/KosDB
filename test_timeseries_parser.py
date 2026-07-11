#!/usr/bin/env python3
"""Unit tests for timeseries parser."""

import unittest
from timeseries_parser import TimeSeriesParser, get_timeseries_parser


class TestTimeseriesParser(unittest.TestCase):
    def setUp(self):
        self.parser = TimeSeriesParser()

    def test_create_hypertable(self):
        result = self.parser.parse('CREATE HYPERTABLE metrics CHUNK_INTERVAL 1h RETENTION 7d')
        self.assertEqual(result['type'], 'CREATE_HYPERTABLE')
        self.assertEqual(result['chunk_interval'], '1h')

    def test_drop_hypertable(self):
        result = self.parser.parse('DROP HYPERTABLE metrics')
        self.assertEqual(result['type'], 'DROP_HYPERTABLE')

    def test_insert(self):
        result = self.parser.parse("INSERT INTO metrics VALUES (1234567890, 42.0, {'host':'a'})")
        self.assertEqual(result['type'], 'INSERT')
        self.assertEqual(result['value'], 42.0)

    def test_insert_now(self):
        result = self.parser.parse("INSERT INTO metrics VALUES (NOW, 1.0)")
        self.assertIsNone(result['timestamp'])

    def test_select(self):
        result = self.parser.parse('SELECT * FROM metrics WHERE time > 0 AND time < 100 LIMIT 10')
        self.assertEqual(result['type'], 'SELECT')
        self.assertEqual(result['limit'], 10)

    def test_time_bucket(self):
        result = self.parser.parse("TIME_BUCKET('1h', metrics, avg)")
        self.assertEqual(result['type'], 'TIME_BUCKET')

    def test_downsample(self):
        result = self.parser.parse('DOWNSAMPLE metrics FROM 1h TO 1d WHERE time > 0 AND time < 100')
        self.assertEqual(result['type'], 'DOWNSAMPLE')

    def test_retention_apply(self):
        result = self.parser.parse('RETENTION POLICY APPLY metrics')
        self.assertEqual(result['type'], 'RETENTION_APPLY')

    def test_retention_show(self):
        result = self.parser.parse('RETENTION POLICY SHOW metrics')
        self.assertEqual(result['type'], 'RETENTION_SHOW')

    def test_first(self):
        result = self.parser.parse('FIRST metrics WHERE time > 0')
        self.assertEqual(result['type'], 'FIRST')

    def test_last(self):
        result = self.parser.parse('LAST metrics WHERE time < 100')
        self.assertEqual(result['type'], 'LAST')

    def test_hypertable_stats(self):
        result = self.parser.parse('HYPERTABLE STATS metrics')
        self.assertEqual(result['type'], 'HYPERTABLE_STATS')

    def test_list_hypertables(self):
        result = self.parser.parse('LIST HYPERTABLES')
        self.assertEqual(result['type'], 'LIST_HYPERTABLES')

    def test_unrelated(self):
        self.assertIsNone(self.parser.parse('SELECT 1'))

    def test_singleton(self):
        self.assertIs(get_timeseries_parser(), get_timeseries_parser())


if __name__ == '__main__':
    unittest.main()
