#!/usr/bin/env python3
"""Unit tests for security parser."""

import unittest
from security_parser import SecurityParser, get_security_parser


class TestSecurityParser(unittest.TestCase):
    def setUp(self):
        self.parser = SecurityParser()

    def test_audit_log(self):
        result = self.parser.parse('AUDIT LOG USER alice TYPE login RISK 50')
        self.assertEqual(result['type'], 'AUDIT_LOG')
        self.assertEqual(result['min_risk'], 50)

    def test_export_audit(self):
        result = self.parser.parse('EXPORT AUDIT LOG FORMAT csv')
        self.assertEqual(result['format'], 'csv')

    def test_grant_role(self):
        result = self.parser.parse('GRANT ROLE alice admin')
        self.assertEqual(result['type'], 'GRANT_ROLE')

    def test_revoke_role(self):
        result = self.parser.parse('REVOKE ROLE alice admin')
        self.assertEqual(result['type'], 'REVOKE_ROLE')

    def test_check_permission(self):
        result = self.parser.parse('CHECK PERMISSION alice SELECT')
        self.assertEqual(result['type'], 'CHECK_PERMISSION')

    def test_encrypt_column(self):
        result = self.parser.parse('ENCRYPT COLUMN users ssn 123-45-6789')
        self.assertEqual(result['type'], 'ENCRYPT_COLUMN')

    def test_decrypt_column(self):
        result = self.parser.parse('DECRYPT COLUMN users ssn cipher')
        self.assertEqual(result['type'], 'DECRYPT_COLUMN')

    def test_validate_password(self):
        result = self.parser.parse('VALIDATE PASSWORD Secret123!')
        self.assertEqual(result['type'], 'VALIDATE_PASSWORD')

    def test_sql_injection(self):
        result = self.parser.parse('CHECK SQL INJECTION SELECT * FROM users')
        self.assertEqual(result['type'], 'CHECK_SQL_INJECTION')

    def test_compliance_report(self):
        result = self.parser.parse('COMPLIANCE REPORT SOC2 DAYS 30')
        self.assertEqual(result['days'], 30)

    def test_security_stats(self):
        result = self.parser.parse('SECURITY STATS')
        self.assertEqual(result['type'], 'SECURITY_STATS')

    def test_high_risk_events(self):
        result = self.parser.parse('HIGH RISK EVENTS THRESHOLD 75')
        self.assertEqual(result['threshold'], 75)

    def test_unrelated(self):
        self.assertIsNone(self.parser.parse('SELECT 1'))

    def test_singleton(self):
        self.assertIs(get_security_parser(), get_security_parser())


if __name__ == '__main__':
    unittest.main()
