"""
Test JSON Data Type for KosDB v3.2.0

Tests:
- CREATE TABLE with JSON column type
- JSON validation on INSERT
- JSON validation on UPDATE
- JSON extraction operators (-> and ->>)
- JSON functions: json_extract, json_contains, json_keys, json_array_length
- Invalid JSON handling
- Nested JSON operations
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
from json_functions import (
    validate_json, parse_json, json_extract, json_extract_text,
    json_contains, json_keys, json_array_length, json_valid
)


class TestJSONType(unittest.TestCase):
    """Test JSON data type functionality."""
    
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
    
    def test_json_type_parsing(self):
        """Test parsing JSON column type."""
        sql = "CREATE TABLE events (id INT PRIMARY KEY, data JSON)"
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'CREATE')
        columns = params.get('columns', [])
        
        # Find data column
        data_col = next((c for c in columns if c.get('name') == 'data'), None)
        self.assertIsNotNone(data_col)
        self.assertEqual(data_col.get('type'), 'JSON')
    
    def test_create_table_with_json_column(self):
        """Test creating table with JSON column."""
        result = self.db.create_table("events", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'data', 'type': 'JSON'},
            {'name': 'name', 'type': 'TEXT'}
        ])
        self.assertIn("created", result.lower())
    
    def test_insert_valid_json_object(self):
        """Test INSERT with valid JSON object."""
        self.db.create_table("events", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'data', 'type': 'JSON'}
        ])
        
        result = self.db.insert("events", [1, '{"user": "Alice", "action": "login"}'])
        self.assertIn("Inserted", result)
    
    def test_insert_valid_json_array(self):
        """Test INSERT with valid JSON array."""
        self.db.create_table("events", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'data', 'type': 'JSON'}
        ])
        
        result = self.db.insert("events", [1, '[1, 2, 3, 4, 5]'])
        self.assertIn("Inserted", result)
    
    def test_insert_invalid_json(self):
        """Test INSERT with invalid JSON fails."""
        self.db.create_table("events", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'data', 'type': 'JSON'}
        ])
        
        result = self.db.insert("events", [1, 'not valid json'])
        self.assertIn("ERROR", result)
        self.assertIn("Invalid JSON", result)
    
    def test_insert_null_json(self):
        """Test INSERT with NULL JSON value."""
        self.db.create_table("events", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'data', 'type': 'JSON'}
        ])
        
        result = self.db.insert("events", [1, None])
        self.assertIn("Inserted", result)
    
    def test_update_json_column(self):
        """Test UPDATE JSON column."""
        self.db.create_table("events", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'data', 'type': 'JSON'}
        ])
        
        self.db.insert("events", [1, '{"count": 1}'])
        
        result = self.db.update("events", {"data": '{"count": 2}'}, {"id": "1"})
        self.assertIn("Updated", result)
    
    def test_update_invalid_json(self):
        """Test UPDATE with invalid JSON fails."""
        self.db.create_table("events", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'data', 'type': 'JSON'}
        ])
        
        self.db.insert("events", [1, '{"count": 1}'])
        
        result = self.db.update("events", {"data": 'invalid json'}, {"id": "1"})
        self.assertIn("ERROR", result)
        self.assertIn("Invalid JSON", result)


class TestJSONFunctions(unittest.TestCase):
    """Test JSON utility functions."""
    
    def test_validate_json_valid(self):
        """Test validate_json with valid JSON."""
        self.assertTrue(validate_json('{"a": 1}'))
        self.assertTrue(validate_json('[1, 2, 3]'))
        self.assertTrue(validate_json('"string"'))
        self.assertTrue(validate_json(123))
        self.assertTrue(validate_json(True))
        self.assertTrue(validate_json(None))
        self.assertTrue(validate_json({'a': 1}))  # Already parsed
    
    def test_validate_json_invalid(self):
        """Test validate_json with invalid JSON."""
        self.assertFalse(validate_json('not json'))
        self.assertFalse(validate_json('{invalid}'))
        self.assertFalse(validate_json(''))
    
    def test_json_extract_object(self):
        """Test json_extract from object."""
        data = '{"user": {"name": "Alice", "age": 30}, "action": "login"}'
        
        self.assertEqual(json_extract(data, '$.user.name'), 'Alice')
        self.assertEqual(json_extract(data, '$.user.age'), 30)
        self.assertEqual(json_extract(data, '$.action'), 'login')
    
    def test_json_extract_array(self):
        """Test json_extract from array."""
        data = '[1, 2, 3, 4, 5]'
        
        self.assertEqual(json_extract(data, '$[0]'), 1)
        self.assertEqual(json_extract(data, '$[4]'), 5)
    
    def test_json_extract_nested(self):
        """Test json_extract with nested path."""
        data = '{"store": {"book": [{"title": "Book 1"}, {"title": "Book 2"}]}}'
        
        self.assertEqual(json_extract(data, '$.store.book[0].title'), 'Book 1')
    
    def test_json_extract_text(self):
        """Test json_extract_text returns unquoted string."""
        data = '{"name": "Alice"}'
        
        self.assertEqual(json_extract_text(data, '$.name'), 'Alice')
        
        # For non-string values, should return JSON representation
        data = '{"count": 42}'
        self.assertEqual(json_extract_text(data, '$.count'), '42')
    
    def test_json_contains(self):
        """Test json_contains function."""
        data = '{"a": 1, "b": 2, "c": [1, 2, 3]}'
        
        self.assertTrue(json_contains(data, 1))
        self.assertTrue(json_contains(data, 2))
        self.assertTrue(json_contains(data, 3))
        self.assertFalse(json_contains(data, 4))
    
    def test_json_contains_with_path(self):
        """Test json_contains with path."""
        data = '{"user": {"tags": ["admin", "active"]}}'
        
        self.assertTrue(json_contains(data, 'admin', '$.user.tags'))
        self.assertFalse(json_contains(data, 'inactive', '$.user.tags'))
    
    def test_json_keys(self):
        """Test json_keys function."""
        data = '{"name": "Alice", "age": 30, "city": "NYC"}'
        
        keys = json_keys(data)
        self.assertIsNotNone(keys)
        self.assertIn('name', keys)
        self.assertIn('age', keys)
        self.assertIn('city', keys)
    
    def test_json_keys_with_path(self):
        """Test json_keys with path."""
        data = '{"user": {"name": "Alice", "age": 30}}'
        
        keys = json_keys(data, '$.user')
        self.assertIsNotNone(keys)
        self.assertIn('name', keys)
        self.assertIn('age', keys)
    
    def test_json_array_length(self):
        """Test json_array_length function."""
        data = '[1, 2, 3, 4, 5]'
        
        self.assertEqual(json_array_length(data), 5)
        
        data = '[]'
        self.assertEqual(json_array_length(data), 0)
    
    def test_json_array_length_with_path(self):
        """Test json_array_length with path."""
        data = '{"user": {"items": [1, 2, 3]}}'
        
        self.assertEqual(json_array_length(data, '$.user.items'), 3)
    
    def test_json_valid_function(self):
        """Test json_valid function."""
        self.assertTrue(json_valid('{"a": 1}'))
        self.assertTrue(json_valid('[]'))
        self.assertFalse(json_valid('not json'))
        self.assertFalse(json_valid('{broken}'))


class TestJSONExtractionOperators(unittest.TestCase):
    """Test JSON extraction operators in SELECT."""
    
    def setUp(self):
        """Set up test database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db = Database(self.temp_dir, server_id=1)
        self.parser = CommandParser()
        
        self.db.create_database("testdb")
        self.db.use_database("testdb")
    
    def tearDown(self):
        """Clean up."""
        self.db.close()
        shutil.rmtree(self.temp_dir)
    
    def test_parse_json_extraction_operator(self):
        """Test parsing -> operator."""
        sql = "SELECT data->$.user.name FROM events"
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'SELECT')
        columns = params.get('columns', [])
        
        self.assertEqual(len(columns), 1)
        self.assertEqual(columns[0]['name'], 'data')
        self.assertEqual(columns[0]['json_path'], '$.user.name')
        self.assertFalse(columns[0]['json_as_text'])
    
    def test_parse_json_extraction_text_operator(self):
        """Test parsing ->> operator."""
        sql = "SELECT data->>$.user.name FROM events"
        cmd_type, params = self.parser.parse(sql)
        
        columns = params.get('columns', [])
        self.assertTrue(columns[0]['json_as_text'])
    
    def test_parse_json_with_alias(self):
        """Test parsing JSON extraction with alias."""
        sql = "SELECT data->$.user.name AS username FROM events"
        cmd_type, params = self.parser.parse(sql)
        
        columns = params.get('columns', [])
        self.assertEqual(columns[0]['alias'], 'username')
    
    def test_json_select_extraction(self):
        """Test SELECT with JSON extraction."""
        self.db.create_table("events", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'data', 'type': 'JSON'}
        ])
        
        self.db.insert("events", [1, '{"user": {"name": "Alice", "id": 123}}'])
        self.db.insert("events", [2, '{"user": {"name": "Bob", "id": 456}}'])
        
        # Test extraction via column specs
        columns = [
            {'name': 'data', 'json_path': '$.user.name', 'json_as_text': True, 'alias': 'username'}
        ]
        results = self.db.select("events", columns=columns, raw=True)
        
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['username'], 'Alice')
        self.assertEqual(results[1]['username'], 'Bob')


