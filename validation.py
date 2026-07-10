"""
Comprehensive Input Validation Layer for KosDB

Provides schema-based validation, type checking, sanitization,
and custom validators for database operations.
"""

import re
import os
import json
from typing import Any, Dict, List, Optional, Tuple, Union, Callable
from dataclasses import dataclass
from enum import Enum


class ValidationError(Exception):
    """Raised when validation fails."""
    def __init__(self, field: str, message: str, code: str = "INVALID"):
        self.field = field
        self.message = message
        self.code = code
        super().__init__(f"[{code}] {field}: {message}")


class ValidationResult:
    """Result of validation operation."""
    def __init__(self):
        self.errors: List[ValidationError] = []
        self.warnings: List[str] = []
        self.sanitized: Dict[str, Any] = {}
    
    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0
    
    def add_error(self, field: str, message: str, code: str = "INVALID"):
        self.errors.append(ValidationError(field, message, code))
    
    def add_warning(self, message: str):
        self.warnings.append(message)
    
    def raise_if_invalid(self):
        if not self.is_valid:
            raise self.errors[0]


class ValidatorType(Enum):
    """Built-in validator types."""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    LIST = "list"
    DICT = "dict"
    EMAIL = "email"
    URL = "url"
    UUID = "uuid"
    JSON = "json"
    REGEX = "regex"
    FILE_PATH = "file_path"
    IDENTIFIER = "identifier"
    DATABASE_NAME = "database_name"
    TABLE_NAME = "table_name"
    USERNAME = "username"
    PASSWORD = "password"
    SQL_VALUE = "sql_value"


@dataclass
class FieldSchema:
    """Schema definition for a field."""
    name: str
    type: Union[ValidatorType, str]
    required: bool = True
    nullable: bool = False
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    pattern: Optional[str] = None
    allowed_values: Optional[List[Any]] = None
    custom_validator: Optional[Callable[[Any], Tuple[bool, str]]] = None
    sanitize: bool = True
    default: Any = None


class BaseValidator:
    """Base class for all validators."""
    
    def __init__(self, schema: FieldSchema):
        self.schema = schema
    
    def validate(self, value: Any) -> Tuple[bool, Optional[str], Optional[Any]]:
        """
        Validate a value.
        Returns: (is_valid, error_message, sanitized_value)
        """
        raise NotImplementedError
    
    def sanitize(self, value: Any) -> Any:
        """Sanitize a value."""
        return value


class StringValidator(BaseValidator):
    """Validator for string values."""
    
    def validate(self, value: Any) -> Tuple[bool, Optional[str], Optional[Any]]:
        if value is None:
            if self.schema.nullable:
                return True, None, None
            return False, "Value is required", None
        
        if not isinstance(value, str):
            return False, f"Expected string, got {type(value).__name__}", None
        
        if self.schema.min_length is not None and len(value) < self.schema.min_length:
            return False, f"Minimum length is {self.schema.min_length}", None
        
        if self.schema.max_length is not None and len(value) > self.schema.max_length:
            return False, f"Maximum length is {self.schema.max_length}", None
        
        if self.schema.pattern and not re.match(self.schema.pattern, value):
            return False, f"Value does not match required pattern", None
        
        if self.schema.allowed_values and value not in self.schema.allowed_values:
            return False, f"Value must be one of: {self.schema.allowed_values}", None
        
        sanitized = self.sanitize(value) if self.schema.sanitize else value
        return True, None, sanitized
    
    def sanitize(self, value: str) -> str:
        # Remove null bytes and control characters
        sanitized = value.replace('\x00', '')
        sanitized = ''.join(c for c in sanitized if ord(c) >= 32 or c in '\t\n\r')
        # Normalize whitespace
        sanitized = ' '.join(sanitized.split())
        return sanitized.strip()


