#!/usr/bin/env python3
"""
Sort Engine Examples for KosDB

Demonstrates various sort engine features and configurations.
Run: python sort_examples.py
"""

import os
import random
import string
from datetime import datetime, timedelta

# Set up example environment
os.environ['KOSDB_SORT_BACKEND'] = 'auto'


def example_1_basic_usage():
    """Example 1: Basic sort engine usage."""
    print("\n" + "=" * 60)
    print("Example 1: Basic Sort Engine Usage")
    print("=" * 60)
    
    from sort_engine import SortEngine
    
    # Create sort engine (auto-detects best backend)
    engine = SortEngine()
    print(f"Selected backend: {engine.backend_name}")
    
    # Sample data
    data = [
        {'name': 'Charlie', 'age': 35, 'score': 85},
        {'name': 'Alice', 'age': 28, 'score': 92},
        {'name': 'Bob', 'age': 42, 'score': 78},
    ]
    
    # Sort by age
    result = engine.sort(data, key=lambda x: x['age'])
    print(f"\nSorted by age: {[r['name'] for r in result]}")
    
    # Sort by score (descending)
    result = engine.sort(data, key=lambda x: x['score'], reverse=True)
    print(f"Sorted by score (desc): {[r['name'] for r in result]}")
    
    # Top-K (top 2 by score)
    result = engine.sort(data, key=lambda x: x['score'], reverse=True, topk=2)
    print(f"Top 2 by score: {[r['name'] for r in result]}")


def example_2_configuration():
    """Example 2: Configuration options."""
    print("\n" + "=" * 60)
    print("Example 2: Sort Engine Configuration")
    print("=" * 60)
    
    from sort_config import SortConfig, get_sort_config
    
    # Default configuration
    config = SortConfig()
    print(f"Default backend: {config.default_backend}")
    print(f"Small threshold: {config.small_dataset_threshold:,} rows")
    
    # Custom configuration
    custom = SortConfig(
        default_backend='builtin',
        small_dataset_threshold=500,
        topk_threshold=0.05
    )
    print(f"\nCustom backend: {custom.default_backend}")
    print(f"Custom threshold: {custom.small_dataset_threshold}")
    
    # Backend selection by size
    print("\nBackend selection:")
    for size in [100, 5000, 50000, 500000]:
        backend = config.select_backend_for_size(size)
        print(f"  {size:>7,} rows -> {backend}")


def example_3_query_optimizer():
    """Example 3: Query optimizer with sort heuristics."""
    print("\n" + "=" * 60)
    print("Example 3: Query Optimizer Integration")
    print("=" * 60)
    
    from query_optimizer import QueryOptimizer
    
    optimizer = QueryOptimizer()
    
    # Simple ORDER BY
    plan = optimizer.optimize("SELECT * FROM users ORDER BY name")
    print(f"Simple ORDER BY:")
    print(f"  Strategy: {plan.sort_strategy.get('strategy', 'none')}")
    print(f"  Cost: {plan.sort_strategy.get('cost', 0):.2f}")
    
    # ORDER BY with LIMIT (should use top-K)
    plan = optimizer.optimize("SELECT * FROM products ORDER BY price LIMIT 10")
    print(f"\nORDER BY with LIMIT:")
    print(f"  Strategy: {plan.sort_strategy.get('strategy', 'none')}")
    print(f"  Top-K optimized: {plan.sort_strategy.get('topk_optimized', False)}")


def example_4_database_integration():
    """Example 4: Database integration."""
    print("\n" + "=" * 60)
    print("Example 4: Database Integration")
    print("=" * 60)
    
    # Note: This is a demonstration - actual database would need setup
    print("Creating database with sort engine...")
    
    from database import Database as KosDB
    
    try:
        db = KosDB(data_dir="example_data", server_id=1)
        print(f"Database created with sort engine: {db.sort_engine.backend_name}")
        
        # Show sort method
        sample_data = [
            {'id': 1, 'name': 'Zebra'},
            {'id': 2, 'name': 'Apple'},
            {'id': 3, 'name': 'Mango'},
        ]
        
        sorted_data = db._sort_results(sample_data, 'name', reverse=False)
        print(f"Sorted names: {[r['name'] for r in sorted_data]}")
        
        db.close()
        
    except Exception as e:
        print(f"Note: Database example skipped ({e})")


