
"""
Test cases for batch execution error handling strategies.

Tests:
- CONTINUE mode: Execute all commands, report all results
- STOP_ON_ERROR mode: Halt on first error
- ROLLBACK_ALL mode: Rollback all changes if any command fails
"""

import unittest
import sys
import os
import sqlite3
import tempfile
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from batch_executor import BatchExecutor, ErrorMode, BatchResult, BatchHistoryStore


class MockParser:
    """Mock parser for testing."""
    
    def parse(self, command: str):
        cmd_upper = command.strip().upper()
        
        if cmd_upper.startswith('SELECT'):
            return 'SELECT', {'table': 'test_table'}
        elif cmd_upper.startswith('INSERT'):
            return 'INSERT', {'table': 'test_table', 'values': [1, 'test']}
        elif cmd_upper.startswith('UPDATE'):
            return 'UPDATE', {'table': 'test_table', 'set': {'col': 'val'}}
        elif cmd_upper.startswith('DELETE'):
            return 'DELETE', {'table': 'test_table'}
        elif cmd_upper.startswith('BEGIN'):
            return 'BEGIN', {}
        elif cmd_upper.startswith('COMMIT'):
            return 'COMMIT', {}
        elif cmd_upper.startswith('ROLLBACK'):
            return 'ROLLBACK', {}
        elif cmd_upper.startswith('ERROR'):
            return 'ERROR', {'message': 'Simulated error'}
        else:
            return 'UNKNOWN', None


class MockCommandRegistry:
    """Mock command registry for testing."""
    
    def __init__(self, fail_commands=None):
        self.fail_commands = fail_commands or set()
        self.executed_commands = []
        self.transaction_active = False
    
    def execute(self, cmd_type: str, params: dict, client_state: dict) -> str:
        self.executed_commands.append((cmd_type, params))
        
        # Simulate transaction commands
        if cmd_type == 'BEGIN':
            self.transaction_active = True
            return "OK: Transaction started"
        elif cmd_type == 'COMMIT':
            self.transaction_active = False
            return "OK: Transaction committed"
        elif cmd_type == 'ROLLBACK':
            self.transaction_active = False
            return "OK: Transaction rolled back"
        
        # Check if this command should fail
        if cmd_type in self.fail_commands:
            return f"ERROR: Simulated failure for {cmd_type}"
        
        return f"OK: {cmd_type} executed"


