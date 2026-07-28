#!/usr/bin/env python3
"""
Final Validation for Sort Engine Integration

Comprehensive validation before release:
1. Import validation
2. Functionality tests
3. Performance benchmarks
4. Edge case handling
5. Integration verification
"""

import sys
import tempfile
import shutil
import time
import random


def test_imports():
    """Test all imports work."""
    print("=" * 60)
    print("1. Import Validation")
    print("=" * 60)
    
    imports = {
        'sort_engine': ['SortEngine', 'get_sort_engine', 'detect_available_backends'],
        'sort_config': ['SortConfig', 'get_sort_config'],
        'sort_backends.builtin': ['BuiltinBackend'],
        'sort_backends.madsort_py': ['MadS0rtPyBackend'],
        'sort_backends.madsort_rust': ['MadS0rtRustBackend'],
    }
    
    all_ok = True
    for module, items in imports.items():
        try:
            mod = __import__(module, fromlist=items)
            for item in items:
                if hasattr(mod, item):
                    print(f"  ✓ {module}.{item}")
                else:
                    print(f"  ✗ {module}.{item} - NOT FOUND")
                    all_ok = False
        except ImportError as e:
            print(f"  ✗ {module} - {e}")
            all_ok = False
    
    return all_ok


def test_basic_functionality():
    """Test basic sort functionality."""
    print("\n" + "=" * 60)
    print("2. Basic Functionality Tests")
    print("=" * 60)
    
    from sort_engine import SortEngine
    
    tests_passed = 0
    tests_failed = 0
    
    # Test 1: Integer sort
    try:
        engine = SortEngine(backend='builtin')
        data = [3, 1, 4, 1, 5, 9, 2, 6]
        result = engine.sort(data)
        assert result == [1, 1, 2, 3, 4, 5, 6, 9]
        print("  ✓ Integer sort")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Integer sort: {e}")
        tests_failed += 1
    
    # Test 2: String sort
    try:
        data = ['banana', 'apple', 'cherry']
        result = engine.sort(data)
        assert result == ['apple', 'banana', 'cherry']
        print("  ✓ String sort")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ String sort: {e}")
        tests_failed += 1
    
    # Test 3: Sort with key
    try:
        data = [{'name': 'Charlie', 'age': 35}, {'name': 'Alice', 'age': 28}]
        result = engine.sort(data, key=lambda x: x['age'])
        assert result[0]['name'] == 'Alice'
        print("  ✓ Sort with key")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Sort with key: {e}")
        tests_failed += 1
    
    # Test 4: Reverse sort
    try:
        data = [1, 2, 3, 4, 5]
        result = engine.sort(data, reverse=True)
        assert result == [5, 4, 3, 2, 1]
        print("  ✓ Reverse sort")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Reverse sort: {e}")
        tests_failed += 1
    
    # Test 5: Top-K
    try:
        data = list(range(100))
        random.shuffle(data)
        result = engine.sort(data, topk=10)
        assert len(result) == 10
        print("  ✓ Top-K optimization")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Top-K: {e}")
        tests_failed += 1
    
    # Test 6: In-place sort
    try:
        data = [3, 1, 4, 1, 5]
        engine.sort_in_place(data)
        assert data == [1, 1, 3, 4, 5]
        print("  ✓ In-place sort")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ In-place sort: {e}")
        tests_failed += 1
    
    print(f"\n  Passed: {tests_passed}/{tests_passed + tests_failed}")
    return tests_failed == 0


def test_configuration():
    """Test configuration system."""
    print("\n" + "=" * 60)
    print("3. Configuration Tests")
    print("=" * 60)
    
    from sort_config import SortConfig
    
    tests_passed = 0
    tests_failed = 0
    
    # Test 1: Default config
    try:
        config = SortConfig()
        assert config.default_backend == 'auto'
        print("  ✓ Default configuration")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Default config: {e}")
        tests_failed += 1
    
    # Test 2: Backend selection
    try:
        config = SortConfig()
        backend = config.select_backend_for_size(5000)
        assert backend in ['builtin', 'madsort_py', 'madsort_rust', 'auto']
        print("  ✓ Backend selection")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Backend selection: {e}")
        tests_failed += 1
    
    # Test 3: Top-K threshold
    try:
        config = SortConfig(topk_threshold=0.1)
        assert config.should_use_topk(10, 200) == True
        assert config.should_use_topk(50, 200) == False
        print("  ✓ Top-K threshold")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Top-K threshold: {e}")
        tests_failed += 1
    
    # Test 4: Validation
    try:
        config = SortConfig()
        assert config.validate() == True
        print("  ✓ Configuration validation")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Validation: {e}")
        tests_failed += 1
    
    print(f"\n  Passed: {tests_passed}/{tests_passed + tests_failed}")
    return tests_failed == 0


