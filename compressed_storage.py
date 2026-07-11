"""
Compressed Storage Wrapper for KosDB

Wraps LevelDB storage with transparent compression/decompression.
Supports per-table compression configuration and decompression caching.
"""

import json
import threading
import logging
import time
from typing import Optional, Dict, Any, List, Union, Callable
from dataclasses import dataclass, field

from compression import (
    CompressionAlgorithm,
    CompressionManager,
    CompressedData,
    compress_data,
    decompress_data,
    CompressionError
)

logger = logging.getLogger(__name__)


@dataclass
class TableCompressionConfig:
    """Compression configuration for a table."""
    enabled: bool = False
    algorithm: CompressionAlgorithm = CompressionAlgorithm.ZLIB
    level: int = 6  # Compression level (algorithm-specific)
    min_size: int = 100  # Minimum size to compress (bytes)
    cache_decompressed: bool = True
    cache_size: int = 1000  # Max cached entries


class DecompressionCache:
    """
    LRU cache for decompressed data.
    
    Avoids repeated decompression of frequently accessed data.
    """
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._cache: Dict[str, Any] = {}
        self._access_order: List[str] = []
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached decompressed value."""
        with self._lock:
            if key in self._cache:
                # Move to end (most recently used)
                self._access_order.remove(key)
                self._access_order.append(key)
                self._hits += 1
                return self._cache[key]
            self._misses += 1
            return None
    
    def put(self, key: str, value: Any):
        """Cache decompressed value."""
        with self._lock:
            if key in self._cache:
                self._access_order.remove(key)
            elif len(self._cache) >= self.max_size:
                # Evict least recently used
                lru_key = self._access_order.pop(0)
                del self._cache[lru_key]
            
            self._cache[key] = value
            self._access_order.append(key)
    
    def invalidate(self, key: str):
        """Remove entry from cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._access_order.remove(key)
    
    def clear(self):
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()
            self._access_order.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0
            return {
                'size': len(self._cache),
                'max_size': self.max_size,
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': round(hit_rate, 4)
            }


