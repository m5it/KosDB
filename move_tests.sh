#!/bin/bash
# Create test directory if it doesn't exist
mkdir -p test

# Move all test files from root to test directory
mv test_session_recovery.py test/ 2>/dev/null
mv test_schema_migration.py test/ 2>/dev/null
mv test_audit_integration.py test/ 2>/dev/null
mv test_query_optimizer.py test/ 2>/dev/null
mv test_backup_utils.py test/ 2>/dev/null
mv test_audit_logger.py test/ 2>/dev/null
mv test_agent_protocol.py test/ 2>/dev/null
mv test_write_ahead_log.py test/ 2>/dev/null
mv test_tls_manager.py test/ 2>/dev/null
mv test_concurrent_index.py test/ 2>/dev/null
mv test_gpu_integration.py test/ 2>/dev/null
mv test_encrypted_database.py test/ 2>/dev/null
mv test_vector_search.py test/ 2>/dev/null
mv test_streaming_results.py test/ 2>/dev/null
mv test_distributed_tx.py test/ 2>/dev/null
mv test_encryption_integration.py test/ 2>/dev/null
mv test_validation.py test/ 2>/dev/null
mv test_gpu_vector_search.py test/ 2>/dev/null
mv test_integration.py test/ 2>/dev/null
mv test_connection_pool.py test/ 2>/dev/null
mv test_query_cache.py test/ 2>/dev/null
mv test_tls_integration.py test/ 2>/dev/null

echo "Test files moved successfully!"
