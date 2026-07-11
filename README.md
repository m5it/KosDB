# KosDB v3.4.0

A high-performance, feature-rich LevelDB-based database server with SQL-like interface, replication, TLS encryption, GPU acceleration, comprehensive audit logging, advanced query capabilities, window functions, CTEs, prepared statements, and automated event scheduling.

## Features

### Core Database
- **SQL-like Interface**: Familiar CREATE, INSERT, SELECT, UPDATE, DELETE commands
- **Multiple Databases**: Support for multiple named databases
- **Table Schema**: Define columns with types (INT, TEXT, FLOAT, JSON, etc.)
- **Transactions**: ACID-compliant operations with BEGIN, COMMIT, ROLLBACK
- **Indexing**: Primary, secondary, and full-text index support
- **Views**: Virtual tables based on SELECT queries
- **Subqueries**: Scalar, IN/NOT IN, EXISTS/NOT EXISTS, correlated subqueries

### Event Scheduler (New in v3.4.0)
- **Automated Tasks**: Schedule recurring and one-time events
- **Cron-like Scheduling**: EVERY 1 DAY, EVERY 1 HOUR, AT specific timestamp
- **Event History**: Track execution history with 10,000 entry limit
- **Failure Handling**: Automatic retries with configurable limits
- **Event Management**: CREATE EVENT, ALTER EVENT, DROP EVENT, ENABLE/DISABLE

### Advanced SQL (v3.3.0+)
- **Window Functions**: ROW_NUMBER, RANK, DENSE_RANK, LEAD, LAG, FIRST_VALUE, LAST_VALUE
- **Common Table Expressions (CTEs)**: Recursive and non-recursive WITH clauses
- **Prepared Statements**: PREPARE, EXECUTE, DEALLOCATE with parameter binding
- **SQL Injection Prevention**: Secure parameter binding with proper escaping

### Security (v3.1.0+)
- **TLS/SSL Encryption**: Secure client-server communication
  - Certificate-based authentication
  - Self-signed certificate generation
  - Client certificate verification (mTLS)
- **At-Rest Encryption**: AES-256-GCM database encryption
  - PBKDF2 key derivation
  - Master key rotation support
- **Audit Logging**: Comprehensive operation logging
  - Multiple output targets (file, syslog, webhook)
  - Log rotation and compression
  - Sensitive command masking

### Authentication & Authorization
- **Database-backed Authentication**: Username/password with bcrypt hashing
- **Role-Based Access Control (RBAC)**: Create roles and assign to users
- **Granular Permissions**: SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, INDEX, REFERENCES, ADMIN
- **Column-level Security**: Restrict access to specific columns
- **Session Management**: JWT-based sessions with TTL

### Replication & High Availability
- **Master-Slave Replication**: Automatic failover support
- **Master-Master Replication**: Multi-master with conflict resolution
- **Async Replication**: Non-blocking replication
- **Replication Lag Monitoring**: Track replication health

### Query Optimization (v3.2.0+)
- **Query Plan Caching**: LRU cache for parsed execution plans
- **Cost-Based Optimizer**: Statistics-driven plan selection
- **Semi-Join Optimization**: Efficient IN/EXISTS subquery execution
- **Index Advisor**: Automatic index recommendations
- **Query Statistics**: Execution metrics and profiling

### Advanced SQL (v3.2.0+)
- **CHECK Constraints**: Data validation with complex expressions
- **Foreign Keys**: Referential integrity with CASCADE/SET NULL/RESTRICT
- **ALTER TABLE**: Add/drop/modify columns, indexes, constraints
- **JSON Support**: Native JSON columns with path extraction
- **Full-Text Search**: MATCH ... AGAINST syntax with relevance scoring
- **Subqueries**: Scalar, IN, EXISTS, correlated subqueries

### Performance Features
- **GPU Acceleration**: CUDA-powered query processing
  - Vector operations
  - Matrix multiplication
  - Sorting algorithms
- **Connection Pooling**: Efficient connection management
- **Query Caching**: Result cache for frequent queries
- **Plan Caching**: Execution plan cache for repeated queries
- **Compression**: Multiple algorithms (gzip, lz4, zstd)

### Monitoring (v3.2.0+)
- **Prometheus Metrics**: Query counts, latency, cache hit rates
- **Health Checks**: Liveness and readiness endpoints
- **Detailed Status**: Server status via HTTP API
- **Cache Statistics**: Plan cache performance metrics

