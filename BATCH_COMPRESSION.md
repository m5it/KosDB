
# Batch Response Compression Guide

Version: 2.3.0  
Last Updated: 2024-01-15

## Overview

Batch response compression reduces bandwidth usage and improves response times for large batch results. This guide covers configuration, algorithms, trade-offs, and best practices.

## Quick Start

```python
from batch_compression import BatchCompressionManager

# Enable compression
manager = BatchCompressionManager()
manager.configure(
    enabled=True,
    threshold_bytes=1024,  # Compress responses > 1KB
    algorithm='gzip'
)

# Compress response
result = manager.compress_response(large_data)
# Returns: {'data': compressed_bytes, 'compressed': True, 'algorithm': 'gzip', ...}
```

## Configuration

### Default Configuration

```python
CompressionConfig(
    enabled=True,              # Enable compression
    threshold_bytes=1024,      # 1KB default threshold
    algorithm=CompressionAlgorithm.GZIP,
    compression_level=6,       # 1-9 for gzip
    min_ratio=0.1            # Minimum 10% compression to use
)
```

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `enabled` | True | Master switch for compression |
| `threshold_bytes` | 1024 | Minimum size to compress |
| `algorithm` | 'gzip' | Compression algorithm |
| `compression_level` | 6 | Compression level (algorithm-specific) |
| `min_ratio` | 0.1 | Minimum compression ratio to apply |

## Supported Algorithms

### GZIP (Default)

```python
config = CompressionConfig(
    algorithm=CompressionAlgorithm.GZIP,
    compression_level=6  # 1=fast, 9=best compression
)
```

**Characteristics:**
- Widely supported
- Good compression ratio
- Moderate CPU usage
- Best for: General purpose, compatibility

### LZ4 (Fast)

```python
config = CompressionConfig(
    algorithm=CompressionAlgorithm.LZ4,
    compression_level=9  # 1-12
)
```

**Characteristics:**
- Very fast compression/decompression
- Lower compression ratio than gzip
- Low CPU usage
- Best for: Real-time, low-latency applications

### ZSTD (Best Ratio)

```python
config = CompressionConfig(
    algorithm=CompressionAlgorithm.ZSTD,
    compression_level=3  # 1-22
)
```

**Characteristics:**
- Excellent compression ratio
- Configurable speed/ratio trade-off
- Moderate CPU usage
- Best for: Bandwidth-constrained environments

## Algorithm Comparison

| Algorithm | Speed | Ratio | CPU Usage | Best Use Case |
|-----------|-------|-------|-----------|---------------|
| GZIP | Medium | Good | Medium | General purpose |
| LZ4 | Very Fast | Fair | Low | Real-time |
| ZSTD | Fast | Excellent | Medium-High | Bandwidth limited |
| None | N/A | N/A | None | Small responses |

## CPU vs Bandwidth Trade-offs

### When to Use Compression

**Use Compression:**
- Response size > 1KB
- Bandwidth is constrained
- Network latency is high
- CPU resources available
- Repetitive data (JSON, text)

**Avoid Compression:**
- Response size < 1KB
- CPU is bottleneck
- Data is already compressed (images, video)
- Low-latency requirements critical

### Trade-off Analysis

```
Bandwidth Savings vs CPU Cost:

Small batches (< 1KB):
  - Overhead: 10-50 bytes (headers)
  - Savings: None or negative
  - Recommendation: Don't compress

Medium batches (1KB - 100KB):
  - Compression time: 1-5ms
  - Bandwidth savings: 30-70%
  - Recommendation: Use LZ4 or GZIP

Large batches (100KB - 10MB):
  - Compression time: 5-50ms
  - Bandwidth savings: 50-90%
  - Recommendation: Use GZIP or ZSTD

Very large batches (> 10MB):
  - Compression time: 50-500ms
  - Bandwidth savings: 60-95%
  - Recommendation: Use ZSTD with streaming
```

### Performance Benchmarks

Typical performance on modern hardware:

| Algorithm | Compress 1MB | Decompress 1MB | Ratio |
|-----------|------------|--------------|-------|
| GZIP-6 | 15ms | 3ms | 75% |
| LZ4-9 | 3ms | 1ms | 50% |
| ZSTD-3 | 8ms | 2ms | 80% |

## Client Negotiation

### Accept-Encoding Style

```python
negotiator = CompressionNegotiator()

# Parse client preferences
preferences = negotiator.parse_accept_encoding("gzip, lz4;q=0.8, *;q=0.1")
# Returns: ['gzip', 'lz4', '*']

# Negotiate best algorithm
algorithm = negotiator.negotiate(preferences)
# Returns: 'gzip' (first available match)
```

### CLI Integration

```python
# CLI automatically decompresses responses
result = manager.compress_response(data, client_encoding="gzip, lz4")

# In CLI
if result['compressed']:
    decompressed = decompress_batch_response(
        result['data'],
        result['algorithm']
    )
```

