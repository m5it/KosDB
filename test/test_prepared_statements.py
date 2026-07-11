"""
Test Prepared Statements for KosDB v3.3.0

Tests:
- PREPARE statement creation
- EXECUTE with parameter binding
- DEALLOCATE statement removal
- SQL injection prevention
- Positional (?) and named (:param) parameters
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prepared_statement_cache import (
    PreparedStatementCache, ParameterBinder, 
    ParameterStyle, SQLInjectionTest
)
from parser import CommandParser


class TestPreparedStatementParsing(unittest.TestCase):
    """Test parsing of PREPARE, EXECUTE, DEALLOCATE commands."""
    
    def setUp(self):
        self.parser = CommandParser()
    
    def test_parse_prepare(self):
        """Parse PREPARE statement."""
        sql = "PREPARE get_user AS SELECT * FROM users WHERE id = ?"
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'PREPARE')
        self.assertEqual(params['name'], 'get_user')
        self.assertIn('SELECT', params['sql'])
    
    def test_parse_prepare_with_named_params(self):
        """Parse PREPARE with named parameters."""
        sql = "PREPARE get_user AS SELECT * FROM users WHERE name = :name AND age > :min_age"
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'PREPARE')
        self.assertEqual(params['name'], 'get_user')
    
    def test_parse_execute_positional(self):
        """Parse EXECUTE with positional parameters."""
        sql = "EXECUTE get_user USING (42, 'Alice')"
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'EXECUTE')
        self.assertEqual(params['name'], 'get_user')
        self.assertIsInstance(params['parameters'], list)
    
    def test_parse_execute_named(self):
        """Parse EXECUTE with named parameters."""
        sql = "EXECUTE get_user USING id=42, name='Alice'"
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'EXECUTE')
        self.assertEqual(params['name'], 'get_user')
        self.assertIsInstance(params['parameters'], dict)
    
    def test_parse_execute_no_params(self):
        """Parse EXECUTE without parameters."""
        sql = "EXECUTE get_all_users"
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'EXECUTE')
        self.assertEqual(params['name'], 'get_all_users')
        self.assertIsNone(params.get('parameters'))
    
    def test_parse_deallocate(self):
        """Parse DEALLOCATE statement."""
        sql = "DEALLOCATE get_user"
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'DEALLOCATE')
        self.assertEqual(params['name'], 'get_user')
    
    def test_parse_deallocate_all(self):
        """Parse DEALLOCATE ALL statement."""
        sql = "DEALLOCATE ALL"
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'DEALLOCATE_ALL')


class TestParameterBinder(unittest.TestCase):
    """Test parameter binding functionality."""
    
    def setUp(self):
        self.binder = ParameterBinder()
    
    def test_bind_positional_integer(self):
        """Bind positional integer parameter."""
        sql = "SELECT * FROM users WHERE id = ?"
        result = self.binder.bind_positional(sql, [42])
        self.assertEqual(result, "SELECT * FROM users WHERE id = 42")
    
    def test_bind_positional_string(self):
        """Bind positional string parameter."""
        sql = "SELECT * FROM users WHERE name = ?"
        result = self.binder.bind_positional(sql, ["Alice"])
        self.assertEqual(result, "SELECT * FROM users WHERE name = 'Alice'")
    
    def test_bind_positional_multiple(self):
        """Bind multiple positional parameters."""
        sql = "SELECT * FROM users WHERE id = ? AND status = ?"
        result = self.binder.bind_positional(sql, [1, "active"])
        self.assertEqual(result, "SELECT * FROM users WHERE id = 1 AND status = 'active'")
    
    def test_bind_positional_float(self):
        """Bind float parameter."""
        sql = "SELECT * FROM products WHERE price = ?"
        result = self.binder.bind_positional(sql, [19.99])
        self.assertIn("19.99", result)
    
    def test_bind_positional_boolean(self):
        """Bind boolean parameter."""
        sql = "SELECT * FROM users WHERE active = ?"
        result = self.binder.bind_positional(sql, [True])
        self.assertEqual(result, "SELECT * FROM users WHERE active = TRUE")
    
    def test_bind_positional_null(self):
        """Bind NULL parameter."""
        sql = "SELECT * FROM users WHERE deleted_at = ?"
        result = self.binder.bind_positional(sql, [None])
        self.assertEqual(result, "SELECT * FROM users WHERE deleted_at = NULL")
    
    def test_bind_named_parameters(self):
        """Bind named parameters."""
        sql = "SELECT * FROM users WHERE name = :name AND age > :min_age"
        result = self.binder.bind_named(sql, {"name": "Alice", "min_age": 18})
        self.assertEqual(result, "SELECT * FROM users WHERE name = 'Alice' AND age > 18")
    
    def test_bind_mismatch_count(self):
        """Test parameter count mismatch raises error."""
        sql = "SELECT * FROM users WHERE id = ? AND name = ?"
        with self.assertRaises(ValueError) as context:
            self.binder.bind_positional(sql, [42])  # Missing second parameter
        self.assertIn("count mismatch", str(context.exception))


class TestSQLInjectionPrevention(unittest.TestCase):
    """Test SQL injection prevention in parameter binding."""
    
    def setUp(self):
        self.binder = ParameterBinder()
    
    def test_quote_escaping(self):
        """Test single quote escaping."""
        sql = "SELECT * FROM users WHERE name = ?"
        result = self.binder.bind_positional(sql, ["O'Brien"])
        self.assertEqual(result, "SELECT * FROM users WHERE name = 'O''Brien'")
    
    def test_double_quote_escaping(self):
        """Test double quote in string."""
        sql = "SELECT * FROM users WHERE name = ?"
        result = self.binder.bind_positional(sql, ['Say "Hello"'])
        self.assertIn("''Hello''", result)
    
    def test_backslash_escaping(self):
        """Test backslash escaping."""
        sql = "SELECT * FROM users WHERE path = ?"
        result = self.binder.bind_positional(sql, ["/path\\to\\file"])
        self.assertIn("\\\\\\\\to\\\\\\\\file", result)
    
    def test_null_byte_removal(self):
        """Test null byte removal (security)."""
        sql = "SELECT * FROM users WHERE name = ?"
        result = self.binder.bind_positional(sql, ["admin\x00' OR '1'='1"])
        self.assertNotIn("\x00", result)
        self.assertNotIn("' OR '", result)
    
    def test_comment_injection_blocked(self):
        """Test that SQL comments don't break out."""
        sql = "SELECT * FROM users WHERE id = ?"
        result = self.binder.bind_positional(sql, ["1; -- comment"])
        self.assertNotIn("--", result.replace("'--", ""))
    
    def test_union_injection_blocked(self):
        """Test that UNION injection is escaped."""
        sql = "SELECT * FROM users WHERE id = ?"
        result = self.binder.bind_positional(sql, ["1 UNION SELECT * FROM passwords"])
        self.assertIn("'1 UNION SELECT * FROM passwords'", result)
    
    def test_sql_injection_test_suite(self):
        """Run the comprehensive SQL injection test suite."""
        results = SQLInjectionTest.run_tests()
        
        failures = [(desc, msg) for desc, passed, msg in results if not passed]
        
        if failures:
            self.fail(f"SQL injection tests failed: {failures}")


