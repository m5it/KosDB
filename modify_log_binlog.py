#!/usr/bin/env python3
"""Modify _log_binlog to use queue and add shutdown handling"""

with open('database.py', 'r') as f:
    content = f.read()

# Step 5: Modify _log_binlog to use queue (non-blocking)
# Find where binlog entries are written and replace with queue put
old_binlog_write = '''        # Log to binlog
        if self._binlog:
            self._binlog.write_entry('''
    
new_binlog_write = '''        # Log to binlog (async - non-blocking)
        if self._binlog and self._binlog_queue:
            self._binlog_queue.put({'''
    
content = content.replace(old_binlog_write, new_binlog_write)

# Also need to close the parenthesis properly - find the closing pattern
old_binlog_close = '''                data={"row": row}
            )
        
        return f"Inserted'''

new_binlog_close = '''                "data": {"row": row}
            })
        
        return f"Inserted'''
    
content = content.replace(old_binlog_close, new_binlog_close)

# Fix other binlog writes similarly
content = content.replace(
    '''            self._binlog.write_entry(
                server_id=self.server_id,
                database=db_name,
                operation="DROP_DB",
                data={"db_name": db_name}
            )''',
    '''            self._binlog_queue.put({
                "server_id": self.server_id,
                "database": db_name,
                "operation": "DROP_DB",
                "data": {"db_name": db_name}
            })'''
)

content = content.replace(
    '''            self._binlog.write_entry(
                server_id=self.server_id,
                database=db_name,
                operation="CREATE_DB",
                data={"db_name": db_name}
            )''',
    '''            self._binlog_queue.put({
                "server_id": self.server_id,
                "database": db_name,
                "operation": "CREATE_DB",
                "data": {"db_name": db_name}
            })'''
)

with open('database.py', 'w') as f:
    f.write(content)

print("Step 5: Modified _log_binlog to use queue (partial)")