## COMPRESS Command Syntax

### SQL-Style Command

```sql
-- Enable compression for this batch
COMPRESS BATCH USING gzip;

INSERT INTO users VALUES (1, 'Alice');
INSERT INTO users VALUES (2, 'Bob');
SELECT * FROM users;

-- Batch will be compressed if response > threshold
```

### Programmatic Usage

```python
# Parse COMPRESS command
if command.upper().startswith('COMPRESS BATCH'):
    config = parse_compress_options(command)
    manager.configure(**config)
```

## Compression Ratios by Data Type

### JSON Data

```python
# Typical JSON result
data = {
    'rows': [{'id': i, 'name': f'user_{i}'} for i in range(1000)]
}

# Ratios:
# - GZIP: 70-85%
# - LZ4: 40-60%
# - ZSTD: 75-90%
```

### SQL Statements

```python
# Repetitive INSERT statements
statements = "; ".join([
    f"INSERT INTO logs VALUES ({i}, 'event')"
    for i in range(1000)
])

# Ratios:
# - GZIP: 80-95%
# - LZ4: 60-80%
# - ZSTD: 85-98%
```

### Binary Data

```python
# Random binary data
import os
data = os.urandom(10000)

# Ratios:
# - All algorithms: 0-5% (don't compress random data)
```

## Best Practices

### 1. Use Threshold Wisely

```python
# Don't compress small responses
config = CompressionConfig(
    threshold_bytes=1024,  # 1KB minimum
    min_ratio=0.1         # At least 10% savings
)
```

### 2. Choose Algorithm Based on Workload

```python
# High-frequency, small responses
config = CompressionConfig(
    algorithm=CompressionAlgorithm.LZ4,
    threshold_bytes=512
)

# Large analytical queries
config = CompressionConfig(
    algorithm=CompressionAlgorithm.ZSTD,
    threshold_bytes=4096
)
```

### 3. Monitor Compression Effectiveness

```python
stats = manager.get_stats()
print(f"Avg compression ratio: {stats['avg_compression_ratio']:.2%}")
print(f"Avg compression time: {stats['avg_time_ms']:.2f}ms")
```

### 4. Handle Decompression Failures

```python
try:
    decompressed = decompress_batch_response(data, algorithm)
except Exception as e:
    logger.error(f"Decompression failed: {e}")
    # Fall back to raw data or error
```

## Integration with Storage

### Compressed Storage Integration

```python
# If compressed_storage.py is available
try:
    from compressed_storage import CompressedStorage
    
    class CompressedBatchStorage:
        def __init__(self):
            self.storage = CompressedStorage()
            self.compression = BatchCompressionManager()
        
        def store_batch_result(self, batch_id, data):
            # Compress before storage
            compressed = self.compression.compress_response(data)
            return self.storage.store(batch_id, compressed)
        
        def retrieve_batch_result(self, batch_id):
            data = self.storage.retrieve(batch_id)
            if data.get('compressed'):
                return self.compression.decompress_response(
                    data['data'],
                    data['algorithm']
                )
            return data
except ImportError:
    pass  # compressed_storage not available
```

## Monitoring and Metrics

### Key Metrics

```python
stats = manager.get_stats()

# Total data
print(f"Uncompressed: {stats['total_uncompressed']} bytes")
print(f"Compressed: {stats['total_compressed']} bytes")

# Efficiency
print(f"Avg ratio: {stats['avg_compression_ratio']:.2%}")
print(f"Avg time: {stats['avg_time_ms']:.2f}ms")

# Algorithm usage
for algo, count in stats['algorithms_used'].items():
    print(f"{algo}: {count} uses")
```

### Alerting

```python
# Alert if compression is ineffective
if stats['avg_compression_ratio'] < 0.05:
    logger.warning("Compression ratio very low - check threshold")

# Alert if compression is slow
if stats['avg_time_ms'] > 50:
    logger.warning("Compression taking too long - consider LZ4")
```

## Troubleshooting

### Issue: Compression Not Applied

**Symptoms:** Responses not compressed despite configuration

**Check:**
1. Is `enabled=True`?
2. Is response size > `threshold_bytes`?
3. Is compression ratio > `min_ratio`?

### Issue: High CPU Usage

**Symptoms:** CPU usage spikes during compression

**Solutions:**
1. Switch to LZ4 algorithm
2. Increase `threshold_bytes`
3. Lower `compression_level`
4. Use hardware acceleration if available

### Issue: Client Can't Decompress

**Symptoms:** Client receives compressed data it can't read

**Solutions:**
1. Check client supports algorithm
2. Use negotiation to select compatible algorithm
3. Fall back to no compression

## See Also

- [Batch Operations Guide](OPERATIONS.md)
- [Performance Tuning](performance.md)
- [Network Optimization](network.md)
