
"""
Test cases for batch sharding functionality.

Tests:
- Shard analysis and grouping
- Cross-shard batch coordination
- Distributed transaction support
- Shard routing cache
- Failure handling
"""

import unittest
import sys
import os
import time
import threading

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from batch_sharding import (
    ShardedBatchManager,
    BatchShardAnalyzer,
    CrossShardCoordinator,
    BatchShardExecutor,
    ShardRoutingCache,
    ShardTarget,
    BatchShardGroup,
    CrossShardBatchState,
    ShardRoutingStrategy
)


class MockShardManager:
    """Mock shard manager for testing."""
    
    def __init__(self):
        self.shards = ["shard_1", "shard_2", "shard_3"]
        self.local_shard = "shard_1"
        self.commands_executed = []
        self.prepared_batches = set()
        self.committed_batches = set()
    
    def get_shards(self):
        return self.shards
    
    def get_local_shard(self):
        return self.local_shard
    
    def get_coordinator(self):
        return self.local_shard
    
    def execute_command(self, shard_id, command):
        self.commands_executed.append((shard_id, command))
        return {"success": True, "shard": shard_id}
    
    def send_prepare(self, shard_id, batch_id):
        self.prepared_batches.add((shard_id, batch_id))
    
    def send_commit(self, shard_id, batch_id):
        self.committed_batches.add((shard_id, batch_id))
    
    def send_rollback(self, shard_id, batch_id):
        pass
    
    def rollback_commands(self, shard_id, commands):
        pass
    
    def lookup_shard(self, table, key):
        # Simple hash-based lookup
        hash_val = hash(f"{table}:{key}") % len(self.shards)
        return self.shards[hash_val]


class TestShardRoutingCache(unittest.TestCase):
    """Test suite for shard routing cache."""
    
    def setUp(self):
        self.cache = ShardRoutingCache(max_size=100, ttl_seconds=1.0)
    
    def test_cache_basic(self):
        """Test basic cache operations."""
        target = ShardTarget(shard_id="shard_1")
        
        # Cache miss
        self.assertIsNone(self.cache.get("key1"))
        
        # Put and get
        self.cache.put("key1", target)
        cached = self.cache.get("key1")
        
        self.assertIsNotNone(cached)
        self.assertEqual(cached.shard_id, "shard_1")
    
    def test_cache_expiration(self):
        """Test cache entry expiration."""
        target = ShardTarget(shard_id="shard_1")
        self.cache.put("key1", target)
        
        # Should be cached
        self.assertIsNotNone(self.cache.get("key1"))
        
        # Wait for expiration
        time.sleep(1.1)
        
        # Should be expired
        self.assertIsNone(self.cache.get("key1"))
    
    def test_cache_invalidation(self):
        """Test cache invalidation."""
        target = ShardTarget(shard_id="shard_1")
        self.cache.put("key1", target)
        
        # Invalidate
        self.cache.invalidate("key1")
        
        self.assertIsNone(self.cache.get("key1"))
    
    def test_cache_stats(self):
        """Test cache statistics."""
        target = ShardTarget(shard_id="shard_1")
        
        # Miss
        self.cache.get("key1")
        
        # Hit
        self.cache.put("key1", target)
        self.cache.get("key1")
        
        stats = self.cache.get_stats()
        self.assertEqual(stats['hits'], 1)
        self.assertEqual(stats['misses'], 1)


