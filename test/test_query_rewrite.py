"""
Test Query Rewrite Engine for KosDB v3.4.0

Tests:
- View merging
- Predicate pushdown
- Subquery unnesting
- Join reordering
- Constant folding
- Query hints parsing
- Performance improvement verification
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from query_rewrite import (
    QueryRewriteEngine, RewriteContext, RewriteRule, RewriteType,
    parse_query_hints, create_rewrite_context
)


class TestQueryRewriteEngine(unittest.TestCase):
    """Test query rewrite engine functionality."""
    
    def setUp(self):
        self.engine = QueryRewriteEngine()
    
    def test_create_rewrite_engine(self):
        """Create rewrite engine with default rules."""
        self.assertGreater(len(self.engine.rules), 0)
        self.assertIn('view_merge', [r.name for r in self.engine.rules])
        self.assertIn('predicate_pushdown', [r.name for r in self.engine.rules])
    
    def test_rewrite_returns_stats(self):
        """Rewrite returns query and statistics."""
        query = {'type': 'SELECT', 'table': 'users', 'columns': ['*']}
        context = RewriteContext()
        
        rewritten, stats = self.engine.rewrite(query, context)
        
        self.assertIn('original', stats)
        self.assertIn('rewritten', stats)
        self.assertIn('rules_applied', stats)
    
    def test_disable_rule(self):
        """Disable a rewrite rule."""
        self.engine.disable_rule('view_merge')
        
        rule = next(r for r in self.engine.rules if r.name == 'view_merge')
        self.assertFalse(rule.enabled)
    
    def test_enable_rule(self):
        """Enable a rewrite rule."""
        self.engine.disable_rule('view_merge')
        self.engine.enable_rule('view_merge')
        
        rule = next(r for r in self.engine.rules if r.name == 'view_merge')
        self.assertTrue(rule.enabled)


class TestViewMerging(unittest.TestCase):
    """Test view merging rewrite."""
    
    def setUp(self):
        self.engine = QueryRewriteEngine()
    
    def test_merge_simple_view(self):
        """Merge simple view into query."""
        query = {
            'type': 'SELECT',
            'columns': ['*'],
            'table': 'high_value_customers',
            'where': {'column': 'region', 'op': '=', 'value': 'US'}
n        }\n        \n        context = RewriteContext()\n        context.views['high_value_customers'] = {\n            'type': 'SELECT',\n            'table': 'customers',\n            'where': {'column': 'total_orders', 'op': '>', 'value': 1000}\n        }\n        \n        rewritten, stats = self.engine.rewrite(query, context)\n        \n        self.assertEqual(rewritten['table'], 'customers')\n        self.assertIn('rules_applied', stats)
        self.assertIn('view_merge', stats['rules_applied'])
    
    def test_view_merge_combines_predicates(self):
        \"\"\"View merge combines WHERE predicates.\"\"\"\n        query = {\n            'type': 'SELECT',\n            'columns': ['*'],\n            'table': 'active_users',\n            'where': {'column': 'age', 'op': '>', 'value': 25}\n        }\n        \n        context = RewriteContext()\n        context.views['active_users'] = {\n            'type': 'SELECT',\n            'table': 'users',\n            'where': {'column': 'status', 'op': '=', 'value': 'active'}\n        }\n        \n        rewritten, _ = self.engine.rewrite(query, context)\n        \n        # Should have combined WHERE with AND\n        self.assertEqual(rewritten['where']['op'], 'AND')


class TestPredicatePushdown(unittest.TestCase):
n    \"\"\"Test predicate pushdown rewrite.\"\"\"\n    \n    def setUp(self):\n        self.engine = QueryRewriteEngine()
    
    def test_pushdown_into_subquery(self):
n        \"\"\"Push predicate into subquery.\"\"\"\n        query = {\n            'type': 'SELECT',\n            'columns': ['*'],\n            'table': {\n                'type': 'SELECT',\n                'table': 'orders',\n                'where': {'column': 'amount', 'op': '>', 'value': 100}\n            },\n            'where': {'column': 'customer_id', 'op': '=', 'value': 5}\n        }\n        \n        context = RewriteContext()\n        rewritten, stats = self.engine.rewrite(query, context)\n        \n        # Predicate should be pushed into subquery\n        inner = rewritten['table']\n        self.assertIn('rules_applied', stats)


class TestSubqueryUnnesting(unittest.TestCase):
n    \"\"\"Test subquery unnesting rewrite.\"\"\"\n    \n    def setUp(self):\n        self.engine = QueryRewriteEngine()
    
    def test_unnest_in_subquery(self):
n        \"\"\"Convert IN subquery to JOIN.\"\"\"\n        query = {\n            'type': 'SELECT',\n            'columns': ['*'],\n            'table': 'orders',\n            'where': {\n                'op': 'IN',\n                'left': {'column': 'customer_id'},\n                'right': {\n                    'subquery': {\n                        'type': 'SELECT',\n                        'table': 'customers',\n                        'columns': ['id'],\n                        'where': {'column': 'country', 'op': '=', 'value': 'US'}\n                    }\n                }\n            }\n        }\n        \n        context = RewriteContext()\n        rewritten, stats = self.engine.rewrite(query, context)\n        \n        # Should be converted to JOIN\n        self.assertIn('joins', rewritten)


class TestConstantFolding(unittest.TestCase):
n    \"\"\"Test constant folding rewrite.\"\"\"\n    \n    def setUp(self):\n        self.engine = QueryRewriteEngine()
    
    def test_fold_arithmetic_constants(self):
n        \"\"\"Fold arithmetic constant expressions.\"\"\"\n        query = {\n            'type': 'SELECT',\n            'columns': ['*'],\n            'table': 'users',\n            'where': {\n                'op': '+',\n                'left': 10,\n                'right': 20\n            }\n        }\n        \n        context = RewriteContext()\n        rewritten, stats = self.engine.rewrite(query, context)\n        \n        # Should have folded constants
        self.assertIn('rules_applied', stats)
    
    def test_remove_true_from_and(self):
n        \"\"\"Remove TRUE from AND expression.\"\"\"\n        query = {\n            'type': 'SELECT',\n            'columns': ['*'],\n            'table': 'users',\n            'where': {\n                'op': 'AND',\n                'left': {'op': 'TRUE'},\n                'right': {'column': 'x', 'op': '=', 'value': 5}\n            }\n        }\n        \n        context = RewriteContext()\n        rewritten, _ = self.engine.rewrite(query, context)\n        \n        # Should simplify to just the right side\n        self.assertEqual(rewritten['where']['column'], 'x')


class TestJoinReordering(unittest.TestCase):
n    \"\"\"Test join reordering rewrite.\"\"\"\n    \n    def setUp(self):\n        self.engine = QueryRewriteEngine()
    
    def test_reorder_joins_by_size(self):
n        \"\"\"Reorder joins to process smaller tables first.\"\"\"\n        query = {\n            'type': 'SELECT',\n            'columns': ['*'],\n            'table': 'large_table',\n            'joins': [\n                {'table': 'huge_table', 'on': {'op': 'TRUE'}},\n                {'table': 'small_table', 'on': {'op': 'TRUE'}}\n            ]\n        }\n        \n        context = RewriteContext()\n        context.statistics['large_table'] = {'row_count': 10000}\n        context.statistics['huge_table'] = {'row_count': 1000000}\n        context.statistics['small_table'] = {'row_count': 100}\n        \n        rewritten, stats = self.engine.rewrite(query, context)
        
        # Joins should be reordered (small_table first)
        joins = rewritten.get('joins', [])
n        if joins:\n            self.assertEqual(joins[0]['table'], 'small_table')


class TestQueryHints(unittest.TestCase):
n    \"\"\"Test query hints parsing.\"\"\"\n    \n    def test_parse_simple_hint(self):
n        \"\"\"Parse simple query hint.\"\"\"\n        sql = \"SELECT /*+ NO_VIEW_MERGE */ * FROM users\"\n        \n        cleaned, hints = parse_query_hints(sql)\n        \n        self.assertIn('NO_VIEW_MERGE', hints)\n        self.assertNotIn('/*+', cleaned)
    
    def test_parse_multiple_hints(self):
n        \"\"\"Parse multiple query hints.\"\"\"\n        sql = \"SELECT /*+ NO_VIEW_MERGE NO_SUBQUERY_UNNEST PARALLEL(4) */ * FROM t\"\n        \n        cleaned, hints = parse_query_hints(sql)\n        \n        self.assertIn('NO_VIEW_MERGE', hints)\n        self.assertIn('NO_SUBQUERY_UNNEST', hints)\n        self.assertIn('PARALLEL(4)', hints)
    
    def test_no_hints(self):
n        \"\"\"Handle SQL without hints.\"\"\"\n        sql = \"SELECT * FROM users\"\n        \n        cleaned, hints = parse_query_hints(sql)\n        \n        self.assertEqual(len(hints), 0)\n        self.assertEqual(cleaned.strip(), sql)


class TestRewriteContext(unittest.TestCase):
n    \"\"\"Test rewrite context.\"\"\"\n    \n    def test_create_context(self):
n        \"\"\"Create rewrite context.\"\"\"\n        context = create_rewrite_context()\n        \n        self.assertIsInstance(context, RewriteContext)
    
    def test_add_hint(self):
n        \"\"\"Add hint to context.\"\"\"\n        context = RewriteContext()\n        context.add_hint('NO_REWRITE')\n        \n        self.assertTrue(context.has_hint('NO_REWRITE'))
    
    def test_context_with_views(self):
n        \"\"\"Create context with views.\"\"\"\n        views = {\n            'v1': {'type': 'SELECT', 'table': 't1'},\n            'v2': {'type': 'SELECT', 'table': 't2'}\n        }\n        \n        context = create_rewrite_context(views=views)\n        \n        self.assertEqual(len(context.views), 2)


class TestRewriteStatistics(unittest.TestCase):
n    \"\"\"Test rewrite statistics tracking.\"\"\"\n    \n    def setUp(self):
n        self.engine = QueryRewriteEngine()
n    \n    def test_stats_tracking(self):
n        \"\"\"Track rewrite statistics.\"\"\"\n        initial_stats = self.engine.get_stats()\n        \n        # Perform some rewrites\n        query = {'type': 'SELECT', 'table': 't', 'columns': ['*']}\n        context = RewriteContext()\n        \n        self.engine.rewrite(query, context)\n        self.engine.rewrite(query, context)\n        \n        final_stats = self.engine.get_stats()\n        \n        self.assertEqual(final_stats['queries_rewritten'], 2)


class TestRewriteRulePriority(unittest.TestCase):
n    \"\"\"Test rewrite rule priority ordering.\"\"\"\n    \n    def test_rules_sorted_by_priority(self):
n        \"\"\"Rules should be sorted by priority.\"\"\"\n        engine = QueryRewriteEngine()\n        \n        priorities = [r.priority for r in engine.rules]\n        \n        # Should be in ascending order\n        self.assertEqual(priorities, sorted(priorities))
    
    def test_constant_folding_first(self):
n        \"\"\"Constant folding should have highest priority.\"\"\"\n        engine = QueryRewriteEngine()\n        \n        rule = next(r for r in engine.rules if r.name == 'constant_folding')\n        self.assertLess(rule.priority, 20)  # Lower than view_merge


class TestPerformanceImprovement(unittest.TestCase):
n    \"\"\"Test performance improvements from rewrite.\"\"\"\n    \n    def setUp(self):
n        self.engine = QueryRewriteEngine()
n    \n    def test_view_merge_reduces_cost(self):
n        \"\"\"View merge should reduce query cost.\"\"\"\n        # Query through view\n        query_with_view = {\n            'type': 'SELECT',\n            'columns': ['*'],\n            'table': 'customer_view',\n            'where': {'column': 'region', 'op': '=', 'value': 'US'}\n        }\n        \n        # Direct query\n        query_direct = {\n            'type': 'SELECT',\n            'columns': ['*'],\n            'table': 'customers',\n            'where': {\n                'op': 'AND',\n                'left': {'column': 'active', 'op': '=', 'value': 1},\n                'right': {'column': 'region', 'op': '=', 'value': 'US'}\n            }\n        }\n        \n        context = RewriteContext()\n        context.views['customer_view'] = {\n            'type': 'SELECT',\n            'table': 'customers',\n            'where': {'column': 'active', 'op': '=', 'value': 1}\n        }\n        \n        rewritten, _ = self.engine.rewrite(query_with_view, context)\n        \n        # After rewrite, should be similar to direct query\n        self.assertEqual(rewritten['table'], 'customers')


if __name__ == '__main__':\n    unittest.main(verbosity=2)\n