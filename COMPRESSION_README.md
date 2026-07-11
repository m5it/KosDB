# Data Compression for KosDB

Transparent data compression with multiple algorithm support for storage efficiency.

## Features

- **Multiple Algorithms**: LZ4, Zstandard, Snappy, zlib
- **Per-Table Configuration**: Different compression per table
- **Automatic Ratio Monitoring**: Track compression efficiency
- **Decompression Caching**: LRU cache for frequently accessed data
- **Transparent Operations**: Automatic compress/decompress on read/write

## Supported Algorithms

| Algorithm | Speed | Ratio | Best For |
|-----------|-------|-------|----------|
| **LZ4** | Very Fast | Low | Real-time, low latency |
| **Zstandard** | Medium | High | Archival, backup |
| **Snappy** | Fast | Low | Balanced performance |
| **zlib** | Medium | Medium | General purpose |

## Usage

### Enable Compression for Table

```sql
COMPRESSION ENABLE users ALGORITHM zstd LEVEL 6 MIN_SIZE 100
```

### Disable Compression

```sql
COMPRESSION DISABLE users
```

### View Statistics

```sql
COMPRESSION STATS
COMPRESSION STATS users
```

### List Algorithms

```sql
COMPRESSION ALGORITHMS
```

### Benchmark

```sql
COMPRESSION BENCHMARK DATA_SIZE 100000
```

### Test Compression

```sql
COMPRESSION TEST users SAMPLE_SIZE 1000
```

### Cache Statistics

```sql
COMPRESSION CACHE STATS
```

## Configuration

```json
{
    "compression": {
        "default_algorithm": "zlib",
        "default_level": 6,
        "min_size": 100,
        "cache_decompressed": true,
        "cache_size": 1000
    }
}
```

## API Reference

### CompressionManager

```python
from compression import CompressionManager, CompressionAlgorithm

# Get available algorithms
available = CompressionManager.get_available_algorithms()

# Get compressor
compressor = CompressionManager.get_compressor(CompressionAlgorithm.ZLIB, level=6)

# Get statistics
stats = CompressionManager.get_stats()
```

### CompressedStorage

```python
from compressed_storage import CompressedStorage

storage = CompressedStorage("/path/to/db")

# Configure table compression
storage.configure_table(
    "users",
    enabled=True,
    algorithm="zstd",
    level=6,
    min_size=100,
    cache_decompressed=True
)

# Store data (automatically compressed)
metadata = storage.put("users", "key", b"large data...")

# Retrieve data (automatically decompressed)
data = storage.get("users", "key")

# Get statistics
stats = storage.get_stats()
```

## Compression Stats

```python
{
    'tables_compressed': 150,
    'tables_uncompressed': 50,
    'total_bytes_original': 1024000,
    'total_bytes_stored': 512000,
    'compression_ratio': 0.5,
    'space_saved_percent': 50.0,
    'algorithms': {
        'zlib_6': {
            'total_compressed': 100,
            'compression_ratio': 0.5,
            'space_saved_percent': 50.0
        }
    }
}
```

## Testing

```bash
python test_compression.py
```

All 13 tests passing ✓

## Installation of Optional Algorithms

```bash
# LZ4 (fastest)
pip install lz4

# Zstandard (best ratio)
pip install zstandard

# Snappy (Google)
pip install python-snappy
```
