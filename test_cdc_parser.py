#!/usr/bin/env python3
"""Unit tests for CDC parser."""

import unittest
from cdc_parser import CDCParser, get_cdc_parser


class TestCDCParser(unittest.TestCase):
    def setUp(self):
        self.parser = CDCParser()

    def test_start_consumer_minimal(self):
        result = self.parser.parse('CDC START CONSUMER c1')
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'CDC_START_CONSUMER')
        self.assertEqual(result['consumer_id'], 'c1')
        self.assertEqual(result['format'], 'json')
        self.assertFalse(result['from_latest'])

    def test_start_consumer_full(self):
        result = self.parser.parse('CDC START CONSUMER c2 TABLES t1,t2 OPS INSERT,UPDATE FORMAT protobuf FROM_LATEST')
        self.assertEqual(result['tables'], 't1,t2')
        self.assertEqual(result['operations'], 'INSERT,UPDATE')
        self.assertEqual(result['format'], 'protobuf')
        self.assertTrue(result['from_latest'])

    def test_stop_consumer(self):
        result = self.parser.parse('CDC STOP CONSUMER c1')
        self.assertEqual(result['type'], 'CDC_STOP_CONSUMER')

    def test_list_consumers(self):
        result = self.parser.parse('CDC LIST CONSUMERS')
        self.assertEqual(result['type'], 'CDC_LIST_CONSUMERS')

    def test_stats(self):
        result = self.parser.parse('CDC STATS')
        self.assertEqual(result['type'], 'CDC_STATS')

    def test_setup_kafka(self):
        result = self.parser.parse('CDC SETUP KAFKA localhost:9092 PREFIX kosdb')
        self.assertEqual(result['type'], 'CDC_SETUP_KAFKA')
        self.assertEqual(result['bootstrap_servers'], 'localhost:9092')
        self.assertEqual(result['topic_prefix'], 'kosdb')

    def test_snapshot(self):
        result = self.parser.parse('CDC SNAPSHOT t1,t2')
        self.assertEqual(result['type'], 'CDC_SNAPSHOT')

    def test_non_cdc_returns_none(self):
        self.assertIsNone(self.parser.parse('SELECT * FROM t'))

    def test_get_cdc_parser_singleton(self):
        self.assertIs(get_cdc_parser(), get_cdc_parser())


if __name__ == '__main__':
    unittest.main()
