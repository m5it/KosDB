"""
Test Materialized Views for KosDB v3.4.0

Tests:
- CREATE MATERIALIZED VIEW
- REFRESH MATERIALIZED VIEW (complete and fast)
- DROP MATERIALIZED VIEW
- Query rewrite to use materialized views
- Staleness tracking
- Incremental refresh with change tracking
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from materialized_view_manager import (
    MaterializedViewManager, MaterializedView,
    RefreshType, RefreshTiming, BuildType, QueryRewriteRule,
    parse_create_materialized_view
)
from parser import CommandParser


class TestMaterializedViewCreation(unittest.TestCase):
    """Test materialized view creation."""
    
    def setUp(self):
        self.manager = MaterializedViewManager()
    
    def test_create_simple_mv(self):
        """Create simple materialized view."""
        mv = self.manager.create_materialized_view(
            name='mv_test',
            query='SELECT * FROM users',
            base_tables=['users'],
            columns=['id', 'name']
        )
        
        self.assertEqual(mv.name, 'mv_test')
        self.assertEqual(mv.base_tables, ['users'])
        self.assertEqual(mv.refresh_type, RefreshType.COMPLETE)
    
    def test_create_mv_with_refresh_options(self):
        """Create MV with refresh options."""
        mv = self.manager.create_materialized_view(
            name='mv_sales',
            query='SELECT region, SUM(amount) FROM sales GROUP BY region',
            base_tables=['sales'],
            columns=['region', 'total'],
            refresh_type='COMPLETE',
            refresh_timing='ON DEMAND',
            build_type='IMMEDIATE'
        )
        
        self.assertEqual(mv.refresh_type, RefreshType.COMPLETE)
        self.assertEqual(mv.refresh_timing, RefreshTiming.ON_DEMAND)
        self.assertEqual(mv.build_type, BuildType.IMMEDIATE)
    
    def test_create_mv_with_query_rewrite(self):
        """Create MV with query rewrite enabled."""
        mv = self.manager.create_materialized_view(
            name='mv_users',
            query='SELECT id, name, email FROM users',
            base_tables=['users'],
            columns=['id', 'name', 'email'],
            enable_query_rewrite=True
        )
        
        self.assertTrue(mv.enable_query_rewrite)
        self.assertIn('MV_USERS', self.manager.rewrite_rules)
    
    def test_create_duplicate_mv(self):
        """Cannot create duplicate materialized views."""
        self.manager.create_materialized_view(
            name='mv_unique',
            query='SELECT * FROM t',
            base_tables=['t'],
            columns=['id']
        )
        
        with self.assertRaises(ValueError) as context:
            self.manager.create_materialized_view(
                name='mv_unique',
                query='SELECT * FROM t2',
                base_tables=['t2'],
                columns=['id']
            )
        
        self.assertIn('already exists', str(context.exception))


class TestMaterializedViewRefresh(unittest.TestCase):
    """Test materialized view refresh."""
    
    def setUp(self):
        self.manager = MaterializedViewManager()
        self.mv = self.manager.create_materialized_view(
            name='mv_test',
            query='SELECT * FROM users',
            base_tables=['users'],
            columns=['id', 'name'],
            build_type='DEFERRED'  # Don't build immediately
        )
    
    def test_complete_refresh(self):
        """Complete refresh rebuilds from scratch."""
        # Mock data
        self.manager._execute_query = lambda q: [
            {'id': 1, 'name': 'Alice'},
            {'id': 2, 'name': 'Bob'}
        ]
        
        result = self.manager.refresh('mv_test', refresh_type='COMPLETE')
        
        self.assertEqual(result['refresh_type'], 'COMPLETE')
        self.assertEqual(result['rows_affected'], 2)
        self.assertTrue(result['success'])
        self.assertIsNotNone(self.mv.last_refresh)
        self.assertFalse(self.mv.is_stale)
    
    def test_fast_refresh(self):
        """Fast refresh applies incremental changes."""
        # Setup MV with data
        self.mv.data = [
            {'id': 1, 'name': 'Alice'},
            {'id': 2, 'name': 'Bob'}
        ]
        self.mv.row_count = 2
        
        # Record a change
        self.manager.record_change(
            table='users',
            operation='INSERT',
            new_data={'id': 3, 'name': 'Charlie'}
        )
        
        # Fast refresh
        result = self.manager.refresh('mv_test', refresh_type='FAST')
        
        self.assertEqual(result['refresh_type'], 'FAST')
        self.assertTrue(result['success'])
    
    def test_refresh_tracks_statistics(self):
        """Refresh updates statistics."""
        self.manager._execute_query = lambda q: [
            {'id': 1, 'name': 'Alice'}
        ]
        
        self.manager.refresh('mv_test')
        
        self.assertEqual(self.mv.refresh_count, 1)
        self.assertEqual(self.mv.row_count, 1)
    
    def test_concurrent_refresh(self):
        """Concurrent refresh allows queries during refresh."""
        self.manager._execute_query = lambda q: [{'id': 1}]
        
        result = self.manager.refresh('mv_test', concurrently=True)
        
        self.assertTrue(result['success'])


class TestMaterializedViewDrop(unittest.TestCase):
    """Test dropping materialized views."""
    
    def setUp(self):
        self.manager = MaterializedViewManager()
        self.manager.create_materialized_view(
            name='mv_temp',
            query='SELECT * FROM t',
            base_tables=['t'],
            columns=['id']
        )
    
    def test_drop_mv(self):
        """Drop materialized view."""
        success = self.manager.drop_materialized_view('mv_temp')
        
        self.assertTrue(success)
        self.assertNotIn('MV_TEMP', self.manager.views)
    
    def test_drop_nonexistent_mv(self):
        """Drop non-existent MV returns False."""
        success = self.manager.drop_materialized_view('nonexistent')
        
        self.assertFalse(success)


class TestQueryRewrite(unittest.TestCase):
    """Test query rewrite to use materialized views."""
    
    def setUp(self):
        self.manager = MaterializedViewManager()
        self.manager.create_materialized_view(
            name='mv_sales',
            query='SELECT region, SUM(amount) FROM sales GROUP BY region',
            base_tables=['sales'],
            columns=['region', 'total'],
            enable_query_rewrite=True
        )
    
    def test_can_rewrite_matching_query(self):
        """Rewrite query that matches MV."""
        query = "SELECT region, SUM(amount) FROM sales GROUP BY region"
        
        rewritten, was_rewritten = self.manager.try_rewrite_query(
            query, ['sales']
        )
        
        self.assertTrue(was_rewritten)
        self.assertIn('mv_sales', rewritten)
    
    def test_no_rewrite_for_stale_mv(self):
        """Don't rewrite if MV is stale and integrity is enforced."""
        self.manager.views['MV_SALES'].is_stale = True
        
        query = "SELECT region, SUM(amount) FROM sales GROUP BY region"
        
        rewritten, was_rewritten = self.manager.try_rewrite_query(
            query, ['sales']
        )
        
        self.assertFalse(was_rewritten)
    
    def test_no_rewrite_for_different_tables(self):
        """Don't rewrite if query uses different tables."""
        query = "SELECT * FROM orders"
        
        rewritten, was_rewritten = self.manager.try_rewrite_query(
            query, ['orders']
        )
        
        self.assertFalse(was_rewritten)


