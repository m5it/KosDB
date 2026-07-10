"""
GPU-Accelerated Vector Search for KosDB

Provides GPU-accelerated similarity search using CUDA via cupy or pycuda.
Falls back to CPU implementation when GPU is unavailable.
"""

import os
import sys
import logging
import threading
from typing import Dict, Any, List, Optional, Tuple, Callable, Union
from enum import Enum, auto
from dataclasses import dataclass, field

# Import CPU vector search for fallback
from vector_search import VectorIndex, VectorDocument, DistanceMetric, VectorSearchEngine

# Configure logging
logger = logging.getLogger(__name__)

# GPU library detection
GPU_AVAILABLE = False
GPU_LIBRARY = None

try:
    import cupy as cp
    GPU_AVAILABLE = True
    GPU_LIBRARY = 'cupy'
    logger.info("[GPU] Using CuPy for GPU acceleration")
except ImportError:
    try:
        import pycuda.driver as cuda
        import pycuda.autoinit
        from pycuda.compiler import SourceModule
        GPU_AVAILABLE = True
        GPU_LIBRARY = 'pycuda'
        logger.info("[GPU] Using PyCUDA for GPU acceleration")
    except ImportError:
        logger.info("[GPU] GPU libraries not available. Using CPU fallback.")

# CUDA kernel for cosine similarity (if using PyCUDA)
COSINE_SIMILARITY_KERNEL = """
__global__ void cosine_similarity(float *vectors, float *query, float *results, int n_vectors, int dim) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx < n_vectors) {
        float dot = 0.0f;
        float norm_v = 0.0f;
        float norm_q = 0.0f;
        
        for (int i = 0; i < dim; i++) {
            float v = vectors[idx * dim + i];
            float q = query[i];
            dot += v * q;
            norm_v += v * v;
            norm_q += q * q;
        }
        
        if (norm_v > 0 && norm_q > 0) {
            results[idx] = dot / (sqrtf(norm_v) * sqrtf(norm_q));
        } else {
            results[idx] = 0.0f;
        }
    }
}
"""

EUCLIDEAN_DISTANCE_KERNEL = """
__global__ void euclidean_distance(float *vectors, float *query, float *results, int n_vectors, int dim) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx < n_vectors) {
        float dist = 0.0f;
        for (int i = 0; i < dim; i++) {
            float diff = vectors[idx * dim + i] - query[i];
            dist += diff * diff;
        }
        results[idx] = -sqrtf(dist);
    }
}
"""


class GPUMemoryPool:
    """Manages GPU memory allocation for vector operations."""
    
    def __init__(self, max_vectors: int = 100000, dimension: int = 384):
        self.max_vectors = max_vectors
        self.dimension = dimension
        self._buffers: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._initialized = False
        
        if GPU_AVAILABLE and GPU_LIBRARY == 'cupy':
            self._init_cupy_buffers()
        elif GPU_AVAILABLE and GPU_LIBRARY == 'pycuda':
            self._init_pycuda_buffers()
    
    def _init_cupy_buffers(self):
        """Initialize CuPy GPU buffers."""
        try:
            with self._lock:
                self._buffers['vectors'] = cp.empty(
                    (self.max_vectors, self.dimension), 
                    dtype=cp.float32
                )
                self._buffers['query'] = cp.empty(
                    self.dimension, 
                    dtype=cp.float32
                )
                self._buffers['results'] = cp.empty(
                    self.max_vectors, 
                    dtype=cp.float32
                )
                self._initialized = True
                logger.info(f"[GPU] Allocated CuPy buffers for {self.max_vectors} vectors")
        except Exception as e:
            logger.error(f"[GPU] Failed to allocate CuPy buffers: {e}")
            self._initialized = False
    
    def _init_pycuda_buffers(self):
        """Initialize PyCUDA GPU buffers."""
        try:
            with self._lock:
                import pycuda.gpuarray as gpuarray
                
                self._buffers['vectors'] = gpuarray.empty(
                    (self.max_vectors, self.dimension), 
                    dtype=cp.float32
                )
                self._buffers['query'] = gpuarray.empty(
                    self.dimension, 
                    dtype=cp.float32
                )
                self._buffers['results'] = gpuarray.empty(
                    self.max_vectors, 
                    dtype=cp.float32
                )
                self._initialized = True
                logger.info(f"[GPU] Allocated PyCUDA buffers for {self.max_vectors} vectors")
        except Exception as e:
            logger.error(f"[GPU] Failed to allocate PyCUDA buffers: {e}")
            self._initialized = False
    
    def get_buffer(self, name: str) -> Optional[Any]:
        """Get a GPU buffer by name."""
        with self._lock:
            return self._buffers.get(name)
    
    def resize_if_needed(self, n_vectors: int) -> bool:
        """Resize buffers if needed."""
        if n_vectors > self.max_vectors:
            logger.warning(f"[GPU] Requested {n_vectors} vectors exceeds max {self.max_vectors}")
            return False
        return True
    
    def cleanup(self):
        """Free GPU memory."""
        with self._lock:
            self._buffers.clear()
            self._initialized = False
            logger.info("[GPU] Freed GPU buffers")


