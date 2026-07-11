"""
Test Window Functions for KosDB v3.3.0

Tests:
- ROW_NUMBER()
- RANK() and DENSE_RANK()
- LEAD() and LAG()
- FIRST_VALUE() and LAST_VALUE()
- OVER clause with PARTITION BY and ORDER BY
- Parser integration
"""

import unittest
import sys
import os
import tempfile
import shutil

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from window_functions import (
    WindowFunctionType, WindowFrame, WindowFunctionCall,
    WindowFunctionExecutor, parse_window_function
)
from parser import CommandParser


class TestWindowFunctionParser(unittest.TestCase):
    """Test window function parsing."""
    
    def setUp(self):
        self.parser = CommandParser()
    
    def test_parse_row_number(self):
        """Test parsing ROW_NUMBER()."""
        sql = "SELECT ROW_NUMBER() OVER (ORDER BY id) FROM users"
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'SELECT')
        columns = params.get('columns', [])
        
        # Find window function column
        window_cols = [c for c in columns if isinstance(c, dict) and c.get('type') == 'WINDOW_FUNCTION']
        self.assertEqual(len(window_cols), 1)
        self.assertEqual(window_cols[0]['function'], 'ROW_NUMBER')
    
    def test_parse_rank(self):
        """Test parsing RANK()."""
        sql = "SELECT RANK() OVER (PARTITION BY dept ORDER BY salary DESC) FROM employees"
        cmd_type, params = self.parser.parse(sql)
        
        columns = params.get('columns', [])
        window_cols = [c for c in columns if isinstance(c, dict) and c.get('type') == 'WINDOW_FUNCTION']
        
        self.assertEqual(len(window_cols), 1)
        self.assertEqual(window_cols[0]['function'], 'RANK')
        self.assertEqual(window_cols[0]['over']['partition_by'], ['dept'])
        self.assertEqual(window_cols[0]['over']['order_by'], [('salary', 'DESC')])
    
    def test_parse_dense_rank(self):
        """Test parsing DENSE_RANK()."""
        sql = "SELECT DENSE_RANK() OVER (ORDER BY score DESC) FROM scores"
        cmd_type, params = self.parser.parse(sql)
        
        columns = params.get('columns', [])
        window_cols = [c for c in columns if isinstance(c, dict) and c.get('type') == 'WINDOW_FUNCTION']
        
        self.assertEqual(len(window_cols), 1)
        self.assertEqual(window_cols[0]['function'], 'DENSE_RANK')
    
    def test_parse_lead(self):
        """Test parsing LEAD()."""
        sql = "SELECT LEAD(salary, 1, 0) OVER (PARTITION BY dept ORDER BY hire_date) FROM employees"
        cmd_type, params = self.parser.parse(sql)
        
        columns = params.get('columns', [])
        window_cols = [c for c in columns if isinstance(c, dict) and c.get('type') == 'WINDOW_FUNCTION']
        
        self.assertEqual(len(window_cols), 1)
        self.assertEqual(window_cols[0]['function'], 'LEAD')
        self.assertEqual(window_cols[0]['args'], ['salary', '1', '0'])
    
    def test_parse_lag(self):
        """Test parsing LAG()."""
        sql = "SELECT LAG(salary, 1) OVER (ORDER BY hire_date) FROM employees"
        cmd_type, params = self.parser.parse(sql)
        
        columns = params.get('columns', [])
        window_cols = [c for c in columns if isinstance(c, dict) and c.get('type') == 'WINDOW_FUNCTION']
        
        self.assertEqual(len(window_cols), 1)
        self.assertEqual(window_cols[0]['function'], 'LAG')
    
    def test_parse_first_value(self):
        """Test parsing FIRST_VALUE()."""
        sql = "SELECT FIRST_VALUE(salary) OVER (PARTITION BY dept ORDER BY hire_date) FROM employees"
        cmd_type, params = self.parser.parse(sql)
        
        columns = params.get('columns', [])
        window_cols = [c for c in columns if isinstance(c, dict) and c.get('type') == 'WINDOW_FUNCTION']
        
        self.assertEqual(len(window_cols), 1)
        self.assertEqual(window_cols[0]['function'], 'FIRST_VALUE')
        self.assertEqual(window_cols[0]['args'], ['salary'])
    
    def test_parse_last_value(self):
        """Test parsing LAST_VALUE()."""
        sql = "SELECT LAST_VALUE(salary) OVER (PARTITION BY dept ORDER BY hire_date DESC) FROM employees"
        cmd_type, params = self.parser.parse(sql)
        
        columns = params.get('columns', [])
        window_cols = [c for c in columns if isinstance(c, dict) and c.get('type') == 'WINDOW_FUNCTION']
        
        self.assertEqual(len(window_cols), 1)
        self.assertEqual(window_cols[0]['function'], 'LAST_VALUE')


