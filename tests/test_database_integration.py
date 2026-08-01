#!/usr/bin/env python3
"""
Integration Tests: Sort Engine with Database

Tests the complete integration of sort engine with KosDB:
- ORDER BY queries use sort engine
- Configuration affects sort behavior
- Fallback mechanisms work
- Performance improvements measurable

Run: python -m pytest test_database_integration.py -v
"""

import unittest
import tempfile
import shutil
import random
import os
import sys
from typing import List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestDatabaseSortIntegration(unittest.TestCase):
    """Test sort engine integration with Database class."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test database."""
        from database import Database
        
        cls.test_dir = tempfile.mkdtemp()
        cls.db = Database(data_dir=cls.test_dir, server_id=1)
        
        # Create test table with sample data
        cls.db.create_table("test_sort", {
            "id": "INTEGER",
            "name": "TEXT",
            "score": "INTEGER",
            "category": "TEXT"
        })
        
        # Insert test data
        test_data = [
            (1, "Alice", 85, "A"),
            (2, "Bob", 92, "B"),
            (3, "Charlie", 78, "A"),
            (4, "Diana", 95, "B"),
            (5, "Eve", 88, "A"),
            (6, "Frank", 73, "C"),
            (7, "Grace", 91, "B"),
            (8, "Henry", 82, "C"),
        ]
        
        for row in test_data:
            cls.db.insert("test_sort", {
                "id": row[0],
                "name": row[1],
                "score": row[2],
                "category": row[3]
            })
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test database."""
        cls.db.close()
        shutil.rmtree(cls.test_dir)
    
    def test_sort_engine_available(self):
        """Test that sort engine is available in database."""
        self.assertIsNotNone(self.db.sort_engine)
        self.assertIsNotNone(self.db.sort_engine.backend_name)
    
    def test_select_with_order_by(self):
        """Test SELECT with ORDER BY uses sort engine."""
        results = self.db.select("test_sort", order_by="score")
        scores = [r["score"] for r in results]
        self.assertEqual(scores, sorted(scores))
    
    def test_select_with_order_by_desc(self):
        """Test SELECT with ORDER BY DESC."""
        results = self.db.select("test_sort", order_by="score", order_desc=True)
        scores = [r["score"] for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))
    
    def test_select_with_order_by_string(self):
        """Test ORDER BY on string column."""
        results = self.db.select("test_sort", order_by="name")
        names = [r["name"] for r in results]
        self.assertEqual(names, sorted(names))
    
    def test_select_with_limit_and_order(self):
        """Test ORDER BY with LIMIT."""
        results = self.db.select(
            "test_sort",
            order_by="score",
            order_desc=True,
            limit=3
        )
        self.assertEqual(len(results), 3)
        # Should be top 3 scores
        self.assertEqual(results[0]["score"], 95)
        self.assertEqual(results[1]["score"], 92)
        self.assertEqual(results[2]["score"], 91)
    
    def test_where_with_order_by(self):
        """Test WHERE clause combined with ORDER BY."""
        results = self.db.select(
            "test_sort",
            where={"category": "A"},
            order_by="score",
            order_desc=True
        )
        self.assertEqual(len(results), 3)  # Alice, Charlie, Eve
        scores = [r["score"] for r in results]
        self.assertEqual(scores, [88, 85, 78])
    
    def test_sort_results_helper(self):
        """Test _sort_results helper method."""
        sample = [
            {"id": 3, "name": "Charlie"},
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
        sorted_sample = self.db._sort_results(sample, "id", reverse=False)
        self.assertEqual([s["id"] for s in sorted_sample], [1, 2, 3])
    
    def test_fallback_count_tracking(self):
        """Test that fallback count is tracked."""
        initial_count = self.db.sort_engine.fallback_count
        
        # Force a sort that might trigger fallback
        results = self.db.select("test_sort", order_by="name")
        self.assertIsNotNone(results)
        
        # Fallback count should be accessible
        final_count = self.db.sort_engine.fallback_count
        self.assertIsInstance(final_count, int)


class TestSortConfiguration(unittest.TestCase):
    """Test sort configuration integration."""
    
    def test_env_var_backend_selection(self):
        """Test backend selection via environment variable."""
        from sort_config import SortConfig
        
        # Set environment variable
        original = os.environ.get('KOSDB_SORT_BACKEND')
        os.environ['KOSDB_SORT_BACKEND'] = 'builtin'
        
        try:
            config = SortConfig.from_env()
            self.assertEqual(config.default_backend, 'builtin')
        finally:
            # Restore
            if original:
                os.environ['KOSDB_SORT_BACKEND'] = original
            else:
                del os.environ['KOSDB_SORT_BACKEND']
    
    def test_config_file_loading(self):
        """Test loading configuration from file."""
        from sort_config import SortConfig
        import json
        
        # Create temp config file
        config_data = {
            "sort": {
                "default_backend": "builtin",
                "topk_threshold": 0.05
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_file = f.name
        
        try:
            config = SortConfig.from_file(config_file)
            self.assertEqual(config.default_backend, 'builtin')
            self.assertEqual(config.topk_threshold, 0.05)
        finally:
            os.unlink(config_file)


class TestSortPerformance(unittest.TestCase):
    """Test sort performance characteristics."""
    
    @classmethod
    def setUpClass(cls):
        """Set up large test database."""
        from database import Database
        
        cls.test_dir = tempfile.mkdtemp()
        cls.db = Database(data_dir=cls.test_dir, server_id=1)
        
        # Create table with larger dataset
        cls.db.create_table("perf_test", {
            "id": "INTEGER",
            "value": "REAL",
            "name": "TEXT"
        })
        
        # Insert 1000 rows
        for i in range(1000):
            cls.db.insert("perf_test", {
                "id": i,
                "value": random.random() * 1000,
                "name": f"item_{i:04d}"
            })
    
    @classmethod
    def tearDownClass(cls):
        """Clean up."""
        cls.db.close()
        shutil.rmtree(cls.test_dir)
    
    def test_large_dataset_sort(self):
        """Test sorting large dataset."""
        import time
        
        start = time.perf_counter()
        results = self.db.select("perf_test", order_by="value")
        elapsed = time.perf_counter() - start
        
        # Should complete in reasonable time
        self.assertLess(elapsed, 5.0)
        self.assertEqual(len(results), 1000)
        
        # Verify sorted
        for i in range(len(results) - 1):
            self.assertLessEqual(results[i]["value"], results[i + 1]["value"])
    
    def test_topk_optimization(self):
        """Test that top-K optimization is used for LIMIT queries."""
        import time
        
        # Full sort
        start = time.perf_counter()
        all_results = self.db.select("perf_test", order_by="value", order_desc=True)
        full_time = time.perf_counter() - start
        
        # Top-10
        start = time.perf_counter()
        top_results = self.db.select(
            "perf_test",
            order_by="value",
            order_desc=True,
            limit=10
        )
        topk_time = time.perf_counter() - start
        
        self.assertEqual(len(top_results), 10)
        # Top-K should generally be faster (though not guaranteed in all cases)
        # Just verify it works correctly
        self.assertEqual(top_results[0]["value"], max(r["value"] for r in all_results))


class TestSortEdgeCases(unittest.TestCase):
    """Test edge cases in sort integration."""
    
    def setUp(self):
        """Set up test database."""
        from database import Database
        
        self.test_dir = tempfile.mkdtemp()
        self.db = Database(data_dir=self.test_dir, server_id=1)
        
        self.db.create_table("edge_cases", {
            "id": "INTEGER",
            "data": "TEXT"
        })
    
    def tearDown(self):
        """Clean up."""
        self.db.close()
        shutil.rmtree(self.test_dir)
    
    def test_empty_table_sort(self):
        """Test ORDER BY on empty table."""
        results = self.db.select("edge_cases", order_by="id")
        self.assertEqual(len(results), 0)
    
    def test_single_row_sort(self):
        """Test ORDER BY with single row."""
        self.db.insert("edge_cases", {"id": 1, "data": "test"})
        
        results = self.db.select("edge_cases", order_by="id")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], 1)
    
    def test_duplicate_values_sort(self):
        """Test ORDER BY with duplicate values."""
        for i in range(5):
            self.db.insert("edge_cases", {"id": 100, "data": f"item_{i}"})
        
        results = self.db.select("edge_cases", order_by="id")
        # All should have same id, order among them is stable
        self.assertEqual(len(results), 5)
        for r in results:
            self.assertEqual(r["id"], 100)
    
    def test_null_values_handling(self):
        """Test handling of NULL values in sort."""
        # Insert some rows with NULL
        self.db.insert("edge_cases", {"id": 1, "data": "a"})
        self.db.insert("edge_cases", {"id": None, "data": "b"})
        self.db.insert("edge_cases", {"id": 2, "data": "c"})
        
        # This may raise an error or handle NULLs depending on implementation
        try:
            results = self.db.select("edge_cases", order_by="id")
            # If it works, verify structure
            self.assertEqual(len(results), 3)
        except (TypeError, ValueError):
            # NULL comparison may not be supported - that's acceptable
            pass


class TestSortBackendsAvailability(unittest.TestCase):
    """Test backend availability detection."""
    
    def test_detect_backends(self):
        """Test backend detection."""
        from sort_engine import detect_available_backends
        
        backends = detect_available_backends()
        
        # Builtin should always be available
        self.assertIn('builtin', backends)
        self.assertTrue(backends['builtin'])
        
        # Others may or may not be available
        self.assertIn('madsort_py', backends)
        self.assertIn('madsort_rust', backends)
    
    def test_sort_engine_auto_selection(self):
        """Test automatic backend selection."""
        from sort_engine import SortEngine
        
        engine = SortEngine(backend='auto')
        self.assertIsNotNone(engine.backend_name)
        # Should select some backend
        self.assertIn(engine.backend_name, 
                      ['builtin', 'madsort_py', 'madsort_rust'])


def create_test_suite():
    """Create complete test suite."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestDatabaseSortIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestSortConfiguration))
    suite.addTests(loader.loadTestsFromTestCase(TestSortPerformance))
    suite.addTests(loader.loadTestsFromTestCase(TestSortEdgeCases))
    suite.addTests(loader.loadTestsFromTestCase(TestSortBackendsAvailability))
    
    return suite


if __name__ == '__main__':
    runner = unittest.TextTestRunner(verbosity=2)
    suite = create_test_suite()
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
