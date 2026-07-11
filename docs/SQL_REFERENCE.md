# KosDB SQL Reference

Complete SQL syntax reference for KosDB v3.2.0.

## Table of Contents

- [Data Types](#data-types)
- [DDL Commands](#ddl-commands)
- [DML Commands](#dml-commands)
- [DCL Commands](#dcl-commands)
- [TCL Commands](#tcl-commands)
- [Query Operations](#query-operations)
- [Functions](#functions)
- [Constraints](#constraints)
- [Operators](#operators)

## Data Types

| Type | Description | Example |
|------|-------------|---------|
| `INT` | 64-bit integer | `42` |
| `FLOAT` | Double-precision float | `3.14` |
| `TEXT` | Variable-length string | `'Hello'` |
| `BOOLEAN` | True/False value | `TRUE`, `FALSE` |
| `JSON` | JSON document | `'{"key": "value"}'` |
| `BLOB` | Binary data | `X'1A2B3C'` |
| `TIMESTAMP` | Date and time | `'2024-01-15 10:30:00'` |

## DDL Commands

### CREATE DATABASE

Create a new database.

```sql
CREATE DATABASE database_name;
```

### DROP DATABASE

Delete a database.

```sql
DROP DATABASE database_name;
```

### USE

Select current database.

```sql
USE database_name;
```

### CREATE TABLE

Create a new table with columns and constraints.

```sql
CREATE TABLE table_name (
    column_name data_type [constraints],
    ...
    [table_constraints]
);
```

**Example:**

```sql
CREATE TABLE users (
    id INT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    age INT CHECK (age >= 18),
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Table-level constraints
    CONSTRAINT chk_email CHECK (email LIKE '%@%'),
    INDEX idx_name (name)
);
```

### DROP TABLE

Delete a table.

```sql
DROP TABLE table_name;
```

### ALTER TABLE

Modify table structure (v3.2.0+).

#### ADD COLUMN

```sql
ALTER TABLE table_name ADD COLUMN column_name data_type [constraints];
```

**Example:**
```sql
ALTER TABLE users ADD COLUMN phone TEXT;
ALTER TABLE users ADD COLUMN status TEXT CHECK (status IN ('active', 'inactive'));
```

#### DROP COLUMN

```sql
ALTER TABLE table_name DROP COLUMN column_name [CASCADE];
```

**Example:**
```sql
ALTER TABLE users DROP COLUMN phone;
ALTER TABLE users DROP COLUMN email CASCADE;
```

#### MODIFY COLUMN

```sql
ALTER TABLE table_name MODIFY COLUMN column_name new_data_type [constraints];
```

**Example:**
```sql
ALTER TABLE users MODIFY COLUMN age FLOAT;
```

#### RENAME COLUMN

```sql
ALTER TABLE table_name RENAME COLUMN old_name TO new_name;
```

**Example:**
```sql
ALTER TABLE users RENAME COLUMN name TO full_name;
```

#### ADD INDEX

```sql
ALTER TABLE table_name ADD INDEX index_name (column1, column2, ...);
```

**Example:**
```sql
ALTER TABLE users ADD INDEX idx_email (email);
ALTER TABLE users ADD INDEX idx_name_age (name, age);
```

#### DROP INDEX

```sql
ALTER TABLE table_name DROP INDEX index_name;
```

**Example:**
```sql
ALTER TABLE users DROP INDEX idx_email;
```

#### ADD CONSTRAINT

```sql
ALTER TABLE table_name ADD CONSTRAINT constraint_name constraint_definition;
```

**Example:**
```sql
-- Foreign key
ALTER TABLE orders ADD CONSTRAINT fk_user 
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

-- CHECK constraint
ALTER TABLE users ADD CONSTRAINT chk_age CHECK (age >= 0);

-- UNIQUE constraint
ALTER TABLE users ADD CONSTRAINT uk_email UNIQUE (email);
```

#### DROP CONSTRAINT

```sql
ALTER TABLE table_name DROP CONSTRAINT constraint_name;
```

**Example:**
```sql
ALTER TABLE users DROP CONSTRAINT chk_age;
```

### CREATE VIEW

Create a virtual table based on a query (v3.2.0+).

```sql
CREATE VIEW view_name AS select_statement;
```

**Example:**
```sql
CREATE VIEW active_users AS
SELECT * FROM users WHERE status = 'active';

CREATE VIEW user_orders AS
SELECT u.name, o.total, o.status
FROM users u
JOIN orders o ON u.id = o.user_id;
```

### DROP VIEW

Delete a view.

```sql
DROP VIEW view_name;
```

### CREATE FULLTEXT INDEX

Create full-text search index (v3.2.0+).

```sql
CREATE FULLTEXT INDEX index_name ON table_name(column_name);
```

**Example:**
```sql
CREATE FULLTEXT INDEX idx_content ON articles(content);
```

### DROP FULLTEXT INDEX

Remove full-text index.

```sql
DROP FULLTEXT INDEX index_name ON table_name;
```

## DML Commands

### INSERT

Insert data into a table.

```sql
INSERT INTO table_name VALUES (value1, value2, ...);
INSERT INTO table_name (column1, column2) VALUES (value1, value2);
INSERT INTO table_name VALUES (value1, value2, ...), (value3, value4, ...);
```

**Example:**
```sql
INSERT INTO users VALUES (1, 'Alice', 'alice@example.com', 30, NULL);
INSERT INTO users (name, email) VALUES ('Bob', 'bob@example.com');
INSERT INTO users VALUES 
    (2, 'Charlie', 'charlie@example.com', 25, NULL),
    (3, 'Diana', 'diana@example.com', 28, NULL);
```

### SELECT

Query data from tables.

```sql
SELECT [DISTINCT] column1, column2, ...
FROM table_name
[JOIN ...]
[WHERE conditions]
[GROUP BY column1, ...]
[HAVING conditions]
[ORDER BY column1 [ASC|DESC], ...]
[LIMIT n [OFFSET m]];
```

**Basic Examples:**
```sql
SELECT * FROM users;
SELECT name, email FROM users;
SELECT DISTINCT status FROM users;
```

#### WHERE Clause

```sql
SELECT * FROM users WHERE age > 25;
SELECT * FROM users WHERE name = 'Alice';
SELECT * FROM users WHERE email LIKE '%@example.com';
SELECT * FROM users WHERE age BETWEEN 20 AND 30;
SELECT * FROM users WHERE status IN ('active', 'pending');
```

#### JOIN Operations

```sql
-- Inner join
SELECT * FROM users u JOIN orders o ON u.id = o.user_id;

-- Left join
SELECT * FROM users u LEFT JOIN orders o ON u.id = o.user_id;

-- Multiple joins
SELECT * FROM users u
JOIN orders o ON u.id = o.user_id
JOIN products p ON o.product_id = p.id;
```

#### Subqueries (v3.2.0+)

**Scalar Subquery:**
```sql
SELECT name, (SELECT COUNT(*) FROM orders) as order_count 
FROM users;
```

**IN Subquery:**
```sql
SELECT * FROM users WHERE id IN (SELECT user_id FROM orders WHERE total > 100);
SELECT * FROM users WHERE id NOT IN (SELECT user_id FROM orders);
```

**EXISTS Subquery:**
```sql
SELECT * FROM users WHERE EXISTS (SELECT 1 FROM orders WHERE user_id = users.id);
SELECT * FROM users WHERE NOT EXISTS (SELECT 1 FROM orders WHERE user_id = users.id);
```

**Correlated Subquery:**
```sql
SELECT name, 
    (SELECT MAX(total) FROM orders WHERE orders.user_id = users.id) as max_order
FROM users;
```

#### JSON Operations (v3.2.0+)

```sql
-- Extract JSON value
SELECT metadata->city FROM users;
SELECT metadata->>'city' FROM users;  -- As text

-- Filter by JSON value
SELECT * FROM users WHERE metadata->type = 'premium';
```

#### Full-Text Search (v3.2.0+)

```sql
-- Natural language mode
SELECT * FROM articles WHERE MATCH(content) AGAINST('database optimization');

-- Boolean mode
SELECT * FROM articles WHERE MATCH(content) AGAINST('+database -mysql' IN BOOLEAN MODE);

-- With query expansion
SELECT * FROM articles WHERE MATCH(content) AGAINST('database' WITH QUERY EXPANSION);
```

#### ORDER BY

```sql
SELECT * FROM users ORDER BY age;
SELECT * FROM users ORDER BY age DESC;
SELECT * FROM users ORDER BY name ASC, age DESC;
```

#### LIMIT and OFFSET

```sql
SELECT * FROM users LIMIT 10;
SELECT * FROM users LIMIT 10 OFFSET 20;
SELECT * FROM users ORDER BY id LIMIT 10 OFFSET 20;
```

### UPDATE

Modify existing data.

```sql
UPDATE table_name 
SET column1 = value1, column2 = value2, ...
[WHERE conditions];
```

**Example:**
```sql
UPDATE users SET age = 31 WHERE id = 1;
UPDATE users SET status = 'inactive', updated_at = CURRENT_TIMESTAMP 
WHERE last_login < '2023-01-01';
UPDATE users SET metadata = '{"tier": "premium"}' WHERE id = 1;
```

### DELETE

Remove data from tables.

```sql
DELETE FROM table_name [WHERE conditions];
```

**Example:**
```sql
DELETE FROM users WHERE id = 1;
DELETE FROM users WHERE status = 'inactive';
DELETE FROM users;  -- Delete all rows (use with caution!)
```

## DCL Commands

### CREATE USER

Create a new database user.

```sql
CREATE USER username PASSWORD 'password';
```

### DROP USER

Delete a user.

```sql
DROP USER username;
```

### GRANT

Grant privileges to users or roles.

```sql
GRANT privilege_list ON database.table TO username;
GRANT privilege_list ON database.* TO username;
GRANT privilege_list ON *.* TO username;
```

**Privileges:** SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, INDEX, REFERENCES, ADMIN

**Example:**
```sql
GRANT SELECT, INSERT ON mydb.users TO alice;
GRANT ALL ON mydb.* TO admin;
GRANT REFERENCES ON mydb.* TO developer;
```

### REVOKE

Remove privileges.

```sql
REVOKE privilege_list ON database.table FROM username;
```

**Example:**
```sql
REVOKE DELETE ON mydb.users FROM alice;
REVOKE ALL ON mydb.* FROM admin;
```

### CREATE ROLE

Create a role (v3.2.0+).

```sql
CREATE ROLE role_name [DESCRIPTION 'description'];
```

**Example:**
```sql
CREATE ROLE readonly DESCRIPTION 'Read-only database access';
CREATE ROLE developer DESCRIPTION 'Full development access';
```

### DROP ROLE

Delete a role.

```sql
DROP ROLE role_name;
```

### GRANT ROLE

Assign role to user.

```sql
GRANT ROLE role_name TO username;
```

**Example:**
```sql
GRANT ROLE readonly TO alice;
```

### REVOKE ROLE

Remove role from user.

```sql
REVOKE ROLE role_name FROM username;
```

### SHOW GRANTS

Display user privileges.

```sql
SHOW GRANTS [FOR username];
```

## TCL Commands

### BEGIN

Start a transaction.

```sql
BEGIN [TRANSACTION];
```

### COMMIT

Commit transaction.

```sql
COMMIT;
```

### ROLLBACK

Rollback transaction.

```sql
ROLLBACK;
```

**Example:**
```sql
BEGIN;
INSERT INTO users VALUES (1, 'Alice', 'alice@example.com');
INSERT INTO orders VALUES (1, 1, 100.00);
COMMIT;
```

## Query Operations

### EXPLAIN

Show query execution plan (v3.2.0+).

```sql
EXPLAIN select_statement;
EXPLAIN CACHE;  -- Show plan cache statistics
```

**Example:**
```sql
EXPLAIN SELECT * FROM users WHERE age > 25;
EXPLAIN SELECT * FROM users WHERE id IN (SELECT user_id FROM orders);
```

### ANALYZE

Update table statistics.

```sql
ANALYZE TABLE table_name;
```

### DESCRIBE

Show table structure.

```sql
DESCRIBE table_name;
```

### SHOW

Display database information.

```sql
SHOW DATABASES;
SHOW TABLES;
SHOW USERS;
SHOW VIEWS;  -- v3.2.0+
SHOW ROLES;   -- v3.2.0+
SHOW GRANTS [FOR username];
```

## Functions

### Aggregate Functions

| Function | Description | Example |
|----------|-------------|---------|
| `COUNT(*)` | Count rows | `SELECT COUNT(*) FROM users` |
| `COUNT(column)` | Count non-null | `SELECT COUNT(email) FROM users` |
| `SUM(column)` | Sum values | `SELECT SUM(total) FROM orders` |
| `AVG(column)` | Average | `SELECT AVG(age) FROM users` |
| `MIN(column)` | Minimum | `SELECT MIN(age) FROM users` |
| `MAX(column)` | Maximum | `SELECT MAX(age) FROM users` |

### String Functions

| Function | Description | Example |
|----------|-------------|---------|
| `CONCAT(s1, s2)` | Concatenate | `SELECT CONCAT(first_name, ' ', last_name)` |
| `UPPER(s)` | Uppercase | `SELECT UPPER(name) FROM users` |
| `LOWER(s)` | Lowercase | `SELECT LOWER(email) FROM users` |
| `LENGTH(s)` | String length | `SELECT LENGTH(name) FROM users` |
| `SUBSTRING(s, start, len)` | Extract substring | `SELECT SUBSTRING(name, 1, 3)` |
| `TRIM(s)` | Remove whitespace | `SELECT TRIM(name) FROM users` |

### Numeric Functions

| Function | Description | Example |
|----------|-------------|---------|
| `ABS(n)` | Absolute value | `SELECT ABS(-10)` |
| `ROUND(n, d)` | Round to d decimals | `SELECT ROUND(3.14159, 2)` |
| `CEIL(n)` | Round up | `SELECT CEIL(3.2)` |
| `FLOOR(n)` | Round down | `SELECT FLOOR(3.8)` |
| `MOD(n, m)` | Modulo | `SELECT MOD(10, 3)` |

### Date/Time Functions

| Function | Description | Example |
|----------|-------------|---------|
| `CURRENT_TIMESTAMP` | Current datetime | `SELECT CURRENT_TIMESTAMP` |
| `NOW()` | Current datetime | `SELECT NOW()` |
| `DATE(timestamp)` | Extract date | `SELECT DATE(created_at)` |
| `YEAR(timestamp)` | Extract year | `SELECT YEAR(created_at)` |
| `MONTH(timestamp)` | Extract month | `SELECT MONTH(created_at)` |
| `DAY(timestamp)` | Extract day | `SELECT DAY(created_at)` |

### JSON Functions (v3.2.0+)

| Function | Description | Example |
|----------|-------------|---------|
| `JSON_EXTRACT(json, path)` | Extract value | `SELECT JSON_EXTRACT(metadata, '$.city')` |
| `JSON_EXTRACT_TEXT(json, path)` | Extract as text | `SELECT JSON_EXTRACT_TEXT(metadata, '$.city')` |

## Constraints

### PRIMARY KEY

Unique identifier for rows.

```sql
CREATE TABLE users (
    id INT PRIMARY KEY,
    ...
);
```

### UNIQUE

Ensure column values are unique.

```sql
CREATE TABLE users (
    email TEXT UNIQUE,
    ...
);

-- Multi-column unique
CREATE TABLE orders (
    user_id INT,
    order_number INT,
    UNIQUE (user_id, order_number)
);
```

### NOT NULL

Require non-null values.

```sql
CREATE TABLE users (
    name TEXT NOT NULL,
    ...
);
```

### CHECK (v3.2.0+)

Validate data with expressions.

```sql
CREATE TABLE users (
    age INT CHECK (age >= 18),
    status TEXT CHECK (status IN ('active', 'inactive')),
    email TEXT CHECK (email LIKE '%@%'),
    ...
);

-- Table-level CHECK
CREATE TABLE products (
    price FLOAT,
    cost FLOAT,
    CHECK (price >= cost)
);
```

**Supported operators:**
- Comparison: `=`, `!=`, `<>`, `<`, `>`, `<=`, `>=`
- Range: `BETWEEN ... AND ...`
- Set: `IN (...)`
- Pattern: `LIKE` (with `%` and `_`)
- Null: `IS NULL`, `IS NOT NULL`

### FOREIGN KEY (v3.2.0+)

Maintain referential integrity.

```sql
CREATE TABLE orders (
    id INT PRIMARY KEY,
    user_id INT REFERENCES users(id),
    ...
);

-- With ON DELETE/UPDATE actions
CREATE TABLE orders (
    id INT PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    ...
);
```

**Actions:**
- `CASCADE`: Propagate changes
- `SET NULL`: Set to NULL
- `RESTRICT`: Prevent changes
- `NO ACTION`: Same as RESTRICT

### DEFAULT

Set default value.

```sql
CREATE TABLE users (
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'active',
    ...
);
```

## Operators

### Comparison Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `=` | Equal | `age = 25` |
| `!=`, `<>` | Not equal | `status != 'inactive'` |
| `<` | Less than | `age < 18` |
| `>` | Greater than | `age > 65` |
| `<=` | Less than or equal | `age <= 100` |
| `>=` | Greater than or equal | `age >= 0` |
| `IS NULL` | Is null | `email IS NULL` |
| `IS NOT NULL` | Is not null | `email IS NOT NULL` |
| `BETWEEN` | In range | `age BETWEEN 18 AND 65` |
| `IN` | In set | `status IN ('active', 'pending')` |
| `LIKE` | Pattern match | `name LIKE 'A%'` |

### Logical Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `AND` | Both conditions | `age > 18 AND status = 'active'` |
| `OR` | Either condition | `status = 'active' OR status = 'pending'` |
| `NOT` | Negation | `NOT status = 'inactive'` |

### JSON Operators (v3.2.0+)

| Operator | Description | Example |
|----------|-------------|---------|
| `->` | Extract JSON value | `metadata->city` |
| `->>` | Extract as text | `metadata->>city` |

## Backup Commands

### BACKUP

Create database backup.

```sql
BACKUP DATABASE database_name TO '/path/to/backup';
BACKUP DATABASE database_name TO '/path/to/backup' WITH ENCRYPTION 'password';
BACKUP DATABASE database_name TO '/path/to/backup' WITH COMPRESSION gzip;
BACKUP DATABASE database_name TO '/path/to/backup' 
    WITH ENCRYPTION 'password' COMPRESSION lz4 LEVEL 9;
```

### RESTORE

Restore from backup.

```sql
RESTORE DATABASE database_name FROM '/path/to/backup';
RESTORE DATABASE database_name FROM '/path/to/backup' WITH ENCRYPTION 'password';
```

## Examples

### Complex Query Examples

**Join with subquery:**
```sql
SELECT u.name, o.total
FROM users u
JOIN (
    SELECT user_id, SUM(total) as total
    FROM orders
    WHERE created_at > '2024-01-01'
    GROUP BY user_id
) o ON u.id = o.user_id
WHERE o.total > 1000;
```

**Correlated subquery with EXISTS:**
```sql
SELECT name FROM users u
WHERE EXISTS (
    SELECT 1 FROM orders o
    WHERE o.user_id = u.id
    AND o.total > (SELECT AVG(total) FROM orders)
);
```

**JSON filtering:**
```sql
SELECT * FROM events
WHERE metadata->type = 'purchase'
AND (metadata->amount)::FLOAT > 100;
```

**Full-text search with ranking:**
```sql
SELECT title, MATCH(content) AGAINST('database') as relevance
FROM articles
WHERE MATCH(content) AGAINST('database')
ORDER BY relevance DESC
LIMIT 10;
```
