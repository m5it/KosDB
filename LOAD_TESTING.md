
# Load Testing Guide for Batch Operations

This document describes the comprehensive load testing framework for KosDB batch operations.

## Overview

The load testing framework provides:
- **Throughput benchmarks** - Commands per second under various loads
- **Latency analysis** - Response times at different percentiles
- **Scalability testing** - Performance with concurrent clients
- **Memory profiling** - Resource usage during batch operations
- **Regression detection** - Automated baseline comparisons

## Test Suite Structure

```
tests/test_batch_load.py
├── TestBatchThroughput       # Sustained throughput tests
├── TestBatchSizes            # Various batch size tests
├── TestConcurrentExecution   # Multi-client scenarios
├── TestMemoryProfiling       # Memory usage analysis
├── TestConnectionPool        # Connection pool stress
├── TestBenchmarkComparisons  # Single vs batch comparisons
├── TestRealisticWorkloads   # Real-world scenarios
└── TestPerformanceBaselines # Regression thresholds
```

## Running Load Tests

### Run All Tests
```bash
python -m unittest tests.test_batch_load -v
```

### Run Specific Test Class
```bash
python -m unittest tests.test_batch_load.TestBatchThroughput -v
```

### Run Single Test
```bash
python -m unittest tests.test_batch_load.TestBatchThroughput.test_throughput_single_commands -v
```

## Test Categories

### 1. Throughput Tests

#### Single Command Throughput
```python
def test_throughput_single_commands(self):
    # Measures: Commands per second for individual operations
    # Baseline: > 100 cmd/sec (relaxed for mock)
    # Duration: ~100 ms for 100 commands
```

#### Batch Throughput
```python
def test_throughput_small_batches(self):
    # Batch size: 10 commands
    # Baseline: > 200 cmd/sec
    # Expected: 5-10x faster than single commands
```

#### Sustained Throughput
```python
def test_sustained_throughput_10_seconds(self):
    # Duration: 10 seconds continuous execution
    # Batch size: 50 commands
    # Measures: Consistency over time
```

### 2. Batch Size Tests

Tests batch sizes: 1, 10, 100, 1000, 10000 commands

| Batch Size | Expected Throughput | Latency |
|------------|---------------------|---------|
| 1 | ~1600 cmd/sec | ~0.6 ms |
| 10 | ~9000 cmd/sec | ~1.1 ms |
| 100 | ~15000 cmd/sec | ~6.3 ms |
| 1000 | ~19000 cmd/sec | ~51 ms |

### 3. Concurrent Execution

Tests with 2, 5, 10 concurrent clients:

```python
def test_concurrent_5_clients(self):
    # Clients: 5
    # Batches per client: 20
    # Batch size: 10
    # Expected: Linear or near-linear scaling
```

### 4. Memory Profiling

```python
def test_memory_batch_size(self, size: int):
    # Measures: Memory per command
    # Threshold: < 10 KB per command
    # Includes: GC before/after measurements
```

### 5. Benchmark Comparisons

Single vs Batch comparison:

```
Single: 105.13 ms for 100 commands
Batch:  11.08 ms for 100 commands
Speedup: 9.49x
```

## Performance Baselines

### Current Baselines

| Metric | Baseline | Threshold |
|--------|----------|-----------|
| Single cmd throughput | 100 cmd/sec | 80 cmd/sec |
| Small batch throughput | 200 cmd/sec | 160 cmd/sec |
| P99 latency | 100 ms | 120 ms |
| Memory per command | 10 KB | 12 KB |

### Regression Detection

Tests fail if performance drops below 80% of baseline:

```python
self.assertGreaterEqual(
    throughput, 
    baseline * 0.8,
    f"Throughput {throughput:.2f} below baseline {baseline}"
)
```

## Interpreting Results

### Throughput Metrics

**Good Results:**
- Batch throughput 5-10x higher than single commands
- Linear scaling with concurrent clients
- Consistent throughput over sustained periods

**Warning Signs:**
- Throughput plateaus with batch size
- Concurrent clients don't improve throughput
- Memory grows with batch size

### Latency Metrics

Measure at percentiles:
- **P50 (Median)**: Typical user experience
- **P95**: Most user experiences
- **P99**: Worst-case acceptable

### Memory Metrics