class IntegerValidator(BaseValidator):
    """Validator for integer values."""
    
    def validate(self, value: Any) -> Tuple[bool, Optional[str], Optional[Any]]:
        if value is None:
            if self.schema.nullable:
                return True, None, None
            return False, "Value is required", None
        
        try:
            if isinstance(value, bool):
                return False, "Boolean is not an integer", None
            if isinstance(value, float):
                if not value.is_integer():
                    return False, "Float with decimal places is not an integer", None
                int_value = int(value)
            elif isinstance(value, str):
                int_value = int(value)
            else:
                int_value = int(value)
        except (ValueError, TypeError):
            return False, f"Cannot convert to integer", None
        
        if self.schema.min_value is not None and int_value < self.schema.min_value:
            return False, f"Minimum value is {self.schema.min_value}", None
        
        if self.schema.max_value is not None and int_value > self.schema.max_value:
            return False, f"Maximum value is {self.schema.max_value}", None
        
        return True, None, int_value


class FloatValidator(BaseValidator):
    """Validator for float values."""
    
    def validate(self, value: Any) -> Tuple[bool, Optional[str], Optional[Any]]:
        if value is None:
            if self.schema.nullable:
                return True, None, None
            return False, "Value is required", None
        
        try:
            float_value = float(value)
        except (ValueError, TypeError):
            return False, f"Cannot convert to float", None
        
        if self.schema.min_value is not None and float_value < self.schema.min_value:
            return False, f"Minimum value is {self.schema.min_value}", None
        
        if self.schema.max_value is not None and float_value > self.schema.max_value:
            return False, f"Maximum value is {self.schema.max_value}", None
        
        return True, None, float_value


class BooleanValidator(BaseValidator):
    """Validator for boolean values."""
    
    TRUE_VALUES = {'true', '1', 'yes', 'on', 'enabled', True}
    FALSE_VALUES = {'false', '0', 'no', 'off', 'disabled', False}
    
    def validate(self, value: Any) -> Tuple[bool, Optional[str], Optional[Any]]:
        if value is None:
            if self.schema.nullable:
                return True, None, None
            return False, "Value is required", None
        
        if isinstance(value, bool):
            return True, None, value
        
        if isinstance(value, str):
            lower = value.lower()
            if lower in self.TRUE_VALUES:
                return True, None, True
            if lower in self.FALSE_VALUES:
                return True, None, False
        
        return False, "Expected boolean value", None


class ListValidator(BaseValidator):
    """Validator for list values."""
    
    def validate(self, value: Any) -> Tuple[bool, Optional[str], Optional[Any]]:
        if value is None:
            if self.schema.nullable:
                return True, None, None
            return False, "Value is required", None
        
        if isinstance(value, str):
            # Try to parse as JSON list
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    value = parsed
                else:
                    return False, "String is not a JSON list", None
            except json.JSONDecodeError:
                return False, "Invalid JSON list format", None
        
        if not isinstance(value, (list, tuple)):
            return False, f"Expected list, got {type(value).__name__}", None
        
        if self.schema.min_length is not None and len(value) < self.schema.min_length:
            return False, f"Minimum {self.schema.min_length} items required", None
        
        if self.schema.max_length is not None and len(value) > self.schema.max_length:
            return False, f"Maximum {self.schema.max_length} items allowed", None
        
        return True, None, list(value)


class DictValidator(BaseValidator):
    """Validator for dictionary values."""
    
    def validate(self, value: Any) -> Tuple[bool, Optional[str], Optional[Any]]:
        if value is None:
            if self.schema.nullable:
                return True, None, None
            return False, "Value is required", None
        
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return False, "Invalid JSON object format", None
        
        if not isinstance(value, dict):
            return False, f"Expected dict, got {type(value).__name__}", None
        
        return True, None, dict(value)


class EmailValidator(StringValidator):
    """Validator for email addresses."""
    
    EMAIL_PATTERN = re.compile(
        r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    )
    
    def validate(self, value: Any) -> Tuple[bool, Optional[str], Optional[Any]]:
        valid, error, sanitized = super().validate(value)
        if not valid:
            return valid, error, sanitized
        
        if not self.EMAIL_PATTERN.match(sanitized):
            return False, "Invalid email format", None
        
        return True, None, sanitized.lower()


