#!/usr/bin/env python3
"""Unit tests for compression parser."""

import unittest
from compression_parser import CompressionParser, get_compression_parser


class TestCompressionParser(unittest.TestCase):
    def setUp(self):
        self.parser = CompressionParser()

    def test_enable(self):
        result = self.parser.parse('COMPRESSION ENABLE users ALGORITHM zstd LEVEL 9 MIN_SIZE 200')
        self.assertEqual(result['type'], 'COMPRESSION_ENABLE')
        self.assertEqual(result['table_name'], 'users')
        self.assertEqual(result['algorithm'], 'zstd')
        self.assertEqual(result['level'], 9)
        self.assertEqual(result['min_size'], 200)

    def test_disable(self):
        result = self.parser.parse('COMPRESSION DISABLE users')
        self.assertEqual(result['type'], 'COMPRESSION_DISABLE')

    def test_stats(self):
        result = self.parser.parse('COMPRESSION STATS users')
        self.assertEqual(result['type'], 'COMPRESSION_STATS')

    def test_algorithms(self):
        result = self.parser.parse('COMPRESSION ALGORITHMS')
        self.assertEqual(result['type'], 'COMPRESSION_ALGORITHMS')

    def test_benchmark(self):
        result = self.parser.parse('COMPRESSION BENCHMARK DATA_SIZE 5000')
        self.assertEqual(result['data_size'], 5000)

    def test_test(self):
        result = self.parser.parse('COMPRESSION TEST users SAMPLE_SIZE 20')
        self.assertEqual(result['sample_size'], 20)

    def test_cache_stats(self):
        result = self.parser.parse('COMPRESSION CACHE STATS users')
        self.assertEqual(result['type'], 'COMPRESSION_CACHE_STATS')

    def test_unrelated_returns_none(self):
        self.assertIsNone(self.parser.parse('SELECT 1'))

    def test_singleton(self):
        self.assertIs(get_compression_parser(), get_compression_parser())


if __name__ == '__main__':
    unittest.main()
