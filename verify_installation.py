#!/usr/bin/env python3
"""
KosDB Installation Verification Script
Tests that all components are properly installed and working
"""

import sys
import os
import tempfile
import shutil

def print_header(text):
    print("\n" + "="*60)
    print(text)
    print("="*60)

def print_success(text):
    print(f"✓ {text}")

def print_error(text):
    print(f"✗ {text}")
    return False

def check_leveldb():
    """Check LevelDB installation"""
    print_header("Checking LevelDB Installation")
    
    # Check library exists
    paths = [
        "/usr/local/lib/libleveldb.a",
        "/usr/lib/libleveldb.a",
        "/usr/local/lib64/libleveldb.a",
    ]
    
    found = False
    for path in paths:
        if os.path.exists(path):
            print_success(f"LevelDB library found: {path}")
            found = True
            break
    
    if not found:
        return print_error("LevelDB library not found")
    
    # Check headers
    if os.path.exists("/usr/local/include/leveldb/db.h"):
        print_success("LevelDB headers found")
    else:
        return print_error("LevelDB headers not found")
    
    # Check pkg-config
    import subprocess
    result = subprocess.run(["pkg-config", "--exists", "leveldb"])
    if result.returncode == 0:
        print_success("pkg-config entry exists")
    else:
        print("⚠ pkg-config entry not found (may need manual configuration)")
    
    return True

def check_plyvel():
    """Check Plyvel installation"""
    print_header("Checking Plyvel Installation")
    
    try:
        import plyvel
        print_success(f"Plyvel {plyvel.__version__} imported")
        print_success(f"LevelDB version: {plyvel.__leveldb_version__}")
    except ImportError as e:
        return print_error(f"Plyvel import failed: {e}")
    
    # Test basic functionality
    test_dir = tempfile.mkdtemp()
    try:
        db = plyvel.DB(test_dir, create_if_missing=True)
        db.put(b'test', b'value')
        value = db.get(b'test')
        assert value == b'value'
        db.close()
        print_success("Basic operations test passed")
    except Exception as e:
        return print_error(f"Plyvel functionality test failed: {e}")
    finally:
        shutil.rmtree(test_dir)
    
    return True

def check_kosdb():
    """Check KosDB installation"""
    print_header("Checking KosDB Installation")
    
    modules = [
        'database',
        'server',
        'commands',
        'parser',
        'auth',
        'binlog',
    ]
    
    all_ok = True
    for module in modules:
        try:
            __import__(module)
            print_success(f"Module '{module}' imported")
        except ImportError as e:
            print_error(f"Module '{module}' failed: {e}")
            all_ok = False
    
    return all_ok

def check_performance():
    """Run quick performance test"""
    print_header("Running Quick Performance Test")
    
    try:
        from database import Database
        
        test_dir = tempfile.mkdtemp()
        db = Database(test_dir, server_id=1)
        
        db.create_database("testdb")
        db.use_database("testdb")
        
        # Quick write test
        import time
        start = time.time()
        for i in range(100):
            db._db.put(f"test:{i}".encode(), b'{"data": "value"}')
        elapsed = time.time() - start
        
        ops_per_sec = 100 / elapsed
        print_success(f"Write performance: {ops_per_sec:.0f} ops/sec")
        
        # Quick read test
        start = time.time()
        for i in range(100):
            db._db.get(f"test:{i}".encode())
        elapsed = time.time() - start
        
        ops_per_sec = 100 / elapsed
        print_success(f"Read performance: {ops_per_sec:.0f} ops/sec")
        
        db.close()
        shutil.rmtree(test_dir)
        
    except Exception as e:
        return print_error(f"Performance test failed: {e}")
    
    return True

def main():
    print_header("KosDB Installation Verification")
    
    results = []
    
    results.append(("LevelDB", check_leveldb()))
    results.append(("Plyvel", check_plyvel()))
    results.append(("KosDB Modules", check_kosdb()))
    results.append(("Performance", check_performance()))
    
    print_header("Verification Summary")
    
    all_passed = all(r[1] for r in results)
    
    for name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{name:20s} {status}")
    
    print()
    if all_passed:
        print("✓ All checks passed! KosDB is ready to use.")
        print("\nStart the server with:")
        print("  python server.py")
        return 0
    else:
        print("✗ Some checks failed. Please review the errors above.")
        print("\nFor help, see:")
        print("  - INSTALL.md")
        print("  - https://github.com/m5it/KosDB")
        return 1

if __name__ == "__main__":
    sys.exit(main())
