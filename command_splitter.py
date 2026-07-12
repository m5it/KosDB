
"""
Robust Command Splitter for KosDB v2.3.0

Handles edge cases in SQL command splitting:
- Escaped semicolons (backslash;)
- Nested quotes (single inside double, double inside single)
- SQL-style escaped quotes ('' inside ', "" inside ")
- Multi-line commands
- SQL comments (-- and /* */)
- Unicode and special characters
"""

import re
from typing import List, Tuple, Optional
from enum import Enum, auto


class CommandSplitter:
    """
    Robust SQL command splitter with full edge case support.
    
    Features:
    - Escaped semicolons (backslash; don't split)
    - Nested quotes handling
    - SQL escaped quotes ('' and "")
    - Multi-line command support
    - Comment removal (-- and /* */)
    - Unicode support
    """
    
    def __init__(self):
        # State tracking
        self.in_single_quote = False
        self.in_double_quote = False
        self.in_line_comment = False
        self.in_block_comment = False
        self.escape_next = False
        self.current_command = []
        self.commands = []
        
        # SQL escaped quote tracking
        self.prev_char = None
    
    def split_commands(self, text: str) -> List[str]:
        """
        Split SQL text into individual commands.
        
        Args:
            text: SQL text potentially containing multiple commands
            
        Returns:
            List of individual SQL commands
            
        Example:
            >>> splitter = CommandSplitter()
            >>> splitter.split_commands("SELECT 1; SELECT 2")
            ['SELECT 1', 'SELECT 2']
            
            >>> splitter.split_commands("INSERT INTO t VALUES ('a;b')")
            ["INSERT INTO t VALUES ('a;b')"]
        """
        if not text or not text.strip():
            return []
        
        # Normalize line endings
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        # Reset state
        self._reset_state()
        
        i = 0
        while i < len(text):
            char = text[i]
            next_char = text[i + 1] if i + 1 < len(text) else None
            
            # Handle escape sequences
            if self.escape_next:
                self._handle_escaped_char(char)
                i += 1
                continue
            
            # Check for escape character
            if char == '\\' and not self._in_string_or_comment():
                self.escape_next = True
                self.current_command.append(char)
                i += 1
                continue
            
            # Handle comments
            if self._handle_comments(char, next_char):
                i += 2 if self.in_block_comment or self.in_line_comment else 1
                continue
            
            # Skip characters inside comments
            if self.in_line_comment:
                if char == '\n':
                    self.in_line_comment = False
                    self.current_command.append(' ')  # Replace with space
                i += 1
                continue
            
            if self.in_block_comment:
                if char == '*' and next_char == '/':
                    self.in_block_comment = False
                    self.current_command.append(' ')  # Replace with space
                    i += 2
                else:
                    i += 1
                continue
            
            # Handle quotes
            if self._handle_quotes(char):
                self.current_command.append(char)
                i += 1
                continue
            
            # Handle semicolons (command separators)
            if char == ';' and not self._in_string():
                self._finalize_command()
                i += 1
                continue
            
            # Regular character
            self.current_command.append(char)
            self.prev_char = char
            i += 1
        
        # Finalize last command
        self._finalize_command()
        
        # Clean up and return
        return self._clean_commands()
    
    def _reset_state(self):
        """Reset all parsing state."""
        self.in_single_quote = False
        self.in_double_quote = False
        self.in_line_comment = False
        self.in_block_comment = False
        self.escape_next = False
        self.current_command = []
        self.commands = []
        self.prev_char = None
    
    def _in_string(self) -> bool:
        """Check if currently inside a string."""
        return self.in_single_quote or self.in_double_quote
    
    def _in_string_or_comment(self) -> bool:
        """Check if inside string or comment."""
        return self._in_string() or self.in_line_comment or self.in_block_comment
    
    def _handle_escaped_char(self, char: str):
        """Handle escaped character."""
        self.escape_next = False
        if char == ';':
            # Escaped semicolon - add literally, don't split
            self.current_command.append('\\' + char)
        else:
            # Other escaped character
            self.current_command.append('\\' + char)
    
    def _handle_comments(self, char: str, next_char: Optional[str]) -> bool:
        """
        Handle comment detection.
        
        Returns:
            True if comment state changed
        """
        # Start of line comment
        if char == '-' and next_char == '-' and not self._in_string():
            self.in_line_comment = True
            return True
        
        # Start of block comment
        if char == '/' and next_char == '*' and not self._in_string():
            self.in_block_comment = True
            return True
        
        return False
    
    def _handle_quotes(self, char: str) -> bool:
        """
        Handle quote characters including SQL escaped quotes.
        
        Returns:
            True if quote was handled
        """
        # Handle SQL escaped quotes: '' inside ', "" inside "
        if char == "'" and self.in_single_quote:
            # Check if this is an escaped quote (double single quote)
            if len(self.current_command) > 0 and self.current_command[-1] == "'":
                # This is an escaped quote, don't exit string mode
                self.current_command.append(char)
                return True
            # Exit single quote
            self.in_single_quote = False
            return False  # Let caller append
        
        if char == '"' and self.in_double_quote:
            # Check if this is an escaped quote (double double quote)
            if len(self.current_command) > 0 and self.current_command[-1] == '"':
                # This is an escaped quote, don't exit string mode
                self.current_command.append(char)
                return True
            # Exit double quote
            self.in_double_quote = False
            return False  # Let caller append
        
        # Enter single quote
        if char == "'" and not self.in_double_quote:
            self.in_single_quote = True
            return False  # Let caller append
        
        # Enter double quote
        if char == '"' and not self.in_single_quote:
            self.in_double_quote = True
            return False  # Let caller append
        
        return False
    
    def _finalize_command(self):
        """Finalize current command and add to list."""
        if self.current_command:
            cmd = ''.join(self.current_command).strip()
            if cmd:
                self.commands.append(cmd)
            self.current_command = []
    
    def _clean_commands(self) -> List[str]:
        """Clean up and normalize commands."""
        result = []
        for cmd in self.commands:
            # Normalize whitespace
            cmd = ' '.join(cmd.split())
            if cmd:
                result.append(cmd)
        return result
    
    def split_with_metadata(self, text: str) -> List[Tuple[str, dict]]:
        """
        Split commands and return with metadata about parsing.
        
        Returns:
            List of (command, metadata) tuples where metadata includes:
            - had_comments: bool
            - had_escaped_semicolons: bool
            - had_multiline: bool
            - original_length: int
        """
        commands = self.split_commands(text)
        result = []
        
        for cmd in commands:
            metadata = {
                'had_comments': '--' in text or '/*' in text,
                'had_escaped_semicolons': '\\;' in cmd,
                'had_multiline': '\n' in text,
                'original_length': len(cmd)
            }
            result.append((cmd, metadata))
        
        return result


