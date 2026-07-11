#!/usr/bin/env python3
"""Validate Python syntax for KosDB v3.3.0 window functions."""

import ast
import sys

files_to_check = [
    'window_functions.py',
    'parser.py',
    'query_optimizer.py',
    'test/test_window_functions.py',
]

def check_file(filepath):
    """Check if file has valid Python syntax."""
    try:
        with open(filepath, 'r') as f:
            source = f.read()
        ast.parse(source)
        print(f"✅ {filepath}: OK")
        return True
    except SyntaxError as e:
        print(f"❌ {filepath}: Syntax error at line {e.lineno}: {e.msg}")
        return False
    except Exception as e:
        print(f"❌ {filepath}: Error: {e}")
        return False

def main():
    print("="*60)
    print("KosDB v3.3.0 Syntax Validation")
    print("="*60)
    
    all_ok = True
    for filepath in files_to_check:
        if not check_file(filepath):
            all_ok = False
    
    print("="*60)
    if all_ok:
        print("✅ All files have valid syntax")
        return 0
    else:
        print("❌ Some files have errors")
        return 1

if __name__ == '__main__':
    sys.exit(main())
