"""
SQL-like Command Parser for LevelDB Socket Server

Supports parsing of various SQL-like commands for database operations.
"""

import re
from typing import Dict, Any, Tuple, Optional, List


class CommandParser:
    """Parser for SQL-like commands."""
    
    def __init__(self):
        # Initialize command patterns
        self.patterns = {
            'CREATE_DB': re.compile(
                r'^\s*CREATE\s+DATABASE\s+(?P<db_name>\w+)\s*$',
                re.IGNORECASE
            ),
            'DROP_DB': re.compile(
                r'^\s*DROP\s+DATABASE\s+(?P<db_name>\w+)\s*$',
                re.IGNORECASE
            ),
            'USE': re.compile(
                r'^\s*USE\s+(?P<db_name>\w+)\s*$',
                re.IGNORECASE
            ),
            'CREATE': re.compile(
                r'^\s*CREATE\s+TABLE\s+(?P<table>\w+)\s*\((?P<columns>[^)]+)\)\s*$',
                re.IGNORECASE
            ),
            'DROP': re.compile(
                r'^\s*DROP\s+TABLE\s+(?P<table>\w+)\s*$',
                re.IGNORECASE
            ),
            'ALTER': re.compile(
                r'^\s*ALTER\s+TABLE\s+(?P<table>\w+)\s+(?P<alter_spec>.+)$',
                re.IGNORECASE
            ),
            'INSERT': re.compile(
                r'^\s*INSERT\s+INTO\s+(?P<table>\w+)\s+VALUES\s*\((?P<values>[^)]+)\)\s*$',
                re.IGNORECASE
            ),
            'SELECT': re.compile(
                r'^\s*SELECT\s+(?P<columns>[\w\s,]+)\s+FROM\s+(?P<table>\w+)(?:\s+WHERE\s+(?P<where>.+))?\s*$',
                re.IGNORECASE
            ),
            'UPDATE': re.compile(
                r'^\s*UPDATE\s+(?P<table>\w+)\s+SET\s+(?P<set>[\w\s=,]+)(?:\s+WHERE\s+(?P<where>.+))?\s*$',
                re.IGNORECASE
            ),
            'DELETE': re.compile(
                r'^\s*DELETE\s+FROM\s+(?P<table>\w+)(?:\s+WHERE\s+(?P<where>.+))?\s*$',
                re.IGNORECASE
            ),
            'SHOW': re.compile(
                r'^\s*SHOW\s+(?P<target>DATABASES|TABLES|USERS)\s*$',
                re.IGNORECASE
            ),
            'DESCRIBE': re.compile(
                r'^\s*DESCRIBE\s+(?P<table>\w+)\s*$',
                re.IGNORECASE
            ),
            'CREATE_USER': re.compile(
                r'^\s*CREATE\s+USER\s+(?P<username>\w+)\s+PASSWORD\s+(?P<password>\S+)\s*$',
                re.IGNORECASE
            ),
            'DROP_USER': re.compile(
                r'^\s*DROP\s+USER\s+(?P<username>\w+)\s*$',
                re.IGNORECASE
            ),
            'GRANT': re.compile(
                r'^\s*GRANT\s+(?P<privileges>[\w\s,]+)\s+ON\s+(?P<db>\w+)\.(?P<table>\w+)\s+TO\s+(?P<username>\w+)\s*$',
                re.IGNORECASE
            ),
            'REVOKE': re.compile(
                r'^\s*REVOKE\s+(?P<privileges>[\w\s,]+)\s+ON\s+(?P<db>\w+)\.(?P<table>\w+)\s+FROM\s+(?P<username>\w+)\s*$',
                re.IGNORECASE
            ),
            'CREATE_ROLE': re.compile(
                r'^\s*CREATE\s+ROLE\s+(?P<role_name>\w+)(?:\s+DESCRIPTION\s+(?P<description>\'[^\']*\'|\"[^\"]*\"))?\s*$',
                re.IGNORECASE
            ),
            'DROP_ROLE': re.compile(
                r'^\s*DROP\s+ROLE\s+(?P<role_name>\w+)\s*$',
                re.IGNORECASE
            ),
            'GRANT_ROLE': re.compile(
                r'^\s*GRANT\s+ROLE\s+(?P<role_name>\w+)\s+TO\s+(?P<username>\w+)\s*$',
                re.IGNORECASE
            ),
            'REVOKE_ROLE': re.compile(
                r'^\s*REVOKE\s+ROLE\s+(?P<role_name>\w+)\s+FROM\s+(?P<username>\w+)\s*$',
                re.IGNORECASE
            ),
            'SHOW_GRANTS': re.compile(
                r'^\s*SHOW\s+GRANTS(?:\s+FOR\s+(?P<username>\w+))?\s*$',
                re.IGNORECASE
            ),
            'SHOW_ROLES': re.compile(
                r'^\s*SHOW\s+ROLES\s*$',
                re.IGNORECASE
            ),
            'AUDIT_LOG': re.compile(
                r'^\s*AUDIT\s+LOG(?:\s+LIMIT\s+(?P<limit>\d+))?(?:\s+USER\s+(?P<user>\w+))?(?:\s+ACTION\s+(?P<action>\w+))?\s*$',
                re.IGNORECASE
            ),
        }
    
    def parse(self, sql: str) -> Tuple[str, Dict[str, Any]]:
        """
        Parse SQL-like command and return command type and parameters.
        
        Args:
            sql: SQL command string
        
        Returns:
            Tuple of (command_type, parameters_dict)
        """
        sql = sql.strip()
        
        # Try each pattern
        for cmd_type, pattern in self.patterns.items():
            match = pattern.match(sql)
            if match:
                params = match.groupdict()
                
                # Parse special fields
                if 'columns' in params and params['columns']:
                    params['columns'] = [c.strip() for c in params['columns'].split(',')]
                
                if 'values' in params and params['values']:
                    params['values'] = self._parse_values(params['values'])
                
                if 'privileges' in params and params['privileges']:
                    params['privileges'] = [p.strip().upper() for p in params['privileges'].split(',')]
                
                if 'description' in params and params['description']:
                    # Remove quotes
                    params['description'] = params['description'].strip('\'"')
                
                if 'limit' in params and params['limit']:
                    params['limit'] = int(params['limit'])
                
                return cmd_type, params
        
        # Check for simple commands
        sql_upper = sql.upper()
        if sql_upper == 'QUIT' or sql_upper == 'EXIT':
            return 'QUIT', {}
        
        return 'UNKNOWN', {'sql': sql}
    
    def _parse_values(self, values_str: str) -> List[Any]:
        """Parse VALUES clause."""
        values = []
        for val in values_str.split(','):
            val = val.strip()
            # Try to convert to number
            try:
                if '.' in val:
                    values.append(float(val))
                else:
                    values.append(int(val))
            except ValueError:
                # Remove quotes if present
                if (val.startswith("'") and val.endswith("'")) or \
                   (val.startswith('"') and val.endswith('"')):
                    val = val[1:-1]
                values.append(val)
        return values


