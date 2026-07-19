
"""
Command Execution Framework for LevelDB Socket Server
KosDB v2.3.0 - Batch Execution Support
"""

import json
import re
from typing import Dict, Any, Optional, List
from database import Database


class Command:
    """Base command class."""
    def __init__(self, db: Database, replication_client=None):
        self.db = db
        self.replication_client = replication_client
    
    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        raise NotImplementedError
    
    def validate_params(self, params: Dict[str, Any], required: List[str]) -> bool:
        for param in required:
            if param not in params or params[param] is None:
                return False
        return True


class BatchStatusCommand(Command):
    """Get status of last batch execution."""
    def execute(self, params, client_state):
        batch_id = params.get('batch_id')
        
        batch_executor = getattr(self.db, '_batch_executor', None)
        
        if not batch_executor:
            return "ERROR: Batch execution not initialized"
        
        try:
            if batch_id:
                status = batch_executor.get_batch_status(batch_id)
            else:
                status = batch_executor.get_last_batch_status(
                    client_state.get('username')
                )
            
            if not status:
                return "OK: No batch execution found"
            
            lines = []
            lines.append("-" * 60)
            lines.append(f"Batch ID: {status['batch_id']}")
            lines.append(f"Timestamp: {status['timestamp']}")
            lines.append(f"User: {status['user_id']}")
            lines.append(f"Commands: {status['command_count']}")
            lines.append(f"Error Mode: {status['error_mode']}")
            lines.append(f"Total Time: {status['total_time_ms']:.2f}ms")
            lines.append(f"Success: {status['success_count']}")
            lines.append(f"Errors: {status['error_count']}")
            
            if status.get('was_rolled_back'):
                lines.append("Status: ROLLED BACK")
            else:
                lines.append("Status: COMPLETED")
            
            lines.append("-" * 60)
            return "\n".join(lines)
            
        except Exception as e:
            return f"ERROR: {e}"


class CreateDatabaseCommand(Command):
    def execute(self, params, client_state):
        if not self.validate_params(params, ['database']):
            return "ERROR: Database name required"
        try:
            self.db.create_database(params['database'])
            return f"OK: Database '{params['database']}' created"
        except Exception as e:
            return f"ERROR: {e}"


class DropDatabaseCommand(Command):
    def execute(self, params, client_state):
        if not self.validate_params(params, ['database']):
            return "ERROR: Database name required"
        try:
            self.db.drop_database(params['database'])
            if client_state.get('current_db') == params['database']:
                client_state['current_db'] = None
            return f"OK: Database '{params['database']}' dropped"
        except Exception as e:
            return f"ERROR: {e}"


class UseDatabaseCommand(Command):
    def execute(self, params, client_state):
        if not self.validate_params(params, ['database']):
            return "ERROR: Database name required"
        try:
            result = self.db.use_database(params['database'])
            client_state['current_db'] = params['database']
            return result
        except Exception as e:
            return f"ERROR: {e}"


class CreateTableCommand(Command):
    def execute(self, params, client_state):
        if not self.validate_params(params, ['table']):
            return "ERROR: Table name required"
        if not client_state.get('current_db'):
            return "ERROR: No database selected"
        try:
            columns = params.get('columns', [])
            self.db.create_table(params['table'], columns)
            return f"OK: Table '{params['table']}' created"
        except Exception as e:
            return f"ERROR: {e}"


class DropTableCommand(Command):
    def execute(self, params, client_state):
        if not self.validate_params(params, ['table']):
            return "ERROR: Table name required"
        if not client_state.get('current_db'):
            return "ERROR: No database selected"
        try:
            self.db.drop_table(params['table'])
            return f"OK: Table '{params['table']}' dropped"
        except Exception as e:
            return f"ERROR: {e}"



class InsertCommand(Command):
    def execute(self, params, client_state):
        if not self.validate_params(params, ['table', 'values']):
            return "ERROR: Table and values required"
        if not client_state.get('current_db'):
            return "ERROR: No database selected"
        try:
            # Support optional column list: INSERT INTO table (col1, col2) VALUES (...)
            columns = params.get('columns')
            if columns:
                # Columns already parsed as list by parser
                self.db.insert_with_columns(params['table'], columns, params['values'])
            else:
                self.db.insert(params['table'], params['values'])
            return f"OK: Inserted into '{params['table']}'"
        except Exception as e:
            return f"ERROR: {e}"

            return f"ERROR: {e}"

class SelectCommand(Command):
    def execute(self, params, client_state):
        if not self.validate_params(params, ['table']):
            return "ERROR: Table name required"
        if not client_state.get('current_db'):
            return "ERROR: No database selected"
        try:
            columns = params.get('columns', ['*'])
            where = params.get('where')
            order_by = params.get('order_by')
            order_desc = params.get('order_desc', False)
            result = self.db.select(params['table'], columns, where, order_by, order_desc)
            return result
        except Exception as e:
            return f"ERROR: {e}"


