"""
Command Execution Framework for LevelDB Socket Server
"""

from typing import Dict, Any, Optional, List
from database import Database


class Command:
    def __init__(self, db: Database):
        self.db = db
    
    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        raise NotImplementedError
    
    def validate_params(self, params: Dict[str, Any], required: List[str]) -> bool:
        for param in required:
            if param not in params or params[param] is None:
                return False
        return True


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
            count = self.db.update(params['table'], params['set'], params.get('where'))
            return f"OK: Updated {count} row(s)"
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
        is_admin = client_state.get('is_admin', False)
        help_text = """Available commands:
  SHOW DATABASES           - List databases
  CREATE DATABASE <name>   - Create database
  DROP DATABASE <name>     - Delete database
  USE <database>           - Select database
  SHOW TABLES              - List tables
  
  CREATE TABLE <name> (col [PRIMARY KEY], col [INDEX], ...)
                           - Create table with indexes
  DROP TABLE <name>        - Delete table
  
  INSERT INTO <t> VALUES (v...)  - Insert row
  SELECT * FROM <t>              - Select all
  SELECT * FROM <t> ORDER BY c [ASC|DESC]
                           - Select sorted
  SELECT c FROM <t> WHERE cond ORDER BY c
                           - Select filtered
  UPDATE <t> SET c=v WHERE...    - Update
  DELETE FROM <t> WHERE cond     - Delete
  
  HELP                     - This help
  QUIT                     - Disconnect
"""
        if is_admin:
            help_text += """
Admin:
  SHOW USERS               - List users
"""
        return help_text


class QuitCommand(Command):
    def execute(self, params, client_state):
        return "BYE"


class CommandRegistry:
    def __init__(self, db: Database):
        self.db = db
        self.commands = {
            'CREATE_DB': CreateDatabaseCommand(db),
            'DROP_DB': DropDatabaseCommand(db),
            'USE': UseDatabaseCommand(db),
            'CREATE': CreateTableCommand(db),
            'DROP': DropTableCommand(db),
            'INSERT': InsertCommand(db),
            'SELECT': SelectCommand(db),
            'UPDATE': UpdateCommand(db),
            'DELETE': DeleteCommand(db),
            'SHOW_TABLES': ShowTablesCommand(db),
            'SHOW_DATABASES': ShowDatabasesCommand(db),
            'SHOW_USERS': ShowUsersCommand(db),
            'HELP': HelpCommand(db),
            'QUIT': QuitCommand(db),
        }
    
    def execute(self, cmd_type: str, params: Dict, client_state: Dict) -> str:
        if cmd_type == 'UNKNOWN':
            return "ERROR: Unknown command"
        if cmd_type not in self.commands:
            return f"ERROR: {cmd_type} not implemented"
        return self.commands[cmd_type].execute(params, client_state)