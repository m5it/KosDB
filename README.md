# KosDB - Distributed Database System

[![Version](https://img.shields.io/badge/version-2.0.0-blue.svg)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A high-performance, distributed database system built on LevelDB with support for replication, transactions, failover, monitoring, and advanced features including vector similarity search and schema migrations.

## Features

### Core Database
- **Socket-based Protocol**: Fast binary protocol over TCP
- **ACID Transactions**: Full transaction support with BEGIN/COMMIT/ROLLBACK
- **Distributed Transactions**: Two-Phase Commit (2PC) for multi-node consistency
- **Master-Slave Replication**: Asynchronous replication with binlog
- **Automatic Failover**: Raft consensus for leader election

### Advanced Features (v2.0)
- **🔌 Agent Protocol** - Inter-agent communication with capability registry and task delegation
- **⚡ Command Parser** - Full SQL parser with statement validation and parameter extraction
- **🛡️ Input Validation** - Schema-based validation with type checking and sanitization
- **💾 Session Recovery** - Persistent sessions with automatic recovery and integrity checking
- **⚙️ Query Optimizer** - Cost-based execution planning with index advisor
- **📊 Concurrent Index** - Online index building without blocking reads/writes
- **🌊 Streaming Results** - Progressive result streaming for large datasets
- **📈 Metrics & Monitoring** - Prometheus-compatible metrics with health checks
- **📝 Write-Ahead Log** - Durable transaction logging with ARIES recovery
- **🔄 Schema Migration** - Versioned schema changes with rollback support
- **🔍 Vector Search** - Semantic similarity search using embeddings

### Operations
- **Backup & Restore**: Compressed JSON backups with integrity checking
- **Schema Migrations**: Versioned database migrations with rollback
- **Vector Search**: AI-powered semantic search with multiple distance metrics

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
python server.py --data-dir ./data --port 5555
```

### Connect with CLI

```bash
python cli.py -H localhost -P 5555 -u admin -p secret
```

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   CLI Client    │────▶│  Socket Server  │────▶│    LevelDB      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
        ┌─────────┬─────────┬─────────┬─────────┬─────────┐
        ▼         ▼         ▼         ▼         ▼         ▼
   ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
   │ Agent  │ │ Query  │ │Stream  │ │Vector  │ │Schema  │ │Metrics │
   │Protocol│ │Optimize│ │Results │ │ Search │ │Migrate │ │        │
   └────────┘ └────────┘ └────────┘ └────────┘ └────────┘ └────────┘
```

## Commands

### Database Operations
- `CREATE DATABASE <name>` - Create a new database
- `DROP DATABASE <name>` - Delete a database
- `USE <database>` - Select current database
- `SHOW DATABASES` - List all databases

### Table Operations
- `CREATE TABLE <name> (col1, col2, ...)` - Create table
- `DROP TABLE <name>` - Delete table
- `SHOW TABLES` - List tables in current database

### Data Operations
- `INSERT INTO <table> VALUES (v1, v2, ...)` - Insert row
- `SELECT * FROM <table> [WHERE ...] [ORDER BY ...]` - Query data
- `UPDATE <table> SET col=v WHERE ...` - Update rows
- `DELETE FROM <table> WHERE ...` - Delete rows

### Transactions
- `BEGIN` - Start transaction
- `COMMIT` - Commit transaction
- `ROLLBACK` - Rollback transaction

### Vector Search (New in v2.0)
- `CREATE VECTOR INDEX <name> ON <table> (column)` - Create vector index
- `VECTOR SEARCH <index> WITH <query> [K <n>]` - Semantic search
- `VECTOR ADD <index> <id> <text>` - Add document to index
- `VECTOR DELETE <index> <id>` - Remove from index

### Schema Migration (New in v2.0)
- `MIGRATE CREATE <description>` - Create new migration
- `MIGRATE UP` - Apply pending migrations
- `MIGRATE DOWN` - Rollback last migration
- `MIGRATE STATUS` - Show migration status

### Backup & Restore
- `BACKUP DATABASE <db> TO <file>` - Backup database
- `RESTORE DATABASE <db> FROM <file>` - Restore database
- `BACKUP TABLE <t> TO <file>` - Backup single table
- `SHOW BACKUPS [path]` - List backups
- `VERIFY BACKUP <file>` - Check integrity

### Distributed Transactions
- `DIST_TX_BEGIN <ops_json>` - Start distributed transaction
- `DIST_TX_STATUS <tx_id>` - Check transaction status
- `DIST_TX_LIST` - List all distributed transactions

### Failover & Clustering
- `FAILOVER STATUS` - Show cluster status
- `FAILOVER PROPOSE <cmd>` - Propose command through Raft

### Monitoring
- `METRICS` - Show system metrics
- `HEALTH` - Run health checks
- `PROMETHEUS` - Export Prometheus format

### Replication (Admin)
- `SHOW MASTER STATUS` - Show binlog position
- `SHOW SLAVE STATUS` - Show replication status
- `START SLAVE` - Start replication
- `STOP SLAVE` - Stop replication
- `RESET SLAVE` - Reset replication

## Configuration

### Server Configuration

Create `config.json`:

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 5555,
    "data_dir": "./data",
    "max_connections": 100
  },
  "replication": {
    "enabled": true,
    "role": "master",
    "slaves": [
      {"host": "slave1.example.com", "port": 5555}
    ]
  },
  "failover": {
    "enabled": true,
    "node_id": "node1",
    "peers": [
      {"id": "node2", "host": "192.168.1.2", "port": 9000},
      {"id": "node3", "host": "192.168.1.3", "port": 9000}
    ]
  },
  "monitoring": {
    "enabled": true,
    "http_port": 9090
  },
  "vector_search": {
    "enabled": true,
    "default_dimension": 384,
    "metric": "cosine"
  },
  "migrations": {
    "directory": "./migrations",
    "auto_apply": false
  }
}
```

## New Features in v2.0

### 🔍 Vector Similarity Search
```sql
-- Create a vector index for semantic search
CREATE VECTOR INDEX articles_idx ON articles (content);