class FilePathValidator(StringValidator):
    """Validator for file paths with security checks."""
    
    DANGEROUS_PATTERNS = [
        r'\.\.',  # Directory traversal
        r'~',     # Home directory
        r'\$[A-Z]',  # Environment variables
        r'`',     # Command substitution
        r'\|',    # Pipe
        r';',     # Command separator
        r'&&',    # Command chaining
        r'\|\|',  # Command chaining
    ]
    
    def __init__(self, schema: FieldSchema, allow_absolute: bool = False,
                 allowed_extensions: Optional[List[str]] = None,
                 must_exist: bool = False):
        super().__init__(schema)
        self.allow_absolute = allow_absolute
        self.allowed_extensions = allowed_extensions
        self.must_exist = must_exist
    
    def validate(self, value: Any) -> Tuple[bool, Optional[str], Optional[Any]]:
        valid, error, sanitized = super().validate(value)
        if not valid:
            return valid, error, sanitized
        
        # Check for dangerous patterns
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, sanitized):
                return False, f"Path contains dangerous pattern: {pattern}", None
        
        # Normalize path
        normalized = os.path.normpath(sanitized)
        
        # Check for absolute paths
        if os.path.isabs(normalized) and not self.allow_absolute:
            return False, "Absolute paths not allowed", None
        
        # Check extension
        if self.allowed_extensions:
            ext = os.path.splitext(normalized)[1].lower()
            if ext not in self.allowed_extensions:
                return False, f"Allowed extensions: {self.allowed_extensions}", None
        
        # Check if file exists (for read operations)
        if self.must_exist and not os.path.exists(normalized):
            return False, f"File does not exist: {normalized}", None
        
        return True, None, normalized


class IdentifierValidator(StringValidator):
    """Validator for SQL identifiers (table/column names)."""
    
    IDENTIFIER_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
    RESERVED_WORDS = {
        'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'TABLE',
        'DATABASE', 'WHERE', 'FROM', 'VALUES', 'SET', 'AND', 'OR', 'NOT',
        'NULL', 'TRUE', 'FALSE', 'BEGIN', 'COMMIT', 'ROLLBACK', 'USE',
        'SHOW', 'HELP', 'QUIT', 'EXIT', 'BACKUP', 'RESTORE', 'VERIFY'
    }
    
    def validate(self, value: Any) -> Tuple[bool, Optional[str], Optional[Any]]:
        valid, error, sanitized = super().validate(value)
        if not valid:
            return valid, error, sanitized
        
        if not self.IDENTIFIER_PATTERN.match(sanitized):
            return False, "Identifier must start with letter or underscore, followed by alphanumeric characters", None
        
        if sanitized.upper() in self.RESERVED_WORDS:
            return False, f"'{sanitized}' is a reserved word", None
        
        if len(sanitized) > 64:
            return False, "Identifier too long (max 64 characters)", None
        
        return True, None, sanitized


class DatabaseNameValidator(IdentifierValidator):
    """Validator for database names."""
    
    RESERVED_NAMES = {'system', 'sys', 'information_schema', 'mysql', 'postgres'}
    
    def validate(self, value: Any) -> Tuple[bool, Optional[str], Optional[Any]]:
        valid, error, sanitized = super().validate(value)
        if not valid:
            return valid, error, sanitized
        
        if sanitized.lower() in self.RESERVED_NAMES:
            return False, f"'{sanitized}' is a reserved database name", None
        
        return True, None, sanitized


class UsernameValidator(StringValidator):
    """Validator for usernames."""
    
    USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\-]{3,32}$')
    
    def validate(self, value: Any) -> Tuple[bool, Optional[str], Optional[Any]]:
        valid, error, sanitized = super().validate(value)
        if not valid:
            return valid, error, sanitized
        
        if not self.USERNAME_PATTERN.match(sanitized):
            return False, "Username must be 3-32 characters, alphanumeric with underscores and hyphens", None
        
        return True, None, sanitized.lower()