class TestBatchErrorModes(unittest.TestCase):
    """Test suite for batch error handling modes."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.parser = MockParser()
        self.client_state = {
            'current_db': 'test_db',
            'username': 'test_user',
            'session_id': 'test_session'
        }
    
    def test_continue_mode_all_success(self):
        """Test CONTINUE mode with all successful commands."""
        registry = MockCommandRegistry()
        executor = BatchExecutor(self.parser, registry)
        
        commands = [
            "SELECT * FROM test",
            "INSERT INTO test VALUES (1, 'a')",
            "UPDATE test SET col='val'"
        ]
        
        result = executor.execute_batch(
            commands, 
            self.client_state,
            error_mode=ErrorMode.CONTINUE,
            user_id="test_user"
        )
        
        # Check result format - mode is lowercase in output
        self.assertIn("mode: continue", result)
        self.assertIn("Commands: 3", result)
        self.assertIn("Succeeded: 3", result)
        self.assertIn("Failed: 0", result)
    
    def test_continue_mode_with_errors(self):
        """Test CONTINUE mode with some failing commands."""
        registry = MockCommandRegistry(fail_commands={'INSERT'})
        executor = BatchExecutor(self.parser, registry)
        
        commands = [
            "SELECT * FROM test",
            "INSERT INTO test VALUES (1, 'a')",  # This will fail
            "UPDATE test SET col='val'"
        ]
        
        result = executor.execute_batch(
            commands,
            self.client_state,
            error_mode=ErrorMode.CONTINUE,
            user_id="test_user"
        )
        
        # Check result format - mode is lowercase in output
        self.assertIn("mode: continue", result)
        self.assertIn("Succeeded: 2", result)
        self.assertIn("Failed: 1", result)
        
        # Check error details
        self.assertIn("Simulated failure", result)
    
    def test_stop_on_error_mode_first_success(self):
        """Test STOP_ON_ERROR mode - stop on first error."""
        registry = MockCommandRegistry(fail_commands={'INSERT'})
        executor = BatchExecutor(self.parser, registry)
        
        commands = [
            "SELECT * FROM test",  # Success
            "INSERT INTO test VALUES (1, 'a')",  # This fails - should stop
            "UPDATE test SET col='val'"  # Should not execute
        ]
        
        result = executor.execute_batch(
            commands,
            self.client_state,
            error_mode=ErrorMode.STOP_ON_ERROR,
            user_id="test_user"
        )
        
        # Only first two commands should execute (SELECT + failing INSERT)
        self.assertEqual(len(registry.executed_commands), 2)
        
        # Check result format - mode is lowercase in output
        self.assertIn("mode: stop_on_error", result)
        self.assertIn("STOPPED at command 2", result)
        
        # Third command should not have executed
        executed_types = [cmd[0] for cmd in registry.executed_commands]
        self.assertNotIn('UPDATE', executed_types)
    
    def test_stop_on_error_mode_all_success(self):
        """Test STOP_ON_ERROR mode with all successful commands."""
        registry = MockCommandRegistry()
        executor = BatchExecutor(self.parser, registry)
        
        commands = [
            "SELECT * FROM test",
            "INSERT INTO test VALUES (1, 'a')",
            "UPDATE test SET col='val'"
        ]
        
        result = executor.execute_batch(
            commands,
            self.client_state,
            error_mode=ErrorMode.STOP_ON_ERROR,
            user_id="test_user"
        )
        
        # All commands should execute
        self.assertEqual(len(registry.executed_commands), 3)
        
        # Check result format - mode is lowercase in output
        self.assertIn("mode: stop_on_error", result)
        self.assertIn("Succeeded: 3", result)
        self.assertIn("Failed: 0", result)
    
    def test_rollback_all_mode_all_success(self):
        """Test ROLLBACK_ALL mode with all successful commands."""
        registry = MockCommandRegistry()
        executor = BatchExecutor(self.parser, registry)
        
        commands = [
            "SELECT * FROM test",
            "INSERT INTO test VALUES (1, 'a')",
            "UPDATE test SET col='val'"
        ]
        
        result = executor.execute_batch(
            commands,
            self.client_state,
            error_mode=ErrorMode.ROLLBACK_ALL,
            user_id="test_user"
        )
        
        # Commands should execute (wrapped in transaction)
        self.assertGreater(len(registry.executed_commands), 0)
        
        # Should not be rolled back
        self.assertNotIn("ROLLED BACK", result)
    
    def test_rollback_all_mode_with_error(self):
        """Test ROLLBACK_ALL mode - rollback on any error."""
        registry = MockCommandRegistry(fail_commands={'INSERT'})
        executor = BatchExecutor(self.parser, registry)
        
        commands = [
            "SELECT * FROM test",
            "INSERT INTO test VALUES (1, 'a')",  # This fails
            "UPDATE test SET col='val'"
        ]
        
        result = executor.execute_batch(
            commands,
            self.client_state,
            error_mode=ErrorMode.ROLLBACK_ALL,
            user_id="test_user"
        )
        
        # Check rollback happened
        self.assertIn("ROLLED BACK", result)
        
        # Should have executed ROLLBACK command
        executed_types = [cmd[0] for cmd in registry.executed_commands]
        self.assertIn('ROLLBACK', executed_types)
    
    def test_rollback_all_with_explicit_transaction(self):
        """Test ROLLBACK_ALL mode with explicit transaction markers."""
        registry = MockCommandRegistry(fail_commands={'INSERT'})
        executor = BatchExecutor(self.parser, registry)
        
        # User provides explicit transaction
        commands = [
            "BEGIN",
            "SELECT * FROM test",
            "INSERT INTO test VALUES (1, 'a')",  # This fails
            "UPDATE test SET col='val'",
            "COMMIT"
        ]
        
        result = executor.execute_batch(
            commands,
            self.client_state,
            error_mode=ErrorMode.ROLLBACK_ALL,
            user_id="test_user"
        )
        
        # Check rollback happened
        self.assertIn("ROLLED BACK", result)
        
        # Should have executed ROLLBACK (not COMMIT)
        executed_types = [cmd[0] for cmd in registry.executed_commands]
        self.assertIn('ROLLBACK', executed_types)
        self.assertNotIn('COMMIT', executed_types)
    
    def test_error_context_details(self):
        """Test that error context includes detailed information."""
        registry = MockCommandRegistry(fail_commands={'INSERT'})
        executor = BatchExecutor(self.parser, registry)
        
        commands = [
            "SELECT * FROM test",
            "INSERT INTO test VALUES (1, 'a')",  # Fails at index 2
            "UPDATE test SET col='val'"
        ]
        
        result = executor.execute_batch(
            commands,
            self.client_state,
            error_mode=ErrorMode.CONTINUE,
            user_id="test_user"
        )
        
        # Check error details in result
        self.assertIn("[2/3]", result)  # Command index
        self.assertIn("Simulated failure", result)  # Error message
        self.assertIn("INSERT", result)  # Failed command
    
    def test_batch_status_command(self):
        """Test BATCH STATUS command functionality."""
        # Use temp file for history database to persist across calls
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            registry = MockCommandRegistry()
            config = {'batch_history_db': db_path}
            executor = BatchExecutor(self.parser, registry, config)
            
            # Execute a batch
            commands = [
                "SELECT * FROM test",
                "INSERT INTO test VALUES (1, 'a')"
            ]
            
            executor.execute_batch(
                commands,
                self.client_state,
                error_mode=ErrorMode.CONTINUE,
                user_id="test_user"
            )
            
            # Get last batch status
            status = executor.get_last_batch_status("test_user")
            
            self.assertIsNotNone(status)
            self.assertEqual(status['command_count'], 2)
            self.assertEqual(status['success_count'], 2)
            self.assertEqual(status['error_count'], 0)
            self.assertEqual(status['error_mode'], 'continue')
        finally:
            os.unlink(db_path)
    
    def test_batch_history_recording(self):
        """Test that batch execution is recorded in history."""
        # Use temp file for history database
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            registry = MockCommandRegistry()
            config = {'batch_history_db': db_path}
            executor = BatchExecutor(self.parser, registry, config)
            
            commands = [
                "SELECT * FROM test",
                "INSERT INTO test VALUES (1, 'a')"
            ]
            
            executor.execute_batch(
                commands,
                self.client_state,
                error_mode=ErrorMode.CONTINUE,
                user_id="test_user"
            )
            
            # Get recent batches
            batches = executor.get_recent_batches("test_user", limit=1)
            
            self.assertEqual(len(batches), 1)
            self.assertEqual(batches[0]['command_count'], 2)
            self.assertEqual(batches[0]['user_id'], 'test_user')
            
        finally:
            os.unlink(db_path)
    
    def test_default_error_mode_from_config(self):
        """Test that default error mode is read from config."""
        registry = MockCommandRegistry()
        config = {'batch_error_mode': 'stop_on_error'}
        executor = BatchExecutor(self.parser, registry, config)
        
        # Default should be STOP_ON_ERROR
        self.assertEqual(executor.default_error_mode, ErrorMode.STOP_ON_ERROR)
    
    def test_invalid_error_mode_falls_back(self):
        """Test that invalid error mode falls back to CONTINUE."""
        registry = MockCommandRegistry()
        config = {'batch_error_mode': 'invalid_mode'}
        executor = BatchExecutor(self.parser, registry, config)
        
        # Should fall back to CONTINUE
        self.assertEqual(executor.default_error_mode, ErrorMode.CONTINUE)
    
    def test_batch_with_privilege_checking(self):
        """Test batch execution with privilege checking."""
        registry = MockCommandRegistry()
        executor = BatchExecutor(self.parser, registry)
        
        # Privilege checker that denies INSERT
        def deny_insert(cmd_type, params):
            return cmd_type != 'INSERT'
        
        commands = [
            "SELECT * FROM test",
            "INSERT INTO test VALUES (1, 'a')",  # Should be denied
            "UPDATE test SET col='val'"
        ]
        
        result = executor.execute_batch(
            commands,
            self.client_state,
            privilege_checker=deny_insert,
            error_mode=ErrorMode.CONTINUE,
            user_id="test_user"
        )
        
        # INSERT should fail with permission denied
        self.assertIn("Permission denied", result)
        
        # Should have 1 failure - check for the number pattern
        self.assertIn("Failed: 1", result)
    
    def test_empty_batch(self):
        """Test handling of empty batch."""
        registry = MockCommandRegistry()
        executor = BatchExecutor(self.parser, registry)
        
        commands = []
        
        result = executor.execute_batch(
            commands,
            self.client_state,
            error_mode=ErrorMode.CONTINUE,
            user_id="test_user"
        )
        
        # Should handle gracefully
        self.assertIn("0 commands", result)
    
    def test_batch_metrics_tracking(self):
        """Test that batch metrics are tracked."""
        registry = MockCommandRegistry()
        executor = BatchExecutor(self.parser, registry)
        
        commands = [
            "SELECT * FROM test",
            "INSERT INTO test VALUES (1, 'a')"
        ]
        
        executor.execute_batch(
            commands,
            self.client_state,
            error_mode=ErrorMode.CONTINUE,
            user_id="test_user"
        )
        
        # Check metrics
        metrics = executor.get_metrics()
        self.assertEqual(metrics['total_batches'], 1)
        self.assertEqual(metrics['total_commands'], 2)
        self.assertGreater(metrics['avg_batch_time_ms'], 0)


class TestBatchHistoryStore(unittest.TestCase):
    """Test suite for batch history storage."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp_db.close()
        self.store = BatchHistoryStore(self.temp_db.name)
    
    def tearDown(self):
        """Clean up test fixtures."""
        import os
        os.unlink(self.temp_db.name)
    
    def test_record_and_retrieve(self):
        """Test recording and retrieving batch execution."""
        from batch_executor import BatchExecutionRecord
        
        record = BatchExecutionRecord(
            batch_id="test-123",
            timestamp=time.time(),
            user_id="test_user",
            command_count=3,
            error_mode="continue",
            results=[
                {'index': 1, 'command': 'SELECT', 'status': 'OK'},
                {'index': 2, 'command': 'INSERT', 'status': 'OK'},
                {'index': 3, 'command': 'UPDATE', 'status': 'ERROR'}
            ],
            summary="3 commands: 2 succeeded, 1 failed",
            total_time_ms=100.0,
            success_count=2,
            error_count=1,
            was_rolled_back=False,
            metadata={'client_ip': '127.0.0.1'}
        )
        
        self.store.record(record)
        
        # Retrieve
        retrieved = self.store.get_batch_status("test-123")
        
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved['batch_id'], 'test-123')
        self.assertEqual(retrieved['user_id'], 'test_user')
        self.assertEqual(retrieved['success_count'], 2)
        self.assertEqual(retrieved['error_count'], 1)
    
    def test_get_last_batch(self):
        """Test retrieving last batch for user."""
        from batch_executor import BatchExecutionRecord
        
        # Record two batches
        for i in range(2):
            record = BatchExecutionRecord(
                batch_id=f"batch-{i}",
                timestamp=time.time() + i,
                user_id="test_user",
                command_count=1,
                error_mode="continue",
                results=[],
                summary="1 command: 1 succeeded",
                total_time_ms=50.0,
                success_count=1,
                error_count=0,
                was_rolled_back=False,
                metadata={}
            )
            self.store.record(record)
        
        # Get last batch
        last = self.store.get_last_batch("test_user")
        
        self.assertIsNotNone(last)
        self.assertEqual(last['batch_id'], 'batch-1')  # Most recent
    
    def test_get_recent_batches(self):
        """Test retrieving recent batches."""
        from batch_executor import BatchExecutionRecord
        
        # Record multiple batches
        for i in range(5):
            record = BatchExecutionRecord(
                batch_id=f"batch-{i}",
                timestamp=time.time() + i,
                user_id="test_user",
                command_count=1,
                error_mode="continue",
                results=[],
                summary="1 command: 1 succeeded",
                total_time_ms=50.0,
                success_count=1,
                error_count=0,
                was_rolled_back=False,
                metadata={}
            )
            self.store.record(record)
        
        # Get recent (limit 3)
        recent = self.store.get_recent_batches("test_user", limit=3)
        
        self.assertEqual(len(recent), 3)
        # Should be in reverse chronological order
        self.assertEqual(recent[0]['batch_id'], 'batch-4')
        self.assertEqual(recent[2]['batch_id'], 'batch-2')


if __name__ == '__main__':
    unittest.main(verbosity=2)
