#!/usr/bin/env python3
"""
Sort Engine Benchmarks for KosDB

Comprehensive performance benchmarks comparing:
- Builtin Python sort (Timsort)
- madS0rt Python implementation
- madS0rt Rust implementation (if available)

Metrics:
- Sort time for various data sizes
- Memory usage
- Performance with different data types
- Top-K optimization effectiveness
"""

import time
import random
import string
import statistics
import gc
from typing import List, Dict, Any, Callable, Optional
from dataclasses import dataclass


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""
    name: str
    backend: str
    data_size: int
    elapsed_time: float
    memory_mb: float
    throughput: float  # rows/sec


class SortBenchmark:
    """
    Benchmark suite for sort engines.
    
    Usage:
        benchmark = SortBenchmark()
        results = benchmark.run_all()
        benchmark.report(results)
    """
    
    # Data sizes to test (number of rows)
    DATA_SIZES = [100, 1000, 10000, 100000, 1000000]
    
    # Number of iterations for each test
    ITERATIONS = 3
    
    def __init__(self):
        """Initialize benchmark suite."""
        self.results: List[BenchmarkResult] = []
        self._sort_engine = None
        
        # Try to import sort engine
        try:
            from sort_engine import SortEngine, detect_available_backends
            self._sort_engine_available = True
            self._available_backends = detect_available_backends()
        except ImportError:
            self._sort_engine_available = False
            self._available_backends = {'builtin': True}
    
    def _create_sort_engine(self, backend: str) -> Any:
        """Create sort engine for backend."""
        if not self._sort_engine_available:
            from sort_backends.builtin import BuiltinBackend
            return BuiltinBackend()
        
        from sort_engine import SortEngine
        return SortEngine(backend=backend)
    
    def _generate_integers(self, n: int) -> List[int]:
        """Generate random integers."""
        return [random.randint(0, n * 10) for _ in range(n)]
    
    def _generate_strings(self, n: int) -> List[str]:
        """Generate random strings."""
        return [''.join(random.choices(string.ascii_lowercase, k=10)) 
                for _ in range(n)]
    
    def _generate_records(self, n: int) -> List[Dict[str, Any]]:
        """Generate record-like dictionaries."""
        return [
            {
                'id': i,
                'name': ''.join(random.choices(string.ascii_lowercase, k=8)),
                'value': random.random() * 1000,
                'category': random.choice(['A', 'B', 'C', 'D'])
            }
            for i in range(n)
        ]
    
    def _measure_time(self, func: Callable, *args) -> tuple:
        """
        Measure execution time and memory of function.
        
        Returns:
            (result, elapsed_time, memory_mb)
        """
        gc.collect()
        
        start_time = time.perf_counter()
        result = func(*args)
        elapsed = time.perf_counter() - start_time
        
        # Rough memory estimate (simplified)
        memory_mb = 0.0
        
        return result, elapsed, memory_mb
    
    def benchmark_backend(self,
                         backend: str,
                         data: List[Any],
                         key: Optional[Callable] = None,
                         reverse: bool = False) -> float:
        """
        Benchmark a single sort backend.
        
        Args:
            backend: Backend name
            data: Data to sort
            key: Optional key function
            reverse: Reverse sort
        
        Returns:
            Average elapsed time over iterations
        """
        times = []
        
        for _ in range(self.ITERATIONS):
            # Make a copy to avoid sorted data caching
            data_copy = data.copy()
            
            engine = self._create_sort_engine(backend)
            
            _, elapsed, _ = self._measure_time(
                engine.sort,
                data_copy,
                key=key,
                reverse=reverse
            )
            
            times.append(elapsed)
        
        return statistics.median(times)
    
    def run_integer_sort(self, size: int) -> List[BenchmarkResult]:
        """Benchmark integer sorting."""
        data = self._generate_integers(size)
        results = []
        
        for backend in self._available_backends:
            if not self._available_backends[backend]:
                continue
            
            try:
                elapsed = self.benchmark_backend(backend, data)
                
                result = BenchmarkResult(
                    name='integer_sort',
                    backend=backend,
                    data_size=size,
                    elapsed_time=elapsed,
                    memory_mb=0.0,
                    throughput=size / elapsed
                )
                results.append(result)
            except Exception as e:
                print(f"  {backend}: FAILED - {e}")
        
        return results
    
    def run_string_sort(self, size: int) -> List[BenchmarkResult]:
        """Benchmark string sorting."""
        data = self._generate_strings(size)
        results = []
        
        for backend in self._available_backends:
            if not self._available_backends[backend]:
                continue
            
            try:
                elapsed = self.benchmark_backend(backend, data)
                
                result = BenchmarkResult(
                    name='string_sort',
                    backend=backend,
                    data_size=size,
                    elapsed_time=elapsed,
                    memory_mb=0.0,
                    throughput=size / elapsed
                )
                results.append(result)
            except Exception as e:
                print(f"  {backend}: FAILED - {e}")
        
        return results
    
    def run_record_sort(self, size: int) -> List[BenchmarkResult]:
        """Benchmark record sorting with key function."""
        data = self._generate_records(size)
        results = []
        
        for backend in self._available_backends:
            if not self._available_backends[backend]:
                continue
            
            try:
                # Sort by 'value' field
                elapsed = self.benchmark_backend(
                    backend, 
                    data,
                    key=lambda x: x['value']
                )
                
                result = BenchmarkResult(
                    name='record_sort_by_value',
                    backend=backend,
                    data_size=size,
                    elapsed_time=elapsed,
                    memory_mb=0.0,
                    throughput=size / elapsed
                )
                results.append(result)
            except Exception as e:
                print(f"  {backend}: FAILED - {e}")
        
        return results
    
    def run_reverse_sort(self, size: int) -> List[BenchmarkResult]:
        """Benchmark reverse sorting."""
        data = self._generate_integers(size)
        results = []
        
        for backend in self._available_backends:
            if not self._available_backends[backend]:
                continue
            
            try:
                elapsed = self.benchmark_backend(backend, data, reverse=True)
                
                result = BenchmarkResult(
                    name='reverse_sort',
                    backend=backend,
                    data_size=size,
                    elapsed_time=elapsed,
                    memory_mb=0.0,
                    throughput=size / elapsed
                )
                results.append(result)
            except Exception as e:
                print(f"  {backend}: FAILED - {e}")
        
        return results
    
    def run_topk_sort(self, size: int, k: int = 100) -> List[BenchmarkResult]:
        """Benchmark top-K sorting."""
        data = self._generate_integers(size)
        results = []
        
        for backend in self._available_backends:
            if not self._available_backends[backend]:
                continue
            
            try:
                engine = self._create_sort_engine(backend)
                
                times = []
                for _ in range(self.ITERATIONS):
                    data_copy = data.copy()
                    start = time.perf_counter()
                    result = engine.sort(data_copy, topk=k)
                    elapsed = time.perf_counter() - start
                    times.append(elapsed)
                
                elapsed = statistics.median(times)
                
                result = BenchmarkResult(
                    name=f'top{k}_sort',
                    backend=backend,
                    data_size=size,
                    elapsed_time=elapsed,
                    memory_mb=0.0,
                    throughput=size / elapsed
                )
                results.append(result)
            except Exception as e:
                print(f"  {backend}: FAILED - {e}")
        
        return results
    
    def run_all(self) -> List[BenchmarkResult]:
        """Run complete benchmark suite."""
        all_results = []
        
        print("=" * 70)
        print("Sort Engine Benchmark Suite")
        print("=" * 70)
        
        for size in self.DATA_SIZES:
            print(f"\n--- Data size: {size:,} rows ---")
            
            # Integer sort
            print("Running integer sort...")
            all_results.extend(self.run_integer_sort(size))
            
            # String sort
            print("Running string sort...")
            all_results.extend(self.run_string_sort(size))
            
            # Record sort
            print("Running record sort...")
            all_results.extend(self.run_record_sort(size))
            
            # Reverse sort
            print("Running reverse sort...")
            all_results.extend(self.run_reverse_sort(size))
            
            # Top-K for larger datasets
            if size >= 10000:
                print(f"Running top-100 sort...")
                all_results.extend(self.run_topk_sort(size, k=100))
        
        self.results = all_results
        return all_results
    
    def report(self, results: Optional[List[BenchmarkResult]] = None) -> str:
        """
        Generate benchmark report.
        
        Args:
            results: Results to report (or use self.results)
        
        Returns:
            Formatted report string
        """
        if results is None:
            results = self.results
        
        lines = []
        lines.append("=" * 70)
        lines.append("BENCHMARK RESULTS")
        lines.append("=" * 70)
        
        # Group by benchmark name and data size
        from collections import defaultdict
        grouped = defaultdict(lambda: defaultdict(list))
        
        for r in results:
            grouped[r.name][r.data_size].append(r)
        
        # Report each benchmark type
        for bench_name in sorted(grouped.keys()):
            lines.append(f"\n{bench_name.upper()}")
            lines.append("-" * 70)
            lines.append(f"{'Size':>10} {'Backend':>15} {'Time (ms)':>12} {'Rows/sec':>15}")
            lines.append("-" * 70)
            
            for size in sorted(grouped[bench_name].keys()):
                for r in sorted(grouped[bench_name][size], 
                               key=lambda x: x.elapsed_time):
                    time_ms = r.elapsed_time * 1000
                    throughput = r.throughput
                    lines.append(
                        f"{size:>10,} {r.backend:>15} {time_ms:>12.2f} {throughput:>15,.0f}"
                    )
        
        lines.append("\n" + "=" * 70)
        
        # Speedup analysis
        lines.append("\nSPEEDUP ANALYSIS (vs builtin)")
        lines.append("-" * 70)
        
        for bench_name in sorted(grouped.keys()):
            for size in sorted(grouped[bench_name].keys()):
                runs = grouped[bench_name][size]
                builtin_time = None
                
                for r in runs:
                    if r.backend == 'builtin':
                        builtin_time = r.elapsed_time
                        break
                
                if builtin_time:
                    for r in runs:
                        if r.backend != 'builtin':
                            speedup = builtin_time / r.elapsed_time
                            lines.append(
                                f"{bench_name} n={size:,}: "
                                f"{r.backend} = {speedup:.2f}x faster"
                            )
        
        report = '\n'.join(lines)
        print(report)
        return report
    
    def save_results(self, filename: str = "sort_benchmark_results.json"):
        """Save results to JSON file."""
        import json
        
        data = [
            {
                'name': r.name,
                'backend': r.backend,
                'data_size': r.data_size,
                'elapsed_time': r.elapsed_time,
                'memory_mb': r.memory_mb,
                'throughput': r.throughput
            }
            for r in self.results
        ]
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"\nResults saved to {filename}")


def quick_benchmark():
    """Run quick benchmark for development."""
    benchmark = SortBenchmark()
    benchmark.DATA_SIZES = [1000, 10000, 100000]
    benchmark.ITERATIONS = 2
    
    results = benchmark.run_all()
    benchmark.report(results)
    
    return results


def full_benchmark():
    """Run full benchmark suite."""
    benchmark = SortBenchmark()
    results = benchmark.run_all()
    benchmark.report(results)
    benchmark.save_results()
    
    return results


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--full':
        full_benchmark()
    else:
        quick_benchmark()
