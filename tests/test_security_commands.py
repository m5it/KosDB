#!/usr/bin/env python3
"""Unit tests for security command handlers."""

import unittest
from unittest.mock import MagicMock, patch
from security_commands import (
    AuditLogCommand,
    ExportAuditLogCommand,
    GrantRoleCommand,
    RevokeRoleCommand,
    CheckPermissionCommand,
    EncryptColumnCommand,
    DecryptColumnCommand,
    ValidatePasswordCommand,
    SQLInjectionCheckCommand,
    ComplianceReportCommand,
    SecurityStatsCommand,
    HighRiskEventsCommand,
)


class TestSecurityCommands(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.auth = MagicMock()

    @patch('security_commands.get_security_manager')
    def test_audit_log(self, mock_get):
        manager = MagicMock()
        event = MagicMock()
        event.to_dict.return_value = {}
        manager.audit_logger.query.return_value = [event]
        mock_get.return_value = manager
        cmd = AuditLogCommand(self.db, self.auth)
        result = cmd.execute()
        self.assertEqual(result['status'], 'success')

    @patch('security_commands.get_security_manager')
    def test_audit_log_invalid_type(self, mock_get):
        manager = MagicMock()
        mock_get.return_value = manager
        cmd = AuditLogCommand(self.db, self.auth)
        result = cmd.execute(event_type='invalid')
        self.assertEqual(result['status'], 'error')

    @patch('security_commands.get_security_manager')
    def test_export_audit(self, mock_get):
        manager = MagicMock()
        manager.audit_logger.export.return_value = 'data'
        mock_get.return_value = manager
        cmd = ExportAuditLogCommand(self.db, self.auth)
        result = cmd.execute('json')
        self.assertEqual(result['status'], 'success')

    def test_export_audit_bad_format(self):
        cmd = ExportAuditLogCommand(self.db, self.auth)
        result = cmd.execute('xml')
        self.assertEqual(result['status'], 'error')

    @patch('security_commands.get_security_manager')
    def test_grant_role(self, mock_get):
        manager = MagicMock()
        mock_get.return_value = manager
        cmd = GrantRoleCommand(self.db, self.auth)
        result = cmd.execute('alice', 'admin')
        self.assertEqual(result['status'], 'success')

    @patch('security_commands.get_security_manager')
    def test_grant_role_error(self, mock_get):
        manager = MagicMock()
        manager.rbac.grant_role.side_effect = ValueError('bad role')
        mock_get.return_value = manager
        cmd = GrantRoleCommand(self.db, self.auth)
        result = cmd.execute('alice', 'bad')
        self.assertEqual(result['status'], 'error')

    @patch('security_commands.get_security_manager')
    def test_revoke_role(self, mock_get):
        manager = MagicMock()
        mock_get.return_value = manager
        cmd = RevokeRoleCommand(self.db, self.auth)
        result = cmd.execute('alice', 'admin')
        self.assertEqual(result['status'], 'success')

    @patch('security_commands.get_security_manager')
    def test_check_permission(self, mock_get):
        manager = MagicMock()
        manager.check_permission.return_value = True
        manager.rbac.get_user_permissions.return_value = {'SELECT'}
        mock_get.return_value = manager
        cmd = CheckPermissionCommand(self.db, self.auth)
        result = cmd.execute('alice', 'SELECT')
        self.assertTrue(result['has_permission'])

    @patch('security_commands.get_security_manager')
    def test_encrypt_column(self, mock_get):
        manager = MagicMock()
        manager.encrypt_sensitive_data.return_value = 'cipher'
        mock_get.return_value = manager
        cmd = EncryptColumnCommand(self.db, self.auth)
        result = cmd.execute('users', 'ssn', '123-45-6789')
        self.assertEqual(result['encrypted'], 'cipher')

    @patch('security_commands.get_security_manager')
    def test_decrypt_column(self, mock_get):
        manager = MagicMock()
        manager.decrypt_sensitive_data.return_value = 'plain'
        mock_get.return_value = manager
        cmd = DecryptColumnCommand(self.db, self.auth)
        result = cmd.execute('users', 'ssn', 'cipher')
        self.assertEqual(result['decrypted'], 'plain')

    @patch('security_commands.get_security_manager')
    def test_decrypt_error(self, mock_get):
        manager = MagicMock()
        manager.decrypt_sensitive_data.side_effect = Exception('fail')
        mock_get.return_value = manager
        cmd = DecryptColumnCommand(self.db, self.auth)
        result = cmd.execute('users', 'ssn', 'cipher')
        self.assertEqual(result['status'], 'error')

    @patch('security_commands.get_security_manager')
    def test_validate_password(self, mock_get):
        manager = MagicMock()
        manager.policy.validate_password.return_value = (True, [])
        mock_get.return_value = manager
        cmd = ValidatePasswordCommand(self.db, self.auth)
        result = cmd.execute('StrongP@ss1')
        self.assertTrue(result['is_valid'])

    @patch('security_commands.get_security_manager')
    def test_sql_injection_check(self, mock_get):
        manager = MagicMock()
        manager.injection_detector.analyze.return_value = (True, 0.9, [])
        mock_get.return_value = manager
        cmd = SQLInjectionCheckCommand(self.db, self.auth)
        result = cmd.execute('SELECT 1')
        self.assertTrue(result['is_safe'])

    @patch('security_commands.get_security_manager')
    def test_compliance_report(self, mock_get):
        manager = MagicMock()
        manager.compliance.generate_report.return_value = {}
        mock_get.return_value = manager
        cmd = ComplianceReportCommand(self.db, self.auth)
        result = cmd.execute('SOC2', days=7)
        self.assertEqual(result['status'], 'success')

    @patch('security_commands.get_security_manager')
    def test_security_stats(self, mock_get):
        manager = MagicMock()
        manager.get_security_report.return_value = {}
        mock_get.return_value = manager
        cmd = SecurityStatsCommand(self.db, self.auth)
        result = cmd.execute()
        self.assertEqual(result['status'], 'success')

    @patch('security_commands.get_security_manager')
    def test_high_risk_events(self, mock_get):
        manager = MagicMock()
        event = MagicMock()
        event.to_dict.return_value = {}
        manager.audit_logger.get_high_risk_events.return_value = [event]
        mock_get.return_value = manager
        cmd = HighRiskEventsCommand(self.db, self.auth)
        result = cmd.execute(threshold=75)
        self.assertEqual(result['status'], 'success')


if __name__ == '__main__':
    unittest.main()
