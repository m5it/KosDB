#!/usr/bin/env python3
"""Unit tests for multitenant command handlers."""

import unittest
from unittest.mock import MagicMock, patch
from multitenant_commands import (
    CreateTenantCommand,
    DropTenantCommand,
    UseTenantCommand,
    ListTenantsCommand,
    TenantStatsCommand,
    SetTenantQuotaCommand,
    AddRowPolicyCommand,
    RemoveRowPolicyCommand,
    CheckQuotaCommand,
    TenantBackupCommand,
    TenantRestoreCommand,
)


class TestMultitenantCommands(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.auth = MagicMock()

    @patch('multitenant_commands.get_tenant_manager')
    def test_create_tenant(self, mock_mgr):
        tenant = MagicMock()
        tenant.quota.to_dict.return_value = {}
        mock_mgr.return_value.create_tenant.return_value = tenant
        cmd = CreateTenantCommand(self.db, self.auth)
        result = cmd.execute('t1', 'Tenant One', storage_gb=5)
        self.assertEqual(result['status'], 'success')

    @patch('multitenant_commands.get_tenant_manager')
    def test_create_tenant_error(self, mock_mgr):
        from multitenant import TenantError
        mock_mgr.return_value.create_tenant.side_effect = TenantError('exists')
        cmd = CreateTenantCommand(self.db, self.auth)
        result = cmd.execute('t1', 'Tenant One')
        self.assertEqual(result['status'], 'error')

    @patch('multitenant_commands.get_tenant_manager')
    def test_drop_tenant(self, mock_mgr):
        mock_mgr.return_value.drop_tenant.return_value = True
        cmd = DropTenantCommand(self.db, self.auth)
        result = cmd.execute('t1')
        self.assertEqual(result['status'], 'success')

    @patch('multitenant_commands.get_tenant_manager')
    def test_use_tenant(self, mock_mgr):
        tenant = MagicMock()
        tenant.is_active = True
        tenant.to_dict.return_value = {}
        mock_mgr.return_value.get_tenant.return_value = tenant
        cmd = UseTenantCommand(self.db, self.auth)
        result = cmd.execute('t1')
        self.assertEqual(result['status'], 'success')

    @patch('multitenant_commands.get_tenant_manager')
    def test_use_tenant_inactive(self, mock_mgr):
        tenant = MagicMock()
        tenant.is_active = False
        mock_mgr.return_value.get_tenant.return_value = tenant
        cmd = UseTenantCommand(self.db, self.auth)
        result = cmd.execute('t1')
        self.assertEqual(result['status'], 'error')

    @patch('multitenant_commands.get_tenant_manager')
    def test_list_tenants(self, mock_mgr):
        tenant = MagicMock()
        tenant.to_dict.return_value = {}
        mock_mgr.return_value.list_tenants.return_value = [tenant]
        cmd = ListTenantsCommand(self.db, self.auth)
        result = cmd.execute()
        self.assertEqual(result['count'], 1)

    @patch('multitenant_commands.get_tenant_manager')
    def test_tenant_stats(self, mock_mgr):
        tenant = MagicMock()
        tenant.get_stats.return_value = {}
        mock_mgr.return_value.get_tenant.return_value = tenant
        cmd = TenantStatsCommand(self.db, self.auth)
        result = cmd.execute('t1')
        self.assertEqual(result['status'], 'success')

    @patch('multitenant_commands.get_tenant_manager')
    def test_set_quota(self, mock_mgr):
        tenant = MagicMock()
        tenant.quota.to_dict.return_value = {}
        mock_mgr.return_value.get_tenant.return_value = tenant
        cmd = SetTenantQuotaCommand(self.db, self.auth)
        result = cmd.execute('t1', storage_gb=20)
        self.assertEqual(result['status'], 'success')

    @patch('multitenant_commands.get_tenant_manager')
    def test_add_row_policy(self, mock_mgr):
        tenant = MagicMock()
        mock_mgr.return_value.get_tenant.return_value = tenant
        cmd = AddRowPolicyCommand(self.db, self.auth)
        result = cmd.execute('t1', 'p1', 'users', 'tenant_id = current_tenant')
        self.assertEqual(result['status'], 'success')

    @patch('multitenant_commands.get_tenant_manager')
    def test_remove_row_policy(self, mock_mgr):
        tenant = MagicMock()
        tenant.remove_row_policy.return_value = True
        mock_mgr.return_value.get_tenant.return_value = tenant
        cmd = RemoveRowPolicyCommand(self.db, self.auth)
        result = cmd.execute('t1', 'p1')
        self.assertEqual(result['status'], 'success')

    @patch('multitenant_commands.get_tenant_manager')
    def test_check_quota(self, mock_mgr):
        tenant = MagicMock()
        tenant.quota.storage_bytes = 100
        tenant.usage.storage_bytes = 50
        tenant.usage.active_connections = 2
        tenant.quota.max_connections = 10
        mock_mgr.return_value.get_tenant.return_value = tenant
        cmd = CheckQuotaCommand(self.db, self.auth)
        result = cmd.execute('t1')
        self.assertEqual(result['status'], 'success')

    @patch('multitenant_commands.get_tenant_manager')
    def test_tenant_backup(self, mock_mgr):
        tenant = MagicMock()
        mock_mgr.return_value.get_tenant.return_value = tenant
        cmd = TenantBackupCommand(self.db, self.auth)
        result = cmd.execute('t1', '/tmp/backup')
        self.assertEqual(result['status'], 'success')

    def test_tenant_restore(self):
        cmd = TenantRestoreCommand(self.db, self.auth)
        result = cmd.execute('t1', '/tmp/backup')
        self.assertEqual(result['status'], 'success')


if __name__ == '__main__':
    unittest.main()
