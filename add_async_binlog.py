#!/usr/bin/env python3
"""Add async binlog writing with background thread"""

with open('database.py', 'r') as f:
    content = f.read()

# Step 1: Add queue import and thread initialization in __init__
old_init = '''import os
import json
import hashlib
import secrets
import time
import threading
import plyvel
from typing import Optional, Dict, Any, List
from binlog import Binlog'''

new_init = '''import os
import json
import hashlib
import secrets
import time
import threading
import queue
import plyvel
from typing import Optional, Dict, Any, List
from binlog import Binlog'''

content = content.replace(old_init, new_init)

# Step 2: Add binlog queue and thread in __init__
old_binlog_init = '''        self._binlog: Optional[Binlog] = None
        self._transaction_active = False'''

new_binlog_init = '''        self._binlog: Optional[Binlog] = None
        self._binlog_queue: Optional[queue.Queue] = None
        self._binlog_thread: Optional[threading.Thread] = None
        self._binlog_shutdown = False
        self._transaction_active = False'''

content = content.replace(old_binlog_init, new_binlog_init)

# Step 3: Add queue and thread startup after _open_binlog
old_open_binlog_call = '''        self._open_system_db()
        self._open_binlog()'''
    
new_open_binlog_call = '''        self._open_system_db()
        self._open_binlog()
        self._start_binlog_worker()'''

content = content.replace(old_open_binlog_call, new_open_binlog_call)

with open('database.py', 'w') as f:
    f.write(content)

print("Step 1-3: Added queue import, binlog queue/thread initialization, and startup call")
