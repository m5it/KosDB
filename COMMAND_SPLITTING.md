
# Command Splitting Documentation

## Overview

KosDB v2.3.0 includes a robust command splitter that handles complex SQL edge cases when executing batch commands.

## Features

### 1. Basic Semicolon Separation

Commands are split on semicolons by default:

```sql
SELECT 1; SELECT 2; SELECT 3
-- Results in 3 commands: ['SELECT 1', 'SELECT 2', 'SELECT 3']
```

### 2. Semicolons Inside Strings

Semicolons inside quoted strings are NOT command separators:

```sql
-- Single quotes
INSERT INTO t VALUES ('a;b;c')  -- Single command

-- Double quotes
INSERT INTO t VALUES ("x;y")      -- Single command
```

### 3. Escaped Semicolons

Use backslash to escape semicolons that should not split:

```sql
SELECT '\;' ; SELECT 2
-- Results in: ["SELECT '\;' ", 'SELECT 2']
```

### 4. SQL Escaped Quotes

Standard SQL escaped quotes are supported:

```sql
-- Single quote escaped by doubling
INSERT INTO t VALUES ('it''s working')  -- Contains: it's working

-- Double quote escaped by doubling
INSERT INTO t VALUES (""quoted"")         -- Contains: "quoted"
```

### 5. Nested Quotes

Different quote types can be nested:

```sql
SELECT "outer 'inner' end"      -- Double quotes contain single quotes
SELECT 'outer "inner" end'      -- Single quotes contain double quotes
```

### 6. Comments

SQL comments are removed during splitting:

```sql
-- Line comments (to end of line)
SELECT 1; -- this is a comment
SELECT 2

/* Block comments */
SELECT 1; /* inline */ SELECT 2

/* Multi-line
   block comment */
SELECT 3
```

### 7. Multi-line Commands

Commands can span multiple lines:

```sql
SELECT
    column1,
    column2
FROM
    table1;
```

### 8. Unicode Support

Full Unicode support for international characters:

```sql
INSERT INTO users VALUES ('日本語', '中文', '한국어');
INSERT INTO products VALUES ('🎉 Emoji', 'Ñoño');
```

## Usage

### Python API

```python
from command_splitter import CommandSplitter, split_commands

# Simple usage
commands = split_commands("SELECT 1; SELECT 2")
# ['SELECT 1', 'SELECT 2']

# With metadata
splitter = CommandSplitter()
result = splitter.split_with_metadata("""
    SELECT 1; -- comment
    SELECT 2
""")
# [
#   ('SELECT 1', {'had_comments': True, ...}),
#   ('SELECT 2', {'had_comments': True, ...})
# ]
```

### In Server

The server automatically uses the robust splitter when batch commands are detected:

```python
# In server.py
commands_list = self.parser.split_commands(data)
if len(commands_list) > 1:
    response = self._execute_batch(commands_list)
```

## Supported Escape Sequences

| Sequence | Meaning |
|----------|---------|
| `\'` | Literal single quote |
| `\"` | Literal double quote |
| `\\` | Literal backslash |
| `\;` | Literal semicolon (not a separator) |
| `''` | Escaped single quote (SQL standard) |
| `""` | Escaped double quote (SQL standard) |

## Limitations

1. **Complex Nested Quotes**: Very deeply nested quote patterns may not be handled correctly
2. **Comment Edge Cases**: Comments inside string literals that look like comment markers are treated as strings
3. **Backslash Escapes**: Only `\;`, `\'`, `\"`, and `\\` are supported as escape sequences
4. **Windows Paths**: Backslashes in Windows paths (e.g., `C:\path`) should be written as `C:\\path` or use forward slashes

## Testing

Run the comprehensive test suite:

```bash
python -m unittest tests.test_command_splitter -v
```

## Performance

- Small batches (< 10 commands): < 1ms
- Medium batches (10-100 commands): 1-5ms
- Large batches (100-1000 commands): 5-20ms

The splitter is optimized for performance with:
- Single-pass parsing
- Minimal memory allocations
- Efficient state tracking

## Migration from Legacy Splitter

The new splitter is backward compatible. To use the legacy simple splitter:

```python
from command_splitter import split_commands_legacy

commands = split_commands_legacy("SELECT 1; SELECT 2")
```

However, the legacy splitter does not handle:
- Escaped semicolons
- SQL escaped quotes
- Comments
- Complex nested quotes

## Examples

### Transaction Batch

```sql
BEGIN;
INSERT INTO accounts VALUES (1, 'Alice', 1000);
INSERT INTO accounts VALUES (2, 'Bob', 500);
UPDATE accounts SET balance = balance - 100 WHERE id = 1;
UPDATE accounts SET balance = balance + 100 WHERE id = 2;
COMMIT;
```

### Bulk Insert with Comments

```sql
-- Create table
CREATE TABLE logs (
    id INT,
    message TEXT,
    created_at TEXT
);

/* Insert sample data */
INSERT INTO logs VALUES (1, 'Started');
INSERT INTO logs VALUES (2, 'Processing; please wait');  -- Note: semicolon in string
INSERT INTO logs VALUES (3, 'Completed');
```

### Complex Query

```sql
-- User report with filters
SELECT 
    u.id,
    u.name,
    u.email
FROM users u
WHERE u.created_at > '2024-01-01'
    AND u.status = 'active'
ORDER BY u.name;

/* Count summary */
SELECT COUNT(*) FROM users WHERE status = 'active';
```

## See Also

- [Batch Execution Guide](BATCH_README.md)
- [Python Client Examples](examples/python/batch_example.py)
- [PHP Client Examples](examples/php/batch_example.php)
