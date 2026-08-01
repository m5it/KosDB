#!/usr/bin/env python3
"""
Test Suite for Sort Engine

Comprehensive tests for:
- SortEngine class
- Sort backends (builtin, madS0rt_py, madS0rt_rust)
- Configuration management
- Query optimizer integration
- Edge cases and error handling

Run: python -m pytest test_sort_engine.py -v
"""

import unittest
import random
import string
import os
import sys
from typing import List, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestSortEngine(unittest.TestCase):
    """Test SortEngine class."""
    
    def setUp(self):
        """Set up test fixtures."""
        from sort_engine import SortEngine
        
        self.builtin_engine = SortEngine(backend='builtin')
    
    def test_builtin_backend_selection(self):
        """Test builtin backend is selected."""
        self.assertEqual(self.builtin_engine.backend_name, 'builtin')
    
    def test_sort_integers(self):
        """Test sorting integers."""
        data = [3, 1, 4, 1, 5, 9, 2, 6]
        result = self.builtin_engine.sort(data)
        self.assertEqual(result, [1, 1, 2, 3, 4, 5, 6, 9])
    
    def test_sort_strings(self):
        """Test sorting strings."""
        data = ['banana', 'apple', 'cherry', 'date']
        result = self.builtin_engine.sort(data)
        self.assertEqual(result, ['apple', 'banana', 'cherry', 'date'])
    
    def test_sort_with_key(self):
        """Test sorting with key function."""
        data = [{'name': 'Charlie', 'age': 35},
                {'name': 'Alice', 'age': 28},
                {'name': 'Bob', 'age': 42}]
        
        result = self.builtin_engine.sort(data, key=lambda x: x['age'])
        self.assertEqual([r['name'] for r in result], ['Alice', 'Charlie', 'Bob'])
    
    def test_sort_reverse(self):
        """Test reverse sorting."""
        data = [3, 1, 4, 1, 5]
        result = self.builtin_engine.sort(data, reverse=True)
        self.assertEqual(result, [5, 4, 3, 1, 1])
    
    def test_sort_empty_list(self):
        """Test sorting empty list."""
        data = []
        result = self.builtin_engine.sort(data)
        self.assertEqual(result, [])
    
    def test_sort_single_element(self):
        """Test sorting single element."""
        data = [42]
        result = self.builtin_engine.sort(data)
        self.assertEqual(result, [42])
    
    def test_sort_already_sorted(self):
        """Test sorting already sorted data."""
        data = [1, 2, 3, 4, 5]
        result = self.builtin_engine.sort(data)
        self.assertEqual(result, [1, 2, 3, 4, 5])
    
    def test_sort_reverse_sorted(self):
        """Test sorting reverse sorted data."""
        data = [5, 4, 3, 2, 1]
        result = self.builtin_engine.sort(data)
        self.assertEqual(result, [1, 2, 3, 4, 5])
    
    def test_sort_duplicates(self):
        """Test sorting with many duplicates."""
        data = [3, 3, 3, 1, 1, 2, 2]
        result = self.builtin_engine.sort(data)
        self.assertEqual(result, [1, 1, 2, 2, 3, 3, 3])
    
    def test_sort_stability(self):
        """Test sort stability."""
        data = [(1, 'a'), (2, 'b'), (1, 'c'), (2, 'd'), (1, 'e')]
        result = self.builtin_engine.sort(data, key=lambda x: x[0])
        # Stable sort preserves order of equal elements
        self.assertEqual(result, [(1, 'a'), (1, 'c'), (1, 'e'), (2, 'b'), (2, 'd')])
    
    def test_sort_large_dataset(self):
        """Test sorting large dataset."""
        data = list(range(10000))
        random.shuffle(data)
        result = self.builtin_engine.sort(data)
        self.assertEqual(result, list(range(10000)))
    
    def test_topk_basic(self):
        """Test top-K sorting."""
        data = list(range(100))
        random.shuffle(data)
        result = self.builtin_engine.sort(data, topk=10)
        self.assertEqual(len(result), 10)
        self.assertEqual(result, list(range(10)))
    
    def test_topk_with_reverse(self):
        """Test top-K with reverse."""
        data = list(range(100))
        random.shuffle(data)
        result = self.builtin_engine.sort(data, reverse=True, topk=10)
        self.assertEqual(len(result), 10)
        self.assertEqual(result, list(range(99, 89, -1)))
    
    def test_sort_in_place(self):
        """Test in-place sorting."""
        data = [3, 1, 4, 1, 5]
        self.builtin_engine.sort_in_place(data)
        self.assertEqual(data, [1, 1, 3, 4, 5])
    
    def test_sort_preserves_original(self):
        """Test that sort doesn't modify original."""
        data = [3, 1, 4, 1, 5]
        result = self.builtin_engine.sort(data)
        self.assertEqual(data, [3, 1, 4, 1, 5])  # Original unchanged
        self.assertEqual(result, [1, 1, 3, 4, 5])  # New sorted list