class GPUVectorIndex(VectorIndex):
    """
    GPU-accelerated vector index that mirrors VectorIndex interface.
    Automatically falls back to CPU when GPU is unavailable.
    """
    
    def __init__(self, dimension: int, metric: DistanceMetric = DistanceMetric.COSINE,
                 use_gpu: bool = True, batch_size: int = 10000):
        super().__init__(dimension, metric)
        
        self.use_gpu = use_gpu and GPU_AVAILABLE
        self.batch_size = batch_size
        self._memory_pool: Optional[GPUMemoryPool] = None
        self._gpu_module = None
        self._kernels = {}
        
        if self.use_gpu:
            self._initialize_gpu()
        else:
            if use_gpu and not GPU_AVAILABLE:
                logger.warning("[GPU] GPU acceleration requested but not available. Using CPU.")
            self.use_gpu = False
    
    def _initialize_gpu(self):
        """Initialize GPU resources."""
        try:
            self._memory_pool = GPUMemoryPool(
                max_vectors=self.batch_size,
                dimension=self.dimension
            )
            
            if GPU_LIBRARY == 'pycuda':
                self._gpu_module = SourceModule(
                    COSINE_SIMILARITY_KERNEL + EUCLIDEAN_DISTANCE_KERNEL
                )
                self._kernels['cosine'] = self._gpu_module.get_function("cosine_similarity")
                self._kernels['euclidean'] = self._gpu_module.get_function("euclidean_distance")
            
            logger.info(f"[GPU] Initialized GPU acceleration with {GPU_LIBRARY}")
            
        except Exception as e:
            logger.error(f"[GPU] Failed to initialize GPU: {e}")
            self.use_gpu = False
    
    def add(self, doc_id: str, vector: List[float], 
            metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Add document with vector to index."""
        return super().add(doc_id, vector, metadata)
    
    def search(self, query_vector: List[float], k: int = 10,
               filter_fn: Optional[Callable[[VectorDocument], bool]] = None) -> List[Tuple[str, float]]:
        """Search for k nearest neighbors using GPU if available."""
        if filter_fn or not self.use_gpu:
            if filter_fn and self.use_gpu:
                logger.debug("[GPU] Filter provided, falling back to CPU")
            return super().search(query_vector, k, filter_fn)
        
        try:
            return self._gpu_search(query_vector, k)
        except Exception as e:
            logger.error(f"[GPU] GPU search failed, falling back to CPU: {e}")
            return super().search(query_vector, k, filter_fn)
    
    def _gpu_search(self, query_vector: List[float], k: int) -> List[Tuple[str, float]]:
        """Perform GPU-accelerated search."""
        import numpy as np
        
        with self._lock:
            doc_ids = list(self._documents.keys())
            vectors = [self._documents[doc_id].vector for doc_id in doc_ids]
        
        if not vectors:
            return []
        
        n_vectors = len(vectors)
        all_scores = []
        
        for start_idx in range(0, n_vectors, self.batch_size):
            end_idx = min(start_idx + self.batch_size, n_vectors)
            batch_vectors = vectors[start_idx:end_idx]
            batch_doc_ids = doc_ids[start_idx:end_idx]
            
            batch_scores = self._compute_similarities_gpu(batch_vectors, query_vector)
            
            if batch_scores is not None:
                all_scores.extend(zip(batch_doc_ids, batch_scores))
            else:
                logger.debug("[GPU] Batch computation failed, using CPU")
                for doc_id, vec in zip(batch_doc_ids, batch_vectors):
                    score = self._compute_similarity(query_vector, vec)
                    all_scores.append((doc_id, score))
        
        all_scores.sort(key=lambda x: x[1], reverse=True)
        return all_scores[:k]
    
    def _compute_similarities_gpu(self, vectors: List[List[float]], 
                                  query: List[float]) -> Optional[List[float]]:
        """Compute similarities using GPU."""
        if GPU_LIBRARY == 'cupy':
            return self._compute_similarities_cupy(vectors, query)
        elif GPU_LIBRARY == 'pycuda':
            return self._compute_similarities_pycuda(vectors, query)
        return None
    
    def _compute_similarities_cupy(self, vectors: List[List[float]], 
                                     query: List[float]) -> Optional[List[float]]:
        """Compute similarities using CuPy."""
        try:
            import numpy as np
            
            vectors_cp = cp.array(vectors, dtype=cp.float32)
            query_cp = cp.array(query, dtype=cp.float32)
            
            if self.metric == DistanceMetric.COSINE:
                vectors_norm = cp.linalg.norm(vectors_cp, axis=1, keepdims=True)
                query_norm = cp.linalg.norm(query_cp)
                dot_product = cp.dot(vectors_cp, query_cp)
                similarities = dot_product / (vectors_norm.flatten() * query_norm)
                similarities = cp.where(vectors_norm.flatten() > 0, similarities, 0.0)
                
            elif self.metric == DistanceMetric.EUCLIDEAN:
                diff = vectors_cp - query_cp
                distances = cp.linalg.norm(diff, axis=1)
                similarities = -distances
                
            elif self.metric == DistanceMetric.DOT_PRODUCT:
                similarities = cp.dot(vectors_cp, query_cp)
                
            else:
                return None
            
            return cp.asnumpy(similarities).tolist()
            
        except Exception as e:
            logger.error(f"[GPU] CuPy computation failed: {e}")
            return None
    
    def _compute_similarities_pycuda(self, vectors: List[List[float]], 
                                       query: List[float]) -> Optional[List[float]]:
        """Compute similarities using PyCUDA."""
        try:
            import numpy as np
            
            n_vectors = len(vectors)
            dim = len(query)
            
            vectors_flat = np.array(vectors, dtype=np.float32).flatten()
            query_array = np.array(query, dtype=np.float32)
            results = np.empty(n_vectors, dtype=np.float32)
            
            vectors_gpu = cuda.mem_alloc(vectors_flat.nbytes)
            query_gpu = cuda.mem_alloc(query_array.nbytes)
            results_gpu = cuda.mem_alloc(results.nbytes)
            
            cuda.memcpy_htod(vectors_gpu, vectors_flat)
            cuda.memcpy_htod(query_gpu, query_array)
            
            if self.metric == DistanceMetric.COSINE:
                kernel = self._kernels['cosine']
            else:
                kernel = self._kernels['euclidean']
            
            block_size = 256
            grid_size = (n_vectors + block_size - 1) // block_size
            
            kernel(
                vectors_gpu, query_gpu, results_gpu,
                np.int32(n_vectors), np.int32(dim),
                block=(block_size, 1, 1), grid=(grid_size, 1)
            )
            
            cuda.memcpy_dtoh(results, results_gpu)
            
            vectors_gpu.free()
            query_gpu.free()
            results_gpu.free()
            
            return results.tolist()
            
        except Exception as e:
            logger.error(f"[GPU] PyCUDA computation failed: {e}")
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics including GPU info."""
        stats = super().get_stats()
        stats['gpu_accelerated'] = self.use_gpu
        stats['gpu_library'] = GPU_LIBRARY if self.use_gpu else None
        stats['batch_size'] = self.batch_size if self.use_gpu else None
        return stats
    
    def cleanup(self):
        """Clean up GPU resources."""
        if self._memory_pool:
            self._memory_pool.cleanup()


class GPUSearchEngine(VectorSearchEngine):
    """GPU-accelerated search engine that mirrors VectorSearchEngine."""
    
    def __init__(self, use_gpu: bool = True):
        super().__init__()
        self.use_gpu = use_gpu and GPU_AVAILABLE
        self._gpu_indexes: Dict[str, GPUVectorIndex] = {}
    
    def create_index(self, name: str, dimension: int,
                     metric: DistanceMetric = DistanceMetric.COSINE,
                     use_gpu: Optional[bool] = None) -> GPUVectorIndex:
        """Create new vector index with optional GPU acceleration."""
        with self._lock:
            if name in self._indexes:
                raise ValueError(f"Index {name} already exists")
            
            gpu_enabled = use_gpu if use_gpu is not None else self.use_gpu
            
            index = GPUVectorIndex(dimension, metric, use_gpu=gpu_enabled)
            self._indexes[name] = index
            self._gpu_indexes[name] = index
            
            return index
    
    def get_gpu_stats(self) -> Dict[str, Any]:
        """Get GPU statistics for all indexes."""
        stats = {
            'gpu_available': GPU_AVAILABLE,
            'gpu_library': GPU_LIBRARY,
            'gpu_indexes': len(self._gpu_indexes),
            'cpu_indexes': len(self._indexes) - len(self._gpu_indexes)
        }
        
        for name, index in self._gpu_indexes.items():
            stats[name] = index.get_stats()
        
        return stats


def check_gpu_availability() -> Dict[str, Any]:
    """Check GPU availability and return detailed information."""
    info = {
        'available': GPU_AVAILABLE,
        'library': GPU_LIBRARY,
        'device_name': None,
        'memory_total': None,
        'memory_free': None
    }
    
    if not GPU_AVAILABLE:
        return info
    
    try:
        if GPU_LIBRARY == 'cupy':
            mem_info = cp.cuda.Device().mem_info
            if mem_info:
                info['memory_free'] = mem_info[0]
                info['memory_total'] = mem_info[1]
                
        elif GPU_LIBRARY == 'pycuda':
            from pycuda.driver import Device
            device = Device(0)
            info['device_name'] = device.name()
            
    except Exception as e:
        logger.error(f"[GPU] Failed to get GPU info: {e}")
    
    return info


def create_gpu_search_engine(use_gpu: bool = True) -> GPUSearchEngine:
    """Create a GPU-accelerated search engine."""
    if use_gpu and not GPU_AVAILABLE:
        logger.warning("[GPU] GPU acceleration requested but not available. Using CPU.")
    
    return GPUSearchEngine(use_gpu=use_gpu)