class CompressedStorage:
    """
    LevelDB wrapper with transparent compression.
    
    Features:
    - Per-table compression configuration
    - Automatic compression ratio monitoring
    - Decompression caching
    - Transparent get/put operations
    """
    
    def __init__(self, db_path: str, compression_config: Optional[Dict] = None):
        """
        Initialize compressed storage.
        
        Args:
            db_path: Path to LevelDB database
            compression_config: Global compression settings
        """
        self.db_path = db_path
        self._db = None  # Would be initialized with plyvel
        self._table_configs: Dict[str, TableCompressionConfig] = {}
        self._decompression_caches: Dict[str, DecompressionCache] = {}
        self._global_stats = {
            'tables_compressed': 0,
            'tables_uncompressed': 0,
            'total_bytes_stored': 0,
            'total_bytes_original': 0
        }
        self._lock = threading.RLock()
        
        # Initialize default config
        self._default_config = TableCompressionConfig(
            enabled=compression_config.get('enabled', False) if compression_config else False,
            algorithm=CompressionAlgorithm(compression_config.get('algorithm', 'zlib')) if compression_config else CompressionAlgorithm.ZLIB,
            level=compression_config.get('level', 6) if compression_config else 6
        )
        
        logger.info(f"CompressedStorage initialized for {db_path}")
    
    def configure_table(
        self,
        table_name: str,
        enabled: bool = True,
        algorithm: str = "zlib",
        level: int = 6,
        min_size: int = 100,
        cache_decompressed: bool = True
    ):
        """
        Configure compression for a table.
        
        Args:
            table_name: Table to configure
            enabled: Enable compression
            algorithm: Compression algorithm name
            level: Compression level
            min_size: Minimum size to compress
            cache_decompressed: Cache decompressed values
        """
        with self._lock:
            algo = CompressionAlgorithm(algorithm.lower()) if enabled else CompressionAlgorithm.NONE
            
            config = TableCompressionConfig(
                enabled=enabled,
                algorithm=algo,
                level=level,
                min_size=min_size,
                cache_decompressed=cache_decompressed
            )
            
            self._table_configs[table_name] = config
            
            if cache_decompressed:
                self._decompression_caches[table_name] = DecompressionCache(
                    max_size=config.cache_size
                )
            
            logger.info(f"Configured compression for table {table_name}: "
                       f"{algorithm if enabled else 'disabled'}")
    
    def _get_config(self, table_name: str) -> TableCompressionConfig:
        """Get compression config for table."""
        return self._table_configs.get(table_name, self._default_config)
    
    def _get_cache(self, table_name: str) -> Optional[DecompressionCache]:
        """Get decompression cache for table."""
        return self._decompression_caches.get(table_name)
    
    def put(self, table_name: str, key: str, value: bytes) -> Dict[str, Any]:
        """
        Store value with optional compression.
        
        Args:
            table_name: Target table
            key: Record key
            value: Data to store
        
        Returns:
            Storage metadata including compression info
        """
        config = self._get_config(table_name)
        
        metadata = {
            'table': table_name,
            'key': key,
            'original_size': len(value),
            'compressed': False,
            'algorithm': None,
            'stored_size': len(value)
        }
        
        if config.enabled and len(value) >= config.min_size:
            try:
                compressed = compress_data(value, config.algorithm, config.level)
                packed = compressed.pack()
                
                metadata['compressed'] = True
                metadata['algorithm'] = config.algorithm.value
                metadata['stored_size'] = len(packed)
                metadata['compression_ratio'] = compressed.compression_ratio
                
                # Update global stats
                self._global_stats['tables_compressed'] += 1
                self._global_stats['total_bytes_stored'] += len(packed)
                self._global_stats['total_bytes_original'] += len(value)
                
                # Store compressed
                storage_key = self._make_key(table_name, key)
                # Would write to LevelDB: self._db.put(storage_key, packed)
                logger.debug(f"Stored compressed: {key} ({len(value)} -> {len(packed)} bytes, "
                           f"ratio: {compressed.compression_ratio:.2f})")
                
                return metadata
            
            except CompressionError as e:
                logger.warning(f"Compression failed for {key}, storing uncompressed: {e}")
        
        # Store uncompressed
        storage_key = self._make_key(table_name, key)
        # Would write to LevelDB: self._db.put(storage_key, value)
        
        self._global_stats['tables_uncompressed'] += 1
        self._global_stats['total_bytes_stored'] += len(value)
        self._global_stats['total_bytes_original'] += len(value)
        
        logger.debug(f"Stored uncompressed: {key} ({len(value)} bytes)")
        return metadata
    
    def get(self, table_name: str, key: str) -> Optional[bytes]:
        """
        Retrieve value with automatic decompression.
        
        Args:
            table_name: Source table
            key: Record key
        
        Returns:
            Decompressed value or None if not found
        """
        config = self._get_config(table_name)
        
        # Check cache first
        cache = self._get_cache(table_name)
        if cache:
            cached = cache.get(key)
            if cached is not None:
                logger.debug(f"Cache hit for {key}")
                return cached
        
        # Retrieve from storage
        storage_key = self._make_key(table_name, key)
        # Would read from LevelDB: data = self._db.get(storage_key)
        data = None  # Placeholder
        
        if data is None:
            return None
        
        # Check if compressed (has header)
        if len(data) >= 5 and data[0] in CompressedData.ID_TO_ALGORITHM:
            try:
                compressed = CompressedData.unpack(data)
                value = decompress_data(compressed)
                
                # Cache decompressed value
                if cache and config.cache_decompressed:
                    cache.put(key, value)
                
                logger.debug(f"Decompressed {key}: {len(data)} -> {len(value)} bytes")
                return value
                
            except (CompressionError, Exception) as e:
                logger.error(f"Decompression failed for {key}: {e}")
                return None
        
        # Uncompressed data
        if cache and config.cache_decompressed:
            cache.put(key, data)
        
        return data
    
    def delete(self, table_name: str, key: str):
        """Delete a key from storage."""
        # Invalidate cache
        cache = self._get_cache(table_name)
        if cache:
            cache.invalidate(key)
        
        # Delete from storage
        storage_key = self._make_key(table_name, key)
        # Would delete from LevelDB: self._db.delete(storage_key)
        logger.debug(f"Deleted {key} from {table_name}")
    
    def _make_key(self, table_name: str, key: str) -> str:
        """Create storage key with table prefix."""
        return f"{table_name}:{key}"
    
    def get_stats(self, table_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get compression statistics.
        
        Args:
            table_name: Specific table or all tables
        
        Returns:
            Statistics dictionary
        """
        with self._lock:
            if table_name:
                config = self._get_config(table_name)
                cache = self._get_cache(table_name)
                
                return {
                    'table': table_name,
                    'compression_enabled': config.enabled,
                    'algorithm': config.algorithm.value if config.enabled else None,
                    'cache_stats': cache.get_stats() if cache else None
                }
            else:
                # Global stats
                total_savings = (self._global_stats['total_bytes_original'] - 
                               self._global_stats['total_bytes_stored'])
                
                compression_stats = CompressionManager.get_stats()
                
                return {
                    'global': self._global_stats,
                    'total_space_saved': total_savings,
                    'average_compression_ratio': (
                        self._global_stats['total_bytes_stored'] / 
                        self._global_stats['total_bytes_original']
                        if self._global_stats['total_bytes_original'] > 0 else 1.0
                    ),
                    'compression_algorithms': compression_stats,
                    'configured_tables': list(self._table_configs.keys())
                }
    
    def get_available_algorithms(self) -> List[str]:
        """Get list of available compression algorithms."""
        return [algo.value for algo in CompressionManager.get_available_algorithms()]
    
    def close(self):
        """Close storage and cleanup."""
        with self._lock:
            # Clear all caches
            for cache in self._decompression_caches.values():
                cache.clear()
            self._decompression_caches.clear()
            
            # Close database
            if self._db:
                # self._db.close()
                pass
            
            logger.info("CompressedStorage closed")


class CompressionMonitor:
    """
    Monitor compression efficiency and recommend optimizations.
    """
    
    def __init__(self, storage: CompressedStorage):
        self.storage = storage
        self._recommendations: List[str] = []
    
    def analyze_table(self, table_name: str) -> Dict[str, Any]:
        """
        Analyze compression efficiency for a table.
        
        Returns:
            Analysis results with recommendations
        """
        stats = self.storage.get_stats(table_name)
        
        recommendations = []
        
        # Check if compression is enabled
        if not stats['compression_enabled']:
            recommendations.append(f"Consider enabling compression for table {table_name}")
        
        # Check cache hit rate
        if stats['cache_stats']:
            cache_hit_rate = stats['cache_stats']['hit_rate']
            if cache_hit_rate < 0.5:
                recommendations.append(f"Low cache hit rate ({cache_hit_rate:.1%}), consider adjusting cache size")
            elif cache_hit_rate > 0.95:
                recommendations.append(f"Very high cache hit rate, cache size may be larger than needed")
        
        return {
            'table': table_name,
            'stats': stats,
            'recommendations': recommendations
        }
    
    def get_all_recommendations(self) -> List[str]:
        """Get recommendations for all tables."""
        all_stats = self.storage.get_stats()
        recommendations = []
        
        for table in all_stats.get('configured_tables', []):
            analysis = self.analyze_table(table)
            recommendations.extend(analysis['recommendations'])
        
        return recommendations
