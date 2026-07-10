"""
Tests for the validation layer.
"""

import unittest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validation import (
    ValidationResult, ValidationError,
    StringValidator, IntegerValidator, FloatValidator, BooleanValidator,
    ListValidator, DictValidator, EmailValidator, FilePathValidator,
    IdentifierValidator, DatabaseNameValidator, UsernameValidator,
    PasswordValidator, SQLValueValidator, SchemaValidator, FieldSchema,
    ValidatorType, InputSanitizer,
    validate_database_name, validate_table_name, validate_username,
    validate_password, validate_sql_values,
    CREATE_DATABASE_SCHEMA, INSERT_SCHEMA, UPDATE_SCHEMA
)


class TestStringValidator(unittest.TestCase):
    def test_valid_string(self):
        schema = FieldSchema("name", ValidatorType.STRING)
        validator = StringValidator(schema)
        valid, error, sanitized = validator.validate("hello")
        self.assertTrue(valid)
        self.assertIsNone(error)
        self.assertEqual(sanitized, "hello")
    
    def test_null_bytes_removed(self):
        schema = FieldSchema("name", ValidatorType.STRING)
        validator = StringValidator(schema)
        valid, error, sanitized = validator.validate("he\x00llo")
        self.assertTrue(valid)
        self.assertEqual(sanitized, "hello")
    
    def test_control_chars_removed(self):
        schema = FieldSchema("name", ValidatorType.STRING)
        validator = StringValidator(schema)
        valid, error, sanitized = validator.validate("hello\x01\x02world")
        self.assertTrue(valid)
        self.assertEqual(sanitized, "helloworld")
    
    def test_whitespace_normalized(self):
        schema = FieldSchema("name", ValidatorType.STRING)
        validator = StringValidator(schema)
        valid, error, sanitized = validator.validate("  hello   world  ")
        self.assertTrue(valid)
        self.assertEqual(sanitized, "hello world")
    
    def test_min_length(self):
        schema = FieldSchema("name", ValidatorType.STRING, min_length=5)
        validator = StringValidator(schema)
        valid, error, sanitized = validator.validate("hi")
        self.assertFalse(valid)
        self.assertIn("Minimum length", error)
    
    def test_max_length(self):
        schema = FieldSchema("name", ValidatorType.STRING, max_length=5)
        validator = StringValidator(schema)
        valid, error, sanitized = validator.validate("hello world")
        self.assertFalse(valid)
        self.assertIn("Maximum length", error)
    
    def test_pattern_match(self):
        schema = FieldSchema("name", ValidatorType.STRING, pattern=r'^[a-z]+$')
        validator = StringValidator(schema)
        valid, error, sanitized = validator.validate("hello")
        self.assertTrue(valid)
        
        valid, error, sanitized = validator.validate("Hello123")
        self.assertFalse(valid)
    
    def test_allowed_values(self):
        schema = FieldSchema("name", ValidatorType.STRING, allowed_values=["a", "b", "c"])
        validator = StringValidator(schema)
        valid, error, sanitized = validator.validate("a")
        self.assertTrue(valid)
        
        valid, error, sanitized = validator.validate("d")
        self.assertFalse(valid)


class TestIntegerValidator(unittest.TestCase):
    def test_valid_integer(self):
        schema = FieldSchema("count", ValidatorType.INTEGER)
        validator = IntegerValidator(schema)
        valid, error, sanitized = validator.validate(42)
        self.assertTrue(valid)
        self.assertEqual(sanitized, 42)
    
    def test_string_conversion(self):
        schema = FieldSchema("count", ValidatorType.INTEGER)
        validator = IntegerValidator(schema)
        valid, error, sanitized = validator.validate("42")
        self.assertTrue(valid)
        self.assertEqual(sanitized, 42)
    
    def test_float_conversion(self):
        schema = FieldSchema("count", ValidatorType.INTEGER)
        validator = IntegerValidator(schema)
        valid, error, sanitized = validator.validate(42.0)
        self.assertTrue(valid)
        self.assertEqual(sanitized, 42)
    
    def test_reject_float_with_decimals(self):
        schema = FieldSchema("count", ValidatorType.INTEGER)
        validator = IntegerValidator(schema)
        valid, error, sanitized = validator.validate(42.5)
        self.assertFalse(valid)
    
    def test_reject_boolean(self):
        schema = FieldSchema("count", ValidatorType.INTEGER)
        validator = IntegerValidator(schema)
        valid, error, sanitized = validator.validate(True)
        self.assertFalse(valid)
    
    def test_min_value(self):
        schema = FieldSchema("count", ValidatorType.INTEGER, min_value=0)
        validator = IntegerValidator(schema)
        valid, error, sanitized = validator.validate(-1)
        self.assertFalse(valid)
    
    def test_max_value(self):
        schema = FieldSchema("count", ValidatorType.INTEGER, max_value=100)
        validator = IntegerValidator(schema)
        valid, error, sanitized = validator.validate(101)
        self.assertFalse(valid)


