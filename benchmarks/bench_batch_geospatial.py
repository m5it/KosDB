
"""
Batch Geospatial Operations Benchmarks

Performance benchmarks for batch geospatial operations.
"""

import time
import random
import statistics
from typing import List, Tuple
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock for standalone execution
class MockSpatialIndex:
    def __init__(self):
        self.points = {}
    
    def insert(self, pid, lat, lon, meta=None):
        self.points[pid] = {'lat': lat, 'lon': lon, 'meta': meta or {}}
    
    def radius_search(self, lat, lon, radius, limit=10):
        results = []
        for k, v in self.points.items():
            dist = ((v['lat'] - lat)**2 + (v['lon'] - lon)**2)**0.5 * 111000
            results.append((k, dist))
        results.sort(key=lambda x: x[1])
        return results[:limit]
    
    def nearest_neighbors(self, lat, lon, k=5):
        results = []
        for point_id, data in self.points.items():
            dist = ((data['lat'] - lat)**2 + (data['lon'] - lon)**2)**0.5 * 111000
            results.append((point_id, dist))
        results.sort(key=lambda x: x[1])
        return results[:k]
    
    def bbox_search(self, bbox):
        return list(self.points.keys())[:100]


class MockBoundingBox:
    def __init__(self, min_lat, min_lon, max_lat, max_lon):
        self.min_lat = min_lat
        self.min_lon = min_lon
        self.max_lat = max_lat
        self.max_lon = max_lon


try:
    from geospatial import SpatialIndex, BoundingBox
except ImportError:
    SpatialIndex = MockSpatialIndex
    BoundingBox = MockBoundingBox

from batch_geospatial import BatchGeospatialManager


def generate_points(n: int) -> List[Tuple]:
    """Generate n random points."""
    return [
        (f'point_{i}',
         random.uniform(30, 50),
         random.uniform(-120, -70),
         {'index': i, 'category': random.choice(['A', 'B', 'C'])})
        for i in range(n)
    ]


def generate_queries(n: int) -> List[Tuple]:
    """Generate n random query points."""
    return [
        (f'q_{i}',
         random.uniform(30, 50),
         random.uniform(-120, -70))
        for i in range(n)
    ]


def generate_centers(n: int) -> List[Tuple]:
    """Generate n random search centers."""
    return [
        (f'center_{i}',
         random.uniform(30, 50),
         random.uniform(-120, -70),
         random.uniform(1000, 50000))  # radius in meters
        for i in range(n)
    ]


def benchmark_batch_add():
    """Benchmark batch point insertion."""
    print("\n=== Batch Point Insertion Benchmark ===\n")
    
    batch_sizes = [100, 1000, 10000]
    
    for batch_size in batch_sizes:
        points = generate_points(batch_size)
        index = SpatialIndex()
        manager = BatchGeospatialManager(index)
        
        # Warmup
        manager.batch_geo_add(points[:10])
        
        # Benchmark
        times = []
        for _ in range(5):
            index = SpatialIndex()
            manager = BatchGeospatialManager(index)
            
            start = time.time()
            result = manager.batch_geo_add(points)
            elapsed = (time.time() - start) * 1000
            times.append(elapsed)
        
        avg_time = statistics.mean(times)
        throughput = batch_size / (avg_time / 1000)
        
        print(f"Batch size: {batch_size}")
        print(f"  Avg time: {avg_time:.2f}ms")
        print(f"  Throughput: {throughput:.0f} points/sec")
        print(f"  Per-point: {avg_time/batch_size*1000:.3f}µs")
        print()


def benchmark_batch_radius_search():
    """Benchmark batch radius search."""
    print("\n=== Batch Radius Search Benchmark ===\n")
    
    # Setup: index 10k points
    points = generate_points(10000)
    index = SpatialIndex()
    manager = BatchGeospatialManager(index)
    manager.batch_geo_add(points)
    
    query_counts = [10, 100, 500]
    
    for num_queries in query_counts:
        centers = generate_centers(num_queries)
        
        # Benchmark
        times = []
        for _ in range(5):
            start = time.time()
            results = manager.batch_radius_search(centers, k=10)
            elapsed = (time.time() - start) * 1000
            times.append(elapsed)
        
        avg_time = statistics.mean(times)
        queries_per_sec = num_queries / (avg_time / 1000)
        
        print(f"Queries: {num_queries}")
        print(f"  Avg time: {avg_time:.2f}ms")
        print(f"  Throughput: {queries_per_sec:.0f} queries/sec")
        print(f"  Per-query: {avg_time/num_queries:.3f}ms")
        print()


