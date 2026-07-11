"""
Data Compression Module for KosDB

Implements transparent data compression with support for multiple algorithms:
- LZ4: Fast compression/decompression
- Zstandard (zstd): High compression ratio
- Snappy: Google's fast compressor
- zlib: Standard compression
"""

import zlib
import struct
import logging
from enum import Enum
from typing import Optional, Dict, Any, Tuple, Union
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class CompressionAlgorithm(Enum):
    """Supported compression algorithms."""
    NONE = "none"
    LZ4 = "lz4"
    ZSTD = "zstd"
    SNAPPY = "snappy"
    ZLIB = "zlib"


class CompressionError(Exception):
    """Raised when compression operations fail."""
    pass


@dataclass
class CompressionStats:
    """Statistics for compression operations."""
    total_compressed: int = 0
    total_decompressed: int = 0
    total_bytes_in: int = 0
    total_bytes_out: int = 0
    compression_time_ms: float = 0.0
    decompression_time_ms: float = 0.0
    
    @property
    def compression_ratio(self) -> float:
        """Calculate compression ratio."""
        if self.total_bytes_in == 0:
            return 1.0
        return self.total_bytes_out / self.total_bytes_in
    
    @property
    def space_saved_percent(self) -> float:
        """Calculate space saved percentage."""
        if self.total_bytes_in == 0:
            return 0.0
        return (1.0 - self.compression_ratio) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'total_compressed': self.total_compressed,
            'total_decompressed': self.total_decompressed,
            'total_bytes_in': self.total_bytes_in,
            'total_bytes_out': self.total_bytes_out,
            'compression_ratio': round(self.compression_ratio, 4),
            'space_saved_percent': round(self.space_saved_percent, 2),
            'compression_time_ms': round(self.compression_time_ms, 2),
            'decompression_time_ms': round(self.decompression_time_ms, 2)
        }


class Compressor:
    """
    Base class for compression algorithms.
    """
    
    def __init__(self, level: int = 0):
        self.level = level
        self.stats = CompressionStats()
    
    def compress(self, data: bytes) -> bytes:
        """Compress data."""
        raise NotImplementedError
    
    def decompress(self, data: bytes) -> bytes:
        """Decompress data."""
        raise NotImplementedError
    
    def get_name(self) -> str:
        """Get compressor name."""
        raise NotImplementedError


class ZlibCompressor(Compressor):
    """zlib compression (built-in)."""
    
    def __init__(self, level: int = 6):
        super().__init__(level)
    
    def compress(self, data: bytes) -> bytes:
        import time
        start = time.time()
        
        compressed = zlib.compress(data, self.level)
        
        elapsed = (time.time() - start) * 1000
        self.stats.total_compressed += 1
        self.stats.total_bytes_in += len(data)
        self.stats.total_bytes_out += len(compressed)
        self.stats.compression_time_ms += elapsed
        
        return compressed
    
    def decompress(self, data: bytes) -> bytes:
        import time
        start = time.time()
        
        decompressed = zlib.decompress(data)
        
        elapsed = (time.time() - start) * 1000
        self.stats.total_decompressed += 1
        self.stats.decompression_time_ms += elapsed
        
        return decompressed
    
    def get_name(self) -> str:
        return "zlib"


class LZ4Compressor(Compressor):
    """LZ4 fast compression."""
    
    def __init__(self, level: int = 0):
        super().__init__(level)
        try:
            import lz4.frame
            self._lz4 = lz4.frame
        except ImportError:
            raise CompressionError("lz4 module not installed. Install with: pip install lz4")
    
    def compress(self, data: bytes) -> bytes:
        import time
        start = time.time()
        
        # LZ4 frame format with compression level
        compressed = self._lz4.compress(data, compression_level=self.level)
        
        elapsed = (time.time() - start) * 1000
        self.stats.total_compressed += 1
        self.stats.total_bytes_in += len(data)
        self.stats.total_bytes_out += len(compressed)
        self.stats.compression_time_ms += elapsed
        
        return compressed
    
    def decompress(self, data: bytes) -> bytes:
        import time
        start = time.time()
        
        decompressed = self._lz4.decompress(data)
        
        elapsed = (time.time() - start) * 1000
        self.stats.total_decompressed += 1
        self.stats.decompression_time_ms += elapsed
        
        return decompressed
    
    def get_name(self) -> str:
        return "lz4"


class ZstdCompressor(Compressor):
    """Zstandard compression (high ratio)."""
    
    def __init__(self, level: int = 3):
        super().__init__(level)
        try:
            import zstandard as zstd
            self._zstd = zstd
        except ImportError:
            raise CompressionError("zstandard module not installed. Install with: pip install zstandard")
    
    def compress(self, data: bytes) -> bytes:
        import time
        start = time.time()
        
        compressor = self._zstd.ZstdCompressor(level=self.level)
        compressed = compressor.compress(data)
        
        elapsed = (time.time() - start) * 1000
        self.stats.total_compressed += 1
        self.stats.total_bytes_in += len(data)
        self.stats.total_bytes_out += len(compressed)
        self.stats.compression_time_ms += elapsed
        
        return compressed
    
    def decompress(self, data: bytes) -> bytes:
        import time
        start = time.time()
        
        decompressor = self._zstd.ZstdDecompressor()
        decompressed = decompressor.decompress(data)
        
        elapsed = (time.time() - start) * 1000
        self.stats.total_decompressed += 1
        self.stats.decompression_time_ms += elapsed
        
        return decompressed
    
    def get_name(self) -> str:
        return "zstd"


