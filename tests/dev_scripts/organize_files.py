#!/usr/bin/env python3
"""Organize project files into appropriate folders"""

import os
import shutil

# Create directories
os.makedirs('docs', exist_ok=True)
os.makedirs('specs', exist_ok=True)

# Files to move to docs/ (user-facing documentation)
docs_files = [
    'README_SORT_ENGINE.md',
    'SORT_ENGINE_GUIDE.md', 
    'QUICK_REFERENCE.md',
    'sort_examples.py',  # Examples are documentation too
]

# Files to move to specs/ (technical specifications)
specs_files = [
    'SORT_INTEGRATION_SUMMARY.md',
    'PERFORMANCE_REPORT.md',
    'INTEGRATION_CHECKLIST.md',
    'IMPLEMENTATION_SUMMARY.md',
    'PROJECT_COMPLETE.md',
    'FINAL_DELIVERABLES.md',
    'PROJECT_CLOSURE.md',
]

# Move docs
print("Moving documentation files to docs/")
for f in docs_files:
    if os.path.exists(f):
        dest = os.path.join('docs', f)
        if not os.path.exists(dest):
            shutil.move(f, dest)
            print(f"  ✓ Moved {f} -> docs/{f}")
        else:
            print(f"  ⚠ {f} already exists in docs/")
    else:
        print(f"  ✗ {f} not found")

# Move specs
print("\nMoving specification files to specs/")
for f in specs_files:
    if os.path.exists(f):
        dest = os.path.join('specs', f)
        if not os.path.exists(dest):
            shutil.move(f, dest)
            print(f"  ✓ Moved {f} -> specs/{f}")
        else:
            print(f"  ⚠ {f} already exists in specs/")
    else:
        print(f"  ✗ {f} not found")

print("\n" + "="*60)
print("Organization complete!")
print("="*60)

# Show what remains in root
print("\nFiles remaining in root directory:")
for f in sorted(os.listdir('.')):
    if os.path.isfile(f) and not f.startswith('.') and f != 'organize_files.py':
        print(f"  - {f}")

print("\nDirectory structure:")
for root, dirs, files in os.walk('.'):
    if not root.startswith('./.') and '__pycache__' not in root:
        level = root.count(os.sep)
        indent = '  ' * level
        print(f"{indent}{os.path.basename(root)}/")
        for f in sorted(files):
            if not f.startswith('.'):
                print(f"{indent}  - {f}")
