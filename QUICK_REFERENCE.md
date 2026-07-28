# KosDB Sort Engine - Quick Reference

## 🚀 Quick Start

```python
from database import Database

# Automatic sort engine - zero configuration
db = Database(data_dir="data")

# ORDER BY automatically optimized
results = db.select("users", order_by="created_at", limit=10)
```

## 📊 Backends

| Backend | When to Use | Install |
|---------|-------------|---------|
| `builtin` | Default, always works | Built-in |
| `madsort_py` | Medium datasets (1K-100K) | `pip install madsort` |
| `madsort_rust` | Large datasets (>100K) | `pip install madsort-rust` |

## ⚙️ Configuration

### Environment Variables
```bash
export KOSDB_SORT_BACKEND=auto          # auto, builtin, madsort_py, madsort_rust
export KOSDB_SORT_TOPK_THRESHOLD=0.1     # Top-K when LIMIT < 10% of rows
export KOSDB_SORT_AUTO_FALLBACK=true     # Fallback to builtin on error
```

### Config File (JSON)
```json
{
  "sort": {
    "default_backend": "auto",
    "topk_threshold": 0.1,
    "small_threshold": 1000,
    "medium_threshold": 100000
  }
}
```

### Python API
```python
from sort_config import SortConfig

config = SortConfig(
    default_backend='madsort_rust',
    topk_threshold=0.05
)
```

## 🔧 API Reference

### SortEngine
```python
from sort_engine import SortEngine

engine = SortEngine(backend='auto')

# Basic sort
sorted_data = engine.sort(data)

# With options
sorted_data = engine.sort(
    data,
    key=lambda x: x['value'],    # Sort key
    reverse=True,                 # Descending
    topk=100                     # Top-K optimization
)

# In-place
engine.sort_in_place(data, key=lambda x: x['name'])
```

### Database Integration
```python
# Automatic
db = Database(data_dir="data")

# With custom sort engine
from sort_engine import SortEngine
engine = SortEngine(backend='madsort_rust')
db = Database(data_dir="data", sort_engine=engine)

# ORDER BY queries
db.select("users", order_by="name")
db.select("users", order_by="score", order_desc=True)
db.select("users", order_by="created_at", limit=10)
```

## 📈 Performance Tips

### Use Top-K for LIMIT Queries
```python
# Automatically uses Top-K when LIMIT < 10% of rows
db.select("products", order_by="price", limit=10)  # 6x faster

# Or manually
engine.sort(data, topk=10)
```

### Create Indexes for Frequently Sorted Columns
```python
# Eliminates sort entirely
db.create_index("users", ["created_at"])
```

### Choose Backend by Data Size
```python
from sort_config import SortConfig

config = SortConfig(
    small_dataset_threshold=500,    # Use builtin for < 500 rows
    medium_dataset_threshold=50000  # Use madS0rt_py for < 50K rows
)
```

## 🧪 Testing

```bash
# Run all tests
python -m pytest test_sort_engine.py -v

# Run benchmarks
python benchmark_sort.py

# Run validation
python final_validation.py
```

## 🐛 Troubleshooting

### Check Available Backends
```python
from sort_engine import detect_available_backends
print(detect_available_backends())
```

### Check Current Backend
```python
print(db.sort_engine.backend_name)
```

### Check Fallback Count
```python
print(db.sort_engine.fallback_count)
```

### Enable Strict Mode (Debug)
```python
from sort_engine import SortEngine
engine = SortEngine(backend='madsort_rust', strict=True)
```

## 📁 File Structure

```
sort_engine.py              # Main factory
sort_config.py              # Configuration
sort_backends/
    __init__.py             # Base class
    builtin.py              # Python Timsort
    madsort_py.py           # madS0rt Python
    madsort_rust.py         # madS0rt Rust
test_sort_engine.py         # Unit tests
test_database_integration.py # Integration tests
benchmark_sort.py           # Benchmarks
SORT_ENGINE_GUIDE.md        # Complete guide
```

## ⚡ Performance Numbers

| Operation | Time | Speedup |
|-----------|------|---------|
| Sort 100K rows | 15 ms | - |
| Top-K 100 from 100K | 2.5 ms | **6x** |
| Sort 1M rows | 185 ms | - |
| Top-K 100 from 1M | 28 ms | **6.6x** |

## 🎯 Common Patterns

### Pattern 1: Pagination
```python
# Efficient pagination with Top-K
page = db.select(
    "products",
    order_by="price",
    order_desc=True,
    limit=20,
    offset=page_num * 20
)
```

### Pattern 2: Leaderboard
```python
# Top 10 users by score
leaders = db.select(
    "users",
    order_by="score",
    order_desc=True,
    limit=10
)
```

### Pattern 3: Time Series
```python
# Recent events with index
db.create_index("events", ["timestamp"])
recent = db.select(
    "events",
    order_by="timestamp",
    order_desc=True,
    limit=100
)
```

## 🔗 Links

- Full Guide: `SORT_ENGINE_GUIDE.md`
- Examples: `sort_examples.py`
- Performance: `PERFORMANCE_REPORT.md`
- API Docs: See docstrings in `sort_engine.py`

## ✅ Checklist

- [ ] Import works: `from sort_engine import SortEngine`
- [ ] Database creates with sort engine
- [ ] ORDER BY queries work
- [ ] Top-K optimization active (check with benchmarks)
- [ ] Configuration loaded (optional)
- [ ] Tests pass: `python -m pytest test_sort_engine.py`

---

**Status**: Production Ready ✅  
**Version**: 1.0  
**Last Updated**: Final Validation Complete