### Backup & Recovery
- **Hot Backups**: Non-blocking backup operations
- **Encrypted Backups**: Password-protected backup files
- **Compression Options**: gzip, lz4, zstd
- **Point-in-Time Recovery**: Restore to specific timestamp
- **Integrity Verification**: SHA-256 checksums

## Quick Start

### Installation

```bash
# Clone repository
git clone https://github.com/yourusername/kosdb.git
cd kosdb

# Install dependencies
pip install -r requirements.txt

# Optional: Install GPU support
pip install pycuda  # For CUDA acceleration

# Optional: Install encryption
pip install cryptography  # For TLS and at-rest encryption
```

### Basic Usage

```bash
# Start server with default config
python server.py

# Or specify configuration file
python server.py -c config.json

# Create admin user
python server.py --prepare_admin admin --prepare_password secret123
```

### Client Connection

```bash
# Connect with CLI client
python cli.py -H localhost -p 9999 -u admin -P secret123

# Or use with TLS
python cli.py -H localhost -p 9999 --tls --ca-cert ca.crt -u admin -P secret123
```

## Configuration

### Basic Configuration (config.json)

```json
{
  "version": "3.4.0",
  "server": {
    "host": "0.0.0.0",
    "port": 9999,
    "data_dir": "./data"
  },
  "database": {
    "engine": "leveldb",
    "compression": true
  }
}
```

### TLS Configuration

```json
{
  "tls": {
    "enabled": true,
    "cert_file": "/etc/kosdb/server.crt",
    "key_file": "/etc/kosdb/server.key",
    "ca_file": "/etc/kosdb/ca.crt",
    "client_auth": true
  }
}
```

### Event Scheduler Configuration (New in v3.4.0)

```json
{
  "event_scheduler": {
    "enabled": true,
    "check_interval": 60,
    "max_history_entries": 10000,
    "default_max_retries": 3,
    "retry_delay_seconds": 300
  }
}
```

### Metrics and Monitoring (v3.2.0+)

```json
{
  "metrics": {
    "enabled": true,
    "host": "0.0.0.0",
    "port": 9090,
    "collection_interval": 15,
    "retention_days": 30
  }
}
```

Access metrics at:
- `http://localhost:9090/metrics` - Prometheus format
- `http://localhost:9090/health` - Health checks
- `http://localhost:9090/status` - Detailed status

### Query Optimizer Configuration (v3.2.0+)

```json
{
  "optimizer": {
    "enabled": true,
    "cache_size": 100,
    "collect_statistics": true,
    "enable_semi_join": true
  }
}
```

### Prepared Statement Configuration (v3.3.0+)

```json
{
  "prepared_statements": {
    "cache_size": 100,
    "max_parameters": 100,
    "parameter_style": "named"
  }
}
```

### Audit Logging Configuration

```json
{
  "audit_logging": {
    "enabled": true,
    "log_dir": "./audit_logs",
    "max_size_mb": 100,
    "max_age_days": 30,
    "targets": ["file", "syslog"],
    "exclude_commands": ["PING"],
    "mask_commands": ["PASS", "PASSWORD"]
  }
}
```

### GPU Configuration

```json
{
  "gpu": {
    "enabled": true,
    "device_id": 0,
    "memory_fraction": 0.8,
    "kernels": ["vector_ops", "matrix_mult", "sort"]
  }
}
```

See [Configuration Guide](README_CONFIG.md) for complete documentation.

## SQL Commands

### Database Operations

```sql
-- Create database
CREATE DATABASE mydb;

-- Use database
USE mydb;

-- Drop database
DROP DATABASE mydb;
```

### Table Operations

```sql
-- Create table with constraints
CREATE TABLE users (
    id INT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    age INT CHECK (age >= 18),
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create table with foreign key
CREATE TABLE orders (
    id INT PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    total FLOAT CHECK (total > 0),
    status TEXT CHECK (status IN ('pending', 'shipped', 'delivered'))
);

-- Describe table
DESCRIBE users;

-- Drop table
DROP TABLE users;
```

### ALTER TABLE (v3.2.0+)

