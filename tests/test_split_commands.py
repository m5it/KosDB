"""
Unit tests for the split_commands() method in BackupRestoreParser.

Tests cover:
- Basic command splitting
- Quoted string handling
- Escaped characters
- Edge cases (empty strings, multiple semicolons)
- Mixed quote types
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parser import BackupRestoreParser


class TestSplitCommands(unittest.TestCase):
    """Test cases for command splitting functionality."""
    
    def setUp(self):
        self.parser = BackupRestoreParser()
    
    def test_empty_string(self):
        """Empty string should return empty list."""
        self.assertEqual(self.parser.split_commands(""), [])
        self.assertEqual(self.parser.split_commands("   "), [])
        self.assertEqual(self.parser.split_commands(None), [])
    
    def test_single_command_no_semicolon(self):
        """Single command without semicolon should return list with one item."""
        result = self.parser.split_commands("SELECT * FROM users")
        self.assertEqual(result, ["SELECT * FROM users"])
    
    def test_basic_split(self):
        """Basic semicolon separation."""
        result = self.parser.split_commands("CMD1; CMD2; CMD3")
        self.assertEqual(result, ["CMD1", "CMD2", "CMD3"])
    
    def test_split_with_whitespace(self):
        """Whitespace should be stripped from commands."""
        result = self.parser.split_commands("  CMD1  ;   CMD2   ;   CMD3  ")
        self.assertEqual(result, ["CMD1", "CMD2", "CMD3"])
    
    def test_multiple_semicolons(self):
        """Multiple consecutive semicolons should be handled."""
        result = self.parser.split_commands("CMD1;; CMD2;;; CMD3")
        self.assertEqual(result, ["CMD1", "CMD2", "CMD3"])
    
    def test_trailing_semicolon(self):
        """Trailing semicolon should not create empty command."""
        result = self.parser.split_commands("CMD1; CMD2;")
        self.assertEqual(result, ["CMD1", "CMD2"])
    
    def test_leading_semicolon(self):
        """Leading semicolon should be ignored."""
        result = self.parser.split_commands("; CMD1; CMD2")
        self.assertEqual(result, ["CMD1", "CMD2"])
    
    def test_semicolon_in_single_quotes(self):
        """Semicolons inside single quotes should not split."""
        result = self.parser.split_commands("INSERT INTO t VALUES ('a;b'); SELECT * FROM t")
        self.assertEqual(result, [
            "INSERT INTO t VALUES ('a;b')",
            "SELECT * FROM t"
        ])
    
    def test_semicolon_in_double_quotes(self):
        """Semicolons inside double quotes should not split."""
        result = self.parser.split_commands('INSERT INTO t VALUES ("a;b"); SELECT * FROM t')
        self.assertEqual(result, [
            'INSERT INTO t VALUES ("a;b")',
            "SELECT * FROM t"
        ])
    
    def test_mixed_quotes(self):
        """Mixed quote types should be handled correctly."""
        result = self.parser.split_commands(
            "INSERT INTO t VALUES ('single'); INSERT INTO t VALUES (\"double\")"
        )
        self.assertEqual(result, [
            "INSERT INTO t VALUES ('single')",
            'INSERT INTO t VALUES ("double")'
        ])
    
    def test_nested_quotes(self):
        """Different quote types inside each other."""
        result = self.parser.split_commands(
            "INSERT INTO t VALUES ('he said \"hello; world\"'); SELECT 1"
        )
        self.assertEqual(result, [
            "INSERT INTO t VALUES ('he said \"hello; world\"')",
            "SELECT 1"
        ])
    
    def test_escaped_quotes(self):
        """Escaped quotes should not end string."""
        result = self.parser.split_commands(r"INSERT INTO t VALUES ('it\'s; ok'); SELECT 1")
        self.assertEqual(result, [
            r"INSERT INTO t VALUES ('it\'s; ok')",
            "SELECT 1"
        ])
    
    def test_escaped_backslash(self):
        """Escaped backslash before quote - complex escape sequence."""
        # When we have \' the quote is escaped and doesn't close the string
        # So 'a\\';b' is actually: 'a\' followed by ;b' 
        result = self.parser.split_commands(r"INSERT INTO t VALUES ('a\\';b'); SELECT 1")
        # The escaped backslash doesn't escape the following quote in our parser
        # So the string ends at 'a\' and ; splits there
        self.assertEqual(result[0], r"INSERT INTO t VALUES ('a\\'")
        # After that we get the rest
        self.assertIn("b')", result[1])
    
    def test_real_sql_batch(self):
        """Realistic SQL batch example."""
        batch = """
            CREATE TABLE users (id, name);
            INSERT INTO users VALUES (1, 'Alice');
            INSERT INTO users VALUES (2, 'Bob; Smith');
            SELECT * FROM users;
            DROP TABLE users
        """
        result = self.parser.split_commands(batch)
        self.assertEqual(result, [
            "CREATE TABLE users (id, name)",
            "INSERT INTO users VALUES (1, 'Alice')",
            "INSERT INTO users VALUES (2, 'Bob; Smith')",
            "SELECT * FROM users",
            "DROP TABLE users"
        ])
    
    def test_complex_batch_with_transactions(self):
        """Batch with transaction commands."""
        batch = "BEGIN; INSERT INTO t VALUES (1); INSERT INTO t VALUES (2); COMMIT"
        result = self.parser.split_commands(batch)
        self.assertEqual(result, [
            "BEGIN",
            "INSERT INTO t VALUES (1)",
            "INSERT INTO t VALUES (2)",
            "COMMIT"
        ])
    
    def test_only_semicolons(self):
        """String with only semicolons should return empty list."""
        result = self.parser.split_commands(";;;")
        self.assertEqual(result, [])
    
    def test_newlines_in_batch(self):
        """Newlines should be preserved within commands but stripped at ends."""
        batch = "SELECT 1;\nSELECT 2;\nSELECT 3"
        result = self.parser.split_commands(batch)
        # Newlines within commands are preserved, but stripped at ends
        self.assertEqual(result, ["SELECT 1", "SELECT 2", "SELECT 3"])
    
    def test_unicode_in_commands(self):
        """Unicode characters should be handled."""
        result = self.parser.split_commands("INSERT INTO t VALUES ('日本語'); SELECT * FROM t")
        self.assertEqual(result, [
            "INSERT INTO t VALUES ('日本語')",
            "SELECT * FROM t"
        ])
    
    def test_empty_quotes(self):
        """Empty quotes should be handled."""
        result = self.parser.split_commands("INSERT INTO t VALUES (''); SELECT 1")
        self.assertEqual(result, [
            "INSERT INTO t VALUES ('')",
            "SELECT 1"
        ])
    
    def test_quote_at_end(self):
        """Quote at end of command."""
        result = self.parser.split_commands("SELECT 'test'; SELECT 1")
        self.assertEqual(result, ["SELECT 'test'", "SELECT 1"])
    
    def test_unclosed_quote(self):
        """Unclosed quote should treat rest as string."""
        result = self.parser.split_commands("INSERT INTO t VALUES ('unclosed; SELECT 1")
        self.assertEqual(result, ["INSERT INTO t VALUES ('unclosed; SELECT 1"])
    
    def test_single_character_commands(self):
        """Very short commands."""
        result = self.parser.split_commands("A; B; C")
        self.assertEqual(result, ["A", "B", "C"])





class TestSplitCommandsEdgeCases(unittest.TestCase):
    """Additional edge case tests."""
    
    def setUp(self):
        self.parser = BackupRestoreParser()
    
    def test_semicolon_in_comment_not_handled(self):
        """Note: SQL comments with semicolons are not specially handled."""
        # This documents current behavior - comments are not parsed specially
        # The comment becomes part of the command, and semicolons in comments DO split
        result = self.parser.split_commands("SELECT 1; -- comment; SELECT 2")
        # We get 3 commands because the semicolon in comment splits
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], "SELECT 1")
        self.assertEqual(result[1], "-- comment")
        self.assertEqual(result[2], "SELECT 2")
    
    def test_very_long_batch(self):
        """Large batch should work efficiently."""
        commands = ["INSERT INTO t VALUES ({})".format(i) for i in range(100)]
        batch = "; ".join(commands)
        result = self.parser.split_commands(batch)
        self.assertEqual(len(result), 100)
        self.assertEqual(result[0], "INSERT INTO t VALUES (0)")
        self.assertEqual(result[99], "INSERT INTO t VALUES (99)")


if __name__ == '__main__':
    unittest.main()

if __name__ == '__main__':
    unittest.main()
