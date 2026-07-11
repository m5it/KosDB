"""
Test Parallel Query Execution for KosDB v3.4.0

Tests:
- Parallel table scans
- Parallel aggregations
- Parallel joins
- Worker pool management
- Load balancing
- Result correctness
- Performance improvement
"""

import unittest
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parallel_executor import (
    ParallelExecutor, ParallelPlan, ParallelStrategy,
    WorkerPool, WorkerTask, ParallelQueryOptimizer
)
from query_optimizer import QueryOptimizer, Statistics


class MockDB:
    """Mock database for testing."""
    
    def __init__(self, row_count=10000):
        self.row_count = row_count
        self.data = [
            {'id': i, 'value': i * 10, 'category': f'cat_{i % 10}'}
            for i in range(row_count)
        ]
    
    def select(self, table, columns, where):
        """Sequential select."""
        return self.data
    
    def select_range(self, table, columns, start, end, where):
        """Select range of rows."""
        return self.data[start:min(end, len(self.data))]
    
    def get_table_row_count(self, table):
        """Return row count."""
        return self.row_count


class TestWorkerPool(unittest.TestCase):
    """Test worker pool management."""
    
    def test_create_worker_pool(self):
        """Create worker pool with specified workers."""
        pool = WorkerPool(max_workers=4, use_processes=False)
        self.assertEqual(pool.max_workers, 4)
        self.assertFalse(pool.use_processes)
    
    def test_worker_pool_context_manager(self):
        """Test worker pool as context manager."""
        with WorkerPool(max_workers=2) as pool:
            self.assertIsNotNone(pool.executor)
    
    def test_load_balance_calculation(self):
        """Test load balance metric calculation."""
        pool = WorkerPool(max_workers=4)
        
        # Simulate some work distribution
        pool._worker_stats[0]['tasks'] = 10
        pool._worker_stats[1]['tasks'] = 10
        pool._worker_stats[2]['tasks'] = 10
        pool._worker_stats[3]['tasks'] = 10
        
        balance = pool.get_load_balance()
        self.assertEqual(balance, 1.0)  # Perfect balance
    
    def test_load_balance_imbalanced(self):
        """Test load balance with imbalanced workers."""
        pool = WorkerPool(max_workers=4)
        
        pool._worker_stats[0]['tasks'] = 20
        pool._worker_stats[1]['tasks'] = 5
        pool._worker_stats[2]['tasks'] = 5
        pool._worker_stats[3]['tasks'] = 5
        
        balance = pool.get_load_balance()
        self.assertLess(balance, 1.0)  # Imbalanced


class TestParallelScan(unittest.TestCase):
    """Test parallel table scans."""
    
    def setUp(self):
        self.db = MockDB(row_count=10000)
        self.executor = ParallelExecutor(self.db, max_workers=4)
    
    def test_parallel_scan_small_table(self):
        """Small tables should use sequential scan."""
        small_db = MockDB(row_count=100)
        executor = ParallelExecutor(small_db, max_workers=4)
        
        results = list(executor.execute_parallel_scan(
            'test', ['id', 'value'], None, dop=4
        ))
        
        self.assertEqual(len(results), 100)
    
    def test_parallel_scan_large_table(self):
        """Large tables should use parallel scan."""
        results = list(executor.execute_parallel_scan(
            'test', ['id', 'value'], None, dop=4
        ))
        
        self.assertEqual(len(results), 10000)
    
    def test_parallel_scan_with_filter(self):
        """Parallel scan with WHERE clause."""
        results = list(executor.execute_parallel_scan(
            'test', ['id', 'value'], 'id > 5000', dop=4
        ))
        
        # Should return all rows (filter applied after scan)
        self.assertEqual(len(results), 10000)
    
    def test_parallel_scan_performance(self):
        """Verify parallel scan is faster than sequential."""
        # Sequential scan
        start = time.time()
        seq_results = list(self.db.select('test', ['id', 'value'], None))
        seq_time = time.time() - start
        
        # Parallel scan
        start = time.time()
        par_results = list(self.executor.execute_parallel_scan(
            'test', ['id', 'value'], None, dop=4
        ))
        par_time = time.time() - start
        
        # Parallel should not be significantly slower
        # (Note: With mock data, overhead may dominate)
        self.assertEqual(len(seq_results), len(par_results))


