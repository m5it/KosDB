"""
Tests for query cache with invalidation.
"""

import unittest
import time
import threading
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from query_cache import (
    CacheStrategy, CacheEntry, QueryCache,
    CachedQueryExecutor, create_query_cache, cache_query
)


class MockExecutor:
    """Mock query executor for testing."""
    def __init__(self):
        self.call_count = 0
        self.results = {}
    
    def execute(self, query: str, params=None):
        self.call_count += 1
        key = f"{query}:{params}"
        if key not in self.results:
            self.results[key] = f"result_{self.call_count}"
        return self.results[key]


class TestCacheEntry(unittest.TestCase):
    def test_entry_creation(self):
        entry = CacheEntry(
            key="abc123",
            query="SELECT * FROM users",
            result=[{'id': 1}],
            tables={'users'},
            created_at=time.time(),
            ttl=300.0
        )
        
        self.assertEqual(entry.key, "abc123")
        self.assertEqual(entry.size, 1)
        self.assertFalse(entry.is_expired())
    
    def test_entry_expiration(self):
        entry = CacheEntry(
            key="abc123",
            query="SELECT * FROM users",
            result=[],
            tables=set(),
            created_at=time.time() - 400,  # 400 seconds ago
            ttl=300.0
        )
        
        self.assertTrue(entry.is_expired())
    
    def test_entry_no_ttl(self):
        entry = CacheEntry(
            key="abc123",
            query="SELECT * FROM users",
            result=[],
            tables=set(),
            created_at=time.time(),
            ttl=None
        )
        
        self.assertFalse(entry.is_expired())
    
    def test_entry_touch(self):
        entry = CacheEntry(
            key="abc123",
            query="SELECT * FROM users",
            result=[],
            tables=set(),
            created_at=time.time(),
            ttl=300.0
        )
        
        time.sleep(0.01)
        entry.touch()
        
        self.assertEqual(entry.access_count, 1)
        self.assertGreater(entry.last_accessed, entry.created_at)


