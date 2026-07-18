
"""
Command Execution Framework for LevelDB Socket Server
KosDB v2.3.0 - Batch Execution Support
"""

import re
from typing import Dict, Any, Optional, List
from database import Database
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
            self.db.insert(params['table'], params['values'])
            return f"OK: Inserted into '{params['table']}'"
        except Exception as e:
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
