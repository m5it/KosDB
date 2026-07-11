"""
Test ALTER TABLE Operations for KosDB v3.2.0

Tests:
- ALTER TABLE ADD COLUMN with types and constraints
- ALTER TABLE DROP COLUMN with CASCADE
- ALTER TABLE MODIFY COLUMN for type changes
- ALTER TABLE RENAME COLUMN
- ALTER TABLE ADD/DROP INDEX
- ALTER TABLE ADD/DROP CONSTRAINT (FOREIGN KEY, UNIQUE, CHECK)
- Data integrity during modifications
"""

import unittest
import sys
import os
import json
import tempfile
import shutil
import os
import tempfile
import shutil

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database
from parser import CommandParser


class TestAlterTable(unittest.TestCase):
    """Test ALTER TABLE operations."""
    
    def setUp(self):
        """Set up test database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db = Database(self.temp_dir, server_id=1)
        self.parser = CommandParser()
        
        # Create test database
        self.db.create_database("testdb")
        self.db.use_database("testdb")
        
        # Create base table
        self.db.create_table("test_table", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'name', 'type': 'TEXT'},
            {'name': 'age', 'type': 'INT'}
        ])
        
        # Insert test data
        self.db.insert("test_table", [1, "Alice", 25])
        self.db.insert("test_table", [2, "Bob", 30])
    
    def tearDown(self):
        """Clean up test database."""
        self.db.close()
        shutil.rmtree(self.temp_dir)
    
    def test_add_column_basic(self):
        """Test ALTER TABLE ADD COLUMN basic."""
        result = self.db.alter_add_column("test_table", {
            'name': 'email',
            'type': 'TEXT',
            'nullable': True
        })
        
        self.assertIn("added", result.lower())
        
        # Verify column exists
        schema = self._get_schema("test_table")
        self.assertIn("email", schema["columns"])
        
        # Verify existing rows have NULL
        rows = self.db.select("test_table", raw=True)
        for row in rows:
            self.assertIsNone(row.get("email"))
    
    def test_add_column_with_constraints(self):
        """Test ALTER TABLE ADD COLUMN with constraints."""
        result = self.db.alter_add_column("test_table", {
            'name': 'status',
            'type': 'TEXT',
            'index': True,
            'check': {'expression': "status IN ('active', 'inactive')"}
        })
        
        self.assertIn("added", result.lower())
        
        schema = self._get_schema("test_table")
        self.assertIn("status", schema["columns"])
        self.assertIn("status", schema.get("indexes", []))
    
    def test_drop_column_basic(self):
        """Test ALTER TABLE DROP COLUMN."""
        result = self.db.alter_drop_column("test_table", "age", cascade=False)
        
        self.assertIn("dropped", result.lower())
        
        # Verify column removed
        schema = self._get_schema("test_table")
        self.assertNotIn("age", schema["columns"])
        
        # Verify data removed
        rows = self.db.select("test_table", raw=True)
        for row in rows:
            self.assertNotIn("age", row)
    
    def test_drop_column_cascade(self):
        """Test ALTER TABLE DROP COLUMN CASCADE."""
        # First add an indexed column
        self.db.alter_add_column("test_table", {
            'name': 'email',
            'type': 'TEXT',
            'index': True
        })
        
        # Drop with cascade should succeed
        result = self.db.alter_drop_column("test_table", "email", cascade=True)
        self.assertIn("dropped", result.lower())
        
        schema = self._get_schema("test_table")
        self.assertNotIn("email", schema["columns"])
    
    def test_modify_column_type(self):
        """Test ALTER TABLE MODIFY COLUMN type change."""
        # First add a TEXT column
        self.db.alter_add_column("test_table", {
            'name': 'score',
            'type': 'TEXT'
        })
        
        # Update with numeric string
        self.db.update("test_table", {"score": "100"}, {"id": "1"})
        
        # Modify to INT
        result = self.db.alter_modify_column("test_table", "score", "INT", "")
        self.assertIn("modified", result.lower())
        
        schema = self._get_schema("test_table")
        self.assertEqual(schema["column_types"]["score"], "INT")
    
    def test_modify_column_invalid_conversion(self):
        """Test ALTER TABLE MODIFY COLUMN with invalid conversion."""
        # Add TEXT column with non-numeric data
        self.db.alter_add_column("test_table", {
            'name': 'data',
            'type': 'TEXT'
        })
        self.db.update("test_table", {"data": "not-a-number"}, {"id": "1"})
        
        # Try to modify to INT - should fail
        result = self.db.alter_modify_column("test_table", "data", "INT", "")
        self.assertIn("ERROR", result)
    
    def test_rename_column(self):
        """Test ALTER TABLE RENAME COLUMN."""
        result = self.db.alter_rename_column("test_table", "age", "years")
        
        self.assertIn("renamed", result.lower())
        
        # Verify old name gone
        schema = self._get_schema("test_table")
        self.assertNotIn("age", schema["columns"])
        self.assertIn("years", schema["columns"])
        
        # Verify data preserved
        rows = self.db.select("test_table", raw=True)
        for row in rows:
            self.assertIn("years", row)
            self.assertNotIn("age", row)
    
    def test_add_index(self):
        """Test ALTER TABLE ADD INDEX."""
        result = self.db.alter_add_index("test_table", ["name"])
        
        self.assertIn("Index added", result)
        
        schema = self._get_schema("test_table")
        self.assertIn("name", schema.get("indexes", []))
    
    def test_drop_index(self):
        """Test ALTER TABLE DROP INDEX."""
        # First add index
        self.db.alter_add_index("test_table", ["name"])
        
        # Then drop it
        result = self.db.alter_drop_index("test_table", "name")
        
        self.assertIn("dropped", result.lower())
        
        schema = self._get_schema("test_table")
        self.assertNotIn("name", schema.get("indexes", []))
    
    def test_add_foreign_key_constraint(self):
        """Test ALTER TABLE ADD FOREIGN KEY constraint."""
        # Create referenced table
        self.db.create_table("departments", [
            {'name': 'dept_id', 'type': 'INT', 'primary_key': True},
            {'name': 'dept_name', 'type': 'TEXT'}
        ])
        self.db.insert("departments", [1, "Engineering"])
        
        # Add column to test_table
        self.db.alter_add_column("test_table", {
            'name': 'dept_id',
            'type': 'INT'
        })
        
        # Add FK constraint
        result = self.db.alter_add_constraint("test_table", "FOREIGN_KEY", {
            'column': 'dept_id',\n            'references_table': 'departments',\n            'references_column': 'dept_id'\n        })
        
        self.assertIn("constraint added", result.lower())
        
        schema = self._get_schema("test_table")
        self.assertTrue(any(fk.get('column') == 'dept_id' for fk in schema.get("foreign_keys", [])))
    
    def test_add_unique_constraint(self):
        """Test ALTER TABLE ADD UNIQUE constraint."""
        result = self.db.alter_add_constraint("test_table", "UNIQUE", {
            'columns': ['name']
        })
        
        self.assertIn("constraint added", result.lower())
        
        schema = self._get_schema("test_table")
        self.assertTrue(any('name' in uc for uc in schema.get("unique_constraints", [])))
    
    def test_add_check_constraint(self):
        """Test ALTER TABLE ADD CHECK constraint."""
        result = self.db.alter_add_constraint("test_table", "CHECK", {
            'expression': 'age >= 18'
        })
        
        self.assertIn("constraint added", result.lower())
        
        schema = self._get_schema("test_table")
        self.assertIn("age >= 18", schema.get("check_constraints", []))
    
    def test_drop_constraint(self):
        """Test ALTER TABLE DROP CONSTRAINT."""
        # First add a unique constraint
        self.db.alter_add_constraint("test_table", "UNIQUE", {
            'columns': ['name']
        })
        
        # Then drop it
        result = self.db.alter_drop_constraint("test_table", "name")
        
        self.assertIn("dropped", result.lower())
    
    def _get_schema(self, table_name):
        """Helper to get table schema."""
        schema_key = f"_schema:{table_name}".encode()
        schema_data = self.db._db.get(schema_key)
        return json.loads(schema_data.decode())


class TestAlterTableParser(unittest.TestCase):
    """Test ALTER TABLE SQL parsing."""
    
    def setUp(self):
        self.parser = CommandParser()
    
    def test_parse_add_column(self):
        """Test parsing ALTER TABLE ADD COLUMN."""
        sql = "ALTER TABLE users ADD COLUMN email TEXT"
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'ALTER_ADD_COLUMN')
        self.assertEqual(params['table'], 'users')
        self.assertEqual(params['column']['name'], 'email')
    
    def test_parse_drop_column(self):
        """Test parsing ALTER TABLE DROP COLUMN."""
        sql = "ALTER TABLE users DROP COLUMN email"
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'ALTER_DROP_COLUMN')
        self.assertEqual(params['table'], 'users')
        self.assertEqual(params['column'], 'email')
    
    def test_parse_modify_column(self):
        """Test parsing ALTER TABLE MODIFY COLUMN."""
        sql = "ALTER TABLE users MODIFY COLUMN age FLOAT"
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'ALTER_MODIFY_COLUMN')
        self.assertEqual(params['table'], 'users')
        self.assertEqual(params['column'], 'age')
        self.assertEqual(params['new_type'], 'FLOAT')
    
    def test_parse_rename_column(self):
        """Test parsing ALTER TABLE RENAME COLUMN."""
        sql = "ALTER TABLE users RENAME COLUMN age TO years"
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'ALTER_RENAME_COLUMN')
        self.assertEqual(params['table'], 'users')
        self.assertEqual(params['old_name'], 'age')
        self.assertEqual(params['new_name'], 'years')
    
    def test_parse_add_index(self):
        """Test parsing ALTER TABLE ADD INDEX."""
        sql = "ALTER TABLE users ADD INDEX idx_name (name)"
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'ALTER_ADD_INDEX')
        self.assertEqual(params['table'], 'users')
        self.assertIn('name', params['columns'])
    
    def test_parse_add_constraint(self):
        """Test parsing ALTER TABLE ADD CONSTRAINT."""
        sql = "ALTER TABLE users ADD CONSTRAINT fk_dept FOREIGN KEY (dept_id) REFERENCES departments (id)"
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'ALTER_ADD_FK')
        self.assertEqual(params['table'], 'users')
        self.assertEqual(params['column'], 'dept_id')


class TestAlterTableEdgeCases(unittest.TestCase):
    """Test edge cases for ALTER TABLE."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db = Database(self.temp_dir, server_id=1)
        self.db.create_database("testdb")
        self.db.use_database("testdb")
        
        # Create table with data
        self.db.create_table("test_table", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'data', 'type': 'TEXT'}
        ])
        self.db.insert("test_table", [1, "test"])
    
    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.temp_dir)
    
    def test_add_column_already_exists(self):
        """Test adding column that already exists."""
        result = self.db.alter_add_column("test_table", {
            'name': 'data',  # Already exists
            'type': 'INT'
        })
        
        self.assertIn("ERROR", result)
        self.assertIn("already exists", result.lower())
    
    def test_drop_column_not_exists(self):
        """Test dropping column that doesn't exist."""
        result = self.db.alter_drop_column("test_table", "nonexistent")
        
        self.assertIn("ERROR", result)
        self.assertIn("does not exist", result.lower())
    
    def test_rename_column_already_exists(self):
        """Test renaming to existing column name."""
        result = self.db.alter_rename_column("test_table", "id", "data")
        
        self.assertIn("ERROR", result)
        self.assertIn("already exists", result.lower())
    
    def test_modify_column_not_exists(self):
        """Test modifying non-existent column."""
        result = self.db.alter_modify_column("test_table", "nonexistent", "INT", "")
        
        self.assertIn("ERROR", result)
    
    def test_drop_primary_key_without_cascade(self):
        """Test dropping primary key without CASCADE."""
        result = self.db.alter_drop_column("test_table", "id", cascade=False)
        
        self.assertIn("ERROR", result)
        self.assertIn("CASCADE", result)


if __name__ == '__main__':
    unittest.main(verbosity=2)