class TestBooleanValidator(unittest.TestCase):
    def test_true_values(self):
        schema = FieldSchema("active", ValidatorType.BOOLEAN)
        validator = BooleanValidator(schema)
        
        for value in [True, "true", "TRUE", "1", "yes", "on", "enabled"]:
            valid, error, sanitized = validator.validate(value)
            self.assertTrue(valid, f"Failed for {value}")
            self.assertTrue(sanitized)
    
    def test_false_values(self):
        schema = FieldSchema("active", ValidatorType.BOOLEAN)
        validator = BooleanValidator(schema)
        
        for value in [False, "false", "FALSE", "0", "no", "off", "disabled"]:
            valid, error, sanitized = validator.validate(value)
            self.assertTrue(valid, f"Failed for {value}")
            self.assertFalse(sanitized)


class TestIdentifierValidator(unittest.TestCase):
    def test_valid_identifiers(self):
        schema = FieldSchema("name", ValidatorType.IDENTIFIER)
        validator = IdentifierValidator(schema)
        
        for name in ["users", "_private", "table_123", "UserName"]:
            valid, error, sanitized = validator.validate(name)
            self.assertTrue(valid, f"Failed for {name}")
    
    def test_invalid_start_char(self):
        schema = FieldSchema("name", ValidatorType.IDENTIFIER)
        validator = IdentifierValidator(schema)
        
        valid, error, sanitized = validator.validate("123abc")
        self.assertFalse(valid)
    
    def test_reserved_words(self):
        schema = FieldSchema("name", ValidatorType.IDENTIFIER)
        validator = IdentifierValidator(schema)
        
        for word in ["SELECT", "INSERT", "TABLE", "DROP"]:
            valid, error, sanitized = validator.validate(word)
            self.assertFalse(valid, f"Should reject reserved word: {word}")
    
    def test_too_long(self):
        schema = FieldSchema("name", ValidatorType.IDENTIFIER)
        validator = IdentifierValidator(schema)
        
        valid, error, sanitized = validator.validate("a" * 65)
        self.assertFalse(valid)


class TestDatabaseNameValidator(unittest.TestCase):
    def test_valid_names(self):
        schema = FieldSchema("name", ValidatorType.DATABASE_NAME)
        validator = DatabaseNameValidator(schema)
        
        for name in ["mydb", "users_db", "app123"]:
            valid, error, sanitized = validator.validate(name)
            self.assertTrue(valid, f"Failed for {name}")
    
    def test_reserved_names(self):
        schema = FieldSchema("name", ValidatorType.DATABASE_NAME)
        validator = DatabaseNameValidator(schema)
        
        for name in ["system", "sys", "mysql", "postgres"]:
            valid, error, sanitized = validator.validate(name)
            self.assertFalse(valid, f"Should reject reserved name: {name}")


class TestUsernameValidator(unittest.TestCase):
    def test_valid_usernames(self):
        schema = FieldSchema("name", ValidatorType.USERNAME)
        validator = UsernameValidator(schema)
        
        for name in ["alice", "bob_smith", "user-123", "a" * 32]:
            valid, error, sanitized = validator.validate(name)
            self.assertTrue(valid, f"Failed for {name}")
    
    def test_too_short(self):
        schema = FieldSchema("name", ValidatorType.USERNAME)
        validator = UsernameValidator(schema)
        
        valid, error, sanitized = validator.validate("ab")
        self.assertFalse(valid)
    
    def test_too_long(self):
        schema = FieldSchema("name", ValidatorType.USERNAME)
        validator = UsernameValidator(schema)
        
        valid, error, sanitized = validator.validate("a" * 33)
        self.assertFalse(valid)
    
    def test_invalid_chars(self):
        schema = FieldSchema("name", ValidatorType.USERNAME)
        validator = UsernameValidator(schema)
        
        for char in ["@", "!", "#", "$", "%", " "]:
            valid, error, sanitized = validator.validate(f"user{char}name")
            self.assertFalse(valid)


