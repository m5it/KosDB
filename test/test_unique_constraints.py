"""
Test Unique Constraints for KosDB v3.2.0

Tests:
- Inline UNIQUE constraint syntax
- Table-level UNIQUE constraint syntax
- Composite unique constraints (multiple columns)
- INSERT with unique constraint validation
- UPDATE with unique constraint validation
- Duplicate value detection
- NULL value handling in unique constraints
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


class TestUniqueConstraints(unittest.TestCase):
    """Test unique constraint functionality."""
    
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
    
    def test_inline_unique_constraint_parsing(self):
        """Test parsing inline UNIQUE syntax."""
        sql = "CREATE TABLE users (id INT PRIMARY KEY, email TEXT UNIQUE)"
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'CREATE')
        columns = params.get('columns', [])
        
        # Find email column
        email_col = next((c for c in columns if c.get('name') == 'email'), None)
        self.assertIsNotNone(email_col)
        self.assertTrue(email_col.get('unique'))
    
    def test_table_level_unique_constraint_parsing(self):
        """Test parsing table-level UNIQUE syntax."""
        sql = ("CREATE TABLE users (id INT PRIMARY KEY, first_name TEXT, last_name TEXT, "
               "UNIQUE (first_name, last_name))")
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'CREATE')
        columns = params.get('columns', [])
        
        # Find UNIQUE constraint
        unique_constraint = None
        for col in columns:
            if col.get('constraint_type') == 'UNIQUE':
                unique_constraint = col
                break
        
        self.assertIsNotNone(unique_constraint)
        self.assertEqual(unique_constraint['columns'], ['first_name', 'last_name'])
    
    def test_create_table_with_unique_constraint(self):
        """Test creating table with unique constraint."""
        result = self.db.create_table("users", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'email', 'type': 'TEXT', 'unique': True},
            {'name': 'name', 'type': 'TEXT'}
        ])
        self.assertIn("created", result.lower())
        
        # Verify unique index was created
        idx_key = b"_unique_index:users:email"
        idx_data = self.db._db.get(idx_key)
        self.assertIsNotNone(idx_data)
    
    def test_create_table_with_composite_unique(self):
        """Test creating table with composite unique constraint."""
        result = self.db.create_table("orders", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'user_id', 'type': 'INT'},
            {'name': 'product_id', 'type': 'INT'},
            {'name': 'quantity', 'type': 'INT'}
        ])
        self.assertIn("created", result.lower())
        
        # Manually add composite unique constraint via table-level syntax
        # (In real usage, this would be part of CREATE TABLE)
        schema_key = b"_schema:orders"
        schema_data = self.db._db.get(schema_key)
        schema = json.loads(schema_data.decode())
        schema['unique_constraints'] = [['user_id', 'product_id']]
        self.db._db.put(schema_key, json.dumps(schema).encode())
        
        # Create unique index
        idx_key = b"_unique_index:orders:user_id:product_id"
        self.db._db.put(idx_key, json.dumps({}).encode())
    
    def test_insert_with_unique_constraint_success(self):
        """Test INSERT with unique values."""
        self.db.create_table("users", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'email', 'type': 'TEXT', 'unique': True},
            {'name': 'name', 'type': 'TEXT'}
        ])
        
        result = self.db.insert("users", [1, "alice@example.com", "Alice"])
        self.assertIn("Inserted", result)
        
        result = self.db.insert("users", [2, "bob@example.com", "Bob"])
        self.assertIn("Inserted", result)
    
    def test_insert_duplicate_unique_value(self):
        """Test INSERT with duplicate unique value fails."""
        self.db.create_table("users", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'email', 'type': 'TEXT', 'unique': True},
            {'name': 'name', 'type': 'TEXT'}
        ])
        
        # Insert first user
        result = self.db.insert("users", [1, "alice@example.com", "Alice"])
        self.assertIn("Inserted", result)
        
        # Try to insert duplicate email
        result = self.db.insert("users", [2, "alice@example.com", "Alice Clone"])
        self.assertIn("ERROR", result)
        self.assertIn("Duplicate entry", result)
        self.assertIn("unique constraint", result.lower())
    
    def test_update_unique_constraint_success(self):
        """Test UPDATE to unique value succeeds."""
        self.db.create_table("users", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'email', 'type': 'TEXT', 'unique': True},
            {'name': 'name', 'type': 'TEXT'}
        ])
        
        self.db.insert("users", [1, "alice@example.com", "Alice"])
        self.db.insert("users", [2, "bob@example.com", "Bob"])
        
        # Update Alice's email to new unique value
        result = self.db.update("users", {"email": "alice.smith@example.com"}, {"id": "1"})
        self.assertIn("Updated", result)
    
    def test_update_duplicate_unique_value(self):
        """Test UPDATE to duplicate unique value fails."""
        self.db.create_table("users", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'email', 'type': 'TEXT', 'unique': True},
            {'name': 'name', 'type': 'TEXT'}
        ])
        
        self.db.insert("users", [1, "alice@example.com", "Alice"])
        self.db.insert("users", [2, "bob@example.com", "Bob"])
        
        # Try to update Alice's email to Bob's email
        result = self.db.update("users", {"email": "bob@example.com"}, {"id": "1"})
        self.assertIn("ERROR", result)
        self.assertIn("Duplicate entry", result)
    
    def test_null_values_allowed_in_unique_constraint(self):
        """Test that NULL values are allowed in unique constraints."""
        self.db.create_table("users", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'email', 'type': 'TEXT', 'unique': True},
            {'name': 'name', 'type': 'TEXT'}
        ])
        
        # Insert with NULL email
        result = self.db.insert("users", [1, None, "Alice"])
        self.assertIn("Inserted", result)
        
        # Insert another with NULL email (should be allowed)
        result = self.db.insert("users", [2, None, "Bob"])
        self.assertIn("Inserted", result)
    
    def test_composite_unique_constraint(self):
        """Test composite unique constraint on multiple columns."""
        # Create table with composite unique
        self.db.create_table("orders", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'user_id', 'type': 'INT'},
            {'name': 'product_id', 'type': 'INT'},
            {'name': 'quantity', 'type': 'INT'}
        ])
        
        # Add composite unique constraint
        schema_key = b"_schema:orders"
        schema_data = self.db._db.get(schema_key)
        schema = json.loads(schema_data.decode())
        schema['unique_constraints'] = [['user_id', 'product_id']]
        self.db._db.put(schema_key, json.dumps(schema).encode())
        
        # Create unique index
        idx_key = b"_unique_index:orders:user_id:product_id"
        self.db._db.put(idx_key, json.dumps({}).encode())
        
        # Insert first order
        result = self.db.insert("orders", [1, 1, 100, 5])
        self.assertIn("Inserted", result)
        
        # Insert different user, same product
        result = self.db.insert("orders", [2, 2, 100, 3])
        self.assertIn("Inserted", result)
        
        # Insert same user, different product
        result = self.db.insert("orders", [3, 1, 200, 2])
        self.assertIn("Inserted", result)
        
        # Try duplicate user_id + product_id combination
        result = self.db.insert("orders", [4, 1, 100, 10])
        self.assertIn("ERROR", result)
        self.assertIn("Duplicate entry", result)
    
    def test_unique_constraint_with_table_level_syntax(self):
        """Test creating unique constraint with table-level syntax."""
        sql = ("CREATE TABLE products (id INT PRIMARY KEY, sku TEXT, name TEXT, "
               "UNIQUE (sku))")
        cmd_type, params = self.parser.parse(sql)
        
        # Create table using parsed columns
        result = self.db.create_table("products", params['columns'])
        self.assertIn("created", result.lower())
        
        # Test unique constraint
        result = self.db.insert("products", [1, "SKU001", "Widget"])
        self.assertIn("Inserted", result)
        
        result = self.db.insert("products", [2, "SKU001", "Duplicate"])
        self.assertIn("ERROR", result)
    
    def test_multiple_unique_constraints(self):
        """Test table with multiple unique constraints."""
        self.db.create_table("users", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'email', 'type': 'TEXT', 'unique': True},
            {'name': 'username', 'type': 'TEXT', 'unique': True},
            {'name': 'name', 'type': 'TEXT'}
        ])
        
        # Insert with unique email and username
        result = self.db.insert("users", [1, "alice@example.com", "alice", "Alice"])
        self.assertIn("Inserted", result)
        
        # Duplicate email
        result = self.db.insert("users", [2, "alice@example.com", "bob", "Bob"])
        self.assertIn("ERROR", result)
        
        # Duplicate username
        result = self.db.insert("users", [3, "charlie@example.com", "alice", "Charlie"])
        self.assertIn("ERROR", result)
        
        # Different email and username
        result = self.db.insert("users", [4, "dave@example.com", "dave", "Dave"])
        self.assertIn("Inserted", result)


class TestUniqueConstraintEdgeCases(unittest.TestCase):
    """Test edge cases for unique constraints."""
    
    def setUp(self):
        """Set up test database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db = Database(self.temp_dir, server_id=1)
        self.db.create_database("testdb")
        self.db.use_database("testdb")
    
    def tearDown(self):
        """Clean up."""
        self.db.close()
        shutil.rmtree(self.temp_dir)
    
    def test_update_to_same_value(self):
        """Test UPDATE to same unique value succeeds."""
        self.db.create_table("users", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'email', 'type': 'TEXT', 'unique': True},
            {'name': 'name', 'type': 'TEXT'}
        ])
        
        self.db.insert("users", [1, "alice@example.com", "Alice"])
        
        # Update to same value (no change)
        result = self.db.update("users", {"email": "alice@example.com"}, {"id": "1"})
        self.assertIn("Updated", result)
    
    def test_empty_string_vs_null(self):
        """Test empty string is different from NULL in unique constraint."""
        self.db.create_table("users", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'email', 'type': 'TEXT', 'unique': True},
            {'name': 'name', 'type': 'TEXT'}
        ])
        
        # Insert with empty string
        result = self.db.insert("users", [1, "", "Alice"])
        self.assertIn("Inserted", result)
        
        # Insert another with empty string (should fail - empty != NULL)
        result = self.db.insert("users", [2, "", "Bob"])
        self.assertIn("ERROR", result)
    
    def test_case_sensitivity_in_unique_constraint(self):
        """Test unique constraint is case-sensitive."""
        self.db.create_table("users", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'email', 'type': 'TEXT', 'unique': True},
            {'name': 'name', 'type': 'TEXT'}
        ])
        
        # Insert lowercase
        result = self.db.insert("users", [1, "alice@example.com", "Alice"])
        self.assertIn("Inserted", result)
        
        # Insert uppercase (should succeed - case sensitive)
        result = self.db.insert("users", [2, "ALICE@EXAMPLE.COM", "Alice Upper"])
        self.assertIn("Inserted", result)
    
    def test_unique_constraint_error_message_format(self):
        """Test error message format for unique constraint violations."""
        self.db.create_table("users", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'email', 'type': 'TEXT', 'unique': True},
            {'name': 'name', 'type': 'TEXT'}
        ])
        
        self.db.insert("users", [1, "test@example.com", "Test"])
        
        result = self.db.insert("users", [2, "test@example.com", "Another"])
        self.assertIn("ERROR", result)
        self.assertIn("Duplicate entry", result)
        self.assertIn("test@example.com", result)
        self.assertIn("unique constraint", result.lower())


if __name__ == '__main__':
    unittest.main(verbosity=2)