class PasswordValidator(StringValidator):
    """Validator for passwords with strength requirements."""
    
    def __init__(self, schema: FieldSchema, min_length: int = 8,
                 require_uppercase: bool = True,
                 require_lowercase: bool = True,
                 require_digit: bool = True,
                 require_special: bool = False):
        super().__init__(schema)
        self.min_length = min_length
        self.require_uppercase = require_uppercase
        self.require_lowercase = require_lowercase
        self.require_digit = require_digit
        self.require_special = require_special
    
    def validate(self, value: Any) -> Tuple[bool, Optional[str], Optional[Any]]:
        if value is None:
            if self.schema.nullable:
                return True, None, None
            return False, "Password is required", None
        
        if not isinstance(value, str):
            return False, "Password must be a string", None
        
        if len(value) < self.min_length:
            return False, f"Password must be at least {self.min_length} characters", None
        
        if self.require_uppercase and not re.search(r'[A-Z]', value):
            return False, "Password must contain at least one uppercase letter", None
        
        if self.require_lowercase and not re.search(r'[a-z]', value):
            return False, "Password must contain at least one lowercase letter", None
        
        if self.require_digit and not re.search(r'\d', value):
            return False, "Password must contain at least one digit", None
        
        if self.require_special and not re.search(r'[!@#$%^&*(),.?":{}|<>]', value):
            return False, "Password must contain at least one special character", None
        
        # Don't sanitize passwords - preserve exact value
        return True, None, value


class SQLValueValidator(BaseValidator):
    """Validator for SQL values (literals in INSERT/UPDATE)."""
    
    MAX_LENGTH = 65535  # Max string length
    
    def validate(self, value: Any) -> Tuple[bool, Optional[str], Optional[Any]]:
        if value is None:
            return True, None, None  # NULL is valid
        
        if isinstance(value, bool):
            return True, None, int(value)
        
        if isinstance(value, (int, float)):
            return True, None, value
        
        if isinstance(value, str):
            if len(value) > self.MAX_LENGTH:
                return False, f"String too long (max {self.MAX_LENGTH} characters)", None
            
            # Check for null bytes
            if '\x00' in value:
                return False, "Null bytes not allowed in strings", None
            
            # Basic SQL injection check
            dangerous = ['--', '/*', '*/', ';', 'DROP ', 'DELETE ', 'INSERT ']
            upper = value.upper()
            for pattern in dangerous:
                if pattern in upper:
                    return False, f"Potentially dangerous pattern detected: {pattern.strip()}", None
            
            return True, None, value
        
        return False, f"Unsupported value type: {type(value).__name__}", None


class SchemaValidator:
    """Main schema validation class."""
    
    VALIDATOR_MAP = {
        ValidatorType.STRING: StringValidator,
        ValidatorType.INTEGER: IntegerValidator,
        ValidatorType.FLOAT: FloatValidator,
        ValidatorType.BOOLEAN: BooleanValidator,
        ValidatorType.LIST: ListValidator,
        ValidatorType.DICT: DictValidator,
        ValidatorType.EMAIL: EmailValidator,
        ValidatorType.FILE_PATH: FilePathValidator,
        ValidatorType.IDENTIFIER: IdentifierValidator,
        ValidatorType.DATABASE_NAME: DatabaseNameValidator,
        ValidatorType.TABLE_NAME: IdentifierValidator,
        ValidatorType.USERNAME: UsernameValidator,
        ValidatorType.PASSWORD: PasswordValidator,
        ValidatorType.SQL_VALUE: SQLValueValidator,
    }
    
    def __init__(self, fields: List[FieldSchema]):
        self.fields = {f.name: f for f in fields}
    
    def validate(self, data: Dict[str, Any]) -> ValidationResult:
        """Validate data against schema."""
        result = ValidationResult()
        
        # Check required fields
        for name, field in self.fields.items():
            if field.required and name not in data:
                if field.default is not None:
                    result.sanitized[name] = field.default
                else:
                    result.add_error(name, "Required field missing", "REQUIRED")
                continue
            
            value = data.get(name)
            
            # Handle null values
            if value is None:
                if field.nullable:
                    result.sanitized[name] = None
                elif field.default is not None:
                    result.sanitized[name] = field.default
                else:
                    result.add_error(name, "Null value not allowed", "NULL_NOT_ALLOWED")
                continue
            
            # Get validator
            validator_class = self.VALIDATOR_MAP.get(field.type)
            if validator_class is None:
                result.add_error(name, f"Unknown validator type: {field.type}", "UNKNOWN_TYPE")
                continue
            
            # Validate
            validator = validator_class(field)
            is_valid, error, sanitized = validator.validate(value)
            
            if not is_valid:
                result.add_error(name, error or "Validation failed", "VALIDATION_FAILED")
            else:
                result.sanitized[name] = sanitized
        
        # Check for extra fields
        for key in data.keys():
            if key not in self.fields:
                result.add_warning(f"Unexpected field: {key}")
        
        return result


