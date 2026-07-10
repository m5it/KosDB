# KosDB Configuration Guide

Complete reference for KosDB v3.1.0 configuration options.

## Configuration File Structure

```json
{
  "version": "3.1.0",
  "server": { ... },
  "database": { ... },
  "tls": { ... },
  "gpu": { ... },
  "audit_logging": { ... },
  "replication": { ... },
  "authentication": { ... },
  "backup": { ... },
  "monitoring": { ... },
  "logging": { ... },
  "performance": { ... }
}
```

## Server Configuration

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 9999,
    "data_dir": "./data",
    "server_id": 1,
    "max_connections": 100,
    "connection_timeout": 30,
    "request_timeout": 60
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `host` | string | "0.0.0.0" | Bind address |
| `port` | integer | 9999 | Server port (1-65535) |
| `data_dir` | string | "./data" | Data storage directory |
| `server_id` | integer | 1 | Unique server ID |
| `max_connections` | integer | 100 | Max concurrent connections |
| `connection_timeout` | integer | 30 | Connection timeout (seconds) |
| `request_timeout` | integer | 60 | Request timeout (seconds) |

## Database Configuration

```json
{
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
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `engine` | string | "leveldb" | Database engine |
| `cache_size_mb` | integer | 64 | Cache size in MB |
| `write_buffer_mb` | integer | 16 | Write buffer size in MB |
| `compression` | boolean | true | Enable compression |
| `encryption.enabled` | boolean | false | Enable at-rest encryption |
| `encryption.key_file` | string | null | Path to key file |
| `encryption.passphrase_env` | string | "KOSDB_ENCRYPTION_PASSPHRASE" | Env var for passphrase |

## TLS Configuration

```json
{
  "tls": {
    "enabled": false,
    "cert_file": "/path/to/cert.pem",
    "key_file": "/path/to/key.pem",
    "ca_file": "/path/to/ca.pem",
    "generate_self_signed": false,
    "client_auth": false,
    "protocols": ["TLSv1.2", "TLSv1.3"],
    "ciphers": "HIGH:!aNULL:!MD5"
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | false | Enable TLS |
| `cert_file` | string | null | Server certificate |
| `key_file` | string | null | Private key |
| `ca_file` | string | null | CA certificate |
| `generate_self_signed` | boolean | false | Auto-generate cert |
| `client_auth` | boolean | false | Require client certs |
| `protocols` | array | ["TLSv1.2", "TLSv1.3"] | Allowed protocols |
| `ciphers` | string | "HIGH:!aNULL:!MD5" | Cipher suite |

## GPU Configuration

```json
{
  "gpu": {
    "enabled": false,
    "device_id": 0,
    "memory_fraction": 0.8,
    "compute_capability": "auto",
    "kernels": ["vector_ops", "matrix_mult", "sort"]
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | false | Enable GPU |
| `device_id` | integer | 0 | GPU device ID |
| `memory_fraction` | number | 0.8 | GPU memory fraction |
| `compute_capability` | string | "auto" | CUDA compute capability |
| `kernels` | array | [...] | Enabled kernels |

## Audit Logging Configuration

```json
{
  "audit_logging": {
    "enabled": false,
    "log_dir": "./audit_logs",
    "max_size_mb": 100,
    "max_age_days": 30,
    "compress": true,
    "targets": ["file"],
    "syslog_facility": "local0",
    "webhook_url": null,
    "webhook_headers": {},
    "exclude_commands": ["PING", "ECHO"],
    "mask_commands": ["PASS", "PASSWORD", "SECRET"]
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | false | Enable audit logging |
| `log_dir` | string | "./audit_logs" | Log directory |
| `max_size_mb` | number | 100 | Max log file size |
| `max_age_days` | integer | 30 | Log retention days |
| `compress` | boolean | true | Compress old logs |
| `targets` | array | ["file"] | Output targets |
| `syslog_facility` | string | "local0" | Syslog facility |
| `webhook_url` | string | null | Webhook URL |
| `webhook_headers` | object | {} | Webhook headers |
| `exclude_commands` | array | ["PING"] | Commands to exclude |
| `mask_commands` | array | ["PASS"] | Commands to mask |

## Replication Configuration

```json
{
  "replication": {
    "enabled": false,
    "role": "master",
    "master_host": null,
    "replication_port": null,
    "peer_host": null,
    "sync_interval": 5,
    "heartbeat_interval": 10,
    "max_lag_seconds": 60
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | false | Enable replication |
| `role` | string | "master" | Server role |
| `master_host` | string | null | Master host:port |
| `replication_port` | integer | null | Replication port |
| `peer_host` | string | null | Peer host:port |
| `sync_interval` | integer | 5 | Sync interval (seconds) |
| `heartbeat_interval` | integer | 10 | Heartbeat interval |
| `max_lag_seconds` | integer | 60 | Max replication lag |

## Authentication Configuration

```json
{
  "authentication": {
    "method": "database",
    "jwt_secret_env": "KOSDB_JWT_SECRET",
    "session_ttl_minutes": 60,
    "max_failed_attempts": 5,
    "lockout_duration_minutes": 30,
    "rbac_enabled": true,
    "default_roles": ["readonly", "readwrite", "admin"]
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `method` | string | "database" | Auth method |
| `jwt_secret_env` | string | "KOSDB_JWT_SECRET" | JWT secret env var |
| `session_ttl_minutes` | integer | 60 | Session TTL |
| `max_failed_attempts` | integer | 5 | Max failed attempts |
| `lockout_duration_minutes` | integer | 30 | Lockout duration |
| `rbac_enabled` | boolean | true | Enable RBAC |
| `default_roles` | array | [...] | Default roles |

## Backup Configuration

```json
{
  "backup": {
    "enabled": true,
    "backup_dir": "./backups",
    "auto_backup": false,
    "backup_interval_hours": 24,
    "retention_count": 10,
    "compression": "gzip",
    "compression_level": 6,
    "encryption_passphrase_env": "KOSDB_BACKUP_PASSPHRASE"
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | true | Enable backups |
| `backup_dir` | string | "./backups" | Backup directory |
| `auto_backup` | boolean | false | Auto backup |
| `backup_interval_hours` | integer | 24 | Backup interval |
| `retention_count` | integer | 10 | Retention count |
| `compression` | string | "gzip" | Compression algorithm |
| `compression_level` | integer | 6 | Compression level |
| `encryption_passphrase_env` | string | "KOSDB_BACKUP_PASSPHRASE" | Backup passphrase env var |

## Monitoring Configuration

```json
{
  "monitoring": {
    "enabled": false,
    "metrics_port": 9090,
    "prometheus_enabled": false,
    "health_check_interval": 30,
    "slow_query_threshold_ms": 1000
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | false | Enable monitoring |
| `metrics_port` | integer | 9090 | Metrics port |
| `prometheus_enabled` | boolean | false | Enable Prometheus |
| `health_check_interval` | integer | 30 | Health check interval |
| `slow_query_threshold_ms` | integer | 1000 | Slow query threshold |

## Logging Configuration

```json
{
  "logging": {
    "level": "INFO",
    "format": "[%(asctime)s] %(levelname)s: %(message)s",
    "file": null,
    "max_size_mb": 100,
    "max_files": 5,
    "console": true
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `level` | string | "INFO" | Log level |
| `format` | string | "[%(asctime)s]..." | Log format |
| `file` | string | null | Log file path |
| `max_size_mb` | integer | 100 | Max log size |
| `max_files` | integer | 5 | Max log files |
| `console` | boolean | true | Console output |

## Performance Configuration

```json
{
  "performance": {
    "query_cache_size": 1000,
    "connection_pool_min": 5,
    "connection_pool_max": 20,
    "worker_threads": 4
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `query_cache_size` | integer | 1000 | Query cache size |
| `connection_pool_min` | integer | 5 | Min pool connections |
| `connection_pool_max` | integer | 20 | Max pool connections |
| `worker_threads` | integer | 4 | Worker threads |

## Environment Variables

Store sensitive values in environment variables:

```bash
export KOSDB_ENCRYPTION_PASSPHRASE="your-secret-key"
export KOSDB_JWT_SECRET="your-jwt-secret"
export KOSDB_BACKUP_PASSPHRASE="your-backup-passphrase"
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

## Command Line Overrides

Override config values with command-line arguments:

```bash
python server.py -c config.json --host 127.0.0.1 --port 8888
```

Available overrides:
- `--host`
- `--port`
- `--data_dir`
- `--server-id`
- `--tls-cert`
- `--tls-key`
- `--audit-log-dir`
- `--role`
- `--master-host`
- `--replication-port`
- `--peer-host`

## Validation

Configuration is validated on startup. Common errors:

| Error | Solution |
|-------|----------|
| Missing required section | Add missing section to config |
| Invalid port number | Use port 1-65535 |
| File not found | Check file paths |
| Invalid compression | Use gzip, lz4, zstd, or none |

## Examples

See example configurations:
- [config.tls.example.json](config.tls.example.json) - TLS/SSL setup
- [config.gpu.example.json](config.gpu.example.json) - GPU acceleration
