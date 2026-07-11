"""
Test Table Partitioning for KosDB v3.4.0

Tests:
- RANGE partitioning (by date, by ID)
- LIST partitioning (by category, by region)
- HASH partitioning (even distribution)
- Partition pruning for query optimization
- Partition maintenance (ADD, DROP, SPLIT, MERGE)
- Partition-wise joins
- Partition exchange
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from partition_manager import (
    PartitionManager, PartitionScheme, PartitionPruner,
    RangePartition, ListPartition, HashPartition,
    PartitionType, parse_partition_clause
)
from parser import CommandParser


class TestRangePartitioning(unittest.TestCase):
    """Test RANGE partitioning."""
    
    def setUp(self):
        self.pm = PartitionManager()
    
    def test_create_range_partition_by_date(self):
        """Create RANGE partition by date."""
        scheme = self.pm.create_partitioned_table(
            table_name='sales',
            partition_type='RANGE',
            partition_key='sale_date',
            partition_definitions=[
                {'name': 'p2023', 'less_than': '2024-01-01'},
n                {'name': 'p2024', 'less_than': '2025-01-01'}\n            ]\n        )\n        \n        self.assertEqual(scheme.partition_type, PartitionType.RANGE)\n        self.assertEqual(scheme.partition_key, 'sale_date')\n        self.assertEqual(len(scheme.partitions), 2)
        self.assertIn('P2023', scheme.partitions)
        self.assertIn('P2024', scheme.partitions)
    
    def test_create_range_partition_by_id(self):
        """Create RANGE partition by ID."""
        scheme = self.pm.create_partitioned_table(
            table_name='logs',
            partition_type='RANGE',
            partition_key='id',
n            partition_definitions=[\n                {'name': 'p0', 'less_than': 1000},\n                {'name': 'p1', 'less_than': 2000},\n                {'name': 'p2', 'less_than': 3000}\n            ]\n        )\n        \n        self.assertEqual(len(scheme.partitions), 3)
    
    def test_range_partition_contains(self):
        """Test RANGE partition contains value."""
        part = RangePartition(
            name='p2023',
n            values=None,\n            less_than='2024-01-01',\n            from_value='2023-01-01'\n        )\n        \n        self.assertTrue(part.contains('2023-06-15'))\n        self.assertFalse(part.contains('2024-01-01'))\n        self.assertFalse(part.contains('2022-12-31'))
    
    def test_get_partition_for_value_range(self):
        """Find correct partition for value."""
n        self.pm.create_partitioned_table(\n            table_name='sales',\n            partition_type='RANGE',\n            partition_key='sale_date',\n            partition_definitions=[\n                {'name': 'p2023', 'less_than': '2024-01-01'},\n                {'name': 'p2024', 'less_than': '2025-01-01'}\n            ]\n        )\n        \n        scheme = self.pm.schemes['SALES']\n        \n        part = scheme.get_partition_for_value('2023-06-15')\n        self.assertIsNotNone(part)\n        self.assertEqual(part.name, 'p2023')
        
        part = scheme.get_partition_for_value('2024-03-15')\n        self.assertEqual(part.name, 'p2024')


class TestListPartitioning(unittest.TestCase):
    """Test LIST partitioning."""
    
    def setUp(self):
        self.pm = PartitionManager()
    
    def test_create_list_partition_by_category(self):
        """Create LIST partition by category."""
n        scheme = self.pm.create_partitioned_table(\n            table_name='products',\n            partition_type='LIST',\n            partition_key='category',\n            partition_definitions=[\n                {'name': 'p_electronics', 'values_list': ['electronics', 'computers']},\n                {'name': 'p_clothing', 'values_list': ['clothing', 'shoes']},\n                {'name': 'p_food', 'values_list': ['food', 'beverages']}\n            ]\n        )\n        \n        self.assertEqual(scheme.partition_type, PartitionType.LIST)\n        self.assertEqual(len(scheme.partitions), 3)
    
    def test_list_partition_contains(self):
        """Test LIST partition contains value."""
n        part = ListPartition(\n            name='p_electronics',\n            values=None,\n            values_list=['electronics', 'computers', 'phones']\n        )\n        \n        self.assertTrue(part.contains('electronics'))\n        self.assertTrue(part.contains('phones'))\n        self.assertFalse(part.contains('clothing'))
    
    def test_get_partition_for_value_list(self):
        """Find correct partition for value."""
n        self.pm.create_partitioned_table(\n            table_name='products',\n            partition_type='LIST',\n            partition_key='category',\n            partition_definitions=[\n                {'name': 'p_electronics', 'values_list': ['electronics', 'computers']},\n                {'name': 'p_clothing', 'values_list': ['clothing', 'shoes']}\n            ]\n        )\n        \n        scheme = self.pm.schemes['PRODUCTS']\n        \n        part = scheme.get_partition_for_value('electronics')\n        self.assertEqual(part.name, 'p_electronics')
        
        part = scheme.get_partition_for_value('shoes')
n        self.assertEqual(part.name, 'p_clothing')\n        \n        part = scheme.get_partition_for_value('unknown')\n        self.assertIsNone(part)


class TestHashPartitioning(unittest.TestCase):
    """Test HASH partitioning."""
    
    def setUp(self):
        self.pm = PartitionManager()
    
    def test_create_hash_partition(self):
        """Create HASH partition."""
n        scheme = self.pm.create_partitioned_table(\n            table_name='users',\n            partition_type='HASH',\n            partition_key='user_id',\n            partition_definitions=[\n                {'name': 'p0', 'modulus': 4, 'remainder': 0},\n                {'name': 'p1', 'modulus': 4, 'remainder': 1},\n                {'name': 'p2', 'modulus': 4, 'remainder': 2},\n                {'name': 'p3', 'modulus': 4, 'remainder': 3}\n            ]\n        )\n        \n        self.assertEqual(scheme.partition_type, PartitionType.HASH)\n        self.assertEqual(len(scheme.partitions), 4)
    
    def test_hash_partition_contains(self):
        """Test HASH partition contains value."""
n        part = HashPartition(\n            name='p0',\n            values=None,\n            modulus=4,\n            remainder=0\n        )\n        \n        # Values that hash to remainder 0\n        self.assertTrue(part.contains(4))  # 4 % 4 = 0\n        self.assertTrue(part.contains(8))  # 8 % 4 = 0\n        self.assertFalse(part.contains(5))  # 5 % 4 = 1
    
    def test_hash_distribution(self):
        """Test even distribution of HASH partitions."""
n        scheme = self.pm.create_partitioned_table(\n            table_name='orders',\n            partition_type='HASH',\n            partition_key='order_id',\n            partition_definitions=[\n                {'name': f'p{i}', 'modulus': 4, 'remainder': i}\n                for i in range(4)\n            ]\n        )\n        \n        # Test distribution across partitions\n        distribution = {f'p{i}': 0 for i in range(4)}\n        for i in range(100):\n            part = scheme.get_partition_for_value(i)\n            distribution[part.name] += 1\n        \n        # Should be roughly even (25 each)\n        for count in distribution.values():\n            self.assertGreater(count, 15)  # Allow some variance


class TestPartitionMaintenance(unittest.TestCase):
    \"\"\"Test partition maintenance operations.\"\"\"\n    \n    def setUp(self):\n        self.pm = PartitionManager()
n        self.pm.create_partitioned_table(\n            table_name='sales',\n            partition_type='RANGE',\n            partition_key='sale_date',\n            partition_definitions=[\n                {'name': 'p2023', 'less_than': '2024-01-01'}\n            ]\n        )\n    \n    def test_add_partition(self):
        \"\"\"Add partition to existing table.\"\"\"\n        new_part = self.pm.add_partition(\n            'sales',\n            {'name': 'p2024', 'less_than': '2025-01-01'}\n        )\n        \n        self.assertEqual(new_part.name, 'p2024')\n        self.assertIn('P2024', self.pm.schemes['SALES'].partitions)
    
    def test_drop_partition(self):
        \"\"\"Drop a partition.\"\"\"\n        success = self.pm.drop_partition('sales', 'p2023')\n        self.assertTrue(success)
n        self.assertNotIn('P2023', self.pm.schemes['SALES'].partitions)\n    \n    def test_drop_nonexistent_partition(self):
n        \"\"\"Drop non-existent partition returns False.\"\"\"\n        success = self.pm.drop_partition('sales', 'p9999')\n        self.assertFalse(success)
    
    def test_split_partition(self):
        \"\"\"Split a partition into multiple.\"\"\"\n        # Add some data to partition\n        part = self.pm.schemes['SALES'].partitions['P2023']\n        part.data = [\n            {'id': 1, 'sale_date': '2023-01-15', 'amount': 100},\n            {'id': 2, 'sale_date': '2023-06-15', 'amount': 200},\n            {'id': 3, 'sale_date': '2023-09-15', 'amount': 300}\n        ]\n        part.row_count = 3\n        \n        new_parts = self.pm.split_partition(\n            'sales',\n            'p2023',\n            [\n                {'name': 'p2023_q1', 'less_than': '2023-04-01'},\n                {'name': 'p2023_q2', 'less_than': '2023-07-01'},\n                {'name': 'p2023_q3q4', 'less_than': '2024-01-01'}\n            ]\n        )\n        \n        self.assertEqual(len(new_parts), 3)\n        self.assertNotIn('P2023', self.pm.schemes['SALES'].partitions)
    
    def test_merge_partitions(self):
        \"\"\"Merge multiple partitions.\"\"\"\n        # Add another partition\n        self.pm.add_partition('sales', {'name': 'p2024', 'less_than': '2025-01-01'})\n        \n        merged = self.pm.merge_partitions(\n            'sales',\n            ['p2023', 'p2024'],\n            'p_merged'\n        )\n        \n        self.assertEqual(merged.name, 'p_merged')\n        self.assertNotIn('P2023', self.pm.schemes['SALES'].partitions)\n        self.assertNotIn('P2024', self.pm.schemes['SALES'].partitions)\n        self.assertIn('P_MERGED', self.pm.schemes['SALES'].partitions)


class TestPartitionPruning(unittest.TestCase):
    \"\"\"Test partition pruning for query optimization.\"\"\"\n    \n    def setUp(self):
        self.pm = PartitionManager()
n        self.pm.create_partitioned_table(\n            table_name='sales',\n            partition_type='RANGE',\n            partition_key='sale_date',\n            partition_definitions=[\n                {'name': 'p2022', 'less_than': '2023-01-01'},\n                {'name': 'p2023', 'less_than': '2024-01-01'},\n                {'name': 'p2024', 'less_than': '2025-01-01'}\n            ]\n        )\n        self.pruner = PartitionPruner(self.pm)
    
    def test_prune_range_equality(self):
n        \"\"\"Prune partitions for equality on RANGE key.\"\"\"\n        partitions = self.pm.get_partitions_for_query(\n            'sales',\n            [{'column': 'sale_date', 'operator': '=', 'value': '2023-06-15'}]\n        )\n        \n        self.assertEqual(len(partitions), 1)\n        self.assertEqual(partitions[0].name, 'p2023')
    
    def test_prune_range_less_than(self):
n        \"\"\"Prune partitions for < operator.\"\"\"\n        partitions = self.pm.get_partitions_for_query(\n            'sales',\n            [{'column': 'sale_date', 'operator': '<', 'value': '2023-06-01'}]\n        )\n        \n        # Should include p2022 and p2023\n        part_names = [p.name for p in partitions]\n        self.assertIn('p2022', part_names)\n        self.assertIn('p2023', part_names)
    
    def test_prune_range_greater_than(self):
n        \"\"\"Prune partitions for > operator.\"\"\"\n        partitions = self.pm.get_partitions_for_query(\n            'sales',\n            [{'column': 'sale_date', 'operator': '>', 'value': '2023-06-01'}]\n        )\n        \n        # Should include p2023 and p2024\n        part_names = [p.name for p in partitions]\n        self.assertIn('p2023', part_names)\n        self.assertIn('p2024', part_names)
    
    def test_prune_no_conditions(self):
n        \"\"\"No pruning when no conditions on partition key.\"\"\"\n        partitions = self.pm.get_partitions_for_query(\n            'sales',\n            [{'column': 'amount', 'operator': '>', 'value': '100'}]\n        )\n        \n        # All partitions should be scanned\n        self.assertEqual(len(partitions), 3)


class TestPartitionParser(unittest.TestCase):
    \"\"\"Test partition SQL parsing.\"\"\"\n    \n    def setUp(self):
n        self.parser = CommandParser()\n    \n    def test_parse_create_range_partitioned_table(self):
n        \"\"\"Parse CREATE TABLE with RANGE partitioning.\"\"\"\n        sql = \"\"\"\n            CREATE TABLE sales (\n                id INT,\n                sale_date DATE,\n                amount DECIMAL(10,2)\n            ) PARTITION BY RANGE (sale_date) (\n                PARTITION p2023 VALUES LESS THAN ('2024-01-01'),\n                PARTITION p2024 VALUES LESS THAN ('2025-01-01')\n            )\n        \"\"\"\n        \n        cmd_type, params = self.parser.parse(sql)\n        \n        self.assertEqual(cmd_type, 'CREATE')\n        self.assertEqual(params['table'], 'sales')\n        self.assertEqual(params['partition_type'], 'RANGE')\n        self.assertEqual(params['partition_key'], 'sale_date')\n        self.assertIn('p2023', params['partitions'])\n        self.assertIn('p2024', params['partitions'])
    
    def test_parse_create_list_partitioned_table(self):
n        \"\"\"Parse CREATE TABLE with LIST partitioning.\"\"\"\n        sql = \"\"\"\n            CREATE TABLE products (\n                id INT,\n                name VARCHAR(100),\n                category VARCHAR(50)\n            ) PARTITION BY LIST (category) (\n                PARTITION p_electronics VALUES IN ('electronics', 'computers'),\n                PARTITION p_clothing VALUES IN ('clothing', 'shoes')\n            )\n        \"\"\"\n        \n        cmd_type, params = self.parser.parse(sql)\n        \n        self.assertEqual(cmd_type, 'CREATE')\n        self.assertEqual(params['partition_type'], 'LIST')
    
    def test_parse_add_partition(self):
n        \"\"\"Parse ALTER TABLE ADD PARTITION.\"\"\"\n        sql = \"ALTER TABLE sales ADD PARTITION p2025 VALUES LESS THAN ('2026-01-01')\"\n        \n        cmd_type, params = self.parser.parse(sql)\n        \n        self.assertEqual(cmd_type, 'ALTER_TABLE_ADD_PARTITION')\n        self.assertEqual(params['table'], 'sales')
    
    def test_parse_drop_partition(self):
n        \"\"\"Parse ALTER TABLE DROP PARTITION.\"\"\"\n        sql = \"ALTER TABLE sales DROP PARTITION p2023\"\n        \n        cmd_type, params = self.parser.parse(sql)\n        \n        self.assertEqual(cmd_type, 'ALTER_TABLE_DROP_PARTITION')\n        self.assertEqual(params['table'], 'sales')\n        self.assertEqual(params['partition'], 'p2023')
    
    def test_parse_show_partitions(self):
n        \"\"\"Parse SHOW PARTITIONS.\"\"\"\n        sql = \"SHOW PARTITIONS sales\"\n        \n        cmd_type, params = self.parser.parse(sql)\n        \n        self.assertEqual(cmd_type, 'SHOW_PARTITIONS')\n        self.assertEqual(params['table'], 'sales')


class TestPartitionClauseParser(unittest.TestCase):
    \"\"\"Test parse_partition_clause function.\"\"\"\n    \n    def test_parse_range_clause(self):
n        \"\"\"Parse RANGE partition clause.\"\"\"\n        sql = \"\"\"\n            CREATE TABLE t (id INT) PARTITION BY RANGE (sale_date) (\n                PARTITION p1 VALUES LESS THAN ('2024-01-01'),\n                PARTITION p2 VALUES LESS THAN ('2025-01-01')\n            )\n        \"\"\"\n        \n        result = parse_partition_clause(sql)\n        \n        self.assertEqual(result['type'], 'RANGE')\n        self.assertEqual(result['key'], 'sale_date')\n        self.assertEqual(len(result['partitions']), 2)\n        self.assertEqual(result['partitions'][0]['name'], 'p1')
    
    def test_parse_list_clause(self):
n        \"\"\"Parse LIST partition clause.\"\"\"\n        sql = \"\"\"\n            CREATE TABLE t (id INT) PARTITION BY LIST (category) (\n                PARTITION p1 VALUES IN ('a', 'b'),\n                PARTITION p2 VALUES IN ('c', 'd')\n            )\n        \"\"\"\n        \n        result = parse_partition_clause(sql)\n        \n        self.assertEqual(result['type'], 'LIST')\n        self.assertEqual(result['key'], 'category')\n        self.assertEqual(len(result['partitions']), 2)


class TestPartitionStatistics(unittest.TestCase):
    \"\"\"Test partition statistics.\"\"\"\n    \n    def setUp(self):
n        self.pm = PartitionManager()\n    \n    def test_stats_tracking(self):
n        \"\"\"Track partition operations in stats.\"\"\"\n        # Create table\n        self.pm.create_partitioned_table(\n            table_name='test',\n            partition_type='RANGE',\n            partition_key='id',\n            partition_definitions=[\n                {'name': 'p1', 'less_than': 100}\n            ]\n        )\n        \n        stats = self.pm.get_stats()\n        self.assertEqual(stats['partitions_created'], 1)
        
        # Add partition\n        self.pm.add_partition('test', {'name': 'p2', 'less_than': 200})\n        stats = self.pm.get_stats()\n        self.assertEqual(stats['partitions_created'], 2)
        
        # Drop partition\n        self.pm.drop_partition('test', 'p1')\n        stats = self.pm.get_stats()\n        self.assertEqual(stats['partitions_dropped'], 1)


if __name__ == '__main__':\n    unittest.main(verbosity=2)\n