class TestWindowFunctionExecution(unittest.TestCase):
    """Test window function execution."""
    
    def setUp(self):
        self.executor = WindowFunctionExecutor()
        
        # Sample data
        self.sample_data = [
            {'dept': 'Sales', 'name': 'Alice', 'salary': 50000, 'hire_date': '2020-01-15'},
            {'dept': 'Sales', 'name': 'Bob', 'salary': 55000, 'hire_date': '2019-03-20'},
            {'dept': 'Sales', 'name': 'Carol', 'salary': 55000, 'hire_date': '2018-06-10'},
            {'dept': 'IT', 'name': 'David', 'salary': 60000, 'hire_date': '2017-11-05'},
            {'dept': 'IT', 'name': 'Eve', 'salary': 65000, 'hire_date': '2016-08-15'},
        ]
    
    def test_row_number(self):
        """Test ROW_NUMBER() execution."""
        call = WindowFunctionCall(
            function_type=WindowFunctionType.ROW_NUMBER,
            args=[],
            window_frame=WindowFrame(partition_by=['dept'], order_by=[('salary', 'DESC')]),
            alias='row_num'
        )
        
        result = self.executor.execute(self.sample_data.copy(), [call])
        
        # Check row numbers within each partition
        sales_rows = [r for r in result if r['dept'] == 'Sales']
        self.assertEqual(sales_rows[0]['row_num'], 1)
        self.assertEqual(sales_rows[1]['row_num'], 2)
        self.assertEqual(sales_rows[2]['row_num'], 3)
    
    def test_rank(self):
        """Test RANK() execution."""
        call = WindowFunctionCall(
            function_type=WindowFunctionType.RANK,
            args=[],
            window_frame=WindowFrame(partition_by=['dept'], order_by=[('salary', 'DESC')]),
            alias='rank'
        )
        
        result = self.executor.execute(self.sample_data.copy(), [call])
        
        # Check ranks - should have gaps for ties
        sales_rows = [r for r in result if r['dept'] == 'Sales']
        # Carol and Bob have same salary (55000), so they should both rank 1
        # Alice has 50000, should rank 3 (gap after 2)
        ranks = [r['rank'] for r in sales_rows]
        self.assertIn(1, ranks)
        self.assertIn(3, ranks)
    
    def test_dense_rank(self):
        """Test DENSE_RANK() execution."""
        call = WindowFunctionCall(
            function_type=WindowFunctionType.DENSE_RANK,
            args=[],
            window_frame=WindowFrame(partition_by=['dept'], order_by=[('salary', 'DESC')]),
            alias='dense_rank'
        )
        
        result = self.executor.execute(self.sample_data.copy(), [call])
        
        # Check dense ranks - no gaps for ties
        sales_rows = [r for r in result if r['dept'] == 'Sales']
        # Carol and Bob tie for rank 1, Alice is rank 2 (no gap)
        ranks = [r['dense_rank'] for r in sales_rows]
        self.assertIn(1, ranks)
        self.assertIn(2, ranks)
    
    def test_lead(self):
        """Test LEAD() execution."""
        call = WindowFunctionCall(
            function_type=WindowFunctionType.LEAD,
            args=['salary', '1', '0'],
            window_frame=WindowFrame(partition_by=['dept'], order_by=[('hire_date', 'ASC')]),
            alias='next_salary'
        )
        
        result = self.executor.execute(self.sample_data.copy(), [call])
        
        # Check LEAD values
        sales_rows = sorted([r for r in result if r['dept'] == 'Sales'], 
                          key=lambda x: x['hire_date'])
        # Carol (oldest) should see Bob's salary as next
        self.assertEqual(sales_rows[0]['next_salary'], 55000)  # Carol sees Bob
        # Bob should see Alice's salary
        self.assertEqual(sales_rows[1]['next_salary'], 50000)  # Bob sees Alice
        # Alice (newest) should see default (0)
        self.assertEqual(sales_rows[2]['next_salary'], 0)
    
    def test_lag(self):
        """Test LAG() execution."""
        call = WindowFunctionCall(
            function_type=WindowFunctionType.LAG,
            args=['salary', '1', '0'],
            window_frame=WindowFrame(partition_by=['dept'], order_by=[('hire_date', 'ASC')]),
            alias='prev_salary'
        )
        
        result = self.executor.execute(self.sample_data.copy(), [call])
        
        # Check LAG values
        sales_rows = sorted([r for r in result if r['dept'] == 'Sales'], 
                          key=lambda x: x['hire_date'])
        # Carol (oldest) should see default (0)
        self.assertEqual(sales_rows[0]['prev_salary'], 0)
        # Bob should see Carol's salary
        self.assertEqual(sales_rows[1]['prev_salary'], 55000)
        # Alice should see Bob's salary
        self.assertEqual(sales_rows[2]['prev_salary'], 55000)
    
        result = self.executor.execute(self.sample_data.copy(), [call])
        
        # Check FIRST_VALUE - should be same for all rows in partition
        sales_rows = [r for r in result if r['dept'] == 'Sales']
        first_salaries = [r['first_salary'] for r in sales_rows]
        # All should have the same first value (Carol's salary: 55000)
        self.assertTrue(all(s == 55000 for s in first_salaries))
    
    def test_last_value(self):
        """Test LAST_VALUE() execution."""
        call = WindowFunctionCall(
            function_type=WindowFunctionType.LAST_VALUE,
            args=['salary'],
            window_frame=WindowFrame(partition_by=['dept'], order_by=[('hire_date', 'ASC')]),
            alias='last_salary'
        )
        
        result = self.executor.execute(self.sample_data.copy(), [call])
        
        # Check LAST_VALUE - should be same for all rows in partition
        sales_rows = [r for r in result if r['dept'] == 'Sales']
        last_salaries = [r['last_salary'] for r in sales_rows]
        # All should have the same last value (Alice's salary: 50000)
        self.assertTrue(all(s == 50000 for s in last_salaries))


