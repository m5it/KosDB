
#!/usr/bin/env python3
"""
Automated Acceptance Test Runner for Batch Operations

Runs all batch-related tests and generates a comprehensive report.
"""

import subprocess
import sys
import time
from datetime import datetime


def run_test_suite(test_module, description):
    """Run a test suite and return results."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"{'='*60}")
    
    start_time = time.time()
    
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'unittest', test_module, '-v'],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        elapsed = time.time() - start_time
        
        success = result.returncode == 0
        
        print(f"\nResult: {'PASSED ✓' if success else 'FAILED ✗'}")
        print(f"Time: {elapsed:.2f}s")
        
        if not success:
            print("\nSTDERR:")
            print(result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
        
        return {
            'module': test_module,
            'description': description,
            'success': success,
            'elapsed': elapsed,
            'output': result.stdout,
            'stderr': result.stderr
        }
        
    except subprocess.TimeoutExpired:
        print(f"\nResult: TIMEOUT ✗")
        return {
            'module': test_module,
            'description': description,
            'success': False,
            'elapsed': 300,
            'output': '',
            'stderr': 'Timeout'
        }
    except Exception as e:
        print(f"\nResult: ERROR ✗ ({e})")
        return {
            'module': test_module,
            'description': description,
            'success': False,
            'elapsed': 0,
            'output': '',
            'stderr': str(e)
        }


def main():
    """Run all batch acceptance tests."""
    print("="*60)
    print("BATCH OPERATIONS ACCEPTANCE TEST SUITE")
    print(f"Started: {datetime.now().isoformat()}")
    print("="*60)
    
    test_suites = [
        ('tests.test_batch_acceptance', 'End-to-End Acceptance Tests'),
        ('tests.test_batch_backup', 'Batch Backup Tests'),
        ('tests.test_batch_geospatial', 'Batch Geospatial Tests'),
        ('tests.test_batch_migration', 'Batch Migration Tests'),
        ('tests.test_batch_vector_search', 'Batch Vector Search Tests'),
    ]
    
    results = []
    
    for module, description in test_suites:
        result = run_test_suite(module, description)
        results.append(result)
    
    # Generate summary report
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    total = len(results)
    passed = sum(1 for r in results if r['success'])
    failed = total - passed
    
    print(f"\nTotal test suites: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    print("\nDetailed Results:")
    for r in results:
        status = "✓ PASSED" if r['success'] else "✗ FAILED"
        print(f"  {status} - {r['description']} ({r['elapsed']:.2f}s)")
    
    print("\n" + "="*60)
    if failed == 0:
        print("ALL TESTS PASSED ✓")
        print("Ready for release")
    else:
        print(f"SOME TESTS FAILED ({failed}/{total}) ✗")
        print("Review failures before release")
    print("="*60)
    
    return failed == 0


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
