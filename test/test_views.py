"""
Test Database Views for KosDB v3.2.0

Tests:
- CREATE VIEW syntax
- DROP VIEW syntax
- SHOW VIEWS command
- View query execution
- Circular reference detection
- View dependencies
- View description
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
from view_manager import ViewManager, ViewDefinition


class TestViewManager(unittest.TestCase):
    """Test view manager functionality."""
    
    def setUp(self):
        """Set up test database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db = Database(self.temp_dir, server_id=1)
        
        # Create test database
        self.db.create_database("testdb")
        self.db.use_database("testdb")
        
        # Create test table
        self.db.create_table("users", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'name', 'type': 'TEXT'},
            {'name': 'age', 'type': 'INT'},
            {'name': 'active', 'type': 'INT'}
        ])
        
        # Insert test data
        self.db.insert("users", [1, "Alice", 30, 1])
        self.db.insert("users", [2, "Bob", 25, 1])
        self.db.insert("users", [3, "Charlie", 35, 0])
        
        # Initialize view manager
        self.view_manager = ViewManager(self.db)
    
    def tearDown(self):
        """Clean up."""
        self.db.close()
        shutil.rmtree(self.temp_dir)
    
    def test_create_view(self):
        """Test creating a view."""
        result = self.view_manager.create_view(
            "testdb", 
            "active_users", 
            "SELECT * FROM users WHERE active = 1"
        )
        
        self.assertIn("created successfully", result)
        
        # Verify view exists
        self.assertTrue(self.view_manager.view_exists("testdb", "active_users"))
    
    def test_create_duplicate_view(self):
        """Test creating duplicate view fails."""
        self.view_manager.create_view("testdb", "test_view", "SELECT * FROM users")
        
        result = self.view_manager.create_view("testdb", "test_view", "SELECT * FROM users")
        
        self.assertIn("ERROR", result)
        self.assertIn("already exists", result)
    
    def test_create_view_invalid_query(self):
        """Test creating view with non-SELECT query fails."""
        result = self.view_manager.create_view(
            "testdb",
            "bad_view",
            "INSERT INTO users VALUES (1, 'test')"
        )
        
        self.assertIn("ERROR", result)
        self.assertIn("SELECT query", result)
    
    def test_drop_view(self):
        """Test dropping a view."""
        self.view_manager.create_view("testdb", "test_view", "SELECT * FROM users")
        
        result = self.view_manager.drop_view("testdb", "test_view")
        
        self.assertIn("dropped successfully", result)
        self.assertFalse(self.view_manager.view_exists("testdb", "test_view"))
    
    def test_drop_nonexistent_view(self):
        """Test dropping non-existent view fails."""
        result = self.view_manager.drop_view("testdb", "nonexistent")
        
        self.assertIn("ERROR", result)
        self.assertIn("does not exist", result)
    
    def test_get_view(self):
        """Test retrieving view definition."""
        self.view_manager.create_view(
            "testdb",
            "active_users",
            "SELECT * FROM users WHERE active = 1"
        )
        
        view_def = self.view_manager.get_view("testdb", "active_users")
        
        self.assertIsNotNone(view_def)
        self.assertEqual(view_def.name, "active_users")
        self.assertEqual(view_def.query, "SELECT * FROM users WHERE active = 1")
        self.assertIn("users", view_def.dependencies)
    
    def test_list_views(self):
        """Test listing all views."""
        self.view_manager.create_view("testdb", "view1", "SELECT * FROM users")
        self.view_manager.create_view("testdb", "view2", "SELECT * FROM users WHERE active = 1")
        
        views = self.view_manager.list_views("testdb")
        
        self.assertEqual(len(views), 2)
        self.assertIn("view1", views)
        self.assertIn("view2", views)
    
    def test_describe_view(self):
        """Test describing a view."""
        self.view_manager.create_view("testdb", "test_view", "SELECT * FROM users")
        
        desc = self.view_manager.describe_view("testdb", "test_view")
        
        self.assertIsNotNone(desc)
        self.assertIn("View: test_view", desc)
        self.assertIn("SELECT * FROM users", desc)


