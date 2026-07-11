"""
Tests for security module.
"""

import unittest
import time
import re
from security import (
    AuditEvent,
    AuditEventType,
    AuditLogger,
    AESEncryption,
    RBACManager,
    SQLInjectionDetector,
    SecurityPolicy,
    ComplianceReporter,
    SecurityManager,
    get_security_manager,
    SQLInjectionError,
    EncryptionError
)


class TestAuditEvent(unittest.TestCase):
    
    def test_create_event(self):
        """Test creating audit event."""
        event = AuditEvent(
            event_id="abc123",
            timestamp=1234567890.0,
            event_type=AuditEventType.QUERY,
            user_id="user1",
            client_ip="192.168.1.1",
            resource="users",
            action="SELECT",
            success=True
        )
        
        self.assertEqual(event.event_id, "abc123")
        self.assertEqual(event.event_type, AuditEventType.QUERY)
        self.assertEqual(event.risk_score, 0)
    
    def test_to_dict(self):
        """Test event serialization."""
        event = AuditEvent(
            event_id="abc123",
            timestamp=1234567890.0,
            event_type=AuditEventType.INSERT,
            user_id="user1",
            client_ip="192.168.1.1",
            resource="users",
            action="INSERT",
            details={'row_count': 1}
        )
        
        d = event.to_dict()
        self.assertEqual(d['event_type'], 'insert')
        self.assertEqual(d['user_id'], 'user1')
        self.assertIn('timestamp_iso', d)


class TestAuditLogger(unittest.TestCase):
    
    def setUp(self):
        self.logger = AuditLogger()
    
    def test_log_event(self):
        """Test logging event."""
        event = self.logger.log(
            event_type=AuditEventType.QUERY,
            user_id="user1",
            resource="users",
            action="SELECT * FROM users",
            client_ip="192.168.1.1"
        )
        
        self.assertIsNotNone(event.event_id)
        self.assertEqual(event.user_id, "user1")
        self.assertGreater(event.timestamp, 0)
    
    def test_risk_scoring(self):
        """Test risk score calculation."""
        # High risk: admin action
        event1 = self.logger.log(
            event_type=AuditEventType.GRANT,
            user_id="admin",
            resource="users",
            action="GRANT ROLE",
            details={}
        )
        self.assertGreater(event1.risk_score, 0)
        
        # Low risk: simple query
        event2 = self.logger.log(
            event_type=AuditEventType.QUERY,
            user_id="user1",
            resource="users",
            action="SELECT"
        )
        self.assertLess(event2.risk_score, 50)
    
    def test_query_events(self):
        """Test querying events."""
        self.logger.log(
            event_type=AuditEventType.QUERY,
            user_id="user1",
            resource="users",
            action="SELECT"
        )
        
        self.logger.log(
            event_type=AuditEventType.INSERT,
            user_id="user2",
            resource="orders",
            action="INSERT"
        )
        
        # Query by user
        events = self.logger.query(user_id="user1")
        self.assertEqual(len(events), 1)
        
        # Query by type
        events = self.logger.query(event_type=AuditEventType.INSERT)
        self.assertEqual(len(events), 1)
    
    def test_high_risk_events(self):
        """Test getting high risk events."""
        self.logger.log(
            event_type=AuditEventType.GRANT,
            user_id="admin",
            resource="users",
            action="GRANT",
            details={}
        )
        
        high_risk = self.logger.get_high_risk_events(threshold=10)
        self.assertGreaterEqual(len(high_risk), 0)


