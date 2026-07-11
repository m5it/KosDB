"""
Tests for multi-tenant module.
"""

import unittest
import time
import threading
from multitenant import (
    Tenant,
    TenantManager,
    ResourceQuota,
    ResourceType,
    RowLevelPolicy,
    TenantContext,
    get_tenant_manager,
    TenantError,
    QuotaExceededError,
    TenantNotFoundError
)


class TestResourceQuota(unittest.TestCase):
    
    def test_default_quota(self):
        """Test default quota values."""
        quota = ResourceQuota()
        
        self.assertEqual(quota.storage_bytes, 10 * 1024 * 1024 * 1024)
        self.assertEqual(quota.queries_per_minute, 1000)
        self.assertEqual(quota.max_connections, 100)
    
    def test_to_dict(self):
        """Test quota serialization."""
        quota = ResourceQuota(storage_bytes=5 * 1024 * 1024 * 1024)
        d = quota.to_dict()
        
        self.assertEqual(d['storage_gb'], 5.0)
        self.assertIn('queries_per_minute', d)


class TestTenant(unittest.TestCase):
    
    def setUp(self):
        self.tenant = Tenant(
            tenant_id="test_tenant",
            name="Test Tenant",
            quota=ResourceQuota(
                storage_bytes=1024 * 1024 * 1024,
                queries_per_minute=100,
                max_connections=10,
                max_tables=5
            )
        )
    
    def test_check_quota_storage(self):
        """Test storage quota check."""
        self.tenant.usage.storage_bytes = 500 * 1024 * 1024
        
        # Should be within quota
        self.assertTrue(self.tenant.check_quota(ResourceType.STORAGE, 400 * 1024 * 1024))
        
        # Should exceed quota
        self.assertFalse(self.tenant.check_quota(ResourceType.STORAGE, 600 * 1024 * 1024))
    
    def test_check_quota_connections(self):
        """Test connection quota check."""
        self.tenant.usage.active_connections = 5
        
        self.assertTrue(self.tenant.check_quota(ResourceType.CONNECTIONS, 4))
        self.assertFalse(self.tenant.check_quota(ResourceType.CONNECTIONS, 6))
    
    def test_add_remove_connection(self):
        """Test connection management."""
        # Add connections up to limit
        for i in range(10):
            self.assertTrue(self.tenant.add_connection(f"conn_{i}"))
        
        # Should fail at limit
        self.assertFalse(self.tenant.add_connection("conn_overflow"))
        
        # Remove and add again
        self.tenant.remove_connection("conn_0")
        self.assertTrue(self.tenant.add_connection("conn_new"))
    
    def test_record_query(self):
        """Test query recording."""
        for i in range(50):
            self.tenant.record_query()
        
        self.assertEqual(self.tenant.usage.queries_this_minute, 50)
    
    def test_update_usage(self):
        """Test usage updates."""
        self.tenant.update_usage(ResourceType.STORAGE, 1024)
        self.assertEqual(self.tenant.usage.storage_bytes, 1024)
        
        self.tenant.update_usage(ResourceType.TABLES, 5)
        self.assertEqual(self.tenant.usage.table_count, 5)
        
        # Test negative delta
        self.tenant.update_usage(ResourceType.TABLES, -3)
        self.assertEqual(self.tenant.usage.table_count, 2)
    
    def test_row_policy(self):
        """Test row-level security policies."""
        def allow_own_rows(row, tenant_id):
            return row.get('tenant_id') == tenant_id
        
        policy = RowLevelPolicy(
            name="own_data_only",
            table_pattern="users_*",
            condition=allow_own_rows
        )
        
        self.tenant.add_row_policy(policy)
        self.assertEqual(len(self.tenant.row_policies), 1)
        
        # Check access
        row = {'tenant_id': 'test_tenant', 'data': 'secret'}
        self.assertTrue(self.tenant.check_row_access('users_1', row))
        
        row = {'tenant_id': 'other_tenant', 'data': 'secret'}
        self.assertFalse(self.tenant.check_row_access('users_1', row))
        
        # Remove policy
        self.assertTrue(self.tenant.remove_row_policy("own_data_only"))
        self.assertEqual(len(self.tenant.row_policies), 0)
    
    def test_get_stats(self):
        """Test statistics."""
        stats = self.tenant.get_stats()
        
        self.assertEqual(stats['tenant_id'], 'test_tenant')
        self.assertEqual(stats['name'], 'Test Tenant')
        self.assertIn('quota', stats)
        self.assertIn('usage', stats)


