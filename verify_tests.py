#!/usr/bin/env python3
"""
Test Verification Script for KosDB v3.2.0

Verifies that all test files can be imported and have correct syntax.
"""

import sys
import os
import ast
import importlib.util

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TEST_FILES = [
    'test/test_check_constraints.py',
    'test/test_alter_table.py',
    'test/test_subqueries.py',
    'test/test_metrics.py',
    'test/test_query_plan_cache.py',
]

CORE_MODULES = [
    'database',
    'parser',
    'commands',
    'query_optimizer',
    'metrics',
    'metrics_server',
]

def check_syntax(filepath):
    """Check if Python file has valid syntax."""
    try:
        with open(filepath, 'r') as f:
            source = f.read()
        ast.parse(source)
        return True, None
    except SyntaxError as e:
        return False, str(e)

def check_imports(module_name):
    """Check if module can be imported."""
    try:
        module = importlib.import_module(module_name)
        return True, None
    except Exception as e:
        return False, str(e)

def main():
    """Run verification checks."""
    print("="*70)
    print("KOSDB v3.2.0 TEST VERIFICATION")
    print("="*70)
    
    all_passed = True
    
    # Check core modules
    print("\n1. Checking Core Modules...")
    print("-"*70)
    for module in CORE_MODULES:
        success, error = check_imports(module)
        status = "✅" if success else "❌"
        print(f"  {status} {module}")
        if not success:
            print(f"      Error: {error}")
            all_passed = False
    
    # Check test files exist and have valid syntax
    print("\n2. Checking Test Files...")
    print("-"*70)
    for test_file in TEST_FILES:
        filepath = os.path.join(os.path.dirname(__file__), test_file)
        if not os.path.exists(filepath):
            print(f"  ❌ {test_file} - FILE NOT FOUND")
            all_passed = False
            continue
            
        success, error = check_syntax(filepath)
        status = "✅" if success else "❌"
        print(f"  {status} {test_file}")
        if not success:
            print(f"      Syntax Error: {error}")
            all_passed = False
    
    # Check for required imports in test files
    print("\n3. Checking Test File Structure...")
    print("-"*70)
    
    required_imports = ['unittest', 'sys', 'os']
    
    for test_file in TEST_FILES:
        filepath = os.path.join(os.path.dirname(__file__), test_file)
        if not os.path.exists(filepath):
            continue
            
        with open(filepath, 'r') as f:
            content = f.read()
        
        missing = []
        for imp in required_imports:
            if imp not in content:
                missing.append(imp)
        
        if missing:
            print(f"  ⚠️  {test_file} - Missing imports: {', '.join(missing)}")
        else:
            print(f"  ✅ {test_file} - All required imports present")
    
    # Summary
    print("\n" + "="*70)
    if all_passed:
        print("✅ ALL CHECKS PASSED")
        print("\nTests are ready to run with:")
        print("  python -m unittest discover -s test -v")
    else:
        print("❌ SOME CHECKS FAILED")
        print("\nPlease fix the errors above before running tests.")
    print("="*70)
    
    return 0 if all_passed else 1

if __name__ == '__main__':
    sys.exit(main())