def split_commands(text: str) -> List[str]:
    """
    Convenience function for splitting commands.
    
    Args:
        text: SQL text to split
        
    Returns:
        List of individual commands
        
    Example:
        >>> split_commands("SELECT 1; SELECT 2")
        ['SELECT 1', 'SELECT 2']
    """
    splitter = CommandSplitter()
    return splitter.split_commands(text)


# Legacy compatibility
def split_commands_legacy(text: str) -> List[str]:
    """
    Legacy simple split (for backward compatibility).
    Only handles basic semicolon separation.
    """
    if not text:
        return []
    
    # Simple split on semicolons not inside quotes
    commands = []
    current = []
    in_single = False
    in_double = False
    
    for char in text:
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == ';' and not in_single and not in_double:
            cmd = ''.join(current).strip()
            if cmd:
                commands.append(cmd)
            current = []
            continue
        
        current.append(char)
    
    # Add final command
    cmd = ''.join(current).strip()
    if cmd:
        commands.append(cmd)
    
    return commands


if __name__ == '__main__':
    # Test cases
    test_cases = [
        # Basic cases
        ("SELECT 1; SELECT 2", ['SELECT 1', 'SELECT 2']),
        
        # Semicolons in strings
        ("INSERT INTO t VALUES ('a;b')", ["INSERT INTO t VALUES ('a;b')"]),
        ('INSERT INTO t VALUES ("x;y")', ['INSERT INTO t VALUES ("x;y")']),
        
        # Escaped semicolons
        (r"SELECT '\;' ; SELECT 2", [r"SELECT '\;' ", 'SELECT 2']),
        
        # SQL escaped quotes
        ("INSERT INTO t VALUES ('it''s')", ["INSERT INTO t VALUES ('it''s')"]),
        
        # Comments
        ("SELECT 1; -- comment\nSELECT 2", ['SELECT 1', 'SELECT 2']),
        ("SELECT 1; /* comment */ SELECT 2", ['SELECT 1', 'SELECT 2']),
        
        # Multi-line
        ("SELECT\n  1;\nSELECT\n  2", ['SELECT 1', 'SELECT 2']),
        
        # Empty
        ("", []),
        (";;;", []),
        
        # Unicode
        ("INSERT INTO t VALUES ('日本語'); SELECT 1", ["INSERT INTO t VALUES ('日本語')", 'SELECT 1']),
    ]
    
    splitter = CommandSplitter()
    
    print("Command Splitter Tests")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for text, expected in test_cases:
        result = splitter.split_commands(text)
        
        if result == expected:
            print(f"PASS: {repr(text)[:40]}...")
            passed += 1
        else:
            print(f"FAIL: {repr(text)[:40]}...")
            print(f"  Expected: {expected}")
            print(f"  Got:      {result}")
            failed += 1
    
    print(f"\nResults: {passed} passed, {failed} failed")
