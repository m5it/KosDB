"""
Test Query Plan Cache for KosDB v3.2.0

Tests:
- Plan cache storage and retrieval
- LRU eviction policy
- Cache invalidation on schema changes
- Cache statistics (hit rate, miss rate, evictions)
- EXPLAIN CACHE command
- Cache dependency tracking
"""

import unittest
import sys
import os
import tempfile
import shutil
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from query_optimizer import (
    QueryOptimizer, PlanCache, ExecutionPlan, Operator, OperatorType,
    Statistics, CostModel
)


class TestPlanCache(unittest.TestCase):
    """Test plan cache functionality."""
    
    def setUp(self):
        """Set up test cache."""
        self.cache = PlanCache(max_size=5)
    
    def test_cache_put_and_get(self):
        """Test basic cache put and get."""
        plan = self._create_dummy_plan()
        
        # Put plan in cache
        self.cache.put("key1", plan, {"users"})
        
        # Get plan from cache
        retrieved = self.cache.get("key1")
        
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.total_cost, plan.total_cost)
    
    def test_cache_miss(self):
        """Test cache miss returns None."""
        result = self.cache.get("nonexistent")
        self.assertIsNone(result)
        self.assertEqual(self.cache.stats['misses'], 1)
    
    def test_cache_hit_updates_stats(self):
        """Test cache hit updates statistics."""
        plan = self._create_dummy_plan()
        self.cache.put("key1", plan, {"users"})
        
        # First access
        self.cache.get("key1")
        self.assertEqual(self.cache.stats['hits'], 1)
        
        # Second access
        self.cache.get("key1")
        self.assertEqual(self.cache.stats['hits'], 2)
    
    def test_lru_eviction(self):
        """Test LRU eviction when cache is full."""
        # Fill cache to capacity
        for i in range(5):
            plan = self._create_dummy_plan(cost=i)
            self.cache.put(f"key{i}", plan, {"users"})
        
        # All 5 should be in cache
        self.assertEqual(len(self.cache.cache), 5)
        
        # Access key0 to make it recently used
        self.cache.get("key0")
        
        # Add 6th entry - should evict key1 (least recently used)
        plan = self._create_dummy_plan(cost=99)
        self.cache.put("key5", plan, {"users"})
        
        self.assertEqual(len(self.cache.cache), 5)
        self.assertIn("key0", self.cache.cache)  # Recently accessed
        self.assertIn("key5", self.cache.cache)  # Just added
        self.assertNotIn("key1", self.cache.cache)  # Evicted
    
    def test_cache_invalidation_by_table(self):
        """Test invalidating cache entries by table."""
        # Add plans depending on different tables
        plan1 = self._create_dummy_plan()
        plan2 = self._create_dummy_plan()
        
        self.cache.put("key1", plan1, {"users"})
        self.cache.put("key2", plan2, {"orders"})
        
        # Invalidate by table
        self.cache.invalidate("users")
        
        # key1 should be gone, key2 should remain
        self.assertIsNone(self.cache.get("key1"))
        self.assertIsNotNone(self.cache.get("key2"))
        self.assertEqual(self.cache.stats['invalidations'], 1)
    
    def test_cache_invalidation_all(self):
        """Test invalidating all cache entries."""
        plan = self._create_dummy_plan()
        
        self.cache.put("key1", plan, {"users"})
        self.cache.put("key2", plan, {"orders"})
        
        # Invalidate all
        self.cache.invalidate()
        
        self.assertEqual(len(self.cache.cache), 0)
        self.assertEqual(self.cache.stats['invalidations'], 2)
    
    def test_cache_stats(self):
        """Test cache statistics reporting."""
        plan = self._create_dummy_plan()
        
        # Add some hits and misses
        self.cache.put("key1", plan, {"users"})
        self.cache.get("key1")  # hit
        self.cache.get("key1")  # hit
        self.cache.get("missing")  # miss
        
        stats = self.cache.get_stats()
        
        self.assertEqual(stats['size'], 1)
        self.assertEqual(stats['max_size'], 5)
        self.assertEqual(stats['hits'], 2)
        self.assertEqual(stats['misses'], 1)
        self.assertAlmostEqual(stats['hit_rate'], 2/3, places=2)
        self.assertAlmostEqual(stats['miss_rate'], 1/3, places=2)
    
    def test_cache_explain(self):
        """Test cache explain output."""
        plan = self._create_dummy_plan()
        self.cache.put("key1", plan, {"users"})
        
        explain = self.cache.explain()
        
        self.assertIn("Plan Cache Status:", explain)
        self.assertIn("Size:", explain)
        self.assertIn("Hit Rate:", explain)
        self.assertIn("Cached Plans:", explain)
    
    def _create_dummy_plan(self, cost: float = 10.0) -> ExecutionPlan:
        """Create a dummy execution plan for testing."""
        root = Operator(
            op_type=OperatorType.SCAN,
            table="test",
            estimated_rows=100,
            estimated_cost=cost
        )
        
        return ExecutionPlan(
            root=root,
            total_cost=cost,
            estimated_rows=100
        )


