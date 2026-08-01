#!/usr/bin/env python3
"""Add binlog worker thread methods"""

with open('database.py', 'r') as f:
    content = f.read()

# Step 4: Add _start_binlog_worker and _binlog_worker methods after _open_binlog
old_open_binlog = '''    def _open_binlog(self):
        """Open binary log for replication."""
        self._binlog = Binlog(self.data_dir)'''
    
new_open_binlog = '''    def _open_binlog(self):
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
                # Wait up to 1 second for entries
                entry = self._binlog_queue.get(timeout=1)
                if entry is None:  # Shutdown signal
                    break
                # Write to binlog
                self._binlog.write_entry(**entry)
                self._binlog_queue.task_done()
            except queue.Empty:
                continue  # Check shutdown flag
            except Exception as e:
                # Log error but continue processing
                print(f"Binlog worker error: {e}")
                continue
    
    def _flush_binlog_queue(self):
        """Flush remaining binlog entries on shutdown."""
        if self._binlog_queue and self._binlog:
            # Signal no more entries
            self._binlog_shutdown = True
            # Wait for queue to empty (with timeout)
            try:
                self._binlog_queue.join(timeout=5)
            except:
                pass
            # Process any remaining entries
            while not self._binlog_queue.empty():
                try:
                    entry = self._binlog_queue.get_nowait()
                    if entry:
                        self._binlog.write_entry(**entry)
                except:
                    break'''
    
content = content.replace(old_open_binlog, new_open_binlog)

with open('database.py', 'w') as f:
    f.write(content)

print("Step 4: Added binlog worker thread methods")
