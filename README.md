# LevelDB Socket Server - Distributed Database System

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A high-performance, distributed database system built on LevelDB with support for replication, transactions, failover, and monitoring.

## Features

- **Socket-based Protocol**: Fast binary protocol over TCP
- **ACID Transactions**: Full transaction support with BEGIN/COMMIT/ROLLBACK
- **Distributed Transactions**: Two-Phase Commit (2PC) for multi-node consistency
- **Master-Slave Replication**: Asynchronous replication with binlog
- **Automatic Failover**: Raft consensus for leader election
- **Backup & Restore**: Compressed JSON backups with integrity checking
- **Monitoring**: Prometheus-compatible metrics and health checks
- **Authentication**: Role-based access control

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/leveldb-socket-server.git
cd leveldb-socket-server

# Install dependencies
pip install -r requirements.txt

# Or install as package
pip install -e .
```
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
                    ┌─────────┼─────────┐
                    ▼         ▼         ▼
              ┌────────┐ ┌────────┐ ┌────────┐
              │Replication│ │Failover │ │Metrics │
              └────────┘ └────────┘ └────────┘
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
  }
}
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

## What's New in v1.0.0

See [CHANGELOG.md](CHANGELOG.md) for detailed release notes.

### Highlights
- ✅ **Complete ACID Transactions** - Full BEGIN/COMMIT/ROLLBACK support
- ✅ **Distributed Transactions** - 2PC for multi-node consistency  
- ✅ **Master-Slave Replication** - Asynchronous replication with binlog
- ✅ **Raft Failover** - Automatic leader election and failover
- ✅ **Prometheus Metrics** - Built-in monitoring and health checks
- ✅ **Backup & Restore** - Compressed backups with integrity verification
- ✅ **Interactive CLI** - Feature-rich command-line client

## Development

### Project Structure

```
.
├── server.py           # Main server entry point
├── cli.py             # Command-line client
├── database.py        # Database operations
├── commands.py        # Command handlers
├── parser.py          # SQL parser
├── auth.py            # Authentication
├── replication.py     # Replication system
├── binlog.py          # Binary logging
├── distributed_tx.py  # Distributed transactions
├── failover.py        # Raft failover
├── monitoring.py      # Metrics and health
├── test_integration.py # Integration tests
├── README.md          # This file
├── CHANGELOG.md       # Release notes
├── requirements.txt   # Dependencies
└── setup.py          # Package setup
```

### Adding New Commands

1. Add pattern to `parser.py`
2. Implement command in `commands.py`
3. Register in `CommandRegistry`
4. Add tests in `test_integration.py`

## Version History

- **v1.0.0** (2025-01-09) - Initial release with all core features

## Roadmap

- **v1.1.0** - TLS encryption, query caching, secondary indexes
- **v1.2.0** - Multi-region replication, automatic sharding
- **v2.0.0** - SQL compatibility, stored procedures, triggers

## License

MIT License - See [LICENSE](LICENSE) file for details

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Add tests for new functionality
4. Commit your changes (`git commit -m 'Add amazing feature'`)
5. Push to the branch (`git push origin feature/amazing-feature`)
6. Open a Pull Request

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and development process.

## Support

- 📖 Documentation: https://leveldb-server.readthedocs.io
- 🐛 Issues: https://github.com/yourusername/leveldb-server/issues
- 💬 Discussions: https://github.com/yourusername/leveldb-server/discussions

## Acknowledgments

- LevelDB - Fast key-value storage library
- Plyvel - Python LevelDB bindings
- Raft consensus algorithm - Diego Ongaro and John Ousterhout

---

<p align="center">
  Made with ❤️ by the Development Team
</p>
- Distributed transactions: ~5,000 tx/sec

## Security

- All connections use TCP with optional TLS
- Password-based authentication
- Role-based access control (admin/user)
- Replication user with limited privileges

## Troubleshooting

### Connection Refused
- Check server is running: `python server.py --status`
- Verify firewall rules
- Check port availability

### Replication Lag
- Check network latency between nodes
- Monitor binlog size
- Consider increasing batch size

### Failover Issues
- Verify Raft ports are accessible
- Check node connectivity: `FAILOVER STATUS`
- Review logs for election timeouts

## Development

### Project Structure

```
.
├── server.py           # Main server entry point
├── cli.py             # Command-line client
├── database.py        # Database operations
├── commands.py        # Command handlers
├── parser.py          # SQL parser
├── auth.py            # Authentication
├── replication.py     # Replication system
├── distributed_tx.py  # Distributed transactions
├── failover.py        # Raft failover
├── monitoring.py      # Metrics and health
└── tests/             # Test suite
```

### Adding New Commands

1. Add pattern to `parser.py`
2. Implement command in `commands.py`
3. Register in `CommandRegistry`
4. Add tests

## License

MIT License - See LICENSE file for details

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## Support

- GitHub Issues: https://github.com/m5it/KosDB/issues
- Documentation: https://kosdb.readthedocs.io
- Email: w4d4f4k@gmail.com
