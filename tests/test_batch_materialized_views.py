
"""
Tests for Batch Materialized View Operations
"""

import unittest
import sys
import os
import time
import threading


from batch_materialized_views import (
    BatchMaterializedViewManager,
    RefreshMode,
    parse_refresh_command,
    ScheduledRefresh,
    RefreshStrategy
)

# Mock materialized view manager for testing
class MockView:
    def __init__(self, name, query):
        self.name = name
        self.query = query
        self.is_stale = True
        self.last_refresh = None
        self.refresh_count = 0
        self.row_count = 100
        self._lock = threading.RLock()
        self.refresh_strategy = RefreshStrategy.FULL
# Mock materialized view manager for testing
class MockView:
    def __init__(self, name, query):
        self.name = name
        self.query = query
        self.is_stale = True
        self.last_refresh = None
        self.refresh_count = 0
        self.row_count = 100
        self._lock = threading.RLock()
        # Add refresh_strategy for compatibility
        from batch_materialized_views import RefreshStrategy
        self.refresh_strategy = RefreshStrategy.FULL

class MockMVManager:
    def __init__(self):
        self.views = {
            'view1': MockView('view1', 'SELECT * FROM table1'),
            'view2': MockView('view2', 'SELECT * FROM view1'),
            'view3': MockView('view3', 'SELECT * FROM table2'),
        }
    
    def refresh_view(self, name):
        view = self.views.get(name)
        if view:
            view.is_stale = False
            view.last_refresh = time.time()
            view.refresh_count += 1
            return {'rows': view.row_count}
        return {'rows': 0}


class TestBatchMaterializedViewManager(unittest.TestCase):
    """Test batch MV manager functionality."""
    
    def setUp(self):
        self.mv_manager = MockMVManager()
        self.batch_manager = BatchMaterializedViewManager(self.mv_manager)
    
    def test_refresh_view_blocking(self):
        """Test blocking refresh."""
        result = self.batch_manager.refresh_view('view1', mode=RefreshMode.BLOCKING)
        
        self.assertTrue(result['success'])
        self.assertEqual(result['view_name'], 'view1')
        self.assertEqual(result['mode'], 'blocking')
        self.assertIn('elapsed_ms', result)
    
    def test_refresh_view_concurrently(self):
        """Test concurrent refresh."""
        result = self.batch_manager.refresh_view('view1', concurrently=True)
        
        self.assertTrue(result['success'])
        self.assertEqual(result['mode'], 'concurrently')
    
    def test_refresh_nonexistent_view(self):
        """Test refresh of non-existent view."""
        result = self.batch_manager.refresh_view('nonexistent')
        
        self.assertFalse(result['success'])
        self.assertIn('error', result)
    
    def test_refresh_all_views(self):
        """Test refresh all views."""
        result = self.batch_manager.refresh_all_views()
        
        self.assertTrue(result['success'])
        self.assertEqual(result['total_views'], 3)
        self.assertEqual(result['refreshed'], 3)
        self.assertEqual(result['failed'], 0)
    
    def test_refresh_all_with_dependencies(self):
        """Test refresh all respects dependencies."""
        result = self.batch_manager.refresh_all_views(respect_dependencies=True)
        
        self.assertTrue(result['success'])
        # view2 depends on view1, so view1 should be refreshed first
        self.assertEqual(len(result['results']), 3)
    
    def test_schedule_refresh(self):
        """Test scheduling refresh."""
        result = self.batch_manager.schedule_refresh('view1', interval_minutes=5)
        
        self.assertTrue(result['success'])
        self.assertEqual(result['view_name'], 'view1')
        self.assertEqual(result['interval_minutes'], 5)
        self.assertIn('next_run', result)
        
        # Clean up
        self.batch_manager.cancel_schedule('view1')
    
    def test_cancel_schedule(self):
        """Test canceling scheduled refresh."""
        self.batch_manager.schedule_refresh('view1', interval_minutes=5)
        
        result = self.batch_manager.cancel_schedule('view1')
        self.assertTrue(result)
        
        # Already canceled
        result = self.batch_manager.cancel_schedule('view1')
        self.assertFalse(result)
    
    def test_get_schedules(self):
        """Test getting all schedules."""
        self.batch_manager.schedule_refresh('view1', interval_minutes=5)
        self.batch_manager.schedule_refresh('view2', interval_minutes=10)
        
        schedules = self.batch_manager.get_schedules()
        
        self.assertEqual(len(schedules), 2)
        self.assertTrue(any(s['view_name'] == 'view1' for s in schedules))
        self.assertTrue(any(s['view_name'] == 'view2' for s in schedules))
        
        # Clean up
        self.batch_manager.cancel_schedule('view1')
        self.batch_manager.cancel_schedule('view2')
    
    def test_get_metrics(self):
        """Test getting metrics."""
        # Do some refreshes
        self.batch_manager.refresh_view('view1')
        self.batch_manager.refresh_view('view2', concurrently=True)
        
        metrics = self.batch_manager.get_metrics()
        
        self.assertEqual(metrics['total_refreshes'], 2)
        self.assertEqual(metrics['blocking_refreshes'], 1)
        self.assertEqual(metrics['concurrent_refreshes'], 1)
        self.assertGreater(metrics['avg_refresh_time_ms'], 0)
    
    def test_get_view_status(self):
        """Test getting view status."""
        # Single view
        status = self.batch_manager.get_view_status('view1')
        self.assertEqual(status['name'], 'view1')
        self.assertIn('is_stale', status)
        
        # All views
        status = self.batch_manager.get_view_status()
        self.assertEqual(status['total_views'], 3)
        self.assertEqual(len(status['views']), 3)
    
    def test_dependency_extraction(self):
        """Test extracting dependencies from query."""
        query = "SELECT * FROM users JOIN orders ON users.id = orders.user_id"
        deps = self.batch_manager._extract_dependencies(query)
        
        self.assertIn('users', deps)
        self.assertIn('orders', deps)