class TestChangeTracking(unittest.TestCase):
    """Test change tracking for fast refresh."""
    
    def setUp(self):
        self.manager = MaterializedViewManager()
        self.manager.create_materialized_view(
            name='mv_users',
            query='SELECT * FROM users',
            base_tables=['users'],
            columns=['id', 'name']
        )
    
    def test_record_insert(self):
        """Record INSERT operation."""
        self.manager.record_change(
            table='users',
            operation='INSERT',
            new_data={'id': 1, 'name': 'Alice'}
        )
        
        mv = self.manager.views['MV_USERS']
        self.assertEqual(len(mv.change_log), 1)
        self.assertEqual(mv.change_log[0]['operation'], 'INSERT')
        self.assertTrue(mv.is_stale)
    
    def test_record_delete(self):
        """Record DELETE operation."""
        self.manager.record_change(
            table='users',
            operation='DELETE',
            old_data={'id': 1, 'name': 'Alice'}
        )
        
        mv = self.manager.views['MV_USERS']
        self.assertEqual(len(mv.change_log), 1)
        self.assertEqual(mv.change_log[0]['operation'], 'DELETE')
    
    def test_record_update(self):
        """Record UPDATE operation."""
        self.manager.record_change(
            table='users',
            operation='UPDATE',
            old_data={'id': 1, 'name': 'Alice'},
            new_data={'id': 1, 'name': 'Alicia'}
        )
        
        mv = self.manager.views['MV_USERS']
        self.assertEqual(len(mv.change_log), 1)
        self.assertEqual(mv.change_log[0]['operation'], 'UPDATE')


