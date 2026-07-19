
"""
SQL-like Command Parser for LevelDB Socket Server
"""

import re
from typing import Dict, Any, Optional, Tuple, List


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
                r'^\s*INSERT\s+INTO\s+(?P<table>\w+)(?:\s*\((?P<columns>[^)]+)\))?\s+VALUES\s*\((?P<values>[^)]+)\)\s*$',
                re.IGNORECASE
            ),
            'SELECT': re.compile(
                r'^\s*SELECT\s+(?P<columns>[\w\s*,]+)\s+FROM\s+(?P<table>\w+)'
                r'(?:\s+WHERE\s+(?P<where>.+?))?'
                r'(?:\s+ORDER\s+BY\s+(?P<order_by>\w+)(?:\s+(?P<order_dir>ASC|DESC))?)?\s*$',
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
            'SHOW_DATABASES': re.compile(
                r'^\s*SHOW\s+DATABASES\s*$',
                re.IGNORECASE
            ),
            'SHOW_USERS': re.compile(
                r'^\s*SHOW\s+USERS\s*$',
                re.IGNORECASE
            ),
            'SHOW_MASTER_STATUS': re.compile(
                r'^\s*SHOW\s+MASTER\s+STATUS\s*$',
                re.IGNORECASE
            ),
            'SHOW_SLAVE_STATUS': re.compile(
                r'^\s*SHOW\s+SLAVE\s+STATUS\s*$',
                re.IGNORECASE
            ),
            'START_SLAVE': re.compile(
                r'^\s*START\s+SLAVE\s*$',
                re.IGNORECASE
            ),
            'STOP_SLAVE': re.compile(
                r'^\s*STOP\s+SLAVE\s*$',
                re.IGNORECASE
            ),
            'RESET_SLAVE': re.compile(
                r'^\s*RESET\s+SLAVE\s*$',
                re.IGNORECASE
            ),
            'CREATE_REPL_USER': re.compile(
                r'^\s*CREATE\s+REPLICATION\s+USER\s+["\']?(?P<username>\w+)["\']?\s+IDENTIFIED\s+BY\s+["\']?(?P<password>[^"\s]+)["\']?\s*$',
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
            'BACKUP': re.compile(
                r'^\s*BACKUP\s+(?:TABLE\s+(?P<table>\w+)|DATABASE\s+(?P<database>\w+))?\s+TO\s+["\']?(?P<file>[^"\']+)["\']?\s*$',
                re.IGNORECASE
            ),
            'RESTORE': re.compile(
                r'^\s*RESTORE\s+FROM\s+["\']?(?P<file>[^"\']+)["\']?(?:\s+TO\s+(?P<target>\w+))?\s*$',
                re.IGNORECASE
            ),
            'VERIFY_BACKUP': re.compile(
                r'^\s*VERIFY\s+BACKUP\s+["\']?(?P<file>[^"\']+)["\']?\s*$',
                re.IGNORECASE
            ),
            'SHOW_BACKUPS': re.compile(
                r'^\s*SHOW\s+BACKUPS(?:\s+(?P<path>\S+))?\s*$',
                re.IGNORECASE
            ),
            'BEGIN': re.compile(
                r'^\s*BEGIN(?:\s+TRANSACTION)?\s*$',
                re.IGNORECASE
            ),
            'COMMIT': re.compile(
                r'^\s*COMMIT(?:\s+TRANSACTION)?\s*$',
                re.IGNORECASE
            ),
            'ROLLBACK': re.compile(
                r'^\s*ROLLBACK(?:\s+TRANSACTION)?\s*$',
                re.IGNORECASE
            ),
            'METRICS': re.compile(
                r'^\s*METRICS\s*$',
                re.IGNORECASE
            ),
            'HEALTH': re.compile(
                r'^\s*HEALTH\s*$',
                re.IGNORECASE
            ),
            'PROMETHEUS': re.compile(
                r'^\s*PROMETHEUS\s*$',
                re.IGNORECASE
            ),
            'BATCH_STATUS': re.compile(
                r'^\s*BATCH\s+STATUS(?:\s+(?P<batch_id>[\w-]+))?\s*$',
                re.IGNORECASE
            ),
        }
    
    def parse(self, command: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Parse a command string into (command_type, parameters)"""
        command = command.strip()
        
        # Check for simple commands first
        cmd_upper = command.upper()
        
        if cmd_upper == 'HELP':
            return 'HELP', {}
        if cmd_upper in ('QUIT', 'EXIT'):
            return 'QUIT', {}
        if cmd_upper == 'SHOW TABLES':
            return 'SHOW_TABLES', {}
        if cmd_upper == 'SHOW DATABASES':
            return 'SHOW_DATABASES', {}
        if cmd_upper == 'SHOW USERS':
            return 'SHOW_USERS', {}
        if cmd_upper == 'SHOW MASTER STATUS':
            return 'SHOW_MASTER_STATUS', {}
        if cmd_upper == 'SHOW SLAVE STATUS':
            return 'SHOW_SLAVE_STATUS', {}
        if cmd_upper == 'START SLAVE':
            return 'START_SLAVE', {}
        if cmd_upper == 'STOP SLAVE':
            return 'STOP_SLAVE', {}
        if cmd_upper == 'RESET SLAVE':
            return 'RESET_SLAVE', {}
        if cmd_upper == 'BEGIN' or cmd_upper == 'BEGIN TRANSACTION':
            return 'BEGIN', {}
        if cmd_upper == 'COMMIT' or cmd_upper == 'COMMIT TRANSACTION':
            return 'COMMIT', {}
        if cmd_upper == 'ROLLBACK' or cmd_upper == 'ROLLBACK TRANSACTION':
            return 'ROLLBACK', {}
        if cmd_upper == 'METRICS':
            return 'METRICS', {}
        if cmd_upper == 'HEALTH':
            return 'HEALTH', {}
        if cmd_upper == 'PROMETHEUS':
            return 'PROMETHEUS', {}
        
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
                
                # Parse ORDER BY
                if 'order_by' in params:
                    params['order_desc'] = (params.get('order_dir') or 'ASC').upper() == 'DESC'
                
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
                
                # Try to convert value
                try:
                    if '.' in val:
                        val = float(val)
                    else:
                        val = int(val)
                except ValueError:
                    # Keep as string, remove quotes if present
                    if (val.startswith("'") and val.endswith("'")) or \
                       (val.startswith('"') and val.endswith('"')):
                        val = val[1:-1]
                
                result[col] = val
        
        return result
    
    def _parse_where_clause(self, where_str: str) -> Dict[str, Any]:
        """Parse WHERE clause into conditions"""
        conditions = {}
        parts = [p.strip() for p in where_str.split('AND')]
        
        for part in parts:
            if '=' in part:
                col, val = part.split('=', 1)
                col = col.strip()
                val = val.strip()
                
                # Try to convert value
                try:
                    if '.' in val:
                        val = float(val)
                    else:
                        val = int(val)
                except ValueError:
                    # Keep as string, remove quotes if present
                    if (val.startswith("'") and val.endswith("'")) or \
                       (val.startswith('"') and val.endswith('"')):
                        val = val[1:-1]
                
                conditions[col] = val
        
        return conditions


class BackupRestoreParser(CommandParser):
    """Extended parser with backup/restore/transaction/batch commands."""
    
    def __init__(self):
        super().__init__()
        # Additional patterns are already included in base parser