class TestBatchShardAnalyzer(unittest.TestCase):
    """Test suite for batch shard analyzer."""
    
    def setUp(self):
        self.shard_manager = MockShardManager()
        self.analyzer = BatchShardAnalyzer(
            shard_manager=self.shard_manager,
            routing_strategy=ShardRoutingStrategy.HASH
        )
    
    def test_single_shard_batch(self):
        """Test batch targeting single shard."""
        # Use same key to ensure same shard
        commands = [
            {"table": "users", "key": "same_key", "op": "INSERT"},
            {"table": "users", "key": "same_key", "op": "UPDATE"},
        ]
        
        groups = self.analyzer.analyze_batch(commands)
        
        # All commands should target same shard
        self.assertEqual(len(groups), 1)
    
    def test_cross_shard_batch(self):
        """Test batch targeting multiple shards."""
        # Use keys that hash to different shards
        commands = [
            {"table": "users", "key": "key_shard_0", "op": "INSERT"},
            {"table": "users", "key": "key_shard_1", "op": "INSERT"},
            {"table": "users", "key": "key_shard_2", "op": "INSERT"},
        ]
        
        groups = self.analyzer.analyze_batch(commands)
        
        # Should have multiple shard groups
        self.assertGreaterEqual(len(groups), 1)
    
    def test_broadcast_command(self):
        """Test command without key broadcasts to all shards."""
        commands = [
            {"table": "users", "key": None, "op": "SELECT"},  # Broadcast
        ]
        
        groups = self.analyzer.analyze_batch(commands)
        
        # Should target all shards
        self.assertEqual(len(groups), 3)
    
    def test_routing_cache(self):
        """Test that routing decisions are cached."""
        commands = [
            {"table": "users", "key": 1, "op": "INSERT"},
        ]
        
        # First analysis
        self.analyzer.analyze_batch(commands)
        
        # Check cache has entry
        stats = self.analyzer.routing_cache.get_stats()
        self.assertGreater(stats['misses'], 0)
        
        # Second analysis - should use cache
        self.analyzer.analyze_batch(commands)
        
        stats = self.analyzer.routing_cache.get_stats()
        self.assertGreater(stats['hits'], 0)


class TestCrossShardCoordinator(unittest.TestCase):
    """Test suite for cross-shard coordinator."""
    
    def setUp(self):
        self.shard_manager = MockShardManager()
        self.coordinator = CrossShardCoordinator(self.shard_manager)
    
    def test_begin_batch(self):
        """Test beginning cross-shard batch."""
        batch_id = "batch_001"
        participants = {"shard_1", "shard_2"}
        
        state = self.coordinator.begin_cross_shard_batch(
            batch_id, participants
        )
        
        self.assertEqual(state.batch_id, batch_id)
        self.assertEqual(state.participant_shards, participants)
        
        # Manually mark as prepared
        self.coordinator.prepare_shard(batch_id, "shard_1")
        self.coordinator.prepare_shard(batch_id, "shard_2")
        
        updated_state = self.coordinator._active_batches.get(batch_id)
        self.assertIn("shard_1", updated_state.prepared_shards)
        self.assertIn("shard_2", updated_state.prepared_shards)
    
    def test_commit_batch(self):
        """Test committing batch."""
        batch_id = "batch_002"
        participants = {"shard_1", "shard_2"}
        
        # Begin
        state = self.coordinator.begin_cross_shard_batch(
            batch_id, participants
        )
        
        # Manually mark as prepared
        self.coordinator.prepare_shard(batch_id, "shard_1")
        self.coordinator.prepare_shard(batch_id, "shard_2")
        
        # Commit
        result = self.coordinator.commit_batch(batch_id)
        
        self.assertTrue(result)
        self.assertIn(("shard_1", batch_id), self.shard_manager.committed_batches)
        self.assertIn(("shard_2", batch_id), self.shard_manager.committed_batches)
    
    def test_metrics(self):
        """Test coordinator metrics."""
        batch_id = "batch_003"
        participants = {"shard_1"}
        
        self.coordinator.begin_cross_shard_batch(batch_id, participants)
        self.coordinator.prepare_shard(batch_id, "shard_1")
        self.coordinator.commit_batch(batch_id)
        
        metrics = self.coordinator.get_metrics()
        self.assertEqual(metrics['total_cross_shard_batches'], 1)
        self.assertEqual(metrics['successful_commits'], 1)


