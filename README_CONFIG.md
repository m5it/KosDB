# KosDB Configuration Guide

Complete reference for KosDB configuration options.

## Configuration File Structure

```json
{
  "version": "3.2.0",
  "server": { ... },
  "database": { ... },
  "tls": { ... },
  "security": { ... },
  "authentication": { ... },
  "authorization": { ... },
  "replication": { ... },
  "audit_logging": { ... },
  "performance": { ... },
  "gpu": { ... },
  "optimizer": { ... },
  "metrics": { ... },
  "monitoring": { ... },
  "backup": { ... }
}
```

## Core Settings

### version
- **Type**: string
- **Required**: Yes
- **Description**: Configuration version. Must match server version.
- **Example**: `"3.2.0"`

### server

Server network and connection settings.

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 9999,
    "data_dir": "./data",
    "max_connections": 100,
    "connection_timeout": 300,
    "request_timeout": 60
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `host` | string | `"0.0.0.0"` | Bind address |
| `port` | int | `9999` | TCP port |
| `data_dir` | string | `"./data"` | Database files directory |
| `max_connections` | int | `100` | Maximum concurrent connections |
| `connection_timeout` | int | `300` | Connection idle timeout (seconds) |
| `request_timeout` | int | `60` | Request processing timeout (seconds) |

### database

Database engine and storage settings.