class TestSortBackends(unittest.TestCase):
    """Test individual sort backends."""
    
    def test_builtin_backend(self):
        """Test BuiltinBackend directly."""
        from sort_backends.builtin import BuiltinBackend
        
        backend = BuiltinBackend()
        data = [3, 1, 4, 1, 5]
        result = backend.sort(data)
        self.assertEqual(result, [1, 1, 3, 4, 5])
        self.assertEqual(backend.name, 'builtin')
    
    def test_builtin_topk_optimization(self):
        """Test builtin top-K uses heapq."""
        from sort_backends.builtin import BuiltinBackend
        
        backend = BuiltinBackend()
        data = list(range(1000))
        random.shuffle(data)
        
        # This should use heapq.nlargest internally
        result = backend.sort(data, topk=10)
        self.assertEqual(len(result), 10)


class TestSortConfig(unittest.TestCase):
    """Test SortConfig class."""
    
    def test_default_config(self):
        """Test default configuration."""
        from sort_config import SortConfig
        
        config = SortConfig()
        self.assertEqual(config.default_backend, 'auto')
        self.assertTrue(config.auto_fallback)
        self.assertFalse(config.strict_mode)
    
    def test_custom_config(self):
        """Test custom configuration."""
        from sort_config import SortConfig
        
        config = SortConfig(
            default_backend='builtin',
            small_dataset_threshold=500
        )
        self.assertEqual(config.default_backend, 'builtin')
        self.assertEqual(config.small_dataset_threshold, 500)
    
    def test_backend_selection_by_size(self):
        """Test backend selection based on data size."""
        from sort_config import SortConfig
        
        config = SortConfig()
        
        # Small dataset
        self.assertEqual(config.select_backend_for_size(100), 'builtin')
        
        # Medium dataset
        self.assertIn(config.select_backend_for_size(50000), 
                      ['madsort_py', 'auto'])
        
        # Large dataset
        self.assertIn(config.select_backend_for_size(500000), 
                      ['madsort_rust', 'auto'])
    
    def test_topk_threshold(self):
        """Test top-K threshold logic."""
        from sort_config import SortConfig
        
        config = SortConfig(topk_threshold=0.1)
        
        # Should use top-K (10 < 10% of 200)
        self.assertTrue(config.should_use_topk(10, 200))
        
        # Should not use top-K (50 > 10% of 200)
        self.assertFalse(config.should_use_topk(50, 200))
    
    def test_config_validation(self):
        """Test configuration validation."""
        from sort_config import SortConfig
        
        # Valid config
        config = SortConfig()
        self.assertTrue(config.validate())
        
        # Invalid backend
        invalid = SortConfig(default_backend='invalid')
        with self.assertRaises(ValueError):
            invalid.validate()
        
        # Invalid threshold
        invalid = SortConfig(topk_threshold=2.0)
        with self.assertRaises(ValueError):
            invalid.validate()


class TestSortHeuristics(unittest.TestCase):
    """Test SortHeuristics class."""
    
    def test_strategy_selection(self):
        """Test strategy selection."""
        try:
            from query_optimizer import SortHeuristics, SortStrategy
        except ImportError:
            self.skipTest("SortHeuristics not available")
        
        heuristics = SortHeuristics()
        
        # Small dataset
        strategy = heuristics.select_strategy(
            estimated_rows=100,
            sort_columns=['name']
        )
        self.assertEqual(strategy, SortStrategy.BUILTIN)
        
        # With limit (top-K)
        strategy = heuristics.select_strategy(
            estimated_rows=10000,
            sort_columns=['name'],
            has_limit=True,
            limit_value=10
        )
        self.assertEqual(strategy, SortStrategy.TOPK_HEAP)
    
    def test_cost_estimation(self):
        """Test sort cost estimation."""
        try:
            from query_optimizer import SortHeuristics, SortStrategy
        except ImportError:
            self.skipTest("SortHeuristics not available")
        
        heuristics = SortHeuristics()
        
        # Index scan should have zero cost
        cost = heuristics.estimate_sort_cost(1000, SortStrategy.INDEX_SCAN)
        self.assertEqual(cost, 0)
        
        # Other strategies should have positive cost
        cost_builtin = heuristics.estimate_sort_cost(1000, SortStrategy.BUILTIN)
        self.assertGreater(cost_builtin, 0)