# Predefined schemas for common operations
CREATE_DATABASE_SCHEMA = SchemaValidator([
    FieldSchema("database", ValidatorType.DATABASE_NAME, required=True),
])

DROP_DATABASE_SCHEMA = SchemaValidator([
    FieldSchema("database", ValidatorType.DATABASE_NAME, required=True),
])

USE_DATABASE_SCHEMA = SchemaValidator([
    FieldSchema("database", ValidatorType.DATABASE_NAME, required=True),
])

CREATE_TABLE_SCHEMA = SchemaValidator([
    FieldSchema("table", ValidatorType.TABLE_NAME, required=True),
    FieldSchema("columns", ValidatorType.LIST, required=False, nullable=True, default=[]),
])

DROP_TABLE_SCHEMA = SchemaValidator([
    FieldSchema("table", ValidatorType.TABLE_NAME, required=True),
])

INSERT_SCHEMA = SchemaValidator([
    FieldSchema("table", ValidatorType.TABLE_NAME, required=True),
    FieldSchema("values", ValidatorType.LIST, required=True, min_length=1),
])

SELECT_SCHEMA = SchemaValidator([
    FieldSchema("table", ValidatorType.TABLE_NAME, required=True),
    FieldSchema("columns", ValidatorType.LIST, required=False, default=["*"]),
    FieldSchema("where", ValidatorType.DICT, required=False, nullable=True),
    FieldSchema("order_by", ValidatorType.IDENTIFIER, required=False, nullable=True),
    FieldSchema("order_desc", ValidatorType.BOOLEAN, required=False, default=False),
])

UPDATE_SCHEMA = SchemaValidator([
    FieldSchema("table", ValidatorType.TABLE_NAME, required=True),
    FieldSchema("set", ValidatorType.DICT, required=True, min_length=1),
    FieldSchema("where", ValidatorType.DICT, required=False, nullable=True),
])

DELETE_SCHEMA = SchemaValidator([
    FieldSchema("table", ValidatorType.TABLE_NAME, required=True),
    FieldSchema("where", ValidatorType.DICT, required=False, nullable=True),
])

BACKUP_SCHEMA = SchemaValidator([
    FieldSchema("database", ValidatorType.DATABASE_NAME, required=True),
    FieldSchema("file", ValidatorType.FILE_PATH, required=True),
])

RESTORE_SCHEMA = SchemaValidator([
    FieldSchema("database", ValidatorType.DATABASE_NAME, required=True),
    FieldSchema("file", ValidatorType.FILE_PATH, required=True),
])

BACKUP_TABLE_SCHEMA = SchemaValidator([
    FieldSchema("table", ValidatorType.TABLE_NAME, required=True),
    FieldSchema("file", ValidatorType.FILE_PATH, required=True),
])

CREATE_USER_SCHEMA = SchemaValidator([
    FieldSchema("username", ValidatorType.USERNAME, required=True),
    FieldSchema("password", ValidatorType.PASSWORD, required=True),
    FieldSchema("is_admin", ValidatorType.BOOLEAN, required=False, default=False),
])

GRANT_PRIVILEGE_SCHEMA = SchemaValidator([
    FieldSchema("username", ValidatorType.USERNAME, required=True),
    FieldSchema("database", ValidatorType.DATABASE_NAME, required=True),
    FieldSchema("table", ValidatorType.TABLE_NAME, required=True),
    FieldSchema("privileges", ValidatorType.LIST, required=True, min_length=1),
])


