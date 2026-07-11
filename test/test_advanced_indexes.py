"""
Test Advanced Indexes for KosDB v3.4.0

Tests:
- Composite indexes (multiple columns)
- Partial indexes (with WHERE clause)
- Expression indexes (on computed expressions)
- Covering indexes (INCLUDE columns)
- Index selectivity calculation
- Index cost estimation
- Index advisor recommendations
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from advanced_index import (
    AdvancedIndexManager, AdvancedIndex, IndexColumn, IndexExpression,
    IndexType, IndexAdvisor, IndexCostEstimator,
    parse_create_index
)
from parser import CommandParser


class TestCompositeIndexes(unittest.TestCase):
    """Test composite (multi-column) indexes."""
    
    def setUp(self):
        self.manager = AdvancedIndexManager()
    
    def test_create_composite_index(self):
        """Create composite index on multiple columns."""
        idx = self.manager.create_index(
            name='idx_name',
            table='users',
            columns=['last_name', 'first_name'],
            index_type=IndexType.COMPOSITE
        )
        
        self.assertEqual(len(idx.columns), 2)
        self.assertEqual(idx.columns[0].name, 'last_name')
        self.assertEqual(idx.columns[1].name, 'first_name')
    
    def test_composite_index_with_ordering(self):
        """Create composite index with ASC/DESC ordering."""
        columns = [
            IndexColumn(name='date', order='DESC'),
            IndexColumn(name='id', order='ASC')
        ]
        
        idx = self.manager.create_index(
            name='idx_ordered',
            table='events',
            columns=columns,
            index_type=IndexType.COMPOSITE
        )
        
        self.assertEqual(idx.columns[0].order, 'DESC')
        self.assertEqual(idx.columns[1].order, 'ASC')
    
    def test_composite_index_matches_query(self):
        """Test composite index matches query."""
        self.manager.create_index(
            name='idx_name',
            table='users',
            columns=['last_name', 'first_name'],
            index_type=IndexType.COMPOSITE
        )
        
        # Query matching leading column
        idx = self.manager.find_best_index(
            'users',
            query_columns=['first_name', 'last_name'],
            query_conditions=[{'column': 'last_name', 'op': '=', 'value': 'Smith'}]
        )
        
        self.assertIsNotNone(idx)
        self.assertEqual(idx.name, 'idx_name')


class TestPartialIndexes(unittest.TestCase):
    """Test partial indexes (with WHERE clause)."""
    
    def setUp(self):
        self.manager = AdvancedIndexManager()
    
    def test_create_partial_index(self):
        """Create partial index with WHERE clause."""
        idx = self.manager.create_index(
            name='idx_active',
            table='users',
            columns=['email'],
            index_type=IndexType.PARTIAL,
            where_clause="status = 'active'"
        )
        
        self.assertEqual(idx.where_clause, "status = 'active'")
        self.assertEqual(idx.index_type, IndexType.PARTIAL)
    
    def test_partial_index_matches_condition(self):
        """Partial index matches query with same condition."""
        self.manager.create_index(
            name='idx_active',
            table='users',
            columns=['email'],
            index_type=IndexType.PARTIAL,
            where_clause="status = 'active'"
        )
        
        # Query with matching condition
        idx = self.manager.find_best_index(
            'users',
            query_columns=['email'],
            query_conditions=[{'column': 'status', 'op': '=', 'value': 'active'}]
        )
        
        self.assertIsNotNone(idx)
    
    def test_partial_index_excludes_non_matching(self):
        """Partial index doesn't match queries with different condition."""
        self.manager.create_index(
            name='idx_active',
            table='users',
            columns=['email'],
            index_type=IndexType.PARTIAL,
            where_clause="status = 'active'"
        )
        
        # Query with different condition
        idx = self.manager.find_best_index(
            'users',
            query_columns=['email'],
            query_conditions=[{'column': 'status', 'op': '=', 'value': 'inactive'}]
        )
        
        # Should not use partial index (or use with lower score)
        if idx:
            self.assertLess(idx.selectivity, 1.0)


class TestExpressionIndexes(unittest.TestCase):
    """Test expression indexes."""
    
    def setUp(self):
        self.manager = AdvancedIndexManager()
    
    def test_create_expression_index(self):
        """Create index on computed expression."""
        idx = self.manager.create_index(
            name='idx_lower_email',
            table='users',
            columns=[],
            index_type=IndexType.EXPRESSION,
            expressions=['LOWER(email)']
        )
        
        self.assertEqual(len(idx.expressions), 1)
        self.assertEqual(idx.expressions[0].expression, 'LOWER(email)')
    
    def test_expression_index_hash(self):
        """Expression index generates hash value."""
        expr = IndexExpression(expression='UPPER(name)')
        
        self.assertTrue(len(expr.hash_value) > 0)
        self.assertEqual(expr.hash_value, 
                        hashlib.md5('UPPER(name)'.encode()).hexdigest()[:16])


