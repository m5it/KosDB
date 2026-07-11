"""
Prepared Statement Cache for KosDB v3.3.0

Provides secure prepared statement execution with:
- PREPARE: Create prepared statements with parameter placeholders
- EXECUTE: Execute prepared statements with bound parameters
- DEALLOCATE: Remove prepared statements

Features:
- Parameter binding (positional ? and named :param)
- SQL injection prevention through proper escaping
- Statement caching with LRU eviction
- Type inference and validation
"""

import re
import hashlib
import threading
from typing import Dict, Any, List, Optional, Union, Tuple
from dataclasses import dataclass, field
from enum import Enum, auto
from collections import OrderedDict
import time


class ParameterStyle(Enum):
    """Styles of parameter placeholders."""
    QMARK = auto()      # ? (positional)
    NAMED = auto()      # :name (named)
    PYFORMAT = auto()   # %(name)s (Python style)


@dataclass
class PreparedStatement:
    """Represents a prepared statement."""
    name: str
    sql_template: str
    parameter_style: ParameterStyle
    parameters: List[str]  # Parameter names or positions
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    use_count: int = 0
    parsed_query: Optional[Dict[str, Any]] = None
    
    def touch(self):
        """Update last used timestamp."""
        self.last_used = time.time()
        self.use_count += 1


class ParameterBinder:
    """
    Handles parameter binding for prepared statements.
    
    Provides secure parameter substitution to prevent SQL injection.
    """
    
    # Type conversion handlers
    TYPE_HANDLERS = {
        int: lambda x: str(int(x)),
        float: lambda x: str(float(x)),
        bool: lambda x: 'TRUE' if x else 'FALSE',
        type(None): lambda x: 'NULL',
    }
    
    def __init__(self):
        self._string_cache: Dict[str, str] = {}
    
    def bind_parameters(self, sql_template: str, 
                       parameters: Union[List[Any], Dict[str, Any]],
                       style: ParameterStyle) -> str:
        """
        Bind parameters to SQL template securely.
        
        Args:
            sql_template: SQL with placeholders
            parameters: Values to bind
            style: Parameter placeholder style
        
        Returns:
            SQL with parameters bound
        
        Raises:
            ValueError: If parameter count mismatch or invalid values
        """
        if style == ParameterStyle.QMARK:
            return self._bind_positional(sql_template, parameters)
        elif style == ParameterStyle.NAMED:
            return self._bind_named(sql_template, parameters)
        elif style == ParameterStyle.PYFORMAT:
            return self._bind_pyformat(sql_template, parameters)
        else:
            raise ValueError(f"Unknown parameter style: {style}")
    
    def _bind_positional(self, sql_template: str, 
                         parameters: List[Any]) -> str:
        """Bind positional ? parameters."""
        parts = sql_template.split('?')
        
        if len(parts) - 1 != len(parameters):
            raise ValueError(
                f"Parameter count mismatch: expected {len(parts) - 1}, "
                f"got {len(parameters)}"
            )
        
        result = []
        for i, part in enumerate(parts[:-1]):
            result.append(part)
            result.append(self._format_value(parameters[i]))
        result.append(parts[-1])
        
        return ''.join(result)
    
    def _bind_named(self, sql_template: str, 
                    parameters: Dict[str, Any]) -> str:
        """Bind named :param parameters."""
        def replace_param(match):
            param_name = match.group(1)
            if param_name not in parameters:
                raise ValueError(f"Missing parameter: {param_name}")
            return self._format_value(parameters[param_name])
        
        # Pattern matches :param_name (alphanumeric and underscore)
        return re.sub(r':([a-zA-Z_][a-zA-Z0-9_]*)', replace_param, sql_template)
    
    def _bind_pyformat(self, sql_template: str, 
                       parameters: Dict[str, Any]) -> str:
        """Bind Python-style %(name)s parameters."""
        def replace_param(match):
            param_name = match.group(1)
            if param_name not in parameters:
                raise ValueError(f"Missing parameter: {param_name}")
            return self._format_value(parameters[param_name])
        
        return re.sub(r'%\\(([a-zA-Z_][a-zA-Z0-9_]*)\\)s', replace_param, sql_template)
    
    def _format_value(self, value: Any) -> str:
        """
        Format a value for SQL insertion.
        
        This is the critical security function - properly escapes
        all values to prevent SQL injection.
        """
        # Handle known types
        handler = self.TYPE_HANDLERS.get(type(value))
        if handler:
            return handler(value)
        
        # Handle strings - CRITICAL for SQL injection prevention
        if isinstance(value, str):
            return self._escape_string(value)
        
        # Default: convert to string and escape
        return self._escape_string(str(value))
    
    def _escape_string(self, value: str) -> str:
        """
        Escape a string value for safe SQL insertion.
        
        Implements standard SQL escaping:
        - Single quotes are doubled (' becomes '')
        - Backslashes are doubled
        - Null bytes are removed
        """
        # Security: Remove null bytes
        value = value.replace('\\x00', '')
        
        # Escape backslashes first (before quotes)
        value = value.replace('\\\\', '\\\\\\\\')
        
        # Escape single quotes by doubling
        value = value.replace("'", "''")
        
        # Wrap in single quotes
        return f"'{value}'"
    
    def validate_parameters(self, expected: List[str], 
                           provided: Union[List[Any], Dict[str, Any]],
                           style: ParameterStyle) -> bool:
        """
        Validate that provided parameters match expected.
        
        Args:
            expected: Expected parameter names/positions
            provided: Provided parameters
            style: Parameter style
        
        Returns:
            True if valid
        
        Raises:
            ValueError: If validation fails
        """
        if style == ParameterStyle.QMARK:
            if not isinstance(provided, (list, tuple)):
                raise ValueError("Positional parameters must be a list or tuple")
            if len(provided) != len(expected):
                raise ValueError(
                    f"Parameter count mismatch: expected {len(expected)}, "
                    f"got {len(provided)}"
                )
        else:
            if not isinstance(provided, dict):
                raise ValueError("Named parameters must be a dictionary")
            
            missing = set(expected) - set(provided.keys())
            if missing:
                raise ValueError(f"Missing parameters: {missing}")
            
            extra = set(provided.keys()) - set(expected)
            if extra:
                # Warn about extra parameters but don't fail
                pass
        
        return True