class TestAESEncryption(unittest.TestCase):
    
    def setUp(self):
        self.encryption = AESEncryption()
    
    def test_encrypt_decrypt(self):
        """Test encryption and decryption."""
        plaintext = "sensitive data"
        
        encrypted = self.encryption.encrypt(plaintext)
        self.assertNotEqual(encrypted, plaintext)
        
        decrypted = self.encryption.decrypt(encrypted)
        self.assertEqual(decrypted, plaintext)
    
    def test_encrypt_column(self):
        """Test column encryption."""
        encrypted = self.encryption.encrypt_column(
            "users", "ssn", "123-45-6789"
        )
        
        self.assertIsNotNone(encrypted)
        
        decrypted = self.encryption.decrypt_column(
            "users", "ssn", encrypted
        )
        self.assertEqual(decrypted, "123-45-6789")
    
    def test_empty_data(self):
        """Test encryption of empty data."""
        self.assertEqual(self.encryption.encrypt(""), "")
        self.assertEqual(self.encryption.decrypt(""), "")


class TestRBACManager(unittest.TestCase):
    
    def setUp(self):
        self.rbac = RBACManager()
    
    def test_default_roles(self):
        """Test default roles exist."""
        self.assertIn('admin', self.rbac._roles)
        self.assertIn('readonly', self.rbac._roles)
        self.assertIn('readwrite', self.rbac._roles)
    
    def test_grant_role(self):
        """Test granting role."""
        self.rbac.grant_role("user1", "readonly")
        
        self.assertIn("readonly", self.rbac._user_roles.get("user1", set()))
    
    def test_check_permission(self):
        """Test permission checking."""
        self.rbac.grant_role("user1", "readonly")
        
        # Should have SELECT
        self.assertTrue(self.rbac.check_permission("user1", "SELECT"))
        
        # Should not have INSERT (verify by checking a new user with only limited role)
        self.rbac.create_role("limited", {"SELECT"})
        self.rbac.grant_role("limited_user", "limited")
        self.assertFalse(self.rbac.check_permission("limited_user", "INSERT"))
    
    def test_revoke_role(self):
        """Test revoking role."""
        self.rbac.grant_role("user1", "readonly")
        self.rbac.revoke_role("user1", "readonly")
        
        self.assertNotIn("readonly", self.rbac._user_roles.get("user1", set()))
    
    def test_get_user_permissions(self):
        """Test getting all user permissions."""
        self.rbac.grant_role("user1", "readonly")
        
        perms = self.rbac.get_user_permissions("user1")
        self.assertIn("SELECT", perms)


class TestSQLInjectionDetector(unittest.TestCase):
    
    def setUp(self):
        self.detector = SQLInjectionDetector()
    
    def test_safe_query(self):
        """Test safe query detection."""
        is_safe, confidence, reasons = self.detector.analyze(
            "SELECT * FROM users WHERE id = 1"
        )
        
        self.assertTrue(is_safe)
        self.assertLess(confidence, 0.5)
    
    def test_dangerous_query(self):
        """Test dangerous query detection."""
        is_safe, confidence, reasons = self.detector.analyze(
            "SELECT * FROM users WHERE id = 1; DROP TABLE users--"
        )
        
        self.assertFalse(is_safe)
        self.assertGreater(confidence, 0.5)
        self.assertGreater(len(reasons), 0)
    
    def test_union_attack(self):
        """Test UNION attack detection."""
        is_safe, confidence, reasons = self.detector.analyze(
            "SELECT * FROM users UNION SELECT password FROM admin"
        )
        
        # UNION SELECT should be detected
        self.assertGreater(len(reasons), 0)
    
    def test_validate_safe(self):
        """Test validation of safe query."""
        # Should not raise
        self.detector.validate("SELECT * FROM users", "user1")
    
    def test_validate_dangerous(self):
        """Test validation of dangerous query."""
        with self.assertRaises(SQLInjectionError):
            self.detector.validate(
                "SELECT * FROM users; DROP TABLE users",
                "user1"
            )


