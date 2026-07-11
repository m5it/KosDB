"""
GPU-Accelerated Vector Operations for KosDB

Provides CUDA-accelerated vector similarity search with CPU fallback.
Supports batch operations and GPU memory management.
"""

import math
import sys
from typing import List, Optional, Tuple, Dict, Any, Union
from dataclasses import dataclass
import threading


# Try to import CUDA libraries
try:
    import cupy as cp
    import cupy.cuda.runtime as cuda_runtime
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


@dataclass
class GPUConfig:
    """Configuration for GPU operations."""
    enabled: bool = True
    device_id: int = 0
    memory_limit_mb: Optional[int] = None  # None = use all available
    batch_size: int = 1000
    use_mixed_precision: bool = False  # Use float16 for memory efficiency
    
    def __post_init__(self):
        if not CUDA_AVAILABLE:
            self.enabled = False


class GPUVectorOps:
    """
    GPU-accelerated vector operations with CPU fallback.
    """
    
    def __init__(self, config: Optional[GPUConfig] = None):
        self.config = config or GPUConfig()
        self._lock = threading.RLock()
        
        # GPU state
        self._gpu_available = CUDA_AVAILABLE and self.config.enabled
        self._device = None
        self._memory_pool = None
        
        if self._gpu_available:
            self._initialize_gpu()
    
    def _initialize_gpu(self):
        """Initialize GPU device."""
        try:
            with self._lock:
                # Set device
                cp.cuda.Device(self.config.device_id).use()
                self._device = cp.cuda.Device(self.config.device_id)
                
                # Create memory pool if limit specified
                if self.config.memory_limit_mb:
                    mem_limit = self.config.memory_limit_mb * 1024 * 1024
                    self._memory_pool = cp.cuda.MemoryPool(cp.cuda.malloc_managed)
                    self._memory_pool.set_limit(size=mem_limit)
                    cp.cuda.set_allocator(self._memory_pool.malloc)
                
                print(f"[GPU] Initialized CUDA device {self.config.device_id}: {self._device.name}")
                
        except Exception as e:
            print(f"[GPU] Failed to initialize GPU: {e}")
            self._gpu_available = False
    
    @property
    def is_available(self) -> bool:
        """Check if GPU is available."""
        return self._gpu_available
    
    def get_device_info(self) -> Dict[str, Any]:
        """Get GPU device information."""
        if not self._gpu_available:
            return {'available': False}
        
        try:
            with self._lock:
                mem_info = cp.cuda.runtime.memGetInfo()
                return {
                    'available': True,
                    'device_id': self.config.device_id,
                    'name': self._device.name if self._device else 'unknown',
                    'total_memory': mem_info[1],
                    'free_memory': mem_info[0],
                    'memory_limit_mb': self.config.memory_limit_mb,
                    'batch_size': self.config.batch_size,
                    'use_mixed_precision': self.config.use_mixed_precision
                }
        except Exception as e:
            return {'available': False, 'error': str(e)}
    
    def to_gpu(self, data: Union[List, 'cp.ndarray']) -> Optional['cp.ndarray']:
        """
        Transfer data to GPU.
        
        Args:
            data: List or numpy array to transfer
        
        Returns:
            CuPy array on GPU or None if failed
        """
        if not self._gpu_available:
            return None
        
        try:
            with self._lock:
                if isinstance(data, list):
                    return cp.array(data, dtype=cp.float32)
                elif isinstance(data, cp.ndarray):
                    return data
                else:
                    # Assume numpy array
                    return cp.asarray(data, dtype=cp.float32)
        except Exception as e:
            print(f"[GPU] Failed to transfer to GPU: {e}")
            return None
    
    def to_cpu(self, gpu_array: 'cp.ndarray') -> List[float]:
        """
        Transfer data from GPU to CPU.
        
        Args:
            gpu_array: CuPy array on GPU
        
        Returns:
            List of floats
        """
        if gpu_array is None:
            return []
        
        try:
            return cp.asnumpy(gpu_array).tolist()
        except Exception as e:
            print(f"[GPU] Failed to transfer to CPU: {e}")
            return []
    
    def cosine_similarity_batch(self, 
                                 query: List[float], 
                                 vectors: List[List[float]]) -> List[float]:
        """
        Compute cosine similarity between query and multiple vectors (batch).
        
        Args:
            query: Query vector
            vectors: List of vectors to compare
        
        Returns:
            List of similarity scores
        """
        if not self._gpu_available or len(vectors) == 0:
            # Fallback to CPU
            return self._cosine_similarity_cpu(query, vectors)
        
        try:
            with self._lock:
                # Convert to GPU arrays
                query_gpu = self.to_gpu(query)
                vectors_gpu = self.to_gpu(vectors)
                
                if query_gpu is None or vectors_gpu is None:
                    return self._cosine_similarity_cpu(query, vectors)
                
                # Compute norms
                query_norm = cp.linalg.norm(query_gpu)
                vector_norms = cp.linalg.norm(vectors_gpu, axis=1)
                
                # Compute dot products
                dot_products = cp.dot(vectors_gpu, query_gpu)
                
                # Compute cosine similarity
                similarities = dot_products / (vector_norms * query_norm)
                
                # Transfer back to CPU
                return cp.asnumpy(similarities).tolist()
                
        except Exception as e:
            print(f"[GPU] Batch similarity failed, using CPU: {e}")
            return self._cosine_similarity_cpu(query, vectors)
    
    def _cosine_similarity_cpu(self, 
                                 query: List[float], 
                                 vectors: List[List[float]]) -> List[float]:
        """CPU fallback for cosine similarity."""
        results = []
        query_norm = math.sqrt(sum(x * x for x in query))
        
        for vec in vectors:
            vec_norm = math.sqrt(sum(x * x for x in vec))
            if query_norm == 0 or vec_norm == 0:
                results.append(0.0)
            else:
                dot = sum(a * b for a, b in zip(query, vec))
                results.append(dot / (query_norm * vec_norm))
        
        return results
    
    def euclidean_distance_batch(self, 
                                  query: List[float], 
                                  vectors: List[List[float]]) -> List[float]:
        """
        Compute Euclidean distance between query and multiple vectors (batch).
        
        Args:
            query: Query vector
            vectors: List of vectors to compare
        
        Returns:
            List of distances
        """
        if not self._gpu_available or len(vectors) == 0:
            return self._euclidean_distance_cpu(query, vectors)
        
        try:
            with self._lock:
                query_gpu = self.to_gpu(query)
                vectors_gpu = self.to_gpu(vectors)
                
                if query_gpu is None or vectors_gpu is None:
                    return self._euclidean_distance_cpu(query, vectors)
                
                # Compute squared differences
                diff = vectors_gpu - query_gpu
                
                # Sum of squares along axis 1
                distances = cp.sqrt(cp.sum(diff ** 2, axis=1))
                
                return cp.asnumpy(distances).tolist()
                
        except Exception as e:
            print(f"[GPU] Batch distance failed, using CPU: {e}")
            return self._euclidean_distance_cpu(query, vectors)
    
    def _euclidean_distance_cpu(self, 
                                  query: List[float], 
                                  vectors: List[List[float]]) -> List[float]:
        """CPU fallback for Euclidean distance."""
        return [math.sqrt(sum((a - b) ** 2 for a, b in zip(query, vec))) 
                for vec in vectors]
    
    def dot_product_batch(self, 
                          query: List[float], 
                          vectors: List[List[float]]) -> List[float]:
        """
        Compute dot product between query and multiple vectors (batch).
        
        Args:
            query: Query vector
            vectors: List of vectors to compare
        
        Returns:
            List of dot products
        """
        if not self._gpu_available or len(vectors) == 0:
            return [sum(a * b for a, b in zip(query, vec)) for vec in vectors]
        
        try:
            with self._lock:
                query_gpu = self.to_gpu(query)
                vectors_gpu = self.to_gpu(vectors)
                
                if query_gpu is None or vectors_gpu is None:
                    return [sum(a * b for a, b in zip(query, vec)) for vec in vectors]
                
                dot_products = cp.dot(vectors_gpu, query_gpu)
                return cp.asnumpy(dot_products).tolist()
                
        except Exception as e:
            print(f"[GPU] Batch dot product failed, using CPU: {e}")
            return [sum(a * b for a, b in zip(query, vec)) for vec in vectors]
    
    def batch_normalize(self, vectors: List[List[float]]) -> List[List[float]]:
        """
        Normalize vectors to unit length (batch).
        
        Args:
            vectors: List of vectors to normalize
        
        Returns:
            List of normalized vectors
        """
        if not self._gpu_available or len(vectors) == 0:
            return [self._normalize_cpu(v) for v in vectors]
        
        try:
            with self._lock:
                vectors_gpu = self.to_gpu(vectors)
                if vectors_gpu is None:
                    return [self._normalize_cpu(v) for v in vectors]
                
                # Compute norms
                norms = cp.linalg.norm(vectors_gpu, axis=1, keepdims=True)
                
                # Avoid division by zero
                norms = cp.where(norms == 0, 1, norms)
                
                # Normalize
                normalized = vectors_gpu / norms
                
                return cp.asnumpy(normalized).tolist()
                
        except Exception as e:
            print(f"[GPU] Batch normalize failed, using CPU: {e}")
            return [self._normalize_cpu(v) for v in vectors]
    
    def _normalize_cpu(self, vector: List[float]) -> List[float]:
        """CPU normalize."""
        norm = math.sqrt(sum(x * x for x in vector))
        if norm == 0:
            return vector
        return [x / norm for x in vector]
    
    def kmeans_cluster(self, 
                       vectors: List[List[float]], 
                       k: int, 
                       max_iters: int = 10) -> Tuple[List[List[float]], List[int]]:
        """
        K-means clustering on GPU.
        
        Args:
            vectors: List of vectors
            k: Number of clusters
            max_iters: Maximum iterations
        
        Returns:
            Tuple of (centroids, cluster_assignments)
        """
        if not self._gpu_available or len(vectors) < k:
            # Fallback to CPU
            return self._kmeans_cpu(vectors, k, max_iters)
        
        try:
            with self._lock:
                data = self.to_gpu(vectors)
                if data is None:
                    return self._kmeans_cpu(vectors, k, max_iters)
                
                n_samples = data.shape[0]
                
                # Random initialization
                indices = cp.random.choice(n_samples, k, replace=False)
                centroids = data[indices]
                
                for _ in range(max_iters):
                    # Compute distances to centroids
                    distances = cp.sqrt(
                        cp.sum((data[:, cp.newaxis] - centroids) ** 2, axis=2)
                    )
                    
                    # Assign to nearest centroid
                    labels = cp.argmin(distances, axis=1)
                    
                    # Update centroids
                    new_centroids = cp.array([
                        data[labels == i].mean(axis=0) if cp.sum(labels == i) > 0 
                        else centroids[i]
                        for i in range(k)
                    ])
                    
                    centroids = new_centroids
                
                return cp.asnumpy(centroids).tolist(), cp.asnumpy(labels).tolist()
                
        except Exception as e:
            print(f"[GPU] K-means failed, using CPU: {e}")
            return self._kmeans_cpu(vectors, k, max_iters)
    
    def _kmeans_cpu(self, 
                    vectors: List[List[float]], 
                    k: int, 
                    max_iters: int) -> Tuple[List[List[float]], List[int]]:
        """CPU fallback for k-means."""
        import random
        
        # Random initialization
        centroids = random.sample(vectors, k)
        labels = [0] * len(vectors)
        
        for _ in range(max_iters):
            # Assign to nearest centroid
            new_labels = []
            for vec in vectors:
                distances = [
                    math.sqrt(sum((a - b) ** 2 for a, b in zip(vec, cent)))
                    for cent in centroids
                ]
                new_labels.append(distances.index(min(distances)))
            
            labels = new_labels
            
            # Update centroids
            for i in range(k):
                cluster_vectors = [v for j, v in enumerate(vectors) if labels[j] == i]
                if cluster_vectors:
                    dim = len(cluster_vectors[0])
                    centroids[i] = [
                        sum(v[d] for v in cluster_vectors) / len(cluster_vectors)
                        for d in range(dim)
                    ]
        
        return centroids, labels
    
    def cleanup(self):
        """Free GPU memory."""
        if self._gpu_available:
            try:
                cp.get_default_memory_pool().free_all_blocks()
                print("[GPU] Memory cleaned up")
            except Exception as e:
                print(f"[GPU] Cleanup error: {e}")


# Global GPU operations instance
_global_gpu_ops: Optional[GPUVectorOps] = None


def get_gpu_ops(config: Optional[GPUConfig] = None) -> GPUVectorOps:
    """Get or create global GPU operations instance."""
    global _global_gpu_ops
    if _global_gpu_ops is None:
        _global_gpu_ops = GPUVectorOps(config)
    return _global_gpu_ops


def configure_gpu(enabled: bool = True,
                  device_id: int = 0,
                  memory_limit_mb: Optional[int] = None,
                  batch_size: int = 1000) -> GPUVectorOps:
    """Configure GPU with settings."""
    config = GPUConfig(
        enabled=enabled,
        device_id=device_id,
        memory_limit_mb=memory_limit_mb,
        batch_size=batch_size
    )
    return get_gpu_ops(config)


def check_cuda_available() -> bool:
    """Check if CUDA is available."""
    return CUDA_AVAILABLE


def get_cuda_version() -> Optional[str]:
    """Get CUDA version if available."""
    if not CUDA_AVAILABLE:
        return None
    try:
        return cp.cuda.runtime.getDeviceCount()
    except:
        return None
