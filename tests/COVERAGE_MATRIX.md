# KosDB Test Coverage Matrix

This document maps every project-root Python module to its existing test file and identifies coverage gaps.

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Has dedicated test file |
| ⚠️ | Test file exists but module is large/complex; needs more tests |
| ❌ | No dedicated test file |
| 🔧 | Utility/script module (tests optional) |
| 📝 | Parser/commands companion module — needs tests |

## Core Engine

| Module | Test File | Status | Notes |
|--------|-----------|--------|-------|
| `database.py` | ❌ none | ❌ | Core LevelDB wrapper, CRUD, auth, transactions |
| `parser.py` | ❌ none | ❌ | SQL parser; many command types to verify |
| `commands.py` | ❌ none | ❌ | Command execution framework; large registry |
| `binlog.py` | ❌ none | ❌ | Binary log for replication |
| `auth.py` | ❌ none | ❌ | Authentication and authorization |
| `server.py` | ❌ none | ❌ | TCP socket server |
| `cli.py` | ❌ none | ❌ | Command-line client |
| `write_ahead_log.py` | `test_write_ahead_log.py` | ✅ | WAL and ARIES recovery |
| `validated_commands.py` | ❌ none | ❌ | Validated command wrappers |

## Replication & Failover

| Module | Test File | Status | Notes |
|--------|-----------|--------|-------|
| `replication.py` | `tests/test_replication.py` | ✅ | Master-slave replication |
| `replication_commands.py` | ❌ none | ❌ | Replication command handlers |
| `failover.py` | ❌ none | ❌ | Raft consensus and failover manager |
| `distributed_tx.py` | `test_distributed_tx.py` | ✅ | Two-phase commit |

## Query & Storage

| Module | Test File | Status | Notes |
|--------|-----------|--------|-------|
| `query_optimizer.py` | `test_query_optimizer.py` | ✅ | Cost-based planning |
| `query_plan_cache.py` | `test_query_plan_cache.py` | ✅ | Cached plans |
| `query_cache.py` | `test_query_cache.py` | ✅ | Query result cache |
| `concurrent_index.py` | `test_concurrent_index.py` | ✅ | Online index builds |
| `streaming_results.py` | `test_streaming_results.py` | ✅ | Progressive result streaming |
| `compressed_storage.py` | ❌ none | ❌ | Compressed storage layer |
| `compression.py` | `test_compression.py` | ✅ | Compression algorithms |
| `compression_commands.py` | ❌ none | 📝 | Compression command handlers |
| `compression_parser.py` | ❌ none | 📝 | Compression SQL parser |
| `fulltext_search.py` | `test_fulltext_search.py` | ✅ | Full-text indexing |

## Advanced Features

| Module | Test File | Status | Notes |
|--------|-----------|--------|-------|
| `vector_search.py` | `test_vector_search.py` | ✅ | Vector similarity search |
| `gpu_vector_ops.py` | `test_gpu_vector_ops.py` | ✅ | GPU vector operations |
| `geospatial.py` | `test_geospatial.py` | ✅ | Geospatial queries |
| `geospatial_commands.py` | ❌ none | 📝 | Geospatial command handlers |
| `geospatial_parser.py` | ❌ none | 📝 | Geospatial SQL parser |
| `timeseries.py` | `test_timeseries.py` | ✅ | Time-series engine |
| `timeseries_commands.py` | ❌ none | 📝 | Time-series command handlers |
| `timeseries_parser.py` | ❌ none | 📝 | Time-series SQL parser |
| `multitenant.py` | `test_multitenant.py` | ✅ | Multi-tenant management |
| `multitenant_commands.py` | ❌ none | 📝 | Multi-tenant command handlers |
| `multitenant_parser.py` | ❌ none | 📝 | Multi-tenant SQL parser |
| `cdc.py` | `test_cdc.py` | ✅ | Change data capture |
| `cdc_commands.py` | ❌ none | 📝 | CDC command handlers |
| `cdc_parser.py` | ❌ none | 📝 | CDC SQL parser |
| `materialized_views.py` | `test_materialized_views.py` | ✅ | Materialized views |
| `mv_commands.py` | ❌ none | 📝 | MV command handlers |
| `mv_parser.py` | ❌ none | 📝 | MV SQL parser |
| `security.py` | `test_security.py` | ✅ | Security suite |
| `security_commands.py` | ❌ none | 📝 | Security command handlers |
| `security_parser.py` | ❌ none | 📝 | Security SQL parser |
| `connection_pool.py` | `test_connection_pool.py` | ✅ | Connection pooling |
| `pool_commands.py` | ❌ none | 📝 | Pool command handlers |
| `pool_parser.py` | ❌ none | 📝 | Pool SQL parser |
| `prepared_statements.py` | `test_prepared_statements.py` | ✅ | Prepared statements |
| `prepared_statement_commands.py` | ❌ none | 📝 | Prepared statement command handlers |
| `prepared_statement_parser.py` | ❌ none | 📝 | Prepared statement SQL parser |
| `schema_migration.py` | `test_schema_migration.py` | ✅ | Schema migrations |
| `session_recovery.py` | `test_session_recovery.py` | ✅ | Session recovery |
| `agent_protocol.py` | `test_agent_protocol.py` | ✅ | Inter-agent protocol |
| `sql_protocol.py` | ❌ none | ❌ | SQL protocol layer |
| `sql_protocol_commands.py` | ❌ none | 📝 | SQL protocol commands |
| `sql_protocol_parser.py` | ❌ none | 📝 | SQL protocol parser |