class PreparedStatementCache:
    """
    Cache for prepared statements with LRU eviction.
    
    Thread-safe implementation for concurrent access.
    """
    
    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self._cache: OrderedDict[str, PreparedStatement] = OrderedDict()
        self._lock = threading.RLock()
        self._stats = {
            'prepares': 0,
            'executes': 0,
            'deallocates': 0,
            'hits': 0,
            'misses': 0,
            'evictions': 0
        }
    
    def prepare(self, name: str, sql: str) -> PreparedStatement:
        """
        Prepare a statement and add to cache.
        
        Args:
            name: Statement name
            sql: SQL with parameter placeholders
        
        Returns:
            PreparedStatement object
        
        Raises:
            ValueError: If statement already exists or SQL is invalid
        """
        with self._lock:
            if name in self._cache:
                raise ValueError(f"Prepared statement already exists: {name}")
            
            # Parse SQL to identify parameters
            style, params = self._parse_parameters(sql)
            
            # Create prepared statement
            stmt = PreparedStatement(
                name=name,
                sql_template=sql,
                parameter_style=style,
                parameters=params
            )
            
            # Evict if necessary
            while len(self._cache) >= self.max_size:
                self._evict_lru()
            
            self._cache[name] = stmt
            self._stats['prepares'] += 1
            
            return stmt
    
    def execute(self, name: str, 
                parameters: Union[List[Any], Dict[str, Any]] = None) -> str:
        """
        Execute a prepared statement with parameters.
        
        Args:
            name: Statement name
            parameters: Values to bind
        
        Returns:
            SQL with parameters bound
        
        Raises:
            ValueError: If statement not found or parameters invalid
        """
        with self._lock:
            stmt = self._cache.get(name)
            
            if not stmt:
                self._stats['misses'] += 1
                raise ValueError(f"Prepared statement not found: {name}")
            
            self._stats['hits'] += 1
            self._stats['executes'] += 1
            
            # Move to end (most recently used)
            self._cache.move_to_end(name)
            stmt.touch()
            
            # Bind parameters
            binder = ParameterBinder()
            
            if parameters is None:
                parameters = [] if stmt.parameter_style == ParameterStyle.QMARK else {}
            
            binder.validate_parameters(stmt.parameters, parameters, stmt.parameter_style)
            
            return binder.bind_parameters(
                stmt.sql_template, 
                parameters, 
                stmt.parameter_style
            )
    
    def deallocate(self, name: str) -> bool:
        """
        Remove a prepared statement from cache.
        
        Args:
            name: Statement name
        
        Returns:
            True if removed, False if not found
        """
        with self._lock:
            if name in self._cache:
                del self._cache[name]
                self._stats['deallocates'] += 1
                return True
            return False
    
    def deallocate_all(self):
        """Remove all prepared statements."""
        with self._lock:
            self._cache.clear()
            self._stats['deallocates'] += len(self._cache)
    
    def get(self, name: str) -> Optional[PreparedStatement]:
        """Get a prepared statement without executing."""
        with self._lock:
            stmt = self._cache.get(name)
            if stmt:
                self._cache.move_to_end(name)
                stmt.touch()
            return stmt
    
    def _parse_parameters(self, sql: str) -> Tuple[ParameterStyle, List[str]]:
        """
        Parse SQL to identify parameter style and names.
        
        Returns:
            Tuple of (style, parameter_list)
        """
        # Check for positional ? markers
        qmark_count = sql.count('?')
        if qmark_count > 0:
            return ParameterStyle.QMARK, list(range(qmark_count))
        
        # Check for named :param markers
        named_params = re.findall(r':([a-zA-Z_][a-zA-Z0-9_]*)', sql)
        if named_params:
            return ParameterStyle.NAMED, named_params
        
        # Check for Python-style %(name)s markers
        pyformat_params = re.findall(r'%\\(([a-zA-Z_][a-zA-Z0-9_]*)\\)s', sql)
        if pyformat_params:
            return ParameterStyle.PYFORMAT, pyformat_params
        
        # No parameters
        return ParameterStyle.QMARK, []
    
    def _evict_lru(self):
        """Evict least recently used statement."""
        if self._cache:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
            self._stats['evictions'] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            return {
                'size': len(self._cache),
                'max_size': self.max_size,
                'prepares': self._stats['prepares'],
                'executes': self._stats['executes'],
                'deallocates': self._stats['deallocates'],
                'hits': self._stats['hits'],
                'misses': self._stats['misses'],
                'evictions': self._stats['evictions'],
                'hit_rate': self._stats['hits'] / (self._stats['hits'] + self._stats['misses'])
                           if (self._stats['hits'] + self._stats['misses']) > 0 else 0.0
            }
    
    def list_statements(self) -> List[str]:
        """List all prepared statement names."""
        with self._lock:
            return list(self._cache.keys())
    
    def explain(self) -> str:
        """Generate human-readable cache status."""
        stats = self.get_stats()
        
        lines = [
            "Prepared Statement Cache Status:",
            "=" * 50,
            f"Size: {stats['size']} / {stats['max_size']} statements",
            f"Prepares: {stats['prepares']}",
            f"Executes: {stats['executes']}",
            f"Deallocates: {stats['deallocates']}",
            f"Hit Rate: {stats['hit_rate']*100:.2f}%",
            f"Evictions: {stats['evictions']}",
            "",
            "Prepared Statements:",
            "-" * 30
        ]
        
        with self._lock:
            for name, stmt in self._cache.items():
                age = time.time() - stmt.created_at
                last_used = time.time() - stmt.last_used
                lines.append(
                    f"  {name}: {len(stmt.parameters)} params, "
                    f"{stmt.use_count} uses, "
                    f"last_used={last_used:.0f}s ago"
                )
        
        return "\\n".join(lines)


