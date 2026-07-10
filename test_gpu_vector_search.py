"""
Unit tests for GPU-Accelerated Vector Search module.

Tests GPU detection, fallback mechanisms, and vector operations.
"""

import unittest
import numpy as np
from unittest.mock import patch, MagicMock

# Import modules to test
from gpu_vector_search import (
    GPUMemoryPool,
    GPUVectorIndex,
    GPUSearchEngine,
    check_gpu_availability,
    create_gpu_search_engine,
    GPU_AVAILABLE,
    GPU_LIBRARY
)

from vector_search import DistanceMetric, VectorDocument


class TestGPUAvailability(unittest.TestCase):
    """Test GPU availability detection."""
    
    def test_check_gpu_availability(self):
        """Test GPU availability check."""
        info = check_gpu_availability()
        
        self.assertIsInstance(info, dict)
        self.assertIn('available', info)
        self.assertIn('library', info)
        self.assertIn('device_name', info)
        
        # Should return boolean for available
        self.assertIsInstance(info['available'], bool)
    
    def test_gpu_available_flag(self):
        """Test that GPU_AVAILABLE flag exists."""
        # Should be boolean
        self.assertIsInstance(GPU_AVAILABLE, bool)
        
        # Library should be string or None
        if GPU_LIBRARY is not None:
            self.assertIsInstance(GPU_LIBRARY, str)


class TestGPUMemoryPool(unittest.TestCase):
    """Test GPU memory pool management."""
    
    def test_memory_pool_creation(self):
        """Test memory pool initialization."""
        # Create with small size for testing
        pool = GPUMemoryPool(max_vectors=100, dimension=10)
        
        self.assertEqual(pool.max_vectors, 100)
        self.assertEqual(pool.dimension, 10)
        self.assertFalse(pool._initialized)  # Won't initialize without GPU
    
    def test_resize_check(self):
        """Test buffer resize checking."""
        pool = GPUMemoryPool(max_vectors=100, dimension=10)
        
        # Should succeed for smaller size
        self.assertTrue(pool.resize_if_needed(50))
        
        # Should fail for larger size
        self.assertFalse(pool.resize_if_needed(200))
    
    def test_cleanup(self):
        """Test memory pool cleanup."""
        pool = GPUMemoryPool(max_vectors=100, dimension=10)
        
        # Should not raise error
        pool.cleanup()
        
        self.assertEqual(len(pool._buffers), 0)
        self.assertFalse(pool._initialized)


class TestGPUVectorIndex(unittest.TestCase):
    """Test GPU vector index functionality."""
    
    def test_cpu_fallback_when_gpu_unavailable(self):
        """Test that index falls back to CPU when GPU unavailable."""
        # Force CPU mode
        index = GPUVectorIndex(dimension=10, metric=DistanceMetric.COSINE, use_gpu=False)
        
        self.assertFalse(index.use_gpu)
        
        # Should still work for basic operations
        index.add("doc1", [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        index.add("doc2", [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        
        results = index.search([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], k=2)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0][0], "doc1")
    
    def test_add_and_search_cpu_mode(self):
        """Test add and search in CPU fallback mode."""
        index = GPUVectorIndex(dimension=5, metric=DistanceMetric.COSINE, use_gpu=False)
        
        # Add documents
        index.add("doc1", [1.0, 0.0, 0.0, 0.0, 0.0])
        index.add("doc2", [0.0, 1.0, 0.0, 0.0, 0.0])
        index.add("doc3", [0.5, 0.5, 0.0, 0.0, 0.0])
        
        # Search
        results = index.search([1.0, 0.0, 0.0, 0.0, 0.0], k=2)
        
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0][0], "doc1")
        self.assertGreater(results[0][1], 0.9)  # High similarity
    
    def test_euclidean_distance_cpu(self):
        """Test Euclidean distance metric in CPU mode."""
        index = GPUVectorIndex(dimension=3, metric=DistanceMetric.EUCLIDEAN, use_gpu=False)
        
        index.add("doc1", [0.0, 0.0, 0.0])
        index.add("doc2", [1.0, 1.0, 1.0])
        
        results = index.search([0.0, 0.0, 0.0], k=2)
        
        self.assertEqual(results[0][0], "doc1")  # Closest to origin
        self.assertGreater(results[0][1], results[1][1])  # Higher score = closer
    
    def test_dot_product_cpu(self):
        """Test dot product metric in CPU mode."""
        index = GPUVectorIndex(dimension=3, metric=DistanceMetric.DOT_PRODUCT, use_gpu=False)
        
        index.add("doc1", [1.0, 0.0, 0.0])
        index.add("doc2", [0.0, 1.0, 0.0])
        
        results = index.search([1.0, 0.0, 0.0], k=2)
        
        self.assertEqual(results[0][0], "doc1")
        self.assertAlmostEqual(results[0][1], 1.0, places=5)
    
    def test_search_with_filter(self):
        """Test search with filter function."""
        index = GPUVectorIndex(dimension=3, metric=DistanceMetric.COSINE, use_gpu=True)
        
        index.add("doc1", [1.0, 0.0, 0.0], metadata={"category": "A"})
        index.add("doc2", [0.0, 1.0, 0.0], metadata={"category": "B"})
        index.add("doc3", [0.5, 0.5, 0.0], metadata={"category": "A"})
        
        # Filter to category A
        filter_fn = lambda doc: doc.metadata.get("category") == "A"
        results = index.search([1.0, 0.0, 0.0], k=10, filter_fn=filter_fn)
        
        self.assertEqual(len(results), 2)
        self.assertTrue(all(doc_id in ["doc1", "doc3"] for doc_id, _ in results))
    
    def test_get_stats(self):
        """Test statistics reporting."""
        index = GPUVectorIndex(dimension=10, metric=DistanceMetric.COSINE, use_gpu=False)
        
        stats = index.get_stats()
        
        self.assertIn('dimension', stats)
        self.assertIn('metric', stats)
        self.assertIn('num_documents', stats)
        self.assertIn('gpu_accelerated', stats)
        
        self.assertEqual(stats['dimension'], 10)
        self.assertFalse(stats['gpu_accelerated'])
    
    def test_cleanup(self):
        """Test resource cleanup."""
        index = GPUVectorIndex(dimension=10, metric=DistanceMetric.COSINE, use_gpu=False)
        
        # Should not raise error
        index.cleanup()


