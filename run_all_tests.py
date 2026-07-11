#!/usr/bin/env python3
"""
Comprehensive Test Runner for KosDB v3.2.0

Runs all test files and reports results.
"""

import unittest
import sys
import os
import importlib
import traceback

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Test modules to run
TEST_MODULES = [
    'test.test_check_constraints',
    'test.test_alter_table',
    'test.test_subqueries',
    'test.test_metrics',
    'test.test_query_plan_cache',
]

def run_test_module(module_name):
    """Run a single test module and return results."""
    print(f"\n{'='*70}")
    print(f"Running: {module_name}")
    print('='*70)
    
    try:
        # Import the module
        module = importlib.import_module(module_name)
        
        # Create test suite
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromModule(module)
        
        # Run tests
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        
        # Return summary
        return {
            'name': module_name,
            'run': result.testsRun,
            'failures': len(result.failures),
            'errors': len(result.errors),
            'skipped': len(result.skipped),
            'success': result.wasSuccessful()
        }
        
    except Exception as e:
        print(f"ERROR loading {module_name}: {e}")
        traceback.print_exc()
        return {
            'name': module_name,
            'run': 0,
            'failures': 0,
            'errors': 1,
            'skipped': 0,
            'success': False,
            'error_msg': str(e)
        }

def main():
    """Run all tests and report results."""
    print("="*70)
    print("KOSDB v3.2.0 COMPREHENSIVE TEST SUITE")
    print("="*70)
    
    results = []
    total_run = 0
    total_failures = 0
    total_errors = 0
    total_skipped = 0
    
    for module_name in TEST_MODULES:
        result = run_test_module(module_name)
        results.append(result)
        
        total_run += result['run']
        total_failures += result['failures']
        total_errors += result['errors']
        total_skipped += result['skipped']
    
    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    for result in results:
        status = "✅ PASS" if result['success'] else "❌ FAIL"
        print(f"\n{result['name']}:")
        print(f"  Status: {status}")
        print(f"  Tests run: {result['run']}")
        print(f"  Failures: {result['failures']}")
        print(f"  Errors: {result['errors']}")
        print(f"  Skipped: {result['skipped']}")
        
        if 'error_msg' in result:
            print(f"  Error: {result['error_msg']}")
    
    print("\n" + "="*70)
    print(f"TOTAL: {total_run} tests, {total_failures} failures, {total_errors} errors, {total_skipped} skipped")
    
    if total_failures == 0 and total_errors == 0:
        print("✅ ALL TESTS PASSED")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        return 1

if __name__ == '__main__':
    sys.exit(main())
