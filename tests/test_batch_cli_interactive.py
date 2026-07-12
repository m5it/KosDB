
"""
Tests for Interactive Batch CLI

Tests:
- Batch mode entry and exit
- Command addition and editing
- Preview functionality
- Save/load functionality
- Tab completion
- Validation
"""

import unittest
import sys
import os
import tempfile
import json
from io import StringIO
from unittest.mock import patch, MagicMock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from batch_cli_interactive import (
    InteractiveBatchBuilder,
    BatchCLI,
    BatchCommand
)


class TestBatchCommand(unittest.TestCase):
    """Test BatchCommand dataclass."""
    
    def test_command_creation(self):
        """Test creating a batch command."""
        cmd = BatchCommand(
            command="SELECT * FROM users",
            line_number=1
        )
        
        self.assertEqual(cmd.command, "SELECT * FROM users")
        self.assertEqual(cmd.line_number, 1)
        self.assertFalse(cmd.validated)
        self.assertIsNone(cmd.error_message)
    
    def test_command_to_dict(self):
        """Test command serialization."""
        cmd = BatchCommand(
            command="INSERT INTO users VALUES (1)",
            line_number=2,
            validated=True
        )
        
        data = cmd.to_dict()
        self.assertEqual(data['command'], "INSERT INTO users VALUES (1)")
        self.assertEqual(data['line_number'], 2)
        self.assertTrue(data['validated'])