class SnappyCompressor(Compressor):
    """Snappy fast compression."""
    
    def __init__(self, level: int = 0):
        super().__init__(level)
        try:
            import snappy
            self._snappy = snappy
        except ImportError:
            raise CompressionError("snappy module not installed. Install with: pip install python-snappy")
    
    def compress(self, data: bytes) -> bytes:
        import time
        start = time.time()
        
        compressed = self._snappy.compress(data)
        
        elapsed = (time.time() - start) * 1000
        self.stats.total_compressed += 1
        self.stats.total_bytes_in += len(data)
        self.stats.total_bytes_out += len(compressed)
        self.stats.compression_time_ms += elapsed
        
        return compressed
    
    def decompress(self, data: bytes) -> bytes:
        import time
        start = time.time()
        
        decompressed = self._snappy.decompress(data)
        
        elapsed = (time.time() - start) * 1000
        self.stats.total_decompressed += 1
        self.stats.decompression_time_ms += elapsed
        
        return decompressed
    
    def get_name(self) -> str:
        return "snappy"


class CompressionManager:
    """
    Manages compression algorithms and provides unified interface.
    """
    
    _compressors: Dict[str, Compressor] = {}
    
    @classmethod
    def get_compressor(cls, algorithm: CompressionAlgorithm, level: int = 0) -> Compressor:
        """
        Get or create compressor for algorithm.
        
        Args:
            algorithm: Compression algorithm
            level: Compression level (algorithm-specific)
        
        Returns:
            Compressor instance
        """
        key = f"{algorithm.value}_{level}"
        
        if key not in cls._compressors:
            if algorithm == CompressionAlgorithm.ZLIB:
                cls._compressors[key] = ZlibCompressor(level)
            elif algorithm == CompressionAlgorithm.LZ4:
                cls._compressors[key] = LZ4Compressor(level)
            elif algorithm == CompressionAlgorithm.ZSTD:
                cls._compressors[key] = ZstdCompressor(level)
            elif algorithm == CompressionAlgorithm.SNAPPY:
                cls._compressors[key] = SnappyCompressor(level)
            else:
                raise CompressionError(f"Unknown algorithm: {algorithm}")
        
        return cls._compressors[key]
    
    @classmethod
    def get_available_algorithms(cls) -> list:
        """Get list of available compression algorithms."""
        available = [CompressionAlgorithm.ZLIB]  # Always available
        
        try:
            import lz4.frame
            available.append(CompressionAlgorithm.LZ4)
        except ImportError:
            pass
        
        try:
            import zstandard
            available.append(CompressionAlgorithm.ZSTD)
        except ImportError:
            pass
        
        try:
            import snappy
            available.append(CompressionAlgorithm.SNAPPY)
        except ImportError:
            pass
        
        return available
    
    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """Get statistics for all compressors."""
        stats = {}
        for key, compressor in cls._compressors.items():
            stats[key] = compressor.stats.to_dict()
        return stats


class CompressedData:
    """
    Wrapper for compressed data with metadata.
    
    Format: [1 byte: algorithm ID][4 bytes: uncompressed size][compressed data]
    """
    
    ALGORITHM_IDS = {
        CompressionAlgorithm.ZLIB: 1,
        CompressionAlgorithm.LZ4: 2,
        CompressionAlgorithm.ZSTD: 3,
        CompressionAlgorithm.SNAPPY: 4,
    }
    
    ID_TO_ALGORITHM = {v: k for k, v in ALGORITHM_IDS.items()}
    
    def __init__(self, data: bytes, algorithm: CompressionAlgorithm):
        self.data = data
        self.algorithm = algorithm
        self.original_size: Optional[int] = None
    
    def pack(self) -> bytes:
        """Pack compressed data with header."""
        algo_id = self.ALGORITHM_IDS.get(self.algorithm, 0)
        if self.original_size is None:
            raise CompressionError("Original size not set")
        
        header = struct.pack('!BI', algo_id, self.original_size)
        return header + self.data
    
    @classmethod
    def unpack(cls, packed: bytes) -> 'CompressedData':
        """Unpack compressed data from header."""
        if len(packed) < 5:
            raise CompressionError("Invalid compressed data format")
        
        algo_id, original_size = struct.unpack('!BI', packed[:5])
        algorithm = cls.ID_TO_ALGORITHM.get(algo_id, CompressionAlgorithm.NONE)
        
        result = cls(packed[5:], algorithm)
        result.original_size = original_size
        return result
    
    @property
    def compression_ratio(self) -> float:
        """Calculate compression ratio."""
        if self.original_size is None or self.original_size == 0:
            return 1.0
        return len(self.data) / self.original_size


def compress_data(data: bytes, algorithm: CompressionAlgorithm, level: int = 0) -> CompressedData:
    """
    Compress data with specified algorithm.
    
    Args:
        data: Data to compress
        algorithm: Compression algorithm
        level: Compression level
    
    Returns:
        CompressedData object
    """
    if algorithm == CompressionAlgorithm.NONE:
        result = CompressedData(data, algorithm)
        result.original_size = len(data)
        return result
    
    compressor = CompressionManager.get_compressor(algorithm, level)
    compressed = compressor.compress(data)
    
    result = CompressedData(compressed, algorithm)
    result.original_size = len(data)
    return result


def decompress_data(compressed: CompressedData) -> bytes:
    """
    Decompress data.
    
    Args:
        compressed: CompressedData object
    
    Returns:
        Decompressed bytes
    """
    if compressed.algorithm == CompressionAlgorithm.NONE:
        return compressed.data
    
    compressor = CompressionManager.get_compressor(compressed.algorithm)
    return compressor.decompress(compressed.data)
