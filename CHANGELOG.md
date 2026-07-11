# Changelog

All notable changes to KosDB will be documented in this file.

## [3.2.0] - 2024-01-15

### Added

#### Query Optimization
- **Query Plan Caching**: LRU cache for parsed execution plans with configurable size
- **Cost-Based Optimizer**: Statistics-driven plan selection for better query performance
- **Semi-Join Optimization**: Efficient IN/EXISTS subquery execution using semi-join transformation
- **Index Advisor**: Automatic index recommendations based on query patterns
- **Plan Cache Statistics**: Hit rate, miss rate, eviction tracking via EXPLAIN CACHE command

#### Subquery Support
- **Scalar Subqueries**: Support for (SELECT ...) in SELECT and WHERE clauses
- **IN/NOT IN Subqueries**: Single column result subqueries with negation support
- **EXISTS/NOT EXISTS Subqueries**: Correlated and non-correlated existence checks
- **Correlated Subqueries**: Outer reference resolution for complex queries
- **Semi-Join Transformation**: Query optimizer rewrites IN/EXISTS to semi-joins where applicable

#### Advanced Constraints
- **CHECK Constraints**: Data validation with complex expressions (=, !=, <, >, <=, >=, IN, BETWEEN, LIKE, IS NULL)
- **Foreign Key Constraints**: Referential integrity with CASCADE, SET NULL, RESTRICT options
- **Unique Constraints**: Multi-column unique constraints with automatic index creation

#### ALTER TABLE Operations
- **ADD COLUMN**: Add columns with full type support and constraints
- **DROP COLUMN**: Remove columns with CASCADE handling for dependent objects
- **MODIFY COLUMN**: Change column types with data validation
- **RENAME COLUMN**: Rename existing columns with constraint updates
- **ADD/DROP INDEX**: Dynamic index management
- **ADD/DROP CONSTRAINT**: Foreign key, unique, and CHECK constraint management

#### Views
- **CREATE VIEW**: Virtual tables based on SELECT queries
- **DROP VIEW**: View removal with dependency checking
- **SHOW VIEWS**: List all views in database

#### Full-Text Search
- **MATCH ... AGAINST**: Natural language and boolean mode search
- **Full-Text Indexes**: Inverted index for text search
- **Relevance Scoring**: TF-IDF based result ranking
- **Query Expansion**: Automatic synonym expansion

#### JSON Support
- **JSON Columns**: Native JSON data type storage
- **JSON Extraction**: column->path and column->>path operators
- **JSON Validation**: Automatic JSON format validation

#### Monitoring and Metrics
- **Prometheus Metrics**: Query counts, latency, cache hit rates, connection stats
- **Health Endpoints**: /health, /health/live, /health/ready for container orchestration
- **Status Endpoint**: /status for detailed server status
- **Configurable Collection**: Metrics collection interval and retention settings

#### SQL Enhancements
- **EXPLAIN**: Query execution plan visualization
- **EXPLAIN CACHE**: Plan cache status and statistics
- **Transactions**: BEGIN, COMMIT, ROLLBACK support
- **JSON Operators**: -> and ->> for JSON path extraction

### Changed

- **Parser**: Enhanced to support subqueries and complex WHERE clauses
- **Query Optimizer**: Major rewrite with cost-based optimization
- **Schema Storage**: Extended to support CHECK constraints and foreign keys
- **Configuration**: New metrics and optimizer sections in config.json

### Performance Improvements

- Query plan caching reduces parsing overhead for repeated queries
- Semi-join optimization improves IN/EXISTS subquery performance
- Index recommendations help optimize query patterns
- Connection metrics help identify bottlenecks

### Deprecated

- None

### Removed

- None

### Security

- Added privilege checks for ALTER TABLE operations
- Constraint validation prevents data integrity violations
- Foreign key enforcement maintains referential integrity

### Bug Fixes

- Fixed query parsing for complex nested conditions
- Improved error messages for constraint violations
- Fixed index updates during column modifications

## [3.1.0] - 2023-12-01

### Added

#### Security Features
- **TLS/SSL Encryption**: Certificate-based authentication and mTLS support
- **At-Rest Encryption**: AES-256-GCM database encryption with PBKDF2
- **Audit Logging**: Comprehensive operation logging with multiple targets
- **Role-Based Access Control**: Granular permissions and role management

#### Replication
- **Master-Slave Replication**: Automatic failover support
- **Master-Master Replication**: Multi-master with conflict resolution
- **Async Replication**: Non-blocking replication

#### Performance
- **GPU Acceleration**: CUDA-powered query processing
- **Connection Pooling**: Efficient connection management
- **Query Caching**: Result cache for frequent queries

#### Backup & Recovery
- **Hot Backups**: Non-blocking encrypted backups
- **Compression**: Multiple algorithms (gzip, lz4, zstd)
- **Point-in-Time Recovery**: Restore to specific timestamp

## [3.0.0] - 2023-10-15

### Added

- Initial release of KosDB
- SQL-like interface with basic CRUD operations
- Multiple database support
- Primary and secondary indexing
- User authentication and basic authorization
- Binary logging for replication

### Features

- CREATE, INSERT, SELECT, UPDATE, DELETE operations
- Multiple databases with USE command
- Table schema with column types
- Primary key and index support
- Basic user management

## Migration Notes

### Upgrading to 3.2.0 from 3.1.0

1. **Configuration Updates**:
   - Add `optimizer` section to config.json
   - Add `metrics` section for monitoring
   - Update version to "3.2.0"

2. **Schema Compatibility**:
   - Existing databases are fully compatible
   - New CHECK constraints apply to future INSERT/UPDATE only
   - Foreign keys can be added to existing tables via ALTER TABLE

3. **API Changes**:
   - New ALTER TABLE commands available
   - Subqueries now supported in WHERE clauses
   - EXPLAIN command added for query analysis

4. **Monitoring Setup**:
   - Configure metrics endpoint for Prometheus
   - Set up health checks for container orchestration

See [MIGRATION_v3.1_to_v3.2.md](MIGRATION_v3.1_to_v3.2.md) for detailed instructions.

## Future Roadmap

### Planned for 3.3.0
- Window functions (ROW_NUMBER, RANK, etc.)
- Common Table Expressions (CTEs)
- Prepared statements
- Stored procedures

### Planned for 4.0.0
- Distributed transactions
- Sharding support
- Columnar storage option
- Vector search capabilities
