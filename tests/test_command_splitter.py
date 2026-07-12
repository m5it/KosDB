
"""
Comprehensive tests for CommandSplitter edge cases.

Tests all supported escape sequences, quote styles, comments,
and special character handling.
"""

import unittest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from command_splitter import CommandSplitter, split_commands


class TestBasicSplitting(unittest.TestCase):
    """Test basic command splitting functionality."""
    
    def setUp(self):
        self.splitter = CommandSplitter()
    
    def test_simple_commands(self):
        """Test simple semicolon-separated commands."""
        result = self.splitter.split_commands("SELECT 1; SELECT 2; SELECT 3")
        self.assertEqual(result, ['SELECT 1', 'SELECT 2', 'SELECT 3'])
    
    def test_single_command(self):
        """Test single command without semicolon."""
        result = self.splitter.split_commands("SELECT 1")
        self.assertEqual(result, ['SELECT 1'])
    
    def test_trailing_semicolon(self):
        """Test command with trailing semicolon."""
        result = self.splitter.split_commands("SELECT 1;")
        self.assertEqual(result, ['SELECT 1'])
    
    def test_multiple_semicolons(self):
        """Test multiple consecutive semicolons."""
        result = self.splitter.split_commands("SELECT 1;; SELECT 2")
        self.assertEqual(result, ['SELECT 1', 'SELECT 2'])
    
    def test_empty_string(self):
        """Test empty string."""
        result = self.splitter.split_commands("")
        self.assertEqual(result, [])
    
    def test_only_semicolons(self):
        """Test string with only semicolons."""
        result = self.splitter.split_commands(";;;")
        self.assertEqual(result, [])


class TestQuoteHandling(unittest.TestCase):
    """Test quote handling in commands."""
    
    def setUp(self):
        self.splitter = CommandSplitter()
    
    def test_single_quotes(self):
        """Test semicolons inside single quotes."""
        result = self.splitter.split_commands("INSERT INTO t VALUES ('a;b')")
        self.assertEqual(result, ["INSERT INTO t VALUES ('a;b')"])
    
    def test_double_quotes(self):
        """Test semicolons inside double quotes."""
        result = self.splitter.split_commands('INSERT INTO t VALUES ("x;y")')
        self.assertEqual(result, ['INSERT INTO t VALUES ("x;y")'])
    
    def test_mixed_quotes(self):
        """Test mixed quote types."""
        result = self.splitter.split_commands(
            "INSERT INTO t VALUES ('a'); INSERT INTO t VALUES (\"b\")"
        )
        self.assertEqual(result, [
            "INSERT INTO t VALUES ('a')",
            'INSERT INTO t VALUES ("b")'
        ])
    
    def test_nested_quotes(self):
        """Test single quotes inside double quotes and vice versa."""
        result = self.splitter.split_commands(
            'SELECT "it\'s working"; SELECT \'he said "hi"\''
        )
        self.assertEqual(result, [
            'SELECT "it\'s working"',
            'SELECT \'he said "hi"\''
        ])


class TestEscapedQuotes(unittest.TestCase):
    """Test SQL-style escaped quotes."""
    
    def setUp(self):
        self.splitter = CommandSplitter()
    
    def test_escaped_single_quotes(self):
        """Test SQL escaped single quotes ('')."""
        result = self.splitter.split_commands("INSERT INTO t VALUES ('it''s a test')")
        self.assertEqual(result, ["INSERT INTO t VALUES ('it''s a test')"])
    
    def test_escaped_double_quotes(self):
        """Test SQL escaped double quotes ("")."""
        result = self.splitter.split_commands('INSERT INTO t VALUES (""quoted"")')
        self.assertEqual(result, ['INSERT INTO t VALUES (""quoted"")'])
    
    def test_escaped_quote_with_semicolon(self):
        """Test escaped quote followed by real semicolon."""
        result = self.splitter.split_commands(
            "INSERT INTO t VALUES ('a''b'); SELECT 1"
        )
        self.assertEqual(result, [
            "INSERT INTO t VALUES ('a''b')",
            "SELECT 1"
        ])


class TestEscapedSemicolons(unittest.TestCase):
    """Test escaped semicolons."""
    
    def setUp(self):
        self.splitter = CommandSplitter()
    
    def test_escaped_semicolon_in_string(self):
        """Test escaped semicolon in string."""
        result = self.splitter.split_commands(r"SELECT '\;'; SELECT 2")
        self.assertEqual(result, [r"SELECT '\;' ", "SELECT 2"])
    
    def test_escaped_semicolon_outside_string(self):
        """Test escaped semicolon outside string."""
        result = self.splitter.split_commands(r"SELECT 1\; SELECT 2")
        self.assertEqual(result, [r"SELECT 1\; SELECT 2"])
    
    def test_multiple_escaped_semicolons(self):
        """Test multiple escaped semicolons."""
        result = self.splitter.split_commands(r"SELECT '\;'; SELECT '\;'")
        self.assertEqual(result, [r"SELECT '\;' ", r"SELECT '\;'"])


