"""
Test CHECK Constraints for KosDB v3.2.0

Tests:
- CHECK with comparison operators (=, !=, <, >, <=, >=)
- CHECK with IN operator
- CHECK with BETWEEN operator
- CHECK with LIKE operator
- CHECK with IS NULL / IS NOT NULL
- Multiple CHECK constraints
- CHECK constraint validation on INSERT
- CHECK constraint validation on UPDATE
- Error messages for constraint violations
"""

import unittest
import sys
import os
import tempfile
import shutil

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database
from parser import CommandParser


class TestCheckConstraints(unittest.TestCase):
    """Test CHECK constraint functionality."""
    
    def setUp(self):
        """Set up test database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db = Database(self.temp_dir, server_id=1)
        self.parser = CommandParser()
        
        # Create test database
        self.db.create_database("testdb")
        self.db.use_database("testdb")
    
    def tearDown(self):
        """Clean up test database."""
        self.db.close()
        shutil.rmtree(self.temp_dir)
    
    def test_check_greater_than(self):
        """Test CHECK with > operator."""
        self.db.create_table("products", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'price', 'type': 'FLOAT'},
            {'name': 'quantity', 'type': 'INT', 'check': {'expression': 'quantity > 0'}}
        ])
        
        # Valid insert
        result = self.db.insert("products", [1, 10.99, 5])
        self.assertIn("Inserted", result)
        
        # Invalid insert
        result = self.db.insert("products", [2, 5.99, 0])
        self.assertIn("ERROR", result)
        self.assertIn("CHECK constraint violation", result)
    
    def test_check_less_than_or_equal(self):
        """Test CHECK with <= operator."""
        self.db.create_table("students", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'name', 'type': 'TEXT'},
            {'name': 'grade', 'type': 'INT', 'check': {'expression': 'grade <= 100'}}
        ])
        
        result = self.db.insert("students", [1, "Alice", 95])
        self.assertIn("Inserted", result)
        
        result = self.db.insert("students", [2, "Bob", 105])
        self.assertIn("ERROR", result)
    
    def test_check_equal(self):
        """Test CHECK with = operator."""
        self.db.create_table("status_table", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'status', 'type': 'INT', 'check': {'expression': 'status = 1'}}
        ])
        
        result = self.db.insert("status_table", [1, 1])
        self.assertIn("Inserted", result)
        
        result = self.db.insert("status_table", [2, 0])
        self.assertIn("ERROR", result)
    
    def test_check_not_equal(self):
        """Test CHECK with != operator."""
        self.db.create_table("users", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'name', 'type': 'TEXT'},
            {'name': 'age', 'type': 'INT', 'check': {'expression': 'age != 0'}}
        ])
        
        result = self.db.insert("users", [1, "Alice", 25])
        self.assertIn("Inserted", result)
        
        result = self.db.insert("users", [2, "Bob", 0])
        self.assertIn("ERROR", result)
    
    def test_check_in_operator(self):
        """Test CHECK with IN operator."""
        self.db.create_table("orders", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'status', 'type': 'TEXT', 'check': {'expression': "status IN ('pending', 'shipped', 'delivered')"}}
        ])
        
        result = self.db.insert("orders", [1, "pending"])
        self.assertIn("Inserted", result)
        
        result = self.db.insert("orders", [2, "cancelled"])
        self.assertIn("ERROR", result)
        self.assertIn("not in", result)
    
    def test_check_between_operator(self):
        """Test CHECK with BETWEEN operator."""
        self.db.create_table("scores", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'player', 'type': 'TEXT'},
            {'name': 'score', 'type': 'INT', 'check': {'expression': 'score BETWEEN 0 AND 100'}}
        ])
        
        result = self.db.insert("scores", [1, "Alice", 75])
        self.assertIn("Inserted", result)
        
        result = self.db.insert("scores", [2, "Bob", 150])
        self.assertIn("ERROR", result)
        self.assertIn("not between", result)
    
    def test_check_like_operator(self):
        """Test CHECK with LIKE operator."""
        self.db.create_table("codes", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'code', 'type': 'TEXT', 'check': {'expression': "code LIKE 'PRD-%'"}}
        ])
        
        result = self.db.insert("codes", [1, "PRD-001"])
        self.assertIn("Inserted", result)
        
        result = self.db.insert("codes", [2, "INVALID"])
        self.assertIn("ERROR", result)
        self.assertIn("not LIKE", result)
    
    def test_check_is_null(self):
        """Test CHECK with IS NULL."""
        self.db.create_table("optional", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'data', 'type': 'TEXT', 'check': {'expression': 'data IS NULL'}}
        ])
        
        result = self.db.insert("optional", [1, None])
        self.assertIn("Inserted", result)
        
        result = self.db.insert("optional", [2, "value"])
        self.assertIn("ERROR", result)
    
    def test_check_is_not_null(self):
        """Test CHECK with IS NOT NULL."""
        self.db.create_table("required", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'name', 'type': 'TEXT', 'check': {'expression': 'name IS NOT NULL'}}
        ])
        
        result = self.db.insert("required", [1, "Alice"])
        self.assertIn("Inserted", result)
        
        result = self.db.insert("required", [2, None])
        self.assertIn("ERROR", result)
    
    def test_multiple_check_constraints(self):
        """Test multiple CHECK constraints on same table."""
        self.db.create_table("employees", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'age', 'type': 'INT', 'check': {'expression': 'age >= 18'}},
            {'name': 'salary', 'type': 'FLOAT', 'check': {'expression': 'salary > 0'}}
        ])
        
        # Valid
        result = self.db.insert("employees", [1, 25, 50000.0])
        self.assertIn("Inserted", result)
        
        # Invalid age
        result = self.db.insert("employees", [2, 16, 50000.0])
        self.assertIn("ERROR", result)
        self.assertIn("age", result)
        
        # Invalid salary
        result = self.db.insert("employees", [3, 30, 0])
        self.assertIn("ERROR", result)
        self.assertIn("salary", result)
    
    def test_check_on_update(self):
        """Test CHECK validation on UPDATE."""
        self.db.create_table("items", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'count', 'type': 'INT', 'check': {'expression': 'count >= 0'}}
        ])
        
        self.db.insert("items", [1, 10])
        
        # Valid update
        result = self.db.update("items", {"count": 5}, {"id": "1"})
        self.assertIn("Updated", result)
        
        # Invalid update
        result = self.db.update("items", {"count": -1}, {"id": "1"})
        self.assertIn("ERROR", result)
        self.assertIn("CHECK constraint violation", result)
    
    def test_check_null_passes(self):
        """Test that NULL values pass CHECK constraints."""
        self.db.create_table("nullable_check", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'value', 'type': 'INT', 'check': {'expression': 'value > 0'}}
        ])
        
        # NULL should pass
        result = self.db.insert("nullable_check", [1, None])
        self.assertIn("Inserted", result)
    
    def test_table_level_check(self):
        """Test table-level CHECK constraint."""
        result = self.db.create_table("balanced", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'credits', 'type': 'FLOAT'},
            {'name': 'debits', 'type': 'FLOAT'},
            {'constraint_type': 'CHECK', 'expression': 'credits >= debits'}
        ])
        
        self.assertIn("created", result.lower())
        
        # Valid
        result = self.db.insert("balanced", [1, 100.0, 50.0])
        self.assertIn("Inserted", result)
        
        # Invalid
        result = self.db.insert("balanced", [2, 50.0, 100.0])
        self.assertIn("ERROR", result)


class TestCheckConstraintParser(unittest.TestCase):
    """Test CHECK constraint parsing."""
    
    def setUp(self):
        self.parser = CommandParser()
    
    def test_parse_check_inline(self):
        """Test parsing inline CHECK constraint."""
        sql = "CREATE TABLE test (id INT, age INT CHECK (age > 0))"
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'CREATE')
        columns = params.get('columns', [])
        
        age_col = next((c for c in columns if c.get('name') == 'age'), None)
        self.assertIsNotNone(age_col)
        self.assertIsNotNone(age_col.get('check'))
    
    def test_parse_check_table_level(self):
        """Test parsing table-level CHECK constraint."""
        sql = "CREATE TABLE test (id INT, age INT, CHECK (age > 0))"
        cmd_type, params = self.parser.parse(sql)
        
        columns = params.get('columns', [])
        check_constraint = next((c for c in columns if c.get('constraint_type') == 'CHECK'), None)
        
        self.assertIsNotNone(check_constraint)
        self.assertEqual(check_constraint['expression'], 'age > 0')


class TestCheckConstraintEdgeCases(unittest.TestCase):
    """Test edge cases for CHECK constraints."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db = Database(self.temp_dir, server_id=1)
        self.db.create_database("testdb")
        self.db.use_database("testdb")
    
    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.temp_dir)
    
    def test_check_with_float_values(self):
        """Test CHECK with float comparisons."""
        self.db.create_table("prices", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'amount', 'type': 'FLOAT', 'check': {'expression': 'amount > 0.0'}}
        ])
        
        result = self.db.insert("prices", [1, 9.99])
        self.assertIn("Inserted", result)
        
        result = self.db.insert("prices", [2, 0.0])
        self.assertIn("ERROR", result)
    
    def test_check_with_string_comparison(self):
        """Test CHECK with string comparisons."""
        self.db.create_table("categories", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'code', 'type': 'TEXT', 'check': {'expression': "code != 'INVALID'"}}
        ])
        
        result = self.db.insert("categories", [1, "VALID"])
        self.assertIn("Inserted", result)
        
        result = self.db.insert("categories", [2, "INVALID"])
        self.assertIn("ERROR", result)
    
    def test_check_like_underscore(self):
        """Test LIKE with underscore wildcard."""
        self.db.create_table("codes", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'code', 'type': 'TEXT', 'check': {'expression': "code LIKE 'A_'"}}
        ])
        
        result = self.db.insert("codes", [1, "A1"])
        self.assertIn("Inserted", result)
        
        result = self.db.insert("codes", [2, "ABC"])
        self.assertIn("ERROR", result)


if __name__ == '__main__':
    unittest.main(verbosity=2)