class TestWindowFunctionEdgeCases(unittest.TestCase):
    """Test edge cases for window functions."""
    
    def setUp(self):
        self.executor = WindowFunctionExecutor()
    
    def test_empty_data(self):
        """Test with empty data."""
        call = WindowFunctionCall(
            function_type=WindowFunctionType.ROW_NUMBER,
            args=[],
            window_frame=WindowFrame(order_by=[('id', 'ASC')]),
            alias='row_num'
        )
        
        result = self.executor.execute([], [call])
        self.assertEqual(len(result), 0)
    
    def test_single_row(self):
        """Test with single row."""
        data = [{'id': 1, 'value': 100}]
        
        call = WindowFunctionCall(
            function_type=WindowFunctionType.ROW_NUMBER,
            args=[],
            window_frame=WindowFrame(order_by=[('id', 'ASC')]),
            alias='row_num'
        )
        
        result = self.executor.execute(data, [call])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['row_num'], 1)
    
    def test_no_partition(self):
        """Test without PARTITION BY."""
        data = [
            {'id': 1, 'value': 100},
            {'id': 2, 'value': 200},
            {'id': 3, 'value': 150}
        ]
        
        call = WindowFunctionCall(
            function_type=WindowFunctionType.ROW_NUMBER,
            args=[],
            window_frame=WindowFrame(order_by=[('value', 'DESC')]),
            alias='row_num'
        )
        
        result = self.executor.execute(data, [call])
        self.assertEqual(len(result), 3)


