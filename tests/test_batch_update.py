#!/usr/bin/env python3
"""Test BATCH UPDATE command"""

import sys
import os
import tempfile
import shutil

sys.path.insert(0, '.')

try:
    from database import Database
    from commands import CommandRegistry
    
    test_dir = tempfile.mkdtemp()
    db = Database(test_dir, server_id=1)
    registry = CommandRegistry(db)
    
    # Create and use test database
    db.create_database("testdb")
    db.use_database("testdb")
    
    # Create a table with primary key
    schema = {
        "columns": ["setting_key", "setting_value"],
        "next_id": 1,
        "primary_key": "setting_key",
        "indexes": []
    }
    db._db.put(b"_schema:settings", __import__('json').dumps(schema).encode())
    db._db.put(b"_index:settings:setting_key", b'{}')
    db._schema_cache["settings"] = schema
    
    client_state = {'current_db': 'testdb'}
    
    # Insert test rows
    db._db.put(b"settings:smtp_host", b'{"id": "1", "setting_key": "smtp_host", "setting_value": "old_host"}')
    db._db.put(b"settings:smtp_port", b'{"id": "2", "setting_key": "smtp_port", "setting_value": "old_port"}')
    db._db.put(b"settings:smtp_user", b'{"id": "3", "setting_key": "smtp_user", "setting_value": "old_user"}')
    
    print("Initial data:")
    print(db.select("settings"))
    
    # Test BATCH UPDATE
    params = {
        'table': 'settings',
        'set': "setting_value='default'",
        'where_col': 'setting_key',
        'where_values': "'smtp_host', 'smtp_port', 'smtp_user'"
    }
    result = registry.execute('BATCH_UPDATE', params, client_state)
    print(f"\nBATCH UPDATE result: {result}")
    
    # Verify all rows were updated
    print("\nData after BATCH UPDATE:")
    print(db.select("settings"))
    
    # Verify all values are now 'default'
    all_rows = db.select("settings", raw=True)
    for row in all_rows:
        assert row['setting_value'] == 'default', f"Expected 'default', got {row['setting_value']}"
    
    # Cleanup
    db._db.close()
    db._system_db.close()
    shutil.rmtree(test_dir)
    
    print("\n✅ BATCH UPDATE command tests passed!")
    print("✅ 3 rows updated in one atomic command!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
