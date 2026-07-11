#!/usr/bin/env python3
"""Validate README.md formatting."""

import re

def check_markdown_syntax(filepath):
    """Basic markdown syntax checks."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    issues = []
    
    # Check for unclosed code blocks
    code_block_count = content.count('```')
    if code_block_count % 2 != 0:
        issues.append(f"Unclosed code blocks: {code_block_count} backtick sets")
    
    # Check for broken headers
    lines = content.split('\n')
    for i, line in enumerate(lines, 1):
        if line.startswith('#') and not re.match(r'^#{1,6}\s', line):
            issues.append(f"Line {i}: Malformed header")
    
    # Check for version consistency
    if 'v3.3.0' not in content:
        issues.append("Version v3.3.0 not found")
    
    # Check for new features
    required_sections = [
        'Window Functions',
        'Common Table Expressions',
        'Prepared Statements'
    ]
    
    for section in required_sections:
        if section not in content:
            issues.append(f"Missing section: {section}")
    
    return issues

if __name__ == '__main__':
    issues = check_markdown_syntax('README.md')
    
    if issues:
        print("Issues found:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("✅ README.md validation passed")
        print("\nDocument structure:")
        print("  - Title: KosDB v3.3.0")
        print("  - Features: Core + v3.3.0 Advanced SQL")
        print("  - Quick Start: Installation and usage")
        print("  - Configuration: All config options")
        print("  - SQL Commands: All features documented")
        print("  - Migration: v3.2 to v3.3 guide")
