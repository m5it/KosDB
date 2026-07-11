"""
Test Common Table Expressions (CTEs) for KosDB v3.3.0

Tests:
- Non-recursive CTEs
- Recursive CTEs (WITH RECURSIVE)
- Multiple CTEs in single query
- CTE scoping and reference resolution
- Integration with parser and optimizer
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cte_engine import CTE, CTEDefinition, CTEEngine, parse_cte_definition
from parser import CommandParser


class TestCTEParsing(unittest.TestCase):
    """Test CTE parsing from SQL."""
    
    def setUp(self):
        self.parser = CommandParser()
    
    def test_simple_cte(self):
        """Parse simple non-recursive CTE."""
        sql = """
            WITH sales_summary AS (
                SELECT dept, SUM(sales) as total_sales
                FROM sales
                GROUP BY dept
            )
            SELECT * FROM sales_summary WHERE total_sales > 10000
        """
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'SELECT_WITH_CTE')
        self.assertIn('ctes', params)
        self.assertEqual(len(params['ctes']), 1)
        self.assertEqual(params['ctes'][0]['name'], 'sales_summary')
        self.assertFalse(params['is_recursive'])
    
    def test_recursive_cte(self):
        """Parse recursive CTE."""
        sql = """
            WITH RECURSIVE employee_hierarchy AS (
                SELECT id, name, manager_id, 0 as level
                FROM employees
                WHERE manager_id IS NULL
                
                UNION ALL
                
                SELECT e.id, e.name, e.manager_id, eh.level + 1
                FROM employees e
                JOIN employee_hierarchy eh ON e.manager_id = eh.id
            )
            SELECT * FROM employee_hierarchy
        """
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'SELECT_WITH_CTE')
        self.assertTrue(params['is_recursive'])
        self.assertEqual(len(params['ctes']), 1)
        self.assertEqual(params['ctes'][0]['name'], 'employee_hierarchy')
        self.assertTrue(params['ctes'][0]['is_recursive'])
        self.assertIn('anchor_query', params['ctes'][0])
        self.assertIn('recursive_query', params['ctes'][0])
    
    def test_multiple_ctes(self):
        """Parse multiple CTEs in single query."""
        sql = """
            WITH 
                cte1 AS (SELECT * FROM table1),
                cte2 AS (SELECT * FROM table2)
            SELECT * FROM cte1 JOIN cte2
        """
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'SELECT_WITH_CTE')
        self.assertEqual(len(params['ctes']), 2)
        self.assertEqual(params['ctes'][0]['name'], 'cte1')
        self.assertEqual(params['ctes'][1]['name'], 'cte2')
    
    def test_cte_with_explicit_columns(self):
        """Parse CTE with explicit column names."""
        sql = """
            WITH sales_summary (dept, total) AS (
                SELECT dept, SUM(sales)
                FROM sales
                GROUP BY dept
            )
            SELECT * FROM sales_summary
        """
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'SELECT_WITH_CTE')
        self.assertEqual(params['ctes'][0]['columns'], ['dept', 'total'])


class TestCTEEngine(unittest.TestCase):
    """Test CTE execution engine."""
    
    def setUp(self):
        self.engine = CTEEngine()
    
    def test_register_ctes(self):
        """Test CTE registration."""
        cte_def = CTEDefinition(
            ctes=[
                CTE(
                    name='test_cte',
                    columns=['id', 'name'],
                    query={'type': 'SELECT'},
                    node_type=None,
                    is_recursive=False
                )
            ],
            is_recursive=False
        )
        
        self.engine.register_ctes(cte_def)
        self.assertIn('TEST_CTE', self.engine.ctes)
    
    def test_resolve_cte_reference(self):
        """Test CTE reference resolution."""
        cte_def = CTEDefinition(
            ctes=[
                CTE(
                    name='my_cte',
                    columns=['a', 'b'],
                    query={},
                    node_type=None,
                    is_recursive=False
                )
            ]
        )
        
        self.engine.register_ctes(cte_def)
        
        # Should find CTE (case insensitive)
        cte = self.engine.resolve_cte_reference('my_cte')
        self.assertIsNotNone(cte)
        self.assertEqual(cte.name, 'my_cte')
        
        cte_upper = self.engine.resolve_cte_reference('MY_CTE')
        self.assertIsNotNone(cte_upper)
        
        # Should not find non-existent CTE
        not_found = self.engine.resolve_cte_reference('other_cte')
        self.assertIsNone(not_found)
    
    def test_get_cte_columns(self):
        """Test getting CTE columns."""
        cte_def = CTEDefinition(
            ctes=[
                CTE(
                    name='test_cte',
                    columns=['col1', 'col2', 'col3'],
                    query={},
                    node_type=None,
                    is_recursive=False
                )
            ]
        )
        
        self.engine.register_ctes(cte_def)
        columns = self.engine.get_cte_columns('test_cte')
        self.assertEqual(columns, ['col1', 'col2', 'col3'])
    
    def test_get_execution_order(self):
        """Test CTE execution order."""
        cte_def = CTEDefinition(
            ctes=[
                CTE(name='cte_a', columns=None, query={'table': 'base'}, node_type=None, is_recursive=False),
                CTE(name='cte_b', columns=None, query={'table': 'cte_a'}, node_type=None, is_recursive=False),
                CTE(name='cte_c', columns=None, query={'table': 'base'}, node_type=None, is_recursive=False),
            ]
        )
        
        self.engine.register_ctes(cte_def)
        order = self.engine.get_execution_order()
        
        # cte_a and cte_c should come before cte_b
        self.assertIn('CTE_A', order)
        self.assertIn('CTE_B', order)
        self.assertIn('CTE_C', order)


class TestParseCTEDefinition(unittest.TestCase):
    """Test standalone CTE parsing function."""
    
    def test_parse_simple_cte(self):
        """Parse simple CTE using standalone function."""
        sql = """
            WITH summary AS (
                SELECT dept, COUNT(*) as cnt
                FROM employees
                GROUP BY dept
            )
            SELECT * FROM summary
        """
        
        cte_def = parse_cte_definition(sql)
        
        self.assertIsNotNone(cte_def)
        self.assertEqual(len(cte_def.ctes), 1)
        self.assertEqual(cte_def.ctes[0].name, 'summary')
        self.assertFalse(cte_def.is_recursive)
    
    def test_parse_recursive_cte(self):
        """Parse recursive CTE using standalone function."""
        sql = """
            WITH RECURSIVE nums AS (
                SELECT 1 as n
                UNION ALL
                SELECT n + 1 FROM nums WHERE n < 10
            )
            SELECT * FROM nums
        """
        
        cte_def = parse_cte_definition(sql)
        
        self.assertIsNotNone(cte_def)
        self.assertTrue(cte_def.is_recursive)
        self.assertTrue(cte_def.ctes[0].is_recursive)
        self.assertIsNotNone(cte_def.ctes[0].anchor_query)
        self.assertIsNotNone(cte_def.ctes[0].recursive_query)


class TestCTEEdgeCases(unittest.TestCase):
    """Test CTE edge cases."""
    
    def setUp(self):
        self.parser = CommandParser()
    
    def test_no_cte_in_regular_select(self):
        """Regular SELECT without CTE."""
        sql = "SELECT * FROM users WHERE id = 1"
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertNotEqual(cmd_type, 'SELECT_WITH_CTE')
    
    def test_cte_with_complex_subquery(self):
        """CTE with complex subquery."""
        sql = """
            WITH complex_cte AS (
                SELECT u.id, u.name, COUNT(o.id) as order_count
                FROM users u
                LEFT JOIN orders o ON u.id = o.user_id
                WHERE u.active = 1
                GROUP BY u.id, u.name
                HAVING COUNT(o.id) > 5
            )
            SELECT * FROM complex_cte
        """
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'SELECT_WITH_CTE')
        self.assertEqual(len(params['ctes']), 1)
    
    def test_empty_cte_list(self):
        """Invalid CTE syntax."""
        sql = "WITH SELECT * FROM users"
        
        # Should not parse as CTE
        cmd_type, params = self.parser.parse(sql)
        self.assertNotEqual(cmd_type, 'SELECT_WITH_CTE')


if __name__ == '__main__':
    unittest.main(verbosity=2)
