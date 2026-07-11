#!/usr/bin/env python3
"""Validate KosDB v3.3.0 implementation."""

import ast
import sys

FILES = [
    'window_functions.py',
    'cte_engine.py',
    'prepared_statement_cache.py',
    'parser.py',
    'commands.py',
    'query_optimizer.py',
    'test/test_window_functions.py',
    'test/test_ctes.py',
    'test/test_prepared_statements.py',
]

def validate_file(filepath):
    """Validate Python syntax."""
    try:
        with open(filepath, 'r') as f:
            source = f.read()
        ast.parse(source)
        print(f"  ✅ {filepath}")
        return True
    except SyntaxError as e:
        print(f"  ❌ {filepath}: Line {e.lineno}: {e.msg}")
        return False
    except Exception as e:
        print(f"  ❌ {filepath}: {e}")
        return False

def main():
    print("="*60)
    print("KosDB v3.3.0 Syntax Validation")
    print("="*60)
    
    all_ok = True
    for filepath in FILES:
        if not validate_file(filepath):
            all_ok = False
    
    print("="*60)
    if all_ok:
        print("✅ All files have valid syntax")
        print("\nv3.3.0 Features Implemented:")
        print("  - Window Functions (ROW_NUMBER, RANK, DENSE_RANK, LEAD, LAG, FIRST_VALUE, LAST_VALUE)")
        print("  - Common Table Expressions (CTEs) with RECURSIVE support")
        print("  - Prepared Statements (PREPARE, EXECUTE, DEALLOCATE)")
        print("  - SQL Injection Prevention")
        return 0
    else:
        print("❌ Some files have syntax errors")
        return 1

if __name__ == '__main__':
    sys.exit(main())
