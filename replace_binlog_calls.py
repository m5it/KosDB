#!/usr/bin/env python3
"""Replace all direct binlog.write_entry calls with _log_binlog_async"""

with open('database.py', 'r') as f:
    content = f.read()

# Replace all binlog write patterns
replacements = [
    # CREATE_DB
    ('''            self._binlog.write_entry(
                server_id=self.server_id,
                database=db_name,
                operation="CREATE_DB",
                data={"db_name": db_name}
            )''',
     '''            self._log_binlog_async(
                server_id=self.server_id,
                database=db_name,
                operation="CREATE_DB",
                data={"db_name": db_name}
            )'''),
    
    # DROP_DB
    ('''            self._binlog.write_entry(
                server_id=self.server_id,
                database=db_name,
                operation="DROP_DB",
                data={"db_name": db_name}
            )''',
     '''            self._log_binlog_async(
                server_id=self.server_id,
                database=db_name,
                operation="DROP_DB",
                data={"db_name": db_name}
            )'''),
    
    # CREATE_TABLE
    ('''            self._binlog.write_entry(
                server_id=self.server_id,
                database=self.current_db or "",
                operation="CREATE_TABLE",
                table=table_name,
                data={"table_name": table_name, "columns": parsed_columns, "primary_key": primary_key, "indexes": index_columns}
            )''',
     '''            self._log_binlog_async(
                server_id=self.server_id,
                database=self.current_db or "",
                operation="CREATE_TABLE",
                table=table_name,
                data={"table_name": table_name, "columns": parsed_columns, "primary_key": primary_key, "indexes": index_columns}
            )'''),
    
    # DROP_TABLE
    ('''            self._binlog.write_entry(
                server_id=self.server_id,
                database=self.current_db or "",
                operation="DROP_TABLE",
                table=table_name,
                data={"table_name": table_name}
            )''',
     '''            self._log_binlog_async(
                server_id=self.server_id,
                database=self.current_db or "",
                operation="DROP_TABLE",
                table=table_name,
                data={"table_name": table_name}
            )'''),
    
    # INSERT
    ('''            self._binlog.write_entry(
                server_id=self.server_id,
                database=self.current_db or "",
                operation="INSERT",
                table=table_name,
                data={"row": row}
            )''',
     '''            self._log_binlog_async(
                server_id=self.server_id,
                database=self.current_db or "",
                operation="INSERT",
                table=table_name,
                data={"row": row}
            )'''),
]

for old, new in replacements:
    content = content.replace(old, new)

with open('database.py', 'w') as f:
    f.write(content)

print("Replaced binlog.write_entry calls with _log_binlog_async")
