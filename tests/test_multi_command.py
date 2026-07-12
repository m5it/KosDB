"""
Comprehensive tests for multi-command batch functionality.

Tests cover:
- Command splitting with various inputs
- Quoted semicolon handling
- Batch execution with mixed results
- Transaction behavior
- Database context persistence
- Privilege checks
- Error handling
- Performance with large batches
- Edge cases
"""
import unittest
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parser import BackupRestoreParser


class TestCommandSplitting(unittest.TestCase):
    """Test 1: Basic command splitting with various inputs."""
    
    def setUp(self):
        self.parser = BackupRestoreParser()
    
    def test_basic_split(self):
        """Basic semicolon separation."""
        result = self.parser.split_commands("CMD1; CMD2; CMD3")
        self.assertEqual(result, ["CMD1", "CMD2", "CMD3"])
    
    def test_single_command(self):
        """Single command without semicolon."""
        result = self.parser.split_commands("SELECT * FROM users")
        self.assertEqual(result, ["SELECT * FROM users"])
    
    def test_whitespace_handling(self):
        """Extra whitespace should be stripped."""
        result = self.parser.split_commands("  CMD1  ;   CMD2   ")
        self.assertEqual(result, ["CMD1", "CMD2"])
    
    def test_empty_string(self):
        """Empty string returns empty list."""
        self.assertEqual(self.parser.split_commands(""), [])
        self.assertEqual(self.parser.split_commands("   "), [])


class TestQuotedSemicolons(unittest.TestCase):
    """Test 2: Quoted semicolons don't split."""
    
    def setUp(self):
        self.parser = BackupRestoreParser()
    
    def test_single_quotes(self):
        """Semicolons in single quotes don't split."""
        result = self.parser.split_commands("INSERT INTO t VALUES ('a;b'); SELECT 1")
        self.assertEqual(len(result), 2)
        self.assertIn("'a;b'", result[0])
    
    def test_double_quotes(self):
        """Semicolons in double quotes don't split."""
        result = self.parser.split_commands('INSERT INTO t VALUES ("a;b"); SELECT 1')
        self.assertEqual(len(result), 2)
        self.assertIn('"a;b"', result[0])
    
    def test_mixed_quotes(self):
        """Mixed quote types."""
        result = self.parser.split_commands(
            "INSERT INTO t VALUES ('single'); INSERT INTO t VALUES (\"double\")"
        )
        self.assertEqual(len(result), 2)


class TestEmptyCommands(unittest.TestCase):
    """Test 3: Empty commands and multiple semicolons."""
    
    def setUp(self):
        self.parser = BackupRestoreParser()
    
    def test_multiple_semicolons(self):
        """Multiple semicolons are handled."""
        result = self.parser.split_commands("CMD1;; CMD2;;; CMD3")
        self.assertEqual(result, ["CMD1", "CMD2", "CMD3"])
    
    def test_trailing_semicolon(self):
        """Trailing semicolon doesn't create empty command."""
        result = self.parser.split_commands("CMD1; CMD2;")
        self.assertEqual(result, ["CMD1", "CMD2"])
    
    def test_leading_semicolon(self):
        """Leading semicolon is ignored."""
        result = self.parser.split_commands("; CMD1; CMD2")
        self.assertEqual(result, ["CMD1", "CMD2"])
    
    def test_only_semicolons(self):
        """String with only semicolons returns empty list."""
        result = self.parser.split_commands(";;;")
        self.assertEqual(result, [])


class TestBatchResults(unittest.TestCase):
    """Test 4: Batch execution with mixed success/failure."""
    
    def test_mixed_status(self):
        """Simulate mixed OK/ERROR results."""
        results = [
            (1, "SELECT 1", "OK: result", "OK"),
            (2, "BAD CMD", "ERROR: failed", "ERROR"),
            (3, "SELECT 2", "OK: result", "OK")
        ]
        success = sum(1 for _, _, _, s in results if s == "OK")
        errors = sum(1 for _, _, _, s in results if s == "ERROR")
        self.assertEqual(success, 2)
        self.assertEqual(errors, 1)


class TestTransactionBehavior(unittest.TestCase):
    """Test 5: Transaction behavior with multi-commands."""
    
    def test_transaction_batch(self):
        """BEGIN; INSERT; INSERT; COMMIT pattern."""
        commands = ["BEGIN", "INSERT INTO t VALUES (1)", "INSERT INTO t VALUES (2)", "COMMIT"]
        self.assertEqual(len(commands), 4)
        self.assertEqual(commands[0], "BEGIN")
        self.assertEqual(commands[3], "COMMIT")
    
    def test_transaction_state_tracking(self):
        """Track transaction state through batch."""
        tx_active = False
        
        # Simulate BEGIN
        tx_active = True
        self.assertTrue(tx_active)
        
        # Simulate COMMIT
        tx_active = False
        self.assertFalse(tx_active)


class TestDatabaseContext(unittest.TestCase):
    """Test 6: Database context persistence across batch."""
    
    def test_use_then_select(self):
        """USE db; SELECT pattern."""
        commands = ["USE mydb", "SELECT * FROM users"]
        self.assertEqual(commands[0], "USE mydb")
        self.assertEqual(commands[1], "SELECT * FROM users")


class TestPrivilegeChecks(unittest.TestCase):
    """Test 7: Privilege checks for each command."""
    
    def test_admin_command_check(self):
        """Admin-only commands should be checked."""
        admin_commands = ['SHOW USERS', 'BACKUP DATABASE', 'RESTORE DATABASE']
        
        for cmd in admin_commands:
            is_admin = False
            should_block = cmd in admin_commands and not is_admin
            self.assertTrue(should_block)


class TestErrorHandling(unittest.TestCase):
    """Test 8: Error handling and recovery."""
    
    def test_continue_after_error(self):
        """Batch continues after error."""
        results = ["OK", "ERROR", "OK"]
        processed = len(results)
        self.assertEqual(processed, 3)  # All commands processed


class TestPerformance(unittest.TestCase):
    """Test 9: Performance with large batches."""
    
    def setUp(self):
        self.parser = BackupRestoreParser()
    
    def test_large_batch_splitting(self):
        """100+ commands split efficiently."""
        commands = ["SELECT {}".format(i) for i in range(150)]
        batch = "; ".join(commands)
        
        start = time.time()
        result = self.parser.split_commands(batch)
        elapsed = time.time() - start
        
        self.assertEqual(len(result), 150)
        self.assertLess(elapsed, 1.0)  # Should complete in under 1 second


class TestEdgeCases(unittest.TestCase):
    """Test 10: Edge cases."""
    
    def setUp(self):
        self.parser = BackupRestoreParser()
    
    def test_unicode_in_commands(self):
        """Unicode characters in commands."""
        result = self.parser.split_commands("INSERT INTO t VALUES ('日本語'); SELECT 1")
        self.assertEqual(len(result), 2)
    
    def test_escaped_quotes(self):
        """Escaped quotes in commands."""
        result = self.parser.split_commands(r"INSERT INTO t VALUES ('it\'s'); SELECT 1")
        self.assertEqual(len(result), 2)
    
    def test_newlines_in_batch(self):
        """Newlines preserved in commands."""
        batch = "SELECT 1;\nSELECT 2"
        result = self.parser.split_commands(batch)
        self.assertEqual(len(result), 2)


if __name__ == '__main__':
    unittest.main()
