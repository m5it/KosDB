#!/usr/bin/env python3
"""Fix: Add call to _start_binlog_worker in __init__"""

with open('database.py', 'r') as f:
    content = f.read()

# Find and replace the _open_binlog() call to also start worker
old_init = '''        self._open_system_db()
        self._open_binlog()
    
    def _cleanup_stale_locks'''

new_init = '''        self._open_system_db()
        self._open_binlog()
        self._start_binlog_worker()
    
    def _cleanup_stale_locks'''

content = content.replace(old_init, new_init)

with open('database.py', 'w') as f:
    f.write(content)

print("Fixed: Added _start_binlog_worker() call in __init__")
