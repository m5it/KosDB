
# Batch Vector Search Guide

Version: 2.3.0  
Last Updated: 2024-01-15

## Overview

Batch Vector Search provides efficient batch operations for vector similarity search, enabling high-throughput embedding ingestion and multi-query search. Features include GPU acceleration, IVF index optimization, and hybrid metadata filtering.

## Features

- **Batch Vector Add**: High-throughput embedding ingestion
- **Batch Vector Search**: Multiple queries in parallel
- **Batch Vector Delete**: Bulk document removal
- **GPU Acceleration**: CUDA-accelerated batch operations
- **IVF Optimization**: Automatic index updates for large batches
- **Hybrid Search**: Vector similarity + metadata filtering

## Quick Start

```python
from batch_vector_search import BatchVectorSearchManager, get_batch_vector_manager
from vector_search import VectorSearchEngine

# Create engine and manager
engine = VectorSearchEngine()
manager = get_batch_vector_manager(engine)

# Batch add vectors
documents = [
    ('doc1', [0.1, 0.2, 0.3], {'category': 'A'}),
    ('doc2', [0.4, 0.5, 0.6], {'category': 'B'}),
    ('doc3', [0.7, 0.8, 0.9], {'category': 'A'}),
]

result = manager.batch_add('my_index', documents)
print(f"Added {result.added} vectors in {result.elapsed_ms:.2f}ms")
```

## SQL Commands

### VECTOR ADD BATCH

```sql
-- Batch add embeddings
VECTOR ADD BATCH my_index [
    ('doc1', [0.1, 0.2, 0.3], {'category': 'article', 'lang': 'en'}),
    ('doc2', [0.4, 0.5, 0.6], {'category': 'blog', 'lang': 'en'}),
    ('doc3', [0.7, 0.8, 0.9], {'category': 'article', 'lang': 'fr'})
];

-- Add without metadata
VECTOR ADD BATCH embeddings [
    ('vec1', [0.1, 0.2, 0.3]),
    ('vec2', [0.4, 0.5, 0.6])
];
```

### VECTOR SEARCH BATCH

```sql
-- Search multiple queries at once
VECTOR SEARCH BATCH my_index [
    ('query1', [0.1, 0.2, 0.3]),
    ('query2', [0.4, 0.5, 0.6]),
    ('query3', [0.7, 0.8, 0.9])
] LIMIT 10;
```

## Batch Vector Add

### Basic Usage

```python
from batch_vector_search import BatchVectorSearchManager

manager = BatchVectorSearchManager(engine)

# Prepare documents
documents = [
    ('id1', embedding1, {'title': 'Document 1'}),
    ('id2', embedding2, {'title': 'Document 2'}),
    # ... more documents
]

# Batch add with GPU acceleration
result = manager.batch_add(
    index_name='my_index',
    documents=documents,
    use_gpu=True,
    batch_size=1000
)

print(f"Added: {result.added}")
print(f"Failed: {result.failed}")
print(f"Time: {result.elapsed_ms:.2f}ms")
print(f"IVF updates: {result.index_updates}")
```

### Performance Benchmarks

| Batch Size | CPU (docs/sec) | GPU (docs/sec) |
|------------|----------------|----------------|
| 100 | 5,000 | 10,000 |
| 1,000 | 8,000 | 50,000 |
| 10,000 | 10,000 | 100,000 |

### GPU Acceleration

```python
# GPU automatically used for large batches
result = manager.batch_add(
    'my_index',
    documents,
    use_gpu=True  # Requires CUDA-capable GPU
)

# Check GPU operations
metrics = manager.get_metrics()
print(f"GPU operations: {metrics['gpu_operations']}")
```

## Batch Vector Search

### Multiple Query Search

```python
# Prepare queries
queries = [
    ('query1', [0.1, 0.2, 0.3]),
    ('query2', [0.4, 0.5, 0.6]),
    ('query3', [0.7, 0.8, 0.9]),
]

# Batch search
results = manager.batch_search(
    index_name='my_index',
    queries=queries,
    k=10,
    use_gpu=True,
    parallel=True  # Use ThreadPoolExecutor
)

for result in results:
    print(f"Query {result.query_id}: {len(result.results)} results")
    print(f"Time: {result.elapsed_ms:.2f}ms")
```

### GPU Batch Search

```python
# GPU batch search for multiple queries
results = manager.batch_search(
    'my_index',
    queries,
    k=10,
    use_gpu=True  # Computes all similarities in parallel on GPU
)
```

## Hybrid Batch Search

### Vector + Metadata Filtering

```python
# Define metadata filter
def metadata_filter(metadata):
    return metadata.get('category') == 'article'

# Hybrid search
queries = [
    ('q1', [0.1, 0.2, 0.3], {'category': 'article'}),
    ('q2', [0.4, 0.5, 0.6], {'category': 'blog'}),
]

results = manager.hybrid_batch_search(
    index_name='my_index',
    queries=queries,
    k=10,
    metadata_filter=metadata_filter
)

for result in results:
    print(f"Vector results: {len(result.vector_results)}")
    print(f"After metadata filter: {len(result.final_results)}")
```

## Batch Vector Delete

### Bulk Document Removal

```python
# Documents to delete
doc_ids = ['doc1', 'doc2', 'doc3', 'doc4', 'doc5']

# Batch delete
result = manager.batch_delete('my_index', doc_ids)

print(f"Deleted: {result.deleted}")
print(f"Not found: {result.not_found}")
print(f"Time: {result.elapsed_ms:.2f}ms")
```

