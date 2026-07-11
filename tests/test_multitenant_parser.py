#!/usr/bin/env python3
"""Unit tests for multitenant parser."""

import unittest
from multitenant_parser import MultitenantParser, get_multitenant_parser


class TestMultitenantParser(unittest.TestCase):
    def setUp(self):
        self.parser = MultitenantParser()

    def test_create_tenant(self):
        result = self.parser.parse('CREATE TENANT t1 NAME TenantOne STORAGE 5 QPM 500 CONNECTIONS 50 TABLES 10')
        self.assertEqual(result['type'], 'CREATE_TENANT')
        self.assertEqual(result['tenant_id'], 't1')

    def test_drop_tenant(self):
        result = self.parser.parse('DROP TENANT t1 FORCE')
        self.assertTrue(result['force'])

    def test_use_tenant(self):
        result = self.parser.parse('USE TENANT t1')
        self.assertEqual(result['type'], 'USE_TENANT')

    def test_list_tenants(self):
        result = self.parser.parse('LIST TENANTS')
        self.assertEqual(result['type'], 'LIST_TENANTS')

    def test_tenant_stats(self):
        result = self.parser.parse('TENANT STATS t1')
        self.assertEqual(result['type'], 'TENANT_STATS')

    def test_set_quota(self):
        result = self.parser.parse('SET TENANT QUOTA t1 STORAGE 20 QPM 2000')
        self.assertEqual(result['type'], 'SET_QUOTA')

    def test_add_row_policy(self):
        result = self.parser.parse('ADD ROW POLICY t1 p1 ON users CONDITION tenant_id = current_tenant')
        self.assertEqual(result['type'], 'ADD_ROW_POLICY')

    def test_remove_row_policy(self):
        result = self.parser.parse('REMOVE ROW POLICY t1 p1')
        self.assertEqual(result['type'], 'REMOVE_ROW_POLICY')

    def test_check_quota(self):
        result = self.parser.parse('CHECK QUOTA t1')
        self.assertEqual(result['type'], 'CHECK_QUOTA')

    def test_tenant_backup(self):
        result = self.parser.parse('TENANT BACKUP t1 TO /tmp/backup')
        self.assertEqual(result['type'], 'TENANT_BACKUP')

    def test_tenant_restore(self):
        result = self.parser.parse('TENANT RESTORE t1 FROM /tmp/backup')
        self.assertEqual(result['type'], 'TENANT_RESTORE')

    def test_unrelated(self):
        self.assertIsNone(self.parser.parse('SELECT 1'))

    def test_singleton(self):
        self.assertIs(get_multitenant_parser(), get_multitenant_parser())


if __name__ == '__main__':
    unittest.main()
