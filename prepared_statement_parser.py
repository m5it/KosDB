"""
Parser extensions for prepared statements.

Adds PREPARE, EXECUTE, and DEALLOCATE command parsing.
"""

import re
from typing import Dict, Any, Optional, List


class PreparedStatementParser:
    """
    Parser for prepared statement commands.
    
    Supports:
    - PREPARE name AS 'SELECT * FROM users WHERE id = :user_id'
    - EXECUTE name(user_id => 123)
    - EXECUTE name USING 123, 'value'
    - DEALLOCATE name
    - DEALLOCATE ALL
    """
    
    # Command patterns
    PREPARE_PATTERN = re.compile(
        r'PREPARE\s+(\w+)\s+AS\s+(.+)',
        re.IGNORECASE | re.DOTALL
    )
    
    EXECUTE_NAMED_PATTERN = re.compile(
        r'EXECUTE\s+(\w+)\s*\(([^)]*)\)',
        re.IGNORECASE
    )
    
    EXECUTE_USING_PATTERN = re.compile(
        r'EXECUTE\s+(\w+)\s+USING\s+(.+)',
        re.IGNORECASE
    )
    
    EXECUTE_SIMPLE_PATTERN = re.compile(
        r'EXECUTE\s+(\w+)',
        re.IGNORECASE
    )
    
    DEALLOCATE_PATTERN = re.compile(
        r'DEALLOCATE\s+(?:(ALL)|(\w+))',
        re.IGNORECASE
    )
    
    SHOW_PREPARED_PATTERN = re.compile(
        r'SHOW\s+PREPARED(\s+STATEMENTS)?',
        re.IGNORECASE
    )
    
    CACHE_STATS_PATTERN = re.compile(
        r'SHOW\s+CACHE\s+STATS',
        re.IGNORECASE
    )
    
    CACHE_INVALIDATE_PATTERN = re.compile(
        r'CACHE\s+INVALIDATE\s+(?:TABLE\s+)?(\w+)?',
        re.IGNORECASE
    )
    
    def parse(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Parse a prepared statement command.
        
        Args:
            query: SQL command string
        
        Returns:
            Parsed command dict or None if not recognized
        """
        query = query.strip()
        upper = query.upper()
        
        # PREPARE
        if upper.startswith('PREPARE'):
            return self._parse_prepare(query)
        
        # EXECUTE
        if upper.startswith('EXECUTE'):
            return self._parse_execute(query)
        
        # DEALLOCATE
        if upper.startswith('DEALLOCATE'):
            return self._parse_deallocate(query)
        
        # SHOW PREPARED
        if self.SHOW_PREPARED_PATTERN.match(query):
            return {
                'type': 'SHOW_PREPARED',
                'command': 'list_prepared'
            }
        
        # SHOW CACHE STATS
        if self.CACHE_STATS_PATTERN.match(query):
            return {
                'type': 'SHOW_CACHE_STATS',
                'command': 'cache_stats'
            }
        
        # CACHE INVALIDATE
        match = self.CACHE_INVALIDATE_PATTERN.match(query)
        if match:
            table_name = match.group(1)
            return {
                'type': 'CACHE_INVALIDATE',
                'command': 'cache_invalidate',
                'table': table_name
            }
        
        return None
    
    def _parse_prepare(self, query: str) -> Optional[Dict[str, Any]]:
        """Parse PREPARE statement."""
        match = self.PREPARE_PATTERN.match(query)
        if not match:
            return None
        
        name = match.group(1)
        sql = match.group(2).strip()
        
        # Remove surrounding quotes if present
        if (sql.startswith("'") and sql.endswith("'")) or \
           (sql.startswith('"') and sql.endswith('"')):
            sql = sql[1:-1]
        
        return {
            'type': 'PREPARE',
            'command': 'prepare',
            'statement_name': name,
            'sql': sql
        }
    
    def _parse_execute(self, query: str) -> Optional[Dict[str, Any]]:
        """Parse EXECUTE statement."""
        # Try named parameters first: EXECUTE name(param => value)
        match = self.EXECUTE_NAMED_PATTERN.match(query)
        if match:
            name = match.group(1)
            params_str = match.group(2).strip()
            parameters = self._parse_named_parameters(params_str)
            
            return {
                'type': 'EXECUTE',
                'command': 'execute',
                'statement_name': name,
                'parameters': parameters,
                'parameter_style': 'named'
            }
        
        # Try USING syntax: EXECUTE name USING value1, value2
        match = self.EXECUTE_USING_PATTERN.match(query)
        if match:
            name = match.group(1)
            values_str = match.group(2).strip()
            parameters = self._parse_positional_parameters(values_str)
            
            return {
                'type': 'EXECUTE',
                'command': 'execute',
                'statement_name': name,
                'parameters': parameters,
                'parameter_style': 'positional'
            }
        
        # Simple execute: EXECUTE name
        match = self.EXECUTE_SIMPLE_PATTERN.match(query)
        if match:
            return {
                'type': 'EXECUTE',
                'command': 'execute',
                'statement_name': match.group(1),
                'parameters': {},
                'parameter_style': 'none'
            }
        
        return None
    
    def _parse_deallocate(self, query: str) -> Optional[Dict[str, Any]]:
        """Parse DEALLOCATE statement."""
        match = self.DEALLOCATE_PATTERN.match(query)
        if not match:
            return None
        
        if match.group(1):  # ALL
            return {
                'type': 'DEALLOCATE_ALL',
                'command': 'deallocate_all'
            }
        else:
            return {
                'type': 'DEALLOCATE',
                'command': 'deallocate',
                'statement_name': match.group(2)
            }
    
    def _parse_named_parameters(self, params_str: str) -> Dict[str, Any]:
        """
        Parse named parameters: key => value, key2 => value2
        
        Args:
            params_str: Parameter string
        
        Returns:
            Dict of parameter names to values
        """
        parameters = {}
        
        # Split by comma, but handle nested structures
        pairs = self._split_parameters(params_str)
        
        for pair in pairs:
            pair = pair.strip()
            if '=>' in pair:
                key, value = pair.split('=>', 1)
                key = key.strip()
                value = self._parse_value(value.strip())
                parameters[key] = value
        
        return parameters
    
    def _parse_positional_parameters(self, values_str: str) -> List[Any]:
        """
        Parse positional parameters: value1, value2, value3
        
        Args:
            values_str: Values string
        
        Returns:
            List of values
        """
        values = []
        
        for val in self._split_parameters(values_str):
            val = val.strip()
            if val:
                values.append(self._parse_value(val))
        
        return values
    
    def _split_parameters(self, param_str: str) -> List[str]:
        """
        Split parameter string by comma, respecting parentheses and quotes.
        
        Args:
            param_str: Parameter string
        
        Returns:
            List of parameter strings
        """
        result = []
        current = []
        depth = 0
        in_quote = None
        
        for char in param_str:
            if char in '"\'':
                if in_quote is None:
                    in_quote = char
                elif in_quote == char:
                    in_quote = None
                current.append(char)
            elif char == '(' and in_quote is None:
                depth += 1
                current.append(char)
            elif char == ')' and in_quote is None:
                depth -= 1
                current.append(char)
            elif char == ',' and depth == 0 and in_quote is None:
                result.append(''.join(current).strip())
                current = []
            else:
                current.append(char)
        
        if current:
            result.append(''.join(current).strip())
        
        return result
    
    def _parse_value(self, value_str: str) -> Any:
        """
        Parse a value string to appropriate type.
        
        Args:
            value_str: Value as string
        
        Returns:
            Parsed value (int, float, bool, str, or None)
        """
        value_str = value_str.strip()
        
        # NULL
        if value_str.upper() == 'NULL':
            return None
        
        # Boolean
        upper = value_str.upper()
        if upper == 'TRUE':
            return True
        if upper == 'FALSE':
            return False
        
        # Number
        try:
            if '.' in value_str:
                return float(value_str)
            return int(value_str)
        except ValueError:
            pass
        
        # Quoted string
        if (value_str.startswith("'") and value_str.endswith("'")) or \
           (value_str.startswith('"') and value_str.endswith('"')):
            return value_str[1:-1]
        
        # Unquoted string
        return value_str


# Singleton parser instance
_prepared_parser: Optional[PreparedStatementParser] = None


def get_prepared_parser() -> PreparedStatementParser:
    """Get global prepared statement parser."""
    global _prepared_parser
    if _prepared_parser is None:
        _prepared_parser = PreparedStatementParser()
    return _prepared_parser
