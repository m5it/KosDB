"""
Vector Similarity Search for KosDB

Implements vector storage and similarity search using embeddings
for semantic queries. Supports cosine similarity, Euclidean distance,
and approximate nearest neighbor search. Includes optional GPU acceleration.
"""

import math
import json
import heapq
import struct
import random
import logging
from typing import Dict, Any, List, Optional, Tuple, Callable, Union
from enum import Enum, auto
from dataclasses import dataclass, field
from collections import defaultdict
import threading

# Try to import GPU acceleration
try:
    from gpu_vector_search import GPUVectorIndex, GPUSearchEngine, GPU_AVAILABLE
    GPU_SUPPORT = True
except ImportError:
    GPU_SUPPORT = False

# Configure logging
logger = logging.getLogger(__name__)


class DistanceMetric(Enum):
    """Distance metrics for vector comparison."""
    COSINE = auto()
    EUCLIDEAN = auto()
    DOT_PRODUCT = auto()
    MANHATTAN = auto()


@dataclass
class VectorDocument:
    """A document with vector embedding."""
    doc_id: str
    vector: List[float]
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=lambda: __import__('time').time())
    
    def __post_init__(self):
        # Normalize vector for cosine similarity
        self._norm = math.sqrt(sum(x * x for x in self.vector))
    
    def normalize(self) -> List[float]:
        """Get normalized vector."""
        if self._norm == 0:
            return self.vector
        return [x / self._norm for x in self.vector]


class VectorIndex:
    """
    In-memory vector index for similarity search.
    Supports brute-force and approximate search methods.
    Automatically uses GPU acceleration when available and beneficial.
    """
    
    # Threshold for automatic GPU selection
    GPU_THRESHOLD = 1000
    
    def __init__(self, dimension: int, metric: DistanceMetric = DistanceMetric.COSINE,
                 use_gpu: Optional[bool] = None):
        """
        Initialize vector index.
        
        Args:
            dimension: Vector dimension
            metric: Distance metric
            use_gpu: Whether to use GPU (None=auto, True=force GPU, False=force CPU)
        """
        self.dimension = dimension
        self.metric = metric
        self._documents: Dict[str, VectorDocument] = {}
        self._lock = threading.RLock()
        
        # GPU configuration
        self._use_gpu_preference = use_gpu
        self._gpu_index: Optional[Any] = None
        
        # For IVF (Inverted File Index)
        self._n_clusters = 0
        self._centroids: List[List[float]] = []
        self._inverted_lists: Dict[int, List[str]] = defaultdict(list)
        self._is_trained = False
        
        # Initialize GPU if forced
        if use_gpu is True and GPU_SUPPORT:
            self._init_gpu_index()
    
    def _init_gpu_index(self):
        """Initialize GPU-accelerated index."""
        if not GPU_SUPPORT:
            logger.warning("GPU acceleration requested but not available")
            return
        
        try:
            self._gpu_index = GPUVectorIndex(
                dimension=self.dimension,
                metric=self.metric,
                use_gpu=True
            )
            logger.info(f"[VectorSearch] GPU acceleration enabled for dimension {self.dimension}")
        except Exception as e:
            logger.error(f"[VectorSearch] Failed to initialize GPU: {e}")
            self._gpu_index = None
    
    def _should_use_gpu(self, n_vectors: int) -> bool:
        """
        Determine if GPU should be used based on configuration and vector count.
        
        Args:
            n_vectors: Number of vectors to process
        
        Returns:
            True if GPU should be used
        """
        # Check explicit preference
        if self._use_gpu_preference is False:
            return False
        if self._use_gpu_preference is True:
            return GPU_SUPPORT and self._gpu_index is not None
        
        # Auto mode: use GPU for large batches
        if n_vectors >= self.GPU_THRESHOLD and GPU_SUPPORT:
            if self._gpu_index is None:
                self._init_gpu_index()
            return self._gpu_index is not None
        
        return False
    
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
            
            # Add to GPU index if active
            if self._gpu_index:
                try:
                    self._gpu_index.add(doc_id, vector, metadata)
                except Exception as e:
                    logger.warning(f"[VectorSearch] Failed to add to GPU index: {e}")
            
            # Add to inverted list if using IVF
            if self._is_trained and self._n_clusters > 0:
                cluster_id = self._assign_to_cluster(vector)
                self._inverted_lists[cluster_id].append(doc_id)
        
        return True
    
    def remove(self, doc_id: str) -> bool:
        """
        Remove document from index.
        
        Args:
            doc_id: Document ID to remove
        
        Returns:
            True if removed
        """
        with self._lock:
            if doc_id not in self._documents:
                return False
            
            doc = self._documents[doc_id]
            del self._documents[doc_id]
            
            # Remove from GPU index
            if self._gpu_index:
                self._gpu_index.remove(doc_id)
            
            # Remove from inverted list
            if self._is_trained:
                cluster_id = self._assign_to_cluster(doc.vector)
                if doc_id in self._inverted_lists[cluster_id]:
                    self._inverted_lists[cluster_id].remove(doc_id)
            
            return True
    
    def search(self, query_vector: List[float], k: int = 10,
               filter_fn: Optional[Callable[[VectorDocument], bool]] = None) -> List[Tuple[str, float]]:
        """
        Search for k nearest neighbors.
        Automatically uses GPU for large datasets when available.
        
        Args:
            query_vector: Query embedding
            k: Number of results
            filter_fn: Optional filter function
        
        Returns:
            List of (doc_id, score) tuples, sorted by score
        """
        if len(query_vector) != self.dimension:
            raise ValueError(f"Expected dimension {self.dimension}, got {len(query_vector)}")
        
        with self._lock:
            n_vectors = len(self._documents)
            
            # Check if we should use GPU
            if self._should_use_gpu(n_vectors) and not filter_fn:
                # Use GPU-accelerated search
                if self._gpu_index:
                    # Sync documents to GPU index if needed
                    self._sync_to_gpu()
                    return self._gpu_index.search(query_vector, k)
            
            # Use CPU implementation
            if self._is_trained and self._n_clusters > 0:
                return self._ivf_search(query_vector, k, filter_fn)
            else:
                return self._brute_force_search(query_vector, k, filter_fn)
    
    def _sync_to_gpu(self):
        """Sync documents to GPU index."""
        if not self._gpu_index:
            return
        
        # Check if GPU index has all documents
        gpu_count = len(self._gpu_index._documents)
        cpu_count = len(self._documents)
        
        if gpu_count < cpu_count:
            # Add missing documents to GPU
            for doc_id, doc in self._documents.items():
                if doc_id not in self._gpu_index._documents:
                    self._gpu_index.add(doc_id, doc.vector, doc.metadata)
    
    def _brute_force_search(self, query_vector: List[float], k: int,
                           filter_fn: Optional[Callable] = None) -> List[Tuple[str, float]]:
        """Brute force search over all documents."""
        scores = []
        
        for doc_id, doc in self._documents.items():
            if filter_fn and not filter_fn(doc):
                continue
            
            score = self._compute_similarity(query_vector, doc.vector)
            scores.append((doc_id, score))
        
        # Return top k
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:k]
    
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
    
    def train_ivf(self, n_clusters: int = 10):
        """
        Train IVF index using k-means clustering.
        
        Args:
            n_clusters: Number of clusters
        """
        if len(self._documents) < n_clusters:
            return  # Not enough documents
        
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
        """Get index statistics including GPU info."""
        with self._lock:
            stats = {
                'dimension': self.dimension,
                'metric': self.metric.name,
                'num_documents': len(self._documents),
                'num_clusters': self._n_clusters,
                'is_trained': self._is_trained,
                'gpu_accelerated': self._gpu_index is not None,
                'use_gpu_preference': self._use_gpu_preference
            }
            return stats


