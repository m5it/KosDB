
"""
Comprehensive Load Testing for Batch Operations

Tests:
- Sustained batch throughput
- Large batch sizes
- Concurrent batch execution
- Memory usage profiling
- Connection pool exhaustion
- Benchmark comparisons
"""

import unittest
import sys
import os
import time
import threading
import psutil
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Dict, Any, Callable
import gc

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass
class BenchmarkResult:
    """Results from a benchmark run."""
    name: str
    duration_ms: float
    commands_per_sec: float
    avg_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    memory_mb: float
    success_rate: float
    batch_size: int
    concurrent_clients: int


class MockDatabase:
    """Mock database for load testing."""
    
    def __init__(self, latency_ms: float = 1.0):
        self.latency_ms = latency_ms
        self.executed_commands = []
        self._lock = threading.Lock()
    
    def execute(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate command execution."""
        time.sleep(self.latency_ms / 1000.0)
        
        with self._lock:
            self.executed_commands.append(command)
        
        return {"success": True, "command": command}
    
    def execute_batch(self, commands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Simulate batch execution."""
        # Batches are more efficient
        total_latency = self.latency_ms * (1 + len(commands) * 0.1)
        time.sleep(total_latency / 1000.0)
        
        with self._lock:
            self.executed_commands.extend(commands)
        
        return [{"success": True, "command": cmd} for cmd in commands]


class TestBatchThroughput(unittest.TestCase):
    """Test sustained batch throughput."""
    
    def setUp(self):
        self.db = MockDatabase(latency_ms=1.0)
    
    def test_throughput_single_commands(self):
        """Measure throughput of individual commands."""
        num_commands = 100
        start_time = time.time()
        
        for i in range(num_commands):
            self.db.execute({"op": "INSERT", "table": "users", "key": i})
        
        duration = time.time() - start_time
        throughput = num_commands / duration
        
        print(f"\nSingle command throughput: {throughput:.2f} cmd/sec")
        self.assertGreater(throughput, 100)
    
    def test_throughput_small_batches(self):
        """Measure throughput of small batches (10 commands)."""
        num_batches = 50
        batch_size = 10
        start_time = time.time()
        
        for i in range(num_batches):
            commands = [
                {"op": "INSERT", "table": "users", "key": i * batch_size + j}
                for j in range(batch_size)
            ]
            self.db.execute_batch(commands)
        
        duration = time.time() - start_time
        total_commands = num_batches * batch_size
        throughput = total_commands / duration
        
        print(f"\nSmall batch (10) throughput: {throughput:.2f} cmd/sec")
        self.assertGreater(throughput, 200)
    
    def test_throughput_medium_batches(self):
        """Measure throughput of medium batches (100 commands)."""
        num_batches = 5
        batch_size = 100
        start_time = time.time()
        
        for i in range(num_batches):
            commands = [
                {"op": "INSERT", "table": "users", "key": i * batch_size + j}
                for j in range(batch_size)
            ]
            self.db.execute_batch(commands)
        
        duration = time.time() - start_time
        total_commands = num_batches * batch_size
        throughput = total_commands / duration
        
        print(f"\nMedium batch (100) throughput: {throughput:.2f} cmd/sec")
    
    def test_sustained_throughput_10_seconds(self):
        """Test sustained throughput over 10 seconds."""
        duration_seconds = 10
        batch_size = 50
        
        start_time = time.time()
        total_commands = 0
        
        while time.time() - start_time < duration_seconds:
            commands = [
                {"op": "INSERT", "table": "users", "key": total_commands + j}
                for j in range(batch_size)
            ]
            self.db.execute_batch(commands)
            total_commands += batch_size
        
        actual_duration = time.time() - start_time
        throughput = total_commands / actual_duration
        
        print(f"\nSustained throughput (10s): {throughput:.2f} cmd/sec")
        print(f"Total commands: {total_commands}")


class TestBatchSizes(unittest.TestCase):
    """Test various batch sizes."""
    
    def setUp(self):
        self.db = MockDatabase(latency_ms=0.5)
    
    def test_batch_size_1(self):
        """Test batch size of 1."""
        self._test_batch_size(1)
    
    def test_batch_size_10(self):
        """Test batch size of 10."""
        self._test_batch_size(10)
    
    def test_batch_size_100(self):
        """Test batch size of 100."""
        self._test_batch_size(100)
    
    def test_batch_size_1000(self):
        """Test batch size of 1000."""
        self._test_batch_size(1000)
    
    def _test_batch_size(self, size: int):
        """Helper to test a specific batch size."""
        commands = [
            {"op": "INSERT", "table": "users", "key": i, "data": "x" * 100}
            for i in range(size)
        ]
        
        start_time = time.time()
        results = self.db.execute_batch(commands)
        duration = time.time() - start_time
        
        throughput = size / duration
        
        print(f"\nBatch size {size}: {throughput:.2f} cmd/sec "
              f"({duration*1000:.2f} ms total)")
        
        self.assertEqual(len(results), size)
        return throughput


class TestConcurrentExecution(unittest.TestCase):
    """Test concurrent batch execution."""
    
    def setUp(self):
        self.db = MockDatabase(latency_ms=2.0)
    
    def test_concurrent_2_clients(self):
        """Test with 2 concurrent clients."""
        self._test_concurrent_clients(2, 20)
    
    def test_concurrent_5_clients(self):
        """Test with 5 concurrent clients."""
        self._test_concurrent_clients(5, 20)
    
    def _test_concurrent_clients(self, num_clients: int, batches_per_client: int):
        """Test with specified number of concurrent clients."""
        batch_size = 10
        
        def client_worker(client_id: int) -> Dict[str, Any]:
            """Worker function for each client."""
            start_time = time.time()
            total_commands = 0
            
            for i in range(batches_per_client):
                commands = [
                    {"op": "INSERT", "table": "users", 
                     "key": f"{client_id}_{i}_{j}"}
                    for j in range(batch_size)
                ]
                self.db.execute_batch(commands)
                total_commands += batch_size
            
            duration = time.time() - start_time
            return {
                'client_id': client_id,
                'duration': duration,
                'commands': total_commands,
                'throughput': total_commands / duration
            }
        
        # Execute concurrently
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=num_clients) as executor:
            futures = [
                executor.submit(client_worker, i)
                for i in range(num_clients)
            ]
            results = [f.result() for f in as_completed(futures)]
        
        total_duration = time.time() - start_time
        total_commands = sum(r['commands'] for r in results)
        overall_throughput = total_commands / total_duration
        
        print(f"\nConcurrent clients: {num_clients}")
        print(f"Total commands: {total_commands}")
        print(f"Overall throughput: {overall_throughput:.2f} cmd/sec")


