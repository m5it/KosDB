# Migration Guide: KosDB v3.1.0 to v3.2.0

This guide helps you upgrade from KosDB v3.1.0 to v3.2.0.

## Overview

KosDB v3.2.0 introduces significant new features including:
- Query plan caching and optimization
- Subquery support (IN, EXISTS, scalar)
- CHECK constraints and foreign keys
- ALTER TABLE operations
- Views and full-text search
- Prometheus metrics and monitoring
- JSON data type support

**Backward Compatibility**: v3.2.0 is fully backward compatible with v3.1.0. Existing databases will work without modification.

## Quick Migration Steps

### 1. Backup Your Data

```bash
# Create backup before upgrading
python cli.py -c "BACKUP DATABASE mydb TO /backups/pre-v3.2.backup"
```

### 2. Update Configuration

Add new sections to your `config.json`:

```json
{
  "version": "3.2.0",
  
  "optimizer": {
    "enabled": true,
    "cache_size": 100,
    "collect_statistics": true,
    "enable_semi_join": true
  },
  
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
    }
  }
}
```

### 3. Update Dependencies

```bash
pip install -r requirements.txt
```

### 4. Restart Server

```bash
python server.py -c config.json
```

### 5. Verify Upgrade

```bash
# Check version
python cli.py -c "SELECT version()"

# Test new features
python cli.py -c "EXPLAIN CACHE"
```

## Detailed Migration

### Configuration Changes

#### New Required Sections

**Optimizer Configuration** (required for query optimization):

```json
{
  "optimizer": {
    "enabled": true,
    "cache_size": 100,
    "collect_statistics": true,
    "enable_semi_join": true,
    "statistics_ttl": 3600
  }
}
```

| Option | Description | Default |
|--------|-------------|---------|
| `enabled` | Enable query optimizer | `true` |
| `cache_size` | Number of cached execution plans | `100` |
| `collect_statistics` | Auto-collect table statistics | `true` |
| `enable_semi_join` | Optimize IN/EXISTS with semi-join | `true` |
| `statistics_ttl` | Statistics cache TTL in seconds | `3600` |

**Metrics Configuration** (optional, for monitoring):

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

#### Deprecated Options

None. All v3.1.0 configuration options remain valid.

### Database Schema Changes

#### Adding CHECK Constraints

Existing tables can have CHECK constraints added:

```sql
-- Add CHECK constraint to existing table
ALTER TABLE users ADD CONSTRAINT chk_age CHECK (age >= 18);

-- Add column with CHECK constraint
ALTER TABLE users ADD COLUMN status TEXT CHECK (status IN ('active', 'inactive'));
```

**Note**: CHECK constraints only apply to new INSERT/UPDATE operations. Existing data is not validated.

#### Adding Foreign Keys

Foreign keys can be added to existing tables:

```sql
-- Add foreign key constraint
ALTER TABLE orders ADD CONSTRAINT fk_user 
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
```

**Note**: Foreign key constraints are enforced immediately. Ensure existing data satisfies the constraint before adding.

#### Creating Views

Views provide a way to create virtual tables:

```sql
-- Create view from existing data
CREATE VIEW active_users AS 
SELECT * FROM users WHERE status = 'active';

-- Query view like a table
SELECT * FROM active_users WHERE age > 25;
```

### SQL Syntax Changes

#### New Statements

**Subqueries**:

```sql
-- Scalar subquery
SELECT name, (SELECT COUNT(*) FROM orders) FROM users;

-- IN subquery
SELECT * FROM users WHERE id IN (SELECT user_id FROM orders);

-- EXISTS subquery
SELECT * FROM users WHERE EXISTS (SELECT 1 FROM orders WHERE user_id = users.id);
```

**ALTER TABLE**:

```sql
-- Add column
ALTER TABLE users ADD COLUMN email TEXT;

-- Modify column
ALTER TABLE users MODIFY COLUMN age FLOAT;

-- Rename column
ALTER TABLE users RENAME COLUMN name TO full_name;

-- Drop column
ALTER TABLE users DROP COLUMN email CASCADE;

-- Add index
ALTER TABLE users ADD INDEX idx_name (name);

-- Add constraint
ALTER TABLE users ADD CONSTRAINT chk_age CHECK (age >= 0);
```

**JSON Operations**:

```sql
-- Create table with JSON column
CREATE TABLE events (id INT, data JSON);

-- Insert JSON data
INSERT INTO events VALUES (1, '{"type": "click", "x": 100, "y": 200}');

-- Query with JSON extraction
SELECT data->type, data->>x FROM events;
```

**Full-Text Search**:

```sql
-- Create full-text index
CREATE FULLTEXT INDEX idx_content ON articles(content);

-- Search
SELECT * FROM articles WHERE MATCH(content) AGAINST('database');
```

**EXPLAIN**:

