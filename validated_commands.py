"""
Validated Command Wrappers for KosDB

Integrates the validation layer with the command execution framework.
Provides automatic input validation for all database operations.
"""

from typing import Dict, Any, Optional, Tuple
from functools import wraps

from validation import (
    ValidationResult, ValidationError,
    CREATE_DATABASE_SCHEMA, DROP_DATABASE_SCHEMA, USE_DATABASE_SCHEMA,
    CREATE_TABLE_SCHEMA, DROP_TABLE_SCHEMA, INSERT_SCHEMA,
    SELECT_SCHEMA, UPDATE_SCHEMA, DELETE_SCHEMA,
    BACKUP_SCHEMA, RESTORE_SCHEMA, BACKUP_TABLE_SCHEMA,
    CREATE_USER_SCHEMA, GRANT_PRIVILEGE_SCHEMA,
    InputSanitizer, validate_sql_values
)
from commands import (
    Command, CommandRegistry,
    CreateDatabaseCommand, DropDatabaseCommand, UseDatabaseCommand,
    CreateTableCommand, DropTableCommand, InsertCommand, SelectCommand,
    UpdateCommand, DeleteCommand, BackupDatabaseCommand, RestoreDatabaseCommand,
    BackupTableCommand
)
from database import Database


class ValidationFailedError(Exception):
    """Raised when command validation fails."""
    def __init__(self, errors: list):
        self.errors = errors
        message = "; ".join(f"{e.field}: {e.message}" for e in errors)
        super().__init__(message)