class VectorSearchEngine:
    """
    High-level vector search engine with multiple indexes.
    Supports GPU acceleration configuration.
    """
    
    def __init__(self, use_gpu: Optional[bool] = None):
        """
        Initialize search engine.
        
        Args:
            use_gpu: Global GPU setting (None=auto, True=force, False=disable)
        """
        self._indexes: Dict[str, VectorIndex] = {}
        self._lock = threading.RLock()
        self._global_use_gpu = use_gpu
        self._gpu_stats = {'cpu_searches': 0, 'gpu_searches': 0}
    
    def create_index(self, name: str, dimension: int,
                     metric: DistanceMetric = DistanceMetric.COSINE,
                     use_gpu: Optional[bool] = None) -> VectorIndex:
        """
        Create new vector index.
        
        Args:
            name: Index name
            dimension: Vector dimension
            metric: Distance metric
            use_gpu: GPU setting (None=inherit from engine)
        
        Returns:
            Created index
        """
        with self._lock:
            if name in self._indexes:
                raise ValueError(f"Index {name} already exists")
            
            # Determine GPU setting
            gpu_setting = use_gpu if use_gpu is not None else self._global_use_gpu
            
            # Use GPU index if available and requested
            if gpu_setting is True and GPU_SUPPORT:
                try:
                    index = GPUVectorIndex(dimension, metric, use_gpu=True)
                    logger.info(f"[VectorSearch] Created GPU-accelerated index: {name}")
                except Exception as e:
                    logger.warning(f"[VectorSearch] GPU index failed, using CPU: {e}")
                    index = VectorIndex(dimension, metric, use_gpu=False)
            else:
                index = VectorIndex(dimension, metric, use_gpu=gpu_setting)
            
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
    
    def get_stats(self) -> Dict[str, Any]:
        """Get engine statistics including GPU usage."""
        with self._lock:
            stats = {
                'num_indexes': len(self._indexes),
                'gpu_available': GPU_SUPPORT,
                'global_use_gpu': self._global_use_gpu,
                'search_stats': self._gpu_stats.copy(),
                'indexes': {}
            }
            
            for name, index in self._indexes.items():
                idx_stats = index.get_stats()
                stats['indexes'][name] = idx_stats
                
                # Track GPU vs CPU usage
                if idx_stats.get('gpu_accelerated'):
                    self._gpu_stats['gpu_searches'] += 1
                else:
                    self._gpu_stats['cpu_searches'] += 1
            
            return stats
    
    def get_gpu_stats(self) -> Dict[str, Any]:
        """Get GPU-specific statistics."""
        return {
            'gpu_available': GPU_SUPPORT,
            'global_setting': self._global_use_gpu,
            'search_counts': self._gpu_stats.copy(),
            'indexes_using_gpu': sum(
                1 for idx in self._indexes.values() 
                if idx._gpu_index is not None
            )
        }


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


def create_vector_search_engine(use_gpu: Optional[bool] = None) -> VectorSearchEngine:
    """
    Factory function to create a vector search engine.
    
    Args:
        use_gpu: GPU setting (None=auto, True=force, False=disable)
    
    Returns:
        Configured VectorSearchEngine
    """
    if use_gpu is True and not GPU_SUPPORT:
        logger.warning("GPU acceleration requested but not available. Using CPU.")
    
    return VectorSearchEngine(use_gpu=use_gpu)


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