```sql
-- Add column
ALTER TABLE users ADD COLUMN phone TEXT;

-- Add column with constraints
ALTER TABLE users ADD COLUMN status TEXT CHECK (status IN ('active', 'inactive'));

-- Drop column
ALTER TABLE users DROP COLUMN phone;

-- Drop column with CASCADE
ALTER TABLE users DROP COLUMN email CASCADE;

-- Modify column type
ALTER TABLE users MODIFY COLUMN age FLOAT;

-- Rename column
ALTER TABLE users RENAME COLUMN name TO full_name;

-- Add index
ALTER TABLE users ADD INDEX idx_email (email);

-- Drop index
ALTER TABLE users DROP INDEX idx_email;

-- Add foreign key constraint
ALTER TABLE orders ADD CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(id);

-- Add CHECK constraint
ALTER TABLE users ADD CONSTRAINT chk_age CHECK (age >= 18);

-- Drop constraint
ALTER TABLE users DROP CONSTRAINT chk_age;
```

### Data Operations

```sql
-- Insert
INSERT INTO users VALUES (1, 'Alice', 'alice@example.com', 30, '{"city": "NYC"}');

-- Insert with JSON
INSERT INTO users VALUES (2, 'Bob', 'bob@example.com', 25, '{"city": "LA", "hobbies": ["reading"]}');

-- Select
SELECT * FROM users;
SELECT name, email FROM users WHERE age > 25;
SELECT * FROM users WHERE name LIKE 'A%';

-- JSON extraction
SELECT name, metadata->city FROM users;
SELECT name, metadata->>city FROM users;  -- As text

-- Update
UPDATE users SET age = 31 WHERE id = 1;

-- Delete
DELETE FROM users WHERE id = 1;
```

### Event Scheduler (New in v3.4.0)

```sql
-- Create recurring event (runs every day at 2 AM)
CREATE EVENT daily_cleanup
ON SCHEDULE EVERY 1 DAY
STARTS '2024-01-01 02:00:00'
DO DELETE FROM logs WHERE created_at < DATE_SUB(NOW(), INTERVAL 30 DAY);

-- Create event with interval
CREATE EVENT hourly_stats
ON SCHEDULE EVERY 1 HOUR
DO INSERT INTO stats_summary SELECT COUNT(*) FROM events;

-- Create one-time event
CREATE EVENT one_time_backup
ON SCHEDULE AT '2024-12-25 02:00:00'
DO CALL backup_database();

-- Create event with error handling
CREATE EVENT retryable_task
ON SCHEDULE EVERY 30 MINUTE
ON COMPLETION PRESERVE
DO CALL process_queue();

-- Enable/Disable events
ALTER EVENT daily_cleanup DISABLE;
ALTER EVENT daily_cleanup ENABLE;

-- Drop event
DROP EVENT daily_cleanup;

-- Show events
SHOW EVENTS;

-- Show event history
SHOW EVENT HISTORY daily_cleanup;

-- Show event statistics
SHOW EVENT STATUS;
```

### Subqueries (v3.2.0+)

```sql
-- Scalar subquery
SELECT name, (SELECT COUNT(*) FROM orders) as order_count FROM users;

-- IN subquery
SELECT * FROM users WHERE id IN (SELECT user_id FROM orders WHERE total > 100);

-- NOT IN subquery
SELECT * FROM users WHERE id NOT IN (SELECT user_id FROM orders);

-- EXISTS subquery
SELECT * FROM users WHERE EXISTS (SELECT 1 FROM orders WHERE orders.user_id = users.id);

-- Correlated subquery
SELECT name, (SELECT MAX(total) FROM orders WHERE orders.user_id = users.id) as max_order
FROM users;
```

### Window Functions (v3.3.0+)

```sql
-- Row number within partition
SELECT 
    name,
    dept,
    salary,
    ROW_NUMBER() OVER (PARTITION BY dept ORDER BY salary DESC) as rank_in_dept
FROM employees;

-- RANK and DENSE_RANK
SELECT 
    name,
    salary,
    RANK() OVER (ORDER BY salary DESC) as salary_rank,
    DENSE_RANK() OVER (ORDER BY salary DESC) as dense_rank
FROM employees;

-- LEAD and LAG
SELECT 
    name,
    salary,
    LAG(salary, 1, 0) OVER (ORDER BY hire_date) as prev_salary,
    LEAD(salary, 1, 0) OVER (ORDER BY hire_date) as next_salary
FROM employees;

-- FIRST_VALUE and LAST_VALUE
SELECT 
    dept,
    name,
    salary,
    FIRST_VALUE(salary) OVER (PARTITION BY dept ORDER BY hire_date) as first_salary,
    LAST_VALUE(salary) OVER (PARTITION BY dept ORDER BY hire_date) as last_salary
FROM employees;
```

### Common Table Expressions (CTEs) (v3.3.0+)

