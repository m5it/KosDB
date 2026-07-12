"""
Tests for BatchResponseFormatter.

Verifies:
- Formatting of batch results with various statuses
- Command numbering and summary generation
- Truncation of long commands and results
- Edge cases (empty batches, all errors, etc.)
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands import BatchResponseFormatter


class TestBatchResponseFormatter(unittest.TestCase):
    """Test batch response formatting."""
    
    def test_empty_batch(self):
        """Empty batch should return appropriate message."""
        result = BatchResponseFormatter.format_batch_results([])
        self.assertIn("0 command(s)", result)
        self.assertIn("Batch Complete", result)
    
    def test_single_success(self):
        """Single successful command."""
        results = [
            (1, "SELECT * FROM users", "OK: 5 rows", "OK")
        ]
        result = BatchResponseFormatter.format_batch_results(results)
        self.assertIn("[1/1]", result)
        self.assertIn("OK:", result)
        self.assertIn("SELECT * FROM users", result)
        self.assertIn("1 command(s), 1 succeeded", result)
    
    def test_single_error(self):
        """Single error command."""
        results = [
            (1, "BAD COMMAND", "ERROR: Unknown command", "ERROR")
        ]
        result = BatchResponseFormatter.format_batch_results(results)
        self.assertIn("[1/1]", result)
        self.assertIn("ERROR:", result)
        self.assertIn("1 failed", result)
    
    def test_mixed_results(self):
        """Mix of success and error commands."""
        results = [
            (1, "SELECT 1", "OK: Result 1", "OK"),
            (2, "BAD CMD", "ERROR: Failed", "ERROR"),
            (3, "SELECT 2", "OK: Result 2", "OK")
        ]
        result = BatchResponseFormatter.format_batch_results(results)
        self.assertIn("3 command(s), 2 succeeded, 1 failed", result)
        self.assertIn("[1/3]", result)
        self.assertIn("[2/3]", result)
        self.assertIn("[3/3]", result)
    
    def test_bye_terminates(self):
        """BYE command in batch."""
        results = [
            (1, "SELECT 1", "OK: Result", "OK"),
            (2, "QUIT", "BYE", "BYE")
        ]
        result = BatchResponseFormatter.format_batch_results(results)
        self.assertIn("BYE:", result)
        self.assertIn("1 terminated early", result)
    
    def test_long_command_truncation(self):
        """Very long commands should be truncated."""
        long_cmd = "SELECT * FROM " + "very_long_table_name" * 10
        results = [
            (1, long_cmd, "OK", "OK")
        ]
        result = BatchResponseFormatter.format_batch_results(results)
        self.assertIn("...", result)  # Should be truncated
        self.assertLess(len(result), len(long_cmd) + 100)
    
    def test_long_result_truncation(self):
        """Very long results should be truncated."""
        long_result = "OK: " + "x" * 1000
        results = [
            (1, "SELECT * FROM big_table", long_result, "OK")
        ]
        result = BatchResponseFormatter.format_batch_results(results)
        self.assertIn("...", result)
    
    def test_create_result_tuple_ok(self):
        """Test result tuple creation for success."""
        tup = BatchResponseFormatter.create_result_tuple(1, "SELECT 1", "OK: result")
        self.assertEqual(tup, (1, "SELECT 1", "OK: result", "OK"))
    
    def test_create_result_tuple_error(self):
        """Test result tuple creation for error."""
        tup = BatchResponseFormatter.create_result_tuple(2, "BAD", "ERROR: fail", is_error=True)
        self.assertEqual(tup[3], "ERROR")
    
    def test_create_result_tuple_bye(self):
        """Test result tuple creation for BYE."""
        tup = BatchResponseFormatter.create_result_tuple(3, "QUIT", "BYE", is_bye=True)
        self.assertEqual(tup[3], "BYE")
    
    def test_auto_detect_error_from_response(self):
        """Error status auto-detected from ERROR prefix."""
        tup = BatchResponseFormatter.create_result_tuple(1, "CMD", "ERROR: something")
        self.assertEqual(tup[3], "ERROR")
    
    def test_response_truncation(self):
        """Test max_response_length parameter."""
        results = [
            (i, f"CMD {i}", f"Result {i}", "OK") for i in range(1, 101)
        ]
        result = BatchResponseFormatter.format_batch_results(results, max_response_length=500)
        self.assertIn("truncated", result.lower())
    
    def test_all_success(self):
        """All commands succeed."""
        results = [
            (1, "CMD1", "OK1", "OK"),
            (2, "CMD2", "OK2", "OK"),
            (3, "CMD3", "OK3", "OK")
        ]
        result = BatchResponseFormatter.format_batch_results(results)
        self.assertIn("3 succeeded", result)
        self.assertNotIn("failed", result.lower())
    
    def test_all_errors(self):
        """All commands fail."""
        results = [
            (1, "CMD1", "ERROR1", "ERROR"),
            (2, "CMD2", "ERROR2", "ERROR")
        ]
        result = BatchResponseFormatter.format_batch_results(results)
        self.assertIn("2 failed", result)
        self.assertNotIn("succeeded", result.lower())


class TestBatchFormatterIntegration(unittest.TestCase):
    """Integration-style tests."""
    
    def test_realistic_sql_batch(self):
        """Realistic SQL batch scenario."""
        results = [
            BatchResponseFormatter.create_result_tuple(
                1, "CREATE TABLE users (id, name)", "OK: Table created"
            ),
            BatchResponseFormatter.create_result_tuple(
                2, "INSERT INTO users VALUES (1, 'Alice')", "OK: Inserted"
            ),
            BatchResponseFormatter.create_result_tuple(
                3, "INSERT INTO users VALUES (2, 'Bob')", "OK: Inserted"
            ),
            BatchResponseFormatter.create_result_tuple(
                4, "SELECT * FROM users", "OK:\n1 Alice\n2 Bob"
            )
        ]
        result = BatchResponseFormatter.format_batch_results(results)
        self.assertIn("4 command(s), 4 succeeded", result)
        self.assertIn("[1/4]", result)
        self.assertIn("[4/4]", result)
    
    def test_batch_with_permission_denied(self):
        """Batch with permission error."""
        results = [
            BatchResponseFormatter.create_result_tuple(
                1, "SHOW DATABASES", "OK: db1, db2", is_error=False
            ),
            BatchResponseFormatter.create_result_tuple(
                2, "SHOW USERS", "ERROR: Admin only", is_error=True
            )
        ]
        result = BatchResponseFormatter.format_batch_results(results)
        self.assertIn("ERROR:", result)
        self.assertIn("Admin only", result)


if __name__ == '__main__':
    unittest.main()
