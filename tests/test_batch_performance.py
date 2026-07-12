
"""
Performance tests for batch command execution.

Compares batch execution vs individual command execution.
Tests caching effectiveness and memory efficiency.
"""

import unittest
import time
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from batch_executor import BatchExecutor, BatchBenchmark, CommandCache, StringBuilder
    BATCH_AVAILABLE = True
except ImportError:
    BATCH_AVAILABLE = False


class MockParser:
    """Mock parser for testing."""
    def __init__(self):
        self.parse_count = 0
    
    def parse(self, cmd):
        self.parse_count += 1
        # Simple parsing: first word is type, rest is params
        parts = cmd.strip().split(None, 1)
        cmd_type = parts[0].upper() if parts else "UNKNOWN"
        params = {'raw': cmd}
        return cmd_type, params


class MockCommandRegistry:
    """Mock command registry for testing."""
    def execute(self, cmd_type, params, client_state):
        # Simulate some work
        time.sleep(0.001)  # 1ms per command
        return f"OK: Executed {cmd_type}"


class TestCommandCache(unittest.TestCase):
    """Test command caching functionality."""
    
    def setUp(self):
        self.cache = CommandCache(max_size=100)
    
    def test_cache_hit(self):
        """Test cache hit increases hit count."""
        self.cache.put("SELECT * FROM users", "SELECT", {"table": "users"})
        
        result = self.cache.get("SELECT * FROM users")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "SELECT")
        
        stats = self.cache.get_stats()
        self.assertEqual(stats['hits'], 1)
        self.assertEqual(stats['misses'], 0)
    
    def test_cache_miss(self):
        """Test cache miss increases miss count."""
        result = self.cache.get("UNKNOWN COMMAND")
        self.assertIsNone(result)
        
        stats = self.cache.get_stats()
        self.assertEqual(stats['hits'], 0)
        self.assertEqual(stats['misses'], 1)
    
    def test_cache_lru_eviction(self):
        """Test LRU eviction when cache is full."""
        # Fill cache
        for i in range(150):
            self.cache.put(f"CMD {i}", "CMD", {"id": i})
        
        stats = self.cache.get_stats()
        self.assertEqual(stats['size'], 100)  # Max size maintained
    
    def test_cache_stats(self):
        """Test cache statistics."""
        for i in range(10):
            self.cache.put(f"CMD {i}", "CMD", {"id": i})
        
        for i in range(5):
            self.cache.get(f"CMD {i}")  # 5 hits
        
        stats = self.cache.get_stats()
        self.assertEqual(stats['size'], 10)
        self.assertEqual(stats['hits'], 5)
        self.assertEqual(stats['misses'], 1)  # From test
        self.assertGreater(stats['hit_rate'], 0)


class TestStringBuilder(unittest.TestCase):
    """Test StringBuilder performance optimization."""
    
    def test_basic_building(self):
        """Test basic string building."""
        builder = StringBuilder()
        builder.append_line("Line 1")
        builder.append_line("Line 2")
        
        result = builder.build()
        self.assertIn("Line 1", result)
        self.assertIn("Line 2", result)
    
    def test_size_tracking(self):
        """Test size tracking."""
        builder = StringBuilder()
        builder.append("test")
        self.assertEqual(len(builder), 4)
    
    def test_separator(self):
        """Test separator appending."""
        builder = StringBuilder()
        builder.append_separator("-", 10)
        result = builder.build()
        self.assertIn("----------", result)


