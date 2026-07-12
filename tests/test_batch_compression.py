
"""
Tests for Batch Response Compression
"""

import unittest
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from batch_compression import (
    BatchCompressor,
    CompressionConfig,
    CompressionAlgorithm,
    CompressionNegotiator,
    BatchCompressionManager,
)


class TestBatchCompressor(unittest.TestCase):
    """Test batch compression functionality."""
    
    def setUp(self):
        self.config = CompressionConfig(
            enabled=True,
            threshold_bytes=100,
            algorithm=CompressionAlgorithm.GZIP,
            compression_level=6
        )
        self.compressor = BatchCompressor(self.config)
    
    def test_compression_disabled(self):
        """Test compression when disabled."""
        config = CompressionConfig(enabled=False)
        compressor = BatchCompressor(config)
        
        data = b"x" * 1000
        result = compressor.compress(data)
        
        self.assertFalse(result['compressed'])
        self.assertEqual(result['algorithm'], 'none')
    
    def test_below_threshold(self):
        """Test data below threshold not compressed."""
        data = b"x" * 50
        result = self.compressor.compress(data)
        self.assertFalse(result['compressed'])
    
    def test_above_threshold(self):
        """Test data above threshold is compressed."""
        data = b"x" * 1000
        result = self.compressor.compress(data)
        self.assertTrue(result['compressed'])
        self.assertEqual(result['algorithm'], 'gzip')
    
    def test_decompress_gzip(self):
        """Test gzip decompression."""
        original = b"Test data" * 100
        result = self.compressor.compress(original, CompressionAlgorithm.GZIP)
        decompressed = self.compressor.decompress(result['data'], 'gzip')
        self.assertEqual(decompressed, original)


class TestCompressionNegotiator(unittest.TestCase):
    """Test compression negotiation."""
    
    def setUp(self):
        self.negotiator = CompressionNegotiator()
    
    def test_simple_negotiation(self):
        """Test simple algorithm negotiation."""
        preferences = ['gzip', 'lz4']
        result = self.negotiator.negotiate(preferences)
        self.assertEqual(result, 'gzip')
    
    def test_parse_accept_encoding(self):
        """Test parsing Accept-Encoding header."""
        header = "gzip, deflate;q=0.5, lz4;q=0.8"
        result = self.negotiator.parse_accept_encoding(header)
        self.assertEqual(result, ['gzip', 'deflate', 'lz4'])


class TestBatchCompressionManager(unittest.TestCase):
    """Test compression manager."""
    
    def setUp(self):
        self.manager = BatchCompressionManager()
    
    def test_compress_response(self):
        """Test response compression."""
        self.manager.configure(threshold_bytes=10)
        data = b"Test data" * 100
        result = self.manager.compress_response(data)
        self.assertTrue(result['compressed'])
    
    def test_decompress_response(self):
        """Test response decompression."""
        self.manager.configure(threshold_bytes=10)
        original = b"Test data for compression"
        compressed = self.manager.compress_response(original)
        decompressed = self.manager.decompress_response(
            compressed['data'],
            compressed['algorithm']
        )
        self.assertEqual(decompressed, original)


if __name__ == '__main__':
    unittest.main(verbosity=2)