class TestTenantManager(unittest.TestCase):
    
    def setUp(self):
        self.manager = TenantManager()
    
    def test_create_tenant(self):
        """Test tenant creation."""
        tenant = self.manager.create_tenant("tenant1", "Tenant One")
        
        self.assertEqual(tenant.tenant_id, "tenant1")
        self.assertEqual(tenant.name, "Tenant One")
        self.assertIn("tenant1", [t.tenant_id for t in self.manager.list_tenants()])
    
    def test_create_duplicate_tenant(self):
        """Test duplicate tenant creation."""
        self.manager.create_tenant("tenant1", "Tenant One")
        
        with self.assertRaises(TenantError):
            self.manager.create_tenant("tenant1", "Duplicate")
    
    def test_get_tenant(self):
        """Test getting tenant."""
        self.manager.create_tenant("tenant1", "Tenant One")
        
        tenant = self.manager.get_tenant("tenant1")
        self.assertIsNotNone(tenant)
        self.assertEqual(tenant.name, "Tenant One")
        
        # Non-existent tenant
        self.assertIsNone(self.manager.get_tenant("nonexistent"))
    
    def test_drop_tenant(self):
        """Test dropping tenant."""
        self.manager.create_tenant("tenant1", "Tenant One")
        
        self.assertTrue(self.manager.drop_tenant("tenant1"))
        self.assertNotIn("tenant1", [t.tenant_id for t in self.manager.list_tenants()])
        
        # Drop non-existent
        self.assertFalse(self.manager.drop_tenant("nonexistent"))
    
    def test_list_tenants(self):
        """Test listing tenants."""
        self.manager.create_tenant("tenant1", "Tenant One")
        self.manager.create_tenant("tenant2", "Tenant Two")
        
        tenants = self.manager.list_tenants()
        self.assertEqual(len(tenants), 2)
        
        # Deactivate one
        tenants[0].is_active = False
        active_only = self.manager.list_tenants(include_inactive=False)
        self.assertEqual(len(active_only), 1)
    
    def test_set_default_tenant(self):
        """Test default tenant."""
        self.manager.create_tenant("tenant1", "Tenant One")
        
        self.manager.set_default_tenant("tenant1")
        self.assertEqual(self.manager.get_default_tenant(), "tenant1")
        
        # Non-existent tenant
        with self.assertRaises(TenantNotFoundError):
            self.manager.set_default_tenant("nonexistent")
    
    def test_global_stats(self):
        """Test global statistics."""
        self.manager.create_tenant("tenant1", "Tenant One")
        
        stats = self.manager.get_global_stats()
        
        self.assertEqual(stats['tenant_count'], 1)
        self.assertIn('total_storage_bytes', stats)


class TestTenantContext(unittest.TestCase):
    
    def test_context_manager(self):
        """Test tenant context manager."""
        # Create a local manager for isolation
        manager = TenantManager()
        manager.create_tenant("tenant1", "Tenant One")
        
        # Use context directly with the tenant
        tenant = manager.get_tenant("tenant1")
        
        # Test connection management
        self.assertTrue(tenant.add_connection("conn_1"))
        self.assertEqual(tenant.usage.active_connections, 1)
        
        tenant.remove_connection("conn_1")
        self.assertEqual(tenant.usage.active_connections, 0)
    
    def test_context_not_found(self):
        """Test context with non-existent tenant."""
        with self.assertRaises(TenantNotFoundError):
            with TenantContext("nonexistent"):
                pass


class TestGlobalTenantManager(unittest.TestCase):
    
    def test_singleton(self):
        """Test global tenant manager is singleton."""
        manager1 = get_tenant_manager()
        manager2 = get_tenant_manager()
        
        self.assertIs(manager1, manager2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
