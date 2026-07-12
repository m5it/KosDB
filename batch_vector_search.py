
"""
Batch Vector Search Operations for KosDB v2.3.0

Provides batch operations for vector similarity search:
- Batch vector add: VECTOR ADD BATCH
- Batch vector search with multiple queries
- Batch vector delete operations
- Optimized IVF index updates for batch
- Hybrid batch search (vector + metadata)
- GPU acceleration for batch operations
"""

import re
import time
import logging
from typing import Dict, List, Optional, Any, Tuple, Callable, Union
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import vector search support
try:
    from vector_search import (
        VectorSearchEngine, VectorIndex, VectorDocument,
        DistanceMetric
    )
    VECTOR_AVAILABLE = True
except ImportError:
    VECTOR_AVAILABLE = False

# Import GPU support
try:
    from gpu_vector_ops import GPUVectorOps, get_gpu_ops
    GPU_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class BatchVectorAddResult:
    """Result of batch vector add operation."""
    added: int
    failed: int
    elapsed_ms: float
    index_updates: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'added': self.added,
            'failed': self.failed,
            'elapsed_ms': self.elapsed_ms,
            'index_updates': self.index_updates
        }


@dataclass
class BatchVectorSearchResult:
    """Result of batch vector search."""
    query_id: str
    results: List[Tuple[str, float]]
    elapsed_ms: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'query_id': self.query_id,
            'results': self.results,
            'elapsed_ms': self.elapsed_ms
        }


@dataclass
class BatchVectorDeleteResult:
    """Result of batch vector delete."""
    deleted: int
    not_found: int
    elapsed_ms: float


@dataclass
class HybridSearchResult:
    """Result of hybrid vector + metadata search."""
    vector_results: List[Tuple[str, float]]
    metadata_filtered: List[str]
    final_results: List[Tuple[str, float]]
    elapsed_ms: float


