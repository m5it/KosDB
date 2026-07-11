"""
Tests for prepared statement manager.
"""

import unittest
import time
import threading
from prepared_statements import (
    PreparedStatementManager,
    ParameterError,
    get_session_manager,
    remove_session_manager,
    list_session_managers
)


class TestPreparedStatementManager(unittest.TestCase):
    
    def setUp(self):
        self.manager = PreparedStatementManager()
    
    def test_prepare_simple_query(self):
        """Test preparing a simple query."""
        sql = "SELECT * FROM users WHERE id = :user_id"
        stmt_id = self.manager.prepare(sql)
        
        self.assertIsNotNone(stmt_id)
        
        stmt = self.manager.get_statement(stmt_id)
        self.assertIsNotNone(stmt)
        self.assertEqual(stmt.original_sql, sql)
        self.assertEqual(stmt.parameter_names, ['user_id'])
    
    def test_prepare_positional(self):
        """Test preparing with positional parameters."""
        sql = "SELECT * FROM users WHERE id = ? AND name = ?"
        stmt_id = self.manager.prepare(sql)
        
        stmt = self.manager.get_statement(stmt_id)
        self.assertEqual(len(stmt.parameter_positions), 2)
    
    def test_prepare_no_params(self):
        """Test preparing query without parameters."""
        sql = "SELECT * FROM users"
        stmt_id = self.manager.prepare(sql)
        
        stmt = self.manager.get_statement(stmt_id)
        self.assertEqual(len(stmt.parameter_names), 0)
        self.assertEqual(len(stmt.parameter_positions), 0)
    
    def test_execute_named_params(self):
        """Test executing with named parameters."""
        sql = "SELECT * FROM users WHERE id = :user_id AND status = :status"
        stmt_id = self.manager.prepare(sql)
        
        final_sql, params = self.manager.execute(stmt_id, {
            'user_id': 123,
            'status': 'active'
        })
        
        self.assertIn('?', final_sql)
        self.assertEqual(params, [123, 'active'])
    
    def test_execute_positional_params(self):
        """Test executing with positional parameters."""
        sql = "SELECT * FROM users WHERE id = ? AND name = ?"
        stmt_id = self.manager.prepare(sql)
        
        final_sql, params = self.manager.execute(stmt_id, [123, 'John'])
        
        self.assertEqual(params, [123, 'John'])
    
    def test_execute_missing_param(self):
        """Test error on missing parameter."""
        sql = "SELECT * FROM users WHERE id = :user_id"
        stmt_id = self.manager.prepare(sql)
        
        with self.assertRaises(ParameterError):
            self.manager.execute(stmt_id, {})
    
    def test_execute_wrong_param_type(self):
        """Test error on wrong parameter type."""
        sql = "SELECT * FROM users WHERE id = :user_id"
        stmt_id = self.manager.prepare(sql)
        
        with self.assertRaises(ParameterError):
            self.manager.execute(stmt_id, ['not a dict'])
    
    def test_deallocate(self):
        """Test deallocating a statement."""
        sql = "SELECT * FROM users"
        stmt_id = self.manager.prepare(sql)
        
        success = self.manager.deallocate(stmt_id)
        self.assertTrue(success)
        
        # Should no longer exist
        self.assertIsNone(self.manager.get_statement(stmt_id))
    
    def test_deallocate_nonexistent(self):
        """Test deallocating non-existent statement."""
        success = self.manager.deallocate("fake_id")
        self.assertFalse(success)
    
    def test_deallocate_all(self):
        """Test deallocating all statements."""
        self.manager.prepare("SELECT 1")
        self.manager.prepare("SELECT 2")
        
        self.manager.deallocate_all()
        
        self.assertEqual(len(self.manager.list_statements()), 0)
    
    def test_duplicate_preparation(self):
        """Test that identical queries return same ID."""
        sql = "SELECT * FROM users WHERE id = ?"
        
        stmt_id1 = self.manager.prepare(sql)
        stmt_id2 = self.manager.prepare(sql)
        
        self.assertEqual(stmt_id1, stmt_id2)
    
    def test_max_statements(self):
        """Test max statements limit."""
        manager = PreparedStatementManager(max_statements=2)
        
        manager.prepare("SELECT 1")
        manager.prepare("SELECT 2")
        
        with self.assertRaises(ValueError):
            manager.prepare("SELECT 3")
    
    def test_usage_count(self):
        """Test that use count increments."""
        sql = "SELECT * FROM users WHERE id = ?"
        stmt_id = self.manager.prepare(sql)
        
        self.manager.execute(stmt_id, [1])
        self.manager.execute(stmt_id, [2])
        
        stmt = self.manager.get_statement(stmt_id)
        self.assertEqual(stmt.use_count, 2)
    
    def test_mixed_parameters_error(self):
        """Test error on mixed named and positional."""
        sql = "SELECT * WHERE id = ? AND name = :name"
        
        with self.assertRaises(ValueError):
            self.manager.prepare(sql)


class TestSessionManagers(unittest.TestCase):
    
    def test_get_session_manager(self):
        """Test getting session manager."""
        manager = get_session_manager("session_123")
        self.assertIsNotNone(manager)
        
        # Same session returns same manager
        manager2 = get_session_manager("session_123")
        self.assertIs(manager, manager2)
    
    def test_remove_session_manager(self):
        """Test removing session manager."""
        get_session_manager("session_456")
        remove_session_manager("session_456")
        
        # Should create new manager
        manager = get_session_manager("session_456")
        # Fresh manager has no statements
        self.assertEqual(len(manager.list_statements()), 0)
    
    def test_list_session_managers(self):
        """Test listing active sessions."""
        get_session_manager("session_A")
        get_session_manager("session_B")
        
        sessions = list_session_managers()
        self.assertIn("session_A", sessions)
        self.assertIn("session_B", sessions)


if __name__ == '__main__':
    unittest.main(verbosity=2)
