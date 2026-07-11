# KosDB Configuration Guide

This guide covers the configuration system for KosDB v2.1.0, including new TLS, caching, GPU, and full-text search settings.

## Configuration Files

- `config.json` - Default configuration with all v2.1.0 features
- `config.development.json` - Optimized for local development
- `config.production.json` - High availability production setup
- `config.gpu-enabled.json` - GPU-accelerated AI/ML workloads

## Configuration Sections

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