```python
# Memory per command calculation
mb_per_command = memory_used_mb / num_commands

# Should be < 10 KB
assert mb_per_command < 0.01  # 10 KB in MB
```

## Performance Bottlenecks

### Common Issues

1. **Network Latency**
   - Symptom: Throughput doesn't scale with batch size
   - Solution: Increase batch size, use connection pooling

2. **Lock Contention**
   - Symptom: Concurrent clients don't improve throughput
   - Solution: Reduce lock granularity, use lock-free structures

3. **Memory Pressure**
   - Symptom: Performance degrades with large batches
   - Solution: Streaming execution, memory limits

4. **Connection Pool Exhaustion**
   - Symptom: Timeouts under load
   - Solution: Increase pool size, connection multiplexing

## CI/CD Integration

### GitHub Actions Example

```yaml
# .github/workflows/performance.yml
name: Performance Tests

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  performance:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.9'
    
    - name: Install dependencies
      run: |
        pip install psutil
        pip install -e .
    
    - name: Run performance tests
      run: |
        python -m unittest tests.test_batch_load -v > performance_results.txt
    
    - name: Upload results
      uses: actions/upload-artifact@v2
      with:
        name: performance-results
        path: performance_results.txt
    
    - name: Check for regressions
      run: |
        # Parse results and check against baselines
        python scripts/check_performance_regression.py
```

### Performance Regression Script

```python
# scripts/check_performance_regression.py
import re
import sys

def check_regression(results_file: str) -> bool:
    """Check test results for performance regressions."""
    
    with open(results_file) as f:
        content = f.read()
    
    # Look for failure indicators
    if 'FAIL' in content:
        print("Performance regression detected!")
        return False
    
    # Extract throughput numbers
    throughput_pattern = r'(\d+\.\d+) cmd/sec'
    matches = re.findall(throughput_pattern, content)
    
    if matches:
        throughputs = [float(m) for m in matches]
        avg_throughput = sum(throughputs) / len(throughputs)
        print(f"Average throughput: {avg_throughput:.2f} cmd/sec")
    
    return True

if __name__ == '__main__':
    success = check_regression('performance_results.txt')
    sys.exit(0 if success else 1)
```

## Best Practices

### 1. Establish Baselines Early

```python
BASELINES = {
    'single_command_throughput': 500,
    'small_batch_throughput': 800,
    # Update based on your environment
}
```

### 2. Run Tests on Dedicated Hardware

- Avoid noisy neighbors (other processes)
- Use consistent VM sizes
- Document hardware specifications

### 3. Warm Up Before Measuring

```python
# Warm up phase
for _ in range(100):
    db.execute_batch(commands)

# Measure phase
start_time = time.time()
# ... actual test ...
```

### 4. Monitor System Resources

```python
import psutil

# CPU usage
cpu_percent = psutil.cpu_percent(interval=1)

# Memory usage
memory = psutil.virtual_memory()

# Disk I/O
disk_io = psutil.disk_io_counters()
```

### 5. Statistical Significance

```python
# Run multiple iterations
results = []
for _ in range(10):
    result = run_test()
    results.append(result)

# Use median, not mean
median_result = statistics.median(results)
```

## Troubleshooting

### Test Failures

**"Throughput below baseline"**
- Check system load
- Verify no other processes running
- Consider adjusting baseline for your environment

**"Memory growth detected"**
- Check for memory leaks
- Verify garbage collection is working
- Review object retention

**"Concurrent scaling poor"**
- Check for lock contention
- Verify thread safety
- Review connection pool configuration

## Extending the Framework

### Adding New Tests

```python
class TestCustomScenarios(unittest.TestCase):
    def test_my_scenario(self):
        # Your test code here
        pass
```

### Custom Metrics

```python
@dataclass
class CustomMetrics:
    custom_metric: float
    
    def to_dict(self):
        return {'custom_metric': self.custom_metric}
```

### Custom Baselines

```python
MY_BASELINES = {
    'my_metric': 100.0,
}

def test_my_baseline(self):
    result = measure()
    self.assertGreaterEqual(result, MY_BASELINES['my_metric'] * 0.8)
```

## See Also

- [Batch Sharding Guide](BATCH_SHARDING.md)
- [Performance Tuning](performance.md)
- [Benchmarking Best Practices](benchmarking.md)