class TestQueryOptimizerCache(unittest.TestCase):
    """Test query optimizer with plan cache integration."""
    
    def setUp(self):
        """Set up test optimizer."""
        self.optimizer = QueryOptimizer(cache_size=10)
        
        # Add statistics for test table
        stats = Statistics(
            table_name="users",
            row_count=1000,
            column_stats={
                "id": {"distinct_count": 1000},
                "name": {"distinct_count": 900}
            },
            index_stats={
                "id": {"type": "btree"}
            }
        )
        self.optimizer.add_statistics("users", stats)
    
    def test_optimize_uses_cache(self):
        """Test that optimization uses cache."""
        query = "SELECT * FROM users WHERE id = 1"
        
        # First optimization - should miss cache
        plan1 = self.optimizer.optimize(query)
        stats1 = self.optimizer.get_cache_stats()
        self.assertEqual(stats1['misses'], 1)
        self.assertEqual(stats1['hits'], 0)
        
        # Second optimization - should hit cache
        plan2 = self.optimizer.optimize(query)
        stats2 = self.optimizer.get_cache_stats()
        self.assertEqual(stats2['misses'], 1)
        self.assertEqual(stats2['hits'], 1)
        
        # Plans should be identical
        self.assertEqual(plan1.total_cost, plan2.total_cost)
    
    def test_optimize_without_cache(self):
        """Test optimization without cache."""
        query = "SELECT * FROM users WHERE id = 1"
        
        # Optimize without cache
        plan = self.optimizer.optimize(query, use_cache=False)
        stats = self.optimizer.get_cache_stats()
        
        # Should not affect cache
        self.assertEqual(stats['misses'], 0)
        self.assertEqual(stats['hits'], 0)
    
    def test_cache_invalidation_integration(self):
        """Test cache invalidation through optimizer."""
        query = "SELECT * FROM users WHERE id = 1"
        
        # Optimize and cache
        self.optimizer.optimize(query)
        self.assertEqual(self.optimizer.get_cache_stats()['size'], 1)
        
        # Invalidate by table
        self.optimizer.invalidate_cache("users")
        self.assertEqual(self.optimizer.get_cache_stats()['size'], 0)
    
    def test_multiple_queries_cache(self):
        """Test caching multiple different queries."""
        queries = [
            "SELECT * FROM users WHERE id = 1",
            "SELECT * FROM users WHERE name = 'Alice'",
            "SELECT * FROM users ORDER BY id",
        ]
        
        # Optimize all queries
        for query in queries:
            self.optimizer.optimize(query)
        
        stats = self.optimizer.get_cache_stats()
        self.assertEqual(stats['size'], 3)
        self.assertEqual(stats['misses'], 3)
        self.assertEqual(stats['hits'], 0)
        
        # Optimize same queries again
        for query in queries:
            self.optimizer.optimize(query)
        
        stats = self.optimizer.get_cache_stats()
        self.assertEqual(stats['size'], 3)
        self.assertEqual(stats['hits'], 3)
    
    def test_cache_key_normalization(self):
        """Test that equivalent queries get same cache key."""
        # These should generate same plan
        query1 = "SELECT * FROM users WHERE id = 1"
        query2 = "select * from users where id = 1"  # lowercase
        query3 = "SELECT  *  FROM  users  WHERE  id  =  1"  # extra spaces
        
        plan1 = self.optimizer.optimize(query1)
        plan2 = self.optimizer.optimize(query2)
        plan3 = self.optimizer.optimize(query3)
        
        # All should hit cache after first
        stats = self.optimizer.get_cache_stats()
        self.assertEqual(stats['misses'], 1)  # Only first is miss
        self.assertEqual(stats['hits'], 2)   # Others are hits
    
    def test_explain_cache(self):
        """Test EXPLAIN CACHE output."""
        # Add some plans to cache
        for i in range(3):
            query = f"SELECT * FROM users WHERE id = {i}"
            self.optimizer.optimize(query)
        
        explain = self.optimizer.explain_cache()
        
        self.assertIn("Plan Cache Status:", explain)
        self.assertIn("3 / 10 entries", explain)  # 3 entries, max 10


