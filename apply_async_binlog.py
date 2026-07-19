#!/usr/bin/env python3
"""Apply async binlog changes comprehensively"""

with open('database.py', 'r') as f:
    content = f.read()

# 1. Add queue import
content = content.replace(
    'import threading\nimport plyvel',
    'import threading\nimport queue\nimport plyvel'
)

# 2. Add binlog queue/thread variables in __init__
content = content.replace(
    '''        self._binlog: Optional[Binlog] = None
        self._transaction_active = False''',
    '''        self._binlog: Optional[Binlog] = None
        self._binlog_queue: Optional[queue.Queue] = None
        self._binlog_thread: Optional[threading.Thread] = None
        self._binlog_shutdown = False
        self._transaction_active = False'''
)

# 3. Add startup call
content = content.replace(
    'self._open_binlog()\n        \n    def _cleanup_stale_locks',
    'self._open_binlog()\n        self._start_binlog_worker()\n        \n    def _cleanup_stale_locks'
)

# 4. Add binlog worker methods after _open_binlog
old_open_binlog = '''    def _open_binlog(self):
        """Open binary log for replication."""
        self._binlog = Binlog(self.data_dir)'''
    
new_methods = '''    def _open_binlog(self):
        """Open binary log for replication."""
        self._binlog = Binlog(self.data_dir)
    
    def _start_binlog_worker(self):
        """Start background thread for async binlog writing."""
        if self._binlog:
            self._binlog_queue = queue.Queue()
            self._binlog_thread = threading.Thread(target=self._binlog_worker, daemon=True)
            self._binlog_thread.start()
    
    def _binlog_worker(self):
        """Background worker that writes binlog entries from queue."""
        while not self._binlog_shutdown:
            try:
                entry = self._binlog_queue.get(timeout=1)
                if entry is None:
                    break
                self._binlog.write_entry(**entry)
                self._binlog_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Binlog worker error: {e}")
    
    def _flush_binlog_queue(self):
        """Flush remaining binlog entries on shutdown."""
        if self._binlog_queue and self._binlog:
            self._binlog_shutdown = True
            try:
                self._binlog_queue.join(timeout=5)
            except:
                pass
            while not self._binlog_queue.empty():
                try:
                    entry = self._binlog_queue.get_nowait()
                    if entry:
                        self._binlog.write_entry(**entry)
                except:
                    break
    
    def _log_binlog_async(self, **kwargs):
        """Non-blocking binlog write - puts entry in queue for background thread."""
        if self._binlog and self._binlog_queue:
            self._binlog_queue.put(kwargs)'''
    
content = content.replace(old_open_binlog, new_methods)

# 5. Update close() to flush binlog
content = content.replace(
    '''    def close(self):
        """Close the database connection."""
        if self._transaction_active:''',
    '''    def close(self):
        """Close the database connection."""
        # Flush binlog before shutdown (graceful)
        self._flush_binlog_queue()
        
        if self._transaction_active:'''
)

# 6. Replace all binlog.write_entry with _log_binlog_async
content = content.replace('self._binlog.write_entry(', 'self._log_binlog_async(')

with open('database.py', 'w') as f:
    f.write(content)

print("Async binlog implementation complete!")