# SQL Injection Prevention Tests
class SQLInjectionTest:
    """
    Test cases for SQL injection prevention.
    """
    
    TEST_CASES = [
        # (description, template, params, expected_pattern)
        (
            "Basic string",
            "SELECT * FROM users WHERE name = ?",
            ["Alice"],
            r"SELECT \\* FROM users WHERE name = 'Alice'"
        ),
        (
            "Quote in string",
            "SELECT * FROM users WHERE name = ?",
            ["O'Brien"],
            r"SELECT \\* FROM users WHERE name = 'O''Brien'"
        ),
        (
            "Double quote in string",
            "SELECT * FROM users WHERE name = ?",
            ['Say "Hello"'],
            r"SELECT \\* FROM users WHERE name = 'Say ''Hello'''"
        ),
        (
            "Backslash in string",
            "SELECT * FROM users WHERE path = ?",
            ["/path\\\\to\\\\file"],
            r"SELECT \\* FROM users WHERE path = '/path\\\\\\\\to\\\\\\\\file'"
        ),
        (
            "Null byte attempt",
            "SELECT * FROM users WHERE name = ?",
            ["admin\\x00' OR '1'='1"],
            r"SELECT \\* FROM users WHERE name = 'admin'"
        ),
        (
            "Comment attempt",
            "SELECT * FROM users WHERE id = ?",
            ["1; -- comment"],
            r"SELECT \\* FROM users WHERE id = '1; -- comment'"
        ),
        (
            "Union attempt",
            "SELECT * FROM users WHERE id = ?",
            ["1 UNION SELECT * FROM passwords"],
            r"SELECT \\* FROM users WHERE id = '1 UNION SELECT \\* FROM passwords'"
        ),
        (
            "Named parameter",
            "SELECT * FROM users WHERE name = :name AND age > :min_age",
            {"name": "Alice", "min_age": 18},
            r"SELECT \\* FROM users WHERE name = 'Alice' AND age > 18"
        ),
        (
            "Integer parameter",
            "SELECT * FROM users WHERE id = ?",
            [42],
            r"SELECT \\* FROM users WHERE id = 42"
        ),
        (
            "Float parameter",
            "SELECT * FROM products WHERE price = ?",
            [19.99],
            r"SELECT \\* FROM products WHERE price = 19\\.99"
        ),
        (
            "Boolean parameter",
            "SELECT * FROM users WHERE active = ?",
            [True],
            r"SELECT \\* FROM users WHERE active = TRUE"
        ),
        (
            "NULL parameter",
            "SELECT * FROM users WHERE deleted_at = ?",
            [None],
            r"SELECT \\* FROM users WHERE deleted_at = NULL"
        ),
    ]
    
    @classmethod
    def run_tests(cls) -> List[Tuple[str, bool, str]]:
        """
        Run all SQL injection test cases.
        
        Returns:
            List of (description, passed, message) tuples
        """
        results = []
        binder = ParameterBinder()
        
        for desc, template, params, expected_pattern in cls.TEST_CASES:
            try:
                if isinstance(params, dict):
                    sql = binder.bind_named(template, params)
                else:
                    sql = binder.bind_positional(template, params)
                
                import re as regex
                if regex.search(expected_pattern, sql):
                    results.append((desc, True, "Passed"))
                else:
                    results.append((desc, False, f"Pattern mismatch. Got: {sql}"))
            except Exception as e:
                results.append((desc, False, str(e)))
        
        return results


