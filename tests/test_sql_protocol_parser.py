#!/usr/bin/env python3
"""Unit tests for SQL protocol parser."""

import unittest
from sql_protocol_parser import SQLProtocolParser, get_sql_protocol_parser


class TestSQLProtocolParser(unittest.TestCase):
    def setUp(self):
        self.parser = SQLProtocolParser()

    def test_show_status(self):
        result = self.parser.parse('SHOW PROTOCOL STATUS')
        self.assertEqual(result['type'], 'SHOW_PROTOCOL_STATUS')

    def test_set_port(self):
        result = self.parser.parse('SET PROTOCOL postgres PORT 5433')
        self.assertEqual(result['type'], 'SET_PROTOCOL_PORT')
        self.assertEqual(result['port'], '5433')

    def test_enable(self):
        result = self.parser.parse('ENABLE PROTOCOL mysql')
        self.assertEqual(result['type'], 'ENABLE_PROTOCOL')

    def test_disable(self):
        result = self.parser.parse('DISABLE PROTOCOL postgres')
        self.assertEqual(result['type'], 'DISABLE_PROTOCOL')

    def test_unrelated(self):
        self.assertIsNone(self.parser.parse('SELECT 1'))

    def test_singleton(self):
        self.assertIs(get_sql_protocol_parser(), get_sql_protocol_parser())


if __name__ == '__main__':
    unittest.main()