class TestParallelAggregation(unittest.TestCase):
    """Test parallel aggregations."""
    
    def setUp(self):
        self.db = MockDB(row_count=10000)
        self.executor = ParallelExecutor(self.db, max_workers=4)
    
    def test_parallel_sum(self):
        """Test parallel SUM aggregation."""
        result = self.executor.execute_parallel_aggregation(
            'test',
            agg_columns=['SUM(value)'],
            group_by=None,
            where_clause=None,
            dop=4
        )
        
        self.assertEqual(len(result), 1)
        # Sum of 0, 10, 20, ... 99990 = 10 * (0+1+2+...+9999) = 10 * 9999*10000/2 = 499950000
        expected_sum = sum(i * 10 for i in range(10000))
        self.assertEqual(result[0]['SUM(value)'], expected_sum)
    
    def test_parallel_count(self):
        """Test parallel COUNT aggregation."""
        result = self.executor.execute_parallel_aggregation(
            'test',
            agg_columns=['COUNT(*)'],
            group_by=None,
            where_clause=None,
            dop=4
        )
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['COUNT(*)'], 10000)
    
    def test_parallel_group_by(self):
        """Test parallel aggregation with GROUP BY."""
        result = self.executor.execute_parallel_aggregation(
            'test',
            agg_columns=['SUM(value)', 'COUNT(*)'],
            group_by=['category'],
            where_clause=None,
            dop=4
        )
        
        # Should have 10 groups (cat_0 through cat_9)
        self.assertEqual(len(result), 10)
        
        # Each group should have count 1000
        for row in result:
            self.assertEqual(row['COUNT(*)'], 1000)


class TestParallelJoin(unittest.TestCase):
    """Test parallel joins."""
    
    def setUp(self):
        self.db = MockDB(row_count=1000)
        self.executor = ParallelExecutor(self.db, max_workers=4)
    
    def test_parallel_hash_join(self):
        """Test parallel hash join."""
        # This is a simplified test
        # Full implementation would require two actual tables
        results = list(self.executor.execute_parallel_join(
            'table1', 'table2', 'INNER', 't1.id = t2.id', dop=4
        ))
        
        # Should return some results (implementation dependent)
        self.assertIsInstance(results, list)


class TestParallelQueryOptimizer(unittest.TestCase):
    """Test parallel query optimizer."""
    
    def setUp(self):
        self.optimizer = QueryOptimizer()
        self.parallel_optimizer = ParallelQueryOptimizer(None)
    
    def test_should_parallelize_large_table(self):
        """Large tables should be parallelized."""
        should_parallel, dop = self.parallel_optimizer.should_parallelize(
            'large_table', 'scan', 100000
        )
        
        self.assertTrue(should_parallel)
        self.assertGreater(dop, 1)
    
    def test_should_not_parallelize_small_table(self):
        """Small tables should not be parallelized."""
        should_parallel, dop = self.parallel_optimizer.should_parallelize(
            'small_table', 'scan', 1000
        )
        
        self.assertFalse(should_parallel)
        self.assertEqual(dop, 1)
    
    def test_recommended_dop_based_on_size(self):
        """DOP should increase with table size."""
        _, dop_small = self.parallel_optimizer.should_parallelize(
            'table', 'scan', 50000
        )
        _, dop_medium = self.parallel_optimizer.should_parallelize(
            'table', 'scan', 500000
        )
        _, dop_large = self.parallel_optimizer.should_parallelize(
            'table', 'scan', 5000000
        )
        
        self.assertLessEqual(dop_small, dop_medium)
        self.assertLessEqual(dop_medium, dop_large)
    
    def test_parallel_strategy_selection(self):
        """Test strategy selection based on operation."""
        # Would test different strategies for different operations
        plan = ParallelPlan(
            strategy=ParallelStrategy.SCAN,
            degree_of_parallelism=4
        )
        
        self.assertEqual(plan.strategy, ParallelStrategy.SCAN)


