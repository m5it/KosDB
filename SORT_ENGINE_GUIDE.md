# Sort Engine Integration Guide

## Overview

KosDB now includes a pluggable sort engine that supports multiple sorting backends for optimal `ORDER BY` performance. The sort engine automatically selects the best algorithm based on data characteristics and can be configured for specific workloads.

## Features

- **Multiple Backends**: Builtin (Timsort), madS0rt Python, madS0rt Rust
- **Automatic Selection**: Chooses optimal backend based on data size
- **Top-K Optimization**: Efficient `LIMIT` queries using heap algorithms
- **Query Optimization**: Integrated with query optimizer for sort planning
- **Configurable**: Environment variables, config files, and per-query overrides

## Quick Start

### Basic Usage

```python
from database import KosDB

# Auto-detect best sort engine
db = KosDB(data_dir="data")

# Execute queries with ORDER BY - automatically optimized
results = db.select("users", order_by="created_at", order_desc=True)
```

### Explicit Backend Selection

```python
from database import KosDB
from sort_engine import SortEngine

# Create database with specific sort engine
sort_engine = SortEngine(backend='madsort_rust')
db = KosDB(data_dir="data", sort_engine=sort_engine)
```

## Backends

### 1. Builtin (Timsort)
- **Best for**: Small datasets (< 1,000 rows)
- **Always available**: Yes
- **Stability**: Stable
- **Time complexity**: O(n log n)

### 2. madS0rt Python
- **Best for**: Medium datasets (1,000 - 100,000 rows)
- **Availability**: Requires `madsort` package
- **Optimized for**: Complex objects and custom key functions
- **Time complexity**: O(n log n) with lower constants

### 3. madS0rt Rust
- **Best for**: Large datasets (> 100,000 rows)
- **Availability**: Requires `madsort-rust` package
- **Performance**: Fastest for large datasets
- **Memory efficient**: Optimized memory layout

## Configuration

### Environment Variables

```bash
# Set default backend
export KOSDB_SORT_BACKEND=madsort_rust

# Enable/disable auto-fallback
export KOSDB_SORT_AUTO_FALLBACK=true

# Set thresholds (rows)
export KOSDB_SORT_SMALL_THRESHOLD=1000
export KOSDB_SORT_MEDIUM_THRESHOLD=100000

# Enable query optimizer heuristics
export KOSDB_SORT_ENABLE_HEURISTICS=true

# Top-K optimization threshold (0.1 = 10%)
export KOSDB_SORT_TOPK_THRESHOLD=0.1
```

### Configuration File

Create `kosdb.yaml`:

```yaml
sort:
  default_backend: auto
  auto_fallback: true
  strict_mode: false
  topk_threshold: 0.1
  small_threshold: 1000
  medium_threshold: 100000
  enable_heuristics: true
  enable_index_sort: true
  max_memory_mb: 100
```

Load in code:

```python
from sort_config import get_sort_config

config = get_sort_config('kosdb.yaml')
```

### Runtime Configuration

```python
from sort_config import SortConfig

# Create custom config
config = SortConfig(
    default_backend='madsort_py',
    small_dataset_threshold=500,
    topk_threshold=0.05
)

# Use with database
db = KosDB(data_dir="data")
db._sort_engine = SortEngine(backend=config.default_backend)
```

## Query Optimization

### Sort Strategy Selection

The query optimizer automatically selects the best sort strategy:

```python
from query_optimizer import QueryOptimizer, SortStrategy

optimizer = QueryOptimizer()

# Analyze query
plan = optimizer.optimize("SELECT * FROM users ORDER BY name LIMIT 10")

# Check sort strategy
print(plan.sort_strategy)
# {
#   'strategy': 'topk_heap',
#   'columns': [('name', False)],
#   'cost': 100.0,
#   'can_use_index': False,
#   'topk_optimized': True
# }
```

### Available Strategies

| Strategy | Description | Use Case |
|----------|-------------|----------|
| `BUILTIN` | Python Timsort | Small datasets |
| `MADSORT_PY` | madS0rt Python | Medium datasets |
| `MADSORT_RUST` | madS0rt Rust | Large datasets |
| `INDEX_SCAN` | Index order | When index covers ORDER BY |
| `TOPK_HEAP` | Heap algorithm | LIMIT queries |

## Performance Tuning

### Threshold Tuning

Adjust thresholds based on your workload:

```python
from sort_config import SortConfig

# For many small sorts
config = SortConfig(
    small_dataset_threshold=5000,  # Use builtin up to 5K rows
    medium_dataset_threshold=500000
)

# For few large sorts
config = SortConfig(
    small_dataset_threshold=100,
    medium_dataset_threshold=10000,
    large_dataset_threshold=100000
)
```

### Top-K Optimization

Enable for LIMIT queries:

```python
# Automatically uses heap for "LIMIT 10" on 1000+ rows
config = SortConfig(topk_threshold=0.01)  # 1% threshold
```

### Index-Based Sorting

Create indexes to avoid sorting:

```python
# Index eliminates sort for: ORDER BY user_id, created_at
db.create_index("orders", ["user_id", "created_at"])
```

## Benchmarking

Run benchmarks to compare backends:

```bash
# Quick benchmark (small datasets)
python benchmark_sort.py

# Full benchmark (all dataset sizes)
python benchmark_sort.py --full
```

