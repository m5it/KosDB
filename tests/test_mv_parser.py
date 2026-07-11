#!/usr/bin/env python3
"""Unit tests for materialized view parser."""

import unittest
from mv_parser import MVParser, get_mv_parser


class TestMVParser(unittest.TestCase):
    def setUp(self):
        self.parser = MVParser()

    def test_create_view(self):
        result = self.parser.parse('CREATE MATERIALIZED VIEW mv1 AS SELECT * FROM users STRATEGY incremental SCHEDULE every_n_minutes INTERVAL 5')
        self.assertEqual(result['type'], 'CREATE_MATERIALIZED_VIEW')
        self.assertEqual(result['name'], 'mv1')
        self.assertEqual(result['refresh_strategy'], 'full')
    def test_drop_view(self):
        result = self.parser.parse('DROP MATERIALIZED VIEW mv1')
        self.assertEqual(result['type'], 'DROP_MATERIALIZED_VIEW')

    def test_refresh_view(self):
        result = self.parser.parse('REFRESH MATERIALIZED VIEW mv1 STRATEGY full')
        self.assertEqual(result['type'], 'REFRESH_MATERIALIZED_VIEW')

    def test_refresh_all(self):
        result = self.parser.parse('REFRESH ALL MATERIALIZED VIEWS')
        self.assertEqual(result['type'], 'REFRESH_ALL')

    def test_list_views(self):
        result = self.parser.parse('LIST MATERIALIZED VIEWS')
        self.assertEqual(result['type'], 'LIST_MATERIALIZED_VIEWS')

    def test_query_view(self):
        result = self.parser.parse('SELECT * FROM MV mv1')
        self.assertEqual(result['type'], 'QUERY_MATERIALIZED_VIEW')

    def test_set_schedule(self):
        result = self.parser.parse('SET REFRESH SCHEDULE mv1 SCHEDULE on_commit INTERVAL 10')
        self.assertEqual(result['type'], 'SET_REFRESH_SCHEDULE')

    def test_stats(self):
        result = self.parser.parse('MATERIALIZED VIEW STATS mv1')
        self.assertEqual(result['type'], 'MV_STATS')

    def test_unrelated(self):
        self.assertIsNone(self.parser.parse('SELECT 1'))

    def test_singleton(self):
        self.assertIs(get_mv_parser(), get_mv_parser())


if __name__ == '__main__':
    unittest.main()
