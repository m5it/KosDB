
"""
Batch Query Cache for KosDB v2.3.0

Provides query result caching within batch execution:
- SELECT result caching
- Cache hint syntax support
- Auto-invalidation on DML
- Cache warming
- Consistency management
- Metrics tracking
"""

import re
import time
import hashlib
import logging
from typing import Dict, Any, Optional, List, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class CachePolicy(Enum):
    """Cache policies for queries."""
    DEFAULT = "default"
    CACHE = "cache"
    NOCACHE = "nocache"
    WARM = "warm"


@dataclass
class CacheEntry:
    """Cached query result."""
    query_hash: str
    result: Any
    timestamp: float
    ttl_seconds: float
    table_deps: Set[str]
    hit_count: int = 0
    
    def is_expired(self) -> bool:
        """Check if cache entry is expired."""
        return time.time() - self.timestamp > self.ttl_seconds
    
    def mark_hit(self):
        """Record cache hit."""
        self.hit_count += 1


@dataclass
class CacheMetrics:
    """Metrics for batch query cache."""
    hits: int = 0
    misses: int = 0
    invalidations: int = 0
    evictions: int = 0
    warm_operations: int = 0
    
    @property
    def hit_ratio(self) -> float:
        """Calculate cache hit ratio."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class BatchQueryCache:
    """Query result cache for batch operations."""
    
    def __init__(
        self,
        default_ttl_seconds: float = 300.0,
        max_size: int = 1000
    ):
        self.default_ttl = default_ttl_seconds
        self.max_size = max_size
        self._cache: Dict[str, CacheEntry] = {}
        self._table_index: Dict[str, Set[str]] = {}
        self._metrics = CacheMetrics()
    
    def _hash_query(self, query: str, params: Optional[Tuple] = None) -> str:
        """Generate hash for query."""
        normalized = " ".join(query.split())
        if params:
            normalized += str(params)
        return hashlib.md5(normalized.encode()).hexdigest()[:16]
    
    def _extract_tables(self, query: str) -> Set[str]:
        """Extract table names from query."""
        tables = set()
        query_upper = query.upper()
        
        from_match = re.search(r'FROM\s+(\w+)', query_upper)
        if from_match:
            tables.add(from_match.group(1).lower())
        
        join_matches = re.findall(r'JOIN\s+(\w+)', query_upper)
        tables.update(t.lower() for t in join_matches)
        
        return tables
    
    def _parse_cache_hint(self, query: str) -> Tuple[str, CachePolicy]:
        """Parse cache hint from query."""
        if '/*+ CACHE */' in query.upper():
            return query.replace('/*+ CACHE */', '').strip(), CachePolicy.CACHE
        
        if '/*+ NOCACHE */' in query.upper():
            return query.replace('/*+ NOCACHE */', '').strip(), CachePolicy.NOCACHE
        
        if query.upper().startswith('WARM CACHE'):
            return query, CachePolicy.WARM
        
        return query, CachePolicy.DEFAULT
    
    def get(self, query: str, params: Optional[Tuple] = None) -> Optional[Any]:
        """Get cached result for query."""
        clean_query, policy = self._parse_cache_hint(query)
        
        if policy == CachePolicy.NOCACHE:
            return None
        
        query_hash = self._hash_query(clean_query, params)
        
        entry = self._cache.get(query_hash)
        if entry and not entry.is_expired():
            entry.mark_hit()
            self._metrics.hits += 1
            return entry.result
        
        self._metrics.misses += 1
        return None
    
    def put(
        self,
        query: str,
        result: Any,
        params: Optional[Tuple] = None,
        ttl: Optional[float] = None,
        table_deps: Optional[Set[str]] = None
    ):
        """Cache query result."""
        clean_query, policy = self._parse_cache_hint(query)
        
        if policy == CachePolicy.NOCACHE:
            return
        
        if table_deps is None:
            table_deps = self._extract_tables(clean_query)
        
        query_hash = self._hash_query(clean_query, params)
        
        if len(self._cache) >= self.max_size:
            self._evict_oldest()
        
        entry = CacheEntry(
            query_hash=query_hash,
            result=result,
            timestamp=time.time(),
            ttl_seconds=ttl or self.default_ttl,
            table_deps=table_deps
        )
        
        self._cache[query_hash] = entry
        
        for table in table_deps:
            if table not in self._table_index:
                self._table_index[table] = set()
            self._table_index[table].add(query_hash)
    
    def invalidate(self, tables: Set[str]):
        """Invalidate cache entries for tables."""
        for table in tables:
            if table in self._table_index:
                hashes_to_remove = self._table_index[table].copy()
                for query_hash in hashes_to_remove:
                    if query_hash in self._cache:
                        del self._cache[query_hash]
                        self._metrics.invalidations += 1
                
                del self._table_index[table]
    
    def invalidate_all(self):
        """Clear all cache entries."""
        count = len(self._cache)
        self._cache.clear()
        self._table_index.clear()
        self._metrics.invalidations += count
    
    def _evict_oldest(self):
        """Evict oldest cache entry."""
        if not self._cache:
            return
        
        oldest_hash = min(self._cache.keys(), key=lambda k: self._cache[k].timestamp)
        entry = self._cache.pop(oldest_hash)
        
        for table in entry.table_deps:
            if table in self._table_index:
                self._table_index[table].discard(oldest_hash)
        
        self._metrics.evictions += 1
    
    def warm_cache(self, query: str, executor: callable) -> bool:
        """Warm cache by executing query."""
        try:
            result = executor(query)
            self.put(query, result)
            self._metrics.warm_operations += 1
            return True
        except Exception as e:
            logger.error(f"Cache warm failed: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            'size': len(self._cache),
            'max_size': self.max_size,
            'hits': self._metrics.hits,
            'misses': self._metrics.misses,
            'hit_ratio': self._metrics.hit_ratio,
            'invalidations': self._metrics.invalidations,
            'evictions': self._metrics.evictions,
            'warm_operations': self._metrics.warm_operations,
        }
    
    def get_status(self) -> str:
        """Get human-readable cache status."""
        stats = self.get_stats()
        
        return f"""