class TestPasswordValidator(unittest.TestCase):
    def test_too_short(self):
        schema = FieldSchema("password", ValidatorType.PASSWORD)
        validator = PasswordValidator(schema, min_length=8)
        
        valid, error, sanitized = validator.validate("short")
        self.assertFalse(valid)
        self.assertIn("at least 8 characters", error)
    
    def test_missing_uppercase(self):
        schema = FieldSchema("password", ValidatorType.PASSWORD)
        validator = PasswordValidator(schema, require_uppercase=True)
        
        valid, error, sanitized = validator.validate("password123")
        self.assertFalse(valid)
        self.assertIn("uppercase", error)
    
    def test_missing_lowercase(self):
        schema = FieldSchema("password", ValidatorType.PASSWORD)
        validator = PasswordValidator(schema, require_lowercase=True)
        
        valid, error, sanitized = validator.validate("PASSWORD123")
        self.assertFalse(valid)
        self.assertIn("lowercase", error)
    
    def test_missing_digit(self):
        schema = FieldSchema("password", ValidatorType.PASSWORD)
        validator = PasswordValidator(schema, require_digit=True)
        
        valid, error, sanitized = validator.validate("Password")
        self.assertFalse(valid)
        self.assertIn("digit", error)
    
    def test_valid_password(self):
        schema = FieldSchema("password", ValidatorType.PASSWORD)
        validator = PasswordValidator(schema)
        
        valid, error, sanitized = validator.validate("Password123")
        self.assertTrue(valid)


class TestFilePathValidator(unittest.TestCase):
    def test_valid_path(self):
        schema = FieldSchema("path", ValidatorType.FILE_PATH)
        validator = FilePathValidator(schema)
        
        valid, error, sanitized = validator.validate("backup.json.gz")
        self.assertTrue(valid)
    
    def test_directory_traversal(self):
        schema = FieldSchema("path", ValidatorType.FILE_PATH)
        validator = FilePathValidator(schema)
        
        valid, error, sanitized = validator.validate("../../etc/passwd")
        self.assertFalse(valid)
    
    def test_absolute_path_rejected(self):
        schema = FieldSchema("path", ValidatorType.FILE_PATH)
        validator = FilePathValidator(schema, allow_absolute=False)
        
        valid, error, sanitized = validator.validate("/etc/passwd")
        self.assertFalse(valid)
    
    def test_absolute_path_allowed(self):
        schema = FieldSchema("path", ValidatorType.FILE_PATH)
        validator = FilePathValidator(schema, allow_absolute=True)
        
        valid, error, sanitized = validator.validate("/etc/passwd")
        self.assertTrue(valid)


class TestSQLValueValidator(unittest.TestCase):
    def test_null_value(self):
        schema = FieldSchema("value", ValidatorType.SQL_VALUE)
        validator = SQLValueValidator(schema)
        
        valid, error, sanitized = validator.validate(None)
        self.assertTrue(valid)
        self.assertIsNone(sanitized)
    
    def test_integer(self):
        schema = FieldSchema("value", ValidatorType.SQL_VALUE)
        validator = SQLValueValidator(schema)
        
        valid, error, sanitized = validator.validate(42)
        self.assertTrue(valid)
        self.assertEqual(sanitized, 42)
    
    def test_boolean_converted(self):
        schema = FieldSchema("value", ValidatorType.SQL_VALUE)
        validator = SQLValueValidator(schema)
        
        valid, error, sanitized = validator.validate(True)
        self.assertTrue(valid)
        self.assertEqual(sanitized, 1)
    
    def test_string_sanitized(self):
        schema = FieldSchema("value", ValidatorType.SQL_VALUE)
        validator = SQLValueValidator(schema)
        
        valid, error, sanitized = validator.validate("hello")
        self.assertTrue(valid)
        self.assertEqual(sanitized, "hello")
    
    def test_null_bytes_rejected(self):
        schema = FieldSchema("value", ValidatorType.SQL_VALUE)
        validator = SQLValueValidator(schema)
        
        valid, error, sanitized = validator.validate("hello\x00world")
        self.assertFalse(valid)
    
    def test_sql_injection_patterns(self):
        schema = FieldSchema("value", ValidatorType.SQL_VALUE)
        validator = SQLValueValidator(schema)
        
        for pattern in ["'; DROP TABLE users; --", "/* malicious */"]:
            valid, error, sanitized = validator.validate(pattern)
            self.assertFalse(valid, f"Should reject: {pattern}")