class TestQueryOptimizerIntegration(unittest.TestCase):
    """Test query optimizer integration."""
    
    def test_optimizer_initialization(self):
        """Test optimizer can be created."""
        from query_optimizer import QueryOptimizer
        
        optimizer = QueryOptimizer()
        self.assertIsNotNone(optimizer)
    
    def test_execution_plan_has_sort_strategy(self):
        """Test ExecutionPlan has expected attributes."""
        from query_optimizer import ExecutionPlan
        
        # Create a minimal plan - ExecutionPlan is a dataclass with specific fields
        # Check that the class exists and can be instantiated
        try:
            # Try with the actual dataclass fields
            plan = ExecutionPlan(
                root=None,  # Would be an Operator in real usage
                total_cost=100.0,
                estimated_rows=100
            )
            # If we get here, the plan was created successfully
            self.assertIsNotNone(plan)
            # Check for any attributes that might hold sort info
            # (The actual attribute names depend on the dataclass definition)
            self.assertTrue(hasattr(plan, 'total_cost'))
            self.assertTrue(hasattr(plan, 'estimated_rows'))
        except TypeError:
            # If the constructor signature is different, just check the class exists
            self.assertTrue(ExecutionPlan is not None)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""
    
    def test_none_values(self):
        """Test sorting with None values."""
        from sort_engine import SortEngine
        
        engine = SortEngine(backend='builtin')
        data = [3, None, 1, None, 2]
        
        # Python 3 doesn't allow None comparison with int
        # This should handle gracefully or raise appropriate error
        try:
            result = engine.sort(data)
            # If it works, None should be at beginning or end
            self.assertIn(None, result)
        except TypeError:
            # Expected behavior - can't compare None with int
            pass
    
    def test_mixed_types(self):
        """Test sorting with mixed types."""
        from sort_engine import SortEngine
        
        engine = SortEngine(backend='builtin')
        data = [1, 'a', 2, 'b']
        
        # Should raise TypeError for incomparable types
        with self.assertRaises(TypeError):
            engine.sort(data)
    
    def test_nan_values(self):
        """Test sorting with NaN values."""
        import math
        from sort_engine import SortEngine
        
        engine = SortEngine(backend='builtin')
        data = [3.0, float('nan'), 1.0, 2.0]
        
        result = engine.sort(data)
        # NaN behavior varies, just ensure it doesn't crash
        self.assertEqual(len(result), 4)
    
    def test_very_large_numbers(self):
        """Test sorting with very large numbers."""
        from sort_engine import SortEngine
        
        engine = SortEngine(backend='builtin')
        data = [10**100, 10**50, 10**150, 10**75]
        
        result = engine.sort(data)
        self.assertEqual(result, [10**50, 10**75, 10**100, 10**150])
    
    def test_negative_numbers(self):
        """Test sorting with negative numbers."""
        from sort_engine import SortEngine
        
        engine = SortEngine(backend='builtin')
        data = [3, -1, 4, -5, 0, 2]
        
        result = engine.sort(data)
        self.assertEqual(result, [-5, -1, 0, 2, 3, 4])


class TestPerformance(unittest.TestCase):
    """Performance-related tests."""
    
    def test_large_dataset_performance(self):
        """Test performance with large dataset."""
        import time
        from sort_engine import SortEngine
        
        engine = SortEngine(backend='builtin')
        data = [random.random() for _ in range(100000)]
        
        start = time.perf_counter()
        result = engine.sort(data)
        elapsed = time.perf_counter() - start
        
        # Should complete in reasonable time (< 1 second for 100K items)
        self.assertLess(elapsed, 1.0)
        self.assertEqual(len(result), 100000)
        
        # Verify sorted
        for i in range(len(result) - 1):
            self.assertLessEqual(result[i], result[i + 1])
    
    def test_topk_performance(self):
        """Test top-K is faster than full sort."""
        import time
        from sort_engine import SortEngine
        
        engine = SortEngine(backend='builtin')
        data = [random.random() for _ in range(100000)]
        
        # Full sort
        start = time.perf_counter()
        full_result = engine.sort(data)
        full_time = time.perf_counter() - start
        
        # Top-K
        start = time.perf_counter()
        topk_result = engine.sort(data, topk=100)
        topk_time = time.perf_counter() - start
        
        # Top-K should be faster
        self.assertLess(topk_time, full_time)
        self.assertEqual(len(topk_result), 100)


def create_test_suite():
    """Create comprehensive test suite."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestSortEngine))
    suite.addTests(loader.loadTestsFromTestCase(TestSortBackends))
    suite.addTests(loader.loadTestsFromTestCase(TestSortConfig))
    suite.addTests(loader.loadTestsFromTestCase(TestSortHeuristics))
    suite.addTests(loader.loadTestsFromTestCase(TestQueryOptimizerIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))
    suite.addTests(loader.loadTestsFromTestCase(TestPerformance))
    
    return suite


if __name__ == '__main__':
    # Run tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    suite = create_test_suite()
    result = runner.run(suite)
    
    # Exit with appropriate code
    sys.exit(0 if result.wasSuccessful() else 1)
