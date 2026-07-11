#!/usr/bin/env python3
"""
Simple Test Runner for KosDB v3.2.0

Runs basic import and syntax checks for all test files.
"""

import sys
import os
import ast

# Test files to verify
TEST_FILES = [
TEST_FILES = [
    'test/test_check_constraints.py',
    'test/test_alter_table.py',
    'test/test_subqueries.py',
    'test/test_metrics.py',
    'test/test_query_plan_cache.py',
    'test/test_window_functions.py',
    'test/test_ctes.py',
    'test/test_prepared_statements.py',
]
    if not os.path.exists(full_path):
        return False, f"File not found: {filepath}"
    
    try:
        with open(full_path, 'r') as f:
            source = f.read()
        ast.parse(source)
        return True, "OK"
    except SyntaxError as e:
        return False, f"Syntax error: {e}"

def main():
    print("="*70)
    print("KOSDB v3.2.0 TEST VERIFICATION")
    print("="*70)
    
    all_ok = True
    
    print("\nChecking test files...")
    for test_file in TEST_FILES:
        success, msg = check_file(test_file)
    modules = ['database', 'parser', 'commands', 'query_optimizer', 'metrics', 'window_functions']
        print(f"  {status} {test_file}: {msg}")
        if not success:
    modules = ['database', 'parser', 'commands', 'query_optimizer', 'metrics', 'window_functions', 'cte_engine', 'prepared_statement_cache']
    
    # Check core modules
    print("\nChecking core modules...")
    sys.path.insert(0, os.path.dirname(__file__))
    
    modules = ['database', 'parser', 'commands', 'query_optimizer', 'metrics']
    for mod in modules:
        try:
            __import__(mod)
            print(f"  ✅ {mod}: OK")
        except Exception as e:
            print(f"  ❌ {mod}: {e}")
            all_ok = False
    
    print("\n" + "="*70)
        print("  python -m unittest test.test_check_constraints -v")
        print("  python -m unittest test.test_alter_table -v")
        print("  python -m unittest test.test_subqueries -v")
        print("  python -m unittest test.test_check_constraints -v")
        print("  python -m unittest test.test_alter_table -v")
        print("  python -m unittest test.test_subqueries -v")
        print("  python -m unittest test.test_metrics -v")
        print("  python -m unittest test.test_query_plan_cache -v")
        print("  python -m unittest test.test_window_functions -v")
        print("  python -m unittest test.test_ctes -v")
        print("  python -m unittest test.test_prepared_statements -v")
    return 0 if all_ok else 1

if __name__ == '__main__':
    sys.exit(main())
