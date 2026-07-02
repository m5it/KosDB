"""
SQL-like Command Parser for LevelDB Socket Server
Parses MySQL-like commands into structured operations
"""

import re
from typing import Dict, Any, Optional, Tuple


class CommandParser:
    """Parse SQL-like commands for LevelDB operations"""
    
    def __init__(self):
        self.patterns = {
            'CREATE': re.compile(
                r'^\s*CREATE\s+TABLE\s+(?P<table>\w+)(?:\s*\((?P<columns>[^)]+)\))?\s*$',
                re.IGNORECASE
            ),
            'DROP': re.compile(
                r'^\s*DROP\s+TABLE\s+(?P<table>\w+)\s*$',
                re.IGNORECASE
            ),
            'INSERT': re.compile(
                r'^\s*INSERT\s+INTO\s+(?P<table>\w+)\s+VALUES\s*\((?P<values>[^)]+)\)\s*$',
                re.IGNORECASE
            ),
            'SELECT': re.compile(
                r'^\s*SELECT\s+(?P<columns>[\w\s*,]+)\s+FROM\s+(?P<table>\w+)(?:\s+WHERE\s+(?P<where>.+))?\s*$',
                re.IGNORECASE
            ),
            'UPDATE': re.compile(
                r'^\s*UPDATE\s+(?P<table>\w+)\s+SET\s+(?P<set>.+?)(?:\s+WHERE\s+(?P<where>.+))?\s*$',
                re.IGNORECASE
            ),
            'DELETE': re.compile(
                r'^\s*DELETE\s+FROM\s+(?P<table>\w+)(?:\s+WHERE\s+(?P<where>.+))?\s*$',
                re.IGNORECASE
            ),
            'USE': re.compile(
                r'^\s*USE\s+(?P<database>\w+)\s*$',
                re.IGNORECASE
            ),
            'CREATE_DB': re.compile(
                r'^\s*CREATE\s+DATABASE\s+(?P<database>\w+)\s*$',
                re.IGNORECASE
            ),
            'DROP_DB': re.compile(
                r'^\s*DROP\s+DATABASE\s+(?P<database>\w+)\s*$',
                re.IGNORECASE
            ),
            'SHOW_TABLES': re.compile(
                r'^\s*SHOW\s+TABLES\s*$',
                re.IGNORECASE
            ),
            'HELP': re.compile(
                r'^\s*HELP\s*$',
                re.IGNORECASE
            ),
            'QUIT': re.compile(
                r'^\s*(?:QUIT|EXIT)\s*$',
                re.IGNORECASE
            ),
        }
    
    def parse(self, command: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Parse a command string into (command_type, parameters)
        
        Returns:
            Tuple of (command_type, params_dict) or ('UNKNOWN', None) if not recognized
        """
        command = command.strip()
        
        # Check for special commands first
        if command.upper() == 'HELP':
            return 'HELP', {}
        if command.upper() in ('QUIT', 'EXIT'):
            return 'QUIT', {}
        if command.upper() == 'SHOW TABLES':
            return 'SHOW_TABLES', {}
        
        # Try to match patterns
        for cmd_type, pattern in self.patterns.items():
            match = pattern.match(command)
            if match:
                params = match.groupdict()
                
                # Parse columns if present
                if 'columns' in params and params['columns']:
                    params['columns'] = [c.strip() for c in params['columns'].split(',')]
                
                # Parse values if present
                if 'values' in params and params['values']:
                    params['values'] = self._parse_values(params['values'])
                
                # Parse SET clause for UPDATE
                if 'set' in params and params['set']:
                    params['set'] = self._parse_set_clause(params['set'])
                
                # Parse WHERE clause
                if 'where' in params and params['where']:
                    params['where'] = self._parse_where_clause(params['where'])
                
                return cmd_type, params
        
        return 'UNKNOWN', None
    
    def _parse_values(self, values_str: str) -> list:
        """Parse VALUES clause into list of values"""
        values = []
        current = ''
        in_string = False
        string_char = None
        
        for char in values_str:
            if char in ("'", '"') and not in_string:
                in_string = True
                string_char = char
                continue
            elif char == string_char and in_string:
                in_string = False
                string_char = None
                values.append(current.strip())
                current = ''
                continue
            
            if char == ',' and not in_string:
                if current.strip():
                    values.append(current.strip())
                current = ''
            else:
                current += char
        
        if current.strip():
            values.append(current.strip())
        
        # Convert numeric strings to numbers
        result = []
        for v in values:
            v = v.strip()
            try:
                if '.' in v:
                    result.append(float(v))
                else:
                    result.append(int(v))
            except ValueError:
                result.append(v)
        
        return result
    
    def _parse_set_clause(self, set_str: str) -> Dict[str, Any]:
        """Parse SET clause into dict of column=value pairs"""
        result = {}
        assignments = [a.strip() for a in set_str.split(',')]
        
        for assignment in assignments:
            if '=' in assignment:
                col, val = assignment.split('=', 1)
                col = col.strip()
                val = val.strip()
                
                # Try to convert to number
                try:
                    if '.' in val:
                        result[col] = float(val)
                    else:
                        result[col] = int(val)
                except ValueError:
                    # Remove quotes if present
                    if (val.startswith("'") and val.endswith("'")) or \
                       (val.startswith('"') and val.endswith('"')):
                        val = val[1:-1]
                    result[col] = val
        
        return result
    
    def _parse_where_clause(self, where_str: str) -> Dict[str, Any]:
        """Parse WHERE clause into conditions"""
        conditions = {}
        
        # Simple parsing for key=value conditions
        parts = [p.strip() for p in where_str.split('AND')]
        
        for part in parts:
            if '=' in part:
                col, val = part.split('=', 1)
                col = col.strip()
                val = val.strip()
                
                # Try to convert to number
                try:
                    if '.' in val:
                        conditions[col] = float(val)
                    else:
                        conditions[col] = int(val)
                except ValueError:
                    # Remove quotes if present
                    if (val.startswith("'") and val.endswith("'")) or \
                       (val.startswith('"') and val.endswith('"')):
                        val = val[1:-1]
                    conditions[col] = val
        
        return conditions


if __name__ == '__main__':
    # Test the parser
    parser = CommandParser()
    
    test_commands = [
        "CREATE TABLE users (id INT, name TEXT)",
        "INSERT INTO users VALUES (1, 'Alice')",
        "SELECT * FROM users",
        "SELECT name, age FROM users WHERE id=1",
        "UPDATE users SET name='Bob' WHERE id=1",
        "DELETE FROM users WHERE id=1",
        "DROP TABLE users",
        "CREATE DATABASE testdb",
        "USE testdb",
        "DROP DATABASE testdb",
        "SHOW TABLES",
        "HELP",
        "QUIT",
    ]
    
    for cmd in test_commands:
        cmd_type, params = parser.parse(cmd)
        print(f"Command: {cmd}")
        print(f"  Type: {cmd_type}")
        print(f"  Params: {params}")
        print()