def test_database_integration():
    """Test database integration."""
    print("\n" + "=" * 60)
    print("4. Database Integration Tests")
    print("=" * 60)
    
    from database import Database
    
    test_dir = tempfile.mkdtemp()
    tests_passed = 0
    tests_failed = 0
    
    try:
        # Test 1: Database creation with sort engine
        try:
            db = Database(data_dir=test_dir, server_id=1)
            assert hasattr(db, 'sort_engine')
            assert db.sort_engine is not None
            print("  ✓ Database with sort engine")
            tests_passed += 1
        except Exception as e:
            print(f"  ✗ Database creation: {e}")
            tests_failed += 1
            return False
        
        # Test 2: Sort results helper
        try:
            sample = [{'id': 3}, {'id': 1}, {'id': 2}]
            result = db._sort_results(sample, 'id', False)
            assert [r['id'] for r in result] == [1, 2, 3]
            print("  ✓ Sort results helper")
            tests_passed += 1
        except Exception as e:
            print(f"  ✗ Sort results: {e}")
            tests_failed += 1
        
        # Test 3: Fallback count
        try:
            count = db.sort_engine.fallback_count
            assert isinstance(count, int)
            print("  ✓ Fallback count accessible")
            tests_passed += 1
        except Exception as e:
            print(f"  ✗ Fallback count: {e}")
            tests_failed += 1
        
        db.close()
        
    finally:
        shutil.rmtree(test_dir)
    
    print(f"\n  Passed: {tests_passed}/{tests_passed + tests_failed}")
    return tests_failed == 0


def test_performance():
    """Test performance characteristics."""
    print("\n" + "=" * 60)
    print("5. Performance Tests")
    print("=" * 60)
    
    from sort_engine import SortEngine
    
    engine = SortEngine(backend='builtin')
    
    # Test 1: Large dataset sort
    try:
        data = [random.random() for _ in range(100000)]
        start = time.perf_counter()
        result = engine.sort(data)
        elapsed = time.perf_counter() - start
        
        assert len(result) == 100000
        assert elapsed < 5.0  # Should complete in < 5 seconds
        
        print(f"  ✓ Large dataset sort ({elapsed:.2f}s)")
    except Exception as e:
        print(f"  ✗ Large dataset sort: {e}")
        return False
    
    # Test 2: Top-K performance
    try:
        data = [random.random() for _ in range(100000)]
        
        start = time.perf_counter()
        full_result = engine.sort(data)
        full_time = time.perf_counter() - start
        
        start = time.perf_counter()
        topk_result = engine.sort(data, topk=100)
        topk_time = time.perf_counter() - start
        
        speedup = full_time / topk_time
        print(f"  ✓ Top-K optimization ({speedup:.1f}x speedup)")
        
    except Exception as e:
        print(f"  ✗ Top-K performance: {e}")
        return False
    
    return True


def test_edge_cases():
    """Test edge cases."""
    print("\n" + "=" * 60)
    print("6. Edge Case Tests")
    print("=" * 60)
    
    from sort_engine import SortEngine
    
    engine = SortEngine(backend='builtin')
    tests_passed = 0
    
    # Test 1: Empty list
    try:
        result = engine.sort([])
        assert result == []
        print("  ✓ Empty list")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Empty list: {e}")
    
    # Test 2: Single element
    try:
        result = engine.sort([42])
        assert result == [42]
        print("  ✓ Single element")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Single element: {e}")
    
    # Test 3: Already sorted
    try:
        data = list(range(1000))
        result = engine.sort(data)
        assert result == data
        print("  ✓ Already sorted")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Already sorted: {e}")
    
    # Test 4: Reverse sorted
    try:
        data = list(range(1000, 0, -1))
        result = engine.sort(data)
        assert result == list(range(1, 1001))
        print("  ✓ Reverse sorted")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Reverse sorted: {e}")
    
    # Test 5: Duplicates
    try:
        data = [1] * 1000
        result = engine.sort(data)
        assert result == [1] * 1000
        print("  ✓ All duplicates")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Duplicates: {e}")
    
    print(f"\n  Passed: {tests_passed}/5")
    return tests_passed == 5


def main():
    """Run all validation tests."""
    print("=" * 60)
    print("FINAL VALIDATION")
    print("Sort Engine Integration for KosDB")
    print("=" * 60)
    
    results = []
    
    # Run all tests
    results.append(("Imports", test_imports()))
    results.append(("Functionality", test_basic_functionality()))
    results.append(("Configuration", test_configuration()))
    results.append(("Database Integration", test_database_integration()))
    results.append(("Performance", test_performance()))
    results.append(("Edge Cases", test_edge_cases()))
    
    # Summary
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {name:25} {status}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("✓ ALL VALIDATION TESTS PASSED")
        print("\nThe sort engine integration is ready for production.")
        return 0
    else:
        print("✗ SOME TESTS FAILED")
        print("\nPlease review the failures above.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