# Convenience functions
def create_prepared_cache(max_size: int = 100) -> PreparedStatementCache:
    """Create a prepared statement cache."""
    return PreparedStatementCache(max_size=max_size)


def prepare_statement(cache: PreparedStatementCache, 
                      name: str, 
                      sql: str) -> PreparedStatement:
    """Prepare a statement."""
    return cache.prepare(name, sql)


def execute_statement(cache: PreparedStatementCache,
                      name: str,
                      parameters: Union[List[Any], Dict[str, Any]] = None) -> str:
    """Execute a prepared statement."""
    return cache.execute(name, parameters)


# Example usage
if __name__ == '__main__':
    # Create cache
    cache = create_prepared_cache()
    
    # Prepare statements
    stmt1 = cache.prepare("get_user", "SELECT * FROM users WHERE id = ?")
    print(f"Prepared: {stmt1.name} with {len(stmt1.parameters)} parameters")
    
    stmt2 = cache.prepare("get_active", 
                          "SELECT * FROM users WHERE status = :status AND age > :min_age")
    print(f"Prepared: {stmt2.name} with params: {stmt2.parameters}")
    
    # Execute with parameters
    sql1 = cache.execute("get_user", [42])
    print(f"Executed: {sql1}")
    
    sql2 = cache.execute("get_active", {"status": "active", "min_age": 18})
    print(f"Executed: {sql2}")
    
    # Run security tests
    print("\nRunning SQL Injection Tests:")
    results = SQLInjectionTest.run_tests()
    for desc, passed, msg in results:
        status = "✅" if passed else "❌"
        print(f"  {status} {desc}: {msg}")
    
    # Show cache stats
    print(f"\n{cache.explain()}")
