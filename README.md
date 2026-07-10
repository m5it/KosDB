# KosDB v3.1.0

A high-performance, feature-rich LevelDB-based database server with SQL-like interface, replication, TLS encryption, GPU acceleration, and comprehensive audit logging.

## Features

### Core Database
- **SQL-like Interface**: Familiar CREATE, INSERT, SELECT, UPDATE, DELETE commands
- **Multiple Databases**: Support for multiple named databases
- **Table Schema**: Define columns with types (INT, TEXT, FLOAT, etc.)
- **Transactions**: ACID-compliant operations
- **Indexing**: Primary and secondary index support

### Security (New in v3.1.0)
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
- **Granular Permissions**: SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, INDEX, ADMIN
- **Column-level Security**: Restrict access to specific columns
- **Session Management**: JWT-based sessions with TTL

### Replication & High Availability
- **Master-Slave Replication**: Automatic failover support
- **Master-Master Replication**: Multi-master with conflict resolution
- **Async Replication**: Non-blocking replication
- **Replication Lag Monitoring**: Track replication health

### Performance Features
- **GPU Acceleration**: CUDA-powered query processing
  - Vector operations
  - Matrix multiplication
  - Sorting algorithms
- **Connection Pooling**: Efficient connection management
- **Query Caching**: Result cache for frequent queries
- **Compression**: Multiple algorithms (gzip, lz4, zstd)

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
  "version": "3.1.0",
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
-- Create table
CREATE TABLE users (
    id INT PRIMARY KEY,
    name TEXT,
    email TEXT,
    age INT
);

-- Describe table
DESCRIBE users;

-- Drop table
DROP TABLE users;
```

### Data Operations

```sql
-- Insert
INSERT INTO users VALUES (1, 'Alice', 'alice@example.com', 30);

-- Select
SELECT * FROM users;
SELECT name, email FROM users WHERE age > 25;
SELECT * FROM users WHERE name LIKE 'A%';

-- Update
UPDATE users SET age = 31 WHERE id = 1;

-- Delete
DELETE FROM users WHERE id = 1;
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

### Backup Operations

```sql
-- Backup with encryption
BACKUP DATABASE mydb TO /backups/mydb.backup WITH ENCRYPTION 'mypassword' COMPRESSION gzip;

-- Restore with encryption
RESTORE DATABASE mydb FROM /backups/mydb.backup WITH ENCRYPTION 'mypassword';
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
# Check server health
python cli.py -c "SHOW STATUS"
```

### Metrics

Enable Prometheus metrics:
```json
{
  "monitoring": {
    "enabled": true,
    "metrics_port": 9090,
    "prometheus_enabled": true
  }
}
```

Access metrics at `http://localhost:9090/metrics`

## Troubleshooting

### Connection Issues

- Verify server is running: `python cli.py -c "PING"`
- Check firewall rules for port 9999
- Verify TLS certificates are valid

### Performance Issues

- Check query cache hit rate
- Monitor replication lag
- Review slow query log

### Encryption Issues

- Verify passphrase is correct
- Check key file permissions (should be 600)
- Ensure cryptography library is installed

## API Reference

See [API Documentation](docs/API.md) for detailed command reference.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history.
