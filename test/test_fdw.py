"""
Test Foreign Data Wrappers for KosDB v3.4.0

Tests:
- Server creation and management
- User mappings
- Foreign table creation
- Schema import
- Query execution with predicate pushdown
- Data type mapping
- CSV file access
- REST API access
"""

import unittest
import sys
import os
import tempfile
import csv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fdw_manager import (
    FDWManager, FDWServer, UserMapping, ForeignTable,
    FDWType, PostgreSQLFDWHandler, MySQLFDWHandler,
    CSVFDWHandler, RESTAPIFDWHandler,
    parse_create_server, parse_create_foreign_table
)


class TestFDWManager(unittest.TestCase):
    """Test FDW manager functionality."""
    
    def setUp(self):
        self.manager = FDWManager()
    
    def test_create_postgresql_server(self):
        """Create PostgreSQL foreign server."""
        server = self.manager.create_server(
            name='pg_test',
            fdw_type='postgresql',
            options={
                'host': 'localhost',
                'port': '5432',
                'dbname': 'test_db'
            }
        )
        
        self.assertEqual(server.name, 'pg_test')
        self.assertEqual(server.fdw_type, FDWType.POSTGRESQL)
        self.assertEqual(server.options['host'], 'localhost')
    
    def test_create_mysql_server(self):
        """Create MySQL foreign server."""
        server = self.manager.create_server(
            name='mysql_test',
            fdw_type='mysql',
            options={
                'host': 'localhost',
                'port': '3306',
                'database': 'test_db'
            }
        )
        
        self.assertEqual(server.fdw_type, FDWType.MYSQL)
    
    def test_create_csv_server(self):
        """Create CSV file server."""
        server = self.manager.create_server(
            name='csv_test',
            fdw_type='csv',
            options={
                'filename': '/tmp/test.csv',
                'delimiter': ','
            }
        )
        
        self.assertEqual(server.fdw_type, FDWType.CSV)
    
    def test_create_duplicate_server(self):
        """Cannot create duplicate servers."""
        self.manager.create_server('dup_test', 'postgresql', {'host': 'localhost'})
        
        with self.assertRaises(ValueError) as context:
            self.manager.create_server('dup_test', 'mysql', {'host': 'other'})
        
        self.assertIn('already exists', str(context.exception))
    
    def test_drop_server(self):
        """Drop foreign server."""
        self.manager.create_server('drop_test', 'postgresql', {'host': 'localhost'})
        
        success = self.manager.drop_server('drop_test')
        
        self.assertTrue(success)
        self.assertNotIn('drop_test', self.manager.servers)
    
    def test_drop_nonexistent_server(self):
        """Drop non-existent server returns False."""
        success = self.manager.drop_server('nonexistent')
        
        self.assertFalse(success)


class TestUserMapping(unittest.TestCase):
    """Test user mappings."""
    
    def setUp(self):
        self.manager = FDWManager()
        self.manager.create_server('pg_server', 'postgresql', {'host': 'localhost'})
    
    def test_create_user_mapping(self):
        """Create user mapping."""
        mapping = self.manager.create_user_mapping(
            server_name='pg_server',
            local_user='kosdb_user',
            remote_user='postgres',
            remote_password='secret'
        )
        
        self.assertEqual(mapping.server_name, 'pg_server')
        self.assertEqual(mapping.local_user, 'kosdb_user')
        self.assertEqual(mapping.remote_user, 'postgres')
    
    def test_create_mapping_for_nonexistent_server(self):
n        \"\"\"Cannot create mapping for non-existent server.\"\"\"\n        with self.assertRaises(ValueError) as context:\n            self.manager.create_user_mapping(\n                server_name='nonexistent',\n                local_user='user',\n                remote_user='remote'\n            )\n        \n        self.assertIn('does not exist', str(context.exception))


class TestForeignTable(unittest.TestCase):
n    \"\"\"Test foreign table creation.\"\"\"\n    \n    def setUp(self):
n        self.manager = FDWManager()\n        self.manager.create_server('pg_server', 'postgresql', {'host': 'localhost'})\n    \n    def test_create_foreign_table(self):
n        \"\"\"Create foreign table.\"\"\"\n        table = self.manager.create_foreign_table(\n            name='remote_customers',\n            local_schema='public',\n            server_name='pg_server',\n            columns=[\n                {'name': 'id', 'type': 'INTEGER'},\n                {'name': 'name', 'type': 'TEXT'},\n                {'name': 'email', 'type': 'TEXT'}\n            ],\n            remote_schema='public',\n            remote_table='customers'\n        )\n        \n        self.assertEqual(table.name, 'remote_customers')\n        self.assertEqual(table.server_name, 'pg_server')\n        self.assertEqual(len(table.columns), 3)\n    \n    def test_create_table_for_nonexistent_server(self):
n        \"\"\"Cannot create table for non-existent server.\"\"\"\n        with self.assertRaises(ValueError) as context:\n            self.manager.create_foreign_table(\n                name='test',\n                local_schema='public',\n                server_name='nonexistent',\n                columns=[{'name': 'id', 'type': 'INTEGER'}]\n            )\n        \n        self.assertIn('does not exist', str(context.exception))


