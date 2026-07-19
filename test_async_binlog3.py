#!/usr/bin/env python3
"""Test async binlog writing - simple"""

import sys
import os
import tempfile
import shutil
import time

sys.path.insert(0, '.')

try:
    from database import Database
    
    test_dir = tempfile.mkdtemp()
    print(f"Test directory: {test_dir}")
    
    db = Database(test_dir, server_id=1)
    
    # Check binlog setup
    print(f"Binlog object: {db._binlog is not None}")
    print(f"Binlog queue: {db._binlog_queue is not None}")
    print(f"Binlog thread: {db._binlog_thread is not None}")
    print(f"Binlog thread alive: {db._binlog_thread.is_alive() if db._binlog_thread else 'N/A'}")
    
    # Create database - should trigger binlog entry
    result = db.create_database("testdb")
    print(f"Create DB: {result}")
    
    # Check queue
    if db._binlog_queue:
        print(f"Queue size after CREATE_DB: {db._binlog_queue.qsize()}")
    
    # Close gracefully
    print("\nClosing database...")
    db.close()
    print("Database closed")
    
    # Cleanup
    shutil.rmtree(test_dir)
    
    print("\n✅ Async binlog test completed!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