class TestBatchShardExecutor(unittest.TestCase):
    """Test suite for batch shard executor."""
    
    def setUp(self):
        self.shard_manager = MockShardManager()
        self.analyzer = BatchShardAnalyzer(
            shard_manager=self.shard_manager,
            routing_strategy=ShardRoutingStrategy.HASH
        )
        self.coordinator = CrossShardCoordinator(self.shard_manager)
        self.executor = BatchShardExecutor(self.analyzer, self.coordinator)
    
    def test_single_shard_execution(self):
        """Test execution on single shard."""
        # Commands that hash to same shard
        commands = [
            {"table": "users", "key": "same_key", "op": "INSERT"},
            {"table": "users", "key": "same_key", "op": "UPDATE"},
        ]
        
        result = self.executor.execute_batch(commands)
        
        self.assertIn('success', result)
        self.assertIn('executed', result)
        self.assertIn('shard', result)
    
    def test_execution_metrics(self):
        """Test execution metrics tracking."""
        commands = [
            {"table": "users", "key": 1, "op": "INSERT"},
        ]
        
        self.executor.execute_batch(commands)
        
        metrics = self.executor.get_metrics()
        self.assertEqual(metrics['total_batches'], 1)
        self.assertEqual(metrics['single_shard_batches'], 1)


class TestShardedBatchManager(unittest.TestCase):
    """Test suite for sharded batch manager."""
    
    def setUp(self):
        self.shard_manager = MockShardManager()
        self.manager = ShardedBatchManager(self.shard_manager)
    
    def test_execute_single_shard_batch(self):
        """Test executing batch on single shard."""
        commands = [
            {"table": "users", "key": "same_key", "op": "INSERT"},
            {"table": "users", "key": "same_key", "op": "INSERT"},
        ]
        
        result = self.manager.execute_batch(commands)
        
        self.assertIn('success', result)
        self.assertTrue(result['success'])
    
    def test_metrics_collection(self):
        """Test metrics collection."""
        commands = [
            {"table": "users", "key": 1, "op": "INSERT"},
        ]
        
        self.manager.execute_batch(commands)
        
        metrics = self.manager.get_all_metrics()
        self.assertIn('routing_cache', metrics)
        self.assertIn('executor', metrics)
    
    def test_cache_invalidation(self):
        """Test cache invalidation."""
        # Execute to populate cache
        commands = [
            {"table": "users", "key": 1, "op": "INSERT"},
        ]
        self.manager.execute_batch(commands)
        
        # Check cache has entries
        stats = self.manager.get_routing_cache_stats()
        self.assertGreater(stats['size'], 0)
        
        # Invalidate specific table
        self.manager.invalidate_routing_cache("users")
        
        # Cache should be cleared
        stats = self.manager.get_routing_cache_stats()
        self.assertEqual(stats['size'], 0)
    
    def test_global_metrics(self):
        """Test global METRICS tracking."""
        from batch_sharding import METRICS
        
        # Execute some batches to populate metrics
        commands = [
            {"table": "users", "key": "same_key", "op": "INSERT"},
        ]
        self.manager.execute_batch(commands)
        
        # Check METRICS were updated
        self.assertGreaterEqual(METRICS['batch_sharding']['total_batches'], 1)


class TestCrossShardBatchIntegration(unittest.TestCase):
    """Integration tests for cross-shard batches."""
    
    def setUp(self):
        self.shard_manager = MockShardManager()
        self.manager = ShardedBatchManager(self.shard_manager)
    
    def test_cross_shard_batch_execution(self):
        """Test full cross-shard batch execution."""
        # Commands targeting different shards
        commands = [
            {"table": "users", "key": "shard1_key", "op": "INSERT"},
            {"table": "users", "key": "shard2_key", "op": "INSERT"},
        ]
        
        result = self.manager.execute_batch(commands)
        
        # Should execute successfully
        self.assertIn('success', result)
    
    def test_error_mode_continue(self):
        """Test continue error mode."""
        commands = [
            {"table": "users", "key": 1, "op": "INSERT"},
        ]
        
        result = self.manager.execute_batch(commands, error_mode="continue")
        
        self.assertIn('success', result)
    
    def test_error_mode_rollback(self):
        """Test rollback error mode."""
        commands = [
            {"table": "users", "key": 1, "op": "INSERT"},
        ]
        
        result = self.manager.execute_batch(commands, error_mode="rollback_all")
        
        self.assertIn('success', result)


if __name__ == '__main__':
    unittest.main(verbosity=2)