class TestCSVFDWHandler(unittest.TestCase):
n    \"\"\"Test CSV file FDW handler.\"\"\"\n    \n    def setUp(self):
n        # Create temporary CSV file\n        self.temp_file = tempfile.NamedTemporaryFile(\n            mode='w', delete=False, suffix='.csv'\n        )\n        \n        writer = csv.writer(self.temp_file)\n        writer.writerow(['id', 'name', 'value'])\n        writer.writerow([1, 'Alice', '100'])\n        writer.writerow([2, 'Bob', '200.5'])\n        writer.writerow([3, 'Charlie', 'true'])\n        \n        self.temp_file.close()\n        \n        # Create server\n        self.server = FDWServer(\n            name='csv_server',\n            fdw_type=FDWType.CSV,\n            options={'filename': self.temp_file.name, 'delimiter': ','}\n        )\n        \n        self.handler = CSVFDWHandler(self.server)\n    \n    def tearDown(self):
n        \"\"\"Clean up temporary file.\"\"\"\n        os.unlink(self.temp_file.name)\n    \n    def test_csv_read(self):
n        \"\"\"Read data from CSV file.\"\"\"\n        conn = self.handler.connect()\n        try:\n            results = self.handler.execute_query(conn, '', [])\n            \n            self.assertEqual(len(results), 3)\n            self.assertEqual(results[0]['name'], 'Alice')\n            self.assertEqual(results[0]['id'], 1)  # Converted to int\n            self.assertEqual(results[1]['value'], 200.5)  # Converted to float\n        finally:\n            self.handler.disconnect(conn)\n    \n    def test_csv_schema_inference(self):
n        \"\"\"Infer schema from CSV file.\"\"\"\n        conn = self.handler.connect()\n        try:\n            schema = self.handler.get_table_schema(conn, '', 'test')\n            \n            self.assertEqual(len(schema), 3)\n            self.assertEqual(schema[0]['name'], 'id')\n            self.assertEqual(schema[0]['type'], 'INTEGER')\n        finally:\n            self.handler.disconnect(conn)\n    \n    def test_type_inference(self):
n        \"\"\"Test type inference from values.\"\"\"\n        self.assertEqual(self.handler._infer_type('123'), 123)\n        self.assertEqual(self.handler._infer_type('45.67'), 45.67)\n        self.assertEqual(self.handler._infer_type('true'), True)\n        self.assertEqual(self.handler._infer_type('hello'), 'hello')
        self.assertIsNone(self.handler._infer_type(''))


class TestTypeMapping(unittest.TestCase):
n    \"\"\"Test data type mapping.\"\"\"\n    \n    def test_postgresql_type_mapping(self):
n        \"\"\"Test PostgreSQL type mappings.\"\"\"\n        server = FDWServer('pg', FDWType.POSTGRESQL, {})\n        handler = PostgreSQLFDWHandler(server)\n        \n        self.assertEqual(handler.map_external_type('INTEGER'), 'INTEGER')\n        self.assertEqual(handler.map_external_type('VARCHAR'), 'TEXT')\n        self.assertEqual(handler.map_external_type('BOOLEAN'), 'BOOLEAN')\n        self.assertEqual(handler.map_external_type('UNKNOWN'), 'TEXT')  # Fallback\n    \n    def test_mysql_type_mapping(self):
n        \"\"\"Test MySQL type mappings.\"\"\"\n        server = FDWServer('mysql', FDWType.MYSQL, {})\n        handler = MySQLFDWHandler(server)\n        \n        self.assertEqual(handler.map_external_type('INT'), 'INTEGER')\n        self.assertEqual(handler.map_external_type('VARCHAR'), 'TEXT')\n        self.assertEqual(handler.map_external_type('DATETIME'), 'TEXT')\n    \n    def test_value_conversion(self):
n        \"\"\"Test value conversion.\"\"\"\n        server = FDWServer('pg', FDWType.POSTGRESQL, {})\n        handler = PostgreSQLFDWHandler(server)\n        \n        self.assertEqual(handler.convert_value('123', 'INTEGER'), 123)\n        self.assertEqual(handler.convert_value('45.67', 'REAL'), 45.67)\n        self.assertEqual(handler.convert_value('true', 'BOOLEAN'), True)\n        self.assertEqual(handler.convert_value('hello', 'TEXT'), 'hello')