def benchmark_batch_nearest_neighbor():
    """Benchmark batch nearest neighbor."""
    print("\n=== Batch Nearest Neighbor Benchmark ===\n")
    
    # Setup
    points = generate_points(10000)
    index = SpatialIndex()
    manager = BatchGeospatialManager(index)
    manager.batch_geo_add(points)
    
    query_counts = [10, 100, 500]
    k_values = [5, 10, 20]
    
    for num_queries in query_counts:
        for k in k_values:
            queries = generate_queries(num_queries)
            
            times = []

            avg_time = statistics.mean(times)
            if avg_time > 0:
                qps = num_queries / (avg_time / 1000)
                print(f"Queries: {num_queries}, k={k}: {avg_time:.2f}ms "
                      f"({qps:.0f} qps)")
            else:
                print(f"Queries: {num_queries}, k={k}: <1ms")
        print()
    # Setup
    points = generate_points(10000)
    index = SpatialIndex()
    manager = BatchGeospatialManager(index)
    manager.batch_geo_add(points)
    
    # Generate bounding boxes
    def generate_bboxes(n):
        bboxes = []
        for i in range(n):
            min_lat = random.uniform(30, 49)
            min_lon = random.uniform(-120, -71)
            max_lat = min_lat + random.uniform(0.5, 2)
            max_lon = min_lon + random.uniform(0.5, 2)
            bboxes.append((f'bbox_{i}', BoundingBox(min_lat, min_lon, max_lat, max_lon)))
        return bboxes
    
    query_counts = [10, 50, 100]
    
    for num_queries in query_counts:
        bboxes = generate_bboxes(num_queries)
        
        times = []
        for _ in range(5):
            start = time.time()
            results = manager.batch_bbox_query(bboxes)
            elapsed = (time.time() - start) * 1000
            times.append(elapsed)
        
        avg_time = statistics.mean(times)
        print(f"BBox queries: {num_queries}: {avg_time:.2f}ms "
              f"({num_queries/(avg_time/1000):.0f} qps)")


def benchmark_parallel_vs_sequential():
    """Compare parallel vs sequential execution."""
    print("\n=== Parallel vs Sequential Benchmark ===\n")
    
    # Setup
    points = generate_points(5000)
    index = SpatialIndex()
    manager = BatchGeospatialManager(index)
    manager.batch_geo_add(points)
    
    centers = generate_centers(100)
    
    # Sequential
    start = time.time()
    results_seq = manager.batch_radius_search(centers, k=10, parallel=False)
    seq_time = (time.time() - start) * 1000
    
    # Parallel
    start = time.time()
    results_par = manager.batch_radius_search(centers, k=10, parallel=True)
    par_time = (time.time() - start) * 1000
    
    print(f"Sequential: {seq_time:.2f}ms")
    print(f"Parallel: {par_time:.2f}ms")
    print(f"Speedup: {seq_time/par_time:.2f}x")


def benchmark_memory_usage():
    """Benchmark memory efficiency."""
    print("\n=== Memory Efficiency Benchmark ===\n")
    
    batch_sizes = [1000, 10000, 50000]
    
    for batch_size in batch_sizes:
        points = generate_points(batch_size)
        
        # Measure batch add
        index = SpatialIndex()
        manager = BatchGeospatialManager(index)
        
        start = time.time()
        result = manager.batch_geo_add(points, batch_size=1000)
        elapsed = (time.time() - start) * 1000
        
        throughput = batch_size / (elapsed / 1000)
        
        print(f"Batch size: {batch_size}")
        print(f"  Time: {elapsed:.2f}ms")
        print(f"  Throughput: {throughput:.0f} points/sec")
        print(f"  Failed: {result.failed}")
        print()


def run_all_benchmarks():
    """Run all benchmarks."""
    print("="*60)
    print("Batch Geospatial Operations Benchmarks")
    print("="*60)
    
    benchmarks = [
        benchmark_batch_add,
        benchmark_batch_radius_search,
        benchmark_batch_nearest_neighbor,
        benchmark_batch_bbox,
        benchmark_parallel_vs_sequential,
        benchmark_memory_usage,
    ]
    
    for benchmark in benchmarks:
        try:
            benchmark()
        except Exception as e:
            print(f"\nError in {benchmark.__name__}: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*60)
    print("Benchmarks completed!")
    print("="*60)


if __name__ == '__main__':
    run_all_benchmarks()