class TestSchemaValidator(unittest.TestCase):
    def test_valid_data(self):
        fields = [
            FieldSchema("name", ValidatorType.STRING, required=True),
            FieldSchema("age", ValidatorType.INTEGER, required=True),
        ]
        validator = SchemaValidator(fields)
        
        result = validator.validate({"name": "Alice", "age": 30})
        self.assertTrue(result.is_valid)
        self.assertEqual(result.sanitized["name"], "Alice")
        self.assertEqual(result.sanitized["age"], 30)
    
    def test_missing_required_field(self):
        fields = [
            FieldSchema("name", ValidatorType.STRING, required=True),
        ]
        validator = SchemaValidator(fields)
        
        result = validator.validate({})
        self.assertFalse(result.is_valid)
        self.assertEqual(result.errors[0].field, "name")
    
    def test_default_value(self):
        fields = [
            FieldSchema("name", ValidatorType.STRING, required=True),
            FieldSchema("active", ValidatorType.BOOLEAN, default=True),
        ]
        validator = SchemaValidator(fields)
        
        result = validator.validate({"name": "Alice"})
        self.assertTrue(result.is_valid)
        self.assertTrue(result.sanitized["active"])
    
    def test_nullable_field(self):
        fields = [
            FieldSchema("name", ValidatorType.STRING, required=True),
            FieldSchema("email", ValidatorType.STRING, nullable=True),
        ]
        validator = SchemaValidator(fields)
        
        result = validator.validate({"name": "Alice", "email": None})
        self.assertTrue(result.is_valid)
        self.assertIsNone(result.sanitized["email"])


class TestPredefinedSchemas(unittest.TestCase):
    def test_create_database_schema(self):
        result = CREATE_DATABASE_SCHEMA.validate({"database": "mydb"})
        self.assertTrue(result.is_valid)
        
        result = CREATE_DATABASE_SCHEMA.validate({"database": "system"})
        self.assertFalse(result.is_valid)
    
    def test_insert_schema(self):
        result = INSERT_SCHEMA.validate({
            "table": "users",
            "values": [1, "Alice", "alice@example.com"]
        })
        self.assertTrue(result.is_valid)
        
        result = INSERT_SCHEMA.validate({"table": "users"})
        self.assertFalse(result.is_valid)  # Missing values
    
    def test_update_schema(self):
        result = UPDATE_SCHEMA.validate({
            "table": "users",
            "set": {"name": "Alice"},
            "where": {"id": 1}
        })
        self.assertTrue(result.is_valid)


class TestInputSanitizer(unittest.TestCase):
    def test_sanitize_sql_identifier(self):
        self.assertEqual(
            InputSanitizer.sanitize_sql_identifier("users"),
            "users"
        )
        self.assertEqual(
            InputSanitizer.sanitize_sql_identifier("users; DROP TABLE"),
            "usersDROPTABLE"
        )
        self.assertEqual(
            InputSanitizer.sanitize_sql_identifier("123users"),
            "_123users"
        )
    
    def test_sanitize_sql_value(self):
        self.assertIsNone(InputSanitizer.sanitize_sql_value(None))
        self.assertEqual(InputSanitizer.sanitize_sql_value(42), 42)
        self.assertEqual(InputSanitizer.sanitize_sql_value(True), 1)
        self.assertEqual(
            InputSanitizer.sanitize_sql_value("O'Brien"),
            "O''Brien"
        )
        self.assertEqual(
            InputSanitizer.sanitize_sql_value("hello\x00world"),
            "helloworld"
        )
    
    def test_sanitize_file_path(self):
        self.assertEqual(
            InputSanitizer.sanitize_file_path("../etc/passwd"),
            "etcpasswd"
        )


class TestConvenienceFunctions(unittest.TestCase):
    def test_validate_database_name(self):
        valid, error, sanitized = validate_database_name("mydb")
        self.assertTrue(valid)
        
        valid, error, sanitized = validate_database_name("system")
        self.assertFalse(valid)
    
    def test_validate_table_name(self):
        valid, error, sanitized = validate_table_name("users")
        self.assertTrue(valid)
        
        valid, error, sanitized = validate_table_name("SELECT")
        self.assertFalse(valid)
    
    def test_validate_username(self):
        valid, error, sanitized = validate_username("alice_smith")
        self.assertTrue(valid)
        
        valid, error, sanitized = validate_username("ab")
        self.assertFalse(valid)
    
    def test_validate_password(self):
        valid, error, sanitized = validate_password("Password123")
        self.assertTrue(valid)
        
        valid, error, sanitized = validate_password("weak")
        self.assertFalse(valid)
    
    def test_validate_sql_values(self):
        valid, error, sanitized = validate_sql_values([1, "hello", None])
        self.assertTrue(valid)
        self.assertEqual(sanitized, [1, "hello", None])
        
        valid, error, sanitized = validate_sql_values(["hello\x00"])
        self.assertFalse(valid)


if __name__ == '__main__':
    unittest.main(verbosity=2)