Output:
```
INTEGER_SORT
----------------------------------------------------------------------
      Size        Backend    Time (ms)        Rows/sec
----------------------------------------------------------------------
     1,000        builtin         0.12         833,333
     1,000      madsort_py         0.10       1,000,000
    10,000        builtin         1.50       6,666,667
    10,000      madsort_py         1.20       8,333,333
   100,000        builtin        20.00       5,000,000
   100,000      madsort_py        15.00       6,666,667
   100,000    madsort_rust        10.00      10,000,000
```

## API Reference

### SortEngine

```python
class SortEngine:
    def __init__(self, backend: str = 'auto', strict: bool = False)
    def sort(self, values, key=None, reverse=False, stable=True, topk=None) -> List
    def sort_in_place(self, values, key=None, reverse=False, stable=True)
    @property
    def backend_name(self) -> str
```

### SortConfig

```python
@dataclass
class SortConfig:
    default_backend: str = 'auto'
    auto_fallback: bool = True
    strict_mode: bool = False
    topk_threshold: float = 0.1
    small_dataset_threshold: int = 1000
    medium_dataset_threshold: int = 100000
    large_dataset_threshold: int = 1000000
    enable_sort_heuristics: bool = True
    enable_index_sort: bool = True
    cache_sort_plans: bool = True
    max_memory_sort_mb: int = 100
```

### QueryOptimizer

```python
class QueryOptimizer:
    def optimize(self, query: str) -> ExecutionPlan
    def _optimize_order_by(self, plan, order_by_columns, limit=None)
    def _can_use_index_for_order(self, table, order_by_columns) -> bool
```

## Troubleshooting

### Backend Not Available

```python
from sort_engine import detect_available_backends

# Check available backends
print(detect_available_backends())
# {'builtin': True, 'madsort_py': False, 'madsort_rust': False}

# Install madS0rt
# pip install madsort
# pip install madsort-rust  # if available
```

### Sort Performance Issues

1. **Check current backend**:
   ```python
   print(db.sort_engine.backend_name)
   ```

2. **Verify thresholds**:
   ```python
   from sort_config import get_sort_config
   config = get_sort_config()
   print(config.small_dataset_threshold)
   ```

3. **Run benchmarks**:
   ```bash
   python benchmark_sort.py
   ```

### Fallback Behavior

When `auto_fallback=True` (default):
- Sort engine errors are caught
- Automatically falls back to builtin sort
- Warning logged

When `strict_mode=True`:
- Sort engine errors propagate
- Useful for debugging

## Migration Guide

### From Previous KosDB Versions

No changes required - sort engine is automatic:

```python
# Existing code continues to work
db = KosDB(data_dir="data")
results = db.select("users", order_by="name")
```

### Opt-in to madS0rt

```python
# Option 1: Environment variable
import os
os.environ['KOSDB_SORT_BACKEND'] = 'madsort_rust'

db = KosDB(data_dir="data")

# Option 2: Explicit configuration
from sort_config import SortConfig, get_sort_config

config = SortConfig(default_backend='madsort_rust')
# Save to file or use directly
```

## Examples

### Example 1: E-commerce Sorting

```python
from database import KosDB
from sort_config import SortConfig

# Optimize for product listings (many small sorts)
config = SortConfig(
    default_backend='auto',
    small_dataset_threshold=5000,
    topk_threshold=0.05  # Aggressive top-K for pagination
)

db = KosDB(data_dir="ecommerce")

# Product listing with pagination - uses top-K optimization
products = db.select(
    "products",
    where={"category": "electronics"},
    order_by="price",
    order_desc=True,
    limit=20
)
```

### Example 2: Analytics Query

```python
from database import KosDB
from sort_engine import SortEngine

# Large dataset - force madS0rt Rust
sort_engine = SortEngine(backend='madsort_rust')
db = KosDB(data_dir="analytics", sort_engine=sort_engine)

# Large aggregation result
results = db.select(
    "events",
    columns=["user_id", "COUNT(*) as count"],
    group_by="user_id",
    order_by="count",
    order_desc=True,
    limit=1000
)
```

### Example 3: Custom Sort Function

```python
from database import KosDB

db = KosDB(data_dir="data")

# Complex sort with custom key
def priority_score(record):
    return record['priority'] * 10 + record['urgency']

# Get all records
all_records = db.select("tasks")

# Sort with custom key (uses configured sort engine)
from sort_engine import get_sort_engine
engine = get_sort_engine()
sorted_records = engine.sort(all_records, key=priority_score, reverse=True)
```

## Best Practices

1. **Use `auto` backend**: Let the engine choose based on data size
2. **Enable top-K**: Set `topk_threshold` based on your typical LIMIT ratios
3. **Create indexes**: For frequently sorted columns
4. **Benchmark**: Run benchmarks on your actual data
5. **Monitor fallback**: Check `sort_engine.fallback_count` for issues

## Contributing

To add a new sort backend:

1. Create backend class in `sort_backends/`
2. Inherit from `SortBackend`
3. Implement `sort()` and `sort_in_place()`
4. Add to `SortEngine.BACKENDS`
5. Update `detect_available_backends()`

See `sort_backends/builtin.py` for reference implementation.