class InputSanitizer:
    """Utility class for sanitizing various inputs."""
    
    @staticmethod
    def sanitize_sql_identifier(identifier: str) -> str:
        """Sanitize SQL identifier."""
        # Remove dangerous characters
        sanitized = re.sub(r'[^\w]', '', identifier)
        # Ensure starts with letter or underscore
        if sanitized and not re.match(r'^[a-zA-Z_]', sanitized):
            sanitized = '_' + sanitized
        return sanitized[:64]  # Limit length
    
    @staticmethod
    def sanitize_sql_value(value: Any) -> Any:
        """Sanitize SQL value for safe use."""
        if value is None:
            return None
        
        if isinstance(value, bool):
            return int(value)
        
        if isinstance(value, (int, float)):
            return value
        
        if isinstance(value, str):
            # Remove null bytes
            value = value.replace('\x00', '')
            # Escape single quotes
            value = value.replace("'", "''")
            # Limit length
            return value[:65535]
        
        return str(value)
    
    @staticmethod
    def sanitize_file_path(path: str, allow_absolute: bool = False) -> str:
        """Sanitize file path."""
        # Normalize
        path = os.path.normpath(path)
        
        # Remove dangerous components
        path = re.sub(r'\.\.+', '', path)
        
        # Ensure relative unless allowed
        if not allow_absolute and os.path.isabs(path):
            path = path.lstrip('/').lstrip('\\')
        
        return path
    
    @staticmethod
    def sanitize_json_input(data: str) -> Dict:
        """Safely parse and sanitize JSON input."""
        try:
            parsed = json.loads(data)
            if not isinstance(parsed, dict):
                raise ValueError("JSON must be an object")
            return parsed
        except json.JSONDecodeError as e:
            raise ValidationError("json", f"Invalid JSON: {e}", "JSON_ERROR")
    
    @staticmethod
    def sanitize_regex_pattern(pattern: str) -> str:
        """Validate and sanitize regex pattern."""
        try:
            re.compile(pattern)
            return pattern
        except re.error as e:
            raise ValidationError("pattern", f"Invalid regex: {e}", "REGEX_ERROR")
    
    @staticmethod
    def escape_like_pattern(pattern: str) -> str:
        """Escape special characters in LIKE pattern."""
        return pattern.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


# Convenience functions
def validate_database_name(name: str) -> Tuple[bool, Optional[str], str]:
    """Quick validation for database names."""
    schema = FieldSchema("name", ValidatorType.DATABASE_NAME)
    validator = DatabaseNameValidator(schema)
    return validator.validate(name)


def validate_table_name(name: str) -> Tuple[bool, Optional[str], str]:
    """Quick validation for table names."""
    schema = FieldSchema("name", ValidatorType.TABLE_NAME)
    validator = IdentifierValidator(schema)
    return validator.validate(name)


def validate_username(name: str) -> Tuple[bool, Optional[str], str]:
    """Quick validation for usernames."""
    schema = FieldSchema("name", ValidatorType.USERNAME)
    validator = UsernameValidator(schema)
    return validator.validate(name)


def validate_password(password: str, min_length: int = 8) -> Tuple[bool, Optional[str], str]:
    """Quick validation for passwords."""
    schema = FieldSchema("password", ValidatorType.PASSWORD)
    validator = PasswordValidator(schema, min_length=min_length)
    return validator.validate(password)


def validate_file_path(path: str, **kwargs) -> Tuple[bool, Optional[str], str]:
    """Quick validation for file paths."""
    schema = FieldSchema("path", ValidatorType.FILE_PATH)
    validator = FilePathValidator(schema, **kwargs)
    return validator.validate(path)


def validate_sql_values(values: List[Any]) -> Tuple[bool, Optional[str], List[Any]]:
    """Validate list of SQL values."""
    schema = FieldSchema("values", ValidatorType.SQL_VALUE)
    validator = SQLValueValidator(schema)
    
    result = []
    for i, value in enumerate(values):
        valid, error, sanitized = validator.validate(value)
        if not valid:
            return False, f"Value at index {i}: {error}", []
        result.append(sanitized)
    
    return True, None, result