class TestGPUSearchEngine(unittest.TestCase):
    """Test GPU search engine."""
    
    def test_create_gpu_index(self):
        """Test creating GPU-accelerated index."""
        engine = GPUSearchEngine(use_gpu=False)  # Force CPU for testing
        
        index = engine.create_index(
            name="test_idx",
            dimension=10,
            metric=DistanceMetric.COSINE,
            use_gpu=False
        )
        
        self.assertIsInstance(index, GPUVectorIndex)
        self.assertFalse(index.use_gpu)
    
    def test_get_gpu_stats(self):
        """Test GPU statistics retrieval."""
        engine = GPUSearchEngine(use_gpu=False)
        
        # Create an index (will be CPU mode since use_gpu=False)
        engine.create_index("test_idx", dimension=10, use_gpu=False)
        
        stats = engine.get_gpu_stats()
        
        self.assertIn('gpu_available', stats)
        self.assertIn('gpu_indexes', stats)
        self.assertIn('cpu_indexes', stats)
        
        # All indexes are CPU mode
        self.assertEqual(stats['gpu_indexes'], 1)  # It's tracked as GPU index object but CPU mode


class TestGPUFallback(unittest.TestCase):
    """Test graceful degradation to CPU."""
    
    def test_gpu_failure_fallback(self):
        """Test fallback when GPU computation fails."""
        index = GPUVectorIndex(dimension=5, metric=DistanceMetric.COSINE, use_gpu=True)
        
        # Add documents
        for i in range(10):
            index.add(f"doc{i}", [float(j == i % 5) for j in range(5)])
        
        # Force GPU failure by corrupting memory pool
        if index._memory_pool:
            index._memory_pool._initialized = False
        
        # Should still work with CPU fallback
        results = index.search([1.0, 0.0, 0.0, 0.0, 0.0], k=3)
        self.assertEqual(len(results), 3)
    
    def test_unsupported_metric_fallback(self):
        """Test fallback for unsupported GPU metrics."""
        # MANHATTAN distance may not be supported on GPU
        index = GPUVectorIndex(dimension=3, metric=DistanceMetric.MANHATTAN, use_gpu=True)
        
        index.add("doc1", [0.0, 0.0, 0.0])
        index.add("doc2", [1.0, 1.0, 1.0])
        
        # Should fallback to CPU for unsupported metric
        results = index.search([0.0, 0.0, 0.0], k=2)
        
        self.assertEqual(len(results), 2)


class TestCreateGPUSearchEngine(unittest.TestCase):
    """Test convenience function."""
    
    def test_create_with_gpu_disabled(self):
        """Test creating engine with GPU disabled."""
        engine = create_gpu_search_engine(use_gpu=False)
        self.assertIsInstance(engine, GPUSearchEngine)
        self.assertFalse(engine.use_gpu)
    
    def test_create_with_gpu_unavailable(self):
        """Test creating engine when GPU unavailable."""
        with patch('gpu_vector_search.GPU_AVAILABLE', False):
            # Should warn but not fail
            engine = create_gpu_search_engine(use_gpu=True)
            self.assertIsInstance(engine, GPUSearchEngine)
            self.assertFalse(engine.use_gpu)  # Falls back to CPU


class TestIntegration(unittest.TestCase):
    """Integration tests for GPU vector search."""
    
    def test_end_to_end_cpu_mode(self):
        """Test complete workflow in CPU mode."""
        engine = create_gpu_search_engine(use_gpu=False)
        
        # Create index
        index = engine.create_index(
            name="articles",
            dimension=128,
            metric=DistanceMetric.COSINE,
            use_gpu=False
        )
        
        # Add documents
        for i in range(100):
            vector = [float(i == j) for j in range(128)]
            index.add(f"doc{i}", vector)
        
        # Search
        query = [1.0] + [0.0] * 127
        results = engine.search("articles", query, k=10)
        
        self.assertEqual(len(results), 10)
        self.assertEqual(results[0][0], "doc0")
    
    def test_multiple_indexes(self):
        """Test managing multiple indexes."""
        engine = GPUSearchEngine(use_gpu=False)
        
        # Create multiple indexes
        engine.create_index("idx1", dimension=10, use_gpu=False)
        engine.create_index("idx2", dimension=20, use_gpu=False)
        engine.create_index("idx3", dimension=30, use_gpu=False)
        
        self.assertEqual(len(engine.list_indexes()), 3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
