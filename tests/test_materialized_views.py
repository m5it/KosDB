"""
Tests for materialized views module.
"""

import unittest
import time
import threading
from materialized_views import (
    MaterializedView,
    MaterializedViewManager,
    QueryRewriter,
    QueryPlan,
    RefreshStrategy,
    RefreshSchedule,
    get_materialized_view_manager
)


class TestQueryRewriter(unittest.TestCase):
    
    def test_rewrite_query(self):
        """Test query rewriting."""
        rewriter = QueryRewriter()
        
        query = "SELECT * FROM users WHERE id = 1"
        plan = rewriter.rewrite(query)
        
        self.assertIsInstance(plan, QueryPlan)
        self.assertEqual(plan.original_query, query)
    
    def test_estimate_cost(self):
        """Test cost estimation."""
        rewriter = QueryRewriter()
        
        # Simple query
        cost1 = rewriter._estimate_cost("SELECT id FROM users")
        
        # Complex query with multiple joins
        cost2 = rewriter._estimate_cost(
            "SELECT * FROM users u JOIN orders o ON u.id = o.user_id JOIN items i ON o.id = i.order_id"
        )
        
        self.assertGreater(cost2, cost1)
    
    def test_rewrite_rules(self):
        """Test individual rewrite rules."""
        rewriter = QueryRewriter()
        
        # Test SELECT * detection
        result = rewriter._rewrite_select_star("SELECT * FROM users")
        # Would need schema to actually rewrite
        
        # Test subquery detection
        result = rewriter._rewrite_subquery_to_join(
            "SELECT * FROM users WHERE id IN (SELECT user_id FROM orders)"
        )


class TestMaterializedView(unittest.TestCase):
    
    def test_create_view(self):
        """Test view creation."""
        view = MaterializedView(
            name="test_view",
            query="SELECT * FROM users",
            refresh_strategy=RefreshStrategy.FULL,
            refresh_schedule=RefreshSchedule.MANUAL
        )
        
        self.assertEqual(view.name, "test_view")
        self.assertEqual(view.refresh_strategy, RefreshStrategy.FULL)
        self.assertTrue(view.is_stale)
    
    def test_mark_stale(self):
        """Test marking view as stale."""
        view = MaterializedView(name="test", query="SELECT 1")
        view.is_stale = False
        
        view.mark_stale()
        self.assertTrue(view.is_stale)
    
    def test_get_stats(self):
        """Test view statistics."""
        view = MaterializedView(
            name="stats_view",
            query="SELECT * FROM users"
        )
        
        stats = view.get_stats()
        
        self.assertEqual(stats['name'], "stats_view")
        self.assertEqual(stats['refresh_strategy'], 'full')
        self.assertIn('is_stale', stats)


class TestMaterializedViewManager(unittest.TestCase):
    
    def setUp(self):
        self.manager = MaterializedViewManager()
    
    def test_create_view(self):
        """Test creating materialized view."""
        view = self.manager.create_view(
            name="users_summary",
            query="SELECT COUNT(*) FROM users",
            refresh_strategy="full",
            refresh_schedule="manual"
        )
        
        self.assertIn("users_summary", self.manager.list_views())
        self.assertEqual(view.name, "users_summary")
    
    def test_create_duplicate_view(self):
        """Test duplicate view creation."""
        self.manager.create_view("test_view", "SELECT 1")
        
        with self.assertRaises(ValueError):
            self.manager.create_view("test_view", "SELECT 2")
    
    def test_drop_view(self):
        """Test dropping view."""
        self.manager.create_view("drop_me", "SELECT 1")
        
        self.assertTrue(self.manager.drop_view("drop_me"))
        self.assertNotIn("drop_me", self.manager.list_views())
        
        # Drop non-existent
        self.assertFalse(self.manager.drop_view("nonexistent"))
    
    def test_refresh_view(self):
        """Test view refresh."""
        self.manager.create_view("refresh_me", "SELECT 1")
        
        result = self.manager.refresh_view("refresh_me")
        
        self.assertEqual(result['view'], "refresh_me")
        self.assertEqual(result['strategy'], "full")
        self.assertIn('duration_ms', result)
        
        view = self.manager.get_view("refresh_me")
        self.assertFalse(view.is_stale)
        self.assertEqual(view.refresh_count, 1)
    
    def test_refresh_with_strategy(self):
        """Test refresh with explicit strategy."""
        self.manager.create_view("strategy_test", "SELECT 1")
        
        result = self.manager.refresh_view("strategy_test", strategy="incremental")
        
        self.assertEqual(result['strategy'], "incremental")
    
    def test_query_view(self):
        """Test querying view."""
        self.manager.create_view("query_test", "SELECT 1 as num")
        
        # Mock data
        view = self.manager.get_view("query_test")
        view.data = [{'num': 1}, {'num': 2}]
        view.row_count = 2
        view.is_stale = False
        
        data, plan = self.manager.query_view("query_test", rewrite=False)
        
        self.assertEqual(len(data), 2)
        self.assertIsNone(plan)
    
    def test_get_stats(self):
        """Test manager statistics."""
        self.manager.create_view("view1", "SELECT 1")
        self.manager.create_view("view2", "SELECT 2")
        
        stats = self.manager.get_stats()
        
        self.assertEqual(stats['view_count'], 2)
class TestIncrementalRefresh(unittest.TestCase):
    
    def setUp(self):
        self.manager = MaterializedViewManager()
    
    def test_full_refresh(self):
        """Test full refresh computation."""
        view = self.manager.create_view("full_test", "SELECT * FROM users")
        
        # Simulate data
        view.data = [{'id': 1}, {'id': 2}]
        
        # Full refresh should update data and change tracking
        self.manager._full_refresh(view)
        
        # Check that change tracking was updated (checksum stored)
        self.assertIsNotNone(view.change_tracking)
        self.assertGreater(len(view.change_tracking), 0)
    
    def test_compute_checksum(self):
        """Test checksum computation."""
        data1 = [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}]
        data2 = [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}]
        data3 = [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Charlie'}]
        
        checksum1 = self.manager._compute_checksum(data1)
        checksum2 = self.manager._compute_checksum(data2)
        checksum3 = self.manager._compute_checksum(data3)
        
        self.assertEqual(checksum1, checksum2)
        self.assertNotEqual(checksum1, checksum3)
    
    def test_singleton(self):
        """Test global manager is singleton."""
        manager1 = get_materialized_view_manager()
        manager2 = get_materialized_view_manager()
        
        self.assertIs(manager1, manager2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