def validated_command(schema_validator=None, sanitize_params=True):
    """
    Decorator for adding validation to command execute methods.
    
    Args:
        schema_validator: SchemaValidator instance or None for no validation
        sanitize_params: Whether to replace params with sanitized values
    """
    def decorator(execute_func):
        @wraps(execute_func)
        def wrapper(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
            # Run validation if schema provided
            if schema_validator is not None:
                result = schema_validator.validate(params)
                
                if not result.is_valid:
                    # Format validation errors
                    error_messages = []
                    for error in result.errors:
                        error_messages.append(f"[{error.code}] {error.field}: {error.message}")
                    return f"ERROR: Validation failed - {'; '.join(error_messages)}"
                
                # Replace params with sanitized values
                if sanitize_params:
                    params = result.sanitized
            
            # Call original execute method
            return execute_func(self, params, client_state)
        
        return wrapper
    return decorator


class ValidatedCreateDatabaseCommand(CreateDatabaseCommand):
    """Create database command with validation."""
    
    @validated_command(CREATE_DATABASE_SCHEMA)
    def execute(self, params, client_state):
        return super().execute(params, client_state)


class ValidatedDropDatabaseCommand(DropDatabaseCommand):
    """Drop database command with validation."""
    
    @validated_command(DROP_DATABASE_SCHEMA)
    def execute(self, params, client_state):
        # Additional safety check - prevent dropping system databases
        db_name = params.get('database', '').lower()
        if db_name in ('system', 'sys', '_system'):
            return "ERROR: Cannot drop system database"
        return super().execute(params, client_state)


class ValidatedUseDatabaseCommand(UseDatabaseCommand):
    """Use database command with validation."""
    
    @validated_command(USE_DATABASE_SCHEMA)
    def execute(self, params, client_state):
        return super().execute(params, client_state)


class ValidatedCreateTableCommand(CreateTableCommand):
    """Create table command with validation."""
    
    @validated_command(CREATE_TABLE_SCHEMA)
    def execute(self, params, client_state):
        # Validate column definitions if provided
        columns = params.get('columns', [])
        if columns and isinstance(columns, list):
            for i, col in enumerate(columns):
                if isinstance(col, str):
                    # Validate column name
                    sanitized = InputSanitizer.sanitize_sql_identifier(col)
                    if sanitized != col:
                        return f"ERROR: Invalid column name at position {i}: '{col}'"
                    if not sanitized:
                        return f"ERROR: Empty column name at position {i}"
                elif isinstance(col, dict):
                    # Column with options: {name, type, primary_key, index}
                    name = col.get('name', '')
                    sanitized = InputSanitizer.sanitize_sql_identifier(name)
                    if sanitized != name:
                        return f"ERROR: Invalid column name: '{name}'"
        
        return super().execute(params, client_state)


class ValidatedDropTableCommand(DropTableCommand):
    """Drop table command with validation."""
    
    @validated_command(DROP_TABLE_SCHEMA)
    def execute(self, params, client_state):
        # Prevent dropping system tables
        table = params.get('table', '').lower()
        if table.startswith('_'):
            return "ERROR: Cannot drop system tables"
        return super().execute(params, client_state)


class ValidatedInsertCommand(InsertCommand):
    """Insert command with validation."""
    
    @validated_command(INSERT_SCHEMA)
    def execute(self, params, client_state):
        # Validate values
        values = params.get('values', [])
        valid, error, sanitized_values = validate_sql_values(values)
        if not valid:
            return f"ERROR: Invalid values - {error}"
        
        # Replace with sanitized values
        params['values'] = sanitized_values
        return super().execute(params, client_state)


class ValidatedSelectCommand(SelectCommand):
    """Select command with validation."""
    
    @validated_command(SELECT_SCHEMA)
    def execute(self, params, client_state):
        # Validate WHERE clause values if present
        where = params.get('where')
        if where and isinstance(where, dict):
            for key, value in where.items():
                # Sanitize column name
                sanitized_key = InputSanitizer.sanitize_sql_identifier(key)
                if sanitized_key != key:
                    return f"ERROR: Invalid column name in WHERE clause: '{key}'"
                
                # Validate value
                valid, error, sanitized = validate_sql_values([value])
                if not valid:
                    return f"ERROR: Invalid value in WHERE clause - {error}"
        
        return super().execute(params, client_state)


class ValidatedUpdateCommand(UpdateCommand):
    """Update command with validation."""
    
    @validated_command(UPDATE_SCHEMA)
    def execute(self, params, client_state):
        # Validate SET clause
        set_clause = params.get('set', {})
        if isinstance(set_clause, dict):
            sanitized_set = {}
            for key, value in set_clause.items():
                # Sanitize column name
                sanitized_key = InputSanitizer.sanitize_sql_identifier(key)
                if sanitized_key != key:
                    return f"ERROR: Invalid column name in SET: '{key}'"
                if not sanitized_key:
                    return f"ERROR: Empty column name in SET"
                
                # Validate and sanitize value
                valid, error, sanitized = validate_sql_values([value])
                if not valid:
                    return f"ERROR: Invalid value in SET - {error}"
                sanitized_set[sanitized_key] = sanitized[0]
            
            params['set'] = sanitized_set
        
        # Validate WHERE clause
        where = params.get('where')
        if where and isinstance(where, dict):
            for key, value in where.items():
                sanitized_key = InputSanitizer.sanitize_sql_identifier(key)
                if sanitized_key != key:
                    return f"ERROR: Invalid column name in WHERE: '{key}'"
        
        return super().execute(params, client_state)


class ValidatedDeleteCommand(DeleteCommand):
    """Delete command with validation."""
    
    @validated_command(DELETE_SCHEMA)
    def execute(self, params, client_state):
        # Require WHERE clause for safety (prevent accidental full table delete)
        where = params.get('where')
        if not where:
            return "ERROR: DELETE requires WHERE clause (use 'WHERE 1=1' to delete all)"
        
        # Validate WHERE clause
        if isinstance(where, dict):
            for key, value in where.items():
                sanitized_key = InputSanitizer.sanitize_sql_identifier(key)
                if sanitized_key != key:
                    return f"ERROR: Invalid column name in WHERE: '{key}'"
        
        return super().execute(params, client_state)


class ValidatedBackupDatabaseCommand(BackupDatabaseCommand):
    """Backup database command with validation."""
    
    @validated_command(BACKUP_SCHEMA)
    def execute(self, params, client_state):
        # Ensure file path has proper extension
        file_path = params.get('file', '')
        if not file_path.endswith('.json.gz'):
            params['file'] = file_path + '.json.gz'
        
        return super().execute(params, client_state)


class ValidatedRestoreDatabaseCommand(RestoreDatabaseCommand):
    """Restore database command with validation."""
    
    @validated_command(RESTORE_SCHEMA)
    def execute(self, params, client_state):
        # Ensure file path has proper extension
        file_path = params.get('file', '')
        if not file_path.endswith('.json.gz'):
            params['file'] = file_path + '.json.gz'
        
        return super().execute(params, client_state)


class ValidatedBackupTableCommand(BackupTableCommand):
    """Backup table command with validation."""
    
    @validated_command(BACKUP_TABLE_SCHEMA)
    def execute(self, params, client_state):
        # Ensure file path has proper extension
        file_path = params.get('file', '')
        if not file_path.endswith('.json.gz'):
            params['file'] = file_path + '.json.gz'
        
        return super().execute(params, client_state)


class ValidatedCommandRegistry(CommandRegistry):
    """
    Command registry that uses validated command classes.
    
    Drop-in replacement for CommandRegistry with full input validation.
    """
    
    def __init__(self, db: Database, replication_client=None):
        self.db = db
        self.replication_client = replication_client
        
        # Use validated command classes
        self.commands = {
            'CREATE_DB': ValidatedCreateDatabaseCommand(db),
            'DROP_DB': ValidatedDropDatabaseCommand(db),
            'USE': ValidatedUseDatabaseCommand(db),
            'CREATE': ValidatedCreateTableCommand(db),
            'DROP': ValidatedDropTableCommand(db),
            'INSERT': ValidatedInsertCommand(db),
            'SELECT': ValidatedSelectCommand(db),
            'UPDATE': ValidatedUpdateCommand(db),
            'DELETE': ValidatedDeleteCommand(db),
            'BACKUP_DB': ValidatedBackupDatabaseCommand(db),
            'RESTORE_DB': ValidatedRestoreDatabaseCommand(db),
            'BACKUP_TABLE': ValidatedBackupTableCommand(db),
        }
        
        # Copy other commands from parent (non-validated for now)
        base_registry = CommandRegistry(db, replication_client)
        for cmd_type, cmd in base_registry.commands.items():
            if cmd_type not in self.commands:
                self.commands[cmd_type] = cmd
    
    def execute(self, cmd_type: str, params: Dict, client_state: Dict) -> str:
        """Execute command with validation."""
        if cmd_type == 'UNKNOWN':
            return "ERROR: Unknown command"
        if cmd_type not in self.commands:
            return f"ERROR: {cmd_type} not implemented"
        
        try:
            return self.commands[cmd_type].execute(params, client_state)
        except ValidationFailedError as e:
            return f"ERROR: Validation failed - {str(e)}"
        except Exception as e:
            return f"ERROR: {e}"


# Migration helper
def enable_validation(registry: CommandRegistry) -> ValidatedCommandRegistry:
    """
    Convert existing CommandRegistry to use validation.
    
    Usage:
        registry = CommandRegistry(db, replication_client)
        validated_registry = enable_validation(registry)
    """
    return ValidatedCommandRegistry(registry.db, registry.replication_client)


# Validation-only mode for testing
class ValidationOnlyCommandRegistry:
    """
    Registry that only validates inputs without executing commands.
    Useful for testing and dry-run mode.
    """
    
    SCHEMA_MAP = {
        'CREATE_DB': CREATE_DATABASE_SCHEMA,
        'DROP_DB': DROP_DATABASE_SCHEMA,
        'USE': USE_DATABASE_SCHEMA,
        'CREATE': CREATE_TABLE_SCHEMA,
        'DROP': DROP_TABLE_SCHEMA,
        'INSERT': INSERT_SCHEMA,
        'SELECT': SELECT_SCHEMA,
        'UPDATE': UPDATE_SCHEMA,
        'DELETE': DELETE_SCHEMA,
        'BACKUP_DB': BACKUP_SCHEMA,
        'RESTORE_DB': RESTORE_SCHEMA,
        'BACKUP_TABLE': BACKUP_TABLE_SCHEMA,
    }
    
    def validate(self, cmd_type: str, params: Dict) -> ValidationResult:
        """Validate command parameters without executing."""
        schema = self.SCHEMA_MAP.get(cmd_type)
        if schema is None:
            result = ValidationResult()
            result.add_error("command", f"No validation schema for {cmd_type}", "NO_SCHEMA")
            return result
        
        return schema.validate(params)
    
    def is_valid(self, cmd_type: str, params: Dict) -> bool:
        """Quick check if parameters are valid."""
        result = self.validate(cmd_type, params)
        return result.is_valid
