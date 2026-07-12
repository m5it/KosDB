
"""
Batch Response Compression for KosDB v2.3.0

Provides compression for large batch results:
- Configurable compression threshold
- Multiple compression algorithms (gzip, lz4)
- Client negotiation
- Automatic decompression
- Compression ratio tracking
"""

import gzip
import zlib
import logging
import time
from typing import Dict, Any, Optional, Union, List
from dataclasses import dataclass, field
from enum import Enum
import json

logger = logging.getLogger(__name__)


class CompressionAlgorithm(Enum):
    """Supported compression algorithms."""
    NONE = "none"
    GZIP = "gzip"
    LZ4 = "lz4"
    ZSTD = "zstd"


@dataclass
class CompressionConfig:
    """Configuration for batch compression."""
    enabled: bool = True
    threshold_bytes: int = 1024  # 1KB default
    algorithm: CompressionAlgorithm = CompressionAlgorithm.GZIP
    compression_level: int = 6  # 1-9 for gzip, 1-12 for lz4
    min_ratio: float = 0.1  # Minimum compression ratio to use compression
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'enabled': self.enabled,
            'threshold_bytes': self.threshold_bytes,
            'algorithm': self.algorithm.value,
            'compression_level': self.compression_level,
            'min_ratio': self.min_ratio,
        }


@dataclass
class CompressionStats:
    """Statistics for compression operations."""
    total_compressed: int = 0
    total_uncompressed: int = 0
    total_time_ms: float = 0
    algorithms_used: Dict[str, int] = field(default_factory=dict)
    
    @property
    def avg_compression_ratio(self) -> float:
        """Calculate average compression ratio."""
        if self.total_uncompressed == 0:
            return 0.0
        return 1.0 - (self.total_compressed / self.total_uncompressed)
    
    @property
    def avg_time_ms(self) -> float:
        """Calculate average compression time."""
        if self.total_compressed == 0:
            return 0.0
        total_ops = sum(self.algorithms_used.values())
        return self.total_time_ms / max(total_ops, 1)


