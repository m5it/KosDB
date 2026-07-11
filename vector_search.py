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
from dataclasses import dataclass, field
from collections import defaultdict
import threading


class DistanceMetric(Enum):
    """Distance metrics for vector comparison."""
    COSINE = auto()      # Cosine similarity (1 - cosine distance)
    EUCLIDEAN = auto()   # L2 distance
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
        return self._gpu_ops is not None and self._gpu_ops.is_available


class VectorIndex:
    """
    In-memory vector index for similarity search.
    Supports brute-force and approximate search methods.
    """
    
    def __init__(self, dimension: int, metric: DistanceMetric = DistanceMetric.COSINE):
        self.dimension = dimension
        self.metric = metric
        self._documents: Dict[str, VectorDocument] = {}
        self._lock = threading.RLock()
        
        # For IVF (Inverted File Index)
        self._n_clusters = 0
        self._centroids: List[List[float]] = []
        self._inverted_lists: Dict[int, List[str]] = defaultdict(list)
        self._is_trained = False
    
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
class VectorSearchEngine:
    """
    High-level vector search engine with multiple indexes and GPU support.
    """
    
    def __init__(self, use_gpu: bool = True, gpu_config: Optional[GPUConfig] = None):
        self._indexes: Dict[str, VectorIndex] = {}
        self._lock = threading.RLock()
        self._use_gpu = use_gpu and GPU_AVAILABLE
        
        # Initialize GPU if requested
        if self._use_gpu and gpu_config:
            self._gpu_ops = configure_gpu(
                enabled=gpu_config.enabled,
                device_id=gpu_config.device_id,
                memory_limit_mb=gpu_config.memory_limit_mb,
                batch_size=gpu_config.batch_size
            )
        elif self._use_gpu:
            self._gpu_ops = get_gpu_ops()
        else:
            self._gpu_ops = None
    
    def create_index(self, name: str, dimension: int,
                     metric: DistanceMetric = DistanceMetric.COSINE) -> VectorIndex:
        """
        Create new vector index.
        
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
            if self._gpu_ops:
                index._gpu_ops = self._gpu_ops
            self._indexes[name] = index
            return index
        with self._lock:
            vectors = [doc.vector for doc in self._documents.values()]
            self._centroids = self._kmeans(vectors, n_clusters)
            self._n_clusters = n_clusters
            
            # Build inverted lists
            self._inverted_lists.clear()
            for doc_id, doc in self._documents.items():
                cluster_id = self._assign_to_cluster(doc.vector)
                self._inverted_lists[cluster_id].append(doc_id)
            
            self._is_trained = True
    
    def _kmeans(self, vectors: List[List[float]], k: int, 
                max_iters: int = 10) -> List[List[float]]:
        """
        Simple k-means clustering.
        
        Args:
            vectors: List of vectors
            k: Number of clusters
            max_iters: Maximum iterations
        
        Returns:
            Cluster centroids
        """
        if not vectors:
            return []
        
        # Random initialization - use deterministic seed for tests
        random.seed(42)
        centroids = random.sample(vectors, k)
        
        for _ in range(max_iters):
            # Assign to clusters
            clusters: Dict[int, List[List[float]]] = defaultdict(list)
            for v in vectors:
                distances = [
                    self._euclidean_distance(v, c) 
                    for c in centroids
                ]
                cluster_id = distances.index(min(distances))
                clusters[cluster_id].append(v)
            
            # Update centroids
            new_centroids = []
            for i in range(k):
                if i in clusters and clusters[i]:
                    # Compute mean
                    mean = [
                        sum(v[j] for v in clusters[i]) / len(clusters[i])
                        for j in range(self.dimension)
                    ]
                    new_centroids.append(mean)
                else:
                    new_centroids.append(centroids[i])
            
            centroids = new_centroids
        
        return centroids
    
    def _assign_to_cluster(self, vector: List[float]) -> int:
        """Assign vector to nearest cluster."""
        distances = [
            self._euclidean_distance(vector, c)
            for c in self._centroids
        ]
        return distances.index(min(distances))
    
    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        with self._lock:
            return {
                'dimension': self.dimension,
                'metric': self.metric.name,
                'num_documents': len(self._documents),
                'num_clusters': self._n_clusters,
                'is_trained': self._is_trained
            }


class VectorSearchEngine:
    """
    High-level vector search engine with multiple indexes.
    """
    
    def __init__(self):
        self._indexes: Dict[str, VectorIndex] = {}
        self._lock = threading.RLock()
    
    def create_index(self, name: str, dimension: int,
                     metric: DistanceMetric = DistanceMetric.COSINE) -> VectorIndex:
        """
        Create new vector index.
        
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
            
            index = VectorIndex(dimension, metric)
            self._indexes[name] = index
            return index
    
    def get_index(self, name: str) -> Optional[VectorIndex]:
        """Get index by name."""
        with self._lock:
            return self._indexes.get(name)
    
    def delete_index(self, name: str) -> bool:
        """Delete index."""
        with self._lock:
            if name not in self._indexes:
                return False
            del self._indexes[name]
            return True
    
    def list_indexes(self) -> List[str]:
        """List all index names."""
        with self._lock:
            return list(self._indexes.keys())
    
    def search(self, index_name: str, query_vector: List[float],
               k: int = 10, **kwargs) -> List[Tuple[str, float]]:
        """
        Search index.
        
        Args:
            index_name: Index to search
            query_vector: Query embedding
            k: Number of results
            **kwargs: Additional search parameters
        
        Returns:
            Search results
        """
        index = self.get_index(index_name)
        if not index:
            raise ValueError(f"Index {index_name} not found")
        
        return index.search(query_vector, k, **kwargs)
    
    def hybrid_search(self, index_name: str, query_vector: List[float],
                     keyword_filter: Optional[str] = None,
                     k: int = 10) -> List[Tuple[str, float, Dict[str, Any]]]:
        """
        Hybrid search combining vector similarity with keyword filtering.
        
        Args:
            index_name: Index to search
            query_vector: Query embedding
            keyword_filter: Optional keyword to filter results
            k: Number of results
        
        Returns:
            Results with metadata
        """
        index = self.get_index(index_name)
        if not index:
            raise ValueError(f"Index {index_name} not found")
        
        # Create filter function
        filter_fn = None
        if keyword_filter:
            def filter_fn(doc):
                text = json.dumps(doc.metadata).lower()
                return keyword_filter.lower() in text
        
        results = index.search(query_vector, k * 2, filter_fn=filter_fn)
        
        # Enrich with metadata
        enriched = []
        for doc_id, score in results[:k]:
            doc = index._documents.get(doc_id)
            if doc:
                enriched.append((doc_id, score, doc.metadata))
        
        return enriched


