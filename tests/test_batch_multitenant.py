
"""
Tests for Batch Multi-Tenant Verification
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from batch_multitenant import (
    BatchTenantVerifier,
    BatchTenantExecutor,
    BatchTenantContext,
    parse_use_tenant,
    is_tenant_command
)


class MockQuota:
    """Mock quota for testing."""
    def __init__(self):
        self.queries_per_minute = 100
        self.storage_bytes = 10 * 1024 * 1024 * 1024
        self.max_connections = 100
        self.max_tables = 100
        self.max_rows = 10_000_000


class MockTenant:
    """Mock tenant for testing."""
    def __init__(self, tenant_id, quota=None):
        self.tenant_id = tenant_id
        self.quota = quota or MockQuota()
        self.usage = type('obj', (object,), {
            'queries_this_minute': 0,
            'storage_bytes': 0,
            'active_connections': 0,
            'table_count': 0,
            'row_count': 0
        })()
    
    def check_quota(self, resource_type, amount):
        return (self.usage.queries_this_minute + amount) <= self.quota.queries_per_minute
    
    def check_row_access(self, table_name, row):
        # Simple RLS: tenant can access rows with matching tenant_id
        return row.get('tenant_id') == self.tenant_id


class MockTenantManager:
    """Mock tenant manager for testing."""
    def __init__(self):
        self._tenants = {
            'tenant1': MockTenant('tenant1'),
            'tenant2': MockTenant('tenant2'),
        }
    
    def get_tenant(self, tenant_id):
        return self._tenants.get(tenant_id)


class TestBatchTenantVerifier(unittest.TestCase):
    """Test batch tenant verification."""
    
    def setUp(self):
        self.tm = MockTenantManager()
        self.verifier = BatchTenantVerifier(self.tm)
    
    def test_single_tenant_batch(self):
        """Test batch with single tenant is valid."""
        commands = [
            "USE TENANT tenant1;",
            "SELECT * FROM users;",
            "INSERT INTO logs VALUES (1);"
        ]
        
        result = self.verifier.verify_batch(commands)
        
        self.assertTrue(result['valid'])
        self.assertEqual(result['tenant_id'], 'tenant1')
    
    def test_multiple_tenants_violation(self):
        """Test batch with multiple tenants is invalid."""
        commands = [
            "USE TENANT tenant1;",
            "SELECT * FROM users;",
            "USE TENANT tenant2;",  # Second USE TENANT - switch
            "SELECT * FROM orders;"
        ]
        
        result = self.verifier.verify_batch(commands)
        
        self.assertFalse(result['valid'])
        self.assertIn('multiple tenants', result['error'].lower())
    
    def test_no_tenant_context(self):
        """Test batch without tenant context."""
        commands = [
            "SELECT * FROM system_settings;",
            "SHOW TABLES;"
        ]
        
        result = self.verifier.verify_batch(commands)
        
        self.assertTrue(result['valid'])
        self.assertIsNone(result['tenant_id'])
    
    def test_use_tenant_persistence(self):
        """Test USE TENANT persistence detected."""
        commands = [
            "USE TENANT tenant1;",
            "SELECT 1;",
            "SELECT 2;"
        ]
        
        result = self.verifier.verify_batch(commands)
        
        self.assertTrue(result['use_tenant_persisted'])
    
    def test_check_tenant_quota(self):
        """Test tenant quota checking."""
        result = self.verifier.check_tenant_quota('tenant1', 10)
        
        self.assertTrue(result['valid'])
        self.assertEqual(result['tenant_id'], 'tenant1')
    
    def test_quota_exceeded(self):
        """Test quota exceeded detection."""
        # Request more than allowed
        result = self.verifier.check_tenant_quota('tenant1', 1000)
        
        self.assertFalse(result['valid'])
        self.assertIn('quota exceeded', result['error'].lower())
    
    def test_rls_policy_enforcement(self):
        """Test row-level security enforcement."""
        rows = [
            {'id': 1, 'tenant_id': 'tenant1', 'data': 'a'},
            {'id': 2, 'tenant_id': 'tenant2', 'data': 'b'},
            {'id': 3, 'tenant_id': 'tenant1', 'data': 'c'},
        ]
        
        filtered = self.verifier.enforce_rls_policies('tenant1', 'users', rows)
        
        self.assertEqual(len(filtered), 2)
        self.assertTrue(all(r['tenant_id'] == 'tenant1' for r in filtered))
    
    def test_cdc_event_tagging(self):
        """Test CDC event tenant tagging."""
        events = [
            {'table': 'users', 'operation': 'INSERT'},
            {'table': 'orders', 'operation': 'UPDATE'},
        ]
        
        tagged = self.verifier.tag_cdc_events('tenant1', events)
        
        self.assertEqual(len(tagged), 2)
        self.assertTrue(all(e['tenant_id'] == 'tenant1' for e in tagged))
    
    def test_metrics_tracking(self):
        """Test metrics are tracked."""
        # Run some operations
        self.verifier.verify_batch(["USE TENANT tenant1;", "SELECT 1;"])
        self.verifier.check_tenant_quota('tenant1', 1)
        self.verifier.enforce_rls_policies('tenant1', 'users', [{'id': 1}])
        
        metrics = self.verifier.get_metrics()
        
        self.assertEqual(metrics['batches_verified'], 1)
        self.assertEqual(metrics['quota_checks'], 1)
        self.assertEqual(metrics['rls_checks'], 1)


class TestBatchTenantExecutor(unittest.TestCase):
    """Test batch tenant executor."""
    
    def setUp(self):
        self.tm = MockTenantManager()
        self.executor = BatchTenantExecutor(self.tm)
    
    def test_execute_with_tenant_check(self):
        """Test execution with tenant verification."""
        commands = ["USE TENANT tenant1;", "SELECT 1;"]
        
        def mock_executor(cmd):
            return f"Result of {cmd}"
        
        result = self.executor.execute_with_tenant_check(
            commands, mock_executor
        )
        
        self.assertTrue(result['success'])
        self.assertEqual(result['tenant_id'], 'tenant1')
        self.assertEqual(len(result['results']), 2)
    
    def test_tenant_switch_error(self):
        """Test tenant switch in batch causes error."""
        commands = [
            "USE TENANT tenant1;",
            "SELECT 1;",
            "USE TENANT tenant2;",  # Switch not allowed
            "SELECT 2;"
        ]
        
        def mock_executor(cmd):
            return "ok"
        
        result = self.executor.execute_with_tenant_check(
            commands, mock_executor
        )
        
        # Should fail due to tenant switch
        self.assertFalse(result['success'])
        # Error message should mention tenant or multiple
        self.assertTrue(
            'tenant' in result['error'].lower() or 
            'multiple' in result['error'].lower()
        )


class TestParseUseTenant(unittest.TestCase):
    """Test USE TENANT parsing."""
    
    def test_parse_use_tenant(self):
        """Test parsing USE TENANT command."""
        cmd, tenant = parse_use_tenant("USE TENANT tenant1; SELECT 1;")
        
        self.assertEqual(tenant, 'tenant1')
        self.assertEqual(cmd, "SELECT 1;")
    
    def test_parse_use_tenant_no_remaining(self):
        """Test parsing USE TENANT with no remaining command."""
        cmd, tenant = parse_use_tenant("USE TENANT tenant1")
        
        self.assertEqual(tenant, 'tenant1')
        self.assertEqual(cmd, '')
    
    def test_parse_non_tenant_command(self):
        """Test parsing non-tenant command."""
        cmd, tenant = parse_use_tenant("SELECT * FROM users")
        
        self.assertIsNone(tenant)
        self.assertEqual(cmd, "SELECT * FROM users")


class TestIsTenantCommand(unittest.TestCase):
    """Test tenant command detection."""
    
    def test_is_tenant_command(self):
        """Test detection of tenant commands."""
        self.assertTrue(is_tenant_command("USE TENANT tenant1"))
        self.assertTrue(is_tenant_command("CREATE TENANT new_tenant"))
        self.assertTrue(is_tenant_command("SELECT * WHERE TENANT_ID = 'x'"))
    
    def test_is_not_tenant_command(self):
        """Test non-tenant commands."""
        self.assertFalse(is_tenant_command("SELECT * FROM users"))
        self.assertFalse(is_tenant_command("INSERT INTO logs VALUES (1)"))


class TestBatchTenantContext(unittest.TestCase):
    """Test batch tenant context."""
    
    def test_context_creation(self):
        """Test context initialization."""
        ctx = BatchTenantContext()
        
        self.assertIsNone(ctx.tenant_id)
        self.assertEqual(ctx.command_count, 0)
        self.assertFalse(ctx.use_tenant_persisted)
    
    def test_context_to_dict(self):
        """Test context serialization."""
        ctx = BatchTenantContext(
            tenant_id='tenant1',
            use_tenant_persisted=True,
            command_count=5,
            rls_policies_applied=3,
            cdc_events_tagged=2
        )
        
        data = ctx.to_dict()
        
        self.assertEqual(data['tenant_id'], 'tenant1')
        self.assertTrue(data['use_tenant_persisted'])
        self.assertEqual(data['command_count'], 5)
        self.assertEqual(data['rls_policies_applied'], 3)
        self.assertEqual(data['cdc_events_tagged'], 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
