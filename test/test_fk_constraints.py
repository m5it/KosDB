"""
Test Foreign Key Constraints for KosDB v3.2.0

Tests:
- CREATE TABLE with FOREIGN KEY constraints
- Inline REFERENCES syntax
- Table-level FOREIGN KEY syntax
- ON DELETE actions (RESTRICT, CASCADE, SET_NULL)
- ON UPDATE actions
- FK validation on INSERT
- FK validation on UPDATE
- FK constraint violations
- Multi-table relationships
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


class TestForeignKeyConstraints(unittest.TestCase):
    """Test foreign key constraint functionality."""
    
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
    
    def test_inline_foreign_key_syntax(self):
        """Test parsing inline REFERENCES syntax."""
        sql = "CREATE TABLE orders (id INT PRIMARY KEY, user_id INT REFERENCES users(id))"
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'CREATE')
        columns = params.get('columns', [])
        
        # Find user_id column
        user_id_col = None
        for col in columns:
            if col.get('name') == 'user_id':
                user_id_col = col
                break
        
        self.assertIsNotNone(user_id_col)
        self.assertIsNotNone(user_id_col.get('foreign_key'))
        self.assertEqual(user_id_col['foreign_key']['references_table'], 'users')
        self.assertEqual(user_id_col['foreign_key']['references_column'], 'id')
    
    def test_table_level_foreign_key_syntax(self):
        """Test parsing table-level FOREIGN KEY syntax."""
        sql = ("CREATE TABLE orders (id INT PRIMARY KEY, user_id INT, "
               "FOREIGN KEY (user_id) REFERENCES users(id))")
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'CREATE')
        columns = params.get('columns', [])
        
        # Find FK constraint
        fk_constraint = None
        for col in columns:
            if col.get('constraint_type') == 'FOREIGN_KEY':
                fk_constraint = col
                break
        
        self.assertIsNotNone(fk_constraint)
        self.assertEqual(fk_constraint['column'], 'user_id')
        self.assertEqual(fk_constraint['references_table'], 'users')
        self.assertEqual(fk_constraint['references_column'], 'id')
    
    def test_foreign_key_with_on_delete(self):
        """Test FK with ON DELETE actions."""
        sql = ("CREATE TABLE orders (id INT, user_id INT REFERENCES users(id) "
               "ON DELETE CASCADE ON UPDATE SET_NULL)")
        cmd_type, params = self.parser.parse(sql)
        
        columns = params.get('columns', [])
        user_id_col = next((c for c in columns if c.get('name') == 'user_id'), None)
        
        self.assertIsNotNone(user_id_col)
        fk = user_id_col['foreign_key']
        self.assertEqual(fk['on_delete'], 'CASCADE')
        self.assertEqual(fk['on_update'], 'SET_NULL')
    
    def test_create_table_with_foreign_key(self):
        """Test creating table with FK constraint."""
        # First create parent table
        result = self.db.create_table("users", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'name', 'type': 'TEXT'}
        ])
        self.assertIn("created", result.lower())
        
        # Insert a user
        self.db.insert("users", [1, "Alice"])
        
        # Create child table with FK
        result = self.db.create_table("orders", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'user_id', 'type': 'INT', 'foreign_key': {
                'references_table': 'users',
                'references_column': 'id',
                'on_delete': 'RESTRICT',
                'on_update': 'RESTRICT'
            }},
            {'name': 'amount', 'type': 'FLOAT'}
        ])
        self.assertIn("created", result.lower())
    
    def test_insert_with_valid_foreign_key(self):
        """Test INSERT with valid FK reference."""
        # Create parent table and insert data
        self.db.create_table("users", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'name', 'type': 'TEXT'}
        ])
        self.db.insert("users", [1, "Alice"])
        self.db.insert("users", [2, "Bob"])
        
        # Create child table
        self.db.create_table("orders", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'user_id', 'type': 'INT', 'foreign_key': {
                'references_table': 'users',
                'references_column': 'id',
                'on_delete': 'RESTRICT',
                'on_update': 'RESTRICT'
            }},
            {'name': 'amount', 'type': 'FLOAT'}
        ])
        
        # Insert with valid FK
        result = self.db.insert("orders", [1, 1, 100.0])
        self.assertIn("Inserted", result)
        
        result = self.db.insert("orders", [2, 2, 200.0])
        self.assertIn("Inserted", result)
    
    def test_insert_with_invalid_foreign_key(self):
        """Test INSERT with invalid FK reference."""
        # Create parent table
        self.db.create_table("users", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'name', 'type': 'TEXT'}
        ])
        self.db.insert("users", [1, "Alice"])
        
        # Create child table
        self.db.create_table("orders", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'user_id', 'type': 'INT', 'foreign_key': {
                'references_table': 'users',
                'references_column': 'id',
                'on_delete': 'RESTRICT',
                'on_update': 'RESTRICT'
            }},
            {'name': 'amount', 'type': 'FLOAT'}
        ])
        
        # Try to insert with invalid FK (user_id=999 doesn't exist)
        result = self.db.insert("orders", [1, 999, 100.0])
        self.assertIn("ERROR", result)
        self.assertIn("Foreign key constraint violation", result)
    
    def test_update_with_foreign_key_violation(self):
        """Test UPDATE that violates FK constraint."""
        # Setup tables
        self.db.create_table("users", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'name', 'type': 'TEXT'}
        ])
        self.db.insert("users", [1, "Alice"])
        
        self.db.create_table("orders", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'user_id', 'type': 'INT', 'foreign_key': {
                'references_table': 'users',
                'references_column': 'id',
                'on_delete': 'RESTRICT',
                'on_update': 'RESTRICT'
            }},
            {'name': 'amount', 'type': 'FLOAT'}
        ])
        self.db.insert("orders", [1, 1, 100.0])
        
        # Try to update to invalid FK
        result = self.db.update("orders", {"user_id": 999}, {"id": "1"})
        self.assertIn("ERROR", result)
        self.assertIn("Foreign key constraint violation", result)
    
    def test_delete_restrict(self):
        """Test ON DELETE RESTRICT prevents deletion."""
        # Setup tables
        self.db.create_table("users", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'name', 'type': 'TEXT'}
        ])
        self.db.insert("users", [1, "Alice"])
        
        self.db.create_table("orders", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'user_id', 'type': 'INT', 'foreign_key': {
                'references_table': 'users',
                'references_column': 'id',
                'on_delete': 'RESTRICT',
                'on_update': 'RESTRICT'
            }},
            {'name': 'amount', 'type': 'FLOAT'}
        ])
        self.db.insert("orders", [1, 1, 100.0])
        
        # Try to delete referenced row
        result = self.db.delete("users", {"id": "1"})
        self.assertIn("ERROR", result)
        self.assertIn("ON DELETE RESTRICT", result)
    
    def test_delete_cascade(self):
        """Test ON DELETE CASCADE."""
        # Setup tables
        self.db.create_table("users", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'name', 'type': 'TEXT'}
        ])
        self.db.insert("users", [1, "Alice"])
        self.db.insert("users", [2, "Bob"])
        
        self.db.create_table("orders", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'user_id', 'type': 'INT', 'foreign_key': {
                'references_table': 'users',
                'references_column': 'id',
                'on_delete': 'CASCADE',
                'on_update': 'RESTRICT'
            }},
            {'name': 'amount', 'type': 'FLOAT'}
        ])
        self.db.insert("orders", [1, 1, 100.0])
        self.db.insert("orders", [2, 1, 150.0])  # Another order for user 1
        self.db.insert("orders", [3, 2, 200.0])  # Order for user 2
        
        # Delete user 1 - should cascade delete orders 1 and 2
        result = self.db.delete("users", {"id": "1"})
        self.assertIn("Deleted", result)
        
        # Verify orders for user 1 are deleted
        orders = self.db.select("orders", raw=True)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]['user_id'], 2)
    
    def test_delete_set_null(self):
        """Test ON DELETE SET_NULL."""
        # Setup tables
        self.db.create_table("users", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'name', 'type': 'TEXT'}
        ])
        self.db.insert("users", [1, "Alice"])
        
        self.db.create_table("orders", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'user_id', 'type': 'INT', 'foreign_key': {
                'references_table': 'users',
                'references_column': 'id',
                'on_delete': 'SET_NULL',
                'on_update': 'RESTRICT'
            }},
            {'name': 'amount', 'type': 'FLOAT'}
        ])
        self.db.insert("orders", [1, 1, 100.0])
        
        # Delete user - should set user_id to NULL
        result = self.db.delete("users", {"id": "1"})
        self.assertIn("Deleted", result)
        
        # Verify order has NULL user_id
        orders = self.db.select("orders", raw=True)
        self.assertEqual(len(orders), 1)
        self.assertIsNone(orders[0].get('user_id'))
    
    def test_multiple_foreign_keys(self):
        """Test table with multiple FK constraints."""
        # Create three tables
        self.db.create_table("users", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'name', 'type': 'TEXT'}
        ])
        self.db.insert("users", [1, "Alice"])
        
        self.db.create_table("products", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'name', 'type': 'TEXT'}
        ])
        self.db.insert("products", [1, "Widget"])
        
        self.db.create_table("orders", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'user_id', 'type': 'INT', 'foreign_key': {
                'references_table': 'users',
                'references_column': 'id',
                'on_delete': 'RESTRICT',
                'on_update': 'RESTRICT'
            }},
            {'name': 'product_id', 'type': 'INT', 'foreign_key': {
                'references_table': 'products',
                'references_column': 'id',
                'on_delete': 'RESTRICT',
                'on_update': 'RESTRICT'
            }},
            {'name': 'quantity', 'type': 'INT'}
        ])
        
        # Insert with valid FKs
        result = self.db.insert("orders", [1, 1, 1, 5])
        self.assertIn("Inserted", result)
        
        # Insert with invalid user_id
        result = self.db.insert("orders", [2, 999, 1, 3])
        self.assertIn("ERROR", result)
        
        # Insert with invalid product_id
        result = self.db.insert("orders", [3, 1, 999, 3])
        self.assertIn("ERROR", result)
    
    def test_self_referencing_foreign_key(self):
        """Test FK that references same table (hierarchical data)."""
        self.db.create_table("categories", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'name', 'type': 'TEXT'},
            {'name': 'parent_id', 'type': 'INT', 'foreign_key': {
                'references_table': 'categories',
                'references_column': 'id',
                'on_delete': 'SET_NULL',
                'on_update': 'RESTRICT'
            }}
        ])
        
        # Insert root category
        result = self.db.insert("categories", [1, "Electronics", None])
        self.assertIn("Inserted", result)
        
        # Insert child category
        result = self.db.insert("categories", [2, "Phones", 1])
        self.assertIn("Inserted", result)
        
        # Insert with invalid parent
        result = self.db.insert("categories", [3, "Tablets", 999])
        self.assertIn("ERROR", result)
    
    def test_foreign_key_with_table_level_syntax(self):
        """Test creating FK with table-level constraint syntax."""
        # Parse and create with table-level FK
        sql = ("CREATE TABLE orders (id INT PRIMARY KEY, user_id INT, "
               "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE)")
        cmd_type, params = self.parser.parse(sql)
        
        # Create parent first
        self.db.create_table("users", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'name', 'type': 'TEXT'}
        ])
        self.db.insert("users", [1, "Alice"])
        
        # Create child with table-level FK
        result = self.db.create_table("orders", params['columns'])
        self.assertIn("created", result.lower())
        
        # Test the FK works
        self.db.insert("orders", [1, 1])
        
        # Delete parent - should cascade
        self.db.delete("users", {"id": "1"})
        
        orders = self.db.select("orders", raw=True)
        self.assertEqual(len(orders), 0)


class TestForeignKeyEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions for FKs."""
    
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
    
    def test_null_foreign_key(self):
        """Test that NULL FK values are allowed."""
        self.db.create_table("users", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'name', 'type': 'TEXT'}
        ])
        self.db.insert("users", [1, "Alice"])
        
        self.db.create_table("orders", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'user_id', 'type': 'INT', 'foreign_key': {
                'references_table': 'users',
                'references_column': 'id',
                'on_delete': 'RESTRICT',
                'on_update': 'RESTRICT'
            }}
        ])
        
        # NULL FK should be allowed
        result = self.db.insert("orders", [1, None])
        self.assertIn("Inserted", result)
    
    def test_nonexistent_referenced_table(self):
        """Test FK referencing non-existent table."""
        result = self.db.create_table("orders", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'user_id', 'type': 'INT', 'foreign_key': {
                'references_table': 'nonexistent',
                'references_column': 'id',
                'on_delete': 'RESTRICT',
                'on_update': 'RESTRICT'
            }}
        ])
        # Creation should succeed, but inserts will fail
        self.assertIn("created", result.lower())
        
        # Insert should fail
        result = self.db.insert("orders", [1, 1])
        self.assertIn("ERROR", result)
        self.assertIn("does not exist", result)


if __name__ == '__main__':
    unittest.main(verbosity=2)