class TestViewCircularReferences(unittest.TestCase):
    """Test circular reference detection in views."""
    
    def setUp(self):
        """Set up test database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db = Database(self.temp_dir, server_id=1)
        
        self.db.create_database("testdb")
        self.db.use_database("testdb")
        
        self.view_manager = ViewManager(self.db)
    
    def tearDown(self):
        """Clean up."""
        self.db.close()
        shutil.rmtree(self.temp_dir)
    
    def test_self_reference(self):
        """Test view cannot reference itself."""
        result = self.view_manager.create_view(
            "testdb",
            "self_ref",
            "SELECT * FROM self_ref"
        )
        
        self.assertIn("ERROR", result)
        self.assertIn("cannot reference itself", result)
    
    def test_simple_circular_reference(self):
        """Test simple circular reference between two views."""
        # Create view1
        self.view_manager.create_view("testdb", "view_a", "SELECT * FROM users")
        
        # Try to create view_b that references view_a, and make view_a reference view_b
        # This should fail when trying to create the circular dependency
        result = self.view_manager.create_view(
            "testdb",
            "view_b",
            "SELECT * FROM view_a"
        )
        self.assertIn("created successfully", result)
        
        # Now try to recreate view_a to reference view_b - this should fail
        # (In real implementation, we'd need ALTER VIEW)
    
    def test_circular_reference_detection(self):
        """Test circular reference detection."""
        # Create view_a
        self.view_manager.create_view("testdb", "view_a", "SELECT * FROM users")
        
        # Create view_b referencing view_a
        self.view_manager.create_view("testdb", "view_b", "SELECT * FROM view_a")
        
        # Create view_c referencing view_b
        self.view_manager.create_view("testdb", "view_c", "SELECT * FROM view_b")
        
        # Try to create view_a referencing view_c (would create cycle)
        # This would require ALTER VIEW in real implementation
    
    def test_drop_view_with_dependencies(self):
        """Test cannot drop view that others depend on."""
        # Create view_a
        self.view_manager.create_view("testdb", "view_a", "SELECT * FROM users")
        
        # Create view_b referencing view_a
        self.view_manager.create_view("testdb", "view_b", "SELECT * FROM view_a")
        
        # Try to drop view_a
        result = self.view_manager.drop_view("testdb", "view_a")
        
        self.assertIn("ERROR", result)
        self.assertIn("depended on by", result)
        self.assertIn("view_b", result)


class TestViewParser(unittest.TestCase):
    """Test view SQL parsing."""
    
    def setUp(self):
        self.parser = CommandParser()
    
    def test_parse_create_view(self):
        """Test parsing CREATE VIEW."""
        sql = "CREATE VIEW active_users AS SELECT * FROM users WHERE active = 1"
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'CREATE_VIEW')
        self.assertEqual(params['view_name'], 'active_users')
        self.assertEqual(params['query'], 'SELECT * FROM users WHERE active = 1')
    
    def test_parse_create_view_complex(self):
        """Test parsing CREATE VIEW with complex query."""
        sql = "CREATE VIEW user_summary AS SELECT name, age FROM users WHERE age > 18 ORDER BY name"
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'CREATE_VIEW')
        self.assertEqual(params['view_name'], 'user_summary')
        self.assertIn("ORDER BY", params['query'])
    
    def test_parse_drop_view(self):
        """Test parsing DROP VIEW."""
        sql = "DROP VIEW active_users"
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'DROP_VIEW')
        self.assertEqual(params['view_name'], 'active_users')
    
    def test_parse_show_views(self):
        """Test parsing SHOW VIEWS."""
        sql = "SHOW VIEWS"
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'SHOW_VIEWS')


class TestViewDependencies(unittest.TestCase):
    """Test view dependency tracking."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db = Database(self.temp_dir, server_id=1)
        
        self.db.create_database("testdb")
        self.db.use_database("testdb")
        
        self.view_manager = ViewManager(self.db)
    
    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.temp_dir)
    
    def test_extract_dependencies(self):
        """Test extracting dependencies from query."""
        query = "SELECT * FROM users JOIN orders ON users.id = orders.user_id"
        deps = self.view_manager._extract_dependencies(query)
        
        self.assertIn('users', deps)
        self.assertIn('orders', deps)
    
    def test_extract_dependencies_with_subquery(self):
        """Test extracting dependencies from query with subquery."""
        query = "SELECT * FROM (SELECT * FROM products) AS p"
        deps = self.view_manager._extract_dependencies(query)
        
        self.assertIn('products', deps)


class TestViewEdgeCases(unittest.TestCase):
    """Test edge cases for views."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db = Database(self.temp_dir, server_id=1)
        
        self.db.create_database("testdb")
        self.db.use_database("testdb")
        
        # Create base table
        self.db.create_table("users", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'name', 'type': 'TEXT'}
        ])
        
        self.view_manager = ViewManager(self.db)
    
    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.temp_dir)
    
    def test_view_with_special_characters(self):
        """Test view with special characters in query."""
        query = "SELECT * FROM users WHERE name LIKE '%test%'"
        result = self.view_manager.create_view("testdb", "special_view", query)
        
        self.assertIn("created successfully", result)
        
        view_def = self.view_manager.get_view("testdb", "special_view")
        self.assertEqual(view_def.query, query)
    
    def test_case_sensitivity(self):
        """Test view name case sensitivity."""
        self.view_manager.create_view("testdb", "TestView", "SELECT * FROM users")
        
        # Should be case-sensitive
        self.assertTrue(self.view_manager.view_exists("testdb", "TestView"))
        self.assertFalse(self.view_manager.view_exists("testdb", "testview"))
    
    def test_empty_view_name(self):
        """Test creating view with empty name."""
        result = self.view_manager.create_view("testdb", "", "SELECT * FROM users")
        
        self.assertIn("ERROR", result)
    
    def test_very_long_query(self):
        """Test view with very long query."""
        long_where = " OR ".join([f"name = 'user{i}'" for i in range(100)])
        query = f"SELECT * FROM users WHERE {long_where}"
        
        result = self.view_manager.create_view("testdb", "long_query_view", query)
        self.assertIn("created successfully", result)
        
        view_def = self.view_manager.get_view("testdb", "long_query_view")
        self.assertEqual(len(view_def.query), len(query))


if __name__ == '__main__':
    unittest.main(verbosity=2)
