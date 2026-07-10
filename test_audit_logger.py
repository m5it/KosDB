"""
Unit tests for Audit Logger module.

Tests audit entry creation, filtering, and output handlers.
"""

import unittest
import json
import tempfile
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from audit_logger import (
    AuditEntry,
    AuditFilter,
    AuditLogger,
    FileAuditHandler,
    AuditAction,
    AuditLevel,
    create_audit_logger
)


class TestAuditEntry(unittest.TestCase):
    """Test AuditEntry class."""
    
    def test_creation(self):
        """Test audit entry creation."""
        entry = AuditEntry(
            timestamp="2024-01-15T10:30:00",
            event_id="abc123",
            user="admin",
            client_ip="192.168.1.1",
            action="DATA_READ",
            command="SELECT * FROM users",
            command_type="SELECT",
            affected_tables=["users"],
            success=True,
            execution_time_ms=45.5
        )
        
        self.assertEqual(entry.user, "admin")
        self.assertEqual(entry.command, "SELECT * FROM users")
        self.assertTrue(entry.success)
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        entry = AuditEntry(
            timestamp="2024-01-15T10:30:00",
            event_id="abc123",
            user="admin",
            client_ip="192.168.1.1",
            action="DATA_READ",
            command="SELECT * FROM users",
            command_type="SELECT",
            affected_tables=["users"],
            success=True,
            execution_time_ms=45.5
        )
        
        data = entry.to_dict()
        self.assertEqual(data['user'], "admin")
        self.assertEqual(data['action'], "DATA_READ")
    
    def test_to_json(self):
        """Test conversion to JSON."""
        entry = AuditEntry(
            timestamp="2024-01-15T10:30:00",
            event_id="abc123",
            user="admin",
            client_ip="192.168.1.1",
            action="DATA_READ",
            command="SELECT * FROM users",
            command_type="SELECT",
            affected_tables=["users"],
            success=True,
            execution_time_ms=45.5
        )
        
        json_str = entry.to_json()
        data = json.loads(json_str)
        self.assertEqual(data['user'], "admin")


class TestAuditFilter(unittest.TestCase):
    """Test AuditFilter class."""
    
    def test_should_log_normal_command(self):
        """Test that normal commands are logged."""
        filter_config = AuditFilter()
        
        entry = AuditEntry(
            timestamp="2024-01-15T10:30:00",
            event_id="abc123",
            user="admin",
            client_ip="192.168.1.1",
            action="DATA_READ",
            command="SELECT * FROM users",
            command_type="SELECT",
            affected_tables=["users"],
            success=True,
            execution_time_ms=45.5
        )
        
        self.assertTrue(filter_config.should_log(entry))
    
    def test_exclude_sensitive_commands(self):
        """Test exclusion of sensitive commands."""
        filter_config = AuditFilter()
        
        entry = AuditEntry(
            timestamp="2024-01-15T10:30:00",
            event_id="abc123",
            user="admin",
            client_ip="192.168.1.1",
            action="AUTHENTICATION",
            command="PASS secret123",
            command_type="PASS",
            affected_tables=[],
            success=True,
            execution_time_ms=0.0
        )
        
        # Should be excluded
        self.assertFalse(filter_config.should_log(entry))
    
    def test_mask_sensitive(self):
        """Test masking of sensitive data."""
        filter_config = AuditFilter()
        
        entry = AuditEntry(
            timestamp="2024-01-15T10:30:00",
            event_id="abc123",
            user="admin",
            client_ip="192.168.1.1",
            action="AUTHENTICATION",
            command="PASS secret123",
            command_type="PASS",
            affected_tables=[],
            success=True,
            execution_time_ms=0.0
        )
        
        masked = filter_config.mask_sensitive(entry)
        self.assertEqual(masked.command, "[MASKED]")
    
    def test_exclude_users(self):
        """Test user exclusion."""
        filter_config = AuditFilter(exclude_users={"system", "monitor"})
        
        entry = AuditEntry(
            timestamp="2024-01-15T10:30:00",
            event_id="abc123",
            user="system",
            client_ip="192.168.1.1",
            action="DATA_READ",
            command="SELECT 1",
            command_type="SELECT",
            affected_tables=[],
            success=True,
            execution_time_ms=0.0
        )
        
        self.assertFalse(filter_config.should_log(entry))