```sql
-- Simple CTE
WITH sales_summary AS (
    SELECT dept, SUM(sales) as total_sales
    FROM sales
    GROUP BY dept
)
SELECT * FROM sales_summary WHERE total_sales > 10000;

-- Multiple CTEs
WITH 
    dept_sales AS (
        SELECT dept, SUM(sales) as total
        FROM sales
        GROUP BY dept
    ),
    top_depts AS (
        SELECT dept FROM dept_sales ORDER BY total DESC LIMIT 5
    )
SELECT * FROM sales WHERE dept IN (SELECT dept FROM top_depts);

-- Recursive CTE for hierarchical data
WITH RECURSIVE employee_hierarchy AS (
    -- Anchor: top-level employees
    SELECT id, name, manager_id, 0 as level
    FROM employees
    WHERE manager_id IS NULL
    
    UNION ALL
    
    -- Recursive: employees with managers
    SELECT e.id, e.name, e.manager_id, eh.level + 1
    FROM employees e
    JOIN employee_hierarchy eh ON e.manager_id = eh.id
)
SELECT * FROM employee_hierarchy ORDER BY level, name;
```

### Prepared Statements (v3.3.0+)

```sql
-- Prepare statement with positional parameters
PREPARE get_user AS SELECT * FROM users WHERE id = ?;

-- Prepare with named parameters
PREPARE get_by_name AS 
    SELECT * FROM users WHERE name = :name AND age > :min_age;

-- Execute with positional parameters
EXECUTE get_user USING (42);

-- Execute with named parameters
EXECUTE get_by_name USING name='Alice', min_age=18;

-- Deallocate prepared statement
DEALLOCATE get_user;

-- Deallocate all prepared statements
DEALLOCATE ALL;
```

### Views (v3.2.0+)

```sql
-- Create view
CREATE VIEW active_users AS
SELECT * FROM users WHERE status = 'active';

-- Query view
SELECT * FROM active_users WHERE age > 25;

-- Drop view
DROP VIEW active_users;

-- Show views
SHOW VIEWS;
```

### Full-Text Search (v3.2.0+)

```sql
-- Create full-text index
CREATE FULLTEXT INDEX idx_content ON articles(content);

-- Search with natural language mode
SELECT * FROM articles WHERE MATCH(content) AGAINST('database optimization');

-- Search with boolean mode
SELECT * FROM articles WHERE MATCH(content) AGAINST('+database -mysql' IN BOOLEAN MODE);

-- Drop full-text index
DROP FULLTEXT INDEX idx_content ON articles;
```

### User Management

```sql
-- Create user
CREATE USER alice PASSWORD 'secret123';

-- Grant privileges
GRANT SELECT, INSERT ON mydb.users TO alice;

-- Revoke privileges
REVOKE DELETE ON mydb.users FROM alice;

-- Show grants
SHOW GRANTS FOR alice;
```

### Role Management

```sql
-- Create role
CREATE ROLE readonly DESCRIPTION 'Read-only access';

-- Grant privileges to role
GRANT SELECT ON *.* TO readonly;

-- Assign role to user
GRANT ROLE readonly TO alice;

-- Show roles
SHOW ROLES;
```

### Transactions

```sql
-- Begin transaction
BEGIN TRANSACTION;

-- Or simply
BEGIN;

-- Commit
COMMIT;

-- Rollback
ROLLBACK;
```

### Backup Operations

```sql
-- Backup with encryption
BACKUP DATABASE mydb TO /backups/mydb.backup WITH ENCRYPTION 'mypassword' COMPRESSION gzip;

-- Restore with encryption
RESTORE DATABASE mydb FROM /backups/mydb.backup WITH ENCRYPTION 'mypassword';
```

### Query Optimization (v3.2.0+)

```sql
-- Explain query plan
EXPLAIN SELECT * FROM users WHERE age > 25;

-- Show plan cache status
EXPLAIN CACHE;

-- Analyze table for statistics
ANALYZE TABLE users;
```

## Environment Variables

Sensitive configuration values can be stored in environment variables:

```bash
# Encryption passphrase
export KOSDB_ENCRYPTION_PASSPHRASE="my-secret-key"

# TLS certificate password
export KOSDB_TLS_PASSWORD="cert-password"

# Backup encryption
export KOSDB_BACKUP_PASSPHRASE="backup-secret"

# JWT secret
export KOSDB_JWT_SECRET="jwt-signing-key"
```