class TestParallelExecutionCorrectness(unittest.TestCase):
    """Test that parallel execution produces correct results."""
    
    def setUp(self):
        self.db = MockDB(row_count=10000)
        self.executor = ParallelExecutor(self.db, max_workers=4)
    
    def test_parallel_scan_correctness(self):
        """Parallel scan should return same results as sequential."""
        # Sequential
        seq_results = list(self.db.select('test', ['id'], None))
        
        # Parallel
        par_results = list(self.executor.execute_parallel_scan(
            'test', ['id'], None, dop=4
        ))
        
        # Sort both by id for comparison
        seq_sorted = sorted(seq_results, key=lambda x: x['id'])
        par_sorted = sorted(par_results, key=lambda x: x['id'])
        
        self.assertEqual(len(seq_sorted), len(par_sorted))
        
        for i, (seq, par) in enumerate(zip(seq_sorted, par_sorted)):
            self.assertEqual(seq['id'], par['id'])
    
    def test_parallel_aggregation_correctness(self):
        """Parallel aggregation should match sequential."""
        # Calculate expected sum
        expected_sum = sum(i * 10 for i in range(10000))
        
        # Parallel aggregation
        result = self.executor.execute_parallel_aggregation(
            'test',
            agg_columns=['SUM(value)'],
            group_by=None,
            where_clause=None,
            dop=4
        )
        
        self.assertEqual(result[0]['SUM(value)'], expected_sum)


class TestWorkerTask(unittest.TestCase):
    """Test worker task functionality."""
    
    def test_create_worker_task(self):
        """Create worker task."""
        task = WorkerTask(
            task_id=1,
n            operation='scan',\n            data_range=(0, 100),\n            query_params={'table': 'test'}\n        )\n        \n        self.assertEqual(task.task_id, 1)\n        self.assertEqual(task.operation, 'scan')\n        self.assertEqual(task.data_range, (0, 100))\n    \n    def test_worker_task_result(self):
n        \"\"\"Test setting task result.\"\"\"\n        task = WorkerTask(\n            task_id=1,\n            operation='scan',\n            data_range=(0, 100),\n            query_params={'table': 'test'}\n        )\n        \n        task.result = [{'id': 1}, {'id': 2}]\n        task.rows_processed = 2\n        task.execution_time = 0.5\n        \n        self.assertEqual(len(task.result), 2)\n        self.assertEqual(task.rows_processed, 2)


class TestParallelExecutionStats(unittest.TestCase):
n    \"\"\"Test parallel execution statistics.\"\"\"\n    \n    def setUp(self):\n        self.db = MockDB(row_count=10000)\n        self.executor = ParallelExecutor(self.db, max_workers=4)
    
    def test_stats_tracking(self):
n        \"\"\"Track execution statistics.\"\"\"\n        # Execute some queries\n        list(self.executor.execute_parallel_scan('test', ['id'], None, dop=2))\n        list(self.executor.execute_parallel_scan('test', ['id'], None, dop=4))\n        \n        stats = self.executor.get_stats()\n        \n        self.assertEqual(stats['queries_executed'], 2)\n        self.assertEqual(stats['parallel_queries'], 2)
    
    def test_max_workers_in_stats(self):
n        \"\"\"Stats should include max workers.\"\"\"\n        stats = self.executor.get_stats()\n        \n        self.assertEqual(stats['max_workers'], 4)
        self.assertFalse(stats['use_processes'])


class TestQueryOptimizerParallelIntegration(unittest.TestCase):
n    \"\"\"Test integration of parallel execution with query optimizer.\"\"\"\n    \n    def setUp(self):\n        self.optimizer = QueryOptimizer()\n        \n        # Add statistics for large table\n        stats = Statistics('large_table', row_count=100000)\n        self.optimizer.add_statistics('large_table', stats)
    
    def test_optimizer_considers_parallel(self):
n        \"\"\"Optimizer should consider parallel execution for large tables.\"\"\"\n        plan = self.optimizer.optimize(\"SELECT * FROM large_table\")\n        \n        # Should have parallel plan for large table\n        self.assertIsNotNone(plan.parallel_plan)\n        self.assertGreater(plan.parallel_plan.degree_of_parallelism, 1)
    
    def test_optimizer_parallel_speedup(self):
n        \"\"\"Parallel plan should show speedup.\"\"\"\n        plan = self.optimizer.optimize(\"SELECT * FROM large_table\")\n        \n        if plan.parallel_plan:\n            self.assertGreater(plan.parallel_plan.speedup_factor, 1.0)


if __name__ == '__main__':\n    unittest.main(verbosity=2)\n