class TestFileAuditHandler(unittest.TestCase):
    """Test FileAuditHandler class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_write_entry(self):
        """Test writing audit entry to file."""
        handler = FileAuditHandler(
            log_dir=self.temp_dir,
            buffer_size=1  # Force immediate write
        )
        
        entry = AuditEntry(
            timestamp="2024-01-15T10:30:00",
            event_id="abc123",
            user="admin",
            client_ip="192.168.1.1",
            action="DATA_READ",
            command="SELECT * FROM users",
            command_type="SELECT",
            affected_tables=["users"],
            success=True,
            execution_time_ms=45.5
        )
        
        handler.write(entry)
        handler.flush()
        
        # Check file exists
        log_files = list(Path(self.temp_dir).glob("*.jsonl"))
        self.assertEqual(len(log_files), 1)
        
        # Check content
        with open(log_files[0], 'r') as f:
            line = f.readline()
            data = json.loads(line)
            self.assertEqual(data['user'], "admin")
        
        handler.close()
    
    def test_rotation(self):
        """Test log rotation."""
        handler = FileAuditHandler(
            log_dir=self.temp_dir,
            max_size_mb=0.001,  # Very small for testing
            buffer_size=1
        )
        
        # Write enough data to trigger rotation
        for i in range(100):
            entry = AuditEntry(
                timestamp="2024-01-15T10:30:00",
                event_id=f"abc{i}",
                user="admin",
                client_ip="192.168.1.1",
                action="DATA_READ",
                command="SELECT * FROM users",
                command_type="SELECT",
                affected_tables=["users"],
                success=True,
                execution_time_ms=45.5
            )
            handler.write(entry)
        
        handler.flush()
        
        # Should have rotated
        log_files = list(Path(self.temp_dir).glob("*.jsonl*"))
        self.assertGreaterEqual(len(log_files), 1)
        
        handler.close()


class TestAuditLogger(unittest.TestCase):
    """Test AuditLogger class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_log_entry(self):
        """Test logging an entry."""
        logger = AuditLogger(async_mode=False)
        
        handler = Mock()
        handler.write = Mock()
        logger.add_handler(handler)
        
        entry = logger.log(
            user="admin",
            client_ip="192.168.1.1",
            command="SELECT * FROM users",
            command_type="SELECT",
            success=True
        )
        
        self.assertIsNotNone(entry)
        self.assertEqual(entry.user, "admin")
        handler.write.assert_called_once()
        
        logger.close()
    
    def test_log_filtered(self):
        """Test that filtered entries are not logged."""
        filter_config = AuditFilter(exclude_commands={"PING"})
        logger = AuditLogger(filter_config=filter_config, async_mode=False)
        
        handler = Mock()
        handler.write = Mock()
        logger.add_handler(handler)
        
        entry = logger.log(
            user="admin",
            client_ip="192.168.1.1",
            command="PING",
            command_type="PING",
            success=True
        )
        
        self.assertIsNone(entry)
        handler.write.assert_not_called()
        
        logger.close()
    
    def test_multiple_handlers(self):
        """Test logging to multiple handlers."""
        logger = AuditLogger(async_mode=False)
        
        handler1 = Mock()
        handler2 = Mock()
        
        logger.add_handler(handler1)
        logger.add_handler(handler2)
        
        logger.log(
            user="admin",
            client_ip="192.168.1.1",
            command="SELECT 1",
            success=True
        )
        
        handler1.write.assert_called_once()
        handler2.write.assert_called_once()
        
        logger.close()


class TestQueryFunctionality(unittest.TestCase):
    """Test audit log querying."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.logger = create_audit_logger(log_dir=self.temp_dir)
        
        # Log some entries
        for i in range(5):
            self.logger.log(
                user="admin",
                client_ip="192.168.1.1",
                command=f"SELECT * FROM table{i}",
                command_type="SELECT",
                success=True
            )
        
        self.logger.flush()
    
    def tearDown(self):
        """Clean up."""
        self.logger.close()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_query_by_user(self):
        """Test querying by user."""
        results = self.logger.query(user="admin", limit=10)
        self.assertEqual(len(results), 5)
    
    def test_query_limit(self):
        """Test query limit."""
        results = self.logger.query(limit=3)
        self.assertEqual(len(results), 3)


class TestConvenienceFunction(unittest.TestCase):
    """Test convenience function."""
    
    def test_create_audit_logger(self):
        """Test factory function."""
        temp_dir = tempfile.mkdtemp()
        
        logger = create_audit_logger(log_dir=temp_dir)
        
        self.assertIsInstance(logger, AuditLogger)
        self.assertEqual(len(logger.handlers), 1)  # File handler
        
        logger.close()
        
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


class TestIntegration(unittest.TestCase):
    """Integration tests."""
    
    def test_full_workflow(self):
        """Test complete audit workflow."""
        temp_dir = tempfile.mkdtemp()
        
        # Create logger
        logger = create_audit_logger(
            log_dir=temp_dir,
            exclude_commands={"PING"}
        )
        
        # Log various operations
        operations = [
            ("admin", "SELECT * FROM users", "SELECT", True),
            ("admin", "INSERT INTO users VALUES (...)", "INSERT", True),
            ("user1", "SELECT * FROM orders", "SELECT", True),
            ("admin", "PING", "PING", True),  # Should be filtered
        ]
        
        for user, cmd, cmd_type, success in operations:
            logger.log(
                user=user,
                client_ip="192.168.1.1",
                command=cmd,
                command_type=cmd_type,
                success=success
            )
        
        logger.flush()
        
        # Query results
        results = logger.query(user="admin")
        
        # Should have 2 entries (PING filtered)
        self.assertEqual(len(results), 2)
        
        logger.close()
        
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