class TestPredicatePushdown(unittest.TestCase):
n    \"\"\"Test predicate pushdown capabilities.\"\"\"\n    \n    def test_postgresql_pushdown(self):
n        \"\"\"PostgreSQL supports most operators.\"\"\"\n        server = FDWServer('pg', FDWType.POSTGRESQL, {})\n        handler = PostgreSQLFDWHandler(server)\n        \n        self.assertTrue(handler.can_pushdown('='))\n        self.assertTrue(handler.can_pushdown('<'))\n        self.assertTrue(handler.can_pushdown('LIKE'))\n        self.assertTrue(handler.can_pushdown('IN'))\n        self.assertFalse(handler.can_pushdown('CUSTOM_OP'))\n    \n    def test_csv_no_pushdown(self):
n        \"\"\"CSV files don't support pushdown.\"\"\"\n        server = FDWServer('csv', FDWType.CSV, {})\n        handler = CSVFDWHandler(server)\n        \n        self.assertFalse(handler.can_pushdown('='))\n    \n    def test_pushdown_separation(self):
n        \"\"\"Test separating pushable and non-pushable conditions.\"\"\"\n        manager = FDWManager()\n        manager.create_server('pg', 'postgresql', {'host': 'localhost'})\n        manager.create_foreign_table(\n            name='test',\n            local_schema='public',\n            server_name='pg',\n            columns=[{'name': 'id', 'type': 'INTEGER'}]\n        )\n        \n        conditions = [\n            {'column': 'id', 'op': '=', 'value': 1},\n            {'column': 'name', 'op': 'CUSTOM', 'value': 'x'}\n        ]\n        \n        pushable, local = manager.get_pushdown_predicates('test', 'public', conditions)\n        \n        self.assertEqual(len(pushable), 1)\n        self.assertEqual(len(local), 1)


class TestFDWSyntaxParsing(unittest.TestCase):
n    \"\"\"Test FDW SQL syntax parsing.\"\"\"\n    \n    def test_parse_create_server(self):
n        \"\"\"Parse CREATE SERVER statement.\"\"\"\n        sql = \"\"\"\n            CREATE SERVER pg_server\n            FOREIGN DATA WRAPPER postgresql\n            OPTIONS (host 'localhost', port '5432', dbname 'test')\n        \"\"\"\n        \n        result = parse_create_server(sql)\n        \n        self.assertEqual(result['name'], 'pg_server')\n        self.assertEqual(result['fdw_type'], 'postgresql')\n        self.assertEqual(result['options']['host'], 'localhost')\n        self.assertEqual(result['options']['port'], '5432')\n    \n    def test_parse_create_foreign_table(self):
n        \"\"\"Parse CREATE FOREIGN TABLE statement.\"\"\"\n        sql = \"\"\"\n            CREATE FOREIGN TABLE remote_customers (\n                id INTEGER,\n                name VARCHAR(100),\n                email VARCHAR(100)\n            ) SERVER pg_server\n            OPTIONS (schema_name 'public', table_name 'customers')\n        \"\"\"\n        \n        result = parse_create_foreign_table(sql)\n        \n        self.assertEqual(result['name'], 'remote_customers')\n        self.assertEqual(result['server_name'], 'pg_server')\n        self.assertEqual(len(result['columns']), 3)\n        self.assertEqual(result['options']['schema_name'], 'public')


class TestFDWStatistics(unittest.TestCase):
n    \"\"\"Test FDW statistics tracking.\"\"\"\n    \n    def setUp(self):
n        self.manager = FDWManager()\n    \n    def test_stats_tracking(self):
n        \"\"\"Track FDW operations in stats.\"\"\"\n        # Create server\n        self.manager.create_server('pg', 'postgresql', {'host': 'localhost'})\n        \n        stats = self.manager.get_stats()\n        self.assertEqual(stats['servers_created'], 1)\n        self.assertEqual(stats['servers'], 1)\n        \n        # Create table\n        self.manager.create_foreign_table(\n            name='test',\n            local_schema='public',\n            server_name='pg',\n            columns=[{'name': 'id', 'type': 'INTEGER'}]\n        )\n        \n        stats = self.manager.get_stats()\n        self.assertEqual(stats['tables_created'], 1)
        self.assertEqual(stats['tables'], 1)


class TestRESTAPIFDW(unittest.TestCase):
n    \"\"\"Test REST API FDW handler.\"\"\"\n    \n    def test_rest_api_type_mapping(self):
n        \"\"\"Test REST API type mappings.\"\"\"\n        server = FDWServer('api', FDWType.REST_API, {'url': 'http://example.com'})\n        handler = RESTAPIFDWHandler(server)\n        \n        self.assertEqual(handler.map_external_type('string'), 'TEXT')\n        self.assertEqual(handler.map_external_type('integer'), 'INTEGER')\n        self.assertEqual(handler.map_external_type('number'), 'REAL')\n        self.assertEqual(handler.map_external_type('boolean'), 'BOOLEAN')\n    \n    def test_json_type_inference(self):
n        \"\"\"Test JSON type inference.\"\"\"\n        server = FDWServer('api', FDWType.REST_API, {'url': 'http://example.com'})\n        handler = RESTAPIFDWHandler(server)\n        \n        self.assertEqual(handler._infer_json_type('hello'), 'TEXT')\n        self.assertEqual(handler._infer_json_type(123), 'INTEGER')\n        self.assertEqual(handler._infer_json_type(45.67), 'REAL')\n        self.assertEqual(handler._infer_json_type(True), 'BOOLEAN')\n        self.assertEqual(handler._infer_json_type({'a': 1}), 'TEXT')
        self.assertEqual(handler._infer_json_type([1, 2, 3]), 'TEXT')


if __name__ == '__main__':\n    unittest.main(verbosity=2)\n