class TestWindowFunctionIntegration(unittest.TestCase):
    """Test window function integration with parser."""
    
    def setUp(self):
        self.parser = CommandParser()
    
    def test_complex_query_with_window(self):
        """Test complex query with window function."""
        sql = """
            SELECT 
                name,
                dept,
                salary,
                ROW_NUMBER() OVER (PARTITION BY dept ORDER BY salary DESC) as rank_in_dept,
                RANK() OVER (ORDER BY salary DESC) as overall_rank
            FROM employees
        """
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'SELECT')
        columns = params.get('columns', [])
        
        # Should have 5 columns (3 regular + 2 window functions)
        self.assertEqual(len(columns), 5)
        
        # Check window functions are parsed
        window_cols = [c for c in columns if isinstance(c, dict) and c.get('type') == 'WINDOW_FUNCTION']
        self.assertEqual(len(window_cols), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)


class TestWindowFunctionIntegration(unittest.TestCase):
    """Test window function integration with parser."""
    
    def setUp(self):
        self.parser = CommandParser()
    
    def test_complex_query_with_window(self):
        """Test complex query with window function."""
        sql = """
            SELECT 
                name,
                dept,
                salary,
                ROW_NUMBER() OVER (PARTITION BY dept ORDER BY salary DESC) as rank_in_dept,
                RANK() OVER (ORDER BY salary DESC) as overall_rank
            FROM employees
        """
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'SELECT')
        columns = params.get('columns', [])
        
        # Should have 5 columns (3 regular + 2 window functions)
        self.assertEqual(len(columns), 5)
        
        # Check window functions are parsed
        window_cols = [c for c in columns if isinstance(c, dict) and c.get('type') == 'WINDOW_FUNCTION']
        self.assertEqual(len(window_cols), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
        )
        
        result = self.executor.execute(data, [call])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['row_num'], 1)
    
    def test_no_partition(self):
        """Test without PARTITION BY."""
        data = [
            {'id': 1, 'value': 100},
n            {'id': 2, 'value': 200},\n            {'id': 3, 'value': 150}\n        ]\n        \n        call = WindowFunctionCall(\n            function_type=WindowFunctionType.ROW_NUMBER,\n            args=[],\n            window_frame=WindowFrame(order_by=[('value', 'DESC')]),\n            alias='row_num'\n        )\n        \n        result = self.executor.execute(data, [call])\n        \n        # Should number all rows together\n        values = [(r['id'], r['row_num']) for r in result]\n        # id=2 (value=200) should be row 1\n        # id=3 (value=150) should be row 2\n        # id=1 (value=100) should be row 3\n        self.assertEqual(len(result), 3)\n\n\nclass TestWindowFunctionIntegration(unittest.TestCase):\n    \"\"\"Test window function integration with parser.\"\"\"\n    \n    def setUp(self):\n        self.parser = CommandParser()\n    \n    def test_complex_query_with_window(self):\n        \"\"\"Test complex query with window function.\"\"\"\n        sql = \"\"\"\n            SELECT \n                name,\n                dept,\n                salary,\n                ROW_NUMBER() OVER (PARTITION BY dept ORDER BY salary DESC) as rank_in_dept,\n                RANK() OVER (ORDER BY salary DESC) as overall_rank\n            FROM employees\n        \"\"\"\n        \n        cmd_type, params = self.parser.parse(sql)\n        \n        self.assertEqual(cmd_type, 'SELECT')\n        columns = params.get('columns', [])\n        \n        # Should have 5 columns (3 regular + 2 window functions)\n        self.assertEqual(len(columns), 5)\n        \n        # Check window functions are parsed\n        window_cols = [c for c in columns if isinstance(c, dict) and c.get('type') == 'WINDOW_FUNCTION']\n        self.assertEqual(len(window_cols), 2)\n\n\nif __name__ == '__main__':\n    unittest.main(verbosity=2)\n