"""
Query Cache with Invalidation for KosDB

Provides query result caching with multiple invalidation strategies:
time-based, table-based, and manual invalidation.
"""

import time
import json
import hashlib
import threading
from typing import Dict, Any, List, Optional, Tuple, Callable, Set
from dataclasses import dataclass, field
from enum import Enum, auto
from collections import OrderedDict


class CacheStrategy(Enum):
    """Cache invalidation strategies."""
    TIME_TO_LIVE = auto()      # Expire after fixed time
    WRITE_INVALIDATE = auto()  # Invalidate on any write
    TABLE_VERSION = auto()     # Track table versions
    MANUAL = auto()            # Manual invalidation only


@dataclass
class CacheEntry:
    """Represents a cached query result."""
    key: str
    query: str
    result: Any
    tables: Set[str]           # Tables involved in query
    created_at: float
    ttl: Optional[float]       # Time to live in seconds
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    
    def is_expired(self) -> bool:
        """Check if entry has expired."""
        if self.ttl is None:
            return False
        return time.time() - self.created_at > self.ttl
    
    def touch(self):
        """Update access metadata."""
        self.last_accessed = time.time()
        self.access_count += 1
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'key': self.key,
            'query': self.query[:100] + '...' if len(self.query) > 100 else self.query,
            'tables': list(self.tables),
            'created_at': self.created_at,
            'expires_at': self.created_at + self.ttl if self.ttl else None,
            'access_count': self.access_count,
            'last_accessed': self.last_accessed,
            'expired': self.is_expired()
        }


