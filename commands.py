"""
Command Execution Framework for LevelDB Socket Server
Provides command classes and registry for executing SQL-like commands
"""

from typing import Dict, Any, Optional, List
from database import Database


class Command:
    """Base command class"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        """Execute the command with given parameters"""
        raise NotImplementedError("Subclasses must implement execute()")
    
    def validate_params(self, params: Dict[str, Any], required: List[str]) -> bool:
        """Validate that required parameters are present"""
        for param in required:
            if param not in params or params[param] is None:
                return False
        return True


class CreateDatabaseCommand(Command):
    """CREATE DATABASE command"""
    
    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        if not self.validate_params(params, ['database']):
            return "ERROR: Database name required"
        
        db_name = params['database']
        try:
            self.db.create_database(db_name)
            return f"OK: Database '{db_name}' created"
        except Exception as e:
            return f"ERROR: {str(e)}"


class DropDatabaseCommand(Command):
    """DROP DATABASE command"""
    
    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        if not self.validate_params(params, ['database']):
            return "ERROR: Database name required"
        
        db_name = params['database']
        try:
            self.db.drop_database(db_name)
            # Clear current database if it was dropped
            if client_state.get('current_db') == db_name:
                client_state['current_db'] = None
            return f"OK: Database '{db_name}' dropped"
        except Exception as e:
            return f"ERROR: {str(e)}"


class UseDatabaseCommand(Command):
    """USE DATABASE command"""
    
    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        if not self.validate_params(params, ['database']):
            return "ERROR: Database name required"
        
        db_name = params['database']
        try:
            self.db.use_database(db_name)
            client_state['current_db'] = db_name
            return f"OK: Using database '{db_name}'"
        except Exception as e:
            return f"ERROR: {str(e)}"


class CreateTableCommand(Command):
    """CREATE TABLE command"""
    
    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        if not self.validate_params(params, ['table']):
            return "ERROR: Table name required"
        
        if not client_state.get('current_db'):
            return "ERROR: No database selected. Use USE <database> first"
        
        table_name = params['table']
        columns = params.get('columns', [])
        
        try:
            self.db.create_table(table_name, columns)
            return f"OK: Table '{table_name}' created"
        except Exception as e:
            return f"ERROR: {str(e)}"


class DropTableCommand(Command):
    """DROP TABLE command"""
    
    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        if not self.validate_params(params, ['table']):
            return "ERROR: Table name required"
        
        if not client_state.get('current_db'):
            return "ERROR: No database selected"
        
        table_name = params['table']
        try:
            self.db.drop_table(table_name)
            return f"OK: Table '{table_name}' dropped"
        except Exception as e:
            return f"ERROR: {str(e)}"


class InsertCommand(Command):
    """INSERT INTO command"""
    
    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        if not self.validate_params(params, ['table', 'values']):
            return "ERROR: Table name and values required"
        
        if not client_state.get('current_db'):
            return "ERROR: No database selected"
        
        table_name = params['table']
        values = params.get('values', [])
        
        try:
            self.db.insert(table_name, values)
            return f"OK: Inserted into '{table_name}'"
        except Exception as e:
            return f"ERROR: {str(e)}"


class SelectCommand(Command):
    """SELECT command"""
    
    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        if not self.validate_params(params, ['table']):
            return "ERROR: Table name required"
        
        if not client_state.get('current_db'):
            return "ERROR: No database selected"
        
        table_name = params['table']
        columns = params.get('columns', ['*'])
        where = params.get('where')
        
        try:
            results = self.db.select(table_name, columns, where)
            
            if not results:
                return "OK: No records found"
            
            # Format results
            lines = []
            for record in results:
                lines.append(str(record))
            
            return "OK:\n" + "\n".join(lines)
        except Exception as e:
            return f"ERROR: {str(e)}"


class UpdateCommand(Command):
    """UPDATE command"""
    
    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        if not self.validate_params(params, ['table', 'set']):
            return "ERROR: Table name and SET clause required"
        
        if not client_state.get('current_db'):
            return "ERROR: No database selected"
        
        table_name = params['table']
        set_values = params.get('set', {})
        where = params.get('where')
        
        try:
            count = self.db.update(table_name, set_values, where)
            return f"OK: Updated {count} record(s) in '{table_name}'"
        except Exception as e:
            return f"ERROR: {str(e)}"


class DeleteCommand(Command):
    """DELETE command"""
    
    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        if not self.validate_params(params, ['table']):
            return "ERROR: Table name required"
        
        if not client_state.get('current_db'):
            return "ERROR: No database selected"
        
        table_name = params['table']
        where = params.get('where')
        
        try:
            count = self.db.delete(table_name, where)
            return f"OK: Deleted {count} record(s) from '{table_name}'"
        except Exception as e:
            return f"ERROR: {str(e)}"


class ShowTablesCommand(Command):
    """SHOW TABLES command"""
    
    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        if not client_state.get('current_db'):
            return "ERROR: No database selected"
        
        try:
            tables = self.db.list_tables()
            if not tables:
                return "OK: No tables found"
            return "OK:\n" + "\n".join(tables)
        except Exception as e:
            return f"ERROR: {str(e)}"


class HelpCommand(Command):
    """HELP command"""
    
    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        help_text = """Available commands:
  CREATE DATABASE <name>              - Create a new database
  DROP DATABASE <name>                - Delete a database
  USE <database>                      - Select database to use
  CREATE TABLE <name> (cols...)       - Create a new table
  DROP TABLE <name>                   - Delete a table
  INSERT INTO <table> VALUES (val...) - Insert a record
  SELECT * FROM <table>               - Select all records
  SELECT col FROM <table> WHERE cond  - Select specific records
  UPDATE <table> SET col=val WHERE... - Update records
  DELETE FROM <table> WHERE cond      - Delete records
  SHOW TABLES                         - List tables
  HELP                                - Show this help
  QUIT / EXIT                         - Disconnect

Authentication:
  USER <username>                     - Send username
  PASS <password>                     - Send password
"""
        return help_text


class QuitCommand(Command):
    """QUIT command"""
    
    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        return "BYE"


class CommandRegistry:
    """Registry for command handlers"""
    
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
            'HELP': HelpCommand(db),
            'QUIT': QuitCommand(db),
        }
    
    def execute(self, command_type: str, params: Dict[str, Any], 
                client_state: Dict[str, Any]) -> str:
        """Execute a command by type with given parameters"""
        if command_type == 'UNKNOWN':
            return "ERROR: Unknown command. Type HELP for available commands."
        
        if command_type not in self.commands:
            return f"ERROR: Command '{command_type}' not implemented"
        
        return self.commands[command_type].execute(params, client_state)


if __name__ == '__main__':
    # Test commands
    db = Database('./test.db')
    registry = CommandRegistry(db)
    state = {'current_db': None}
    
    print("Command registry initialized")
    print(f"Available commands: {list(registry.commands.keys())}")