# KosDB - Distributed Database System

[![Version](https://img.shields.io/badge/version-2.2.0-blue.svg)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A high-performance, distributed database system built on LevelDB with support for replication, transactions, failover, monitoring, and advanced enterprise features including vector similarity search, geospatial queries, time-series data, multi-tenant architecture, change data capture, materialized views, and comprehensive security.

## What's New in v2.2.0

KosDB v2.2.0 brings enterprise-grade capabilities across 9 major feature domains, expanding the platform from a distributed key-value store into a full-featured operational database:

- **Time-Series Data** — Native hypertables with automatic partitioning
- **Multi-Tenancy** — Namespace isolation with resource quotas and RLS
- **Change Data Capture** — Stream database changes to Kafka and other systems
- **Materialized Views** — Automatic query rewriting with incremental refresh
- **Security Suite** — Audit logging, AES-256 encryption, RBAC, SQL injection detection, compliance reporting
- **Geospatial Queries** — Spatial indexing and distance calculations
- **Connection Pooling** — Managed connection lifecycle and load balancing
- **Compression** — Transparent data compression for storage efficiency
- **Prepared Statements** — Query plan reuse and parameter binding

## Features

### Core Database
- **Socket-based Protocol**: Fast text protocol over TCP
- **ACID Transactions**: Full transaction support with BEGIN/COMMIT/ROLLBACK
- **Distributed Transactions**: Two-Phase Commit (2PC) for multi-node consistency
- **Write-Ahead Logging**: Durable transaction logging with ARIES recovery
- **Master-Slave Replication**: Asynchronous replication with binlog
- **Automatic Failover**: Raft consensus for leader election
- **Backup & Restore**: Compressed JSON backups with integrity checking

### Query & Storage
- **SQL Parser**: Full SQL parsing for SELECT, INSERT, UPDATE, DELETE, DDL
- **Query Optimizer**: Cost-based execution planning with index advisor
- **Query Plan Cache**: Cached execution plans for frequently used queries
- **Concurrent Indexing**: Online index building without blocking reads/writes
- **Streaming Results**: Progressive result streaming for large datasets
- **Prepared Statements**: Parameterized queries with plan reuse

### Advanced Features

#### 🔍 Vector Similarity Search
- Multiple distance metrics (Cosine, Euclidean, Dot Product, Manhattan)
- Brute-force and approximate IVF search
- K-means clustering acceleration
- Hybrid vector + keyword search
- GPU acceleration support

#### 🌍 Geospatial Queries
- Point, polygon, and bounding box operations
- Distance and nearest-neighbor calculations
- Spatial indexing for efficient lookups
- GeoJSON-compatible data model

#### ⏱️ Time-Series Data
- Hypertable abstraction with automatic time-based partitioning
- `time_bucket()` aggregations (1m, 5m, 15m, 1h, 1d, 1w, 30d)
- TTL-based retention policies with automatic cleanup
- Downsampling for historical data
- Optimized time-range queries with partition pruning

#### 🏢 Multi-Tenant Architecture
- Namespace isolation per tenant
- Resource quotas (storage, queries/minute, connections, tables)
- Row-level security (RLS) policies
- Tenant-aware backup/restore operations

#### 📡 Change Data Capture (CDC)
- Ordered change events (INSERT, UPDATE, DELETE)
- Multiple output formats: JSON, Avro, Protobuf
- Configurable consumer filtering by table/operation
- Kafka connector for event streaming
- Snapshot initialization for new consumers

#### 📊 Materialized Views
- Automatic query rewriting for optimization
- Full and incremental refresh strategies
- Change tracking for efficient updates
- Scheduled refresh with `REFRESH SCHEDULE`
- Query result caching

#### 🛡️ Security & Compliance
- **Audit Logging**: Tamper-evident logs with hash chains and risk scoring
- **AES-256 Encryption**: Data encryption at rest
- **Column-Level Encryption**: Per-column encryption for sensitive fields
- **RBAC**: Hierarchical roles with fine-grained permissions
- **SQL Injection Detection**: Pattern analysis and query validation
- **Compliance Reporting**: GDPR, SOX, PCI DSS reports

#### 🔧 Operations & Management
- **Schema Migrations**: Versioned schema changes with rollback
- **Metrics & Monitoring**: Prometheus-compatible metrics and health checks
- **Connection Pooling**: Managed connection lifecycle
- **Compression**: Transparent storage compression
- **Session Recovery**: Persistent sessions with automatic recovery
- **Agent Protocol**: Inter-agent communication for distributed coordination

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   CLI Client    │────▶│  Socket Server  │────▶│    LevelDB      │
│   / Web API     │     │  (TLS-enabled)  │     │   Storage       │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
        ┌─────────┬─────────┬─────────┬─────────┬─────────┐
        ▼         ▼         ▼         ▼         ▼         ▼
   ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
   │ SQL    │ │ Query  │ │Storage │ │Time-   │ │Multi-  │ │Security│
   │Parser  │ │Optimizer│ │Engine  │ │Series  │ │Tenant  │ │        │
   └────────┘ └────────┘ └────────┘ └────────┘ └────────┘ └────────┘
        │         │         │         │         │         │
   ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
   │CDC     │ │Material│ │Vector  │ │Geo-    │ │Schema  │ │Metrics │
   │        │ │Views   │ │Search  │ │spatial │ │Migrate │ │        │
   └────────┘ └────────┘ └────────┘ └────────┘ └────────┘ └────────┘
        │                                              │
   ┌────────┐                                   ┌────────┐
   │ Kafka  │                                   │Replication│
   │Connector│                                  │ & Failover│
   └────────┘                                   └────────┘
```

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/m5it/KosDB.git
cd KosDB

# Install dependencies
pip install -r requirements.txt

# Or install as package
pip install -e .
```

### Start the Server

```bash
# Basic start
python server.py --data-dir ./data --port 5555

# With TLS
python server.py --data-dir ./data --port 5555 --tls --tls-cert ./server.crt --tls-key ./server.key

# As slave with replication
python server.py --data-dir ./data --port 5556 --role slave --master-host localhost:5555
```

### Setup Admin User

```bash
python server.py --data-dir ./data --prepare_admin admin --prepare_password secret
```

### Connect with CLI

```bash
python cli.py -H localhost -P 5555 -u admin -p secret
```

## Commands

### Database Operations
- `CREATE DATABASE <name>` — Create a new database
- `DROP DATABASE <name>` — Delete a database
- `USE <database>` — Select current database
- `SHOW DATABASES` — List all databases

### Table Operations
- `CREATE TABLE <name> (col1, col2, ...)` — Create table
- `DROP TABLE <name>` — Delete table
- `SHOW TABLES` — List tables in current database
- `CREATE INDEX <name> ON <table> (column)` — Create index
- `CREATE VECTOR INDEX <name> ON <table> (column)` — Create vector index

### Data Operations
- `INSERT INTO <table> VALUES (v1, v2, ...)` — Insert row
- `SELECT * FROM <table> [WHERE ...] [ORDER BY ...] [LIMIT n]` — Query data
- `UPDATE <table> SET col=v WHERE ...` — Update rows
- `DELETE FROM <table> WHERE ...` — Delete rows

### Transactions
- `BEGIN` — Start transaction
- `COMMIT` — Commit transaction
- `ROLLBACK` — Rollback transaction
- `DIST_TX_BEGIN <ops_json>` — Start distributed transaction

### Time-Series
- `CREATE HYPERTABLE <name> CHUNK_INTERVAL <interval> RETENTION <days>` — Create time-series table
- `INSERT INTO <hypertable> VALUES (timestamp, value, tags)` — Insert time-series point
- `TIME_BUCKET('<size>', <table>, <aggregation>)` — Aggregate by time window
- `DOWNSAMPLE <table> FROM <source> TO <target>` — Reduce granularity
- `RETENTION POLICY APPLY <table>` — Apply TTL cleanup

### Multi-Tenant
- `CREATE TENANT <id> NAME <name> [STORAGE <gb>] [QPM <n>] [CONNECTIONS <n>]` — Create tenant
- `DROP TENANT <id>` — Remove tenant
- `USE TENANT <id>` — Switch context
- `LIST TENANTS` — Show all tenants
- `SET TENANT QUOTA <id> STORAGE <gb> QPM <n>` — Update quotas
- `ADD ROW POLICY <tenant> <name> ON <pattern> CONDITION <expr>` — Add RLS policy

### Change Data Capture
- `CDC START CONSUMER <id> [TABLES <list>] [OPS <list>] [FORMAT <format>] [FROM_LATEST]` — Start CDC
- `CDC STOP CONSUMER <id>` — Stop consumer
- `CDC LIST CONSUMERS` — Show active consumers
- `CDC SETUP KAFKA <servers> [PREFIX <prefix>]` — Configure Kafka
- `CDC SNAPSHOT <tables>` — Create data snapshot

### Materialized Views
- `CREATE MATERIALIZED VIEW <name> AS <query> [STRATEGY full|incremental|auto] [SCHEDULE manual|on_commit|every_n_minutes INTERVAL <min>]` — Create view
- `REFRESH MATERIALIZED VIEW <name> [STRATEGY <type>]` — Refresh view
- `REFRESH ALL MATERIALIZED VIEWS` — Refresh all views
- `SET REFRESH SCHEDULE <name> SCHEDULE <type> [INTERVAL <min>]` — Configure schedule

### Security
- `AUDIT LOG [USER <user>] [TYPE <type>] [RISK <min>]` — Query audit log
- `EXPORT AUDIT LOG [FORMAT json|csv]` — Export audit data
- `GRANT ROLE <user> <role>` — Assign role
- `REVOKE ROLE <user> <role>` — Remove role
- `CHECK PERMISSION <user> <permission>` — Verify access
- `ENCRYPT COLUMN <table> <column> <value>` — Encrypt data
- `DECRYPT COLUMN <table> <column> <ciphertext>` — Decrypt data
- `VALIDATE PASSWORD <password>` — Check password strength
- `CHECK SQL INJECTION <query>` — Analyze for injection
- `COMPLIANCE REPORT <GDPR|SOX|PCI> [DAYS <n>]` — Generate compliance report
- `SECURITY STATS` — Show security statistics
- `HIGH RISK EVENTS [THRESHOLD <n>]` — Show security alerts

### Vector Search
- `CREATE VECTOR INDEX <name> ON <table> (column)` — Create vector index
- `VECTOR ADD <index> <id> <text>` — Add document
- `VECTOR SEARCH <index> WITH <query> [K <n>]` — Semantic search
- `VECTOR DELETE <index> <id>` — Remove document

### Geospatial
- `GEO ADD <index> <id> <lat> <lon> [metadata]` — Add point
- `GEO SEARCH <index> NEAR <lat> <lon> RADIUS <km>` — Radius search
- `GEO NEAREST <index> <lat> <lon> [K <n>]` — Nearest neighbors
- `GEO BBOX <index> <lat1> <lon1> <lat2> <lon2>` — Bounding box search

### Schema Migration
- `MIGRATE CREATE <description>` — Create new migration
- `MIGRATE UP` — Apply pending migrations
- `MIGRATE DOWN` — Rollback last migration
- `MIGRATE STATUS` — Show migration status

### Backup & Restore
- `BACKUP DATABASE <db> TO <file>` — Backup database
- `RESTORE DATABASE <db> FROM <file>` — Restore database
- `BACKUP TABLE <t> TO <file>` — Backup single table
- `SHOW BACKUPS [path]` — List backups
- `VERIFY BACKUP <file>` — Check integrity

### Replication & Failover
- `FAILOVER STATUS` — Show cluster status
- `FAILOVER PROPOSE <cmd>` — Propose command through Raft

### Monitoring & Pooling
- `METRICS` — Show system metrics
- `POOL STATUS` — Show connection pool status
- `HEALTH` — Show health check status

## Configuration

KosDB uses JSON configuration via `config.json`:

```json
{
  \"version\": \"2.2.0\",\n  \"server\": {\n    \"host\": \"0.0.0.0\",\n    \"port\": 9999,\n    \"data_dir\": \"./data\",\n    \"max_connections\": 100,\n    \"connection_timeout\": 30,\n    \"request_timeout\": 60\n  },\n  \"tls\": {\n    \"enabled\": false,\n    \"cert_file\": \"./certs/server.crt\",\n    \"key_file\": \"./certs/server.key\",\n    \"ca_file\": null,\n    \"require_client_cert\": false\n  },\n  \"cache\": {\n    \"enabled\": true,\n    \"max_size\": 1000,\n    \"default_ttl\": 300,\n    \"invalidate_on_write\": true\n  },\n  \"vector_search\": {\n    \"enabled\": true,\n    \"default_dimension\": 384,\n    \"metric\": \"cosine\",\n    \"use_gpu\": false\n  },\n  \"replication\": {\n    \"enabled\": false,\n    \"role\": \"master\",\n    \"slaves\": [],\n    \"replication_port\": null\n  },\n  \"failover\": {\n    \"enabled\": false,\n    \"node_id\": \"node1\",\n    \"peers\": [],\n    \"raft_port\": 9000\n  },\n  \"monitoring\": {\n    \"enabled\": true,\n    \"http_port\": 9090,\n    \"metrics_path\": \"/metrics\",\n    \"health_path\": \"/health\"\n  },\n  \"security\": {\n    \"encryption_at_rest\": true,\n    \"audit_logging\": true,\n    \"sql_injection_detection\": true,\n    \"password_policy\": {\n      \"min_length\": 8,\n      \"require_uppercase\": true,\n      \"require_lowercase\": true,\n      \"require_digits\": true,\n      \"require_special\": true\n    }\n  },\n  \"timeseries\": {\n    \"default_chunk_interval\": 86400,\n    \"retention_check_interval\": 3600\n  }\n}\n```

See `CONFIGURATION.md` for complete configuration reference.

## Testing

Run individual test suites:

```bash
# Core database
python test_parser.py
python test_query_cache.py
python test_concurrent_index.py
python test_distributed_tx.py

# v2.0 features
python test_agent_protocol.py
python test_command_parser.py
python test_validation.py
python test_session_recovery.py
python test_query_optimizer.py
python test_streaming_results.py
python test_metrics_monitoring.py
python test_write_ahead_log.py
python test_schema_migration.py
python test_vector_search.py

# v2.2 features
python test_timeseries.py
python test_multitenant.py
python test_cdc.py
python test_materialized_views.py
python test_security.py
python test_geospatial.py
python test_connection_pool.py
python test_compression.py
python test_prepared_statements.py
```

See `TESTING.md` for detailed testing instructions.

## Module Documentation

- `SQL_README.md` — SQL Parser documentation
- `PLANNER_README.md` — Query Planner documentation
- `STORAGE_README.md` — Storage Engine documentation
- `REPLICATION_README.md` — Replication documentation
- `TIMESERIES_README.md` — Time-Series documentation
- `MULTITENANT_README.md` — Multi-Tenant documentation
- `CDC_README.md` — Change Data Capture documentation
- `MV_README.md` — Materialized Views documentation
- `SECURITY_README.md` — Security Features documentation
- `GEOSPATIAL_README.md` — Geospatial Queries documentation
- `CONNECTION_POOL_README.md` — Connection Pooling documentation
- `COMPRESSION_README.md` — Compression documentation
- `PREPARED_STATEMENTS_README.md` — Prepared Statements documentation
- `CONFIGURATION.md` — Configuration reference
- `TESTING.md` — Testing guide

## Project Structure

```
KosDB/
├── server.py              # TCP socket server
├── cli.py                 # Command-line client
├── database.py            # LevelDB wrapper and core storage
├── auth.py                # Authentication and authorization
├── parser.py              # SQL parser
├── commands.py            # Command registry and execution
├── query_optimizer.py     # Query planning and optimization
├── concurrent_index.py    # Online index operations
├── write_ahead_log.py     # WAL and ARIES recovery
├── replication.py         # Master-slave replication
├── failover.py            # Raft-based failover
├── distributed_tx.py      # Two-phase commit
├── schema_migration.py    # Schema versioning
├── vector_search.py       # Vector similarity search
├── fulltext_search.py     # Full-text indexing
├── geospatial.py          # Geospatial queries
├── timeseries.py          # Time-series engine
├── multitenant.py         # Multi-tenant management
├── cdc.py                 # Change data capture
├── materialized_views.py  # Materialized views
├── security.py            # Security suite
├── compression.py         # Data compression
├── connection_pool.py     # Connection pooling
├── prepared_statements.py # Prepared statements
├── session_recovery.py  # Session persistence
├── agent_protocol.py      # Inter-agent protocol
├── monitoring.py          # Metrics and health
├── *_commands.py          # Command handlers per feature
├── *_parser.py            # SQL parsers per feature
├── *_README.md            # Feature documentation
├── test_*.py              # Unit tests
├── config*.json           # Configuration files
└── README.md              # This file
```

## Performance

- Query optimization reduces execution time by 30-50%
- Concurrent indexing eliminates table locking during index builds
- Streaming results handle datasets larger than available memory
- Vector search (IVF) achieves 10x speedup over brute-force search
- WAL provides sub-millisecond durability guarantees
- Time-series partitioning enables efficient range scans
- Materialized views accelerate analytical queries with caching

## License

MIT License — see LICENSE file for details.

## Contributing

Contributions are welcome! Please read `CONTRIBUTING.md` for guidelines.

## Support

For issues and questions, please use the GitHub issue tracker at https://github.com/m5it/KosDB/issues.