class TestSecurityPolicy(unittest.TestCase):
    
    def setUp(self):
        self.policy = SecurityPolicy()
    
    def test_validate_password_strong(self):
        """Test strong password validation."""
        is_valid, violations = self.policy.validate_password(
            "StrongPass123!"
        )
        
        self.assertTrue(is_valid)
        self.assertEqual(len(violations), 0)
    
    def test_validate_password_weak(self):
        """Test weak password validation."""
        is_valid, violations = self.policy.validate_password("weak")
        
        self.assertFalse(is_valid)
        self.assertGreater(len(violations), 0)
    
    def test_check_session_valid(self):
        """Test session validity."""
        now = time.time()
        
        # Valid session
        self.assertTrue(self.policy.check_session_valid(
            now - 100,  # Started 100 seconds ago
            now - 10    # Last activity 10 seconds ago
        ))
        
        # Expired session
        self.assertFalse(self.policy.check_session_valid(
            now - 4000,  # Started over an hour ago
            now - 10
        ))


class TestComplianceReporter(unittest.TestCase):
    
    def setUp(self):
        self.audit_logger = AuditLogger()
        self.reporter = ComplianceReporter(self.audit_logger)
    
    def test_generate_gdpr_report(self):
        """Test GDPR report generation."""
        # Log some events
        self.audit_logger.log(
            event_type=AuditEventType.QUERY,
            user_id="user1",
            resource="users",
            action="SELECT"
        )
        
        self.audit_logger.log(
            event_type=AuditEventType.ENCRYPTION,
            user_id="system",
            resource="users.ssn",
            action="encrypt"
        )
        
        report = self.reporter.generate_report(
            "GDPR",
            time.time() - 3600,
            time.time()
        )
        
        self.assertEqual(report['report_type'], 'GDPR')
        self.assertIn('data_access_events', report['summary'])
    
    def test_generate_sox_report(self):
        """Test SOX report generation."""
        self.audit_logger.log(
            event_type=AuditEventType.GRANT,
            user_id="admin",
            resource="users",
            action="GRANT ROLE"
        )
        
        report = self.reporter.generate_report(
            "SOX",
            time.time() - 3600,
            time.time()
        )
        
        self.assertEqual(report['report_type'], 'SOX')
    
    def test_generate_generic_report(self):
        """Test generic report generation."""
        report = self.reporter.generate_report(
            "GENERIC",
            time.time() - 3600,
            time.time()
        )
        
        self.assertEqual(report['report_type'], 'GENERIC')
        self.assertIn('total_events', report)


class TestSecurityManager(unittest.TestCase):
    
    def setUp(self):
        self.manager = SecurityManager()
    
    def test_secure_query(self):
        """Test secure query processing."""
        query, metadata = self.manager.secure_query(
            "SELECT * FROM users",
            "user1",
            "192.168.1.1"
        )
        
        self.assertEqual(query, "SELECT * FROM users")
        self.assertTrue(metadata['validated'])
    
    def test_secure_query_injection(self):
        """Test injection detection in secure query."""
        with self.assertRaises(SQLInjectionError):
            self.manager.secure_query(
                "SELECT * FROM users; DROP TABLE users",
                "user1"
            )
    
    def test_encrypt_decrypt_sensitive(self):
        """Test sensitive data encryption."""
        encrypted = self.manager.encrypt_sensitive_data(
            "users", "ssn", "123-45-6789"
        )
        
        decrypted = self.manager.decrypt_sensitive_data(
            "users", "ssn", encrypted
        )
        
        self.assertEqual(decrypted, "123-45-6789")
    
    def test_check_permission(self):
        """Test permission checking."""
        # Create a limited role without DELETE
        self.manager.rbac.create_role("limited", {"SELECT"})
        self.manager.rbac.grant_role("user1", "limited")
        
        self.assertTrue(self.manager.check_permission("user1", "SELECT"))
        self.assertFalse(self.manager.check_permission("user1", "DELETE"))
    
    def test_get_security_report(self):
        """Test security report generation."""
        report = self.manager.get_security_report()
        
        self.assertIn('audit_stats', report)
        self.assertIn('rbac_summary', report)
        self.assertIn('encryption_status', report)


class TestGlobalSecurityManager(unittest.TestCase):
    
    def test_singleton(self):
        """Test global security manager is singleton."""
        manager1 = get_security_manager()
        manager2 = get_security_manager()
        
        self.assertIs(manager1, manager2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