```json
{
  "database": {
    "engine": "leveldb",
    "compression": true,
    "compression_algorithm": "snappy",
    "cache_size_mb": 256,
    "write_buffer_mb": 64,
    "max_open_files": 1000,
    "encryption": {
      "enabled": false,
      "algorithm": "AES-256-GCM",
      "key_derivation": "PBKDF2",
      "iterations": 100000,
      "passphrase_env": "KOSDB_ENCRYPTION_PASSPHRASE"
    }
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `engine` | string | `"leveldb"` | Storage engine (leveldb) |
| `compression` | bool | `true` | Enable compression |
| `compression_algorithm` | string | `"snappy"` | Compression type (snappy, zlib) |
| `cache_size_mb` | int | `256` | Block cache size |
| `write_buffer_mb` | int | `64` | Write buffer size |
| `max_open_files` | int | `1000` | Maximum open file handles |

#### Encryption Settings

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | `false` | Enable at-rest encryption |
| `algorithm` | string | `"AES-256-GCM"` | Encryption algorithm |
| `key_derivation` | string | `"PBKDF2"` | Key derivation function |
| `iterations` | int | `100000` | PBKDF2 iterations |
| `passphrase` | string | - | Encryption passphrase (use env var) |
| `passphrase_env` | string | - | Environment variable for passphrase |
| `key_file` | string | - | Path to key file |

## Security Settings

### tls

TLS/SSL configuration.

```json
{
  "tls": {
    "enabled": false,
    "cert_file": "/etc/kosdb/server.crt",
    "key_file": "/etc/kosdb/server.key",
    "ca_file": "/etc/kosdb/ca.crt",
    "client_auth": false,
    "protocols": ["TLSv1.2", "TLSv1.3"],
    "ciphers": "HIGH:!aNULL:!MD5"
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | `false` | Enable TLS |
| `cert_file` | string | - | Server certificate file |
| `key_file` | string | - | Server private key file |
| `ca_file` | string | - | CA certificate file |
| `client_auth` | bool | `false` | Require client certificates |
| `protocols` | array | `["TLSv1.2", "TLSv1.3"]` | Allowed TLS versions |
| `ciphers` | string | `"HIGH:!aNULL:!MD5"` | Cipher suite selection |

### security

General security settings.

```json
{
  "security": {
    "require_authentication": true,
    "min_password_length": 8,
    "password_hash_algorithm": "bcrypt",
    "password_hash_rounds": 12,
    "session_timeout": 3600,
    "max_failed_logins": 5,
    "lockout_duration": 300
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `require_authentication` | bool | `true` | Require login |
| `min_password_length` | int | `8` | Minimum password length |
| `password_hash_algorithm` | string | `"bcrypt"` | Hash algorithm |
| `password_hash_rounds` | int | `12` | Bcrypt cost factor |
| `session_timeout` | int | `3600` | Session TTL (seconds) |
| `max_failed_logins` | int | `5` | Failed attempts before lockout |
| `lockout_duration` | int | `300` | Account lockout duration |

## Authentication & Authorization

### authentication

Authentication methods configuration.

```json
{
  "authentication": {
    "methods": ["password", "jwt"],
    "jwt": {
      "enabled": true,
      "secret_env": "KOSDB_JWT_SECRET",
      "algorithm": "HS256",
      "expiration": 3600
    },
    "ldap": {
      "enabled": false,
      "server": "ldap://localhost:389",
      "bind_dn": "cn=admin,dc=example,dc=com",
      "base_dn": "dc=example,dc=com",
      "user_filter": "(uid={username})"
    }
  }
}
```

### authorization

RBAC configuration.

```json
{
  "authorization": {
    "enabled": true,
    "default_role": "readonly",
    "cache_ttl": 300,
    "column_level_security": true
  }
}
```

## Replication Settings

### replication

Master-slave and master-master replication.

```json
{
  "replication": {
    "enabled": false,
    "role": "master",
    "server_id": 1,
    "binlog": {
      "enabled": true,
      "format": "row",
      "retention_days": 7
    },
    "slaves": [
      {
        "host": "slave1.example.com",
        "port": 9999,
        "user": "replica",
        "password_env": "REPLICA_PASSWORD"
      }
    ],
    "master": {
      "host": "master.example.com",
      "port": 9999,
      "user": "replica",
      "password_env": "REPLICA_PASSWORD"
    },
    "sync_replication": false,
    "replication_timeout": 30
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | `false` | Enable replication |
| `role` | string | `"master"` | Server role (master/slave) |
| `server_id` | int | `1` | Unique server ID |
| `sync_replication` | bool | `false` | Synchronous replication |
| `replication_timeout` | int | `30` | Replication timeout (seconds) |

## Audit Logging

### audit_logging

Comprehensive operation logging.

```json
{
  "audit_logging": {
    "enabled": true,
    "log_dir": "./audit_logs",
    "log_format": "json",
    "max_size_mb": 100,
    "max_age_days": 30,
    "max_backups": 10,
    "compress_backups": true,
    "targets": ["file", "syslog"],
    "syslog": {
      "address": "localhost:514",
      "protocol": "udp",
      "facility": "local0"
    },
    "webhook": {
      "url": "https://logs.example.com/webhook",
      "headers": {
        "Authorization": "Bearer token"
      }
    },
    "log_commands": ["SELECT", "INSERT", "UPDATE", "DELETE"],
    "exclude_commands": ["PING", "SHOW STATUS"],
    "mask_commands": ["CREATE USER", "ALTER USER"],
    "mask_fields": ["password", "secret", "token"]
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | `true` | Enable audit logging |
| `log_dir` | string | `"./audit_logs"` | Log file directory |
| `log_format` | string | `"json"` | Log format (json/csv) |
| `max_size_mb` | int | `100` | Max log file size |
| `max_age_days` | int | `30` | Log retention |
| `targets` | array | `["file"]` | Output targets |

## Performance Settings

### performance

Query execution and caching.

```json
{
  "performance": {
    "query_cache": {
      "enabled": true,
      "size_mb": 64,
      "ttl_seconds": 300
    },
    "connection_pool": {
      "min_size": 5,
      "max_size": 20,
      "max_idle_time": 300
    },
    "parallel_execution": {
      "enabled": true,
      "max_workers": 4,
      "min_rows_for_parallel": 10000
    },
    "slow_query_threshold_ms": 1000,
    "log_slow_queries": true
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `query_cache.enabled` | bool | `true` | Enable result caching |
| `query_cache.size_mb` | int | `64` | Cache size |
| `slow_query_threshold_ms` | int | `1000` | Slow query threshold |

## GPU Acceleration

### gpu

CUDA GPU acceleration settings.

```json
{
  "gpu": {
    "enabled": false,
    "device_id": 0,
    "memory_fraction": 0.8,
    "kernels": ["vector_ops", "matrix_mult", "sort"],
    "min_rows_for_gpu": 10000,
    "batch_size": 1024
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | `false` | Enable GPU |
| `device_id` | int | `0` | CUDA device ID |
| `memory_fraction` | float | `0.8` | GPU memory fraction |
| `min_rows_for_gpu` | int | `10000` | Minimum rows for GPU |

## Query Optimizer (New in v3.2.0)

### optimizer

Query plan caching and optimization.

```json
{
  "optimizer": {
    "enabled": true,
    "cache_size": 100,
    "collect_statistics": true,
    "statistics_ttl": 3600,
    "enable_semi_join": true,
    "enable_index_advisor": true,
    "cost_model": "hybrid",
    "plan_cache": {
      "enabled": true,
      "max_size": 100,
      "eviction_policy": "lru"
    }
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | `true` | Enable optimizer |
| `cache_size` | int | `100` | Plan cache entries |
| `collect_statistics` | bool | `true` | Auto-collect statistics |
| `statistics_ttl` | int | `3600` | Statistics TTL (seconds) |
| `enable_semi_join` | bool | `true` | Semi-join optimization |
| `enable_index_advisor` | bool | `true` | Index recommendations |
| `cost_model` | string | `"hybrid"` | Cost model type |

## Metrics and Monitoring (New in v3.2.0)

### metrics

Prometheus-compatible metrics.

```json
{
  "metrics": {
    "enabled": true,
    "host": "0.0.0.0",
    "port": 9090,
    "collection_interval": 15,
    "retention_days": 30,
    "endpoints": {
      "metrics": "/metrics",
      "health": "/health",
      "status": "/status"
    },
    "collectors": {
      "query_metrics": true,
      "cache_metrics": true,
      "connection_metrics": true,
      "replication_metrics": true,
      "storage_metrics": true
    }
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | `true` | Enable metrics |
| `host` | string | `"0.0.0.0"` | Bind address |
| `port` | int | `9090` | HTTP port |
| `collection_interval` | int | `15` | Collection interval (seconds) |
| `retention_days` | int | `30` | Data retention |

### monitoring

Health monitoring and alerts.

```json
{
  "monitoring": {
    "enabled": true,
    "health_check_interval": 30,
    "slow_query_threshold_ms": 1000,
    "alert_webhook": "https://alerts.example.com/webhook",
    "metrics_retention_hours": 168
  }
}
```

## Backup Settings

### backup

Backup and recovery configuration.

```json
{
  "backup": {
    "enabled": true,
    "backup_dir": "./backups",
    "schedule": "0 2 * * *",
    "retention_count": 7,
    "compression": "gzip",
    "compression_level": 6,
    "encryption": {
      "enabled": true,
      "algorithm": "AES-256-GCM",
      "passphrase_env": "KOSDB_BACKUP_PASSPHRASE"
    },
    "verify_backups": true,
    "notify_on_failure": true,
    "notification_email": "admin@example.com"
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | `true` | Enable scheduled backups |
| `schedule` | string | `"0 2 * * *"` | Cron schedule |
| `retention_count` | int | `7` | Backup retention count |
| `compression` | string | `"gzip"` | Compression algorithm |
| `verify_backups` | bool | `true` | Verify after backup |

## Environment Variables

Sensitive values should use environment variables:

| Variable | Description | Used In |
|----------|-------------|---------|
| `KOSDB_ENCRYPTION_PASSPHRASE` | Database encryption key | `database.encryption` |
| `KOSDB_TLS_PASSWORD` | TLS key password | `tls` |
| `KOSDB_JWT_SECRET` | JWT signing key | `authentication.jwt` |
| `KOSDB_BACKUP_PASSPHRASE` | Backup encryption key | `backup.encryption` |
| `KOSDB_ADMIN_PASSWORD` | Initial admin password | Setup |

## Complete Example Configuration

```json
{
  "version": "3.2.0",
  "server": {
    "host": "0.0.0.0",
    "port": 9999,
    "data_dir": "./data",
    "max_connections": 100
  },
  "database": {
    "engine": "leveldb",
    "compression": true,
    "cache_size_mb": 256,
    "encryption": {
      "enabled": true,
      "passphrase_env": "KOSDB_ENCRYPTION_PASSPHRASE"
    }
  },
  "tls": {
    "enabled": true,
    "cert_file": "/etc/kosdb/server.crt",
    "key_file": "/etc/kosdb/server.key",
    "client_auth": false
  },
  "security": {
    "require_authentication": true,
    "min_password_length": 12
  },
  "audit_logging": {
    "enabled": true,
    "log_dir": "./audit_logs",
    "max_size_mb": 100,
    "targets": ["file"]
  },
  "performance": {
    "query_cache": {
      "enabled": true,
      "size_mb": 64
    }
  },
  "optimizer": {
    "enabled": true,
    "cache_size": 100,
    "enable_semi_join": true
  },
  "metrics": {
    "enabled": true,
    "port": 9090,
    "collection_interval": 15
  },
  "backup": {
    "enabled": true,
    "backup_dir": "./backups",
    "schedule": "0 2 * * *",
    "retention_count": 7
  }
}
```

## Validation

Validate your configuration:

```bash
# Start server with config validation
python server.py -c config.json --validate

# Test configuration without starting server
python server.py -c config.json --check-config
```

## Troubleshooting

### Configuration Errors

**"Unknown configuration option"**
- Check `version` matches server version
- Verify option name spelling
- See this guide for valid options

**"Invalid value for option"**
- Check data type (string, int, bool, array)
- Verify enum values are valid
- Ensure file paths exist

**"Missing required option"**
- Check all required sections are present
- Verify `version` is set
- Ensure `server.data_dir` exists

### Performance Issues

**High memory usage**
- Reduce `database.cache_size_mb`
- Lower `optimizer.cache_size`
- Decrease `performance.query_cache.size_mb`

**Slow queries**
- Enable `optimizer.collect_statistics`
- Increase `database.cache_size_mb`
- Check `optimizer.enable_semi_join` is true