-- Add documents
VECTOR ADD articles_idx 1 "Python is a programming language";
VECTOR ADD articles_idx 2 "Machine learning uses neural networks";

-- Search semantically
VECTOR SEARCH articles_idx WITH "programming languages" K 5;
```

### 🔄 Schema Migrations
```bash
# Create a migration
python -m kosdb migrate create "Add users table"

# Apply migrations
python -m kosdb migrate up

# Rollback
python -m kosdb migrate down

# Check status
python -m kosdb migrate status
```

### ⚙️ Query Optimization
```sql
-- Get execution plan
EXPLAIN SELECT * FROM users WHERE age > 25;

-- Get index recommendations
ANALYZE TABLE users;
```

### 🌊 Streaming Results
```python
# Stream large results without memory issues
for chunk in db.stream_query("SELECT * FROM large_table"):
    process(chunk)
```

## Replication Setup

### 1. Configure Master

```bash
python server.py --role master --binlog-dir ./binlog
```

### 2. Create Replication User

```sql
CREATE REPLICATION USER replicator IDENTIFIED BY 'secret';
```

### 3. Configure Slave

```bash
python server.py --role slave --master-host master.example.com --master-port 5555 --repl-user replicator --repl-pass secret
```

## Failover Setup

### 3-Node Cluster Example

Node 1 (192.168.1.1):
```bash
python server.py --node-id node1 --raft-port 9000 --peers node2:192.168.1.2:9000,node3:192.168.1.3:9000
```

Node 2 (192.168.1.2):
```bash
python server.py --node-id node2 --raft-port 9000 --peers node1:192.168.1.1:9000,node3:192.168.1.3:9000
```

Node 3 (192.168.1.3):
```bash
python server.py --node-id node3 --raft-port 9000 --peers node1:192.168.1.1:9000,node2:192.168.1.2:9000
```

## Monitoring

### Prometheus Endpoint

Metrics are exposed at `http://localhost:9090/metrics`

Key metrics:
- `queries_total` - Total queries executed
- `queries_duration_seconds` - Query latency histogram
- `system_cpu_percent` - CPU usage
- `system_memory_rss_bytes` - Memory usage
- `connections_total` - Connection count
- `vector_search_latency_seconds` - Vector search latency
- `migration_duration_seconds` - Migration timing

### Health Checks

Check health at `http://localhost:9090/health`

## Testing

Run all tests:

```bash
python -m pytest tests/ -v
```

Run specific component tests:

```bash
python -m pytest test_agent_protocol.py -v
python -m pytest test_command_parser.py -v
python -m pytest test_validation.py -v
python -m pytest test_session_recovery.py -v
python -m pytest test_query_optimizer.py -v
python -m pytest test_concurrent_index.py -v
python -m pytest test_streaming_results.py -v
python -m pytest test_metrics_monitoring.py -v
python -m pytest test_write_ahead_log.py -v
python -m pytest test_distributed_tx.py -v
python -m pytest test_schema_migration.py -v
python -m pytest test_vector_search.py -v
```

## Performance

Benchmark results on a typical server:
- Single-node: ~50,000 ops/sec
- With replication: ~40,000 ops/sec
- Distributed transactions: ~5,000 tx/sec
- Vector search (brute force): ~1,000 queries/sec
- Vector search (IVF): ~10,000 queries/sec

