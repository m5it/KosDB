#!/usr/bin/env python3
"""Add missing commands to commands.py"""

with open('commands.py', 'r') as f:
    content = f.read()

# Add json import if not present
if 'import json' not in content:
    content = content.replace('import re', 'import json\nimport re')

# Find CommandRegistry and add the missing commands before it
registry_pos = content.find('class CommandRegistry:')
if registry_pos == -1:
    print("ERROR: Could not find CommandRegistry")
    exit(1)

# Add UpsertCommand before CommandRegistry
upsert_cmd = '''
class UpsertCommand(Command):
    """UPSERT command - INSERT if not exists, UPDATE if exists."""
    
    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        table = params.get('table')
        columns_str = params.get('columns', '')
        values_str = params.get('values', '')
        
        if not client_state.get('current_db'):
            return "ERROR: No database selected"
        
        # Parse columns
        if columns_str:
            columns = [c.strip() for c in columns_str.split(',')]
        else:
            columns = []
        
        # Parse values
        values = []
        for v in values_str.split(','):
            v = v.strip()
            if (v.startswith("'") and v.endswith("'")) or (v.startswith('"') and v.endswith('"')):
                v = v[1:-1]
            else:
                try:
                    v = int(v)
                except ValueError:
                    try:
                        v = float(v)
                    except ValueError:
                        pass
            values.append(v)
        
        # Get schema to find primary key
        schema = self.db._get_schema(table)
        if not schema:
            return f"ERROR: Table '{table}' does not exist"
        
        primary_key = schema.get("primary_key")
        if not primary_key:
            return self.db.insert_with_columns(table, columns, values)
        
        if primary_key not in columns:
            return f"ERROR: UPSERT requires primary key column '{primary_key}'"
        
        pk_index = columns.index(primary_key)
        pk_value = values[pk_index]
        
        # Check if row exists
        where = {primary_key: pk_value}
        result = self.db.select(table, where=where, raw=True)
        
        if result and len(result) > 0:
            # UPDATE
            set_clause = {col: val for col, val in zip(columns, values) if col != primary_key}
            if set_clause:
                update_result = self.db.update(table, set_clause, where)
                return update_result.replace("Updated", "Upserted (updated)")
            return f"OK: Upserted (no changes) 1 row in '{table}'"
        else:
            # INSERT
            insert_result = self.db.insert_with_columns(table, columns, values)
            return insert_result.replace("Inserted", "Upserted (inserted)")


class BatchUpdateCommand(Command):
    """BATCH UPDATE command - update multiple rows atomically."""
    
    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        table = params.get('table')
        set_clause_str = params.get('set', '')
        where_col = params.get('where_col', '')
        where_values_str = params.get('where_values', '')
        
        if not client_state.get('current_db'):
            return "ERROR: No database selected"
        
        # Parse SET clause
        set_clause = {}
        for assignment in set_clause_str.split(','):
            if '=' not in assignment:
                continue
            col, val = assignment.split('=', 1)
            col = col.strip()
            val = val.strip()
            if (val.startswith("'") and val.endswith("'")) or (val.startswith('"') and val.endswith('"')):
                val = val[1:-1]
            else:
                try:
                    val = int(val)
                except ValueError:
                    try:
                        val = float(val)
                    except ValueError:
                        pass
            set_clause[col] = val
        
        # Parse WHERE IN values
        where_values = []
        for v in where_values_str.split(','):
            v = v.strip()
            if (v.startswith("'") and v.endswith("'")) or (v.startswith('"') and v.endswith('"')):
                v = v[1:-1]
            else:
                try:
                    v = int(v)
                except ValueError:
                    try:
                        v = float(v)
                    except ValueError:
                        pass
            where_values.append(str(v))
        
        # Get schema
        schema = self.db._get_schema(table)
        if not schema:
            return f"ERROR: Table '{table}' does not exist"
        
        primary_key = schema.get("primary_key")
        updated_count = 0
        batch = self.db._db.write_batch()
        
        try:
            for key_val in where_values:
                if primary_key and where_col == primary_key:
                    # Fast path
                    row_key = self.db._make_key(table, key_val)
                    row_data = self.db._db.get(row_key)
                    if row_data:
                        row = json.loads(row_data.decode())
                        for col, val in set_clause.items():
                            row[col] = val
                        batch.put(row_key, json.dumps(row).encode())
                        updated_count += 1
                else:
                    # Scan
                    prefix = f"{table}:".encode()
                    for key, value in self.db._db.iterator(prefix=prefix):
                        if key.startswith(f"_schema:{table}".encode()):
                            continue
                        row = json.loads(value.decode())
                        if str(row.get(where_col)) == key_val:
                            for col, val in set_clause.items():
                                row[col] = val
                            batch.put(key, json.dumps(row).encode())
                            updated_count += 1
                            break
            
            batch.write()
            
            if self._binlog:
                self._binlog.write_entry(
                    server_id=self.db.server_id,
                    database=client_state.get('current_db', ''),
                    operation="BATCH_UPDATE",
                    table=table,
                    data={"set_clause": set_clause, "where_col": where_col, 
                          "where_values": where_values, "updated_count": updated_count}
                )
            
            return f"OK: Batch updated {updated_count} row(s) in '{table}'"
            
        except Exception as e:
            return f"ERROR: Batch update failed: {e}"


'''

content = content[:registry_pos] + upsert_cmd + content[registry_pos:]

# Add commands to registry
old_registry = """            'UPDATE': UpdateCommand(self.db, self.replication_client),
            'DELETE': DeleteCommand(self.db, self.replication_client),"""

new_registry = """            'UPDATE': UpdateCommand(self.db, self.replication_client),
            'UPSERT': UpsertCommand(self.db, self.replication_client),
            'BATCH_UPDATE': BatchUpdateCommand(self.db, self.replication_client),
            'DELETE': DeleteCommand(self.db, self.replication_client),"""

content = content.replace(old_registry, new_registry)

with open('commands.py', 'w') as f:
    f.write(content)

print("Added UpsertCommand and BatchUpdateCommand to commands.py!")
