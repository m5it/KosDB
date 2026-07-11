"""
Tests for GPU-accelerated vector operations.
"""

import unittest
import math
from gpu_vector_ops import (
    GPUConfig, GPUVectorOps, 
    get_gpu_ops, configure_gpu, check_cuda_available
)

class TestGPUConfig(unittest.TestCase):
    def test_default_config(self):
        config = GPUConfig()
        # When CUDA unavailable, config.enabled may be False after post_init
        # Just verify the structure is correct
        self.assertEqual(config.device_id, 0)
        self.assertIsNone(config.memory_limit_mb)
        self.assertEqual(config.batch_size, 1000)
        self.assertFalse(config.use_mixed_precision)
    def test_config_without_cuda(self):
        # Test config behavior when CUDA unavailable
        config = GPUConfig(enabled=True)
        # When CUDA unavailable, post_init sets enabled=False
        self.assertFalse(config.enabled)

class TestGPUVectorOps(unittest.TestCase):
    def setUp(self):
        self.config = GPUConfig(enabled=False)  # Start disabled for tests
        self.ops = GPUVectorOps(self.config)
    
    def test_is_available_disabled(self):
        self.assertFalse(self.ops.is_available)
    
    def test_get_device_info_disabled(self):
        info = self.ops.get_device_info()
        self.assertEqual(info['available'], False)
    
    def test_cosine_similarity_cpu_fallback(self):
        query = [1.0, 0.0, 0.0]
        vectors = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0]
        ]
        
        results = self.ops.cosine_similarity_batch(query, vectors)
        
        self.assertEqual(len(results), 3)
        self.assertAlmostEqual(results[0], 1.0, places=5)
        self.assertAlmostEqual(results[1], 0.0, places=5)
        self.assertAlmostEqual(results[2], 0.0, places=5)
    
    def test_euclidean_distance_cpu_fallback(self):
        query = [0.0, 0.0]
        vectors = [
            [3.0, 4.0],
            [0.0, 0.0]
        ]
        
        results = self.ops.euclidean_distance_batch(query, vectors)
        
        self.assertEqual(len(results), 2)
        self.assertAlmostEqual(results[0], 5.0, places=5)
        self.assertAlmostEqual(results[1], 0.0, places=5)
    
    def test_dot_product_cpu_fallback(self):
        query = [1.0, 2.0, 3.0]
        vectors = [
            [4.0, 5.0, 6.0]
        ]
        
        results = self.ops.dot_product_batch(query, vectors)
        
        self.assertEqual(len(results), 1)
        self.assertAlmostEqual(results[0], 32.0, places=5)
    
    def test_batch_normalize_cpu_fallback(self):
        vectors = [
            [3.0, 4.0],
            [1.0, 0.0]
        ]
        
        results = self.ops.batch_normalize(vectors)
        
        self.assertEqual(len(results), 2)
        # Check first vector is normalized
        norm = math.sqrt(results[0][0]**2 + results[0][1]**2)
        self.assertAlmostEqual(norm, 1.0, places=5)
    
    def test_kmeans_cpu_fallback(self):
        vectors = [
            [1.0, 1.0],
            [1.1, 1.1],
            [5.0, 5.0],
            [5.1, 5.1]
        ]
        
        centroids, labels = self.ops.kmeans_cluster(vectors, k=2, max_iters=5)
        
        self.assertEqual(len(centroids), 2)
        self.assertEqual(len(labels), 4)
        # Points 0,1 should be in same cluster; 2,3 in same cluster
        self.assertEqual(labels[0], labels[1])
        self.assertEqual(labels[2], labels[3])
        self.assertNotEqual(labels[0], labels[2])
    
    def test_empty_vectors(self):
        results = self.ops.cosine_similarity_batch([1.0, 0.0], [])
        self.assertEqual(results, [])
        
        results = self.ops.euclidean_distance_batch([1.0, 0.0], [])
        self.assertEqual(results, [])
    
    def test_to_gpu_returns_none_when_disabled(self):
        result = self.ops.to_gpu([1.0, 2.0, 3.0])
        self.assertIsNone(result)
    
    def test_to_cpu_with_none(self):
        result = self.ops.to_cpu(None)
        self.assertEqual(result, [])


@unittest.skipUnless(check_cuda_available(), "CUDA not available")
class TestGPUVectorOpsWithCUDA(unittest.TestCase):
    """Tests that require CUDA."""
    
    def setUp(self):
        self.config = GPUConfig(enabled=True)
        self.ops = GPUVectorOps(self.config)
    
    def test_is_available_with_cuda(self):
        self.assertTrue(self.ops.is_available)
    
    def test_get_device_info_with_cuda(self):
        info = self.ops.get_device_info()
        self.assertTrue(info['available'])
        self.assertIn('name', info)
        self.assertIn('total_memory', info)
    
    def test_to_gpu_and_back(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        gpu_array = self.ops.to_gpu(data)
        self.assertIsNotNone(gpu_array)
        
        back = self.ops.to_cpu(gpu_array)
        self.assertEqual(len(back), 5)
        for i, val in enumerate(back):
            self.assertAlmostEqual(val, data[i], places=5)
    
    def test_cosine_similarity_gpu(self):
        query = [1.0, 0.0, 0.0]
        vectors = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        
        results = self.ops.cosine_similarity_batch(query, vectors)
        
        self.assertEqual(len(results), 2)
        self.assertAlmostEqual(results[0], 1.0, places=5)
        self.assertAlmostEqual(results[1], 0.0, places=5)
    
    def test_batch_normalize_gpu(self):
        vectors = [[3.0, 4.0], [0.0, 5.0]]
        
        results = self.ops.batch_normalize(vectors)
        
        self.assertEqual(len(results), 2)
        for vec in results:
            norm = math.sqrt(sum(x*x for x in vec))
            self.assertAlmostEqual(norm, 1.0, places=5)


class TestGlobalGPUOps(unittest.TestCase):
    def test_get_gpu_ops_singleton(self):
        import gpu_vector_ops
        gpu_vector_ops._global_gpu_ops = None
        
        ops1 = get_gpu_ops()
        ops2 = get_gpu_ops()
        
        self.assertIs(ops1, ops2)
    
    def test_configure_gpu(self):
        ops = configure_gpu(enabled=False, device_id=1, batch_size=500)
        
        self.assertEqual(ops.config.device_id, 1)
        self.assertEqual(ops.config.batch_size, 500)
    
    def test_check_cuda_available(self):
        result = check_cuda_available()
        self.assertIsInstance(result, bool)


if __name__ == '__main__':
    unittest.main(verbosity=2)