Reference in config.json:
```json
{
  "database": {
    "encryption": {
      "passphrase_env": "KOSDB_ENCRYPTION_PASSPHRASE"
    }
  }
}
```

## Security Hardening

### TLS Setup

1. Generate CA and server certificates:
```bash
# Generate CA
openssl req -x509 -newkey rsa:4096 -keyout ca.key -out ca.crt -days 365 -nodes

# Generate server certificate
openssl req -newkey rsa:4096 -keyout server.key -out server.csr -nodes
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt -days 365
```

2. Configure server:
```json
{
  "tls": {
    "enabled": true,
    "cert_file": "server.crt",
    "key_file": "server.key",
    "ca_file": "ca.crt",
    "client_auth": false
  }
}
```

3. Connect client with TLS:
```bash
python cli.py --tls --ca-cert ca.crt -u admin -P secret123
```

### Encryption Best Practices

1. **Use strong passphrases** (minimum 16 characters)
2. **Store keys securely** (use key files with restricted permissions)
3. **Rotate keys regularly** (use `ROTATE KEY` command)
4. **Backup keys separately** from encrypted data
5. **Enable audit logging** for encryption operations

## Performance Tuning

### GPU Acceleration

Enable GPU for large-scale operations:
```json
{
  "gpu": {
    "enabled": true,
    "device_id": 0,
    "memory_fraction": 0.8
  }
}
```

GPU-accelerated operations:
- Vector mathematical operations
- Matrix multiplication
- Large dataset sorting
- Aggregate functions

### Query Plan Caching (v3.2.0+)

```json
{
  "optimizer": {
    "cache_size": 100,
    "invalidate_on_schema_change": true
  }
}
```

### Connection Pooling

```json
{
  "performance": {
    "connection_pool_min": 5,
    "connection_pool_max": 20,
    "query_cache_size": 1000
  }
}
```

## Monitoring

### Health Check

```bash
# Check server health via HTTP
curl http://localhost:9090/health

# Check via CLI
python cli.py -c "SHOW STATUS"
```

### Metrics

Enable Prometheus metrics:
```json
{
  "metrics": {
    "enabled": true,
    "host": "0.0.0.0",
    "port": 9090,
    "prometheus_enabled": true
  }
}
```

Access metrics:
- `http://localhost:9090/metrics` - Prometheus format
- `http://localhost:9090/health` - Health status
- `http://localhost:9090/health/live` - Liveness probe
- `http://localhost:9090/health/ready` - Readiness probe
- `http://localhost:9090/status` - Detailed server status

## Troubleshooting

### Connection Issues

- Verify server is running: `python cli.py -c "PING"`
- Check firewall rules for port 9999
- Verify TLS certificates are valid

### Performance Issues

- Check query cache hit rate: `EXPLAIN CACHE`
- Monitor replication lag
- Review slow query log
- Check plan cache statistics

### Encryption Issues

- Verify passphrase is correct
- Check key file permissions (should be 600)
- Ensure cryptography library is installed

### Event Scheduler Issues

- Check event scheduler is enabled: `SHOW EVENT STATUS`
- Review event history: `SHOW EVENT HISTORY event_name`
- Check event execution logs
- Verify event schedule expressions

## Migration from v3.3 to v3.4

New in v3.4.0:
- **Event Scheduler**: Automated task scheduling
  - Add `event_scheduler` section to config.json
  - New SQL commands: CREATE EVENT, ALTER EVENT, DROP EVENT
  - New SHOW commands: SHOW EVENTS, SHOW EVENT HISTORY, SHOW EVENT STATUS

All v3.4.0 features are backward compatible with v3.3.0 databases.

See [MIGRATION_v3.3_to_v3.4.md](MIGRATION_v3.3_to_v3.4.md) for detailed migration guide.

## Migration from v3.2 to v3.3

New in v3.3.0:
- **Window Functions**: No migration needed, new SQL feature
- **CTEs**: No migration needed, new SQL feature  
- **Prepared Statements**: No migration needed, new SQL feature

All v3.3.0 features are backward compatible with v3.2.0 databases.

See [MIGRATION_v3.2_to_v3.3.md](MIGRATION_v3.2_to_v3.3.md) for detailed migration guide.

## Migration from v3.1 to v3.2

See [MIGRATION_v3.1_to_v3.2.md](MIGRATION_v3.1_to_v3.2.md) for detailed migration guide.

## API Reference

See [API Documentation](docs/API.md) for detailed command reference.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history.