class TestQueryCache(unittest.TestCase):
    def setUp(self):
        self.cache = QueryCache(max_size=10, default_ttl=1.0)
    
    def tearDown(self):
        self.cache.stop()
    
    def test_put_and_get(self):
        result = [{'id': 1, 'name': 'Alice'}]
        key = self.cache.put("SELECT * FROM users", result, tables={'users'})
        
        cached = self.cache.get("SELECT * FROM users")
        self.assertEqual(cached, result)
    
    def test_get_with_params(self):
        result1 = [{'id': 1}]
        result2 = [{'id': 2}]
        
        self.cache.put("SELECT * FROM users WHERE id=1", result1, params={'id': 1})
        self.cache.put("SELECT * FROM users WHERE id=2", result2, params={'id': 2})
        
        self.assertEqual(
            self.cache.get("SELECT * FROM users WHERE id=1", params={'id': 1}),
            result1
        )
        self.assertEqual(
            self.cache.get("SELECT * FROM users WHERE id=2", params={'id': 2}),
            result2
        )
    
    def test_cache_miss(self):
        result = self.cache.get("SELECT * FROM nonexistent")
        self.assertIsNone(result)
    
    def test_expiration(self):
        result = [{'data': 'test'}]
        self.cache.put("SELECT * FROM test", result, ttl=0.1)
        
        # Should be available immediately
        self.assertIsNotNone(self.cache.get("SELECT * FROM test"))
        
        # Wait for expiration
        time.sleep(0.2)
        
        # Should be expired
        self.assertIsNone(self.cache.get("SELECT * FROM test"))
    
    def test_invalidate_table(self):
        # Cache entries for users table
        self.cache.put("SELECT * FROM users", [{'id': 1}], tables={'users'})
        self.cache.put("SELECT * FROM users WHERE active=1", [{'id': 2}], tables={'users'})
        self.cache.put("SELECT * FROM orders", [{'id': 1}], tables={'orders'})
        
        # Invalidate users table
        count = self.cache.invalidate_table('users')
        self.assertEqual(count, 2)
        
        # Users queries should be gone
        self.assertIsNone(self.cache.get("SELECT * FROM users"))
        self.assertIsNone(self.cache.get("SELECT * FROM users WHERE active=1"))
        
        # Orders query should remain
        self.assertIsNotNone(self.cache.get("SELECT * FROM orders"))
    
    def test_invalidate_all(self):
        self.cache.put("SELECT * FROM users", [])
        self.cache.put("SELECT * FROM orders", [])
        
        count = self.cache.invalidate_all()
        self.assertEqual(count, 2)
        
        self.assertIsNone(self.cache.get("SELECT * FROM users"))
        self.assertIsNone(self.cache.get("SELECT * FROM orders"))
    
    def test_invalidate_pattern(self):
        self.cache.put("SELECT * FROM users WHERE id=1", [])
        self.cache.put("SELECT * FROM users WHERE id=2", [])
        self.cache.put("SELECT * FROM orders", [])
        
        # Invalidate users queries
        count = self.cache.invalidate_pattern(r'FROM\s+users')
        self.assertEqual(count, 2)
        
        self.assertIsNone(self.cache.get("SELECT * FROM users WHERE id=1"))
        self.assertIsNotNone(self.cache.get("SELECT * FROM orders"))
    
    def test_lru_eviction(self):
        cache = QueryCache(max_size=3, default_ttl=None)
        
        # Fill cache
        cache.put("query1", [1])
        cache.put("query2", [2])
        cache.put("query3", [3])
        
        # Access query1 to make it recently used
        cache.get("query1")
        
        # Add new entry - should evict query2 (least recently used)
        cache.put("query4", [4])
        
        self.assertIsNotNone(cache.get("query1"))
        self.assertIsNone(cache.get("query2"))  # Evicted
        self.assertIsNotNone(cache.get("query3"))
        self.assertIsNotNone(cache.get("query4"))
    
    def test_stats(self):
        self.cache.put("SELECT * FROM users", [])
        
        # Miss
        self.cache.get("SELECT * FROM nonexistent")
        
        # Hit
        self.cache.get("SELECT * FROM users")
        
        stats = self.cache.get_stats()
        self.assertEqual(stats['hits'], 1)
        self.assertEqual(stats['misses'], 1)
        self.assertEqual(stats['hit_rate'], 0.5)
        self.assertEqual(stats['size'], 1)
    
    def test_table_version_strategy(self):
        cache = QueryCache(
            max_size=10,
            strategy=CacheStrategy.TABLE_VERSION
        )
        
        # Cache entry with current version
        cache.put("SELECT * FROM users", [{'id': 1}], tables={'users'})
        
        # Should hit
        self.assertIsNotNone(cache.get("SELECT * FROM users"))
        
        # Modify table (increments version)
        cache.invalidate_table('users')
        
        # Should miss due to version mismatch
        self.assertIsNone(cache.get("SELECT * FROM users"))
    
    def test_concurrent_access(self):
        results = []
        
        def writer():
            for i in range(50):
                self.cache.put(f"query_{i}", [i])
                time.sleep(0.001)
        
        def reader():
            for i in range(50):
                result = self.cache.get(f"query_{i % 25}")
                results.append(result)
                time.sleep(0.001)
        
        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=writer),
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Should complete without errors
        self.assertTrue(len(results) > 0)