class TestComments(unittest.TestCase):
    """Test SQL comment handling."""
    
    def setUp(self):
        self.splitter = CommandSplitter()
    
    def test_line_comment(self):
        """Test -- style line comment."""
        result = self.splitter.split_commands("SELECT 1; -- comment\nSELECT 2")
        self.assertEqual(result, ['SELECT 1', 'SELECT 2'])
    
    def test_line_comment_at_end(self):
        """Test line comment at end of command."""
        result = self.splitter.split_commands("SELECT 1 -- comment")
        self.assertEqual(result, ['SELECT 1'])
    
    def test_block_comment(self):
        """Test /* */ style block comment."""
        result = self.splitter.split_commands("SELECT 1; /* comment */ SELECT 2")
        self.assertEqual(result, ['SELECT 1', 'SELECT 2'])
    
    def test_block_comment_multiline(self):
        """Test multiline block comment."""
        result = self.splitter.split_commands(
            "SELECT 1; /* multi\nline\ncomment */ SELECT 2"
        )
        self.assertEqual(result, ['SELECT 1', 'SELECT 2'])
    
    def test_comment_in_string(self):
        """Test that comments inside strings are not treated as comments."""
        result = self.splitter.split_commands("SELECT '-- not a comment'")
        self.assertEqual(result, ["SELECT '-- not a comment'"])
    
    def test_semicolon_in_comment(self):
        """Test semicolons in comments don't split."""
        result = self.splitter.split_commands("SELECT 1; -- comment with ;\nSELECT 2")
        self.assertEqual(result, ['SELECT 1', 'SELECT 2'])


class TestMultilineCommands(unittest.TestCase):
    """Test multi-line command handling."""
    
    def setUp(self):
        self.splitter = CommandSplitter()
    
    def test_newline_in_command(self):
        """Test commands with newlines."""
        result = self.splitter.split_commands("SELECT\n  1;\nSELECT\n  2")
        self.assertEqual(result, ['SELECT 1', 'SELECT 2'])
    
    def test_windows_line_endings(self):
        """Test Windows line endings (\r\n)."""
        result = self.splitter.split_commands("SELECT 1;\r\nSELECT 2")
        self.assertEqual(result, ['SELECT 1', 'SELECT 2'])
    
    def test_old_mac_line_endings(self):
        """Test old Mac line endings (\r)."""
        result = self.splitter.split_commands("SELECT 1;\rSELECT 2")
        self.assertEqual(result, ['SELECT 1', 'SELECT 2'])
    
    def test_multiline_with_comments(self):
        """Test multiline commands with comments."""
        result = self.splitter.split_commands(
            "SELECT /* comment */ \n  1;\n-- line comment\nSELECT 2"
        )
        self.assertEqual(result, ['SELECT 1', 'SELECT 2'])


class TestUnicodeAndSpecialChars(unittest.TestCase):
    """Test Unicode and special character handling."""
    
    def setUp(self):
        self.splitter = CommandSplitter()
    
    def test_unicode_in_command(self):
        """Test Unicode characters in commands."""
        result = self.splitter.split_commands(
            "INSERT INTO t VALUES ('日本語'); SELECT 1"
        )
        self.assertEqual(result, ["INSERT INTO t VALUES ('日本語')", "SELECT 1"])
    
    def test_unicode_in_string_with_semicolon(self):
        """Test Unicode with semicolon-like character."""
        result = self.splitter.split_commands(
            "INSERT INTO t VALUES ('中文；测试')"
        )
        self.assertEqual(result, ["INSERT INTO t VALUES ('中文；测试')"])
    
    def test_emoji_in_string(self):
        """Test emoji in strings."""
        result = self.splitter.split_commands(
            "INSERT INTO t VALUES ('Hello 👋'); SELECT 1"
        )
        self.assertEqual(result, ["INSERT INTO t VALUES ('Hello 👋')", "SELECT 1"])
    
    def test_special_whitespace(self):
        """Test special whitespace characters."""
        result = self.splitter.split_commands("SELECT\u00A01;\u00A0SELECT\u00A02")
        self.assertEqual(result, ['SELECT 1', 'SELECT 2'])