def example_5_topk_optimization():
    """Example 5: Top-K optimization demonstration."""
    print("\n" + "=" * 60)
    print("Example 5: Top-K Optimization")
    print("=" * 60)
    
    from sort_engine import SortEngine
    
    engine = SortEngine(backend='builtin')
    
    # Generate large dataset
    size = 100000
    print(f"Generating {size:,} random records...")
    
    data = [
        {'id': i, 'value': random.random() * 1000}
        for i in range(size)
    ]
    
    # Standard sort (full sort)
    import time
    start = time.perf_counter()
    full_result = engine.sort(data, key=lambda x: x['value'], reverse=True)
    full_time = time.perf_counter() - start
    top_10_full = full_result[:10]
    
    print(f"\nFull sort time: {full_time:.3f}s")
    print(f"Top 10 values: {[r['value'] for r in top_10_full]}")
    
    # Top-K sort (only get top 10)
    start = time.perf_counter()
    topk_result = engine.sort(data, key=lambda x: x['value'], reverse=True, topk=10)
    topk_time = time.perf_counter() - start
    
    print(f"\nTop-K sort time: {topk_time:.3f}s")
    print(f"Speedup: {full_time / topk_time:.2f}x")
    print(f"Top 10 values: {[r['value'] for r in topk_result]}")


def example_6_available_backends():
    """Example 6: Check available backends."""
    print("\n" + "=" * 60)
    print("Example 6: Available Backends")
    print("=" * 60)
    
    from sort_engine import detect_available_backends
    
    backends = detect_available_backends()
    
    print("Backend availability:")
    for backend, available in backends.items():
        status = "✅ Available" if available else "❌ Not available"
        print(f"  {backend:15} {status}")
    
    print("\nTo install additional backends:")
    print("  pip install madsort        # Python implementation")
    print("  pip install madsort-rust   # Rust implementation")


def example_7_performance_comparison():
    """Example 7: Compare backend performance."""
    print("\n" + "=" * 60)
    print("Example 7: Performance Comparison")
    print("=" * 60)
    
    from sort_engine import SortEngine, detect_available_backends
    
    # Generate test data
    sizes = [1000, 10000]
    backends = detect_available_backends()
    
    for size in sizes:
        print(f"\nData size: {size:,} integers")
        data = [random.randint(0, size * 10) for _ in range(size)]
        
        for backend_name, available in backends.items():
            if not available:
                continue
            
            try:
                engine = SortEngine(backend=backend_name)
                
                # Time the sort
                import time
                times = []
                for _ in range(3):
                    data_copy = data.copy()
                    start = time.perf_counter()
                    engine.sort(data_copy)
                    elapsed = time.perf_counter() - start
                    times.append(elapsed)
                
                avg_time = sum(times) / len(times)
                throughput = size / avg_time
                
                print(f"  {backend_name:15} {avg_time*1000:8.2f} ms  {throughput:10,.0f} rows/sec")
                
            except Exception as e:
                print(f"  {backend_name:15} ERROR: {e}")


def main():
    """Run all examples."""
    print("Sort Engine Examples for KosDB")
    print("=" * 60)
    
    examples = [
        example_1_basic_usage,
        example_2_configuration,
        example_3_query_optimizer,
        example_4_database_integration,
        example_5_topk_optimization,
        example_6_available_backends,
        example_7_performance_comparison,
    ]
    
    for example in examples:
        try:
            example()
        except Exception as e:
            print(f"\nExample failed: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("Examples completed!")
    print("=" * 60)
    
    print("\nFor more information, see:")
    print("  - SORT_ENGINE_GUIDE.md")
    print("  - benchmark_sort.py --full")


if __name__ == '__main__':
    main()