class BatchVectorSearchManager:
    """Manager for batch vector search operations."""
    
    def __init__(self, vector_engine: Optional[Any] = None):
        self.vector_engine = vector_engine
        self._metrics = {
            'batch_adds': 0,
            'batch_searches': 0,
            'batch_deletes': 0,
            'hybrid_searches': 0,
            'total_vectors_added': 0,
            'total_vectors_searched': 0,
            'gpu_operations': 0
        }
        self._gpu_ops = get_gpu_ops() if GPU_AVAILABLE else None
    
    def batch_add(
        self,
        index_name: str,
        documents: List[Tuple[str, List[float], Optional[Dict[str, Any]]]],
        use_gpu: bool = True,
        batch_size: int = 1000
    ) -> BatchVectorAddResult:
        """Batch add vectors to index."""
        if not VECTOR_AVAILABLE or not self.vector_engine:
            return BatchVectorAddResult(
                added=0, failed=len(documents), elapsed_ms=0, index_updates=0
            )
        
        start_time = time.time()
        added = 0
        failed = 0
        
        # Get or create index
        index = self.vector_engine.get_index(index_name)
        if not index:
            if documents:
                dim = len(documents[0][1])
                self.vector_engine.create_index(index_name, dimension=dim)
                index = self.vector_engine.get_index(index_name)
        
        if not index:
            return BatchVectorAddResult(
                added=0, failed=len(documents), elapsed_ms=0, index_updates=0
            )
        
        # Process in batches
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            
            if use_gpu and GPU_AVAILABLE and self._gpu_ops and len(batch) >= 100:
                batch_added, batch_failed = self._gpu_batch_add(index, batch)
            else:
                batch_added, batch_failed = self._cpu_batch_add(index, batch)
            
            added += batch_added
            failed += batch_failed
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        # Update IVF index
        index_updates = 0
        if hasattr(index, '_is_trained') and index._is_trained:
            index_updates = self._update_ivf_index(index, added)
        
        self._metrics['batch_adds'] += 1
        self._metrics['total_vectors_added'] += added
        
        return BatchVectorAddResult(
            added=added,
            failed=failed,
            elapsed_ms=elapsed_ms,
            index_updates=index_updates
        )
    
    def _cpu_batch_add(
        self,
        index: Any,
        batch: List[Tuple[str, List[float], Optional[Dict]]]
    ) -> Tuple[int, int]:
        """CPU batch add."""
        added = 0
        failed = 0
        
        for doc_id, vector, metadata in batch:
            try:
                if index.add(doc_id, vector, metadata):
                    added += 1
                else:
                    failed += 1
            except Exception as e:
                logger.warning(f"Failed to add vector {doc_id}: {e}")
                failed += 1
        
        return added, failed
    
    def _gpu_batch_add(
        self,
        index: Any,
        batch: List[Tuple[str, List[float], Optional[Dict]]]
    ) -> Tuple[int, int]:
        """GPU-accelerated batch add."""
        vectors = [v for _, v, _ in batch]
        
        try:
            if index.metric == DistanceMetric.COSINE:
                normalized = self._gpu_ops.normalize_batch(vectors)
            else:
                normalized = vectors
            
            added = 0
            for i, (doc_id, _, metadata) in enumerate(batch):
                try:
                    index.add(doc_id, normalized[i], metadata)
                    added += 1
                except Exception as e:
                    logger.warning(f"Failed to add vector {doc_id}: {e}")
            
            self._metrics['gpu_operations'] += 1
            return added, len(batch) - added
            
        except Exception as e:
            logger.warning(f"GPU batch add failed, falling back to CPU: {e}")
            return self._cpu_batch_add(index, batch)
    
    def _update_ivf_index(self, index: Any, num_new_vectors: int) -> int:
        """Update IVF index after batch add."""
        if num_new_vectors > 1000:
            try:
                n_clusters = min(100, max(10, num_new_vectors // 100))
                index.train_ivf(n_clusters)
                return n_clusters
            except Exception as e:
                logger.warning(f"IVF update failed: {e}")
        return 0
    
    def batch_search(
        self,
        index_name: str,
        queries: List[Tuple[str, List[float]]],
        k: int = 10,
        use_gpu: bool = True,
        parallel: bool = False
    ) -> List[BatchVectorSearchResult]:
        """Batch search with multiple query vectors."""
        if not VECTOR_AVAILABLE or not self.vector_engine:
            return []
        
        index = self.vector_engine.get_index(index_name)
        if not index:
            return []
        
        results = []
        
        if parallel and len(queries) > 1:
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {
                    executor.submit(
                        self._search_single, index, query_id, vector, k, use_gpu
                    ): query_id
                    for query_id, vector in queries
                }
                
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        results.append(result)
        else:
            if use_gpu and GPU_AVAILABLE and self._gpu_ops and len(queries) >= 10:
                results = self._gpu_batch_search(index, queries, k)
            else:
                for query_id, vector in queries:
                    result = self._search_single(index, query_id, vector, k, use_gpu)
                    if result:
                        results.append(result)
        
        self._metrics['batch_searches'] += 1
        self._metrics['total_vectors_searched'] += len(queries)
        
        return results
    
    def _search_single(
        self,
        index: Any,
        query_id: str,
        vector: List[float],
        k: int,
        use_gpu: bool
    ) -> Optional[BatchVectorSearchResult]:
        """Search single query."""
        start_time = time.time()
        
        try:
            search_results = index.search(vector, k=k)
            elapsed_ms = (time.time() - start_time) * 1000
            
            return BatchVectorSearchResult(
                query_id=query_id,
                results=search_results,
                elapsed_ms=elapsed_ms
            )
        except Exception as e:
            logger.warning(f"Search failed for {query_id}: {e}")
            return None
    
    def _gpu_batch_search(
        self,
        index: Any,
        queries: List[Tuple[str, List[float]]],
        k: int
    ) -> List[BatchVectorSearchResult]:
        """GPU-accelerated batch search."""
        start_time = time.time()
        results = []
        
        try:
            doc_vectors = [doc.vector for doc in index._documents.values()]
            doc_ids = list(index._documents.keys())
            
            if not doc_vectors:
                return results
            
            query_vectors = [v for _, v in queries]
            
            if index.metric == DistanceMetric.COSINE:
                similarities = self._gpu_ops.cosine_similarity_matrix(
                    query_vectors, doc_vectors
                )
            elif index.metric == DistanceMetric.EUCLIDEAN:
                distances = self._gpu_ops.euclidean_distance_matrix(
                    query_vectors, doc_vectors
                )
                similarities = [[-d for d in row] for row in distances]
            else:
                return [self._search_single(index, qid, vec, k, False) 
                       for qid, vec in queries]
            
            for i, (query_id, _) in enumerate(queries):
                scores = similarities[i]
                indexed_scores = [(doc_ids[j], scores[j]) 
                                for j in range(len(doc_ids))]
                indexed_scores.sort(key=lambda x: x[1], reverse=True)
                
                results.append(BatchVectorSearchResult(
                    query_id=query_id,
                    results=indexed_scores[:k],
                    elapsed_ms=(time.time() - start_time) * 1000 / len(queries)
                ))
            
            self._metrics['gpu_operations'] += 1
            
        except Exception as e:
            logger.warning(f"GPU batch search failed: {e}")
            return [self._search_single(index, qid, vec, k, False) 
                   for qid, vec in queries]
        
        return results
    
    def batch_delete(
        self,
        index_name: str,
        doc_ids: List[str]
    ) -> BatchVectorDeleteResult:
        """Batch delete vectors from index."""
        if not VECTOR_AVAILABLE or not self.vector_engine:
            return BatchVectorDeleteResult(
                deleted=0, not_found=len(doc_ids), elapsed_ms=0
            )
        
        start_time = time.time()
        index = self.vector_engine.get_index(index_name)
        
        if not index:
            return BatchVectorDeleteResult(
                deleted=0, not_found=len(doc_ids), elapsed_ms=0
            )
        
        deleted = 0
        not_found = 0
        
        for doc_id in doc_ids:
            try:
                if index.remove(doc_id):
                    deleted += 1
                else:
                    not_found += 1
            except Exception as e:
                logger.warning(f"Failed to delete {doc_id}: {e}")
                not_found += 1
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        self._metrics['batch_deletes'] += 1
        
        return BatchVectorDeleteResult(
            deleted=deleted,
            not_found=not_found,
            elapsed_ms=elapsed_ms
        )
    
    def hybrid_batch_search(
        self,
        index_name: str,
        queries: List[Tuple[str, List[float], Dict[str, Any]]],
        k: int = 10,
        metadata_filter: Optional[Callable] = None
    ) -> List[HybridSearchResult]:
        """Hybrid batch search with vector similarity + metadata filtering."""
        if not VECTOR_AVAILABLE or not self.vector_engine:
            return []
        
        index = self.vector_engine.get_index(index_name)
        if not index:
            return []
        
        results = []
        
        for query_id, vector, meta_filter in queries:
            start_time = time.time()
            

def parse_vector_add_batch(command: str) -> Tuple[Optional[str], List[Tuple]]:
    """Parse VECTOR ADD BATCH command."""
    cmd = command.strip()
    
    match = re.match(r'VECTOR\s+ADD\s+BATCH\s+(\w+)', cmd, re.IGNORECASE)
    if not match:
        return None, []
    
    index_name = match.group(1)
    
    values_match = re.search(r'\[(.*)\]', cmd, re.DOTALL)
    if not values_match:
        return index_name, []
    
    values_str = values_match.group(1)
    documents = []
    
    tuple_pattern = r"\(\s*'([^']+)'\s*,\s*\[([^\]]+)\](?:\s*,\s*(\{[^}]*\}))?\s*\)"
    
    for m in re.finditer(tuple_pattern, values_str):
        doc_id = m.group(1)
        vector_str = m.group(2)
        metadata_str = m.group(3) or '{}'
        
        try:
            vector = [float(x.strip()) for x in vector_str.split(',')]
        except ValueError:
            continue
        
        metadata = {}
        if metadata_str and metadata_str != '{}':
            pairs = re.findall(r"'([^']+)':\s*'([^']+)'", metadata_str)
            for k, v in pairs:
                metadata[k] = v
        
        documents.append((doc_id, vector, metadata))
    
    return index_name, documents
def _extract_bracket_content(s: str, start_char: str = '[', end_char: str = ']') -> Optional[str]:
    """Extract content from balanced brackets."""
    start = s.find(start_char)
    if start == -1:
        return None
    
    count = 0
    for i in range(start, len(s)):
        if s[i] == start_char:
            count += 1
        elif s[i] == end_char:
            count -= 1
            if count == 0:
                return s[start+1:i]
    return None


def parse_vector_search_batch(command: str) -> Dict[str, Any]:
    """Parse batch vector search command."""
    # Match VECTOR SEARCH BATCH index_name
    index_match = re.search(r'VECTOR\s+SEARCH\s+BATCH\s+(\w+)', command, re.IGNORECASE)
    if not index_match:
        return {}
    
    index_name = index_match.group(1)
    rest = command[index_match.end():]
    
    # Extract balanced bracket content
    queries_str = _extract_bracket_content(rest)
    if queries_str is None:
        return {'index_name': index_name, 'queries': [], 'k': 10}
    
    # Parse limit from after the closing bracket
    closing_pos = rest.find(']')
    after_bracket = rest[closing_pos+1:] if closing_pos != -1 else ''
    limit_match = re.search(r'LIMIT\s+(\d+)', after_bracket, re.IGNORECASE)
    k = int(limit_match.group(1)) if limit_match else 10
    
    # Parse individual queries
    queries = []
    query_pattern = r"\(\s*'([^']+)'\s*,\s*\[([^\]]+)\]\s*\)"
    
    for m in re.finditer(query_pattern, queries_str):
        query_id = m.group(1)
        vector_str = m.group(2)
        try:
            vector = [float(x.strip()) for x in vector_str.split(',')]
            queries.append((query_id, vector))
        except ValueError:
            continue
    
    return {
        'index_name': index_name,
        'queries': queries,
        'k': k
    }
    
    for m in re.finditer(query_pattern, queries_str):
        query_id = m.group(1)
        vector_str = m.group(2)
        try:
            vector = [float(x.strip()) for x in vector_str.split(',')]
            queries.append((query_id, vector))
        except ValueError:
            continue
    
    return {
        'index_name': index_name,
        'queries': queries,
        'k': k
    }


# Global manager
_batch_vector_manager: Optional[BatchVectorSearchManager] = None


def get_batch_vector_manager(vector_engine: Optional[Any] = None) -> BatchVectorSearchManager:
    """Get global batch vector search manager."""
    global _batch_vector_manager
    if _batch_vector_manager is None:
        _batch_vector_manager = BatchVectorSearchManager(vector_engine)
    return _batch_vector_manager