```sql
-- Show query plan
EXPLAIN SELECT * FROM users WHERE age > 25;

-- Show cache status
EXPLAIN CACHE;
```

### Privilege Changes

#### New Privileges

v3.2.0 adds new privilege types:

| Privilege | Description |
|-----------|-------------|
| `ALTER` | ALTER TABLE operations |
| `REFERENCES` | Create foreign keys |
| `INDEX` | Create/drop indexes |

#### Updating User Privileges

Grant new privileges to existing users:

```sql
-- Grant ALTER privilege
GRANT ALTER ON mydb.* TO admin;

-- Grant REFERENCES for foreign keys
GRANT REFERENCES ON mydb.* TO developer;

-- Grant INDEX privilege
GRANT INDEX ON mydb.* TO developer;
```

### Monitoring Setup

#### Prometheus Integration

1. **Enable metrics endpoint**:

```json
{
  "metrics": {
    "enabled": true,
    "host": "0.0.0.0",
    "port": 9090
  }
}
```

2. **Configure Prometheus** (prometheus.yml):

```yaml
scrape_configs:
  - job_name: 'kosdb'
    static_configs:
      - targets: ['localhost:9090']
    metrics_path: /metrics
```

3. **Health checks for Kubernetes**:

```yaml
livenessProbe:
  httpGet:
    path: /health/live
    port: 9090
  initialDelaySeconds: 30
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /health/ready
    port: 9090
  initialDelaySeconds: 5
  periodSeconds: 5
```

### Performance Considerations

#### Query Plan Cache

The query plan cache improves performance for repeated queries:

```sql
-- Check cache statistics
EXPLAIN CACHE;

-- Typical output:
-- Plan Cache Status:
-- Size: 45 / 100 entries
-- Hit Rate: 87.5%
-- Total Hits: 350
-- Total Misses: 50
```

**Tuning**:
- Increase `cache_size` for high query diversity workloads
- Decrease for memory-constrained environments

#### Statistics Collection

Automatic statistics collection helps the optimizer:

```sql
-- Trigger statistics update
ANALYZE TABLE users;

-- Check statistics (via EXPLAIN)
EXPLAIN SELECT * FROM users WHERE age > 25;
```

### Troubleshooting

#### Migration Issues

**Issue**: "Unknown configuration option 'optimizer'"

**Solution**: Update config.json version to "3.2.0":

```json
{
  "version": "3.2.0",
  ...
}
```

**Issue**: "ALTER TABLE not supported"

**Solution**: Ensure you're running v3.2.0:

```bash
python server.py --version
# Should show: KosDB v3.2.0
```

**Issue**: "Subquery syntax error"

**Solution**: Verify parser is updated. Check that subqueries use correct syntax:

```sql
-- Correct
SELECT * FROM t1 WHERE id IN (SELECT id FROM t2);

-- Incorrect (missing parentheses)
SELECT * FROM t1 WHERE id IN SELECT id FROM t2;
```

#### Performance Regression

If queries are slower after upgrade:

1. **Check plan cache hit rate**:
   ```sql
   EXPLAIN CACHE;
   ```

2. **Analyze tables**:
   ```sql
   ANALYZE TABLE users;
   ANALYZE TABLE orders;
   ```

3. **Disable semi-join optimization** (if causing issues):
   ```json
   {
     "optimizer": {
       "enable_semi_join": false
     }
   }
   ```

### Rollback Procedure

If you need to rollback to v3.1.0:

1. **Stop v3.2.0 server**

2. **Restore v3.1.0 code**:
   ```bash
   git checkout v3.1.0
   ```

3. **Restore config.json** (remove optimizer and metrics sections)

4. **Restart server**

**Note**: Databases created with v3.2.0-specific features (CHECK constraints, views) will still work in v3.1.0, but those features won't be accessible.

## Feature Adoption Guide

### Phase 1: Basic Upgrade (Week 1)
- Update configuration
- Verify existing functionality
- Enable metrics endpoint

### Phase 2: Optimization (Week 2-3)
- Monitor query plan cache hit rates
- Add recommended indexes
- Analyze slow queries with EXPLAIN

### Phase 3: New Features (Week 4+)
- Add CHECK constraints to new tables
- Create views for common queries
- Implement subqueries where beneficial
- Set up Prometheus monitoring

## Support

For migration assistance:
- Review [README.md](README.md) for feature documentation
- Check [CHANGELOG.md](CHANGELOG.md) for complete feature list
- Open issue on GitHub for migration problems

## Verification Checklist

- [ ] Configuration updated to v3.2.0
- [ ] Server starts without errors
- [ ] Existing databases accessible
- [ ] Existing queries execute correctly
- [ ] New ALTER TABLE operations work
- [ ] Subqueries execute correctly
- [ ] Metrics endpoint accessible
- [ ] EXPLAIN CACHE shows statistics
- [ ] Backup/restore tested
- [ ] Documentation reviewed
