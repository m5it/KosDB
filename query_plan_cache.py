"""
Query Plan Cache for KosDB

Implements caching of parsed query plans with LRU eviction
and automatic invalidation on schema changes.
"""

import hashlib
import threading
import time
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field
from collections import OrderedDict
import logging

logger = logging.getLogger(__name__)


@dataclass
class CachedPlan:
    """Represents a cached query plan."""
    query_hash: str
    original_query: str
    parsed_plan: Any  # The parsed query structure
    table_dependencies: List[str]  # Tables this query depends on
    cache_time: float
    hit_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    
    def touch(self):
        """Update last accessed time and increment hit count."""
        self.last_accessed = time.time()
        self.hit_count += 1


class QueryPlanCache:
    """
    LRU cache for parsed query plans.
    
    Features:
    - Thread-safe operations
    - LRU eviction when capacity exceeded
    - Automatic invalidation on schema changes
    - Statistics tracking
    """
    
    def __init__(self, capacity: int = 1000, ttl: Optional[int] = None):
        """
        Initialize query plan cache.
        
        Args:
            capacity: Maximum number of cached plans
            ttl: Time-to-live in seconds (None for no expiration)
        """
        self.capacity = capacity
        self.ttl = ttl
        self._cache: OrderedDict[str, CachedPlan] = OrderedDict()
        self._table_index: Dict[str, set] = {}  # table_name -> set of query_hashes
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._invalidations = 0
    
    def _generate_hash(self, query: str) -> str:
        """Generate hash for query string."""
        return hashlib.sha256(query.strip().lower().encode()).hexdigest()
    
    def get(self, query: str) -> Optional[CachedPlan]:
        """
        Retrieve cached plan for query.
        
        Args:
            query: SQL query string
        
        Returns:
            CachedPlan if found and not expired, None otherwise
        """
        query_hash = self._generate_hash(query)
        
        with self._lock:
            if query_hash not in self._cache:
                self._misses += 1
                return None
            
            plan = self._cache[query_hash]
            
            # Check TTL
            if self.ttl and (time.time() - plan.cache_time) > self.ttl:
                self._evict(query_hash)
                self._misses += 1
                return None
            
            # Move to end (most recently used)
            self._cache.move_to_end(query_hash)
            plan.touch()
            self._hits += 1
            
            return plan
    
    def put(self, query: str, parsed_plan: Any, table_dependencies: List[str]) -> CachedPlan:
        """
        Store parsed plan in cache.
        
        Args:
            query: Original SQL query
            parsed_plan: Parsed query structure
            table_dependencies: List of tables this query depends on
        
        Returns:
            CachedPlan object
        """
        query_hash = self._generate_hash(query)
        
        with self._lock:
            # Evict if at capacity and not already present
            if len(self._cache) >= self.capacity and query_hash not in self._cache:
                self._evict_lru()
            
            plan = CachedPlan(
                query_hash=query_hash,
                original_query=query,
                parsed_plan=parsed_plan,
                table_dependencies=table_dependencies,
                cache_time=time.time()
            )
            
            self._cache[query_hash] = plan
            
            # Update table index
            for table in table_dependencies:
                if table not in self._table_index:
                    self._table_index[table] = set()
                self._table_index[table].add(query_hash)
            
            return plan
    
    def _evict(self, query_hash: str):
        """Evict specific plan from cache."""
        if query_hash in self._cache:
            plan = self._cache[query_hash]
            
            # Remove from table index
            for table in plan.table_dependencies:
                if table in self._table_index:
                    self._table_index[table].discard(query_hash)
                    if not self._table_index[table]:
                        del self._table_index[table]
            
            del self._cache[query_hash]
            self._evictions += 1
    
    def _evict_lru(self):
        """Evict least recently used plan."""
        if self._cache:
            oldest_hash, _ = self._cache.popitem(last=False)
            
            # Clean up table index
            for table, hashes in list(self._table_index.items()):
                hashes.discard(oldest_hash)
                if not hashes:
                    del self._table_index[table]
            
            self._evictions += 1
    
    def invalidate_table(self, table_name: str):
        """
        Invalidate all cached plans depending on a table.
        
        Args:
            table_name: Name of modified table
        """
        with self._lock:
            if table_name not in self._table_index:
                return
            
            hashes_to_remove = list(self._table_index[table_name])
            for query_hash in hashes_to_remove:
                self._evict(query_hash)
            
            self._invalidations += len(hashes_to_remove)
            logger.debug(f"Invalidated {len(hashes_to_remove)} plans for table {table_name}")
    
    def invalidate_all(self):
        """Clear entire cache."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._table_index.clear()
            self._invalidations += count
            logger.debug(f"Cleared entire cache ({count} plans)")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = self._hits / total_requests if total_requests > 0 else 0
            
            return {
                'size': len(self._cache),
                'capacity': self.capacity,
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': round(hit_rate, 4),
                'evictions': self._evictions,
                'invalidations': self._invalidations,
                'ttl': self.ttl
            }
    
    def enable(self):
        """Enable caching (no-op, cache is always enabled)."""
        pass
    
    def disable(self):
        """Disable caching by clearing all entries."""
        self.invalidate_all()


# Global cache instance
_query_plan_cache: Optional[QueryPlanCache] = None


def get_query_plan_cache() -> QueryPlanCache:
    """Get global query plan cache instance."""
    global _query_plan_cache
    if _query_plan_cache is None:
        _query_plan_cache = QueryPlanCache()
    return _query_plan_cache


def configure_query_plan_cache(capacity: int = 1000, ttl: Optional[int] = None):
    """
    Configure global query plan cache.
    
    Args:
        capacity: Maximum cached plans
        ttl: Time-to-live in seconds
    """
    global _query_plan_cache
    _query_plan_cache = QueryPlanCache(capacity=capacity, ttl=ttl)