class TestPlanCacheEdgeCases(unittest.TestCase):
    """Test edge cases for plan cache."""
    
    def setUp(self):
        self.cache = PlanCache(max_size=3)
    
    def test_access_count_tracking(self):
        """Test that access count is tracked."""
        plan = self._create_dummy_plan()
        
        self.cache.put("key1", plan, {"users"})
        entry = self.cache.cache["key1"]
        self.assertEqual(entry.access_count, 1)
        
        self.cache.get("key1")
        entry = self.cache.cache["key1"]
        self.assertEqual(entry.access_count, 2)
    
    def test_timestamp_updates(self):
        """Test that timestamps are updated correctly."""
        plan = self._create_dummy_plan()
        
        before = time.time()
        self.cache.put("key1", plan, {"users"})
        after_put = time.time()
        
        entry = self.cache.cache["key1"]
        self.assertGreaterEqual(entry.created_at, before)
        self.assertLessEqual(entry.created_at, after_put)
        
        # Wait a bit and access
        time.sleep(0.01)
        before_access = time.time()
        self.cache.get("key1")
        after_access = time.time()
        
        self.assertGreaterEqual(entry.last_accessed, before_access)
        self.assertLessEqual(entry.last_accessed, after_access)
    
    def test_empty_cache_stats(self):
        """Test stats with empty cache."""
        stats = self.cache.get_stats()
        
        self.assertEqual(stats['size'], 0)
        self.assertEqual(stats['hits'], 0)
        self.assertEqual(stats['misses'], 0)
        self.assertEqual(stats['hit_rate'], 0.0)
    
    def test_multiple_table_dependencies(self):
        """Test cache entry with multiple table dependencies."""
        plan = self._create_dummy_plan()
        
        self.cache.put("key1", plan, {"users", "orders", "products"})
        
        # Invalidate by any table should remove entry
        self.cache.invalidate("orders")
        self.assertIsNone(self.cache.get("key1"))
    
    def test_eviction_count(self):
        """Test that evictions are counted correctly."""
        # Fill cache beyond capacity
        for i in range(10):
            plan = self._create_dummy_plan()
            self.cache.put(f"key{i}", plan, {"users"})
        
        self.assertEqual(self.cache.stats['evictions'], 7)  # 10 - 3 capacity
    
    def _create_dummy_plan(self, cost: float = 10.0) -> ExecutionPlan:
        """Create a dummy execution plan."""
        root = Operator(
            op_type=OperatorType.SCAN,
            table="test",
            estimated_rows=100,
            estimated_cost=cost
        )
        
        return ExecutionPlan(
            root=root,
            total_cost=cost,
            estimated_rows=100
        )


class TestPlanCacheParser(unittest.TestCase):
    """Test parser support for EXPLAIN CACHE."""
    
    def setUp(self):
        self.parser = CommandParser()
    
    def test_parse_explain_cache(self):
        """Test parsing EXPLAIN CACHE."""
        from parser import CommandParser
        parser = CommandParser()
        
        sql = "EXPLAIN CACHE"
        cmd_type, params = parser.parse(sql)
        
        self.assertEqual(cmd_type, 'EXPLAIN')
        self.assertEqual(params['target'], 'CACHE')
    
    def test_parse_explain_query(self):
        """Test parsing EXPLAIN <query>."""
        from parser import CommandParser
        parser = CommandParser()
        
        sql = "EXPLAIN SELECT * FROM users"
        cmd_type, params = parser.parse(sql)
        
        self.assertEqual(cmd_type, 'EXPLAIN')
        self.assertEqual(params['target'], 'SELECT * FROM users')


if __name__ == '__main__':
    unittest.main(verbosity=2)
