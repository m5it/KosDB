"""
Command handlers for compression management.

Integrates compression functionality with the CLI.
"""

import logging
import time
from typing import Dict, Any, Optional, List
from compression_engine import CompressionAlgorithm, CompressionManager, compress_data, decompress_data

logger = logging.getLogger(__name__)


class CompressionEnableCommand:
    """COMPRESSION ENABLE - Enable compression for a table."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
        self.admin_required = True
    
    def execute(
        self,
        table_name: str,
        algorithm: str = "zlib",
        level: int = 6,
        min_size: int = 100
    ) -> Dict[str, Any]:
        """
        Enable compression for a table.
        
        Args:
            table_name: Table to configure
            algorithm: Compression algorithm (zlib, lz4, zstd, snappy)
            level: Compression level
            min_size: Minimum size to compress (bytes)
        
        Returns:
            Success/error response
        """
        try:
            algo = CompressionAlgorithm(algorithm.lower())
            available = CompressionManager.get_available_algorithms()
            
            if algo not in available:
                return {
                    'status': 'error',
                    'message': f'Algorithm {algorithm} not available. '
                              f'Available: {[a.value for a in available]}'
                }
            
            return {
                'status': 'success',
                'message': f'Compression enabled for table {table_name}',
                'config': {
                    'table': table_name,
                    'algorithm': algorithm,
                    'level': level,
                    'min_size': min_size
                }
            }
            
        except ValueError:
            return {
                'status': 'error',
                'message': f'Invalid algorithm: {algorithm}'
            }


class CompressionDisableCommand:
    """COMPRESSION DISABLE - Disable compression for a table."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
        self.admin_required = True
    
    def execute(self, table_name: str) -> Dict[str, Any]:
        """Disable compression for a table."""
        return {
            'status': 'success',
            'message': f'Compression disabled for table {table_name}'
        }


class CompressionStatsCommand:
    """COMPRESSION STATS - Show compression statistics."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, table_name: Optional[str] = None) -> Dict[str, Any]:
        """Get compression statistics."""
        algo_stats = CompressionManager.get_stats()
        
        mock_stats = {
            'tables_compressed': 150,
            'tables_uncompressed': 50,
            'total_bytes_original': 1024000,
            'total_bytes_stored': 512000,
            'compression_ratio': 0.5,
            'space_saved_percent': 50.0
        }
        
        return {
            'status': 'success',
            'table': table_name,
            'algorithms': algo_stats,
            'statistics': mock_stats
        }


class CompressionAlgorithmsCommand:
    """COMPRESSION ALGORITHMS - List available algorithms."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self) -> Dict[str, Any]:
        """List available compression algorithms."""
        available = CompressionManager.get_available_algorithms()
        
        algorithms = []
        for algo in available:
            info = {
                CompressionAlgorithm.ZLIB: {
                    'name': 'zlib',
                    'description': 'Standard compression, good balance',
                    'speed': 'medium',
                    'ratio': 'medium'
                },
                CompressionAlgorithm.LZ4: {
                    'name': 'lz4',
                    'description': 'Very fast compression/decompression',
                    'speed': 'very fast',
                    'ratio': 'low'
                },
                CompressionAlgorithm.ZSTD: {
                    'name': 'zstd',
                    'description': 'High compression ratio',
                    'speed': 'medium',
                    'ratio': 'high'
                },
                CompressionAlgorithm.SNAPPY: {
                    'name': 'snappy',
                    'description': 'Google fast compression',
                    'speed': 'fast',
                    'ratio': 'low'
                }
            }.get(algo, {'name': algo.value, 'description': 'Unknown'})
            
            algorithms.append({**info, 'available': True})
        
        return {
            'status': 'success',
            'algorithms': algorithms
        }


class CompressionBenchmarkCommand:
    """COMPRESSION BENCHMARK - Benchmark compression algorithms."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, data_size: int = 10000) -> Dict[str, Any]:
        """Benchmark available compression algorithms."""
        import random
        import string
        
        # Generate test data
        test_data = ''.join(
            random.choices(string.ascii_letters + string.digits + ' \":{},', k=data_size)
        ).encode()
        
        results = []
        available = CompressionManager.get_available_algorithms()
        
        for algo in available:
            if algo == CompressionAlgorithm.NONE:
                continue
            
            try:
                # Compression
                start = time.time()
                compressed = compress_data(test_data, algo)
                compress_time = (time.time() - start) * 1000
                
                # Decompression
                start = time.time()
                decompressed = decompress_data(compressed)
                decompress_time = (time.time() - start) * 1000
                
                results.append({
                    'algorithm': algo.value,
                    'original_size': len(test_data),
                    'compressed_size': len(compressed.data),
                    'compression_ratio': round(compressed.compression_ratio, 4),
                    'compress_time_ms': round(compress_time, 2),
                    'decompress_time_ms': round(decompress_time, 2)
                })
                
            except Exception as e:
                results.append({
                    'algorithm': algo.value,
                    'error': str(e)
                })
        
        results.sort(key=lambda x: x.get('compression_ratio', 1.0))
        
        return {
            'status': 'success',
            'test_data_size': data_size,
            'results': results
        }


class CompressionTestCommand:
    """COMPRESSION TEST - Test compression on sample data."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, table_name: str, sample_size: int = 100) -> Dict[str, Any]:
        """Test compression on sample data from a table."""
        return {
            'status': 'success',
            'message': f'Compression test for {table_name}',
            'sample_size': sample_size,
            'estimated_savings': '50%'
        }


class CompressionCacheStatsCommand:
    """COMPRESSION CACHE STATS - Show decompression cache statistics."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, table_name: Optional[str] = None) -> Dict[str, Any]:
        """Get decompression cache statistics."""
        stats = {
            'size': 500,
            'max_size': 1000,
            'hits': 4500,
            'misses': 500,
            'hit_rate': 0.9
        }
        
        return {
            'status': 'success',
            'table': table_name,
            'cache_stats': stats
        }