class QueryCache:
    """
    Thread-safe query cache with multiple invalidation strategies.
    Supports LRU eviction and size limits.
    """
    
    def __init__(self, max_size: int = 1000,
                 default_ttl: Optional[float] = 300.0,  # 5 minutes
                 strategy: CacheStrategy = CacheStrategy.TIME_TO_LIVE):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.strategy = strategy
        
        # Main cache storage: key -> CacheEntry
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        
        # Table index: table_name -> set of cache keys
        self._table_index: Dict[str, Set[str]] = {}
        
        # Table versions for TABLE_VERSION strategy
        self._table_versions: Dict[str, int] = {}
        
        # Statistics
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._invalidations = 0
        
        self._lock = threading.RLock()
        self._cleanup_thread: Optional[threading.Thread] = None
        self._shutdown = False
    
    def start(self):
        """Start background cleanup thread."""
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop)
        self._cleanup_thread.daemon = True
        self._cleanup_thread.start()
    
    def stop(self):
        """Stop background cleanup."""
        self._shutdown = True
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=2.0)
    
    def _cleanup_loop(self):
        """Background thread to clean expired entries."""
        while not self._shutdown:
            time.sleep(60.0)  # Run every minute
            self._remove_expired()
    
    def _generate_key(self, query: str, params: Optional[Dict] = None) -> str:
        """
        Generate cache key from query and parameters.
        
        Args:
            query: SQL query string
            params: Query parameters
        
        Returns:
            Cache key string
        """
        # Normalize query
        normalized = ' '.join(query.split()).lower()
        
        # Include params in key
        if params:
            key_data = f"{normalized}:{json.dumps(params, sort_keys=True)}"
        else:
            key_data = normalized
        
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _extract_tables(self, query: str) -> Set[str]:
        """
        Extract table names from query.
        Simple implementation - can be enhanced with SQL parser.
        """
        tables = set()
        query_upper = query.upper()
        
        # Look for FROM clause
        import re
        from_match = re.search(r'FROM\s+(\w+)', query_upper)
        if from_match:
            tables.add(from_match.group(1).lower())
        
        # Look for JOIN clauses
        join_matches = re.findall(r'JOIN\s+(\w+)', query_upper)
        tables.update(m.lower() for m in join_matches)
        
        # Look for INTO clause (INSERT)\n        into_match = re.search(r'INTO\\s+(\\w+)', query_upper)\n        if into_match:\n            tables.add(into_match.group(1).lower())\n        \n        # Look for UPDATE\n        update_match = re.search(r'UPDATE\\s+(\\w+)', query_upper)\n        if update_match:\n            tables.add(update_match.group(1).lower())\n        \n        return tables\n    \n    def get(self, query: str, \n            params: Optional[Dict] = None,\n            tables: Optional[Set[str]] = None) -> Optional[Any]:\n        \"\"\"\n        Get cached result for query.\n        \n        Args:\n            query: SQL query\n            params: Query parameters\n            tables: Tables involved (auto-detected if not provided)\n        \n        Returns:\n            Cached result or None if not found/expired\n        \"\"\"\n        key = self._generate_key(query, params)\n        \n        with self._lock:\n            entry = self._cache.get(key)\n            \n            if entry is None:\n                self._misses += 1\n                return None\n            \n            # Check expiration\n            if entry.is_expired():\n                self._remove_entry(key)\n                self._misses += 1\n                return None\n            \n            # Check table versions for TABLE_VERSION strategy\n            if self.strategy == CacheStrategy.TABLE_VERSION:\n                for table in entry.tables:\n                    current_version = self._table_versions.get(table, 0)\n                    if current_version != getattr(entry, 'table_version', 0):\n                        self._remove_entry(key)\n                        self._misses += 1\n                        return None\n            \n            # Cache hit\n            entry.touch()\n            self._hits += 1\n            \n            # Move to end (most recently used)\n            self._cache.move_to_end(key)\n            \n            return entry.result\n    \n    def put(self, query: str,\n            result: Any,\n            params: Optional[Dict] = None,\n            tables: Optional[Set[str]] = None,\n            ttl: Optional[float] = None) -> str:\n        \"\"\"\n        Cache query result.\n        \n        Args:\n            query: SQL query\n            result: Query result to cache\n            params: Query parameters\n            tables: Tables involved (auto-detected if not provided)\n            ttl: Time to live (uses default if not specified)\n        \n        Returns:\n            Cache key\n        \"\"\"\n        key = self._generate_key(query, params)\n        \n        if tables is None:\n            tables = self._extract_tables(query)\n        \n        if ttl is None:\n            ttl = self.default_ttl\n        \n        entry = CacheEntry(\n            key=key,\n            query=query,\n            result=result,\n            tables=tables,\n            created_at=time.time(),\n            ttl=ttl\n        )\n        \n        # Store table version for TABLE_VERSION strategy\n        if self.strategy == CacheStrategy.TABLE_VERSION:\n            entry.table_version = max(\n                self._table_versions.get(t, 0) for t in tables\n            ) if tables else 0\n        \n        with self._lock:\n            # Check size limit and evict if necessary\n            while len(self._cache) >= self.max_size:\n                self._evict_lru()\n            \n            # Store entry\n            self._cache[key] = entry\n            \n            # Update table index\n            for table in tables:\n                if table not in self._table_index:\n                    self._table_index[table] = set()\n                self._table_index[table].add(key)\n        \n        return key\n    \n    def invalidate(self, key: str) -> bool:\n        \"\"\"\n        Invalidate specific cache entry.\n        \n        Args:\n            key: Cache key\n        \n        Returns:\n            True if entry was found and removed\n        \"\"\"\n        with self._lock:\n            if key in self._cache:\n                self._remove_entry(key)\n                self._invalidations += 1\n                return True\n            return False\n    \n    def invalidate_table(self, table: str) -> int:\n        \"\"\"\n        Invalidate all entries for a table.\n        \n        Args:\n            table: Table name\n        \n        Returns:\n            Number of entries invalidated\n        \"\"\"\n        with self._lock:\n            keys = self._table_index.get(table, set()).copy()\n            \n            for key in keys:\n                self._remove_entry(key)\n            \n            # Increment table version\n            self._table_versions[table] = self._table_versions.get(table, 0) + 1\n            \n            self._invalidations += len(keys)\n            return len(keys)\n    \n    def invalidate_all(self) -> int:\n        \"\"\"\n        Invalidate all cache entries.\n        \n        Returns:\n            Number of entries invalidated\n        \"\"\"\n        with self._lock:\n            count = len(self._cache)\n            self._cache.clear()\n            self._table_index.clear()\n            self._invalidations += count\n            return count\n    \n    def invalidate_pattern(self, pattern: str) -> int:\n        \"\"\"\n        Invalidate entries matching query pattern.\n        \n        Args:\n            pattern: Query pattern to match\n        \n        Returns:\n            Number of entries invalidated\n        \"\"\"\n        import re\n        regex = re.compile(pattern, re.IGNORECASE)\n        \n        with self._lock:\n            to_remove = [\n                key for key, entry in self._cache.items()\n                if regex.search(entry.query)\n            ]\n            \n            for key in to_remove:\n                self._remove_entry(key)\n            \n            self._invalidations += len(to_remove)\n            return len(to_remove)\n    \n    def _remove_entry(self, key: str):\n        \"\"\"Remove entry from cache and indexes.\"\"\"\n        entry = self._cache.pop(key, None)\n        if entry:\n            for table in entry.tables:\n                if table in self._table_index:\n                    self._table_index[table].discard(key)\n                    if not self._table_index[table]:\n                        del self._table_index[table]\n    \n    def _evict_lru(self):\n        \"\"\"Evict least recently used entry.\"\"\"\n        if self._cache:\n            key, _ = self._cache.popitem(last=False)\n            self._evictions += 1\n            \n            # Clean up table index\n            entry = self._cache.get(key)\n            if entry:\n                for table in entry.tables:\n                    if table in self._table_index:\n                        self._table_index[table].discard(key)\n    \n    def _remove_expired(self) -> int:\n        \"\"\"Remove all expired entries.\"\"\"\n        with self._lock:\n            expired = [\n                key for key, entry in self._cache.items()\n                if entry.is_expired()\n            ]\n            \n            for key in expired:\n                self._remove_entry(key)\n            \n            return len(expired)\n    \n    def get_stats(self) -> Dict[str, Any]:\n        \"\"\"Get cache statistics.\"\"\"\n        with self._lock:\n            total = len(self._cache)\n            total_requests = self._hits + self._misses\n            \n            return {\n                'size': total,\n                'max_size': self.max_size,\n                'utilization': total / self.max_size if self.max_size > 0 else 0,\n                'hits': self._hits,\n                'misses': self._misses,\n                'hit_rate': self._hits / total_requests if total_requests > 0 else 0,\n                'evictions': self._evictions,\n                'invalidations': self._invalidations,\n                'strategy': self.strategy.name,\n                'default_ttl': self.default_ttl,\n                'tables_tracked': len(self._table_index)\n            }\n    \n    def get_entry_info(self, key: str) -> Optional[Dict[str, Any]]:\n        \"\"\"Get information about specific cache entry.\"\"\"\n        with self._lock:\n            entry = self._cache.get(key)\n            return entry.to_dict() if entry else None\n    \n    def list_entries(self, table: Optional[str] = None) -> List[Dict[str, Any]]:\n        \"\"\"List cache entries.\"\"\"\n        with self._lock:\n            if table:\n                keys = self._table_index.get(table, set())\n            else:\n                keys = self._cache.keys()\n            \n            return [self._cache[k].to_dict() for k in keys if k in self._cache]\n\n\nclass CachedQueryExecutor:\n    \"\"\"\n    Query executor with transparent caching.\n    Wraps existing executor with cache layer.\n    \"\"\"\n    \n    def __init__(self, executor: Any, cache: Optional[QueryCache] = None):\n        self.executor = executor\n        self.cache = cache or QueryCache()\n        self.cache.start()\n    \n    def execute(self, query: str, \n                params: Optional[Dict] = None,\n                use_cache: bool = True,\n                cache_ttl: Optional[float] = None) -> Any:\n        \"\"\"\n        Execute query with caching.\n        \n        Args:\n            query: SQL query\n            params: Query parameters\n            use_cache: Whether to use cache\n            cache_ttl: Custom TTL for this query\n        \n        Returns:\n            Query result\n        \"\"\"\n        if not use_cache:\n            return self.executor.execute(query, params)\n        \n        # Try to get from cache\n        cached = self.cache.get(query, params)\n        if cached is not None:\n            return cached\n        \n        # Execute query\n        result = self.executor.execute(query, params)\n        \n        # Cache result (only for SELECT queries)\n        if query.strip().upper().startswith('SELECT'):\n            self.cache.put(query, result, params, ttl=cache_ttl)\n        \n        return result\n    \n    def invalidate_on_write(self, table: str):\n        \"\"\"Invalidate cache entries when table is modified.\"\"\"\n        if self.cache.strategy == CacheStrategy.WRITE_INVALIDATE:\n            count = self.cache.invalidate_table(table)\n            print(f\"[CACHE] Invalidated {count} entries for table '{table}'\")\n    \n    def get_stats(self) -> Dict[str, Any]:\n        \"\"\"Get combined statistics.\"\"\"\n        return {\n            'cache': self.cache.get_stats(),\n            'executor_type': type(self.executor).__name__\n        }\n\n\n# Convenience functions\ndef create_query_cache(max_size: int = 1000,\n                       ttl: float = 300.0,\n                       strategy: CacheStrategy = CacheStrategy.TIME_TO_LIVE) -> QueryCache:\n    \"\"\"\n    Create and configure query cache.\n    \n    Args:\n        max_size: Maximum number of cached entries\n        ttl: Default time to live in seconds\n        strategy: Invalidation strategy\n    \n    Returns:\n        Configured QueryCache instance\n    \"\"\"\n    cache = QueryCache(\n        max_size=max_size,\n        default_ttl=ttl,\n        strategy=strategy\n    )\n    cache.start()\n    return cache\n\n\ndef cache_query(cache: QueryCache, ttl: Optional[float] = None):\n    \"\"\"\n    Decorator for caching function results.\n    \n    Args:\n        cache: QueryCache instance\n        ttl: Time to live for cached results\n    \n    Example:\n        @cache_query(my_cache, ttl=60)\n        def get_user(user_id: int):\n            return db.query(f\"SELECT * FROM users WHERE id={user_id}\")\n    \"\"\"\n    def decorator(func: Callable):\n        def wrapper(*args, **kwargs):\n            # Generate key from function name and arguments\n            key_data = f\"{func.__name__}:{json.dumps(args, sort_keys=True)}:{json.dumps(kwargs, sort_keys=True)}\"\n            key = hashlib.md5(key_data.encode()).hexdigest()\n            \n            # Try cache\n            result = cache.get(key)\n            if result is not None:\n                return result\n            \n            # Execute and cache\n            result = func(*args, **kwargs)\n            cache.put(key, result, ttl=ttl)\n            return result\n        \n        return wrapper\n    return decorator\n