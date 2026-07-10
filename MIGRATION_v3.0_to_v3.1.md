# Migration Guide: KosDB v3.0 to v3.1.0

This guide provides step-by-step instructions for upgrading from KosDB v3.0 to v3.1.0.

## Overview

KosDB v3.1.0 introduces significant new features including:
- TLS/SSL encryption for secure connections
- GPU acceleration for high-performance queries
- Comprehensive audit logging
- Enhanced backup with encryption and compression options
- Role-based access control (RBAC)
- New JSON-based configuration system

## Prerequisites

Before starting the migration:
1. **Backup your data**: Create a full backup of your v3.0 database
2. **Review breaking changes**: See [Breaking Changes](#breaking-changes) section
3. **Check dependencies**: Ensure Python 3.8+ and new dependencies are available

## Step-by-Step Migration

### Step 1: Backup Current Data

```bash
# Stop the v3.0 server
pkill -f "python server.py"

# Create backup
python -c "
from database import Database
db = Database('./data')
print(db.backup_database('mydb', './backup_v3.0.json.gz'))
"
```

### Step 2: Update Dependencies

```bash
# Backup requirements
pip freeze > requirements_v3.0.txt

# Install new dependencies
pip install -r requirements.txt

# Optional: Install GPU support
pip install pycuda

# Optional: Install encryption support
pip install cryptography

# Optional: Install compression libraries
pip install lz4 zstandard
```

### Step 3: Create New Configuration File

Create `config.json` with your v3.0 settings:

```json
{
  "version": "3.1.0",
  "server": {
    "host": "0.0.0.0",
    "port": 9999,
    "data_dir": "./data",
    "server_id": 1
  },
  "database": {
    "engine": "leveldb",
    "cache_size_mb": 64,
    "write_buffer_mb": 16,
    "compression": true,
    "encryption": {
      "enabled": false,
      "key_file": null,
      "passphrase_env": "KOSDB_ENCRYPTION_PASSPHRASE"
    }
  },
  "tls": {
    "enabled": false,
    "cert_file": null,
    "key_file": null,
    "ca_file": null,
    "generate_self_signed": false,
    "client_auth": false
  },
  "audit_logging": {
    "enabled": false,
    "log_dir": "./audit_logs",
    "max_size_mb": 100,
    "max_age_days": 30,
    "compress": true,
    "targets": ["file"],
    "exclude_commands": ["PING", "ECHO"],
    "mask_commands": ["PASS", "PASSWORD", "SECRET"]
  },
  "replication": {
    "enabled": false,
    "role": "master",
    "master_host": null,
    "replication_port": null,
    "peer_host": null
  },
  "authentication": {
    "method": "database",
    "session_ttl_minutes": 60,
    "max_failed_attempts": 5,
    "lockout_duration_minutes": 30,
    "rbac_enabled": true
  },
  "backup": {
    "enabled": true,
    "backup_dir": "./backups",
    "auto_backup": false,
    "compression": "gzip",
    "compression_level": 6
  }
}
```

### Step 4: Migrate User Data

Users and permissions are automatically migrated on first start. However, you should verify:

```bash
# Start v3.1.0 server
python server.py -c config.json

# In another terminal, check users
python cli.py -u admin -P your_password -c "SHOW USERS"

# Verify permissions
python cli.py -u admin -P your_password -c "SHOW GRANTS FOR admin"
```

### Step 5: Update Client Connections

#### Option A: Continue Without TLS (Not Recommended)

No changes needed to client commands.

#### Option B: Enable TLS (Recommended)

1. Generate certificates (see [Security Guide](SECURITY.md))
2. Update client commands:

```bash
# Old (v3.0)
python cli.py -H localhost -p 9999 -u admin -P secret123

# New (v3.1.0 with TLS)
python cli.py -H localhost -p 9999 --tls --ca-cert ca.crt -u admin -P secret123
```

### Step 6: Enable New Features (Optional)

#### Enable Audit Logging

Update `config.json`:
```json
{
  "audit_logging": {
    "enabled": true,
    "log_dir": "./audit_logs",
    "targets": ["file"]
  }
}
```

#### Enable GPU Acceleration

Update `config.json`:
```json
{
  "gpu": {
    "enabled": true,
    "device_id": 0,
    "memory_fraction": 0.8
  }
}
```

#### Enable At-Rest Encryption

⚠️ **Warning**: This requires re-encrypting all data. Plan for downtime.

```bash
# 1. Stop server
# 2. Enable encryption in config
# 3. Start server - it will prompt for passphrase
python server.py -c config.json
```

### Step 7: Update Backup Scripts

Old backup command:
```bash
# v3.0
BACKUP DATABASE mydb TO /backups/mydb.backup
```

New backup command with encryption:
```bash
# v3.1.0
BACKUP DATABASE mydb TO /backups/mydb.backup WITH ENCRYPTION 'mypassword' COMPRESSION gzip
```

### Step 8: Test and Verify

```bash
# Test basic operations
python cli.py -c "CREATE DATABASE testdb"
python cli.py -c "USE testdb"
python cli.py -c "CREATE TABLE test (id INT, name TEXT)"
python cli.py -c "INSERT INTO test VALUES (1, 'test')"
python cli.py -c "SELECT * FROM test"

# Test backup/restore
python cli.py -c "BACKUP DATABASE testdb TO /tmp/test.backup"
python cli.py -c "RESTORE DATABASE testdb FROM /tmp/test.backup"

# Check audit logs (if enabled)
ls -la ./audit_logs/
```

## Breaking Changes

### Command Line Arguments

| Old (v3.0) | New (v3.1.0) | Notes |
|------------|--------------|-------|
| `--host` | `--host` or config | No change |
| `--port` | `--port` or config | No change |
| `--data_dir` | `--data_dir` or config | No change |
| N/A | `-c config.json` | New: Config file support |
| N/A | `--encryption-key` | New: At-rest encryption |

### SQL Commands

| Old (v3.0) | New (v3.1.0) | Notes |
|------------|--------------|-------|
| `BACKUP DATABASE db TO path` | `BACKUP DATABASE db TO path [WITH options]` | Extended syntax |
| `RESTORE DATABASE db FROM path` | `RESTORE DATABASE db FROM path [WITH options]` | Extended syntax |
| N/A | `CREATE ROLE name` | New command |
| N/A | `GRANT ROLE name TO user` | New command |
| N/A | `AUDIT LOG` | New command |

### Configuration

v3.0 used command-line arguments exclusively. v3.1.0 uses JSON configuration files.

## Rollback Procedure

If you need to rollback to v3.0:

1. Stop v3.1.0 server
2. Restore v3.0 code: `git checkout v3.0`
3. Restore v3.0 dependencies: `pip install -r requirements_v3.0.txt`
4. Start v3.0 server with original command-line arguments

## Troubleshooting

### "Config file not found"

Ensure `config.json` exists in working directory or specify path:
```bash
python server.py -c /path/to/config.json
```

### "Permission denied on audit_logs"

Create directory with correct permissions:
```bash
mkdir -p audit_logs
chmod 750 audit_logs
```

### "TLS handshake failed"

Check certificate paths and permissions:
```bash
ls -la /etc/kosdb/*.crt /etc/kosdb/*.key
openssl x509 -in server.crt -text -noout
```

### "GPU not available"

Verify CUDA installation:
```bash
nvidia-smi
python -c "import pycuda.driver as cuda; cuda.init()"
```

## Getting Help

- Review [README.md](README.md) for feature documentation
- Check [CHANGELOG.md](CHANGELOG.md) for detailed changes
- See [SECURITY.md](SECURITY.md) for security hardening
- File issues at: https://github.com/yourusername/kosdb/issues

## Post-Migration Checklist

- [ ] Server starts without errors
- [ ] Can connect with CLI client
- [ ] Can execute basic SQL commands
- [ ] Backups work correctly
- [ ] (If enabled) TLS connections succeed
- [ ] (If enabled) Audit logs are written
- [ ] (If enabled) GPU acceleration works
- [ ] Performance is acceptable
- [ ] Documentation updated for your team

---

**Congratulations!** You have successfully migrated to KosDB v3.1.0.