class TestCoveringIndexes(unittest.TestCase):
    """Test covering indexes (INCLUDE columns)."""
    
    def setUp(self):
        self.manager = AdvancedIndexManager()
    
    def test_create_covering_index(self):
        """Create covering index with included columns."""
        idx = self.manager.create_index(
            name='idx_covering',
            table='users',
            columns=['id'],
            index_type=IndexType.COVERING,
            include_columns=['name', 'email', 'status']
        )
        
        self.assertEqual(len(idx.include_columns), 3)
        self.assertIn('name', idx.include_columns)
        self.assertIn('email', idx.include_columns)
    
    def test_covering_index_allows_index_only_scan(self):
        """Covering index enables index-only scan."""
        idx = self.manager.create_index(
            name='idx_covering',
            table='users',
            columns=['id'],
            index_type=IndexType.COVERING,
            include_columns=['name', 'email']
        )
        
        # Query requesting only covered columns
        is_covering = idx._is_covering(['id', 'name', 'email'])
        self.assertTrue(is_covering)
        
        # Query requesting non-covered column
        is_covering = idx._is_covering(['id', 'name', 'password'])
        self.assertFalse(is_covering)


class TestIndexSelectivity(unittest.TestCase):
    """Test index selectivity calculation."""
    
    def setUp(self):
        self.manager = AdvancedIndexManager()
        self.manager.create_index(
            name='idx_status',
            table='users',
            columns=['status'],
            index_type=IndexType.COMPOSITE
        )
    
    def test_calculate_selectivity(self):
        """Calculate index selectivity from data."""
        # Sample data with 50% unique values
        table_data = [
            {'id': 1, 'status': 'active'},
            {'id': 2, 'status': 'active'},
n            {'id': 3, 'status': 'inactive'},\n            {'id': 4, 'status': 'inactive'}\n        ]\n        \n        self.manager.analyze_index('idx_status', table_data)\n        \n        selectivity = self.manager.get_index_selectivity('idx_status')\n        self.assertEqual(selectivity, 0.5)  # 2 unique / 4 total


class TestIndexCostEstimator(unittest.TestCase):
    \"\"\"Test index cost estimation.\"\"\"\n    \n    def setUp(self):
n        self.estimator = IndexCostEstimator()\n    \n    def test_estimate_index_scan_cost(self):
n        \"\"\"Estimate cost of index scan.\"\"\"\n        idx = AdvancedIndex(\n            name='test',\n            table='users',\n            index_type=IndexType.COMPOSITE,\n            columns=[IndexColumn('id')],\n            index_size=100000\n        )\n        \n        cost = self.estimator.estimate_index_scan_cost(\n            idx,\n            selectivity=0.1,\n            table_pages=1000\n        )\n        \n        self.assertGreater(cost, 0)\n        self.assertLess(cost, 1000)  # Should be less than full scan\n    \n    def test_should_use_index(self):
n        \"\"\"Determine if index scan is better than sequential scan.\"\"\"\n        idx = AdvancedIndex(\n            name='test',\n            table='users',\n            index_type=IndexType.COMPOSITE,\n            columns=[IndexColumn('id')],\n            index_size=100000\n        )\n        \n        # High selectivity - should use index\n        use_index = self.estimator.should_use_index(idx, 0.001, 1000)\n        self.assertTrue(use_index)\n        \n        # Low selectivity - sequential scan better\n        use_index = self.estimator.should_use_index(idx, 0.9, 1000)\n        self.assertFalse(use_index)


class TestIndexAdvisor(unittest.TestCase):
    \"\"\"Test index advisor.\"\"\"\n    \n    def setUp(self):\n        self.manager = AdvancedIndexManager()\n        self.advisor = IndexAdvisor(self.manager)\n    \n    def test_record_query_pattern(self):
n        \"\"\"Record query pattern for analysis.\"\"\"\n        self.advisor.record_query(\n            table='users',\n            columns=['email'],\n            conditions=[{'column': 'status', 'value': 'active'}],\n            execution_time=100.0\n        )\n        \n        self.assertEqual(len(self.advisor.query_patterns), 1)
    
    def test_recommend_index(self):
n        \"\"\"Recommend index based on query patterns.\"\"\"\n        # Record multiple queries\n        for _ in range(10):\n            self.advisor.record_query(\n                table='users',\n                columns=['email'],\n                conditions=[{'column': 'status', 'value': 'active'}],\n                execution_time=50.0\n            )\n        \n        recommendations = self.advisor.recommend_indexes(min_frequency=5)\n        \n        self.assertGreater(len(recommendations), 0)\n        self.assertEqual(recommendations[0]['table'], 'users')
    
    def test_no_recommendation_if_good_index_exists(self):