class TestPreparedStatementCache(unittest.TestCase):
    """Test prepared statement cache functionality."""
    
    def setUp(self):
        self.cache = PreparedStatementCache(max_size=10)
    
    def test_prepare_statement(self):
        """Prepare a statement."""
        stmt = self.cache.prepare("get_user", "SELECT * FROM users WHERE id = ?")
        
        self.assertEqual(stmt.name, "get_user")
        self.assertEqual(stmt.sql_template, "SELECT * FROM users WHERE id = ?")
        self.assertEqual(stmt.parameter_style, ParameterStyle.QMARK)
    
    def test_prepare_named_params(self):
        """Prepare statement with named parameters."""
        stmt = self.cache.prepare("get_by_name", 
                                   "SELECT * FROM users WHERE name = :name")
        
        self.assertEqual(stmt.parameter_style, ParameterStyle.NAMED)
        self.assertEqual(stmt.parameters, ["name"])
    
    def test_execute_statement(self):
        """Prepare and execute a statement."""
        self.cache.prepare("get_user", "SELECT * FROM users WHERE id = ?")
        
        sql = self.cache.execute("get_user", [42])
        self.assertEqual(sql, "SELECT * FROM users WHERE id = 42")
    
    def test_execute_named(self):
        """Execute with named parameters."""
        self.cache.prepare("get_by_name", 
                          "SELECT * FROM users WHERE name = :name AND age > :min_age")
        
        sql = self.cache.execute("get_by_name", {"name": "Alice", "min_age": 18})
        self.assertEqual(sql, "SELECT * FROM users WHERE name = 'Alice' AND age > 18")
    
    def test_deallocate_statement(self):
        """Deallocate a prepared statement."""
        self.cache.prepare("temp_stmt", "SELECT 1")
        
        success = self.cache.deallocate("temp_stmt")
        self.assertTrue(success)
        
        # Should not exist anymore
        with self.assertRaises(ValueError):
            self.cache.execute("temp_stmt", [])
    
    def test_deallocate_nonexistent(self):
        """Deallocate non-existent statement."""
        success = self.cache.deallocate("nonexistent")
        self.assertFalse(success)
    
    def test_deallocate_all(self):
        """Deallocate all statements."""
        self.cache.prepare("stmt1", "SELECT 1")
        self.cache.prepare("stmt2", "SELECT 2")
        
        self.cache.deallocate_all()
        
        self.assertEqual(len(self.cache.list_statements()), 0)
    
    def test_cache_stats(self):
        """Get cache statistics."""
        self.cache.prepare("stmt1", "SELECT 1")
        self.cache.execute("stmt1", [])
        self.cache.execute("stmt1", [])
        
        stats = self.cache.get_stats()
        
        self.assertEqual(stats['prepares'], 1)
        self.assertEqual(stats['executes'], 2)
        self.assertEqual(stats['hits'], 2)
    
    def test_lru_eviction(self):
        """Test LRU eviction when cache is full."""
        cache = PreparedStatementCache(max_size=3)
        
        cache.prepare("stmt1", "SELECT 1")
        cache.prepare("stmt2", "SELECT 2")
        cache.prepare("stmt3", "SELECT 3")
        cache.prepare("stmt4", "SELECT 4")  # Should evict stmt1
        
        statements = cache.list_statements()
        self.assertNotIn("stmt1", statements)
        self.assertIn("stmt4", statements)


