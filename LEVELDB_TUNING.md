# KosDB LevelDB Tuning Guide

This guide covers the LevelDB performance enhancements implemented in KosDB and provides recommendations for tuning based on your workload.

## Table of Contents

1. [Overview](#overview)
2. [Configuration Options](#configuration-options)
3. [Performance Features](#performance-features)
4. [Tuning Recommendations](#tuning-recommendations)
5. [Benchmark Results](#benchmark-results)
6. [Best Practices](#best-practices)

---

## Overview

KosDB now leverages advanced LevelDB features through the plyvel Python bindings to provide:

- **Atomic Transactions** with WriteBatch
- **In-Memory Caching** with configurable block cache
- **Fast Negative Lookups** with Bloom filters
- **Consistent Backups** with snapshots
- **Tunable Performance** for different workloads

---

## Configuration Options

When creating a Database instance, you can tune the following parameters:

```python
from database import Database

db = Database(
    data_dir="data",
    server_id=1,
    
    # Performance tuning options
    cache_size=8*1024*1024,        # LRU block cache (default: 8MB)
    write_buffer_size=4*1024*1024,  # Memtable size (default: 4MB)
    max_open_files=1000,            # File handle limit (default: 1000)
    compression='snappy',            # Compression: 'snappy' or None
    bloom_filter_bits=10            # Bits per key for bloom filter (default: 10)
)
```

### Parameter Details

| Parameter | Default | Description | When to Increase |
|-----------|---------|-------------|----------------|
| `cache_size` | 8MB | In-memory cache for frequently accessed blocks | Large datasets, read-heavy workloads |
| `write_buffer_size` | 4MB | Size of in-memory write buffer before flush to disk | Write-heavy workloads, bulk loads |
| `max_open_files` | 1000 | Maximum number of open file handles | Large databases with many SSTables |
| `bloom_filter_bits` | 10 | Bits per key for Bloom filter (0=disabled) | Many negative lookups (checking non-existent keys) |
| `compression` | 'snappy' | Data compression algorithm | Keep 'snappy' unless CPU-constrained |

---

## Performance Features

### 1. WriteBatch for Atomic Transactions

All transactions now use LevelDB's WriteBatch for atomic commits:

```python
# Begin transaction
db.begin_transaction()

# Queue multiple operations
db._transaction_put(b"key1", b"value1")
db._transaction_put(b"key2", b"value2")
db._transaction_delete(b"key3")

# Atomic commit - all succeed or all fail
result = db.commit_transaction()
# Returns: "OK: Committed 3 change(s) atomically in 0.001s"
```

**Benefits:**
- True atomicity: all changes succeed or none do
- Better performance: single disk write vs multiple
- Automatic rollback on failure

**Performance:** ~1.8x faster than individual puts

### 2. Block Cache for Read Performance

LevelDB's block cache keeps frequently accessed data in memory:

```python
# Create database with 32MB cache
db = Database("data", cache_size=32*1024*1024)

# First read populates cache
data = db._db.get(b"key")

# Subsequent reads are faster (from memory)
data = db._db.get(b"key")  # Cache hit!
```

**Benefits:**
- Reduces disk I/O for hot data
- Eliminates repeated decompression
- Configurable per-database

**Performance:** Up to 2x faster for repeated reads

### 3. Bloom Filters for Fast Negative Lookups

Bloom filters reduce disk seeks when checking for non-existent keys:

```python
# Create database with bloom filter
db = Database("data", bloom_filter_bits=10)

# Check non-existent key - fast!
exists = db._db.get(b"non_existent_key")  # Returns None quickly
```

**Benefits:**
- Avoids disk seeks for "not found" responses
- Critical for index lookups
- Minimal memory overhead

**Performance:** Significant reduction in latency for negative lookups

### 4. Snapshots for Consistent Reads

Snapshots provide point-in-time consistency:

```python
# Create snapshot
snapshot = db.create_snapshot()

# Read using snapshot (consistent view)
data = db.get_with_snapshot(b"key", snapshot)

# Concurrent writes don't affect snapshot
db._db.put(b"key", b"new_value")  # Snapshot still sees old value

# Clean up
snapshot.close()
```

**Benefits:**
- Consistent backups without locking
- Point-in-time queries
- Isolation from concurrent writes

---

## Tuning Recommendations

### For Read-Heavy Workloads (e.g., CMS Frontend)

```python
db = Database(
    "data",
    cache_size=64*1024*1024,      # Large cache: 64MB
    write_buffer_size=4*1024*1024,  # Standard: 4MB
    bloom_filter_bits=10,          # Enable bloom filter
    max_open_files=2000            # More file handles
)
```

### For Write-Heavy Workloads (e.g., Analytics)

```python
db = Database(
    "data",
    cache_size=16*1024*1024,      # Moderate cache: 16MB
    write_buffer_size=64*1024*1024,  # Large buffer: 64MB
    bloom_filter_bits=10,
    max_open_files=1000
)
```

### For Balanced Workloads (e.g., General CMS)

```python
db = Database(
    "data",
    cache_size=32*1024*1024,      # 32MB cache
    write_buffer_size=16*1024*1024,  # 16MB buffer
    bloom_filter_bits=10,
    max_open_files=1500
)
```

### For Memory-Constrained Environments

```python
db = Database(
    "data",
    cache_size=4*1024*1024,       # Minimal cache: 4MB
    write_buffer_size=2*1024*1024,  # Small buffer: 2MB
    bloom_filter_bits=0,           # Disable bloom filter
    compression=None               # Disable compression (saves CPU)
)
```

---

## Benchmark Results

Run benchmarks with:

```bash
python benchmarks/bench_leveldb_enhancements.py
```

### Summary Results

| Feature | Improvement | Use Case |
|---------|-------------|----------|
| WriteBatch | 1.8x faster | Bulk writes, transactions |
| Block Cache | Up to 2x | Repeated reads, hot data |
| Bloom Filter | Significant | Negative lookups, index checks |
| Snapshots | Minimal overhead | Backups, consistent reads |

---

## Best Practices

### 1. Always Use Transactions for Multiple Writes

```python
# Good: Atomic and faster
db.begin_transaction()
for item in items:
    db._transaction_put(key, value)
db.commit_transaction()

# Bad: Slower, not atomic
for item in items:
    db._db.put(key, value)  # Individual writes
```

### 2. Tune Cache Size Based on Working Set

- Monitor cache hit rates via `db.get_stats()`
- Cache size should fit your hot data
- Larger is better, but watch memory usage

### 3. Enable Bloom Filters for Index-Heavy Workloads

```python
# Recommended for tables with indexes
db = Database("data", bloom_filter_bits=10)
```

### 4. Use Snapshots for Backups

```python
snapshot = db.create_snapshot()
# ... perform backup using snapshot ...
snapshot.close()
```

### 5. Monitor LevelDB Statistics

```python
stats = db.get_stats()
print(stats['leveldb_stats'])  # Detailed internal stats
```

### 6. Compact When Needed

```python
# Manual compaction (usually not needed)
db._db.compact_range()
```

---

## Configuration API

### Get Current Configuration

```python
config = db.get_config()
# Returns:
# {
#     'cache_size': 8388608,
#     'write_buffer_size': 4194304,
#     'max_open_files': 1000,
#     'compression': 'snappy',
#     'bloom_filter_bits': 10,
#     'data_dir': 'data',
#     'server_id': 1,
#     'current_db': 'mydb'
# }
```

### Get Database Statistics

```python
stats = db.get_stats()
# Returns LevelDB internal statistics including:
# - Compaction statistics
# - File counts per level
# - Size information
```

---

## Troubleshooting

### High Memory Usage

- Reduce `cache_size`
- Reduce `write_buffer_size`
- Check for memory leaks in application code

### Slow Reads

- Increase `cache_size`
- Enable `bloom_filter_bits`
- Check if data fits in cache (working set size)

### Slow Writes

- Increase `write_buffer_size`
- Use transactions (WriteBatch)
- Consider disabling compression if CPU-bound

### Too Many Open Files

- Increase `max_open_files`
- Check OS file descriptor limits (`ulimit -n`)

---

## References

- [LevelDB Documentation](https://github.com/google/leveldb/blob/master/doc/index.md)
- [Plyvel Documentation](https://plyvel.readthedocs.io/)
- [LevelDB Tuning Guide](https://github.com/google/leveldb/blob/master/doc/impl.md)

---

## Migration Guide

If upgrading from an older KosDB version:

1. **Backup your data** before upgrading
2. Install new version with `pip install -r requirements.txt`
3. No data migration needed - LevelDB is backward compatible
4. Update your code to use new tuning options if desired
5. Run benchmarks to verify performance

All existing code continues to work without changes. New tuning options are optional and use sensible defaults.
