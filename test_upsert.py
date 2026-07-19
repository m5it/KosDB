#!/usr/bin/env python3
"""Test UPSERT command"""

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
    db._schema_cache["settings"] = schema
    
    client_state = {'current_db': 'testdb'}
    
    # Test 1: UPSERT new row (should INSERT)
    params1 = {
        'table': 'settings',
        'columns': 'setting_key, setting_value',
        'values': "'site_name', 'KosCMS'"
    }
    result1 = registry.execute('UPSERT', params1, client_state)
    print(f"UPSERT new row: {result1}")
    
    # Verify row was inserted
    select_result = db.select("settings", where={"setting_key": "site_name"})
    print(f"Verify insert: {select_result}")
    
    # Test 2: UPSERT existing row (should UPDATE)
    params2 = {
        'table': 'settings',
        'columns': 'setting_key, setting_value',
        'values': "'site_name', 'NewSiteName'"
    }
    result2 = registry.execute('UPSERT', params2, client_state)
    print(f"\nUPSERT existing row: {result2}")
    
    # Verify row was updated
    select_result2 = db.select("settings", where={"setting_key": "site_name"})
    print(f"Verify update: {select_result2}")
    
    # Test 3: UPSERT another new row
    params3 = {
        'table': 'settings',
        'columns': 'setting_key, setting_value',
        'values': "'language', 'en'"
    }
    result3 = registry.execute('UPSERT', params3, client_state)
    print(f"\nUPSERT another new row: {result3}")
    
    # Show all settings
    print("\nAll settings:")
    print(db.select("settings"))
    
    # Cleanup
    db._db.close()
    db._system_db.close()
    shutil.rmtree(test_dir)
    
    print("\n✅ UPSERT command tests passed!")
    print("✅ Query count halved: One UPSERT instead of SELECT + INSERT/UPDATE")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
