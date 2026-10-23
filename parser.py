"""
SQL-like Command Parser for LevelDB Socket Server
"""

import re
import json
from typing import Dict, Any, Optional, Tuple, List


class CommandParser:
    """Parse SQL-like commands for LevelDB operations"""
    
    # Identifier that may be backtick-quoted, e.g. `name` or name
    _IDENT = r"`?\w+`?"
    # Optional database prefix: db.table or `db`.`table`
    _TABLE_REF = rf"(?:{_IDENT}\.)?{_IDENT}"
    
    def __init__(self):
        table_ref = self._TABLE_REF
        ident = self._IDENT
        self.patterns = {
            'CREATE': re.compile(
                rf'^\s*CREATE\s+TABLE\s+(?P<table>{table_ref})(?:\s*\((?P<columns>[^)]+)\))?\s*$',
                re.IGNORECASE
            ),
            'ALTER_TABLE': re.compile(
                rf'^\s*ALTER\s+TABLE\s+(?P<table>{table_ref})\s+MODIFY\s+COLUMN\s+(?P<column>{ident})\s+(?P<type>\w+)\s*(?P<attr>.*)$',
                re.IGNORECASE
            ),
            'DROP': re.compile(
                rf'^\s*DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?P<table>{table_ref})\s*$',
                re.IGNORECASE
            ),

            'INSERT': re.compile(
                rf'^\s*INSERT\s+INTO\s+(?P<table>{table_ref})(?:\s*\((?P<columns>[^)]+)\))?\s+VALUES\s*\((?P<values>[^)]+)\)\s*$',
                re.IGNORECASE
            ),
            'UPSERT': re.compile(
                rf'^\s*UPSERT\s+INTO\s+(?P<table>{table_ref})(?:\s*\((?P<columns>[^)]+)\))?\s+VALUES\s*\((?P<values>[^)]+)\)\s*$',
                re.IGNORECASE
            ),
            'SELECT': re.compile(
                rf'^\s*SELECT\s+(?P<columns>[\w\s*,]+)\s+FROM\s+(?P<table>{table_ref})'
                rf'(?:\s+WHERE\s+(?P<where>.+?))?'
                rf'(?:\s+ORDER\s+BY\s+(?P<order_by>\w+)(?:\s+(?P<order_dir>ASC|DESC))?)?\s*$',
                re.IGNORECASE
            ),
            'UPDATE': re.compile(
                rf'^\s*UPDATE\s+(?P<table>{table_ref})\s+SET\s+(?P<set>.+?)(?:\s+WHERE\s+(?P<where>.+))?\s*$',
                re.IGNORECASE
            ),
            'SET': re.compile(
                r'^\s*SET\s+(?P<option>\w+)\s+(?P<value>\w+)\s*$',
                re.IGNORECASE
            ),
            'BATCH_UPDATE': re.compile(
                rf'^\s*BATCH\s+UPDATE\s+(?P<table>{table_ref})\s+SET\s+(?P<set>.+?)\s+WHERE\s+(?P<where_col>\w+)\s+IN\s*\((?P<where_values>[^)]+)\)\s*$',
                re.IGNORECASE
            ),
            'DELETE': re.compile(
                rf'^\s*DELETE\s+FROM\s+(?P<table>{table_ref})(?:\s+WHERE\s+(?P<where>.+))?\s*$',
                re.IGNORECASE
            ),
            'USE': re.compile(
                rf'^\s*USE\s+(?P<database>{ident})\s*$',
                re.IGNORECASE
            ),
            'CREATE_DB': re.compile(
                rf'^\s*CREATE\s+DATABASE\s+(?P<database>{ident})\s*$',
                re.IGNORECASE
            ),
            'DROP_DB': re.compile(
                rf'^\s*DROP\s+DATABASE\s+(?P<database>{ident})\s*$',
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
                rf'^\s*BACKUP\s+(?:TABLE\s+(?P<table>{table_ref})|DATABASE\s+(?P<database>{ident}))?\s+TO\s+["\']?(?P<file>[^"\']+)["\']?\s*$',
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
            'DESCRIBE': re.compile(
                rf'^\s*(?:DESCRIBE|DESC|SHOW\s+CREATE\s+TABLE)\s+(?P<table>{table_ref})\s*$',
                re.IGNORECASE
            ),
            'SET_TABLE': re.compile(
                rf'^\s*SET\s+TABLE\s+(?P<table>{table_ref})\s+next_id\s+(?P<next_id>\d+)\s*$',
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
                
                # Strip backticks from identifiers and split db.table references
                self._normalize_identifiers(params)
                
                # Parse columns if present
                if 'columns' in params and params['columns']:
                    params['columns'] = [self._strip_backticks(c.strip()) for c in params['columns'].split(',')]
                
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

    @staticmethod
    def _strip_backticks(value: Optional[str]) -> Optional[str]:
        if not value:
            return value
        return value.strip('`')
    
    def _normalize_identifiers(self, params: Dict[str, Any]):
        """Strip backticks and split db.table references."""
        # Database names
        for key in ('database', 'target', 'path'):
            if key in params and params[key]:
                params[key] = self._strip_backticks(params[key])
        
        # Table references may include an optional database prefix.
        # Strip backticks from each part separately to handle `db`.`table`.
        if 'table' in params and params['table']:
            table_ref = params['table']
            if '.' in table_ref:
                db_name, table_name = table_ref.split('.', 1)
                params['database'] = self._strip_backticks(db_name)
                params['table'] = self._strip_backticks(table_name)
            else:
                params['table'] = self._strip_backticks(table_ref)
        
        # Column names
        for key in ('column', 'where_col', 'order_by', 'username', 'password'):
            if key in params and params[key]:
                params[key] = self._strip_backticks(params[key])
        
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
        """Parse SET clause into dict of column=value pairs, respecting quoted JSON."""
        result = {}
        current_col = None
        current_val = ''
        in_string = False
        string_char = None
        depth = 0
        state = 'col'
        
        for char in set_str:
            if state == 'col':
                if char == '=':
                    current_col = current_val.strip().strip('`')
                    current_val = ''
                    state = 'val'
                else:
                    current_val += char
            else:
                if char in ("'", '"') and not in_string:
                    in_string = True
                    string_char = char
                    current_val += char
                elif char == string_char and in_string:
                    in_string = False
                    string_char = None
                    current_val += char
                elif char in ('[', '{') and not in_string:
                    depth += 1
                    current_val += char
                elif char in (']', '}') and not in_string:
                    depth -= 1
                    current_val += char
                elif char == ',' and not in_string and depth == 0:
                    if current_col is not None:
                        result[current_col] = self._clean_value(current_val.strip())
                    current_col = None
                    current_val = ''
                    state = 'col'
                else:
                    current_val += char
        
        if current_col is not None:
            result[current_col] = self._clean_value(current_val.strip())
        
        return result
    
    def _clean_value(self, val: str) -> Any:
        """Clean and convert a value string."""
        val = val.strip()
        if (val.startswith("'") and val.endswith("'")) or \
           (val.startswith('"') and val.endswith('"')):
            val = val[1:-1]
        try:
            if '.' in val:
                return float(val)
            else:
                return int(val)
        except ValueError:
            pass
        try:
            if val.startswith('[') or val.startswith('{'):
                return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            pass
        return val
    
    def _parse_where_clause(self, where_str: str) -> Dict[str, Any]:
        """Parse WHERE clause into conditions"""
        conditions = {}
        parts = [p.strip() for p in where_str.split('AND')]
        
        for part in parts:
            if '=' in part:
                col, val = part.split('=', 1)
                col = col.strip().strip('`')
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
