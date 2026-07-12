
# KosDB Configuration Guide

This guide covers the configuration system for KosDB v2.3.0, including multi-command batch execution, TLS, caching, GPU, and full-text search settings.

## Configuration Files

- `config.json` - Default configuration with all v2.3.0 features
- `config.development.json` - Optimized for local development
- `config.production.json` - High availability production setup
- `config.gpu-enabled.json` - GPU-accelerated AI/ML workloads

- `config.json` - Default configuration with all v2.1.0 features

### Server Configuration
```json
"server": {
    "host": "0.0.0.0",
    "port": 9999,
    "data_dir": "./data",
    "max_connections": 100,
    "connection_timeout": 30,
    "request_timeout": 60
}
```

### Batch Configuration (New in v2.3.0)
```json
"batch": {
    "enabled": true,
    "max_commands_per_batch": 100,
    "max_batch_size_bytes": 1048576,
    "max_response_size_bytes": 10485760,
    "batch_timeout_seconds": 30,
    "continue_on_error": true,
    "transaction_support": true
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | `true` | Enable multi-command batch execution |
| `max_commands_per_batch` | integer | `100` | Maximum commands per batch (1-10000) |
| `max_batch_size_bytes` | integer | `1048576` | Maximum batch request size in bytes (1KB-100MB) |
| `max_response_size_bytes` | integer | `10485760` | Maximum batch response size in bytes (1KB-100MB) |
| `batch_timeout_seconds` | integer | `30` | Timeout for batch execution (1-3600 seconds) |
| `continue_on_error` | boolean | `true` | Continue executing remaining commands after error |
| `transaction_support` | boolean | `true` | Enable transaction commands (BEGIN/COMMIT/ROLLBACK) in batches |

    "max_connections": 100,
    "connection_timeout": 30,
    "request_timeout": 60
}
```

### TLS Configuration (New in v2.1.0)
```json
"tls": {
    "enabled": true,
    "cert_file": "/etc/kosdb/certs/server.crt",
    "key_file": "/etc/kosdb/certs/server.key",
    "ca_file": "/etc/kosdb/certs/ca.crt",
    "require_client_cert": false,
    "ssl_version": "TLS"
}
```

### Cache Configuration (New in v2.1.0)
```json
"cache": {
    "enabled": true,
    "max_size": 1000,
    "default_ttl": 300,
    "invalidate_on_write": true
}
```

### GPU Configuration (New in v2.1.0)
```json
"gpu": {
    "enabled": true,
    "device_id": 0,
    "memory_limit_mb": 8192,
    "batch_size": 5000,
    "use_mixed_precision": true
}
```

### Full-Text Search Configuration (New in v2.1.0)
```json
"fulltext": {
    "enabled": true,
    "stem": true,
    "min_token_length": 2,
    "custom_stop_words": []
}
```

## Validation

Use the configuration validator to check your configuration:

```bash
python config_validator.py config.json
```

## Deployment Scenarios

### Development
- Localhost only (`127.0.0.1`)
- TLS disabled
- Debug logging
- Small cache

### Production
- TLS enabled with certificates
- Replication enabled
- Failover cluster configured
- Warning level logging

### GPU-Enabled
- CUDA acceleration for vector search
- Mixed precision for performance
- Higher dimension support (768)
- Memory limits configured

## Environment Variables

Configuration can be overridden via environment variables:
- `KOSDB_PORT` - Server port
- `KOSDB_DATA_DIR` - Data directory
- `KOSDB_LOG_LEVEL` - Logging level
- `KOSDB_GPU_ENABLED` - Enable GPU acceleration
