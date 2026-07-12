
# KosDB Batch Operations - Operational Guide

Version: 2.3.0  
Last Updated: 2024-01-15

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Configuration Tuning](#configuration-tuning)
3. [Monitoring and Alerting](#monitoring-and-alerting)
4. [Troubleshooting](#troubleshooting)
5. [Monitoring Dashboards](#monitoring-dashboards)
6. [Backup and Restore](#backup-and-restore)
7. [Security Hardening](#security-hardening)
8. [Incident Runbook](#incident-runbook)

---

## Architecture Overview

### Batch Command Flow

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│   Client    │────▶│ Batch Parser │────▶│  Validator   │
└─────────────┘     └──────────────┘     └──────────────┘
                                                  │
                       ┌──────────────────────────┘
                       ▼
              ┌──────────────┐     ┌──────────────┐
              │   Executor   │────▶│   Binlog     │
              └──────────────┘     └──────────────┘
                       │
                       ▼
              ┌──────────────┐     ┌──────────────┐
              │    CDC       │────▶│  Replication │
              └──────────────┘     └──────────────┘
```

### Components

| Component | Responsibility | Critical Metrics |
|-----------|---------------|------------------|
| Batch Parser | Syntax validation, command splitting | Parse time, error rate |
| Validator | Permission checks, schema validation | Validation time, rejections |
| Executor | Command execution, error handling | Execution time, throughput |
| Binlog | Write-ahead logging, replication | Write latency, position lag |
| CDC | Change data capture streaming | Event lag, consumer lag |
| Replication | Cross-node synchronization | Replication lag, conflict rate |

### Batch Types

1. **Single-Shard Batches** - All commands target same shard
   - Fastest execution
   - No distributed coordination needed

2. **Cross-Shard Batches** - Commands span multiple shards
   - Uses 2-phase commit
   - Higher latency, stronger consistency

3. **Mixed Batches** - Combination of operations
   - Analyzed and grouped by shard
   - Executed in optimal order

---

## Configuration Tuning

### Batch Size Limits

```python
# config/batch_config.py

BATCH_CONFIG = {
    # Maximum commands per batch
    'max_batch_size': 10000,
    
    # Recommended sizes by operation type
    'recommended_sizes': {
        'INSERT': 1000,
        'UPDATE': 500,
        'DELETE': 500,
        'SELECT': 100,  # Lower for read-heavy
    },
    
    # Warnings thresholds
    'warning_threshold': 5000,
    'error_threshold': 10000,
}
```

### Timeout Configuration

```python
TIMEOUT_CONFIG = {
    # Default batch execution timeout (ms)
    'default_timeout_ms': 30000,
    
    # Size-based timeouts
    'size_based_timeouts': {
        (0, 100): 5000,      # 0-100 commands: 5s
        (101, 1000): 15000,  # 101-1000: 15s
        (1001, 10000): 30000, # 1001-10000: 30s
    },
    
    # Cross-shard timeout multiplier
    'cross_shard_multiplier': 2.0,
    
    # CDC consumer timeout
    'cdc_consumer_timeout_ms': 60000,
}
```

### Memory Configuration

```python
MEMORY_CONFIG = {
    # Maximum memory per batch (MB)
    'max_batch_memory_mb': 100,
    
    # Memory per command estimate (KB)
    'memory_per_command_kb': 10,
    
    # GC threshold (trigger GC after N batches)
    'gc_threshold_batches': 100,
    
    # Streaming threshold (stream if larger)
    'streaming_threshold_commands': 5000,
}
```

### Connection Pool Tuning

```python
CONNECTION_POOL_CONFIG = {
    # Pool size per shard
    'min_connections': 5,
    'max_connections': 50,
    
    # Connection timeout
    'connection_timeout_ms': 5000,
    
    # Idle connection timeout
    'idle_timeout_ms': 300000,  # 5 minutes
    
    # Health check interval
    'health_check_interval_ms': 30000,
}
```

### Sharding Configuration

```python
SHARDING_CONFIG = {
    # Routing cache
    'routing_cache_size': 10000,
    'routing_cache_ttl_seconds': 300,
    
    # Cross-shard coordinator
    'coordinator_timeout_ms': 30000,
    'max_concurrent_cross_shard': 10,
    
    # Retry configuration
    'max_retries': 3,
    'retry_backoff_ms': [100, 500, 1000],
}
```

### Replication Configuration

```python
REPLICATION_CONFIG = {
    # Binlog settings
    'binlog_sync_interval_ms': 100,
    'max_binlog_size_mb': 100,
    
    # Replication lag thresholds
    'warning_lag_threshold_ms': 1000,
    'critical_lag_threshold_ms': 5000,
    
    # Batch marker settings
    'batch_marker_timeout_ms': 60000,
}
```

---

## Monitoring and Alerting

### Key Metrics

#### Execution Metrics

| Metric | Description | Warning | Critical |
|--------|-------------|---------|----------|
| `batch_execution_time_ms` | Average execution time | > 5s | > 30s |
| `batch_throughput_cmd_sec` | Commands per second | < 80% baseline | < 50% baseline |
| `batch_error_rate` | Failed commands / total | > 1% | > 5% |
| `batch_queue_depth` | Pending batches | > 100 | > 500 |

#### Resource Metrics

| Metric | Description | Warning | Critical |
|--------|-------------|---------|----------|
| `batch_memory_usage_mb` | Current memory usage | > 80% limit | > 95% limit |
| `batch_active_count` | Concurrent batches | > 80% max | > 95% max |
| `connection_pool_usage` | Pool utilization | > 70% | > 90% |

#### Replication Metrics

| Metric | Description | Warning | Critical |
|--------|-------------|---------|----------|
| `replication_lag_ms` | Replication delay | > 1s | > 5s |
| `binlog_position_lag` | Binlog entries behind | > 100 | > 1000 |
| `cdc_consumer_lag` | CDC processing delay | > 5s | > 30s |

### Prometheus Metrics

```python
# Example Prometheus instrumentation

from prometheus_client import Counter, Histogram, Gauge

# Counters
batch_commands_total = Counter(
    'batch_commands_total',
    'Total batch commands executed',
    ['operation', 'status']
)

batch_errors_total = Counter(
    'batch_errors_total',
    'Total batch errors',
    ['error_type']
)

# Histograms
batch_execution_time = Histogram(
    'batch_execution_time_seconds',
    'Batch execution time',
    buckets=[.005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10]
)

batch_size_distribution = Histogram(
    'batch_size_commands',
    'Distribution of batch sizes',
    buckets=[1, 10, 50, 100, 500, 1000, 5000, 10000]
)

# Gauges
batch_memory_usage = Gauge(
    'batch_memory_usage_bytes',
    'Current batch memory usage'
)

batch_active_batches = Gauge(
    'batch_active_batches',
    'Number of active batches'
)

replication_lag = Gauge(
    'batch_replication_lag_seconds',
    'Replication lag for batches'
)
```

### Alerting Rules

```yaml
# prometheus-alerts.yml

groups:
  - name: batch_alerts
    rules:
      # High execution time
      - alert: BatchExecutionTimeHigh
        expr: histogram_quantile(0.95, batch_execution_time_seconds) > 5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Batch execution time is high"
          description: "95th percentile batch execution time > 5s"

      # High error rate
      - alert: BatchErrorRateHigh
        expr: rate(batch_errors_total[5m]) / rate(batch_commands_total[5m]) > 0.01
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Batch error rate is high"
          description: "Error rate > 1% over last 5 minutes"

      # Memory pressure
      - alert: BatchMemoryHigh
        expr: batch_memory_usage_bytes / batch_memory_limit_bytes > 0.8
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Batch memory usage high"
          description: "Memory usage > 80% of limit"

      # Replication lag
      - alert: BatchReplicationLagHigh
        expr: batch_replication_lag_seconds > 5
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Batch replication lag critical"
          description: "Replication lag > 5 seconds"

      # CDC consumer lag
      - alert: BatchCDCLagHigh
        expr: batch_cdc_consumer_lag_seconds > 30
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "CDC consumer lag high"
          description: "CDC consumer is > 30s behind"
```

---

## Troubleshooting

### Batch Timeouts

**Symptoms:**
- `TimeoutError: Batch execution exceeded timeout`
- Slow client response times
- Queue buildup

**Diagnosis:**
```bash
# Check current batch execution times
SELECT batch_id, execution_time_ms, command_count 
FROM batch_metrics 
WHERE execution_time_ms > 30000;

# Check for blocked batches
SELECT * FROM active_batches 
WHERE state = 'executing' 
AND start_time < NOW() - INTERVAL '30 seconds';
```

**Solutions:**

1. **Increase timeout for large batches:**
   ```python
   result = db.execute_batch(commands, timeout_ms=60000)
   ```

2. **Reduce batch size:**
   ```python
   # Split large batch
   batches = [commands[i:i+500] for i in range(0, len(commands), 500)]
   ```

3. **Check for slow queries:**
   ```sql
   EXPLAIN ANALYZE <problematic_query>;
   ```

### Memory Issues with Large Batches

**Symptoms:**
- `MemoryError: Unable to allocate`
- System OOM kills
- Degraded performance

**Diagnosis:**
```bash
# Check memory usage
curl http://localhost:8080/metrics | grep batch_memory

# Monitor during batch execution
watch -n 1 'ps -o pid,rss,vsz,comm -p $(pgrep -f kosdb)'
```

**Solutions:**

1. **Enable streaming mode:**
   ```python
   result = db.execute_batch(
       commands,
       streaming=True,
       stream_chunk_size=1000
   )
   ```

2. **Reduce batch size:**
   ```python
   # Process in smaller chunks
   for chunk in chunks(commands, 1000):
       db.execute_batch(chunk)
   ```

3. **Increase system limits:**
   ```bash
   # /etc/systemd/system/kosdb.service
   [Service]
   MemoryLimit=4G
   ```

### Partial Failure Diagnosis

**Symptoms:**
- Some commands succeed, others fail
- `BatchPartialFailure` exceptions
- Inconsistent data state

**Diagnosis:**
```python
# Get detailed error information
result = db.execute_batch(commands, error_mode="continue")

for idx, error in result['errors']:
    print(f"Command {idx} failed: {error}")

# Check binlog for committed commands
binlog_entries = db.binlog.read_since(position)
```

**Solutions:**

1. **Use rollback mode for consistency:**
   ```python
   result = db.execute_batch(commands, error_mode="rollback_all")
   ```

2. **Retry failed commands individually:**
   ```python
   for idx, cmd in failed_commands:
       try:
           db.execute(cmd)
       except Exception as e:
           log.error(f"Command {idx} failed permanently: {e}")
   ```

3. **Implement idempotency:**
   ```python
   # Add idempotency keys
   commands = [
       {"op": "INSERT", "idempotency_key": f"batch_{batch_id}_{i}"}
       for i, cmd in enumerate(commands)
   ]
   ```

### Replication Lag from Batches

**Symptoms:**
- `SHOW SLAVE STATUS` shows lag
- CDC consumers behind
- Read replicas stale

**Diagnosis:**
```bash
# Check replication lag
mysql -e "SHOW SLAVE STATUS\G" | grep Seconds_Behind_Master

# Check binlog rate
ls -la /var/lib/mysql/binlog.* | wc -l

# Monitor CDC lag
curl http://cdc-metrics/lag
```

**Solutions:**

1. **Increase binlog sync interval:**
   ```python
   REPLICATION_CONFIG['binlog_sync_interval_ms'] = 50
   ```

2. **Parallel replication:**
   ```sql
   -- Enable parallel replication threads
   SET GLOBAL slave_parallel_workers = 8;
   ```

3. **Batch size limits for replication:**
   ```python
   # Limit batch size during high replication lag
   if replication_lag > 1000:  # 1 second
       max_batch_size = 100
   ```

### CDC Consumer Overload

**Symptoms:**
- CDC consumer lag increasing
- Consumer memory high
- Event processing delays

**Diagnosis:**
```bash
# Check consumer lag
kafka-consumer-groups --describe --group cdc-consumer

# Monitor consumer metrics
curl http://cdc-consumer:8080/metrics | grep lag
```

**Solutions:**

1. **Scale consumers horizontally:**
   ```bash
   # Add more consumer instances
   docker-compose up --scale cdc-consumer=5
   ```

2. **Implement backpressure:**
   ```python
   # Rate limit batch execution
   if cdc_lag > 10000:
       time.sleep(1)  # Slow down
   ```

3. **Filter CDC events:**
   ```python
   # Only capture relevant tables
   cdc_consumer = BatchCDCConsumer(
       tables={'users', 'orders'},  # Not 'logs'
       operations={BatchCDCEventType.INSERT, BatchCDCEventType.UPDATE}
   )
   ```

---

## Monitoring Dashboards

### Grafana Dashboard JSON

```json
{
  "dashboard": {
    "title": "KosDB Batch Operations",
    "panels": [
      {
        "title": "Batch Throughput",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(batch_commands_total[5m])",
            "legendFormat": "{{operation}}"
          }
        ],
        "yAxes": [{"label": "commands/sec"}]
      },
      {
        "title": "Execution Time Percentiles",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.50, batch_execution_time_seconds)",
            "legendFormat": "p50"
          },
          {
            "expr": "histogram_quantile(0.95, batch_execution_time_seconds)",
            "legendFormat": "p95"
          },
          {
            "expr": "histogram_quantile(0.99, batch_execution_time_seconds)",
            "legendFormat": "p99"
          }
        ],
        "yAxes": [{"label": "seconds"}]
      },
      {
        "title": "Error Rate",
        "type": "singlestat",
        "targets": [
          {
            "expr": "rate(batch_errors_total[5m]) / rate(batch_commands_total[5m]) * 100"
          }
        ],
        "format": "percent",
        "thresholds": "1,5",
        "colorBackground": true
      },
      {
        "title": "Memory Usage",
        "type": "graph",
        "targets": [
          {
            "expr": "batch_memory_usage_bytes / 1024 / 1024",
            "legendFormat": "Memory (MB)"
          }
        ],
        "alert": {
          "conditions": [
            {
              "evaluator": {"params": [80], "type": "gt"},
              "operator": {"type": "and"},
              "query": {"params": ["A", "5m", "now"]},
              "reducer": {"type": "avg"},
              "type": "query"
            }
          ]
        }
      },
      {
        "title": "Replication Lag",
        "type": "graph",
        "targets": [
          {
            "expr": "batch_replication_lag_seconds",
            "legendFormat": "Lag (s)"
          }
        ],
        "alert": {
          "conditions": [
            {
              "evaluator": {"params": [5], "type": "gt"},
              "reducer": {"type": "last"},
              "type": "query"
            }
          ]
        }
      },
      {
        "title": "CDC Consumer Lag",
        "type": "graph",
        "targets": [
          {
            "expr": "batch_cdc_consumer_lag_seconds",
            "legendFormat": "Consumer {{id}}"
          }
        ]
      },
      {
        "title": "Active Batches",
        "type": "graph",
        "targets": [
          {
            "expr": "batch_active_batches",
            "legendFormat": "Active"
          }
        ]
      },
      {
        "title": "Batch Size Distribution",
        "type": "heatmap",
        "targets": [
          {
            "expr": "batch_size_commands_bucket",
            "legendFormat": "{{le}}"
          }
        ],
        "dataFormat": "tsbuckets"
      }
    ]
  }
}
```

### Key Dashboard Panels

1. **Throughput Overview** - Commands/sec by operation type
2. **Latency Heatmap** - Execution time distribution
3. **Error Rate Gauge** - Real-time error percentage
4. **Resource Utilization** - Memory and CPU usage
5. **Replication Status** - Lag and position metrics
6. **CDC Health** - Consumer lag and event rates
7. **Shard Distribution** - Cross-shard batch distribution

---

## Backup and Restore

### Batch Audit Log Backup

#### Automated Backups

```bash
#!/bin/bash
# backup_batch_logs.sh

BACKUP_DIR="/backup/batch-logs/$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR

# Backup binlog with batch markers
mysqlbinlog --read-from-remote-server \
  --raw \
  --host=$DB_HOST \
  --user=$BACKUP_USER \
  --password=$BACKUP_PASS \
  --result-file=$BACKUP_DIR/ \
  mysql-bin.000001 mysql-bin.000002

# Compress
tar czf $BACKUP_DIR.tar.gz $BACKUP_DIR
rm -rf $BACKUP_DIR

# Upload to S3
aws s3 cp $BACKUP_DIR.tar.gz s3://kosdb-backups/batch-logs/

# Cleanup old backups (keep 30 days)
find /backup/batch-logs -name "*.tar.gz" -mtime +30 -delete
```

#### Point-in-Time Recovery

```bash
#!/bin/bash
# restore_batch_logs.sh

RESTORE_TIME="2024-01-15 10:30:00"
BACKUP_FILE="s3://kosdb-backups/batch-logs/20240115.tar.gz"

# Download backup
aws s3 cp $BACKUP_FILE /tmp/restore.tar.gz
tar xzf /tmp/restore.tar.gz -C /tmp/restore

# Find binlogs up to restore time
mysqlbinlog \
  --start-datetime="$RESTORE_TIME" \
  --stop-datetime="$RESTORE_TIME + 1 minute" \
  /tmp/restore/*.00000* > /tmp/restore.sql

# Apply to database
mysql < /tmp/restore.sql
```

### CDC Event Backup

```python
# Backup CDC events to object storage
import boto3

def backup_cdc_events(events, batch_id):
    s3 = boto3.client('s3')
    
    key = f"cdc-backup/{batch_id}/{datetime.now().isoformat()}.json"
    
    s3.put_object(
        Bucket='kosdb-cdc-backup',
        Key=key,
        Body=json.dumps(events)
    )
```

---

## Security Hardening

### Batch Feature Security Checklist

#### Authentication & Authorization

- [ ] Enable authentication for batch endpoints
- [ ] Implement role-based access control (RBAC)
- [ ] Restrict batch operations to authorized users only
- [ ] Audit all batch command execution
- [ ] Implement API rate limiting per user

```python
# Example RBAC configuration
BATCH_PERMISSIONS = {
    'admin': ['EXECUTE', 'READ', 'DELETE'],
    'operator': ['EXECUTE', 'READ'],
    'analyst': ['READ'],
    'service': ['EXECUTE'],
}

def check_permission(user, operation):
    role = user.role
    return operation in BATCH_PERMISSIONS.get(role, [])
```

#### Input Validation

- [ ] Validate all batch commands against schema
- [ ] Sanitize user input to prevent injection
- [ ] Limit batch size to prevent DoS
- [ ] Validate table and column names
- [ ] Check for forbidden operations

```python
# Input validation
def validate_batch_command(cmd):
    # Schema validation
    if not SCHEMA_VALIDATOR.is_valid(cmd):
        raise ValidationError("Invalid command schema")
    
    # Injection prevention
    if contains_sql_injection(cmd):
        raise SecurityError("Potential SQL injection detected")
    
    # Size limits
    if len(cmd.get('data', '')) > MAX_DATA_SIZE:
        raise ValidationError("Data exceeds maximum size")
```

#### Network Security

- [ ] Use TLS for all batch API communications
- [ ] Implement network segmentation
- [ ] Restrict batch endpoints to internal networks
- [ ] Enable connection encryption for replication
- [ ] Use VPN for cross-region batch operations

```yaml
# nginx configuration
server {
    listen 443 ssl;
    server_name batch-api.kosdb.internal;
    
    ssl_certificate /etc/ssl/certs/kosdb.crt;
    ssl_certificate_key /etc/ssl/private/kosdb.key;
    
    location /batch {
        allow 10.0.0.0/8;
        deny all;
        
        proxy_pass http://kosdb_batch_service;
    }
}
```

#### Audit Logging

- [ ] Log all batch execution attempts
- [ ] Include user, timestamp, and command summary
- [ ] Store logs in tamper-resistant storage
- [ ] Implement log forwarding to SIEM
- [ ] Set up alerts for suspicious patterns

```python
# Audit logging
def audit_batch_execution(batch_id, user, commands, result):
    audit_log.info({
        'event': 'batch_execution',
        'batch_id': batch_id,
        'user': user.id,
        'user_name': user.name,
        'command_count': len(commands),
        'tables': extract_tables(commands),
        'success': result['success'],
        'duration_ms': result['duration_ms'],
        'timestamp': datetime.utcnow().isoformat(),
        'source_ip': user.source_ip,
    })
```

#### Secrets Management

- [ ] Store database credentials in vault
- [ ] Rotate credentials regularly
- [ ] Use separate credentials for batch operations
- [ ] Encrypt sensitive data in batch commands
- [ ] Implement key rotation for CDC encryption

```python
# Using HashiCorp Vault
import hvac

vault_client = hvac.Client(url='https://vault.example.com')

def get_db_credentials():
    secret = vault_client.secrets.kv.v2.read_secret_version(
        path='kosdb/batch-credentials'
    )
    return secret['data']['data']
```

---

## Incident Runbook

### P1: Batch System Down

**Symptoms:**
- All batch operations failing
- 500 errors from batch API
- High error rate in metrics

**Response:**

1. **Immediate Actions (0-5 min):**
   ```bash
   # Check service health
   systemctl status kosdb-batch
   
   # Check logs
   journalctl -u kosdb-batch -f -n 100
   
   # Check resource usage
   df -h && free -h
   ```

2. **Assessment (5-10 min):**
   - Determine scope: All batches or specific type?
   - Check if single commands still work
   - Review recent deployments

3. **Mitigation:**
   ```bash
   # Restart service if needed
   systemctl restart kosdb-batch
   
   # Check if recovery successful
   curl http://localhost:8080/health
   ```

4. **Communication:**
   - Notify on-call engineer
   - Post incident channel update
   - Begin status page update if customer-facing

### P2: High Replication Lag

**Symptoms:**
- Replication lag > 5 seconds
- CDC consumers behind
- Read replicas stale

**Response:**

1. **Immediate Actions:**
   ```bash
   # Check replication status
   mysql -e "SHOW SLAVE STATUS\G" | grep -E "(Seconds_Behind|Last_Error)"
   
   # Check binlog rate
   mysql -e "SHOW MASTER STATUS"
   ```

2. **Mitigation:**
   ```python
   # Enable emergency mode
   BATCH_CONFIG['emergency_mode'] = True
   BATCH_CONFIG['max_batch_size'] = 100  # Reduce size
   
   # Pause non-essential batches
   db.pause_batch_queue(priority='low')
   ```

3. **Recovery:**
   - Monitor lag reduction
   - Gradually restore batch sizes
   - Resume paused batches

### P3: Memory Exhaustion

**Symptoms:**
- OOM errors in logs
- System swapping
- Batch operations slow/failing

**Response:**

1. **Immediate Actions:**
   ```bash
   # Check memory usage
   ps aux --sort=-%mem | head -20
   
   # Check for memory leaks
   pmap $(pgrep kosdb) | tail -1
   ```

2. **Mitigation:**
   ```bash
   # Trigger emergency GC
   curl -X POST http://localhost:8080/admin/gc
   
   # Reduce batch memory limit
   curl -X POST http://localhost:8080/admin/config \
     -d '{"max_batch_memory_mb": 50}'
   ```

3. **Long-term Fix:**
   - Identify memory leak source
   - Deploy hotfix
   - Add memory monitoring alerts

### P4: Partial Batch Failures

**Symptoms:**
- Some commands in batch failing
- Inconsistent data state
- Error logs show partial failures

**Response:**

1. **Immediate Actions:**
   ```python
   # Identify failed commands
   result = db.get_batch_errors(batch_id)
   
   # Check if rollback needed
   if result['failed_count'] > result['success_count']:
       db.rollback_batch(batch_id)
   ```

2. **Recovery:**
   ```python
   # Retry failed commands individually
   for cmd in failed_commands:
       try:
           db.execute(cmd)
       except Exception as e:
           # Log for manual review
           log.error(f"Permanent failure: {cmd}, error: {e}")
   ```

3. **Verification:**
   ```sql
   -- Verify data consistency
   SELECT COUNT(*) FROM table WHERE batch_id = 'xxx';
   ```

### Post-Incident Review

**Template:**

```markdown
## Incident Review: [Incident ID]

### Summary
- **Date:** [Date]
- **Duration:** [Duration]
- **Severity:** [P1/P2/P3]
- **Impact:** [Description]

### Timeline
- [Time] - Issue detected
- [Time] - Response started
- [Time] - Mitigation applied
- [Time] - Service restored

### Root Cause
[Detailed explanation]

### Lessons Learned
1. [Lesson 1]
2. [Lesson 2]

### Action Items
- [ ] [Action 1] - Owner: [Name] - Due: [Date]
- [ ] [Action 2] - Owner: [Name] - Due: [Date]

### Monitoring Improvements
- [ ] Add alert for [condition]
- [ ] Update dashboard with [metric]
```

---

## Quick Reference

### Common Commands

```bash
# Check batch status
curl http://localhost:8080/batch/status

# Get batch metrics
curl http://localhost:8080/metrics | grep batch

# Force GC
curl -X POST http://localhost:8080/admin/gc

# Pause batch processing
curl -X POST http://localhost:8080/admin/pause

# Resume batch processing
curl -X POST http://localhost:8080/admin/resume

# Clear routing cache
curl -X POST http://localhost:8080/admin/cache/clear
```

### Emergency Contacts

| Role | Contact | Escalation |
|------|---------|------------|
| On-Call Engineer | oncall@kosdb.com | +1-555-0100 |
| Database Team | dba@kosdb.com | Slack #dba |
| Platform Team | platform@kosdb.com | Slack #platform |

### Useful Links

- [Batch Architecture](BATCH_SHARDING.md)
- [Performance Tuning](LOAD_TESTING.md)
- [Security Guide](SECURITY_README.md)
- [API Reference](api-reference.md)

---

*Document Version: 2.3.0*  
*Last Updated: 2024-01-15*
