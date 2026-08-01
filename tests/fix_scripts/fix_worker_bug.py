#!/usr/bin/env python3
"""Fix: Binlog worker should write to binlog, not call _log_binlog_async"""

with open('database.py', 'r') as f:
    content = f.read()

# Fix the worker to write directly to binlog
old_worker = '''    def _binlog_worker(self):
        """Background worker that writes binlog entries from queue."""
        while not self._binlog_shutdown:
            try:
                entry = self._binlog_queue.get(timeout=1)
                if entry is None:
                    break
                self._log_binlog_async(**entry)
                self._binlog_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Binlog worker error: {e}")'''

new_worker = '''    def _binlog_worker(self):
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
                print(f"Binlog worker error: {e}")'''

content = content.replace(old_worker, new_worker)

# Also fix _flush_binlog_queue
old_flush = '''    def _flush_binlog_queue(self):
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
                        self._log_binlog_async(**entry)
                except:
                    break'''

new_flush = '''    def _flush_binlog_queue(self):
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
                    break'''

content = content.replace(old_flush, new_flush)

with open('database.py', 'w') as f:
    f.write(content)

print("Fixed: Binlog worker now writes directly to binlog")
