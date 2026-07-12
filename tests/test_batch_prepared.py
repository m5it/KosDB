
"""
Test cases for batch prepared statement execution.

Tests:
- PREPARE/EXECUTE/DEALLOCATE within batches
- Bulk insert with prepared statements
- Parameter binding for batch execution
- Performance with 1000+ rows
"""

import unittest
import sys
import os
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from batch_prepared_executor import (
    BatchPreparedExecutor,
    BulkInsertOptimizer,
    bulk_insert,
    BulkInsertResult
)
from batch_executor import BatchExecutor, ErrorMode
from prepared_statements import PreparedStatementManager


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
        elif cmd_upper.startswith('BEGIN'):
            return 'BEGIN', {}
        elif cmd_upper.startswith('COMMIT'):
            return 'COMMIT', {}
        elif cmd_upper.startswith('ROLLBACK'):
            return 'ROLLBACK', {}
        else:
            return 'UNKNOWN', None


class MockCommandRegistry:
    """Mock command registry for testing."""
    
    def __init__(self):
        self.executed_commands = []
    
    def execute(self, cmd_type: str, params: dict, client_state: dict) -> str:
        self.executed_commands.append((cmd_type, params))
        return f"OK: {cmd_type} executed"


class TestBatchPreparedExecutor(unittest.TestCase):
    """Test suite for batch prepared execution."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.parser = MockParser()
        self.registry = MockCommandRegistry()
        self.batch_executor = BatchExecutor(self.parser, self.registry)
        self.prepared_manager = PreparedStatementManager()
        self.prepared_executor = BatchPreparedExecutor(
            self.batch_executor,
            self.prepared_manager
        )
        self.client_state = {
            'current_db': 'test_db',
            'username': 'test_user',
            'session_id': 'test_session'
        }
    
    def test_prepare_in_batch(self):
        """Test PREPARE statement within batch."""
        commands = [
            "PREPARE get_user AS SELECT * FROM users WHERE id = ?",
            "EXECUTE get_user USING 123",
            "DEALLOCATE get_user"
        ]
        
        result = self.prepared_executor.execute_batch_with_prepared(
            commands,
            self.client_state,
            user_id="test_user"
        )
        
        # Should execute without errors
        self.assertIn("Batch Execution", result)
        
        # Check that prepared statement was created
        statements = self.prepared_manager.list_statements()
        self.assertEqual(len(statements), 0)  # Deallocated at end
    
    def test_execute_using_syntax(self):
        """Test EXECUTE ... USING syntax."""
        # First prepare
        self.prepared_manager.prepare("SELECT * FROM users WHERE id = ?")
        
        commands = [
            "EXECUTE stmt USING 123"
        ]
        
        result = self.prepared_executor.execute_batch_with_prepared(
            commands,
            self.client_state,
            user_id="test_user"
        )
        
        self.assertIn("Batch Execution", result)
    
    def test_execute_batch_syntax(self):
        """Test batch parameter binding syntax."""
        # Prepare statement
        stmt_id = self.prepared_manager.prepare(
            "INSERT INTO users (id, name) VALUES (?, ?)"
        )
        
        # Manually register in cache
        self.prepared_executor._prepared_cache['insert_user'] = stmt_id
        
        commands = [
            "EXECUTE insert_user (1, 'Alice')",
            "EXECUTE insert_user (2, 'Bob')",
            "EXECUTE insert_user (3, 'Charlie')"
        ]
        
        result = self.prepared_executor.execute_batch_with_prepared(
            commands,
            self.client_state,
            user_id="test_user"
        )
        
        self.assertIn("Batch Execution", result)
    
    def test_deallocate_all(self):
        """Test DEALLOCATE ALL."""
        # Prepare multiple statements
        self.prepared_manager.prepare("SELECT 1")
        self.prepared_manager.prepare("SELECT 2")
        
        commands = [
            "DEALLOCATE ALL"
        ]
        
        result = self.prepared_executor.execute_batch_with_prepared(
            commands,
            self.client_state,
            user_id="test_user"
        )
        
        # All statements should be deallocated
        statements = self.prepared_manager.list_statements()
        self.assertEqual(len(statements), 0)
    
    def test_batch_execute_prepared(self):
        """Test batch_execute_prepared method."""
        # Prepare statement and get the ID
        stmt_id = self.prepared_manager.prepare("INSERT INTO users (id, name) VALUES (?, ?)")
        
        # Execute with multiple parameter sets using the actual statement ID
        parameter_sets = [
            [1, 'Alice'],
            [2, 'Bob'],
            [3, 'Charlie']
        ]
        
        result = self.prepared_executor.batch_execute_prepared(
            stmt_id,  # Use the actual statement ID
            parameter_sets,
            self.client_state,
            batch_size=2
        )
        
        self.assertEqual(result.rows_inserted, 3)
        self.assertEqual(result.rows_failed, 0)
    
    def test_bulk_insert_100_rows(self):
        """Test bulk insert with 100 rows."""
        # Prepare statement and get ID
        stmt_id = self.prepared_manager.prepare("INSERT INTO users (id, name) VALUES (?, ?)")
        
        # Generate 100 rows
        rows = [[i, f'User{i}'] for i in range(100)]
        
        start_time = time.time()
        result = self.prepared_executor.batch_execute_prepared(
            stmt_id,  # Use actual statement ID
            rows,
            self.client_state,
            batch_size=25
        )
        elapsed = (time.time() - start_time) * 1000
        
        self.assertEqual(result.rows_inserted, 100)
        self.assertEqual(result.rows_failed, 0)
        print(f"\n100 rows inserted in {elapsed:.2f}ms")
    
    def test_bulk_insert_1000_rows(self):
        """Test bulk insert with 1000 rows."""
        # Prepare statement and get ID
        stmt_id = self.prepared_manager.prepare("INSERT INTO users (id, name) VALUES (?, ?)")
        
        # Generate 1000 rows
        rows = [[i, f'User{i}'] for i in range(1000)]
        
        start_time = time.time()
        result = self.prepared_executor.batch_execute_prepared(
            stmt_id,  # Use actual statement ID
            rows,
            self.client_state,
            batch_size=100
        )
        elapsed = (time.time() - start_time) * 1000
        
        self.assertEqual(result.rows_inserted, 1000)
        self.assertEqual(result.rows_failed, 0)
        print(f"\n1000 rows inserted in {elapsed:.2f}ms")
        
        # Should be reasonably fast (under 1 second for 1000 rows)
        self.assertLess(elapsed, 1000)
    
    def test_bulk_insert_performance_comparison(self):
        """Compare prepared batch vs individual execution."""
        # Prepare statement and get ID
        stmt_id = self.prepared_manager.prepare("INSERT INTO users (id, name) VALUES (?, ?)")
        
        rows = [[i, f'User{i}'] for i in range(100)]
        
        # Time prepared batch execution
        start = time.time()
        result1 = self.prepared_executor.batch_execute_prepared(
            stmt_id, rows, self.client_state, batch_size=25
        )
        prepared_time = (time.time() - start) * 1000
        
        # Reset
        self.registry.executed_commands.clear()
        
        # Time individual execution (simulated)
        start = time.time()
        for row in rows:
            self.registry.execute('INSERT', {'values': row}, self.client_state)
        individual_time = (time.time() - start) * 1000
        
        print(f"\nPrepared batch: {prepared_time:.2f}ms")
        print(f"Individual: {individual_time:.2f}ms")
        print(f"Speedup: {individual_time/prepared_time:.1f}x")
        
        # Prepared should be faster
        self.assertLess(prepared_time, individual_time)
    
    def test_parameter_parsing(self):
        """Test parameter parsing from strings."""
        # Test various parameter types
        test_cases = [
            ("1, 2, 3", [1, 2, 3]),
            ("'hello', 'world'", ['hello', 'world']),
            ("1.5, 2.5", [1.5, 2.5]),
            ("NULL, TRUE, FALSE", [None, True, False]),
            ("'string with, comma'", ['string with, comma']),
        ]
        
        for params_str, expected in test_cases:
            result = self.prepared_executor._parse_parameters(params_str)
            self.assertEqual(result, expected, f"Failed for: {params_str}")
    
    def test_named_parameters_in_batch(self):
        """Test named parameters in batch execution."""
        # Prepare with named parameters
        self.prepared_manager.prepare("SELECT * FROM users WHERE id = :user_id AND name = :user_name")
        
        commands = [
            "PREPARE get_user AS SELECT * FROM users WHERE id = :user_id AND name = :user_name",
            "EXECUTE get_user(user_id => 123, user_name => 'Alice')",
            "DEALLOCATE get_user"
        ]
        
        result = self.prepared_executor.execute_batch_with_prepared(
            commands,
            self.client_state,
            user_id="test_user"
        )
        
        self.assertIn("Batch Execution", result)
    
    def test_error_handling_invalid_statement(self):
        """Test error handling for invalid prepared statement."""
        commands = [
            "EXECUTE nonexistent USING 123"
        ]
        
        result = self.prepared_executor.execute_batch_with_prepared(
            commands,
            self.client_state,
            user_id="test_user"
        )
        
        # Should report error
        self.assertIn("ERROR", result)
    
    def test_error_handling_missing_parameters(self):
        """Test error handling for missing parameters."""
        # Prepare statement
        self.prepared_manager.prepare("INSERT INTO users (id, name) VALUES (?, ?)")
        
        commands = [
            "EXECUTE stmt USING 123"  # Missing second parameter
        ]
        
        result = self.prepared_executor.execute_batch_with_prepared(
            commands,
            self.client_state,
            user_id="test_user"
        )
        
        # Should report error
        self.assertIn("ERROR", result)
    
    def test_stats_tracking(self):
        """Test statistics tracking."""
        # Prepare and execute - get actual ID
        stmt_id = self.prepared_manager.prepare("INSERT INTO users (id) VALUES (?)")
        
        rows = [[i] for i in range(10)]
        self.prepared_executor.batch_execute_prepared(
            stmt_id, rows, self.client_state
        )
        
        stats = self.prepared_executor.get_stats()
        
        self.assertEqual(stats['bulk_inserts'], 1)
        self.assertEqual(stats['rows_inserted'], 10)
        self.assertEqual(stats['prepared_executions'], 10)


class TestBulkInsertOptimizer(unittest.TestCase):
    """Test suite for bulk insert optimizer."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.parser = MockParser()
        self.registry = MockCommandRegistry()
        self.batch_executor = BatchExecutor(self.parser, self.registry)
        self.prepared_manager = PreparedStatementManager()
        self.prepared_executor = BatchPreparedExecutor(
            self.batch_executor,
            self.prepared_manager
        )
        self.optimizer = BulkInsertOptimizer(self.prepared_executor)
        self.client_state = {
            'current_db': 'test_db',
            'username': 'test_user'
        }
    
    def test_optimize_insert_sequence(self):
        """Test optimization of INSERT sequence."""
        insert_commands = [
            "INSERT INTO users VALUES (1, 'Alice')",
            "INSERT INTO users VALUES (2, 'Bob')",
            "INSERT INTO users VALUES (3, 'Charlie')"
        ]
        
        result = self.optimizer.optimize_insert_sequence(
            insert_commands,
            'users',
            ['id', 'name'],
            self.client_state
        )
        
        self.assertEqual(result.rows_inserted, 3)
        self.assertEqual(result.rows_failed, 0)
    
    def test_extract_insert_values(self):
        """Test extraction of VALUES from INSERT."""
        sql = "INSERT INTO users VALUES (1, 'Alice', NULL, TRUE)"
        values = self.optimizer._extract_insert_values(sql)
        
        self.assertEqual(values, [1, 'Alice', None, True])
    
    def test_bulk_insert_convenience_function(self):
        """Test bulk_insert convenience function."""
        rows = [
            [1, 'Alice', 'alice@example.com'],
            [2, 'Bob', 'bob@example.com'],
            [3, 'Charlie', 'charlie@example.com']
        ]
        
        result = bulk_insert(
            self.prepared_executor,
            'users',
            ['id', 'name', 'email'],
            rows,
            self.client_state,
            batch_size=2
        )
        
        self.assertEqual(result.rows_inserted, 3)
        self.assertEqual(result.rows_failed, 0)


