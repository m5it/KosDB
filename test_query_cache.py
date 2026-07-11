"""
Tests for query result caching system.
"""

import unittest
import time
import threading
from query_cache import QueryCache, CacheEntry, CachedQueryExecutor


class MockDB:
    """Mock database for testing."""
    def __init__(self):
        self.executed_queries = []
        self.data = {
            'users': [
                {'id': 1, 'name': 'Alice'},
                {'id': 2, 'name': 'Bob'}
            ]
        }
    
    def execute(self, query, params=None):
        self.executed_queries.append((query, params))
        if 'users' in query:
            return self.data['users']
        return []


class TestCacheEntry(unittest.TestCase):
    def test_entry_creation(self):
        entry = CacheEntry(key='test', query='SELECT 1', result=[1, 2, 3], ttl=60)
        self.assertEqual(entry.key, 'test')
        self.assertEqual(entry.result, [1, 2, 3])
        self.assertEqual(entry.ttl, 60)
        self.assertEqual(entry.hit_count, 0)
        self.assertFalse(entry.is_expired)
    
    def test_entry_expiration(self):
        entry = CacheEntry(key='test', query='SELECT 1', result=[], ttl=0)
        time.sleep(0.1)
        self.assertTrue(entry.is_expired)
    
    def test_entry_age(self):
        entry = CacheEntry(key='test', query='SELECT 1', result=[])
        time.sleep(0.1)
        self.assertGreater(entry.age, 0)


class TestQueryCache(unittest.TestCase):
    def setUp(self):
        self.cache = QueryCache(max_size=100, default_ttl=60)
    
    def test_generate_key_consistency(self):
        key1 = self.cache._generate_key("SELECT * FROM users")
        key2 = self.cache._generate_key("SELECT * FROM users")
        self.assertEqual(key1, key2)
    
    def test_generate_key_params(self):
        key1 = self.cache._generate_key("SELECT * FROM users", {'id': 1})
        key2 = self.cache._generate_key("SELECT * FROM users", {'id': 1})
        key3 = self.cache._generate_key("SELECT * FROM users", {'id': 2})
        self.assertEqual(key1, key2)
        self.assertNotEqual(key1, key3)
    
    def test_put_and_get(self):
        result = [{'id': 1, 'name': 'Alice'}]
        self.cache.put("SELECT * FROM users", result)
        
        cached = self.cache.get("SELECT * FROM users")
        self.assertEqual(cached, result)
    
    def test_get_nonexistent(self):
        cached = self.cache.get("SELECT * FROM nonexistent")
        self.assertIsNone(cached)
    
    def test_ttl_expiration(self):
        result = [{'id': 1}]
        self.cache.put("SELECT * FROM users", result, ttl=1)
        time.sleep(1.1)
        
        cached = self.cache.get("SELECT * FROM users")
        self.assertIsNone(cached)
    
    def test_lru_eviction(self):
        cache = QueryCache(max_size=2, default_ttl=300)
        
        cache.put("SELECT 1", [1])
        cache.put("SELECT 2", [2])
        cache.put("SELECT 3", [3])
        
        self.assertIsNone(cache.get("SELECT 1"))
        self.assertIsNotNone(cache.get("SELECT 2"))
        self.assertIsNotNone(cache.get("SELECT 3"))
    
    def test_invalidate_all(self):
        self.cache.put("SELECT 1", [1])
        self.cache.put("SELECT 2", [2])
        
        count = self.cache.invalidate()
        self.assertEqual(count, 2)
        self.assertIsNone(self.cache.get("SELECT 1"))
        self.assertIsNone(self.cache.get("SELECT 2"))
    
    def test_invalidate_by_table(self):
        self.cache.put("SELECT * FROM users", [{'id': 1}])
        self.cache.put("SELECT * FROM orders", [{'id': 2}])
        
        count = self.cache.invalidate(table_name="users")
        self.assertEqual(count, 1)
        self.assertIsNone(self.cache.get("SELECT * FROM users"))
        self.assertIsNotNone(self.cache.get("SELECT * FROM orders"))
    
    def test_enable_disable(self):
        self.assertTrue(self.cache.is_enabled())
        
        self.cache.disable()
        self.assertFalse(self.cache.is_enabled())
        
        result = self.cache.get("SELECT 1")
        self.assertIsNone(result)
        
        self.cache.put("SELECT 1", [1])
        result = self.cache.get("SELECT 1")
        self.assertIsNone(result)
        
        self.cache.enable()
        self.assertTrue(self.cache.is_enabled())
    
    def test_get_stats(self):
        self.cache.put("SELECT 1", [1])
        self.cache.get("SELECT 1")
        self.cache.get("SELECT 2")
        
        stats = self.cache.get_stats()
        self.assertEqual(stats['hits'], 1)
        self.assertEqual(stats['misses'], 1)
        self.assertEqual(stats['size'], 1)
        self.assertEqual(stats['hit_rate'], 50.0)
    
    def test_get_cached_queries(self):
        self.cache.put("SELECT 1", [1])
        queries = self.cache.get_cached_queries()
        
        self.assertEqual(len(queries), 1)
        self.assertIn('key', queries[0])
        self.assertIn('age', queries[0])
        self.assertIn('hits', queries[0])
    
    def test_thread_safety(self):
        results = []
        
        def writer():
            for i in range(100):
                self.cache.put(f"SELECT {i}", [i])
        
        def reader():
            for i in range(100):
                r = self.cache.get(f"SELECT {i}")
                results.append(r)
        
        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=writer)
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        self.assertTrue(len(results) > 0)


class TestCachedQueryExecutor(unittest.TestCase):
    def setUp(self):
        self.db = MockDB()
        self.cache = QueryCache()
        self.executor = CachedQueryExecutor(self.db, self.cache)
    
    def test_execute_caches_select(self):
        result = self.executor.execute("SELECT * FROM users")
        self.assertEqual(len(self.db.executed_queries), 1)
        
        result2 = self.executor.execute("SELECT * FROM users")
        self.assertEqual(len(self.db.executed_queries), 1)
        self.assertEqual(result, result2)
    
    def test_execute_no_cache_for_insert(self):
        self.executor.execute("INSERT INTO users VALUES (1)")
        self.executor.execute("INSERT INTO users VALUES (2)")
        
        self.assertEqual(len(self.db.executed_queries), 2)
    
    def test_execute_skip_cache(self):
        self.executor.execute("SELECT * FROM users", use_cache=False)
        self.executor.execute("SELECT * FROM users", use_cache=False)
        
        self.assertEqual(len(self.db.executed_queries), 2)
    
    def test_invalidate_table(self):
        self.executor.execute("SELECT * FROM users")
        self.assertEqual(self.cache.get_stats()['size'], 1)
        
        count = self.executor.invalidate_table("users")
        self.assertEqual(count, 1)
        self.assertEqual(self.cache.get_stats()['size'], 0)


class TestGlobalCache(unittest.TestCase):
    def test_get_global_cache(self):
        from query_cache import get_global_cache
        
        import query_cache
        query_cache._global_cache = None
        
        cache1 = get_global_cache()
        cache2 = get_global_cache()
        
        self.assertIs(cache1, cache2)
    
    def test_configure_cache(self):
        from query_cache import configure_cache
        
        cache = configure_cache(max_size=500, default_ttl=120)
        
        self.assertEqual(cache.max_size, 500)
        self.assertEqual(cache.default_ttl, 120)


if __name__ == '__main__':
    unittest.main(verbosity=2)