class BatchCompressor:
    """
    Compressor for batch responses.
    
    Supports multiple algorithms and automatic selection
    based on content and client capabilities.
    """
    
    def __init__(self, config: Optional[CompressionConfig] = None):
        """
        Initialize compressor.
        
        Args:
            config: Compression configuration
        """
        self.config = config or CompressionConfig()
        self.stats = CompressionStats()
        self._lz4_available = self._check_lz4()
        self._zstd_available = self._check_zstd()
    
    def _check_lz4(self) -> bool:
        """Check if lz4 is available."""
        try:
            import lz4.frame
            return True
        except ImportError:
            return False
    
    def _check_zstd(self) -> bool:
        """Check if zstd is available."""
        try:
            import zstandard
            return True
        except ImportError:
            return False
    
    def compress(
        self,
        data: Union[str, bytes],
        algorithm: Optional[CompressionAlgorithm] = None,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Compress batch response data.
        
        Args:
            data: Data to compress
            algorithm: Specific algorithm to use (auto-select if None)
            force: Force compression even below threshold
        
        Returns:
            Dict with compressed data and metadata
        """
        if not self.config.enabled and not force:
            return {
                'data': data if isinstance(data, bytes) else data.encode('utf-8'),
                'compressed': False,
                'algorithm': 'none',
                'original_size': len(data) if isinstance(data, bytes) else len(data.encode('utf-8')),
                'compressed_size': len(data) if isinstance(data, bytes) else len(data.encode('utf-8')),
            }
        
        # Convert to bytes
        if isinstance(data, str):
            data = data.encode('utf-8')
        
        original_size = len(data)
        
        # Check threshold
        if original_size < self.config.threshold_bytes and not force:
            return {
                'data': data,
                'compressed': False,
                'algorithm': 'none',
                'original_size': original_size,
                'compressed_size': original_size,
            }
        
        # Select algorithm
        algo = algorithm or self.config.algorithm
        
        # Fall back to gzip if requested algorithm unavailable
        if algo == CompressionAlgorithm.LZ4 and not self._lz4_available:
            logger.warning("LZ4 not available, falling back to gzip")
            algo = CompressionAlgorithm.GZIP
        
        if algo == CompressionAlgorithm.ZSTD and not self._zstd_available:
            logger.warning("ZSTD not available, falling back to gzip")
            algo = CompressionAlgorithm.GZIP
        
        # Compress
        start_time = time.time()
        
        try:
            if algo == CompressionAlgorithm.GZIP:
                compressed = self._compress_gzip(data)
            elif algo == CompressionAlgorithm.LZ4:
                compressed = self._compress_lz4(data)
            elif algo == CompressionAlgorithm.ZSTD:
                compressed = self._compress_zstd(data)
            else:
                # No compression
                compressed = data
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            compressed_size = len(compressed)
            ratio = 1.0 - (compressed_size / original_size)
            
            # Check if compression is beneficial
            if ratio < self.config.min_ratio and not force:
                return {
                    'data': data,
                    'compressed': False,
                    'algorithm': 'none',
                    'original_size': original_size,
                    'compressed_size': original_size,
                    'reason': 'compression_ratio_too_low',
                }
            
            # Update stats
            self.stats.total_compressed += compressed_size
            self.stats.total_uncompressed += original_size
            self.stats.total_time_ms += elapsed_ms
            algo_name = algo.value
            self.stats.algorithms_used[algo_name] = self.stats.algorithms_used.get(algo_name, 0) + 1
            
            return {
                'data': compressed,
                'compressed': True,
                'algorithm': algo.value,
                'original_size': original_size,
                'compressed_size': compressed_size,
                'compression_ratio': ratio,
                'compression_time_ms': elapsed_ms,
            }
            
        except Exception as e:
            logger.error(f"Compression failed: {e}")
            # Return uncompressed on failure
            return {
                'data': data,
                'compressed': False,
                'algorithm': 'none',
                'original_size': original_size,
                'compressed_size': original_size,
                'error': str(e),
            }
    
    def decompress(self, data: bytes, algorithm: str) -> bytes:
        """
        Decompress batch response data.
        
        Args:
            data: Compressed data
            algorithm: Compression algorithm used
        
        Returns:
            Decompressed bytes
        """
        if algorithm == 'none' or not algorithm:
            return data
        
        try:
            if algorithm == 'gzip':
                return gzip.decompress(data)
            elif algorithm == 'lz4':
                if not self._lz4_available:
                    raise RuntimeError("LZ4 not available for decompression")
                import lz4.frame
                return lz4.frame.decompress(data)
            elif algorithm == 'zstd':
                if not self._zstd_available:
                    raise RuntimeError("ZSTD not available for decompression")
                import zstandard
                return zstandard.ZstdDecompressor().decompress(data)
            else:
                raise ValueError(f"Unknown compression algorithm: {algorithm}")
                
        except Exception as e:
            logger.error(f"Decompression failed: {e}")
            raise
    
    def _compress_gzip(self, data: bytes) -> bytes:
        """Compress using gzip."""
        return gzip.compress(data, compresslevel=self.config.compression_level)
    
    def _compress_lz4(self, data: bytes) -> bytes:
        """Compress using lz4."""
        import lz4.frame
        # LZ4 levels: 1-12, where 1 is fastest, 12 is best compression
        level = min(self.config.compression_level, 12)
        return lz4.frame.compress(data, compression_level=level)
    
    def _compress_zstd(self, data: bytes) -> bytes:
        """Compress using zstd."""
        import zstandard as zstd
        cctx = zstd.ZstdCompressor(level=self.config.compression_level)
        return cctx.compress(data)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get compression statistics."""
        return {
            'total_compressed': self.stats.total_compressed,
            'total_uncompressed': self.stats.total_uncompressed,
            'avg_compression_ratio': self.stats.avg_compression_ratio,
            'avg_time_ms': self.stats.avg_time_ms,
            'algorithms_used': self.stats.algorithms_used,
        }


class CompressionNegotiator:
    """
    Negotiate compression with clients.
    
    Handles accept-encoding style negotiation for
    optimal compression algorithm selection.
    """
    
    def __init__(self):
        self.supported_algorithms = ['gzip', 'lz4', 'zstd']
        self._check_availability()
    
    def _check_availability(self):
        """Check which algorithms are available."""
        try:
            import lz4.frame
        except ImportError:
            self.supported_algorithms.remove('lz4')
        
        try:
            import zstandard
        except ImportError:
            self.supported_algorithms.remove('zstd')
    
    def negotiate(self, client_preferences: List[str]) -> str:
        """
        Negotiate compression algorithm.
        
        Args:
            client_preferences: List of preferred algorithms (in order)
        
        Returns:
            Selected algorithm or 'none'
        """
        # Find first mutually supported algorithm
        for algo in client_preferences:
            algo = algo.lower().strip()
            if algo in self.supported_algorithms:
                return algo
            if algo == 'none' or algo == 'identity':
                return 'none'
        
        # Default to gzip if no match
        return 'gzip' if 'gzip' in self.supported_algorithms else 'none'
    
    def parse_accept_encoding(self, header: str) -> List[str]:
        """
        Parse Accept-Encoding style header.
        
        Args:
            header: Accept-Encoding header value
        
        Returns:
            List of algorithms in preference order
        """
        if not header:
            return ['none']
        
        # Parse "gzip, deflate;q=0.5, lz4;q=0.8"
        algorithms = []
        for part in header.split(','):
            part = part.strip()
            if ';' in part:
                algo = part.split(';')[0].strip()
            else:
                algo = part
            
            if algo:
                algorithms.append(algo)
        
        return algorithms if algorithms else ['none']


class BatchCompressionManager:
    """
    Manager for batch compression across the system.
    """
    
    def __init__(self):
        self.config = CompressionConfig()
        self.compressor = BatchCompressor(self.config)
        self.negotiator = CompressionNegotiator()
    
    def configure(
        self,
        enabled: Optional[bool] = None,
        threshold_bytes: Optional[int] = None,
        algorithm: Optional[str] = None,
        compression_level: Optional[int] = None
    ):
        """Configure compression settings."""
        if enabled is not None:
            self.config.enabled = enabled
        if threshold_bytes is not None:
            self.config.threshold_bytes = threshold_bytes
        if algorithm is not None:
            self.config.algorithm = CompressionAlgorithm(algorithm)
        if compression_level is not None:
            self.config.compression_level = compression_level
        
        # Recreate compressor with new config
        self.compressor = BatchCompressor(self.config)
    
    def compress_response(
        self,
        data: Union[str, bytes],
        client_encoding: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Compress response with client negotiation.
        
        Args:
            data: Response data
            client_encoding: Client's accepted encodings
        
        Returns:
            Compression result with metadata
        """
        if client_encoding:
            preferences = self.negotiator.parse_accept_encoding(client_encoding)
            algorithm_str = self.negotiator.negotiate(preferences)
            algorithm = CompressionAlgorithm(algorithm_str)
        else:
            algorithm = None  # Use default
        
        return self.compressor.compress(data, algorithm)
    
    def decompress_response(self, data: bytes, algorithm: str) -> bytes:
        """Decompress response."""
        return self.compressor.decompress(data, algorithm)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get compression statistics."""
        return self.compressor.get_stats()


# Global compression manager
_compression_manager = BatchCompressionManager()


def get_compression_manager() -> BatchCompressionManager:
    """Get global compression manager."""
    return _compression_manager


def compress_batch_response(
    data: Union[str, bytes],
    threshold: int = 1024,
    algorithm: str = 'gzip'
) -> Dict[str, Any]:
    """
    Convenience function to compress batch response.
    
    Args:
        data: Response data
        threshold: Compression threshold in bytes
        algorithm: Compression algorithm
    
    Returns:
        Compression result
    """
    manager = get_compression_manager()
    manager.configure(threshold_bytes=threshold, algorithm=algorithm)
    return manager.compress_response(data)


def decompress_batch_response(data: bytes, algorithm: str) -> bytes:
    """
    Convenience function to decompress batch response.
    
    Args:
        data: Compressed data
        algorithm: Algorithm used for compression
    
    Returns:
        Decompressed data
    """
    return get_compression_manager().decompress_response(data, algorithm)