class TestCachedQueryExecutor(unittest.TestCase):
    def setUp(self):
        self.mock_executor = MockExecutor()
        self.cache = QueryCache(max_size=100)
        self.cached_executor = CachedQueryExecutor(self.mock_executor, self.cache)
        self.cached_executor.cache.start()
    
    def tearDown(self):
        self.cached_executor.cache.stop()
    
    def test_caching(self):
        # First call - should hit executor
        result1 = self.cached_executor.execute("SELECT * FROM users")
        self.assertEqual(self.mock_executor.call_count, 1)
        
        # Second call - should hit cache
        result2 = self.cached_executor.execute("SELECT * FROM users")
        self.assertEqual(self.mock_executor.call_count, 1)  # No new call
        self.assertEqual(result1, result2)
    
    def test_no_cache_for_non_select(self):
        # INSERT should not be cached
        self.cached_executor.execute("INSERT INTO users VALUES (1)", use_cache=True)
        self.cached_executor.execute("INSERT INTO users VALUES (1)", use_cache=True)
        
        # Should execute twice
        self.assertEqual(self.mock_executor.call_count, 2)
    
    def test_custom_ttl(self):
        result = self.cached_executor.execute(
            "SELECT * FROM users",
            cache_ttl=0.1
        )
        
        # Should be cached
        self.assertIsNotNone(self.cached_executor.cache.get("SELECT * FROM users"))
        
        # Wait for expiration
        time.sleep(0.2)
        
        # Should be expired
        self.assertIsNone(self.cached_executor.cache.get("SELECT * FROM users"))
    
    def test_write_invalidation(self):
        cache = QueryCache(max_size=100, strategy=CacheStrategy.WRITE_INVALIDATE)
        cache.start()
        
        cached_exec = CachedQueryExecutor(self.mock_executor, cache)
        
        # Cache a query
        cached_exec.execute("SELECT * FROM users", use_cache=True)
        self.assertIsNotNone(cache.get("SELECT * FROM users"))
        
        # Simulate write
        cached_exec.invalidate_on_write('users')
        
        # Should be invalidated
        self.assertIsNone(cache.get("SELECT * FROM users"))
        
        cache.stop()


class TestConvenienceFunctions(unittest.TestCase):
    def test_create_query_cache(self):
        cache = create_query_cache(
            max_size=500,
            ttl=600.0,
            strategy=CacheStrategy.TIME_TO_LIVE
        )
        
        self.assertEqual(cache.max_size, 500)
        self.assertEqual(cache.default_ttl, 600.0)
        self.assertEqual(cache.strategy, CacheStrategy.TIME_TO_LIVE)
        
        cache.stop()
    
    def test_cache_query_decorator(self):
        cache = QueryCache(max_size=100)
        
        @cache_query(cache, ttl=1.0)
        def expensive_function(x):
            time.sleep(0.01)  # Simulate work
            return x * x
        
        # First call
        result1 = expensive_function(5)
        self.assertEqual(result1, 25)
        
        # Second call - should be cached
        result2 = expensive_function(5)
        self.assertEqual(result2, 25)
        
        # Different argument
        result3 = expensive_function(10)
        self.assertEqual(result3, 100)


class TestIntegration(unittest.TestCase):
    def test_full_workflow(self):
        """Test complete caching workflow."""
        cache = QueryCache(max_size=100, default_ttl=60.0)
        
        # Simulate application queries
        queries = [
            ("SELECT * FROM users", {'users'}, [{'id': 1}, {'id': 2}]),
            ("SELECT * FROM products", {'products'}, [{'sku': 'A'}, {'sku': 'B'}]),
            ("SELECT * FROM orders JOIN users ON orders.user_id = users.id", 
             {'orders', 'users'}, [{'order_id': 1, 'user_id': 1}]),
        ]
        
        # Cache all queries
        for query, tables, result in queries:
            cache.put(query, result, tables=tables)
        
        # Verify all cached
        self.assertEqual(cache.get_stats()['size'], 3)
        
        # Access users query
        users = cache.get("SELECT * FROM users")
        self.assertEqual(len(users), 2)
        
        # Invalidate users table
        invalidated = cache.invalidate_table('users')
        self.assertEqual(invalidated, 2)  # users query + join query
        
        # Products should still be cached
        self.assertIsNotNone(cache.get("SELECT * FROM products"))
        
        # Users queries should be gone
        self.assertIsNone(cache.get("SELECT * FROM users"))
        
        cache.stop()


if __name__ == '__main__':
    unittest.main(verbosity=2)
