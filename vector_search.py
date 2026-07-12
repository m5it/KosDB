
"""
Vector Similarity Search for KosDB

Implements vector storage and similarity search using embeddings
for semantic queries. Supports cosine similarity, Euclidean distance,
and approximate nearest neighbor search with GPU acceleration.
"""

import math
import json
import heapq
import struct
import random
from typing import Dict, Any, List, Optional, Tuple, Callable, Union
from enum import Enum, auto
from dataclasses import dataclass, field
from collections import defaultdict
import threading

# Import GPU operations if available
try:
    from gpu_vector_ops import GPUVectorOps, GPUConfig, get_gpu_ops
    GPU_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False


class DistanceMetric(Enum):
    """Distance metrics for vector comparison."""
    COSINE = auto()      # Cosine similarity (1 - cosine distance)
    EUCLIDEAN = auto()   # L2 distance
    DOT_PRODUCT = auto()   # Dot product
    MANHATTAN = auto()   # L1 distance


@dataclass
class VectorDocument:
    """Document with vector embedding."""
    doc_id: str
    vector: List[float]
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'doc_id': self.doc_id,
            'vector': self.vector,
            'metadata': self.metadata
        }


class VectorIndex:
    """
    In-memory vector index for similarity search.
    Supports brute-force and approximate search methods with GPU acceleration.
    """
    
    def __init__(self, dimension: int, metric: DistanceMetric = DistanceMetric.COSINE,
                 use_gpu: bool = True):
        self.dimension = dimension
        self.metric = metric
        self._documents: Dict[str, VectorDocument] = {}
        self._lock = threading.RLock()
        
        # GPU support
        self._gpu_ops: Optional[GPUVectorOps] = None
        if use_gpu and GPU_AVAILABLE:
            self._gpu_ops = get_gpu_ops()
        
        # For IVF (Inverted File Index)
        self._n_clusters = 0
        self._centroids: List[List[float]] = []
        self._inverted_lists: Dict[int, List[str]] = defaultdict(list)
        self._is_trained = False
    
    def _use_gpu(self) -> bool:
        """Check if GPU should be used."""
        return self._gpu_ops is not None and self._gpu_ops.is_available()
    
    def add(self, doc_id: str, vector: List[float], 
            metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Add document with vector to index.
        
        Args:
            doc_id: Unique document ID
            vector: Embedding vector
            metadata: Optional metadata
        
        Returns:
            True if added successfully
        """
        if len(vector) != self.dimension:
            raise ValueError(f"Expected dimension {self.dimension}, got {len(vector)}")
        
        doc = VectorDocument(
            doc_id=doc_id,
            vector=vector,
            metadata=metadata or {}
        )
        
        with self._lock:
            self._documents[doc_id] = doc
            
            # Add to inverted list if using IVF
            if self._is_trained and self._n_clusters > 0:
                cluster_id = self._assign_to_cluster(vector)
                self._inverted_lists[cluster_id].append(doc_id)
        
        return True
    
    def remove(self, doc_id: str) -> bool:
        """Remove document from index."""
        with self._lock:
            if doc_id in self._documents:
                del self._documents[doc_id]
                
                # Remove from inverted lists
                for cluster_list in self._inverted_lists.values():
                    if doc_id in cluster_list:
                        cluster_list.remove(doc_id)
                        break
                
                return True
            return False
    
    def search(self, query_vector: List[float], k: int = 10,
               filter_fn: Optional[Callable] = None) -> List[Tuple[str, float]]:
        """
        Search for similar vectors.
        
        Args:
            query_vector: Query embedding
            k: Number of results
            filter_fn: Optional filter function
        
        Returns:
            List of (doc_id, score) tuples
        """
        if self._is_trained and self._n_clusters > 0:
            return self._ivf_search(query_vector, k, filter_fn)
        else:
            return self._brute_force_search(query_vector, k, filter_fn)
    
    def _brute_force_search(self, query_vector: List[float], k: int,
                           filter_fn: Optional[Callable] = None) -> List[Tuple[str, float]]:
        """Brute force search over all documents."""
        with self._lock:
            doc_list = list(self._documents.values())
        
        # Apply filter
        if filter_fn:
            doc_list = [d for d in doc_list if filter_fn(d)]
        
        if not doc_list:
            return []
        
        # Use GPU if available and enough documents
        if self._use_gpu() and len(doc_list) >= 10:
            return self._gpu_brute_force_search(query_vector, doc_list, k)
        
        # CPU fallback
        return self._cpu_brute_force_search(query_vector, doc_list, k)
    
    def _gpu_brute_force_search(self, query_vector: List[float],
                                 doc_list: List[VectorDocument],
                                 k: int) -> List[Tuple[str, float]]:
        """GPU-accelerated brute force search."""
        try:
            vectors = [doc.vector for doc in doc_list]
            
            if self.metric == DistanceMetric.COSINE:
                scores = self._gpu_ops.cosine_similarity_batch(query_vector, vectors)
            elif self.metric == DistanceMetric.EUCLIDEAN:
                scores = self._gpu_ops.euclidean_distance_batch(query_vector, vectors)
                # Convert distance to score (negative for sorting)
                scores = [-s for s in scores]
            elif self.metric == DistanceMetric.DOT_PRODUCT:
                scores = self._gpu_ops.dot_product_batch(query_vector, vectors)
            else:
                # Fallback for unsupported metrics
                return self._cpu_brute_force_search(query_vector, doc_list, k)
            
            # Create results
            results = [(doc_list[i].doc_id, scores[i]) for i in range(len(doc_list))]
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:k]
            
        except Exception as e:
            print(f"[VectorSearch] GPU search failed, using CPU: {e}")
            return self._cpu_brute_force_search(query_vector, doc_list, k)
    
    def _cpu_brute_force_search(self, query_vector: List[float],
                                 doc_list: List[VectorDocument],
                                 k: int) -> List[Tuple[str, float]]:
        """CPU brute force search."""
        results = []
        for doc in doc_list:
            score = self._compute_similarity(query_vector, doc.vector)
            results.append((doc.doc_id, score))
        
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:k]
    
    def _ivf_search(self, query_vector: List[float], k: int,
                   filter_fn: Optional[Callable] = None) -> List[Tuple[str, float]]:
        """Search using Inverted File Index."""
        # Find nearest centroids
        centroid_scores = [
            (i, self._compute_similarity(query_vector, centroid))
            for i, centroid in enumerate(self._centroids)
        ]
        centroid_scores.sort(key=lambda x: x[1], reverse=True)
        
        # Search top n_probe clusters
        n_probe = min(3, self._n_clusters)
        candidates = []
        
        for cluster_id, _ in centroid_scores[:n_probe]:
            for doc_id in self._inverted_lists[cluster_id]:
                doc = self._documents.get(doc_id)
                if doc and (not filter_fn or filter_fn(doc)):
                    score = self._compute_similarity(query_vector, doc.vector)
                    candidates.append((doc_id, score))
        
        # Return top k
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:k]
    
    def _assign_to_cluster(self, vector: List[float]) -> int:
        """Assign vector to nearest cluster."""
        best_cluster = 0
        best_score = -float('inf')
        
        for i, centroid in enumerate(self._centroids):
            score = self._compute_similarity(vector, centroid)
            if score > best_score:
                best_score = score
                best_cluster = i
        
        return best_cluster
    
    def _compute_similarity(self, v1: List[float], v2: List[float]) -> float:
        """Compute similarity between two vectors."""
        if self.metric == DistanceMetric.COSINE:
            return self._cosine_similarity(v1, v2)
        elif self.metric == DistanceMetric.EUCLIDEAN:
            return -self._euclidean_distance(v1, v2)  # Negative for sorting
        elif self.metric == DistanceMetric.DOT_PRODUCT:
            return sum(a * b for a, b in zip(v1, v2))
        elif self.metric == DistanceMetric.MANHATTAN:
            return -sum(abs(a - b) for a, b in zip(v1, v2))
        else:
            raise ValueError(f"Unknown metric: {self.metric}")
    
    @staticmethod
    def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
        """Compute cosine similarity."""
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot / (norm1 * norm2)
    
    @staticmethod
    def _euclidean_distance(v1: List[float], v2: List[float]) -> float:
        """Compute Euclidean distance."""
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(v1, v2)))
    
    def train_ivf(self, n_clusters: int = 10) -> None:
        """
        Train IVF index using k-means clustering.
        
        Args:
            n_clusters: Number of clusters
        """
        if len(self._documents) < n_clusters:
            return
        
        with self._lock:
            vectors = [doc.vector for doc in self._documents.values()]
            
            # Use GPU k-means if available
            if self._use_gpu() and len(vectors) > 100:
                try:
                    centroids, labels = self._gpu_ops.kmeans_cluster(vectors, n_clusters)
                except Exception as e:
                    print(f"[VectorSearch] GPU k-means failed, using CPU: {e}")
                    centroids, labels = self._kmeans_cpu(vectors, n_clusters)
            else:
                centroids, labels = self._kmeans_cpu(vectors, n_clusters)
            
            self._centroids = centroids
            self._n_clusters = n_clusters
            
            # Build inverted lists
            self._inverted_lists.clear()
            doc_ids = list(self._documents.keys())
            for i, label in enumerate(labels):
                self._inverted_lists[label].append(doc_ids[i])
            
            self._is_trained = True
    
    def _kmeans_cpu(self, vectors: List[List[float]], n_clusters: int,
                    max_iter: int = 100) -> Tuple[List[List[float]], List[int]]:
        """
        K-means clustering using CPU.
        
        Args:
            vectors: List of vectors
            n_clusters: Number of clusters
            max_iter: Maximum iterations
        
        Returns:
            Centroids and labels
        """
        n = len(vectors)
        dim = len(vectors[0])
        
        # Initialize centroids randomly
        indices = random.sample(range(n), n_clusters)
        centroids = [vectors[i] for i in indices]
        
        for _ in range(max_iter):
            # Assign each vector to nearest centroid
            labels = []
            for v in vectors:
                distances = [self._euclidean_distance(v, c) for c in centroids]
                labels.append(distances.index(min(distances)))
            
            # Update centroids
            new_centroids = []
            for i in range(n_clusters):
                cluster_vectors = [vectors[j] for j in range(n) if labels[j] == i]
                if cluster_vectors:
                    new_centroid = [sum(v[j] for v in cluster_vectors) / len(cluster_vectors) 
                                   for j in range(dim)]
                    new_centroids.append(new_centroid)
                else:
                    new_centroids.append(centroids[i])
            
            # Check convergence
            if new_centroids == centroids:
                break
            
            centroids = new_centroids
        
        return centroids, labels
    
    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        with self._lock:
            stats = {
                'dimension': self.dimension,
                'metric': self.metric.name,
                'num_documents': len(self._documents),
                'num_clusters': self._n_clusters,
                'is_trained': self._is_trained,
                'gpu_enabled': self._use_gpu()
            }
            
            if self._use_gpu():
                gpu_info = self._gpu_ops.get_device_info()
                stats['gpu_info'] = gpu_info
            
            return stats


class VectorSearchEngine:
    """
    High-level vector search engine with multiple indexes and GPU support.
    """
    
    def __init__(self, use_gpu: bool = True, gpu_config: Optional[Any] = None):
        self._indexes: Dict[str, VectorIndex] = {}
        self._lock = threading.RLock()
        self._use_gpu = use_gpu and GPU_AVAILABLE
        
        # Initialize GPU if requested
        if self._use_gpu and gpu_config:
            self._gpu_ops = get_gpu_ops()
        elif self._use_gpu:
            self._gpu_ops = get_gpu_ops()
        else:
            self._gpu_ops = None
    
    def create_index(self, name: str, dimension: int,
                    metric: DistanceMetric = DistanceMetric.COSINE) -> VectorIndex:
        """
        Create a new vector index.
        
        Args:
            name: Index name
            dimension: Vector dimension
            metric: Distance metric
        
        Returns:
            Created index
        """
        with self._lock:
            if name in self._indexes:
                raise ValueError(f"Index {name} already exists")
            
            index = VectorIndex(dimension, metric, use_gpu=self._use_gpu)
            self._indexes[name] = index
            
            return index
    
    def get_index(self, name: str) -> Optional[VectorIndex]:
        """Get index by name."""
        with self._lock:
            return self._indexes.get(name)
    
    def delete_index(self, name: str) -> bool:
        """Delete index."""
        with self._lock:
            if name in self._indexes:
                del self._indexes[name]
                return True
            return False
    
    def list_indexes(self) -> List[str]:
        """List all indexes."""
        with self._lock:
            return list(self._indexes.keys())
    
    def hybrid_search(self, index_name: str, query_vector: List[float],
                     metadata_filter: Optional[Dict[str, Any]] = None,
                     k: int = 10) -> List[Tuple[str, float, Dict[str, Any]]]:
        """
        Hybrid search with vector similarity and metadata filtering.
        
        Args:
            index_name: Index name
            query_vector: Query embedding
            metadata_filter: Metadata filter criteria
            k: Number of results
        
        Returns:
            List of (doc_id, score, metadata) tuples
        """
        index = self.get_index(index_name)
        if not index:
            return []
        
        # Build filter function
        filter_fn = None
        if metadata_filter:
            def filter_fn(doc):
                return all(doc.metadata.get(k) == v for k, v in metadata_filter.items())
        
        # Search
        results = index.search(query_vector, k=k*2, filter_fn=filter_fn)
        
        # Add metadata
        enriched_results = []
        for doc_id, score in results[:k]:
            doc = index._documents.get(doc_id)
            if doc:
                enriched_results.append((doc_id, score, doc.metadata))
        
        return enriched_results


# Utility functions
def normalize_vector(vector: List[float]) -> List[float]:
    """Normalize vector to unit length."""
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0:
        return vector
    return [x / norm for x in vector]


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return dot / (norm1 * norm2)


def euclidean_distance(v1: List[float], v2: List[float]) -> float:
    """Compute Euclidean distance."""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(v1, v2)))


def dot_product(v1: List[float], v2: List[float]) -> float:
    """Compute dot product."""
    return sum(a * b for a, b in zip(v1, v2))
