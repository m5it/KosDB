#!/usr/bin/env python3
"""Fix binlog reference in BatchUpdateCommand"""

with open('commands.py', 'r') as f:
    content = f.read()

# Fix the binlog reference - use self.db._binlog instead of self._binlog
content = content.replace('if self._binlog:', 'if self.db._binlog:')
content = content.replace('self._binlog.write_entry', 'self.db._binlog.write_entry')

with open('commands.py', 'w') as f:
    f.write(content)

print("Fixed binlog reference!")