class EmbeddingGenerator:
    """
    Interface for generating embeddings from text.
    """
    
    def __init__(self, dimension: int = 128):
        self.dimension = dimension
    
    def encode(self, text: str) -> List[float]:
        """
        Generate embedding for text.
        
        Args:
            text: Input text
        
        Returns:
            Embedding vector
        """
        # Simple hash-based embedding for demo
        # In production, use sentence-transformers or similar
        random.seed(hash(text) % (2**32))
        return [random.gauss(0, 1) for _ in range(self.dimension)]
    
    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts
        
        Returns:
            List of embeddings
        """
        return [self.encode(t) for t in texts]


class SemanticSearcher:
    """
    High-level semantic search interface.
    """
    
    def __init__(self, engine: Optional[VectorSearchEngine] = None,
                 embedding_gen: Optional[EmbeddingGenerator] = None):
        self.engine = engine or VectorSearchEngine()
        self.embedding_gen = embedding_gen or EmbeddingGenerator()
    
    def index_document(self, index_name: str, doc_id: str, 
                       text: str, metadata: Optional[Dict[str, Any]] = None):
        """
        Index document with text content.
        
        Args:
            index_name: Index name
            doc_id: Document ID
            text: Document text
            metadata: Optional metadata
        """
        index = self.engine.get_index(index_name)
        if not index:
            raise ValueError(f"Index {index_name} not found")
        
        # Use index dimension for embedding
        embedding_gen = EmbeddingGenerator(dimension=index.dimension)
        embedding = embedding_gen.encode(text)
        
        meta = metadata or {}
        meta['text'] = text  # Store original text
        
        index.add(doc_id, embedding, meta)
    
    def search(self, index_name: str, query: str, k: int = 10) -> List[Dict[str, Any]]:
        """
        Semantic search.
        
        Args:
            index_name: Index name
            query: Search query
            k: Number of results
        
        Returns:
            Search results with text and scores
        """
        index = self.engine.get_index(index_name)
        if not index:
            raise ValueError(f"Index {index_name} not found")
        
        # Use index dimension for embedding
        embedding_gen = EmbeddingGenerator(dimension=index.dimension)
        query_embedding = embedding_gen.encode(query)
        
        results = self.engine.hybrid_search(
            index_name, 
            query_embedding,
            k=k
        )
        
        return [
            {
                'doc_id': doc_id,
                'score': score,
                'metadata': metadata
            }
            for doc_id, score, metadata in results
        ]


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