## Security

- All connections use TCP with optional TLS
- Password-based authentication
- Role-based access control (admin/user)
- Replication user with limited privileges
- Input validation and SQL injection protection

## What's New in v2.0.0

See [CHANGELOG.md](CHANGELOG.md) for detailed release notes.

### Highlights
- ✅ **Agent Protocol** - Inter-agent communication with capability registry
- ✅ **Command Parser** - Full SQL parser with validation
- ✅ **Input Validation** - Schema-based validation and sanitization
- ✅ **Session Recovery** - Persistent sessions with automatic recovery
- ✅ **Query Optimizer** - Cost-based execution planning
- ✅ **Concurrent Index** - Online index building
- ✅ **Streaming Results** - Progressive result streaming
- ✅ **Metrics & Monitoring** - Prometheus-compatible metrics
- ✅ **Write-Ahead Log** - Durable transaction logging
- ✅ **Distributed Transactions** - Two-Phase Commit (2PC)
- ✅ **Schema Migration** - Versioned schema changes with rollback
- ✅ **Vector Search** - Semantic similarity search with embeddings

## Development

### Project Structure

```
.
├── server.py              # Main server entry point
├── cli.py                 # Command-line client
├── database.py            # Database operations
├── commands.py            # Command handlers
├── parser.py              # SQL parser
├── auth.py                # Authentication
├── replication.py         # Replication system
├── binlog.py              # Binary logging
├── distributed_tx.py      # Distributed transactions
├── failover.py            # Raft failover
├── monitoring.py          # Metrics and health
├── agent_protocol.py      # Agent communication
├── command_parser.py      # SQL parsing
├── validation.py          # Input validation
├── session_recovery.py    # Session persistence
├── query_optimizer.py     # Query optimization
├── concurrent_index.py    # Online indexing
├── streaming_results.py   # Result streaming
├── metrics_monitoring.py  # Metrics collection
├── write_ahead_log.py     # WAL implementation
├── schema_migration.py    # Schema migrations
├── vector_search.py       # Vector similarity search
├── tests/                 # Test suite
├── README.md              # This file
├── CHANGELOG.md           # Release notes
├── requirements.txt       # Dependencies
└── setup.py               # Package setup
```

### Component Overview

| Component | File | Description |
|-----------|------|-------------|
| Agent Protocol | `agent_protocol.py` | Inter-agent messaging with capability registry |
| Command Parser | `command_parser.py` | Full SQL tokenizer and parser |
| Input Validation | `validation.py` | Schema-based validation framework |
| Session Recovery | `session_recovery.py` | Persistent session management |
| Query Optimizer | `query_optimizer.py` | Cost-based query planning |
| Concurrent Index | `concurrent_index.py` | Online index operations |
| Streaming Results | `streaming_results.py` | Progressive result delivery |
| Metrics | `metrics_monitoring.py` | Prometheus-compatible metrics |
| Write-Ahead Log | `write_ahead_log.py` | ARIES-style WAL |
| Distributed TX | `distributed_tx.py` | Two-phase commit coordinator |
| Schema Migration | `schema_migration.py` | Versioned schema changes |
| Vector Search | `vector_search.py` | Semantic similarity search |

### Adding New Commands

1. Add pattern to `parser.py`
2. Implement command in `commands.py`
3. Register in `CommandRegistry`
4. Add tests in appropriate test file

## Version History

- **v2.0.0** (2026-01-09) - Major release with 12 advanced features
- **v1.0.0** (2026-01-09) - Initial release with core features

## Roadmap

- **v2.1.0** - TLS encryption, query caching improvements, GPU-accelerated vector search
- **v2.2.0** - Multi-region replication, automatic sharding, vector quantization
- **v3.0.0** - SQL compatibility layer, stored procedures, triggers

## License

MIT License - See [LICENSE](LICENSE) file for details

## Contributing

1. Fork the repository (`https://github.com/m5it/KosDB/fork`)
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Add tests for new functionality
4. Commit your changes (`git commit -m 'Add amazing feature'`)
5. Push to the branch (`git push origin feature/amazing-feature`)
6. Open a Pull Request

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and development process.

## Support

- 📖 Documentation: https://kosdb.readthedocs.io
- 🐛 Issues: https://github.com/m5it/KosDB/issues
- 💬 Discussions: https://github.com/m5it/KosDB/discussions
- 📧 Email: w4d4f4k@gmail.com

## Acknowledgments

- LevelDB - Fast key-value storage library
- Plyvel - Python LevelDB bindings
- Raft consensus algorithm - Diego Ongaro and John Ousterhout

---

<p align="center">
  Made with ❤️ by the Development Team
</p>