class TestJSONEdgeCases(unittest.TestCase):
    """Test edge cases for JSON type."""
    
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
    
    def test_empty_json_object(self):
        """Test empty JSON object."""
        self.db.create_table("events", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'data', 'type': 'JSON'}
        ])
        
        result = self.db.insert("events", [1, '{}'])
        self.assertIn("Inserted", result)
    
    def test_empty_json_array(self):
        """Test empty JSON array."""
        self.db.create_table("events", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'data', 'type': 'JSON'}
        ])
        
        result = self.db.insert("events", [1, '[]'])
        self.assertIn("Inserted", result)
    
    def test_json_with_special_characters(self):
        """Test JSON with special characters."""
        self.db.create_table("events", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'data', 'type': 'JSON'}
        ])
        
        result = self.db.insert("events", [1, '{"message": "Hello\\nWorld\\t!"}'])
        self.assertIn("Inserted", result)
    
    def test_json_with_unicode(self):
        """Test JSON with unicode characters."""
        self.db.create_table("events", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'data', 'type': 'JSON'}
        ])
        
        result = self.db.insert("events", [1, '{"name": "日本語"}'])
        self.assertIn("Inserted", result)
    
    def test_deeply_nested_json(self):
        """Test deeply nested JSON."""
        self.db.create_table("events", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'data', 'type': 'JSON'}
        ])
        
        nested = '{"a": {"b": {"c": {"d": {"e": "deep"}}}}}'
        result = self.db.insert("events", [1, nested])
        self.assertIn("Inserted", result)
        
        # Test extraction
        extracted = json_extract(nested, '$.a.b.c.d.e')
        self.assertEqual(extracted, 'deep')
    
    def test_json_number_types(self):
        """Test JSON number types."""
        self.db.create_table("events", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'data', 'type': 'JSON'}
        ])
        
        # Integer
        result = self.db.insert("events", [1, '{"count": 42}'])
        self.assertIn("Inserted", result)
        
        # Float
        result = self.db.insert("events", [2, '{"price": 19.99}'])
        self.assertIn("Inserted", result)
        
        # Scientific notation
        result = self.db.insert("events", [3, '{"big": 1e10}'])
        self.assertIn("Inserted", result)
    
    def test_json_boolean_and_null(self):
        """Test JSON boolean and null values."""
        self.db.create_table("events", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'data', 'type': 'JSON'}
        ])
        
        result = self.db.insert("events", [1, '{"active": true, "deleted": false, "value": null}'])
        self.assertIn("Inserted", result)


if __name__ == '__main__':
    unittest.main(verbosity=2)
