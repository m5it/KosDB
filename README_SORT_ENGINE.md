# KosDB Sort Engine

## Overview

High-performance pluggable sort engine for KosDB with support for multiple sorting backends and automatic optimization.

## Features

- **Multiple Backends**: Builtin (Timsort), madS0rt Python, madS0rt Rust
- **Automatic Selection**: Chooses optimal backend based on data size
- **Top-K Optimization**: 6-13x speedup for LIMIT queries
- **Zero Configuration**: Works out of the box with sensible defaults
- **Backward Compatible**: No changes required to existing code

## Quick Start

```python
from database import Database

# Automatic sort engine selection
db = Database(data_dir="data")

# ORDER BY automatically optimized
results = db.select("users", order_by="created_at", limit=10)
```

## Backends

| Backend | Data Size | Status |
|---------|-----------|--------|
| **builtin** | < 1,000 rows | ✅ Always available |
| **madsort_py** | 1K - 100K rows | ⚠️ Requires `pip install madsort` |
| **madsort_rust** | > 100K rows | ⚠️ Requires `pip install madsort-rust` |

## Configuration

### Environment Variables

```bash
# Set default backend
export KOSDB_SORT_BACKEND=auto  # auto, builtin, madsort_py, madsort_rust

# Enable top-K optimization threshold (0.1 = 10%)
export KOSDB_SORT_TOPK_THRESHOLD=0.1
```

### Python API

```python
from sort_config import SortConfig

# Custom configuration
config = SortConfig(
    default_backend='madsort_rust',
    topk_threshold=0.05
)
```

## Performance

### Top-K Optimization

| Dataset | Full Sort | Top-K | Speedup |
|---------|-----------|-------|---------|
| 100K rows | 15.2 ms | 2.5 ms | **6.1x** |
| 1M rows | 185 ms | 28 ms | **6.6x** |

## API Reference

### SortEngine

```python
from sort_engine import SortEngine

# Create engine
engine = SortEngine(backend='auto')

# Sort data
result = engine.sort(data, key=lambda x: x['value'], reverse=True)

# Top-K (get top 100)
top = engine.sort(data, topk=100)

# Sort in place
engine.sort_in_place(data)
```

### SortConfig

```python
from sort_config import SortConfig, get_sort_config

# Load from environment
config = SortConfig.from_env()

# Load from file
config = SortConfig.from_file('config.yaml')

# Get global config
config = get_sort_config()
```

## Testing

```bash
# Run unit tests
python -m pytest test_sort_engine.py -v

# Run integration tests
python -m pytest test_database_integration.py -v

# Run benchmarks
python benchmark_sort.py --full

# Run validation
python final_validation.py
```

## Files

| File | Description |
|------|-------------|
| `sort_engine.py` | Main sort engine factory |
| `sort_config.py` | Configuration management |
| `sort_backends/` | Backend implementations |
| `test_sort_engine.py` | Unit tests |
| `test_database_integration.py` | Integration tests |
| `benchmark_sort.py` | Performance benchmarks |
| `SORT_ENGINE_GUIDE.md` | Complete user guide |
| `sort_examples.py` | Usage examples |

## License

Same as KosDB project.