class TestMaterializedViewParser(unittest.TestCase):
    """Test materialized view SQL parsing."""
    
    def setUp(self):
        self.parser = CommandParser()
    
    def test_parse_create_materialized_view(self):
        """Parse CREATE MATERIALIZED VIEW."""
        sql = """
            CREATE MATERIALIZED VIEW mv_sales
            BUILD IMMEDIATE
            REFRESH COMPLETE ON DEMAND
            ENABLE QUERY REWRITE
            AS
            SELECT region, SUM(amount) FROM sales GROUP BY region
        """
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'CREATE_MATERIALIZED_VIEW')
        self.assertEqual(params['name'], 'mv_sales')
        self.assertEqual(params['build'], 'IMMEDIATE')
        self.assertEqual(params['refresh'], 'COMPLETE')
        self.assertEqual(params['rewrite'], 'ENABLE')
    
    def test_parse_refresh_materialized_view(self):
        """Parse REFRESH MATERIALIZED VIEW."""
        sql = "REFRESH MATERIALIZED VIEW mv_sales"
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'REFRESH_MATERIALIZED_VIEW')
        self.assertEqual(params['name'], 'mv_sales')
    
    def test_parse_refresh_concurrently(self):
        """Parse REFRESH MATERIALIZED VIEW CONCURRENTLY."""
        sql = "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_sales"
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'REFRESH_MATERIALIZED_VIEW')
        self.assertEqual(params['name'], 'mv_sales')
        self.assertTrue(params.get('concurrently'))
    
    def test_parse_drop_materialized_view(self):
        """Parse DROP MATERIALIZED VIEW."""
        sql = "DROP MATERIALIZED VIEW mv_sales"
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'DROP_MATERIALIZED_VIEW')
        self.assertEqual(params['name'], 'mv_sales')
    
    def test_parse_show_materialized_views(self):
        """Parse SHOW MATERIALIZED VIEWS."""
        sql = "SHOW MATERIALIZED VIEWS"
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'SHOW_MATERIALIZED_VIEWS')


class TestMaterializedViewDefinitionParser(unittest.TestCase):
    """Test parse_create_materialized_view function."""
    
    def test_parse_mv_with_all_options(self):
        """Parse MV with all options."""
        sql = """
            CREATE MATERIALIZED VIEW mv_test
            BUILD DEFERRED
            REFRESH FAST ON COMMIT
            ENABLE QUERY REWRITE
            AS SELECT * FROM users
        """
        
        result = parse_create_materialized_view(sql)
        
        self.assertEqual(result['name'], 'mv_test')
        self.assertEqual(result['build'], 'DEFERRED')
        self.assertEqual(result['refresh_type'], 'FAST')
        self.assertTrue(result['enable_query_rewrite'])
    
    def test_parse_simple_mv(self):
        """Parse simple MV definition."""
        sql = "CREATE MATERIALIZED VIEW mv_simple AS SELECT * FROM t"
        
        result = parse_create_materialized_view(sql)
        
        self.assertEqual(result['name'], 'mv_simple')


class TestMaterializedViewStatistics(unittest.TestCase):
    """Test materialized view statistics."""
    
    def setUp(self):
        self.manager = MaterializedViewManager()
    
    def test_stats_tracking(self):
        """Track MV operations in stats."""
        # Create view
        self.manager.create_materialized_view(
            name='mv1',
            query='SELECT * FROM t',
            base_tables=['t'],
            columns=['id']
        )
        
        stats = self.manager.get_stats()
        self.assertEqual(stats['views_created'], 1)
        
        # Drop view
        self.manager.drop_materialized_view('mv1')
        stats = self.manager.get_stats()
        self.assertEqual(stats['views_dropped'], 1)


class TestMaterializedViewInfo(unittest.TestCase):
    """Test getting MV information."""
    
    def setUp(self):
        self.manager = MaterializedViewManager()
        self.manager.create_materialized_view(
            name='mv_info',
            query='SELECT * FROM users WHERE active = 1',
            base_tables=['users'],
            columns=['id', 'name'],
            refresh_type='COMPLETE',
            enable_query_rewrite=True
        )
    
    def test_get_view_info(self):
        """Get MV information."""
        info = self.manager.get_view_info('mv_info')
        
        self.assertEqual(info['name'], 'mv_info')
        self.assertEqual(info['base_tables'], ['users'])
        self.assertEqual(info['refresh_type'], 'COMPLETE')
        self.assertTrue(info['enable_query_rewrite'])
    
    def test_list_materialized_views(self):
        """List all materialized views."""
        views = self.manager.list_materialized_views()
        
        self.assertEqual(len(views), 1)
        self.assertEqual(views[0]['name'], 'mv_info')


if __name__ == '__main__':
    unittest.main(verbosity=2)