## IVF Index Optimization

### Automatic Updates

```python
# When adding >1000 vectors, IVF index is automatically retrained
result = manager.batch_add('my_index', large_batch)

print(f"IVF clusters updated: {result.index_updates}")
```

### Manual Training

```python
# Force IVF retraining after batch operations
index = engine.get_index('my_index')
index.train_ivf(n_clusters=100)
```

## Use Cases

### Embedding Ingestion Pipeline

```python
def ingest_embeddings(documents, batch_size=1000):
    """
    High-throughput embedding ingestion pipeline.
    """
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i + batch_size]
        
        # Convert to vectors (using your embedding model)
        vectors = [
            (doc['id'], embed(doc['text']), doc['metadata'])
            for doc in batch
        ]
        
        # Batch add with GPU
        result = manager.batch_add(
            'embeddings_index',
            vectors,
            use_gpu=True
        )
        
        print(f"Batch {i//batch_size}: {result.added} docs, "
              f"{result.elapsed_ms:.2f}ms")
```

### Multi-Query Search

```python
def search_similar_items(items, k=10):
    """
    Find similar items for multiple queries.
    """
    # Generate embeddings for all items
    queries = [
        (item['id'], embed(item['text']))
        for item in items
    ]
    
    # Batch search
    results = manager.batch_search(
        'items_index',
        queries,
        k=k,
        use_gpu=True
    )
    
    return {
        r.query_id: r.results
        for r in results
    }
```

### RAG Document Retrieval

```python
def retrieve_contexts(queries, metadata_filter=None):
    """
    Retrieve relevant documents for RAG.
    """
    # Convert queries to embeddings
    query_vectors = [
        (q['id'], embed(q['text']))
        for q in queries
    ]
    
    # Hybrid search with metadata filtering
    results = manager.hybrid_batch_search(
        'documents_index',
        query_vectors,
        k=5,
        metadata_filter=metadata_filter
    )
    
    # Extract document texts
    contexts = []
    for result in results:
        doc_texts = [
            engine.get_index('documents_index')._documents[doc_id].metadata['text']
            for doc_id, _ in result.final_results
        ]
        contexts.append({
            'query_id': result.query_id,
            'contexts': doc_texts
        })
    
    return contexts
```

## Best Practices

### 1. Use Appropriate Batch Sizes

```python
# Too small: High overhead
manager.batch_add('index', docs, batch_size=10)  # Inefficient

# Optimal: Balance throughput and memory
manager.batch_add('index', docs, batch_size=1000)  # Good

# Too large: Memory pressure
manager.batch_add('index', docs, batch_size=100000)  # Risky
```

### 2. Leverage GPU for Large Batches

```python
# GPU threshold is automatic (100+ vectors)
# But you can control it
if len(docs) > 100:
    result = manager.batch_add('index', docs, use_gpu=True)
else:
    result = manager.batch_add('index', docs, use_gpu=False)
```

### 3. Monitor Metrics

```python
metrics = manager.get_metrics()

print(f"Batch adds: {metrics['batch_adds']}")
print(f"Batch searches: {metrics['batch_searches']}")
print(f"GPU operations: {metrics['gpu_operations']}")
print(f"Total vectors added: {metrics['total_vectors_added']}")
```

### 4. Handle Failures Gracefully

```python
result = manager.batch_add('index', documents)

if result.failed > 0:
    failure_rate = result.failed / (result.added + result.failed)
    
    if failure_rate > 0.01:  # >1% failed
        logger.error(f"High failure rate: {failure_rate:.2%}")
        # Investigate and retry failed documents
```

## Performance Tuning

### GPU Memory Management

```python
# Reduce batch size if GPU OOM
try:
    result = manager.batch_add('index', large_batch, batch_size=10000)
except RuntimeError as e:
    if "out of memory" in str(e):
        result = manager.batch_add('index', large_batch, batch_size=1000)
```

### Parallel Search

```python
# Use parallel=True for independent queries
results = manager.batch_search(
    'index',
    queries,
    k=10,
    parallel=True  # Uses ThreadPoolExecutor
)
```

## Integration with Batch Executor

```python
from batch_executor import BatchExecutor
from batch_vector_search import get_batch_vector_manager

# Create components
engine = VectorSearchEngine()
manager = get_batch_vector_manager(engine)
executor = BatchExecutor(parser, registry)

# Execute vector batch commands
commands = [
    "VECTOR ADD BATCH my_index [('doc1', [0.1, 0.2, 0.3])]",
    "VECTOR SEARCH BATCH my_index [('q1', [0.1, 0.2, 0.3])] LIMIT 5",
]

result = executor.execute_batch(commands, client_state={})
```

## Troubleshooting

### Low GPU Utilization

**Symptoms**: GPU not being used despite `use_gpu=True`

**Check**:
1. GPU available: `GPU_AVAILABLE`
2. Batch size >= 100
3. CUDA drivers installed

### IVF Not Updating

**Symptoms**: Search performance degrades after large ingestion

**Solution**: Check `result.index_updates` after batch_add. If 0, manually retrain:
```python
if result.added > 1000 and result.index_updates == 0:
    index.train_ivf(n_clusters=100)
```

## See Also

- [Vector Search](vector_search.py)
- [GPU Vector Operations](gpu_vector_ops.py)
- [Batch Operations](OPERATIONS.md)
