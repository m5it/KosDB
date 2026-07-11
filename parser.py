"""
SQL-like Command Parser for LevelDB Socket Server

Supports parsing of various SQL-like commands for database operations.
"""

import re
from typing import Dict, Any, Tuple, Optional, List
from json_functions import validate_json, extract_json_path


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
                r'^\s*SELECT\s+(?P<columns>[\w\s,>$\.\[\]\-\*]+)\s+FROM\s+(?P<table>\w+)(?:\s+WHERE\s+(?P<where>.+))?\s*$',
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
            'SELECT': re.compile(
                r'^\\s*SELECT\\s+(?P<columns>[\\w\\s,\\(\\)>\\$\\.\\[\\]\\-\\*]+)\\s+FROM\\s+(?P<table>\\w+)' +
                r'(?:\\s+WHERE\\s+(?P<where>.+))?' +
                r'(?:\\s+ORDER\\s+BY\\s+(?P<order_by>[\\w\\s,]+))?' +
                r'(?:\\s+LIMIT\\s+(?P<limit>\\d+))?\\s*$',
                re.IGNORECASE
            ),
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
            'CREATE_FULLTEXT_INDEX': re.compile(
                r'^\s*CREATE\s+FULLTEXT\s+INDEX\s+(?P<index_name>\w+)?\s*ON\s+(?P<table>\w+)\s*\((?P<columns>[\w\s,]+)\)\s*$',
                re.IGNORECASE
            ),
            'DROP_FULLTEXT_INDEX': re.compile(
                r'^\s*DROP\s+FULLTEXT\s+INDEX\s+(?P<index_name>\w+)?\s*ON\s+(?P<table>\w+)\s*$',
                re.IGNORECASE
            ),
            'SHOW_VIEWS': re.compile(
                r'^\s*SHOW\s+VIEWS\s*$',
                re.IGNORECASE
            ),
            'EXPLAIN': re.compile(
                r'^\s*EXPLAIN\s+(?P<target>.+)$',
                re.IGNORECASE
            ),
        }
    
    def parse(self, sql: str) -> Tuple[str, Dict[str, Any]]:
        """
        Parse SQL-like command and return command type and parameters.
        """
        sql = sql.strip()
        
        # Check for MATCH ... AGAINST first
        match_against = self._parse_match_against(sql)
        if match_against:
            return match_against
        
        # Try each pattern
        for cmd_type, pattern in self.patterns.items():
            match = pattern.match(sql)
            if match:
                params = match.groupdict()
                
                # Handle ALTER specially
                if cmd_type == 'ALTER':
                    return self.parse_alter_spec(params['table'], params['alter_spec'])
                
                # Parse special fields
                if 'columns' in params and params['columns']:
                    if cmd_type == 'CREATE_FULLTEXT_INDEX':
                        params['columns'] = [c.strip() for c in params['columns'].split(',')]
                    else:
                        params['columns'] = self._parse_select_columns(params['columns'])
                
                if 'values' in params and params['values']:
                    params['values'] = self._parse_values(params['values'])
                
                if 'privileges' in params and params['privileges']:
                    params['privileges'] = [p.strip().upper() for p in params['privileges'].split(',')]
                
                if 'description' in params and params['description']:
                    params['description'] = params['description'].strip('\'"')
                
                if 'limit' in params and params['limit']:
                    params['limit'] = int(params['limit'])
                
                return cmd_type, params
        
        # Check for simple commands
        sql_upper = sql.upper()
        if sql_upper == 'QUIT' or sql_upper == 'EXIT':
            return 'QUIT', {}
        return 'UNKNOWN', {'sql': sql}
    
    def _parse_where_clause(self, where_str: str) -> Dict[str, Any]:
        """
        Parse WHERE clause with support for subqueries.
        
        Supports:
        - Simple conditions: col = value
        - IN/NOT IN subqueries: col IN (SELECT ...)
        - EXISTS/NOT EXISTS: EXISTS (SELECT ...)
        - Scalar subqueries: col = (SELECT ...)
        """
        where_str = where_str.strip()
        conditions = []
        
        # Split by AND/OR while respecting parentheses
        parts = self._split_where_conditions(where_str)
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # Check for IN/NOT IN subquery
            in_match = re.match(r'(\\w+)\\s+(NOT\\s+)?IN\\s*\\((.+\\))\\s*$', part, re.IGNORECASE)
            if in_match:
                col = in_match.group(1)
                is_not = in_match.group(2) is not None
                subquery_str = in_match.group(3)
                
                # Check if it's a subquery
                if subquery_str.upper().startswith('SELECT'):
                    subquery = self._parse_subquery(subquery_str)
                    conditions.append({
                        'type': 'IN_SUBQUERY',
                        'column': col,
                        'subquery': subquery,
                        'negated': is_not
                    })
                    continue
                else:
                    # Regular IN with values
                    values = [v.strip().strip("'\"") for v in subquery_str.split(',')]
                    conditions.append({
                        'type': 'IN',
                        'column': col,
                        'values': values,
                        'negated': is_not
                    })
                    continue
            
            # Check for EXISTS/NOT EXISTS
            exists_match = re.match(r'(NOT\\s+)?EXISTS\\s*\\((.+\\))\\s*$', part, re.IGNORECASE)
            if exists_match:
                is_not = exists_match.group(1) is not None
                subquery_str = exists_match.group(2)
                subquery = self._parse_subquery(subquery_str)
                conditions.append({
                    'type': 'EXISTS',
                    'subquery': subquery,
                    'negated': is_not
                })
                continue
            
            # Check for scalar subquery: col = (SELECT ...)
            scalar_match = re.match(r'(\\w+)\\s*([=<>!]+)\\s*\\((SELECT.+\\))\\s*$', part, re.IGNORECASE)
            if scalar_match:
                col = scalar_match.group(1)
                op = scalar_match.group(2)
                subquery_str = scalar_match.group(3)
                subquery = self._parse_subquery(subquery_str)
                conditions.append({
                    'type': 'SCALAR_SUBQUERY',
                    'column': col,
                    'operator': op,
                    'subquery': subquery
                })
                continue
            
            # Regular condition
            cond_match = re.match(r'(\\w+)\\s*([=<>!]+)\\s*(.+)', part)
            if cond_match:
                conditions.append({
                    'type': 'SIMPLE',
                    'column': cond_match.group(1),
                    'operator': cond_match.group(2),
                    'value': cond_match.group(3).strip()
                })
        
        return {'conditions': conditions, 'raw': where_str}
    
    def _parse_subquery(self, subquery_str: str) -> Dict[str, Any]:
        """Parse a subquery string."""
        subquery_str = subquery_str.strip()
        
        # Remove outer parentheses if present
        while subquery_str.startswith('(') and subquery_str.endswith(')'):
            inner = subquery_str[1:-1].strip()
            # Check if parentheses are balanced
            depth = 0
            valid = True
            for char in inner:
                if char == '(':
                    depth += 1
                elif char == ')':
                    depth -= 1
                    if depth < 0:
                        valid = False
                        break
            if valid and depth == 0:
                subquery_str = inner
            else:
                break
        
        # Parse as regular SELECT
        sub_type, sub_params = self.parse(subquery_str)
        
        return {
            'type': sub_type,
            'params': sub_params,
            'raw': subquery_str,
            'is_correlated': self._is_correlated_subquery(subquery_str)
        }
    
    def _is_correlated_subquery(self, subquery_str: str) -> bool:
        """
        Check if subquery is correlated (references outer query).
        
        Looks for outer table references in WHERE clause.
        """
        # Simple heuristic: check for table.column references
        # that don't match the subquery's FROM table
        outer_refs = re.findall(r'(\\w+)\\.(\\w+)', subquery_str)
        
        # Get subquery's table
        from_match = re.search(r'FROM\\s+(\\w+)', subquery_str, re.IGNORECASE)
        if not from_match:
            return False
        
        subquery_table = from_match.group(1)
        
        # Check if any reference is to a different table
        for table, col in outer_refs:
            if table != subquery_table:
                return True
        
        return False
    
    def _split_where_conditions(self, where_str: str) -> List[str]:
        """Split WHERE clause by AND/OR respecting parentheses."""
        parts = []
        current = ""
        depth = 0
        i = 0
        
        while i < len(where_str):
            char = where_str[i]
            
            if char == '(':
                depth += 1
                current += char
            elif char == ')':
                depth -= 1
                current += char
            elif depth == 0:
                # Check for AND/OR
                remaining = where_str[i:].upper()
                if remaining.startswith('AND ') or remaining.startswith('AND\\t'):
                    parts.append(current)
                    current = ""
                    i += 3  # Skip 'AND'
                    continue
                elif remaining.startswith('OR ') or remaining.startswith('OR\\t'):
                    parts.append(current)
                    current = ""
                    i += 2  # Skip 'OR'
                    continue
                else:
                    current += char
            else:
                current += char
            
            i += 1
        
        if current.strip():
            parts.append(current)
        
        return parts
            }
        
        # RENAME COLUMN
        rename_match = re.match(r'RENAME\s+(?:COLUMN\s+)?(\w+)\s+TO\s+(\w+)', alter_spec, re.IGNORECASE)
        if rename_match:
            return 'ALTER_RENAME_COLUMN', {
                'table': table,
                'old_name': rename_match.group(1),
                'new_name': rename_match.group(2)
            }
        
        # ADD INDEX
        add_idx_match = re.match(r'ADD\s+(?:INDEX|KEY)\s+(?:\w+\s+)?\(([^)]+)\)', alter_spec, re.IGNORECASE)
        if add_idx_match:
            columns = [c.strip() for c in add_idx_match.group(1).split(',')]
            return 'ALTER_ADD_INDEX', {'table': table, 'columns': columns}
        
        # DROP INDEX
        drop_idx_match = re.match(r'DROP\s+(?:INDEX|KEY)\s+(\w+)', alter_spec, re.IGNORECASE)
        if drop_idx_match:
            return 'ALTER_DROP_INDEX', {'table': table, 'index_name': drop_idx_match.group(1)}
        
        # ADD CONSTRAINT
        add_cons_match = re.match(r'ADD\s+(?:CONSTRAINT\s+\w+\s+)?(.+)', alter_spec, re.IGNORECASE)
        if add_cons_match:
            constraint_def = add_cons_match.group(1)
            if constraint_def.upper().startswith('FOREIGN KEY'):
                fk_match = re.match(
                    r'FOREIGN\s+KEY\s*\(\s*(\w+)\s*\)\s+REFERENCES\s+(\w+)\s*\(\s*(\w+)\s*\)',
                    constraint_def, re.IGNORECASE
                )
                if fk_match:
                    return 'ALTER_ADD_FK', {
                        'table': table,
                        'column': fk_match.group(1),
                        'references_table': fk_match.group(2),
                        'references_column': fk_match.group(3)
                    }
            elif constraint_def.upper().startswith('UNIQUE'):
                unique_match = re.match(r'UNIQUE\s*\(\s*([^)]+)\s*\)', constraint_def, re.IGNORECASE)
                if unique_match:
                    columns = [c.strip() for c in unique_match.group(1).split(',')]
                    return 'ALTER_ADD_UNIQUE', {'table': table, 'columns': columns}
            elif constraint_def.upper().startswith('CHECK'):
                check_match = re.match(r'CHECK\s*\(([^)]+)\)', constraint_def, re.IGNORECASE)
                if check_match:
                    return 'ALTER_ADD_CHECK', {'table': table, 'expression': check_match.group(1)}
        
        # DROP CONSTRAINT
        drop_cons_match = re.match(r'DROP\s+(?:CONSTRAINT\s+)?(\w+)', alter_spec, re.IGNORECASE)
        if drop_cons_match:
            return 'ALTER_DROP_CONSTRAINT', {'table': table, 'constraint_name': drop_cons_match.group(1)}
        
        return 'UNKNOWN_ALTER', {'table': table, 'spec': alter_spec}
    
    def _parse_match_against(self, sql: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Parse MATCH ... AGAINST ... syntax for full-text search."""
        pattern = re.compile(
            r'^\s*MATCH\s*\((?P<columns>[\w\s,]+)\)\s+AGAINST\s*\(\s*[\'\"](?P<query>[^\'\"]+)[\'\"]\s*(?:\s+IN\s+(?P<mode>[\w\s]+)\s+MODE)?(?:\s+(?P<expansion>WITH\s+QUERY\s+EXPANSION))?\s*\)\s*$',
            re.IGNORECASE
        )
        
        match = pattern.match(sql)
        if match:
            params = match.groupdict()
            columns = [c.strip() for c in params['columns'].split(',')]
            
            mode = 'NATURAL'
            if params.get('mode'):
                mode_str = params['mode'].upper()
                if 'BOOLEAN' in mode_str:
                    mode = 'BOOLEAN'
                elif 'NATURAL' in mode_str:
                    mode = 'NATURAL'
            
            if params.get('expansion'):
                mode = 'EXPANSION'
            
            return 'MATCH_AGAINST', {'columns': columns, 'query': params['query'], 'mode': mode}
        
        return None
    
    def _parse_select_columns(self, columns_str: str) -> List[Any]:
        """Parse SELECT column list with JSON extraction support."""
        columns = []
        parts = self._split_columns(columns_str)
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # Check for JSON extraction: column->path or column->>path
            json_match = re.match(r'(\w+)(->>?)(.+)', part)
            if json_match:
                col_name = json_match.group(1)
                operator = json_match.group(2)
                json_path = json_match.group(3).strip()
                columns.append({
                    'name': col_name,
                    'json_path': json_path,
                    'json_as_text': operator == '->>'
                })
            elif ' AS ' in part.upper():
                parts = part.split()
                col_name = parts[0]
                alias = parts[-1]
                columns.append({'name': col_name, 'alias': alias})
            else:
                columns.append(part)
        
        return columns
    
    def _split_columns(self, args_str: str) -> List[str]:
        """Split comma-separated columns respecting parentheses."""
        parts = []
        current = ""
        depth = 0
        
        for char in args_str:
            if char == '(':
                depth += 1
                current += char
            elif char == ')':
                depth -= 1
                current += char
            elif char == ',' and depth == 0:
                parts.append(current)
                current = ""
            else:
                current += char
        
        if current.strip():
            parts.append(current)
        
        return parts
    
    def _parse_column_definition(self, col_def: str) -> Dict[str, Any]:
        """Parse a single column definition."""
        col_info = {
            'name': None,
            'type': 'TEXT',
            'primary_key': False,
            'index': False,
            'unique': False,
            'foreign_key': None,
            'check': None,
            'nullable': True,
            'default': None
        }
        
        # Check for PRIMARY KEY constraint
        pk_match = re.match(r'^\s*PRIMARY\s+KEY\s*\(\s*(\w+)\s*\)\s*$', col_def, re.IGNORECASE)
        if pk_match:
            return {'constraint_type': 'PRIMARY_KEY', 'column': pk_match.group(1)}
        
        # Check for FOREIGN KEY table-level constraint
        fk_match = re.match(
            r'^\s*FOREIGN\s+KEY\s*\(\s*(\w+)\s*\)\s+REFERENCES\s+(\w+)\s*\(\s*(\w+)\s*\)'
            r'(?:\s+ON\s+DELETE\s+(CASCADE|SET\s+NULL|RESTRICT|NO\s+ACTION))?'
            r'(?:\s+ON\s+UPDATE\s+(CASCADE|SET\s+NULL|RESTRICT|NO\s+ACTION))?\s*$',
            col_def, re.IGNORECASE
        )
        if fk_match:
            return {
                'constraint_type': 'FOREIGN_KEY',
                'column': fk_match.group(1),
                'references_table': fk_match.group(2),
                'references_column': fk_match.group(3),
                'on_delete': (fk_match.group(4) or 'RESTRICT').upper().replace(' ', '_'),
                'on_update': (fk_match.group(5) or 'RESTRICT').upper().replace(' ', '_')
            }
        
        # Check for UNIQUE constraint
        unique_match = re.match(r'^\s*UNIQUE\s*\(\s*([\w\s,]+)\s*\)\s*$', col_def, re.IGNORECASE)
        if unique_match:
            cols = [c.strip() for c in unique_match.group(1).split(',')]
            return {'constraint_type': 'UNIQUE', 'columns': cols}
        
        # Check for CHECK constraint
        check_match = re.match(r'^\s*CHECK\s*\((.+)\)\s*$', col_def, re.IGNORECASE)
        if check_match:
            return {'constraint_type': 'CHECK', 'expression': check_match.group(1).strip()}
        
        # Parse regular column definition
        parts = col_def.split()
        if not parts:
            return col_info
        
        col_info['name'] = parts[0]
        
        # Find type
        type_idx = 1
        if len(parts) > 1 and not parts[1].upper() in ('PRIMARY', 'UNIQUE', 'REFERENCES', 'CHECK', 'NOT', 'DEFAULT'):
            col_info['type'] = parts[1].upper()
            type_idx = 2
        
        # Parse constraints
        i = type_idx
        while i < len(parts):
            token = parts[i].upper()
            
            if token == 'PRIMARY' and i + 1 < len(parts) and parts[i + 1].upper() == 'KEY':
                col_info['primary_key'] = True
                col_info['nullable'] = False
                i += 2
            elif token == 'INDEX':
                col_info['index'] = True
                i += 1
            elif token == 'UNIQUE':
                col_info['unique'] = True
                i += 1
            elif token == 'NOT' and i + 1 < len(parts) and parts[i + 1].upper() == 'NULL':
                col_info['nullable'] = False
                i += 2
            elif token == 'NULL':
                col_info['nullable'] = True
                i += 1
            elif token == 'DEFAULT' and i + 1 < len(parts):
                col_info['default'] = parts[i + 1]
                i += 2
            elif token == 'REFERENCES':
                fk_info = self._parse_references_clause(parts, i)
                col_info['foreign_key'] = fk_info
                i = fk_info.get('_end_index', i + 1)
            elif token == 'CHECK':
                check_expr = self._parse_check_clause(parts, i)
                col_info['check'] = check_expr
                i = check_expr.get('_end_index', i + 1) if isinstance(check_expr, dict) else i + 1
            else:
                i += 1
        
        return col_info
    
    def _parse_references_clause(self, parts: List[str], start_idx: int) -> Dict[str, Any]:
        """Parse REFERENCES table(column) [ON DELETE ...] [ON UPDATE ...]."""
        fk_info = {
            'references_table': None,
            'references_column': None,
            'on_delete': 'RESTRICT',
            'on_update': 'RESTRICT'
        }
        
        i = start_idx + 1
        if i < len(parts):
            ref_table = parts[i]
            paren_match = re.match(r'(\w+)\((\w+)\)', ref_table)
            if paren_match:
                fk_info['references_table'] = paren_match.group(1)
                fk_info['references_column'] = paren_match.group(2)
                i += 1
            elif i + 1 < len(parts) and parts[i + 1].startswith('('):
                fk_info['references_table'] = ref_table
                col_match = re.match(r'\((\w+)\)', parts[i + 1])
                if col_match:
                    fk_info['references_column'] = col_match.group(1)
                i += 2
        
        while i < len(parts):
            token = parts[i].upper()
            if token == 'ON' and i + 2 < len(parts):
                action_type = parts[i + 1].upper()
                action = parts[i + 2].upper()
                if action_type == 'DELETE':
                    fk_info['on_delete'] = action.replace(' ', '_')
                    i += 3
                elif action_type == 'UPDATE':
                    fk_info['on_update'] = action.replace(' ', '_')
                    i += 3
                else:
                    i += 1
            else:
                break
        
        fk_info['_end_index'] = i
        return fk_info
    
    def _parse_check_clause(self, parts: List[str], start_idx: int) -> Dict[str, Any]:
        """Parse CHECK (expression)."""
        remaining = ' '.join(parts[start_idx + 1:])
        paren_match = re.match(r'\((.+)\)', remaining)
        if paren_match:
            return {'expression': paren_match.group(1).strip(), '_end_index': len(parts)}
        return {'expression': remaining.strip(), '_end_index': len(parts)}
    
    def _parse_values(self, values_str: str) -> List[Any]:
        """Parse VALUES clause."""
        values = []
        for val in values_str.split(','):
            val = val.strip()
            try:
                if '.' in val:
                    values.append(float(val))
                else:
                    values.append(int(val))
            except ValueError:
                if (val.startswith("'") and val.endswith("'")) or \
                   (val.startswith('"') and val.endswith('"')):
                    val = val[1:-1]
                values.append(val)
        return values


class BackupRestoreParser:
    """Parser for backup and restore commands."""
    
    def __init__(self):
        self.patterns = {
            'BACKUP': re.compile(
                r'^\s*BACKUP\s+(?:DATABASE\s+)?(?P<db_name>\w+)'
                r'(?:\s+TO\s+(?P<backup_path>\S+))?'
                r'(?:\s+WITH\s+(?P<options>.+))?\s*$',
                re.IGNORECASE
            ),
            'RESTORE': re.compile(
                r'^\s*RESTORE\s+(?:DATABASE\s+)?(?P<db_name>\w+)'
                r'(?:\s+FROM\s+(?P<backup_path>\S+))?'
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
                options_str = params.get('options', '')
                if options_str:
                    options = self._parse_options(options_str)
                    params.update(options)
                return cmd_type, params
        
        regular_parser = CommandParser()
        return regular_parser.parse(sql)
    
    def _parse_options(self, options_str: str) -> Dict[str, Any]:
        """Parse WITH options."""
        options = {}
        enc_match = re.search(r"ENCRYPTION\s+['\"]([^'\"]+)['\"]", options_str, re.IGNORECASE)
        if enc_match:
            options['encryption'] = enc_match.group(1)
        comp_match = re.search(r"COMPRESSION\s+(\w+)", options_str, re.IGNORECASE)
        if comp_match:
            options['compression'] = comp_match.group(1).lower()
        level_match = re.search(r"LEVEL\s+(\d+)", options_str, re.IGNORECASE)
        if level_match:
            options['compression_level'] = int(level_match.group(1))
        return options


if __name__ == '__main__':
    parser = CommandParser()
    
    test_commands = [
        "CREATE DATABASE testdb",
        "USE testdb",
        "CREATE TABLE users (id INT, name TEXT)",
        "INSERT INTO users VALUES (1, 'Alice')",
        "ALTER TABLE users ADD COLUMN email TEXT",
        "ALTER TABLE users DROP COLUMN email",
        "ALTER TABLE users MODIFY COLUMN age FLOAT",
        "ALTER TABLE users RENAME COLUMN age TO years",
    ]
    
    for cmd in test_commands:
        cmd_type, params = parser.parse(cmd)
        print(f"Command: {cmd}")
        print(f"  Type: {cmd_type}")
        print(f"  Params: {params}")
        print()