class UpdateCommand(Command):
    def execute(self, params, client_state):
        if not self.validate_params(params, ['table', 'set']):
            return "ERROR: Table and SET required"
        if not client_state.get('current_db'):
            return "ERROR: No database selected"
        try:
            result = self.db.update(params['table'], params['set'], params.get('where'))
            # Extract row count from result string like "Updated 5 row(s) in 'table'"
            match = re.search(r'Updated (\d+) row', result)
            num = int(match.group(1)) if match else 0
            return f"OK: Updated {num} row(s)"
        except Exception as e:
            return f"ERROR: {e}"


class DeleteCommand(Command):
    def execute(self, params, client_state):
        if not self.validate_params(params, ['table']):
            return "ERROR: Table name required"
        if not client_state.get('current_db'):
            return "ERROR: No database selected"
        try:
            count = self.db.delete(params['table'], params.get('where'))
            return f"OK: Deleted {count} row(s)"
        except Exception as e:
            return f"ERROR: {e}"


class ShowTablesCommand(Command):
    def execute(self, params, client_state):
        if not client_state.get('current_db'):
            return "ERROR: No database selected"
        try:
            tables = self.db.list_tables()
            return "OK:\n" + "\n".join(tables) if tables else "OK: No tables"
        except Exception as e:
            return f"ERROR: {e}"


class ShowDatabasesCommand(Command):
    def execute(self, params, client_state):
        try:
            dbs = self.db.list_databases()
            return "OK:\n" + "\n".join(dbs) if dbs else "OK: No databases"
        except Exception as e:
            return f"ERROR: {e}"


class ShowUsersCommand(Command):
    def execute(self, params, client_state):
        if not client_state.get('is_admin'):
            return "ERROR: Admin only"
        try:
            users = self.db.list_users()
            return "OK:\n" + "\n".join(users) if users else "OK: No users"
        except Exception as e:
            return f"ERROR: {e}"


class HelpCommand(Command):
    def execute(self, params, client_state):
        help_text = """
Available Commands:
------------------
Database Operations:
  CREATE DATABASE <name>     - Create new database
  DROP DATABASE <name>       - Drop database
  USE <database>             - Select database
  SHOW DATABASES             - List databases

Table Operations:
  CREATE TABLE <name> [(cols)] - Create table
  DROP TABLE <name>          - Drop table
  SHOW TABLES                - List tables

Data Operations:
  INSERT INTO <table> VALUES (val1, val2, ...)
  SELECT * FROM <table> [WHERE ...] [ORDER BY ...]
  UPDATE <table> SET col=val [WHERE ...]
  DELETE FROM <table> [WHERE ...]

Batch Operations:
  BEGIN BATCH [ERROR MODE <mode>]
    <command1>
    <command2>
    ...
  COMMIT

Other:
  HELP                       - Show this help
  QUIT                       - Exit
"""
        return help_text



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
            
            if self.db._binlog:
                self.db._binlog.write_entry(
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


class CommandRegistry:
    """Registry of all available commands."""
    
    def __init__(self, db: Database, replication_client=None):
        self.db = db
        self.replication_client = replication_client
        self.commands = self._register_commands()
    
    def _register_commands(self) -> Dict[str, Command]:
        return {
            'CREATE_DB': CreateDatabaseCommand(self.db, self.replication_client),
            'DROP_DB': DropDatabaseCommand(self.db, self.replication_client),
            'USE': UseDatabaseCommand(self.db, self.replication_client),
            'CREATE': CreateTableCommand(self.db, self.replication_client),
            'DROP': DropTableCommand(self.db, self.replication_client),
            'INSERT': InsertCommand(self.db, self.replication_client),
            'SELECT': SelectCommand(self.db, self.replication_client),
            'UPDATE': UpdateCommand(self.db, self.replication_client),
            'UPSERT': UpsertCommand(self.db, self.replication_client),
            'BATCH_UPDATE': BatchUpdateCommand(self.db, self.replication_client),
            'DELETE': DeleteCommand(self.db, self.replication_client),
            'SHOW_TABLES': ShowTablesCommand(self.db, self.replication_client),
            'SHOW_DATABASES': ShowDatabasesCommand(self.db, self.replication_client),
            'SHOW_USERS': ShowUsersCommand(self.db, self.replication_client),
            'BATCH_STATUS': BatchStatusCommand(self.db, self.replication_client),
            'HELP': HelpCommand(self.db, self.replication_client),
        }
    
    def get(self, command_type: str) -> Optional[Command]:
        return self.commands.get(command_type)
    
    def execute(self, command_type: str, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        command = self.get(command_type)
        if not command:
            return f"ERROR: Unknown command '{command_type}'"
        return command.execute(params, client_state)