class BackupRestoreParser:
    """Parser for backup and restore commands with encryption and compression support."""
    
    def __init__(self):
        self.patterns = {
            'BACKUP': re.compile(
                r'^\s*BACKUP\s+(?:DATABASE\s+)?(?P<db_name>\w+)' +
                r'(?:\s+TO\s+(?P<backup_path>\S+))?' +
                r'(?:\s+WITH\s+(?P<options>.+))?\s*$',
                re.IGNORECASE
            ),
            'RESTORE': re.compile(
                r'^\s*RESTORE\s+(?:DATABASE\s+)?(?P<db_name>\w+)' +
                r'(?:\s+FROM\s+(?P<backup_path>\S+))?' +
                r'(?:\s+WITH\s+(?P<options>.+))?\s*$',
                re.IGNORECASE
            ),
        }
    
    def parse(self, sql: str) -> Tuple[str, Dict[str, Any]]:
        """Parse backup/restore commands."""
        sql = sql.strip()
        
        for cmd_type, pattern in self.patterns.items():
            match = pattern.match(sql)
            if match:
                params = match.groupdict()
                
                # Parse options (ENCRYPTION, COMPRESSION, etc.)
                options_str = params.get('options', '')
                if options_str:
                    options = self._parse_options(options_str)
                    params.update(options)
                
                return cmd_type, params
        
        # Fall back to regular parser
        regular_parser = CommandParser()
        return regular_parser.parse(sql)
    
    def _parse_options(self, options_str: str) -> Dict[str, Any]:
        """Parse WITH options for backup/restore."""
        options = {}
        
        # ENCRYPTION 'password'
        enc_match = re.search(r"ENCRYPTION\s+['\"]([^'\"]+)['\"]", options_str, re.IGNORECASE)
        if enc_match:
            options['encryption'] = enc_match.group(1)
        
        # COMPRESSION 'gzip|lz4|zstd|none'
        comp_match = re.search(r"COMPRESSION\s+(\w+)", options_str, re.IGNORECASE)
        if comp_match:
            options['compression'] = comp_match.group(1).lower()
        
        # LEVEL 1-9
        level_match = re.search(r"LEVEL\s+(\d+)", options_str, re.IGNORECASE)
        if level_match:
            options['compression_level'] = int(level_match.group(1))
        
        return options


# Example usage
if __name__ == '__main__':
    parser = CommandParser()
    
    test_commands = [
        "CREATE DATABASE testdb",
        "USE testdb",
        "CREATE TABLE users (id INT, name TEXT)",
        "INSERT INTO users VALUES (1, 'Alice')",
        "SELECT * FROM users WHERE id = 1",
        "UPDATE users SET name = 'Bob' WHERE id = 1",
        "DELETE FROM users WHERE id = 1",
        "DROP TABLE users",
        "DROP DATABASE testdb",
        "GRANT SELECT, INSERT ON testdb.users TO alice",
        "REVOKE DELETE ON testdb.users FROM alice",
        "CREATE ROLE readonly DESCRIPTION 'Read-only access'",
        "GRANT ROLE readonly TO alice",
        "SHOW GRANTS FOR alice",
        "SHOW ROLES",
    ]
    
    for cmd in test_commands:
        cmd_type, params = parser.parse(cmd)
        print(f"Command: {cmd}")
        print(f"  Type: {cmd_type}")
        print(f"  Params: {params}")
        print()
    
    # Test backup/restore parser
    backup_parser = BackupRestoreParser()
    backup_commands = [
        "BACKUP DATABASE mydb TO /path/backup WITH ENCRYPTION 'mypass' COMPRESSION gzip",
        "BACKUP mydb WITH COMPRESSION lz4 LEVEL 9",
        "RESTORE DATABASE mydb FROM /path/backup WITH ENCRYPTION 'mypass'",
        "RESTORE mydb FROM backup.enc",
    ]
    
    print("=== Backup/Restore Commands ===")
    for cmd in backup_commands:
        cmd_type, params = backup_parser.parse(cmd)
        print(f"Command: {cmd}")
        print(f"  Type: {cmd_type}")
        print(f"  Params: {params}")
        print()