## Sharding

| Module | Test File | Status | Notes |
|--------|-----------|--------|-------|
| `sharding.py` | ❌ none | ❌ | Sharding coordinator |
| `shard_manager.py` | ❌ none | ❌ | Shard topology manager |
| `shard_router.py` | ❌ none | ❌ | Shard routing logic |
| `sharding_commands.py` | ❌ none | 📝 | Sharding command handlers |
| `sharding_parser.py` | ❌ none | 📝 | Sharding SQL parser |

## Backup & Monitoring

| Module | Test File | Status | Notes |
|--------|-----------|--------|-------|
| `backup_utils.py` | ❌ none | ❌ | Backup integrity utilities |
| `restore_commands.py` | ❌ none | ❌ | Restore command handlers (currently a git helper script) |
| `monitoring.py` | ❌ none | ❌ | Metrics, health, Prometheus exporter |

## Configuration & Validation

| Module | Test File | Status | Notes |
|--------|-----------|--------|-------|
| `config_validator.py` | `test_config_validator.py` | ✅ | Config validation |
| `validation.py` | `test_validation.py` | ✅ | Input validation |
| `tls_wrapper.py` | `test_tls_wrapper.py` | ✅ | TLS wrapper |

## Tests & Examples

| Module | Test File | Status | Notes |
|--------|-----------|--------|-------|
| `tests/test_client.py` | ✅ | ✅ | Socket client integration tests |
| `tests/test_replication.py` | ✅ | ✅ | Replication integration tests |

## Utility / Build Scripts

| Module | Test File | Status | Notes |
|--------|-----------|--------|-------|
| `run_tests.py` | — | 🔧 | Test runner script |
| `setup.py` | — | 🔧 | Package setup |
| `check_baseline.py` | — | 🔧 | Baseline checker |
| `check_commits.py` | — | 🔧 | Commit checker |
| `check_sizes.py` | — | 🔧 | Size checker |
| `extract_8e234ac.py` | — | 🔧 | Extraction helper |
| `extract_baseline.py` | — | 🔧 | Extraction helper |
| `commands_8e234ac.py` | — | 🔧 | Snapshot of commands |
| `commands_baseline.py` | — | 🔧 | Baseline commands |

## Coverage Summary

| Category | Modules | With Tests | Missing |
|----------|---------|-----------|---------|
| Core Engine | 8 | 1 | 7 |
| Replication/Failover | 4 | 2 | 2 |
| Query/Storage | 9 | 5 | 4 |
| Advanced Features | 24 | 10 | 14 |
| Sharding | 5 | 0 | 5 |
| Backup/Monitoring | 3 | 0 | 3 |
| Config/Validation | 3 | 3 | 0 |
| **Total Project Modules** | **56** | **21** | **35** |

## Priority Test Additions

1. **Core**: `test_database.py`, `test_parser.py`, `test_commands.py`, `test_binlog.py`
2. **Replication/Failover**: `test_failover.py`, `test_replication_commands.py`
3. **Sharding**: `test_sharding.py`, `test_shard_manager.py`, `test_shard_router.py`
4. **Backup/Restore**: `test_backup_utils.py`, `test_restore_commands.py`
5. **Monitoring**: `test_monitoring.py`
6. **Command/Parser modules**: Many `*_commands.py` and `*_parser.py` files need focused tests.
