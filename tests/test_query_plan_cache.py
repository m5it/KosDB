"""
Tests for query plan cache.
"""

import unittest
import time
import threading
from query_plan_cache import (
    QueryPlanCache,
    CachedPlan,
    get_query_plan_cache,
    configure_query_plan_cache
)


class TestQueryPlanCache(unittest.TestCase):
    
    def setUp(self):
        self.cache = QueryPlanCache(capacity=100)
    
    def test_basic_put_get(self):
        """Test basic cache operations."""
        plan = {"type": "SELECT", "table": "users"}
        
        self.cache.put("SELECT * FROM users", plan, ["users"])
        
        cached = self.cache.get("SELECT * FROM users")
        self.assertIsNotNone(cached)
        self.assertEqual(cached.parsed_plan, plan)
        self.assertEqual(cached.table_dependencies, ["users"])
    
    def test_cache_miss(self):
        """Test cache miss returns None."""
        result = self.cache.get("SELECT * FROM nonexistent")
        self.assertIsNone(result)
    
    def test_case_insensitive_lookup(self):
        """Test queries are case-insensitive."""
        plan = {"type": "SELECT"}
        
        self.cache.put("SELECT * FROM users", plan, ["users"])
        
        # Different case should still match
        cached = self.cache.get("select * from users")
        self.assertIsNotNone(cached)
    
    def test_lru_eviction(self):
        """Test LRU eviction when capacity exceeded."""
        cache = QueryPlanCache(capacity=3)
        
        # Add 3 plans
        for i in range(3):
            cache.put(f"SELECT * FROM table{i}", {"id": i}, [f"table{i}"])
        
        # Access first one to make it recently used
        cache.get("SELECT * FROM table0")
        
        # Add 4th plan - should evict table1 (least recently used)
        cache.put("SELECT * FROM table3", {"id": 3}, ["table3"])
        
        self.assertIsNotNone(cache.get("SELECT * FROM table0"))  # Recently used
        self.assertIsNone(cache.get("SELECT * FROM table1"))  # Evicted
        self.assertIsNotNone(cache.get("SELECT * FROM table2"))
    
    def test_table_invalidation(self):
        """Test invalidation by table name."""
        plan1 = {"type": "SELECT", "table": "users"}
        plan2 = {"type": "SELECT", "table": "orders"}
        
        self.cache.put("SELECT * FROM users", plan1, ["users"])
        self.cache.put("SELECT * FROM orders", plan2, ["orders"])
        
        # Invalidate users table
        self.cache.invalidate_table("users")
        
        self.assertIsNone(self.cache.get("SELECT * FROM users"))
        self.assertIsNotNone(self.cache.get("SELECT * FROM orders"))
    
    def test_ttl_expiration(self):
        """Test TTL-based expiration."""
        cache = QueryPlanCache(capacity=100, ttl=0.1)
        
        cache.put("SELECT * FROM users", {"type": "SELECT"}, ["users"])
        
        # Should exist immediately
        self.assertIsNotNone(cache.get("SELECT * FROM users"))
        
        # Wait for expiration
        time.sleep(0.2)
        
        # Should be expired
        self.assertIsNone(cache.get("SELECT * FROM users"))
    
    def test_statistics(self):
        """Test cache statistics."""
        self.cache.put("SELECT * FROM users", {"type": "SELECT"}, ["users"])
        
        # Hit
        self.cache.get("SELECT * FROM users")
        
        # Miss
        self.cache.get("SELECT * FROM nonexistent")
        
        stats = self.cache.get_stats()
        
        self.assertEqual(stats['size'], 1)
        self.assertEqual(stats['hits'], 1)
        self.assertEqual(stats['misses'], 1)
        self.assertAlmostEqual(stats['hit_rate'], 0.5, places=2)
    
    def test_thread_safety(self):
        """Test thread-safe operations."""
        results = []
        
        def put_operations():
            for i in range(100):
                self.cache.put(f"SELECT {i}", {"id": i}, ["table"])
        
        def get_operations():
            for i in range(100):
                result = self.cache.get(f"SELECT {i}")
                results.append(result)
        
        threads = [
            threading.Thread(target=put_operations),
            threading.Thread(target=get_operations)
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Should complete without errors
        self.assertEqual(len(results), 100)
    
    def test_global_cache(self):
        """Test global cache singleton."""
        configure_query_plan_cache(capacity=500)
        
        cache = get_query_plan_cache()
        self.assertEqual(cache.capacity, 500)
        
        cache.put("SELECT * FROM test", {"type": "TEST"}, ["test"])
        
        # Same instance should have the data
        cache2 = get_query_plan_cache()
        self.assertIsNotNone(cache2.get("SELECT * FROM test"))


class TestCachedPlan(unittest.TestCase):
    
    def test_touch_updates_timestamp(self):
        """Test touch() updates access time."""
        plan = CachedPlan(
            query_hash="abc123",
            original_query="SELECT * FROM users",
            parsed_plan={},
            table_dependencies=["users"],
            cache_time=time.time()
        )
        
        old_time = plan.last_accessed
        time.sleep(0.01)
        plan.touch()
        
        self.assertGreater(plan.last_accessed, old_time)
        self.assertEqual(plan.hit_count, 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