class TestParseRefreshCommand(unittest.TestCase):
    """Test refresh command parsing."""
    
    def test_parse_refresh_view(self):
        """Test parse REFRESH MATERIALIZED VIEW."""
        result = parse_refresh_command("REFRESH MATERIALIZED VIEW view1")
        
        self.assertEqual(result['type'], 'refresh')
        self.assertEqual(result['view_name'], 'view1')
        self.assertFalse(result['concurrently'])
    
    def test_parse_refresh_concurrently(self):
        """Test parse REFRESH MATERIALIZED VIEW CONCURRENTLY."""
        result = parse_refresh_command("REFRESH MATERIALIZED VIEW CONCURRENTLY view1")
        
        self.assertEqual(result['type'], 'refresh')
        self.assertEqual(result['view_name'], 'view1')
        self.assertTrue(result['concurrently'])
    
    def test_parse_refresh_all(self):
        """Test parse REFRESH ALL MATERIALIZED VIEWS."""
        result = parse_refresh_command("REFRESH ALL MATERIALIZED VIEWS")
        
        self.assertEqual(result['type'], 'refresh_all')
        self.assertFalse(result['concurrently'])
    
    def test_parse_refresh_all_concurrently(self):
        """Test parse REFRESH ALL MATERIALIZED VIEWS CONCURRENTLY."""
        result = parse_refresh_command("REFRESH ALL MATERIALIZED VIEWS CONCURRENTLY")
        
        self.assertEqual(result['type'], 'refresh_all')
        self.assertTrue(result['concurrently'])
    
    def test_parse_schedule(self):
        """Test parse REFRESH SCHEDULE."""
        result = parse_refresh_command("REFRESH SCHEDULE view1 EVERY 5 MINUTES")
        
        self.assertEqual(result['type'], 'schedule')
        self.assertEqual(result['view_name'], 'view1')
        self.assertEqual(result['interval_minutes'], 5)
    
    def test_parse_unknown(self):
        """Test parse unknown command."""
        result = parse_refresh_command("SOME OTHER COMMAND")
        
        self.assertEqual(result['type'], 'unknown')


class TestRefreshMetrics(unittest.TestCase):
    """Test refresh metrics."""
    
    def test_avg_refresh_time(self):
        """Test average refresh time calculation."""
        from batch_materialized_views import RefreshMetrics
        
        metrics = RefreshMetrics()
        self.assertEqual(metrics.avg_refresh_time_ms, 0.0)
        
        metrics.total_refreshes = 2
        metrics.total_refresh_time_ms = 100.0
        
        self.assertEqual(metrics.avg_refresh_time_ms, 50.0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
