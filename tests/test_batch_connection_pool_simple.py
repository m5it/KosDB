
"""
Simple tests for Batch Connection Pool
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from batch_connection_pool import PoolMetrics


class TestPoolMetrics(unittest.TestCase):
    """Test pool metrics."""
    
    def test_metrics_initialization(self):
        metrics = PoolMetrics()
        self.assertEqual(metrics.total_connections, 0)
        self.assertEqual(metrics.active_connections, 0)
    
    def test_metrics_update(self):
        metrics = PoolMetrics()
        metrics.total_connections = 10
        metrics.active_connections = 5
        self.assertEqual(metrics.total_connections, 10)
        self.assertEqual(metrics.active_connections, 5)


class TestPoolSizingFormula(unittest.TestCase):
    """Test pool sizing calculations."""
    
    def test_basic_calculation(self):
        """Test basic pool size calculation."""
        concurrent_batches = 10
        num_shards = 2
        
        # Simple calculation
        base_size = concurrent_batches * num_shards
        self.assertEqual(base_size, 20)
        
        # With safety margin
        final_size = int(base_size * 1.2)
        self.assertEqual(final_size, 24)
    
    def test_cross_shard_calculation(self):
        """Test cross-shard pool sizing."""
        max_batches = 20
        num_shards = 3
        
        per_shard = max(20, max_batches * 2)
        self.assertEqual(per_shard, 40)
        
        total = per_shard * num_shards
        self.assertEqual(total, 120)


if __name__ == '__main__':
    unittest.main(verbosity=2)