@unittest.skipUnless(BATCH_AVAILABLE, "BatchExecutor not available")
class TestBatchExecutor(unittest.TestCase):
    """Test optimized batch execution."""
    
    def setUp(self):
        self.parser = MockParser()
        self.registry = MockCommandRegistry()
        self.executor = BatchExecutor(self.parser, self.registry)
    
    def test_batch_execution(self):
        """Test basic batch execution."""
        commands = ["SELECT 1", "SELECT 2", "SELECT 3"]
        
        start = time.time()
        result = self.executor.execute_batch(commands, {})
        elapsed = time.time() - start
        
        self.assertIn("Batch Execution", result)
        self.assertIn("3 commands", result)
        self.assertGreater(elapsed, 0)
    
    def test_command_caching(self):
        """Test that command parsing is cached."""
        commands = ["SELECT * FROM users", "SELECT * FROM users", "SELECT * FROM users"]
        
        self.executor.execute_batch(commands, {})
        
        # Should have parsed only once
        self.assertEqual(self.parser.parse_count, 1)
        
        metrics = self.executor.get_metrics()
        self.assertGreater(metrics['cache_hit_rate'], 0)
    
    def test_metrics_collection(self):
        """Test metrics are collected."""
        commands = ["CMD 1", "CMD 2", "CMD 3"]
        self.executor.execute_batch(commands, {})
        
        metrics = self.executor.get_metrics()
        self.assertEqual(metrics['total_batches'], 1)
        self.assertEqual(metrics['total_commands'], 3)
        self.assertGreater(metrics['avg_batch_time_ms'], 0)
    
    def test_large_batch_streaming(self):
        """Test streaming mode for large batches."""
        commands = [f"SELECT {i}" for i in range(150)]
        
        start = time.time()
        result = self.executor.execute_batch(commands, {}, use_streaming=True)
        elapsed = time.time() - start
        
        self.assertIn("streaming mode", result)
        self.assertGreater(elapsed, 0)


@unittest.skipUnless(BATCH_AVAILABLE, "BatchExecutor not available")
class TestBatchBenchmark(unittest.TestCase):
    """Test batch performance benchmarking."""
    
    def setUp(self):
        self.parser = MockParser()
        self.registry = MockCommandRegistry()
        self.executor = BatchExecutor(self.parser, self.registry)
        self.benchmark = BatchBenchmark(self.executor)
    
    def test_benchmark_runs(self):
        """Test that benchmark executes."""
        commands = ["SELECT 1", "SELECT 2", "SELECT 3", "SELECT 4", "SELECT 5"]
        
        results = self.benchmark.benchmark(commands, iterations=3)
        
        self.assertIn('batch', results)
        self.assertIn('individual', results)
        self.assertIn('speedup', results)
        
        # Both should have timing data
        self.assertGreater(results['batch']['avg_ms'], 0)
        self.assertGreater(results['individual']['avg_ms'], 0)
    
    def test_speedup_calculation(self):
        """Test speedup is calculated correctly."""
        commands = ["SELECT 1", "SELECT 2", "SELECT 3"]
        
        results = self.benchmark.benchmark(commands, iterations=2)
        
        # Speedup should be positive
        self.assertGreater(results['speedup'], 0)
        
        # Batch should generally be faster
        self.assertLess(
            results['batch']['avg_ms'],
            results['individual']['avg_ms']
        )


class TestPerformanceComparison(unittest.TestCase):
    """Compare batch vs individual execution performance."""
    
    @unittest.skipUnless(BATCH_AVAILABLE, "BatchExecutor not available")
    def test_100_commands_performance(self):
        """Test performance with 100 commands."""
        parser = MockParser()
        registry = MockCommandRegistry()
        executor = BatchExecutor(parser, registry)
        
        commands = [f"SELECT * FROM table{i}" for i in range(100)]
        
        # Time batch execution
        start = time.time()
        executor.execute_batch(commands, {})
        batch_time = time.time() - start
        
        # Time individual execution
        start = time.time()
        for cmd in commands:
            cmd_type, params = parser.parse(cmd)
            registry.execute(cmd_type, params, {})
        individual_time = time.time() - start
        
        print(f"\nPerformance Results (100 commands):")
        print(f"  Batch time: {batch_time*1000:.2f} ms")
        print(f"  Individual time: {individual_time*1000:.2f} ms")
        print(f"  Speedup: {individual_time/batch_time:.2f}x")
        
        # Batch should be significantly faster due to caching
        self.assertLess(batch_time, individual_time * 0.9)
    
    def test_memory_efficiency(self):
        """Test memory efficiency of StringBuilder vs concatenation."""
        import io
        
        # StringBuilder approach
        builder = StringBuilder()
        for i in range(1000):
            builder.append_line(f"Line {i}: " + "x" * 100)
        
        result1 = builder.build()
        
        # String concatenation approach
        result2 = ""
        for i in range(1000):
            result2 += f"Line {i}: " + "x" * 100 + "\n"
        
        # Both should produce same result
        self.assertEqual(len(result1), len(result2))


if __name__ == '__main__':
    # Run with verbose output
    unittest.main(verbosity=2)
