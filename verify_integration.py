#!/usr/bin/env python3
"""
Final Verification Script for Sort Engine Integration

Checks:
- All modules import correctly
- Sort engine initializes
- Database integration works
- Configuration loads
- Tests can run
"""

import sys
import os


def check_imports():
    """Verify all modules can be imported."""
    print("Checking imports...")
    
    modules = [
        'sort_engine',
        'sort_config',
        'sort_backends.builtin',
        'sort_backends.madsort_py',
        'sort_backends.madsort_rust',
        'query_optimizer',
    ]
    
    failed = []
    for module in modules:
        try:
            __import__(module)
            print(f"  ✓ {module}")
        except ImportError as e:
            print(f"  ✗ {module}: {e}")
            failed.append(module)
    
    return len(failed) == 0


def check_sort_engine():
    """Verify sort engine works."""
    print("\nChecking sort engine...")
    
    try:
        from sort_engine import SortEngine, detect_available_backends
        
        # Check backend detection
        backends = detect_available_backends()
        print(f"  Available backends: {backends}")
        
        # Create engine
        engine = SortEngine(backend='auto')
        print(f"  Selected backend: {engine.backend_name}")
        
        # Test sort
        data = [3, 1, 4, 1, 5, 9, 2, 6]
        result = engine.sort(data)
        assert result == [1, 1, 2, 3, 4, 5, 6, 9], "Sort failed"
        print("  ✓ Sort works")
        
        # Test top-K
        result = engine.sort(list(range(100)), topk=10)
        assert len(result) == 10, "Top-K failed"
        print("  ✓ Top-K works")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Sort engine error: {e}")
        return False


def check_configuration():
    """Verify configuration system."""
    print("\nChecking configuration...")
    
    try:
        from sort_config import SortConfig
        
        # Default config
        config = SortConfig()
        print(f"  Default backend: {config.default_backend}")
        
        # Backend selection
        backend = config.select_backend_for_size(5000)
        print(f"  Backend for 5000 rows: {backend}")
        
        print("  ✓ Configuration works")
        return True
        
    except Exception as e:
        print(f"  ✗ Configuration error: {e}")
        return False


def check_database_integration():
    """Verify database integration."""
    print("\nChecking database integration...")
    
    try:
        import tempfile
        import shutil
        
        from database import Database
        
        # Create temp database
        test_dir = tempfile.mkdtemp()
        
        try:
            db = Database(data_dir=test_dir, server_id=1)
            
            # Check sort engine exists
            if hasattr(db, 'sort_engine') and db.sort_engine:
                print(f"  Sort engine: {db.sort_engine.backend_name}")
                print("  ✓ Database integration works")
                success = True
            else:
                print("  ✗ Sort engine not available")
                success = False
            
            db.close()
            
        finally:
            shutil.rmtree(test_dir)
        
        return success
        
    except Exception as e:
        print(f"  ✗ Database error: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_tests():
    """Verify tests can run."""
    print("\nChecking tests...")
    
    try:
        import subprocess
        
        # Run a quick test
        result = subprocess.run(
            [sys.executable, '-m', 'pytest', 'test_sort_engine.py', '-v', '-x', '-k', 'test_builtin'],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print("  ✓ Tests pass")
            return True
        else:
            print(f"  ✗ Tests failed")
            print(result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)
            return False
            
    except Exception as e:
        print(f"  ✗ Test error: {e}")
        return False


def main():
    """Run all verification checks."""
    print("=" * 60)
    print("Sort Engine Integration Verification")
    print("=" * 60)
    
    checks = [
        ("Imports", check_imports),
        ("Sort Engine", check_sort_engine),
        ("Configuration", check_configuration),
        ("Database Integration", check_database_integration),
        ("Tests", check_tests),
    ]
    
    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ {name} failed with exception: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("Verification Summary")
    print("=" * 60)
    
    all_passed = True
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {name:20} {status}")
        if not result:
            all_passed = False
    
    print("=" * 60)
    if all_passed:
        print("✓ All checks passed!")
        print("\nSort engine integration is ready.")
        return 0
    else:
        print("✗ Some checks failed.")
        print("\nPlease review the errors above.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