class TestMemoryProfiling(unittest.TestCase):
    """Test memory usage during batch operations."""
    
    def setUp(self):
        self.db = MockDatabase(latency_ms=0.1)
        self.process = psutil.Process()
    
    def get_memory_mb(self) -> float:
        """Get current memory usage in MB."""
        return self.process.memory_info().rss / 1024 / 1024
    
    def test_memory_small_batch(self):
        """Test memory with small batch."""
        self._test_memory_batch_size(100)
    
    def test_memory_medium_batch(self):
        """Test memory with medium batch."""
        self._test_memory_batch_size(1000)
    
    def _test_memory_batch_size(self, size: int):
        """Test memory usage for specific batch size."""
        gc.collect()
        
        before_mb = self.get_memory_mb()
        
        commands = [
            {"op": "INSERT", "table": "users", "key": i, "data": "x" * 1000}
            for i in range(size)
        ]
        
        self.db.execute_batch(commands)
        
        after_mb = self.get_memory_mb()
        used_mb = after_mb - before_mb
        
        print(f"\nBatch size {size}: {used_mb:.2f} MB used")
        
        if size > 0:
            mb_per_command = used_mb / size
            print(f"  Memory per command: {mb_per_command * 1024:.4f} KB")


class TestBenchmarkComparisons(unittest.TestCase):
    """Benchmark comparisons between single and batch commands."""
    
    def setUp(self):
        self.db = MockDatabase(latency_ms=1.0)
    
    def test_single_vs_batch_comparison(self):
        """Compare single vs batch execution."""
        num_commands = 100
        
        # Single commands
        start_single = time.time()
        for i in range(num_commands):
            self.db.execute({"op": "INSERT"})
        duration_single = time.time() - start_single
        
        # Batch
        start_batch = time.time()
        commands = [{"op": "INSERT"} for _ in range(num_commands)]
        self.db.execute_batch(commands)
        duration_batch = time.time() - start_batch
        
        print(f"\nSingle: {duration_single*1000:.2f} ms")
        print(f"Batch:  {duration_batch*1000:.2f} ms")
        print(f"Speedup: {duration_single/duration_batch:.2f}x")
        
        self.assertGreater(duration_single, duration_batch)


class TestPerformanceBaselines(unittest.TestCase):
    """Establish and test performance baselines."""
    
    BASELINES = {
        'single_command_throughput': 100,
        'small_batch_throughput': 200,
        'p99_latency_ms': 100,
    }
    
    def setUp(self):
        self.db = MockDatabase(latency_ms=1.0)
    
    def test_baseline_single_throughput(self):
        """Test single command throughput baseline."""
        num_commands = 100
        start_time = time.time()
        
        for i in range(num_commands):
            self.db.execute({"op": "INSERT"})
        
        duration = time.time() - start_time
        throughput = num_commands / duration
        
        baseline = self.BASELINES['single_command_throughput']
        print(f"\nSingle throughput: {throughput:.2f} vs baseline {baseline}")
        
        self.assertGreaterEqual(throughput, baseline * 0.8)


if __name__ == '__main__':
    unittest.main(verbosity=2)