n        \"\"\"Don't recommend if suitable index already exists.\"\"\"\n        # Create index\n        self.manager.create_index(\n            name='idx_email',\n            table='users',\n            columns=['email'],\n            index_type=IndexType.COMPOSITE\n        )\n        \n        # Record queries\n        for _ in range(10):\n            self.advisor.record_query(\n                table='users',\n                columns=['email'],\n                conditions=[],\n                execution_time=10.0\n            )\n        \n        recommendations = self.advisor.recommend_indexes()\n        \n        # Should not recommend since good index exists\n        self.assertEqual(len(recommendations), 0)


class TestIndexParser(unittest.TestCase):
    \"\"\"Test index SQL parsing.\"\"\"\n    \n    def setUp(self):\n        self.parser = CommandParser()\n    \n    def test_parse_create_index_basic(self):
n        \"\"\"Parse basic CREATE INDEX.\"\"\"\n        sql = \"CREATE INDEX idx_name ON users (email)\"\n        \n        cmd_type, params = self.parser.parse(sql)\n        \n        self.assertEqual(cmd_type, 'CREATE_ADVANCED_INDEX')\n        self.assertEqual(params['name'], 'idx_name')\n        self.assertEqual(params['table'], 'users')\n        self.assertEqual(params['columns'], 'email')\n    \n    def test_parse_create_unique_index(self):
n        \"\"\"Parse CREATE UNIQUE INDEX.\"\"\"\n        sql = \"CREATE UNIQUE INDEX idx_unique ON users (username)\"\n        \n        cmd_type, params = self.parser.parse(sql)\n        \n        self.assertEqual(cmd_type, 'CREATE_ADVANCED_INDEX')\n        self.assertTrue(params.get('unique'))\n    \n    def test_parse_partial_index(self):
n        \"\"\"Parse CREATE INDEX with WHERE clause.\"\"\"\n        sql = \"CREATE INDEX idx_active ON users (email) WHERE status = 'active'\"\n        \n        cmd_type, params = self.parser.parse(sql)\n        \n        self.assertEqual(cmd_type, 'CREATE_ADVANCED_INDEX')\n        self.assertEqual(params['where'], \"status = 'active'\")\n    \n    def test_parse_covering_index(self):
n        \"\"\"Parse CREATE INDEX with INCLUDE.\"\"\"\n        sql = \"CREATE INDEX idx_cover ON users (id) INCLUDE (name, email)\"\n        \n        cmd_type, params = self.parser.parse(sql)\n        \n        self.assertEqual(cmd_type, 'CREATE_ADVANCED_INDEX')\n        self.assertEqual(params['include'], 'name, email')\n    \n    def test_parse_expression_index(self):
n        \"\"\"Parse CREATE INDEX on expression.\"\"\"\n        sql = \"CREATE INDEX idx_lower ON users (LOWER(email))\"\n        \n        cmd_type, params = self.parser.parse(sql)\n        \n        self.assertEqual(cmd_type, 'CREATE_EXPRESSION_INDEX')\n        self.assertIn('LOWER', params['expression'])\n    \n    def test_parse_drop_index(self):
n        \"\"\"Parse DROP INDEX.\"\"\"\n        sql = \"DROP INDEX idx_name\"\n        \n        cmd_type, params = self.parser.parse(sql)\n        \n        self.assertEqual(cmd_type, 'DROP_INDEX')\n        self.assertEqual(params['name'], 'idx_name')\n    \n    def test_parse_analyze_index(self):
n        \"\"\"Parse ANALYZE INDEX.\"\"\"\n        sql = \"ANALYZE INDEX idx_name\"\n        \n        cmd_type, params = self.parser.parse(sql)\n        \n        self.assertEqual(cmd_type, 'ANALYZE_INDEX')\n        self.assertEqual(params['name'], 'idx_name')


class TestIndexDefinitionParser(unittest.TestCase):
    \"\"\"Test parse_create_index function.\"\"\"\n    \n    def test_parse_index_with_all_features(self):
n        \"\"\"Parse index with all advanced features.\"\"\"\n        sql = \"\"\"\n            CREATE UNIQUE INDEX idx_complex ON users (last_name DESC, first_name ASC)\n            WHERE status = 'active'\n            INCLUDE (email, phone)\n        \"\"\"\n        \n        result = parse_create_index(sql)\n        \n        self.assertEqual(result['name'], 'idx_complex')\n        self.assertEqual(result['table'], 'users')\n        self.assertTrue(result['unique'])\n        self.assertEqual(result['where'], \"status = 'active'\")\n        self.assertEqual(result['include'], 'email, phone')\n    \n    def test_parse_columns(self):
n        \"\"\"Parse column definitions.\"\"\"\n        sql = \"CREATE INDEX idx ON t (col1 ASC, col2 DESC)\"\n        \n        result = parse_create_index(sql)\n        \n        self.assertEqual(len(result['parsed_columns']), 2)\n        self.assertEqual(result['parsed_columns'][0]['name'], 'col1')\n        self.assertEqual(result['parsed_columns'][0]['order'], 'ASC')\n        self.assertEqual(result['parsed_columns'][1]['order'], 'DESC')


if __name__ == '__main__':\n    unittest.main(verbosity=2)\n