class TestComplexScenarios(unittest.TestCase):
    """Test complex real-world scenarios."""
    
    def setUp(self):
        self.splitter = CommandSplitter()
    
    def test_transaction_batch(self):
        """Test typical transaction batch."""
        sql = """
        BEGIN;
        INSERT INTO accounts VALUES (1, 'Alice', 1000);
        INSERT INTO accounts VALUES (2, 'Bob', 500);
        UPDATE accounts SET balance = balance - 100 WHERE id = 1;
        UPDATE accounts SET balance = balance + 100 WHERE id = 2;
        COMMIT;
        """
        result = self.splitter.split_commands(sql)
        self.assertEqual(len(result), 6)
        self.assertEqual(result[0], "BEGIN")
        self.assertTrue(result[1].startswith("INSERT"))
        self.assertEqual(result[-1], "COMMIT")
    
    def test_realistic_batch_with_comments(self):
        """Test realistic batch with various comments."""
        sql = """
        -- Create users table
        CREATE TABLE users (id INT, name TEXT, email TEXT);
        
        /* Insert sample data
           with comments */
        INSERT INTO users VALUES (1, 'Alice', 'alice@example.com');
        INSERT INTO users VALUES (2, 'Bob', 'bob@example.com'); -- Bob's entry
        
        -- Query results
        SELECT * FROM users;
        """
        result = self.splitter.split_commands(sql)
        # Should have 4 commands (CREATE, 2 INSERTs, SELECT)
        self.assertEqual(len(result), 4)
    
    def test_quoted_semicolons_with_comments(self):
        """Test combination of quoted semicolons and comments."""
        sql = """
        INSERT INTO logs VALUES ('Error: timeout; retrying'); -- log entry
        INSERT INTO logs VALUES ('Success; done');
        SELECT * FROM logs;
        """
        result = self.splitter.split_commands(sql)
        self.assertEqual(len(result), 3)
        self.assertIn("timeout; retrying", result[0])
        self.assertIn("Success; done", result[1])


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions."""
    
    def setUp(self):
        self.splitter = CommandSplitter()
    
    def test_empty_quotes(self):
        """Test empty quotes."""
        result = self.splitter.split_commands("INSERT INTO t VALUES (''); SELECT 1")
        self.assertEqual(result, ["INSERT INTO t VALUES ('')", "SELECT 1"])
    
    def test_only_whitespace(self):
        """Test string with only whitespace."""
        result = self.splitter.split_commands("   \n  \t  ")
        self.assertEqual(result, [])
    
    def test_backslash_not_escape(self):
        """Test backslash before non-special character."""
        result = self.splitter.split_commands(r"SELECT 'C:\path'; SELECT 1")
        self.assertEqual(result, [r"SELECT 'C:\path'", "SELECT 1"])
    
    def test_consecutive_quotes(self):
        """Test consecutive quotes."""
        result = self.splitter.split_commands("SELECT '''', '\"\"\"'")
        self.assertEqual(result, ["SELECT '''', '\"\"\"'"])
    
    def test_very_long_command(self):
        """Test very long command."""
        long_value = "'x'" * 1000
        result = self.splitter.split_commands(f"INSERT INTO t VALUES ({long_value})")
        self.assertEqual(len(result), 1)
    
    def test_deeply_nested_quotes(self):
        """Test deeply nested quote patterns."""
        result = self.splitter.split_commands(
            '''SELECT "outer 'inner \"deepest\"' end"'''
        )
        self.assertEqual(len(result), 1)


class TestMetadata(unittest.TestCase):
    """Test metadata extraction."""
    
    def setUp(self):
        self.splitter = CommandSplitter()
    
    def test_metadata_extraction(self):
        """Test that metadata is correctly extracted."""
        text = "SELECT 1; -- comment\nSELECT 2"
        result = self.splitter.split_with_metadata(text)
        
        self.assertEqual(len(result), 2)
        
        # First command metadata
        cmd1, meta1 = result[0]
        self.assertTrue(meta1['had_comments'])
        self.assertFalse(meta1['had_escaped_semicolons'])
        self.assertTrue(meta1['had_multiline'])
        
        # Second command metadata
        cmd2, meta2 = result[1]
        self.assertEqual(cmd2, "SELECT 2")


class TestConvenienceFunction(unittest.TestCase):
    """Test the convenience split_commands function."""
    
    def test_convenience_function(self):
        """Test that convenience function works."""
        result = split_commands("SELECT 1; SELECT 2")
        self.assertEqual(result, ['SELECT 1', 'SELECT 2'])


class TestPerformance(unittest.TestCase):
    """Test performance with large inputs."""
    
    def test_large_batch(self):
        """Test splitting large batch."""
        commands = ["INSERT INTO t VALUES ({i})".format(i=i) for i in range(100)]
        sql = "; ".join(commands)
        
        splitter = CommandSplitter()
        start = __import__('time').time()
        result = splitter.split_commands(sql)
        elapsed = (__import__('time').time() - start) * 1000
        
        self.assertEqual(len(result), 100)
        print(f"\nLarge batch (100 commands) split in {elapsed:.2f}ms")
    
    def test_many_quoted_semicolons(self):
        """Test many quoted semicolons."""
        commands = []
        for i in range(50):
            commands.append(f"INSERT INTO t VALUES ('a;b;c {i}')")
        sql = "; ".join(commands)
        
        result = split_commands(sql)
        self.assertEqual(len(result), 50)


if __name__ == '__main__':
    unittest.main(verbosity=2)