class TestPerformanceBenchmarks(unittest.TestCase):
    """Performance benchmarks for prepared batch execution."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.parser = MockParser()
        self.registry = MockCommandRegistry()
        self.batch_executor = BatchExecutor(self.parser, self.registry)
        self.prepared_manager = PreparedStatementManager()
        self.prepared_executor = BatchPreparedExecutor(
            self.batch_executor,
            self.prepared_manager
        )
        self.client_state = {
            'current_db': 'test_db',
            'username': 'test_user'
        }
    
    def test_benchmark_100_rows(self):
        """Benchmark 100 rows."""
        stmt_id = self.prepared_manager.prepare("INSERT INTO users (id, name) VALUES (?, ?)")
        rows = [[i, f'User{i}'] for i in range(100)]
        
        start = time.time()
        result = self.prepared_executor.batch_execute_prepared(
            stmt_id, rows, self.client_state, batch_size=25
        )
        elapsed = (time.time() - start) * 1000
        
        print(f"\n=== Benchmark: 100 rows ===")
        print(f"Time: {elapsed:.2f}ms")
        print(f"Rows/sec: {100 / (elapsed/1000):.0f}")
        self.assertEqual(result.rows_inserted, 100)
    
    def test_benchmark_500_rows(self):
        """Benchmark 500 rows."""
        stmt_id = self.prepared_manager.prepare("INSERT INTO users (id, name) VALUES (?, ?)")
        rows = [[i, f'User{i}'] for i in range(500)]
        
        start = time.time()
        result = self.prepared_executor.batch_execute_prepared(
            stmt_id, rows, self.client_state, batch_size=50
        )
        elapsed = (time.time() - start) * 1000
        
        print(f"\n=== Benchmark: 500 rows ===")
        print(f"Time: {elapsed:.2f}ms")
        print(f"Rows/sec: {500 / (elapsed/1000):.0f}")
        self.assertEqual(result.rows_inserted, 500)
    
    def test_benchmark_1000_rows(self):
        """Benchmark 1000 rows."""
        stmt_id = self.prepared_manager.prepare("INSERT INTO users (id, name) VALUES (?, ?)")
        rows = [[i, f'User{i}'] for i in range(1000)]
        
        start = time.time()
        result = self.prepared_executor.batch_execute_prepared(
            stmt_id, rows, self.client_state, batch_size=100
        )
        elapsed = (time.time() - start) * 1000
        
        print(f"\n=== Benchmark: 1000 rows ===")
        print(f"Time: {elapsed:.2f}ms")
        print(f"Rows/sec: {1000 / (elapsed/1000):.0f}")
        self.assertEqual(result.rows_inserted, 1000)
    
    def test_benchmark_10000_rows(self):
        """Benchmark 10000 rows."""
        stmt_id = self.prepared_manager.prepare("INSERT INTO users (id, name) VALUES (?, ?)")
        rows = [[i, f'User{i}'] for i in range(10000)]
        
        start = time.time()
        result = self.prepared_executor.batch_execute_prepared(
            stmt_id, rows, self.client_state, batch_size=1000
        )
        elapsed = (time.time() - start) * 1000
        
        print(f"\n=== Benchmark: 10000 rows ===")
        print(f"Time: {elapsed:.2f}ms")
        print(f"Rows/sec: {10000 / (elapsed/1000):.0f}")
        self.assertEqual(result.rows_inserted, 10000)


if __name__ == '__main__':
    unittest.main(verbosity=2)
