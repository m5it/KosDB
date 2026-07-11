"""
Query Result Cache for KosDB

Implements caching layer for query results with TTL support,
cache invalidation, and statistics tracking.
"""

import time
import hashlib
import threading
from typing import Dict, Any, Optional, List, Tuple, Callable
from dataclasses import dataclass, field
from collections import OrderedDict
import json


@dataclass
class CacheEntry:
    """Single cache entry."""
    key: str
    query: str  # Store query for invalidation matching
    result: Any
    created_at: float = field(default_factory=time.time)
    ttl: int = 300  # Time to live in seconds
    hit_count: int = 0
    
    @property
    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return time.time() - self.created_at > self.ttl
    
    @property
    def age(self) -> float:
        """Get entry age in seconds."""
        return time.time() - self.created_at


class QueryCache:
    """
    LRU cache for query results with TTL support.
    """
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._enabled = True
        
        # Statistics
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._invalidations = 0
    
    def _generate_key(self, query: str, params: Optional[Dict] = None) -> str:
        """Generate cache key from query and parameters."""
        key_data = query.lower().strip()
        if params:
            # Sort params for consistent key generation
            key_data += json.dumps(params, sort_keys=True)
        return hashlib.sha256(key_data.encode()).hexdigest()[:32]
    
    def get(self, query: str, params: Optional[Dict] = None) -> Optional[Any]:
        """
        Get cached result for query.
        
        Args:
            query: SQL query string
            params: Query parameters
        
        Returns:
            Cached result or None if not found/expired
        """
        if not self._enabled:
            return None
        
        key = self._generate_key(query, params)
        
        with self._lock:
            entry = self._cache.get(key)
            
            if entry is None:
                self._misses += 1
                return None
            
            if entry.is_expired:
                # Remove expired entry
                del self._cache[key]
                self._misses += 1
                return None
            
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            entry.hit_count += 1
            self._hits += 1
            
            return entry.result
    
    def put(self, query: str, result: Any, 
            params: Optional[Dict] = None,
            ttl: Optional[int] = None) -> bool:
        """
        Cache query result.
        
        Args:
            query: SQL query string
            result: Query result to cache
            params: Query parameters
            ttl: Time to live in seconds (uses default if None)
        
        Returns:
            True if cached successfully
        """
        if not self._enabled:
            return False
        
        key = self._generate_key(query, params)
        ttl = ttl or self.default_ttl
        
        with self._lock:
            # Evict oldest if at capacity
            while len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
                self._evictions += 1
            
            entry = CacheEntry(
                key=key,
                query=query,
                result=result,
                ttl=ttl
            )
            self._cache[key] = entry
        
        return True
    
    def invalidate(self, query_pattern: Optional[str] = None,
                   table_name: Optional[str] = None) -> int:
        """
        Invalidate cached entries.
        
        Args:
            query_pattern: Invalidate queries matching pattern
            table_name: Invalidate queries referencing table
        
        Returns:
            Number of entries invalidated
        """
        with self._lock:
            if query_pattern is None and table_name is None:
                # Clear all
                count = len(self._cache)
                self._cache.clear()
                self._invalidations += count
                return count
            
            # Pattern matching invalidation
            to_remove = []
            for key, entry in self._cache.items():
                # Check if query references the table
                query_upper = entry.query.upper()
                
                if table_name and table_name.upper() in query_upper:
                    to_remove.append(key)
                elif query_pattern and query_pattern.lower() in entry.query.lower():
                    to_remove.append(key)
            
            for key in to_remove:
                del self._cache[key]
            
            self._invalidations += len(to_remove)
            return len(to_remove)
    
    def invalidate_on_modify(self, table_name: str) -> int:
        """
        Invalidate cache entries for modified table.
        
        Args:
            table_name: Name of modified table
        
        Returns:
            Number of entries invalidated
        """
        return self.invalidate(table_name=table_name)
    
    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()
    
    def enable(self) -> None:
        """Enable caching."""
        self._enabled = True
    
    def disable(self) -> None:
        """Disable caching."""
        self._enabled = False
    
    def is_enabled(self) -> bool:
        """Check if caching is enabled."""
        return self._enabled
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = self._hits / total_requests if total_requests > 0 else 0
            
            return {
                'enabled': self._enabled,
                'size': len(self._cache),
                'max_size': self.max_size,
                'default_ttl': self.default_ttl,
                'hits': self._hits,
                'misses': self._misses,
                'evictions': self._evictions,
                'invalidations': self._invalidations,
                'hit_rate': round(hit_rate * 100, 2),
                'total_requests': total_requests,
                'memory_usage_estimate': len(self._cache) * 1024
            }
    
    def get_cached_queries(self) -> List[Dict[str, Any]]:
        """
        Get list of cached queries.
        
        Returns:
            List of cached query information
        """
        with self._lock:
            return [
                {
                    'key': entry.key,
                    'query': entry.query[:100],
                    'age': round(entry.age, 2),
                    'ttl': entry.ttl,
                    'hits': entry.hit_count,
                    'expired': entry.is_expired
                }
                for entry in self._cache.values()
            ]


class CachedQueryExecutor:
    """
    Query executor with caching support.
    """
    
    def __init__(self, db: Any, cache: Optional[QueryCache] = None):
        self.db = db
        self.cache = cache or QueryCache()
        self._original_execute = None
    
    def execute(self, query: str, params: Optional[Dict] = None,
                use_cache: bool = True) -> Any:
        """
        Execute query with caching.
        
        Args:
            query: SQL query
            params: Query parameters
            use_cache: Whether to use cache
        
        Returns:
            Query result
        """
        # Only cache SELECT queries
        is_select = query.strip().upper().startswith('SELECT')
        
        if use_cache and is_select and self.cache.is_enabled():
            # Try to get from cache
            cached = self.cache.get(query, params)
            if cached is not None:
                return cached
        
        # Execute query
        result = self._execute_query(query, params)
        
        # Cache if applicable
        if use_cache and is_select and self.cache.is_enabled():
            self.cache.put(query, result, params)
        
        return result
    
    def _execute_query(self, query: str, params: Optional[Dict] = None) -> Any:
        """Execute query against database."""
        # This would call the actual database execute method
        if hasattr(self.db, 'execute'):
            return self.db.execute(query, params)
        return None
    
    def invalidate_table(self, table_name: str) -> int:
        """Invalidate cache for table."""
        return self.cache.invalidate_on_modify(table_name)
    
    def wrap_db_execute(self):
        """
        Wrap database execute method with caching.
        
        Returns:
            Original execute method for restoration
        """
        if hasattr(self.db, 'execute'):
            self._original_execute = self.db.execute
            
            def cached_execute(query: str, **kwargs):
                return self.execute(query, kwargs.get('params'), 
                                  kwargs.get('use_cache', True))
            
            self.db.execute = cached_execute
            return self._original_execute
        
        return None
    
    def unwrap_db_execute(self):
        """Restore original execute method."""
        if self._original_execute and hasattr(self.db, 'execute'):
            self.db.execute = self._original_execute
            self._original_execute = None


# Global cache instance
_global_cache: Optional[QueryCache] = None


def get_global_cache() -> QueryCache:
    """Get or create global query cache."""
    global _global_cache
    if _global_cache is None:
        _global_cache = QueryCache()
    return _global_cache


def configure_cache(max_size: int = 1000, default_ttl: int = 300) -> QueryCache:
    """Configure global cache."""
    global _global_cache
    _global_cache = QueryCache(max_size=max_size, default_ttl=default_ttl)
    return _global_cache