========================================
BATCH QUERY CACHE STATUS
========================================
Cache Size:        {stats['size']} / {stats['max_size']}
Hit Ratio:         {stats['hit_ratio']:.2%}
Total Hits:        {stats['hits']}
Total Misses:      {stats['misses']}
Invalidations:     {stats['invalidations']}
Evictions:         {stats['evictions']}
Warm Operations:   {stats['warm_operations']}
========================================
"""


class BatchCacheManager:
    """Manager for batch-level query caching with auto-invalidation."""
    
    def __init__(self, cache: Optional[BatchQueryCache] = None):
        self.cache = cache or BatchQueryCache()
        self.dml_tables: Set[str] = set()
    
    def execute_with_cache(
        self,
        query: str,
        executor: callable,
        params: Optional[Tuple] = None
    ) -> Any:
        """Execute query with caching."""
        self._check_and_invalidate(query)
        
        cached = self.cache.get(query, params)
        if cached is not None:
            return cached
        
        result = executor(query)
        
        if self._is_select(query):
            self.cache.put(query, result, params)
        
        return result
    
    def _check_and_invalidate(self, query: str):
        """Check if query is DML and invalidate affected tables."""
        query_upper = query.upper().strip()
        
        is_dml = (
            query_upper.startswith('INSERT') or
            query_upper.startswith('UPDATE') or
            query_upper.startswith('DELETE') or
            query_upper.startswith('TRUNCATE')
        )
        
        if is_dml:
            tables = self.cache._extract_tables(query)
            if tables:
                self.cache.invalidate(tables)
                self.dml_tables.update(tables)
    
    def _is_select(self, query: str) -> bool:
        """Check if query is SELECT."""
        return query.upper().strip().startswith('SELECT')
    
    def warm_cache(self, query: str, executor: callable) -> bool:
        """Warm cache for query."""
        return self.cache.warm_cache(query, executor)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return self.cache.get_stats()
    
    def get_status(self) -> str:
        """Get cache status."""
        return self.cache.get_status()


# Global cache instance
_batch_cache = BatchQueryCache()


def get_batch_cache() -> BatchQueryCache:
    """Get global batch cache."""
    return _batch_cache


def parse_cache_hint(query: str) -> Tuple[str, bool]:
    """Parse cache hint from query."""
    if '/*+ CACHE */' in query.upper():
        return query.replace('/*+ CACHE */', '').strip(), True
    if '/*+ NOCACHE */' in query.upper():
        return query.replace('/*+ NOCACHE */', '').strip(), False
    return query, True
