#!/usr/bin/env python3
"""Unit tests for prepared statement parser."""

import unittest
from prepared_statement_parser import PreparedStatementParser, get_prepared_parser


class TestPreparedStatementParser(unittest.TestCase):
    def setUp(self):
        self.parser = PreparedStatementParser()

    def test_prepare(self):
        result = self.parser.parse("PREPARE s1 AS 'SELECT * FROM users WHERE id = :id'")
        self.assertEqual(result['type'], 'PREPARE')
        self.assertEqual(result['statement_name'], 's1')

    def test_execute_named(self):
        result = self.parser.parse('EXECUTE s1(id => 123)')
        self.assertEqual(result['type'], 'EXECUTE')
        self.assertEqual(result['parameters']['id'], 123)

    def test_execute_using(self):
        result = self.parser.parse('EXECUTE s1 USING 123, "abc"')
        self.assertEqual(result['parameter_style'], 'positional')
        self.assertEqual(result['parameters'], [123, 'abc'])

    def test_execute_simple(self):
        result = self.parser.parse('EXECUTE s1')
        self.assertEqual(result['parameter_style'], 'none')

    def test_deallocate(self):
        result = self.parser.parse('DEALLOCATE s1')
        self.assertEqual(result['type'], 'DEALLOCATE')

    def test_deallocate_all(self):
        result = self.parser.parse('DEALLOCATE ALL')
        self.assertEqual(result['type'], 'DEALLOCATE_ALL')

    def test_show_prepared(self):
        result = self.parser.parse('SHOW PREPARED STATEMENTS')
        self.assertEqual(result['type'], 'SHOW_PREPARED')

    def test_cache_stats(self):
        result = self.parser.parse('SHOW CACHE STATS')
        self.assertEqual(result['type'], 'SHOW_CACHE_STATS')

    def test_cache_invalidate(self):
        result = self.parser.parse('CACHE INVALIDATE TABLE users')
        self.assertEqual(result['type'], 'CACHE_INVALIDATE')

    def test_unrelated(self):
        self.assertIsNone(self.parser.parse('SELECT 1'))

    def test_singleton(self):
        self.assertIs(get_prepared_parser(), get_prepared_parser())


if __name__ == '__main__':
    unittest.main()