class TestInteractiveBatchBuilder(unittest.TestCase):
    """Test InteractiveBatchBuilder."""
    
    def setUp(self):
        """Set up test builder."""
        self.builder = InteractiveBatchBuilder()
    
    def test_start_batch_mode(self):
        """Test entering batch mode."""
        self.builder.start_batch_mode("test_batch")
        
        self.assertTrue(self.builder.in_batch_mode)
        self.assertEqual(self.builder.batch_name, "test_batch")
        self.assertEqual(self.builder.current_line, 0)
    
    def test_add_command(self):
        """Test adding commands."""
        self.builder.start_batch_mode()
        
        result = self.builder.add_command("SELECT * FROM users")
        self.assertTrue(result)
        self.assertEqual(len(self.builder.commands), 1)
        self.assertEqual(self.builder.commands[0].command, "SELECT * FROM users")
    
    def test_add_empty_command(self):
        """Test adding empty command is ignored."""
        self.builder.start_batch_mode()
        
        result = self.builder.add_command("   ")
        self.assertFalse(result)
        self.assertEqual(len(self.builder.commands), 0)
    
    def test_showbatch_empty(self):
        """Test showbatch with empty batch."""
        self.builder.start_batch_mode("empty_test")
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            self.builder._cmd_showbatch()
            output = fake_out.getvalue()
            self.assertIn("Batch is empty", output)
    
    def test_showbatch_with_commands(self):
        """Test showbatch with commands."""
        self.builder.start_batch_mode("test")
        self.builder.add_command("SELECT * FROM users")
        self.builder.add_command("INSERT INTO orders VALUES (1)")
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            self.builder._cmd_showbatch()
            output = fake_out.getvalue()
            self.assertIn("BATCH: test", output)
            self.assertIn("Commands: 2", output)
            self.assertIn("SELECT * FROM users", output)
    
    def test_clearbatch(self):
        """Test clearing batch."""
        self.builder.start_batch_mode()
        self.builder.add_command("SELECT 1")
        self.builder.add_command("SELECT 2")
        
        self.assertEqual(len(self.builder.commands), 2)
        
        with patch('builtins.input', return_value='y'):
            self.builder._cmd_clearbatch()
        
        self.assertEqual(len(self.builder.commands), 0)
        self.assertEqual(self.builder.current_line, 0)
    
    def test_remove_command(self):
        """Test removing specific command."""
        self.builder.start_batch_mode()
        self.builder.add_command("SELECT 1")
        self.builder.add_command("SELECT 2")
        self.builder.add_command("SELECT 3")
        
        self.assertEqual(len(self.builder.commands), 3)
        
        self.builder._cmd_remove("2")
        
        self.assertEqual(len(self.builder.commands), 2)
        self.assertEqual(self.builder.commands[0].command, "SELECT 1")
        self.assertEqual(self.builder.commands[1].command, "SELECT 3")
    
    def test_remove_invalid_number(self):
        """Test removing invalid command number."""
        self.builder.start_batch_mode()
        self.builder.add_command("SELECT 1")
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            self.builder._cmd_remove("99")
            output = fake_out.getvalue()
            self.assertIn("Invalid command number", output)
    
    def test_preview(self):
        """Test batch preview."""
        self.builder.start_batch_mode("preview_test")
        self.builder.add_command("SELECT * FROM users")
        self.builder.add_command("INSERT INTO orders VALUES (1, 'test')")
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            self.builder._cmd_preview()
            output = fake_out.getvalue()
            self.assertIn("BATCH PREVIEW", output)
            self.assertIn("Total Commands: 2", output)
            self.assertIn("SELECT", output)
            self.assertIn("INSERT", output)
    
    def test_estimate_size(self):
        """Test size estimation."""
        self.builder.start_batch_mode()
        self.builder.add_command("SELECT * FROM users")
        self.builder.add_command("SELECT * FROM orders")
        
        size = self.builder._estimate_size()
        self.assertGreater(size, 0)
        self.assertEqual(size, len("SELECT * FROM users") + len("SELECT * FROM orders"))
    
    def test_estimate_time(self):
        """Test time estimation."""
        self.builder.start_batch_mode()
        self.builder.add_command("SELECT * FROM users")
        self.builder.add_command("INSERT INTO orders VALUES (1)")
        
        time_ms = self.builder._estimate_time()
        self.assertGreater(time_ms, 0)
    
    def test_save_batch(self):
        """Test saving batch to file."""
        self.builder.start_batch_mode("save_test")
        self.builder.add_command("SELECT 1")
        self.builder.add_command("SELECT 2")
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            filename = f.name
        
        try:
            self.builder._cmd_save(filename)
            
            with open(filename, 'r') as f:
                data = json.load(f)
            
            self.assertEqual(data['name'], 'save_test')
            self.assertEqual(len(data['commands']), 2)
        finally:
            os.unlink(filename)
    
    def test_load_batch(self):
        """Test loading batch from file."""
        # Create test file
        test_data = {
            'name': 'loaded_batch',
            'created': '2024-01-15T10:00:00',
            'commands': [
                {'command': 'SELECT 1', 'line_number': 1, 'validated': True},
                {'command': 'SELECT 2', 'line_number': 2, 'validated': False}
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            json.dump(test_data, f)
            filename = f.name
        
        try:
            self.builder._cmd_load(filename)
            
            self.assertEqual(len(self.builder.commands), 2)
            self.assertEqual(self.builder.commands[0].command, 'SELECT 1')
            self.assertTrue(self.builder.commands[0].validated)
            self.assertEqual(self.builder.batch_name, 'loaded_batch')
        finally:
            os.unlink(filename)
    
    def test_load_nonexistent_file(self):
        """Test loading from non-existent file."""
        with patch('sys.stdout', new=StringIO()) as fake_out:
            self.builder._cmd_load('/nonexistent/file.json')
            output = fake_out.getvalue()
            self.assertIn("File not found", output)
    
    def test_cancel_batch(self):
        """Test cancelling batch."""
        self.builder.start_batch_mode()
        self.builder.add_command("SELECT 1")
        
        with patch('builtins.input', return_value='y'):
            self.builder._cmd_cancel()
        
        self.assertFalse(self.builder.in_batch_mode)
        self.assertEqual(len(self.builder.commands), 0)
    
    def test_get_batch(self):
        """Test getting batch commands."""
        self.builder.start_batch_mode()
        self.builder.add_command("SELECT 1")
        self.builder.add_command("SELECT 2")
        
        commands = self.builder.get_batch()
        self.assertEqual(commands, ["SELECT 1", "SELECT 2"])
    
    def test_is_valid(self):
        """Test batch validation check."""
        self.builder.start_batch_mode()
        
        # Empty batch is invalid
        self.assertFalse(self.builder.is_valid())
        
        # Add unvalidated command
        self.builder.add_command("SELECT 1")
        self.assertFalse(self.builder.is_valid())
        
        # Mark as validated
        self.builder.commands[0].validated = True
        self.assertTrue(self.builder.is_valid())


class TestBatchCLI(unittest.TestCase):
    """Test BatchCLI main class."""
    
    def setUp(self):
        """Set up CLI."""
        self.cli = BatchCLI()
    
    def test_validate_good_command(self):
        """Test validation of good command."""
        result = self.cli._validate("SELECT * FROM users")
        self.assertTrue(result)
    
    def test_validate_empty_command(self):
        """Test validation of empty command."""
        with self.assertRaises(ValueError):
            self.cli._validate("   ")
    
    def test_validate_unknown_command(self):
        """Test validation of unknown command."""
        with self.assertRaises(ValueError):
            self.cli._validate("FOOBAR something")
    
    def test_handle_command_batch(self):
        """Test \\batch command."""
        with patch.object(self.cli.batch_builder, 'start_batch_mode') as mock_start:
            self.cli._handle_command("\\batch mybatch")
            mock_start.assert_called_once_with("mybatch")
    
    def test_handle_command_status(self):
        """Test \\status command."""
        with patch('sys.stdout', new=StringIO()) as fake_out:
            self.cli._handle_command("\\status")
            output = fake_out.getvalue()
            self.assertIn("CLI Status", output)
    
    def test_handle_command_quit(self):
        """Test \\quit command."""
        self.assertTrue(self.cli.running)
        self.cli._handle_command("\\quit")
        self.assertFalse(self.cli.running)
    
    def test_execute_single(self):
        """Test executing single command."""
        mock_executor = MagicMock(return_value="result")
        cli = BatchCLI(executor=mock_executor)
        
        with patch('sys.stdout', new=StringIO()):
            cli._execute_single("SELECT 1")
        
        mock_executor.assert_called_once_with("SELECT 1")
    
    def test_execute_single_no_executor(self):
        """Test executing without executor."""
        with patch('sys.stdout', new=StringIO()) as fake_out:
            self.cli._execute_single("SELECT 1")
            output = fake_out.getvalue()
            self.assertIn("No executor configured", output)


class TestSpecialCommands(unittest.TestCase):
    """Test special command handling."""
    
    def setUp(self):
        self.builder = InteractiveBatchBuilder()
        self.builder.start_batch_mode()
    
    def test_endbatch_command(self):
        """Test \\endbatch triggers exit."""
        self.builder.add_command("SELECT 1")
        
        with patch('builtins.input', return_value='y'):
            result = self.builder._handle_special_command("\\endbatch")
            self.assertFalse(result)  # Signals exit
            self.assertFalse(self.builder.in_batch_mode)
    
    def test_help_command(self):
        """Test \\help displays help."""
        with patch('sys.stdout', new=StringIO()) as fake_out:
            self.builder._handle_special_command("\\help")
            output = fake_out.getvalue()
            self.assertIn("Interactive Batch Builder Commands", output)


class TestIntegration(unittest.TestCase):
    """Integration tests."""
    
    def test_full_batch_workflow(self):
        """Test complete batch workflow."""
        builder = InteractiveBatchBuilder()
        
        # Start batch
        builder.start_batch_mode("integration_test")
        self.assertTrue(builder.in_batch_mode)
        
        # Add commands
        builder.add_command("SELECT * FROM users")
        builder.add_command("INSERT INTO logs VALUES (1)")
        builder.add_command("UPDATE users SET last_login = NOW()")
        
        self.assertEqual(len(builder.commands), 3)
        
        # Show batch
        with patch('sys.stdout', new=StringIO()) as fake_out:
            builder._cmd_showbatch()
            output = fake_out.getvalue()
            self.assertIn("integration_test", output)
        
        # Preview
        with patch('sys.stdout', new=StringIO()) as fake_out:
            builder._cmd_preview()
            output = fake_out.getvalue()
            self.assertIn("Total Commands: 3", output)
        
        # Get commands
        commands = builder.get_batch()
        self.assertEqual(len(commands), 3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
