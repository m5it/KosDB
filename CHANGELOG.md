# Changelog

All notable changes to KosDB will be documented in this file.

## [3.1.0] - 2024-01-15

### Added

#### Security Features
- **TLS/SSL Encryption**: Full support for TLS 1.2 and TLS 1.3 with certificate-based authentication
- **At-Rest Encryption**: AES-256-GCM encryption for database files with PBKDF2 key derivation
- **Master Key Rotation**: Support for rotating encryption keys without downtime
- **Audit Logging**: Comprehensive audit trail with multiple output targets (file, syslog, webhook)
- **Log Rotation**: Automatic log rotation with compression for audit logs

#### GPU Acceleration
- **CUDA Support**: GPU-accelerated query processing for large datasets
- **Vector Operations**: CUDA kernels for vector mathematical operations
- **Matrix Multiplication**: GPU-accelerated matrix operations
- **Sorting**: High-performance GPU sorting algorithms
- **Memory Management**: Configurable GPU memory fraction and device selection

#### Authentication & Authorization
- **Role-Based Access Control (RBAC)**: Create roles and assign to users
- **Granular Permissions**: Support for SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, INDEX, ADMIN
- **Column-Level Security**: Restrict access to specific columns
- **Permission Caching**: Performance-optimized permission checking with TTL
- **Session Management**: JWT-based sessions with configurable TTL

#### Backup Enhancements
- **Encrypted Backups**: Password-protected backups with AES-256-GCM
- **Multiple Compression**: Support for gzip, lz4, and zstd compression algorithms
- **Backup Integrity**: SHA-256 checksum verification for all backups
- **Backward Compatibility**: Can restore backups from v3.0

#### Configuration System
- **JSON Configuration**: New JSON-based configuration file support
- **Environment Variables**: Substitute sensitive values from environment variables
- **Hot Reload**: Configuration changes without server restart
- **Validation**: Comprehensive configuration validation with helpful error messages
- **Config Overrides**: Command-line arguments override config file values

#### Connection Pooling
- **Connection Pool**: Thread-safe connection pool for better performance
- **Health Checking**: Automatic connection health checks
- **Idle Timeout**: Configurable idle connection timeout
- **Pool Statistics**: Metrics for pool usage

### Changed

- **Server Startup**: Now uses configuration file instead of command-line arguments
- **Backup Format**: New backup format with encryption and compression metadata
- **Permission System**: Migrated to RBAC-based permission model
- **Logging**: Enhanced logging with structured JSON format

### Deprecated

- Command-line only configuration (use `-c config.json` instead)
- Old backup format without encryption (still supported for restore)

### Removed

- N/A

### Fixed

- Memory leak in connection handling
- Race condition in replication sync
- File descriptor leak on client disconnect
- Incorrect permission check for DROP TABLE

### Security

- CVE-2024-XXXX: Fixed authentication bypass vulnerability
- CVE-2024-YYYY: Fixed SQL injection in WHERE clause parsing
- Implemented secure password storage with bcrypt
- Added protection against timing attacks
- Fixed information disclosure in error messages

## [3.0.0] - 2023-11-01

### Added

- **Database Engine**: LevelDB-based storage engine
- **SQL Interface**: CREATE, INSERT, SELECT, UPDATE, DELETE commands
- **Multi-Database**: Support for multiple named databases
- **Table Schema**: Column definition with types
- **Authentication**: Database-backed user authentication
- **Basic Replication**: Master-slave replication
- **Backup/Restore**: Basic backup and restore functionality
- **CLI Client**: Interactive command-line client

### Changed

- N/A (initial release)

## Migration Notes

### Upgrading to 3.1.0

See [MIGRATION_v3.0_to_v3.1.md](MIGRATION_v3.0_to_v3.1.md) for detailed upgrade instructions.

Key changes:
1. Create `config.json` configuration file
2. Update backup scripts for new encryption options
3. Review and update permission grants for RBAC
4. Test TLS configuration before enabling

### Breaking Changes

- Server now requires `-c config.json` or `config.json` in working directory
- Backup command syntax extended with `WITH` clause
- Permission system now uses RBAC (automatic migration provided)

## Contributors

Thanks to all contributors who helped make this release possible!

- @username1 - TLS implementation
- @username2 - GPU acceleration
- @username3 - Audit logging system
- @username4 - Configuration system

## License

MIT License - see [LICENSE](LICENSE) for details.
