"""
Prepared Statement Manager for KosDB

Implements prepared statement support with parameterized queries
for security (SQL injection prevention) and performance.
"""

import re
import uuid
import time
import threading
import logging
from typing import Dict, Optional, List, Any, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class ParameterError(Exception):
    """Raised when parameter binding fails."""
    pass


@dataclass
class PreparedStatement:
    """Represents a prepared statement."""
    statement_id: str
    original_sql: str
    parsed_sql: str  # SQL with placeholders
    parameter_names: List[str]  # Named parameters :name
    parameter_positions: List[int]  # Positional parameters ?
    created_at: float = field(default_factory=time.time)
    use_count: int = 0
    
    def __post_init__(self):
        import time
    
    def increment_use(self):
        """Increment usage counter."""
        self.use_count += 1


class PreparedStatementManager:
    """
    Manages prepared statements for session.
    
    Features:
    - Named parameters (:name)
    - Positional parameters (?)
    - Type-safe parameter binding
    - Automatic cleanup of expired statements
    """
    
    # Parameter patterns
    NAMED_PARAM_PATTERN = re.compile(r':([a-zA-Z_][a-zA-Z0-9_]*)')
    POSITIONAL_PATTERN = re.compile(r'\?')
    
    def __init__(self, max_statements: int = 100, ttl: Optional[int] = 3600):
        """
        Initialize prepared statement manager.
        
        Args:
            max_statements: Maximum prepared statements per session
            ttl: Time-to-live in seconds
        """
        self.max_statements = max_statements
        self.ttl = ttl
        self._statements: Dict[str, PreparedStatement] = {}
        self._lock = threading.RLock()
        self._sql_to_id: Dict[str, str] = {}  # normalized SQL -> statement_id
    
    def prepare(self, sql: str) -> str:
        """
        Prepare a SQL statement for later execution.
        
        Args:
            sql: SQL statement with parameters (:name or ?)
        
        Returns:
            statement_id: Unique identifier for this prepared statement
        
        Raises:
            ValueError: If statement cannot be prepared
        """
        normalized_sql = self._normalize_sql(sql)
        
        with self._lock:
            # Check if already prepared
            if normalized_sql in self._sql_to_id:
                return self._sql_to_id[normalized_sql]
            
            # Check capacity
            if len(self._statements) >= self.max_statements:
                self._cleanup_expired()
            
            if len(self._statements) >= self.max_statements:
                raise ValueError(f"Maximum prepared statements ({self.max_statements}) reached")
            
            # Parse parameters
            named_params = self.NAMED_PARAM_PATTERN.findall(sql)
            positional_count = len(self.POSITIONAL_PATTERN.findall(sql))
            
            if named_params and positional_count > 0:
                raise ValueError("Cannot mix named (:name) and positional (?) parameters")
            
            # Generate statement ID
            statement_id = str(uuid.uuid4())[:16]
            
            # Create parsed SQL with placeholders
            if named_params:
                parsed_sql = self.NAMED_PARAM_PATTERN.sub('?', sql)
                param_names = named_params
                param_positions = []
            else:
                parsed_sql = sql
                param_names = []
                param_positions = list(range(positional_count))
            
            stmt = PreparedStatement(
                statement_id=statement_id,
                original_sql=sql,
                parsed_sql=parsed_sql,
                parameter_names=param_names,
                parameter_positions=param_positions
            )
            
            self._statements[statement_id] = stmt
            self._sql_to_id[normalized_sql] = statement_id
            
            logger.debug(f"Prepared statement {statement_id}: {sql[:50]}...")
            return statement_id
    
    def execute(self, statement_id: str, parameters: Optional[Dict[str, Any]] = None) -> Tuple[str, List[Any]]:
        """
        Bind parameters to prepared statement.
        
        Args:
            statement_id: Statement ID from prepare()
            parameters: Parameter values (dict for named, list for positional)
        
        Returns:
            Tuple of (final_sql, bound_parameters)
        
        Raises:
            ParameterError: If parameter binding fails
        """
        with self._lock:
            if statement_id not in self._statements:
                raise ParameterError(f"Prepared statement {statement_id} not found")
            
            stmt = self._statements[statement_id]
            stmt.increment_use()
            
            if stmt.parameter_names:
                # Named parameters
                if not isinstance(parameters, dict):
                    raise ParameterError("Expected dict for named parameters")
                
                bound_values = []
                for name in stmt.parameter_names:
                    if name not in parameters:
                        raise ParameterError(f"Missing parameter: {name}")
                    bound_values.append(self._validate_value(parameters[name]))
                
                return stmt.parsed_sql, bound_values
            
            elif stmt.parameter_positions:
                # Positional parameters
                if not isinstance(parameters, (list, tuple)):
                    raise ParameterError("Expected list/tuple for positional parameters")
                
                if len(parameters) != len(stmt.parameter_positions):
                    raise ParameterError(
                        f"Expected {len(stmt.parameter_positions)} parameters, "
                        f"got {len(parameters)}"
                    )
                
                bound_values = [self._validate_value(p) for p in parameters]
                return stmt.parsed_sql, bound_values
            
            else:
                # No parameters
                return stmt.parsed_sql, []
    
    def deallocate(self, statement_id: str) -> bool:
        """
        Deallocate a prepared statement.
        
        Args:
            statement_id: Statement to deallocate
        
        Returns:
            True if found and removed, False otherwise
        """
        with self._lock:
            if statement_id not in self._statements:
                return False
            
            stmt = self._statements.pop(statement_id)
            normalized = self._normalize_sql(stmt.original_sql)
            self._sql_to_id.pop(normalized, None)
            
            logger.debug(f"Deallocated statement {statement_id}")
            return True
    
    def deallocate_all(self):
        """Deallocate all prepared statements."""
        with self._lock:
            count = len(self._statements)
            self._statements.clear()
            self._sql_to_id.clear()
            logger.debug(f"Deallocated all {count} statements")
    
    def get_statement(self, statement_id: str) -> Optional[PreparedStatement]:
        """Get prepared statement info."""
        with self._lock:
            return self._statements.get(statement_id)
    
    def list_statements(self) -> List[Dict[str, Any]]:
        """List all prepared statements."""
        with self._lock:
            return [
                {
                    'id': stmt.statement_id,
                    'sql': stmt.original_sql[:100] + '...' if len(stmt.original_sql) > 100 else stmt.original_sql,
                    'params': len(stmt.parameter_names) or len(stmt.parameter_positions),
                    'use_count': stmt.use_count,
                    'created_at': stmt.created_at
                }
                for stmt in self._statements.values()
            ]
    
    def _normalize_sql(self, sql: str) -> str:
        """Normalize SQL for deduplication."""
        # Remove extra whitespace and lowercase
        return ' '.join(sql.strip().lower().split())
    
    def _validate_value(self, value: Any) -> Any:
        """Validate and sanitize parameter value."""
        if value is None:
            return None
        elif isinstance(value, (int, float, bool)):
            return value
        elif isinstance(value, str):
            # Basic SQL injection prevention
            if any(pattern in value.upper() for pattern in [';', '--', '/*', '*/', 'DROP', 'DELETE FROM']):
                if not value.startswith("'") or not value.endswith("'"):
                    # Check if it looks like an injection attempt
                    dangerous = re.search(r'[;\-/*]', value)
                    if dangerous:
                        logger.warning(f"Potentially dangerous value detected: {value[:50]}")
            return value
        elif isinstance(value, (list, dict)):
            raise ParameterError("Complex types not supported as parameters")
        else:
            return str(value)
    
    def _cleanup_expired(self):
        """Remove expired prepared statements."""
        if not self.ttl:
            return
        
        import time
        cutoff = time.time() - self.ttl
        
        with self._lock:
            expired = [
                sid for sid, stmt in self._statements.items()
                if stmt.created_at < cutoff
            ]
            
            for sid in expired:
                stmt = self._statements.pop(sid)
                normalized = self._normalize_sql(stmt.original_sql)
                self._sql_to_id.pop(normalized, None)
            
            if expired:
                logger.debug(f"Cleaned up {len(expired)} expired statements")


# Session-local storage for prepared statements
_session_managers: Dict[str, PreparedStatementManager] = {}
_managers_lock = threading.Lock()


def get_session_manager(session_id: str) -> PreparedStatementManager:
    """Get or create prepared statement manager for session."""
    with _managers_lock:
        if session_id not in _session_managers:
            _session_managers[session_id] = PreparedStatementManager()
        return _session_managers[session_id]


def remove_session_manager(session_id: str):
    """Remove prepared statement manager for session."""
    with _managers_lock:
        if session_id in _session_managers:
            _session_managers[session_id].deallocate_all()
            del _session_managers[session_id]


def list_session_managers() -> List[str]:
    """List all active session IDs."""
    with _managers_lock:
        return list(_session_managers.keys())
