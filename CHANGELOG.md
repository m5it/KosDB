# Changelog

All notable changes to the LevelDB Socket Server project will be documented in this file.

## [Unreleased]

## [2.0.0] - 2024-XX-XX - Replication Release

### Added
- **Master-Slave Replication** - One master server with multiple slave replicas
- **Master-Master Replication** - Bi-directional replication between peers
- **Binary Log (Binlog)** - All write operations logged for replication
- **Automatic Recovery** - Slaves reconnect and catch up on missed data
- **Replication Protocol** - TCP-based streaming with position tracking
- **Replication Commands:**
  - `SHOW MASTER STATUS` - Display binlog position and connected slaves
  - `SHOW SLAVE STATUS` - Display replication status and lag
  - `START SLAVE` - Begin replication
  - `STOP SLAVE` - Pause replication
  - `RESET SLAVE` - Clear position and restart
  - `CREATE REPLICATION USER` - Create replication-only accounts
- **Replication Configuration:**
  - `--server-id` - Unique server identifier
  - `--role` - Master or slave role
  - `--master-host` - Master connection for slaves
  - `--replication-port` - Port for replication connections
  - `--peer-host` - Peer server for master-master setup
- **Replication Testing Suite** - Automated tests for replication scenarios
- **TESTING.md** - Comprehensive testing documentation

### Changed
- Enhanced server.py with replication support
- Database class now integrates with binlog for all write operations
- CommandRegistry accepts replication_client parameter
- Server initialization includes replication component setup

### Technical Details
- Binlog stored in LevelDB (data/_binlog)
- Position-based replication tracking
- Exponential backoff on connection failures
- Loop prevention via server-id filtering
- Heartbeat messages for connection health

## [1.1.0] - 2024-XX-XX - Authentication & Privileges

### Added
- **Database-Backed Authentication** - User accounts stored in LevelDB
- **Password Hashing** - SHA-256 with unique salt per user
- **Session Management** - Token-based authentication with `secrets.token_hex()`
- **Privilege System** - Role-based access control
- **Admin Users** - Full access to all databases and tables
- **Regular Users** - Database/table-specific permissions
- **Privilege Commands:**
  - `SHOW USERS` - List all users (admin only)
  - `GRANT` system for permissions
- **Admin User Creation:**
  - `--prepare_admin` command-line option
  - `--prepare_password` for non-interactive setup

### Changed
- Server now requires authentication before accepting commands
- All commands check user privileges
- Database operations respect access controls

## [1.0.0] - 2024-XX-XX - Initial Release

### Added
- **Threaded TCP Socket Server** - Handles multiple concurrent clients
- **LevelDB Backend** - Persistent key-value storage
- **SQL-like Commands:**
  - `CREATE DATABASE` / `DROP DATABASE`
  - `USE <database>` - Database selection
  - `CREATE TABLE` / `DROP TABLE`
  - `INSERT INTO` - Row insertion
  - `SELECT` with WHERE, ORDER BY
  - `UPDATE` with SET and WHERE
  - `DELETE FROM` with WHERE
  - `SHOW TABLES` / `SHOW DATABASES`
  - `HELP` / `QUIT`
- **Table Features:**
  - Primary key support
  - Index columns for fast queries
  - WHERE clause filtering
  - ORDER BY sorting (ASC/DESC)
- **Netcat Compatible** - Simple text protocol
- **Command Parser** - SQL-like syntax parsing
- **Command Framework** - Extensible command system

### Project Structure
```
t10/
├── server.py       # Main server entry
├── database.py     # LevelDB wrapper
├── parser.py       # Command parser
├── commands.py     # Command implementations
├── tests/          # Test suite
└── README.md       # Documentation
```

## Version Format

Version numbers follow [Semantic Versioning](https://semver.org/):

- **MAJOR** - Incompatible API changes
- **MINOR** - Backwards-compatible functionality
- **PATCH** - Backwards-compatible bug fixes

## Future Roadmap

### Planned Features
- [ ] SSL/TLS encryption for connections
- [ ] Backup and restore functionality
- [ ] Query caching for improved performance
- [ ] Monitoring dashboard (web UI)
- [ ] Clustering with automatic failover
- [ ] Multi-datacenter replication
- [ ] Read replicas for load balancing
- [ ] Query logging and slow query analysis

### Under Consideration
- [ ] SQL transaction support (BEGIN/COMMIT/ROLLBACK)
- [ ] Stored procedures
- [ ] Triggers
- [ ] Foreign key constraints
- [ ] Full-text search indexing

---

## Contributing

When adding new features:
1. Update the [Unreleased] section
2. Add version bump when releasing
3. Document breaking changes clearly
4. Include migration notes if needed

## Release Checklist

- [ ] Update CHANGELOG.md
- [ ] Update version in server.py
- [ ] Update README.md if needed
- [ ] Run all tests
- [ ] Create git tag
- [ ] Update documentation