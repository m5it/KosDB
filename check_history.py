#!/usr/bin/env python3
"""Check HISTORY.md and move it if appropriate"""

import os

# HISTORY.md is typically a project changelog/history
# It should go in docs/ for user visibility

if os.path.exists('HISTORY.md'):
    import shutil
    shutil.move('HISTORY.md', 'docs/HISTORY.md')
    print("Moved HISTORY.md -> docs/HISTORY.md")
else:
    print("HISTORY.md not found in root")

# Final check
print("\n" + "="*60)
print("FINAL CHECK - Remaining .md files in root:")
print("="*60)
remaining = [f for f in os.listdir('.') if f.endswith('.md') and os.path.isfile(f)]
if remaining:
    for f in sorted(remaining):
        print(f"  - {f}")
else:
    print("  None! All .md files organized.")

print("\n" + "="*60)
print("Organization Summary:")
print("="*60)

docs_files = [f for f in os.listdir('docs') if f.endswith('.md')]
specs_files = [f for f in os.listdir('specs') if f.endswith('.md')]

print(f"docs/:  {len(docs_files)} .md files")
print(f"specs/: {len(specs_files)} .md files")
print(f"root:  {len(remaining)} .md files")