class TestPreparedStatementEdgeCases(unittest.TestCase):
    """Test edge cases for prepared statements."""
    
    def setUp(self):
        self.cache = PreparedStatementCache()
        self.parser = CommandParser()
    
    def test_prepare_duplicate_name(self):
        """Cannot prepare statement with duplicate name."""
        self.cache.prepare("my_stmt", "SELECT 1")
        
        with self.assertRaises(ValueError) as context:
            self.cache.prepare("my_stmt", "SELECT 2")
        
        self.assertIn("already exists", str(context.exception))
    
    def test_execute_not_found(self):
        """Execute non-existent statement."""
        with self.assertRaises(ValueError) as context:
            self.cache.execute("nonexistent", [])
        
        self.assertIn("not found", str(context.exception))
    
    def test_empty_string_parameter(self):
        """Bind empty string."""
        self.cache.prepare("test", "SELECT * FROM t WHERE name = ?")
        result = self.cache.execute("test", [""])
        self.assertEqual(result, "SELECT * FROM t WHERE name = ''")
    
    def test_unicode_parameter(self):
        """Bind unicode string."""
        self.cache.prepare("test", "SELECT * FROM t WHERE name = ?")
        result = self.cache.execute("test", ["日本語"])
        self.assertIn("日本語", result)


if __name__ == '__main__':
    unittest.main(verbosity=2)
