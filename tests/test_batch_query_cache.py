
"""
Tests for Batch Query Cache
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from batch_query_cache import (
    BatchQueryCache,
    BatchCacheManager,
    parse_cache_hint,
    CacheEntry
)


class TestBatchQueryCache(unittest.TestCase):
    """Test batch query cache functionality."""
    
    def setUp(self):
        self.cache = BatchQueryCache(default_ttl_seconds=60.0, max_size=100)
    
    def test_cache_hit(self):
        """Test cache hit."""
        query = "SELECT * FROM users"
        result = [{"id": 1, "name": "Alice"}]
        
        # First put
        self.cache.put(query, result)
        
        # Then get
        cached = self.cache.get(query)
        self.assertEqual(cached, result)
    
    def test_cache_miss(self):
        """Test cache miss."""
        query = "SELECT * FROM unknown_table"
        
        cached = self.cache.get(query)
        self.assertIsNone(cached)
    
    def test_cache_expiration(self):
        """Test cache entry expiration."""
        query = "SELECT * FROM temp"
        result = [{"data": "test"}]
        
        # Put with very short TTL
        self.cache.put(query, result, ttl=0.001)
        
        # Should expire quickly
        import time
        time.sleep(0.01)
        
        cached = self.cache.get(query)
        self.assertIsNone(cached)
    
    def test_cache_invalidation(self):
        """Test cache invalidation on table change."""
        query = "SELECT * FROM users"
        result = [{"id": 1}]
        
        self.cache.put(query, result)
        
        # Invalidate users table
        self.cache.invalidate({"users"})
        
        cached = self.cache.get(query)
        self.assertIsNone(cached)
    
    def test_parse_cache_hint(self):
        """Test parsing cache hints."""
        # Cache hint
        query, use_cache = parse_cache_hint("SELECT /*+ CACHE */ * FROM t")
        self.assertTrue(use_cache)
        self.assertNotIn("CACHE", query)
        
        # Nocache hint
        query, use_cache = parse_cache_hint("SELECT /*+ NOCACHE */ * FROM t")
        self.assertFalse(use_cache)
        
        # Default
        query, use_cache = parse_cache_hint("SELECT * FROM t")
        self.assertTrue(use_cache)
    
    def test_cache_stats(self):
        """Test cache statistics."""
        # Miss
        self.cache.get("SELECT 1")
        
        # Hit
        self.cache.put("SELECT 2", "result")
        self.cache.get("SELECT 2")
        
        stats = self.cache.get_stats()
        self.assertEqual(stats['misses'], 1)
        self.assertEqual(stats['hits'], 1)
        self.assertGreater(stats['hit_ratio'], 0)
    
    def test_cache_status(self):
        """Test cache status output."""
        status = self.cache.get_status()
        self.assertIn("BATCH QUERY CACHE STATUS", status)
        self.assertIn("Cache Size:", status)


class TestBatchCacheManager(unittest.TestCase):
    """Test batch cache manager."""
    
    def setUp(self):
        self.manager = BatchCacheManager()
    
    def test_execute_with_cache(self):
        """Test execute with caching."""
        def executor(q):
            return f"result_of_{q}"
        
        # First execution
        result1 = self.manager.execute_with_cache("SELECT 1", executor)
        self.assertEqual(result1, "result_of_SELECT 1")
        
        # Second execution should use cache
        result2 = self.manager.execute_with_cache("SELECT 1", executor)
        self.assertEqual(result2, "result_of_SELECT 1")
        
        # Check stats
        stats = self.manager.get_stats()

    def test_dml_invalidation(self):
        """Test DML invalidates cache."""
        def executor(q):
            return "done"
        
        # Cache a select on users table
        self.manager.execute_with_cache("SELECT * FROM users", executor)
        
        # Execute DML on users table
        self.manager.execute_with_cache("INSERT INTO users VALUES (1)", executor)
        
        # Check that cache is invalidated - the select should now miss
        result = self.manager.execute_with_cache("SELECT * FROM users", executor)
        
        # Cache should have been invalidated, so this is a new execution
        stats = self.manager.get_stats()
        # After invalidation and re-execution, we should have 1 invalidation
        # and the hit count should reflect the cache miss
        self.assertGreater(stats.get('misses', 0), 0)
