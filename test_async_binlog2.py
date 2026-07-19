#!/usr/bin/env python3
"""Test async binlog writing - comprehensive"""

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
    print(f"Binlog object: {db._binlog}")
    print(f"Binlog queue: {db._binlog_queue}")
    print(f"Binlog thread: {db._binlog_thread}")
    print(f"Binlog shutdown: {db._binlog_shutdown}")
    
    # Create and use test database
    db.create_database("testdb")
    db.use_database("testdb")
    
    print("\nTesting async binlog with CREATE_DB...")
    
    # Check if binlog file exists
    import glob
    binlog_files = glob.glob(f"{test_dir}/binlog.*")
    print(f"Binlog files: {binlog_files}")
    
    # Insert data
    print("\nInserting data...")
    db.begin_transaction()
    db._transaction_put(b"test:key1", b'{"id": "1", "name": "key1", "value": "val1"}')
    result = db.commit_transaction()
    print(f"Insert result: {result}")
    
    # Check queue
    if db._binlog_queue:
        print(f"Queue size after insert: {db._binlog_queue.qsize()}")
        time.sleep(0.2)
        print(f"Queue size after wait: {db._binlog_queue.qsize()}")
    
    # Check binlog files again
    binlog_files = glob.glob(f"{test_dir}/binlog.*")
    print(f"Binlog files after operations: {binlog_files}")
    
    # Graceful shutdown
    print("\nClosing database...")
    db.close()
    
    # Check final state
    binlog_files = glob.glob(f"{test_dir}/binlog.*")
    print(f"Binlog files after close: {binlog_files}")
    
    for f in binlog_files:
        size = os.path.getsize(f)
        print(f"  {f}: {size} bytes")
    
    # Cleanup
    shutil.rmtree(test_dir)
    
    print("\n✅ Async binlog test completed!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
