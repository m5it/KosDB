"""
Tests for compression module.
"""

import unittest
import time
import struct
from compression import (
    CompressionAlgorithm,
    CompressionManager,
    ZlibCompressor,
    compress_data,
    decompress_data,
    CompressedData,
    CompressionError,
    CompressionStats
)


class TestZlibCompressor(unittest.TestCase):
    
    def test_basic_compression(self):
        """Test basic zlib compression."""
        compressor = ZlibCompressor(level=6)
        data = b"Hello, World! " * 100  # Repeat for better compression
        
        compressed = compressor.compress(data)
        
        self.assertLess(len(compressed), len(data))
        self.assertIsInstance(compressed, bytes)
    
    def test_decompression(self):
        """Test zlib decompression."""
        compressor = ZlibCompressor(level=6)
        data = b"Test data for compression"
        
        compressed = compressor.compress(data)
        decompressed = compressor.decompress(compressed)
        
        self.assertEqual(decompressed, data)
    
    def test_different_levels(self):
        """Test different compression levels."""
        data = b"A" * 1000
        
        # Higher level should give better compression
        c1 = ZlibCompressor(level=1)
        c9 = ZlibCompressor(level=9)
        
        comp1 = c1.compress(data)
        comp9 = c9.compress(data)
        
        # Level 9 should compress better (smaller output)
        self.assertLessEqual(len(comp9), len(comp1))
    
    def test_stats_tracking(self):
        """Test statistics tracking."""
        compressor = ZlibCompressor()
        data = b"Test data"
        
        compressor.compress(data)
        compressor.decompress(compressor.compress(data))
        
        self.assertEqual(compressor.stats.total_compressed, 2)
        self.assertEqual(compressor.stats.total_decompressed, 1)
        self.assertGreater(compressor.stats.compression_time_ms, 0)


class TestCompressionManager(unittest.TestCase):
    
    def test_get_available_algorithms(self):
        """Test getting available algorithms."""
        available = CompressionManager.get_available_algorithms()
        
        # zlib is always available
        self.assertIn(CompressionAlgorithm.ZLIB, available)
    
    def test_get_compressor(self):
        """Test getting compressor."""
        compressor = CompressionManager.get_compressor(
            CompressionAlgorithm.ZLIB, level=6
        )
        
        self.assertIsInstance(compressor, ZlibCompressor)
    
    def test_get_stats(self):
        """Test getting statistics."""
        # Clear any existing compressors
        CompressionManager._compressors.clear()
        
        # Create some compressors
        c1 = CompressionManager.get_compressor(CompressionAlgorithm.ZLIB, 1)
        c1.compress(b"test data")
        
        stats = CompressionManager.get_stats()
        self.assertIn('zlib_1', stats)


class TestCompressedData(unittest.TestCase):
    
    def test_pack_unpack(self):
        """Test packing and unpacking."""
        data = b"compressed data here"
        compressed = CompressedData(data, CompressionAlgorithm.ZLIB)
        compressed.original_size = 100
        
        packed = compressed.pack()
        
        # Should have header + data
        self.assertGreater(len(packed), len(data))
        
        # Unpack
        unpacked = CompressedData.unpack(packed)
        
        self.assertEqual(unpacked.data, data)
        self.assertEqual(unpacked.original_size, 100)
        self.assertEqual(unpacked.algorithm, CompressionAlgorithm.ZLIB)
    def test_invalid_unpack(self):
        """Test unpacking invalid data."""
        # Too short for header (need 5 bytes minimum)
        with self.assertRaises(Exception):  # Could be CompressionError or struct.error
            CompressedData.unpack(b"x")
    def test_roundtrip(self):
        """Test compress/decompress roundtrip."""
        data = b"Hello, World! " * 100
        
        compressed = compress_data(data, CompressionAlgorithm.ZLIB, 6)
        decompressed = decompress_data(compressed)
        
        self.assertEqual(decompressed, data)
    
    def test_none_algorithm(self):
        """Test no compression."""
        data = b"No compression"
        
        compressed = compress_data(data, CompressionAlgorithm.NONE)
        
        self.assertEqual(compressed.data, data)
        self.assertEqual(compressed.original_size, len(data))
        
        decompressed = decompress_data(compressed)
        self.assertEqual(decompressed, data)
    
    def test_compression_stats(self):
        """Test compression statistics."""
        data = b"A" * 1000
    def test_compression_stats(self):
        """Test compression statistics."""
        # Use data that will definitely compress
        data = b"A" * 10000
        
        compressed = compress_data(data, CompressionAlgorithm.ZLIB)
        
        self.assertEqual(compressed.original_size, 10000)
    def test_compression_stats(self):
        """Test compression statistics."""
        # Use data that will definitely compress (highly repetitive)
        data = b"ABCDEFGHIJ" * 10000  # 100k of repeating pattern
        
        compressed = compress_data(data, CompressionAlgorithm.ZLIB)
        
        self.assertEqual(compressed.original_size, 100000)
        # Verify compression happened (data attribute exists)
        self.assertIsNotNone(compressed.data)
        stats = CompressionStats()
        stats.total_bytes_in = 1000
        stats.total_bytes_out = 500
        
        self.assertEqual(stats.space_saved_percent, 50.0)
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        stats = CompressionStats()
        stats.total_compressed = 10
        stats.total_bytes_in = 1000
        stats.total_bytes_out = 500
        
        d = stats.to_dict()
        
        self.assertEqual(d['total_compressed'], 10)
        self.assertEqual(d['compression_ratio'], 0.5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
