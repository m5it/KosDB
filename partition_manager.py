"""
Partition Manager for KosDB v3.4.0

Provides table partitioning support:
- RANGE partitioning: By range of values (dates, IDs)
- LIST partitioning: By discrete values (categories, regions)
- HASH partitioning: By hash function for even distribution

Features:
- Automatic partition creation and management
- Partition pruning for query optimization
- Partition-wise joins
- Partition maintenance (add, drop, split, merge)
- Partition statistics

Example:
    CREATE TABLE sales (
        id INT,
        sale_date DATE,
        amount DECIMAL(10,2)
    ) PARTITION BY RANGE (sale_date) (
        PARTITION p2023 VALUES LESS THAN ('2024-01-01'),
        PARTITION p2024 VALUES LESS THAN ('2025-01-01')
    );
"""

import re
import hashlib
import time
from typing import Dict, Any, List, Optional, Tuple, Set, Callable, Union
from dataclasses import dataclass, field
from enum import Enum, auto
from datetime import datetime, timedelta


class PartitionType(Enum):
    """Types of table partitioning."""
    RANGE = "RANGE"
    LIST = "LIST"
    HASH = "HASH"
    RANGE_COLUMNS = "RANGE COLUMNS"
    LIST_COLUMNS = "LIST COLUMNS"


class PartitionStrategy(Enum):
    """Partition maintenance strategies."""
    AUTO_CREATE = auto()  # Auto-create partitions
    MANUAL = auto()       # Manual partition management


@dataclass
class Partition:
    """Represents a single partition."""
    name: str
    values: Any  # Range tuple, list of values, or hash modulus
    data: List[Dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_accessed: Optional[float] = None
    
    def touch(self):
        """Update last accessed time."""
        self.last_accessed = time.time()


@dataclass
class RangePartition(Partition):
    """RANGE partition with less than value."""
    less_than: Any = None  # Upper bound (exclusive)
    from_value: Any = None  # Lower bound (inclusive, optional)
    
    def contains(self, value: Any) -> bool:
        """Check if value is in this partition's range."""
        if self.from_value is not None and value < self.from_value:
            return False
        if self.less_than is not None and value >= self.less_than:
            return False
        return True


@dataclass
class ListPartition(Partition):
    """LIST partition with discrete values."""
    values_list: List[Any] = field(default_factory=list)
    
    def contains(self, value: Any) -> bool:
        """Check if value is in this partition's list."""
        return value in self.values_list


@dataclass
class HashPartition(Partition):
    """HASH partition."""
    modulus: int = 0  # Total number of hash partitions
    remainder: int = 0  # This partition's remainder
    
    def contains(self, value: Any) -> bool:
        """Check if value hashes to this partition."""
        hash_val = self._hash_value(value)
        return hash_val % self.modulus == self.remainder
    
    def _hash_value(self, value: Any) -> int:
        """Hash a value."""
        if isinstance(value, (int, float)):
            return int(value)
        return int(hashlib.md5(str(value).encode()).hexdigest(), 16)


@dataclass
class PartitionScheme:
    """Partitioning scheme for a table."""
    table_name: str
    partition_type: PartitionType
    partition_key: Union[str, List[str]]  # Column(s) to partition by
    partitions: Dict[str, Partition] = field(default_factory=dict)
    default_partition: Optional[Partition] = None  # For values not matching any partition
    strategy: PartitionStrategy = PartitionStrategy.MANUAL
    
    def get_partition_for_value(self, value: Any) -> Optional[Partition]:
        """Find partition containing a value."""
        for partition in self.partitions.values():
            if partition.contains(value):
                return partition
        
        return self.default_partition
    
    def get_relevant_partitions(self, 
                                  operator: str, 
                                  value: Any) -> List[Partition]:
        """
        Get partitions relevant to a predicate.
        Used for partition pruning.
        """
        relevant = []
        
        for partition in self.partitions.values():
            if self._partition_matches_predicate(partition, operator, value):
                relevant.append(partition)
        
        return relevant
    
    def _partition_matches_predicate(self, 
                                     partition: Partition, 
                                     operator: str, 
                                     value: Any) -> bool:
        """Check if partition might contain values matching predicate."""
        # For RANGE partitions
        if isinstance(partition, RangePartition):
            if operator == '=':
                return partition.contains(value)
            elif operator in ('<', '<='):
                # Partition relevant if its lower bound < value
                return (partition.from_value is None or 
                        partition.from_value < value or\n                        (operator == '<=' and partition.from_value <= value))\n            elif operator in ('>', '>='):\n                # Partition relevant if its upper bound > value\n                return (partition.less_than is None or\n                        partition.less_than > value or\n                        (operator == '>=' and partition.less_than >= value))\n        \n        # For LIST partitions\n        if isinstance(partition, ListPartition):\n            if operator == '=':\n                return partition.contains(value)\n            # For other operators, include all (conservative)\n            return True\n        \n        # For HASH partitions\n        if isinstance(partition, HashPartition):\n            if operator == '=':\n                return partition.contains(value)\n            # Hash doesn't support range queries well\n            return True\n        \n        return True


class PartitionManager:
    """
    Main partition manager for KosDB.
    
    Manages partitioned tables and provides partition operations.
    """
    
    def __init__(self, storage_func: Optional[Callable] = None):
        self.schemes: Dict[str, PartitionScheme] = {}
        self._storage = storage_func or self._default_storage
        self._lock = threading.RLock()
        self.stats = {
            'partitions_created': 0,\n            'partitions_dropped': 0,\n            'partitions_split': 0,\n            'partitions_merged': 0,\n            'pruning_hits': 0\n        }
    
    def create_partitioned_table(self,\n                                  table_name: str,\n                                  partition_type: str,\n                                  partition_key: Union[str, List[str]],\n                                  partition_definitions: List[Dict],\n                                  default_partition: bool = False) -> PartitionScheme:\n        \"\"\"\n        Create a partitioned table scheme.\n        \n        Args:\n            table_name: Name of the table\n            partition_type: RANGE, LIST, or HASH\n            partition_key: Column(s) to partition by\n            partition_definitions: List of partition specs\n            default_partition: Whether to create a default partition\n        \n        Returns:\n            PartitionScheme object\n        \"\"\"\n        with self._lock:\n            table_key = table_name.upper()\n            if table_key in self.schemes:\n                raise ValueError(f\"Partitioned table '{table_name}' already exists\")\n            \n            try:\n                ptype = PartitionType(partition_type.upper())\n            except ValueError:\n                raise ValueError(f\"Invalid partition type: {partition_type}\")\n            \n            scheme = PartitionScheme(\n                table_name=table_name,\n                partition_type=ptype,\n                partition_key=partition_key\n            )\n            \n            # Create partitions\n            for part_def in partition_definitions:\n                partition = self._create_partition_from_def(ptype, part_def)\n                scheme.partitions[partition.name.upper()] = partition\n                self.stats['partitions_created'] += 1\n            \n            # Create default partition if requested\n            if default_partition:\n                scheme.default_partition = Partition(\n                    name='p_default',\n                    values=None\n                )\n            \n            self.schemes[table_key] = scheme\n            return scheme\n    \n    def _create_partition_from_def(self, \n                                   ptype: PartitionType, \n                                   part_def: Dict) -> Partition:\n        \"\"\"Create partition from definition.\"\"\"\n        name = part_def['name']\n        \n        if ptype == PartitionType.RANGE:\n            return RangePartition(\n                name=name,\n                values=part_def.get('values'),\n                less_than=part_def.get('less_than'),\n                from_value=part_def.get('from_value')\n            )\n        elif ptype == PartitionType.LIST:\n            return ListPartition(\n                name=name,\n                values=part_def.get('values'),\n                values_list=part_def.get('values_list', [])\n            )\n        elif ptype == PartitionType.HASH:\n            return HashPartition(\n                name=name,\n                values=part_def.get('values'),\n                modulus=part_def.get('modulus', 4),\n                remainder=part_def.get('remainder', 0)\n            )\n        else:\n            return Partition(name=name, values=part_def.get('values'))\n    \n    def add_partition(self, \n                      table_name: str, \n                      partition_def: Dict) -> Partition:\n        \"\"\"Add a new partition to existing table.\"\"\"\n        with self._lock:\n            scheme = self.schemes.get(table_name.upper())\n            if not scheme:\n                raise ValueError(f\"Table '{table_name}' not found\")\n            \n            partition = self._create_partition_from_def(\n                scheme.partition_type, partition_def\n            )\n            \n            scheme.partitions[partition.name.upper()] = partition\n            self.stats['partitions_created'] += 1\n            \n            return partition\n    \n    def drop_partition(self, table_name: str, partition_name: str) -> bool:\n        \"\"\"Drop a partition.\"\"\"\n        with self._lock:\n            scheme = self.schemes.get(table_name.upper())\n            if not scheme:\n                return False\n            \n            part_key = partition_name.upper()\n            if part_key in scheme.partitions:\n                del scheme.partitions[part_key]\n                self.stats['partitions_dropped'] += 1\n                return True\n            \n            return False\n    \n    def split_partition(self, \n                        table_name: str, \n                        partition_name: str,\n                        split_definitions: List[Dict]) -> List[Partition]:\n        \"\"\"\n        Split a partition into multiple partitions.\n        \n        Args:\n            table_name: Table name\n            partition_name: Partition to split\n            split_definitions: New partition definitions\n        \n        Returns:\n            List of new partitions\n        \"\"\"\n        with self._lock:\n            scheme = self.schemes.get(table_name.upper())\n            if not scheme:\n                raise ValueError(f\"Table '{table_name}' not found\")\n            \n            old_part = scheme.partitions.get(partition_name.upper())\n            if not old_part:\n                raise ValueError(f\"Partition '{partition_name}' not found\")\n            \n            # Redistribute data\n            new_partitions = []\n            for part_def in split_definitions:\n                new_part = self._create_partition_from_def(\n                    scheme.partition_type, part_def\n                )\n                scheme.partitions[new_part.name.upper()] = new_part\n                new_partitions.append(new_part)\n                \n                # Move data (simplified - would need actual implementation)\n                for row in old_part.data:\n                    key_value = self._get_key_value(row, scheme.partition_key)\n                    if new_part.contains(key_value):\n                        new_part.data.append(row)\n                        new_part.row_count += 1\n            \n            # Remove old partition\n            del scheme.partitions[partition_name.upper()]\n            \n            self.stats['partitions_split'] += 1\n            return new_partitions\n    \n    def merge_partitions(self, \n                          table_name: str,\n                          partition_names: List[str],\n                          new_partition_name: str) -> Partition:\n        \"\"\"\n        Merge multiple partitions into one.\n        \n        Args:\n            table_name: Table name\n            partition_names: Partitions to merge\n            new_partition_name: Name for merged partition\n        \n        Returns:\n            New merged partition\n        \"\"\"\n        with self._lock:\n            scheme = self.schemes.get(table_name.upper())\n            if not scheme:\n                raise ValueError(f\"Table '{table_name}' not found\")\n            \n            # Combine data\n            merged_data = []\n            total_rows = 0\n            \n            for part_name in partition_names:\n                part = scheme.partitions.get(part_name.upper())\n                if part:\n                    merged_data.extend(part.data)\n                    total_rows += part.row_count\n                    del scheme.partitions[part_name.upper()]\n            \n            # Create merged partition\n            # For RANGE: combine ranges\n            # For LIST: combine lists\n            # For HASH: keep as is\n            new_part = Partition(\n                name=new_partition_name,\n                values=None\n            )\n            new_part.data = merged_data\n            new_part.row_count = total_rows\n            \n            scheme.partitions[new_partition_name.upper()] = new_part\n            self.stats['partitions_merged'] += 1\n            \n            return new_part\n    \n    def get_partition_for_insert(self, \n                                  table_name: str, \n                                  row: Dict[str, Any]) -> Optional[Partition]:\n        \"\"\"Determine which partition a row belongs to.\"\"\"\n        scheme = self.schemes.get(table_name.upper())\n        if not scheme:\n            return None\n        \n        key_value = self._get_key_value(row, scheme.partition_key)\n        return scheme.get_partition_for_value(key_value)\n    \n    def get_partitions_for_query(self,\n                                  table_name: str,\n                                  where_conditions: List[Dict]) -> List[Partition]:\n        \"\"\"\n        Get partitions relevant to a query.\n        Used for partition pruning.\n        \"\"\"\n        scheme = self.schemes.get(table_name.upper())\n        if not scheme:\n            return []\n        \n        # If no conditions, scan all partitions\n        if not where_conditions:\n            return list(scheme.partitions.values())\n        \n        relevant = set()\n        \n        for condition in where_conditions:\n            col = condition.get('column')\n            op = condition.get('operator', '=')\n            value = condition.get('value')\n            \n            # Check if condition is on partition key\n            if col == scheme.partition_key or \\\n               (isinstance(scheme.partition_key, list) and col in scheme.partition_key):\n                \n                partitions = scheme.get_relevant_partitions(op, value)\n                relevant.update(p.name for p in partitions)\n                self.stats['pruning_hits'] += 1\n        \n        if relevant:\n            return [scheme.partitions[name] for name in relevant \n                    if name in scheme.partitions]\n        \n        # If partition key not in conditions, scan all\n        return list(scheme.partitions.values())\n    \n    def _get_key_value(self, row: Dict, key: Union[str, List[str]]) -> Any:\n        \"\"\"Extract partition key value from row.\"\"\"\n        if isinstance(key, str):\n            return row.get(key)\n        else:\n            # Composite key\n            return tuple(row.get(k) for k in key)\n    \n    def get_partition_info(self, table_name: str) -> Optional[Dict]:\n        \"\"\"Get partition information for a table.\"\"\"\n        scheme = self.schemes.get(table_name.upper())\n        if not scheme:\n            return None\n        \n        return {\n            'table': scheme.table_name,\n            'type': scheme.partition_type.value,\n            'key': scheme.partition_key,\n            'partition_count': len(scheme.partitions),\n            'partitions': [\n                {\n                    'name': p.name,\n                    'row_count': p.row_count,\n                    'created': p.created_at\n                }\n                for p in scheme.partitions.values()\n            ]\n        }\n    \n    def list_partitioned_tables(self) -> List[str]:\n        \"\"\"List all partitioned tables.\"\"\"\n        return list(self.schemes.keys())\n    \n    def get_stats(self) -> Dict[str, Any]:\n        \"\"\"Get partition manager statistics.\"\"\"\n        return {\n            **self.stats,\n            'partitioned_tables': len(self.schemes),\n            'total_partitions': sum(\n                len(s.partitions) for s in self.schemes.values()\n            )\n        }\n    \n    def _default_storage(self, operation: str, data: Any = None) -> Any:\n        \"\"\"Default storage function.\"\"\"\n        return None\n\n\nclass PartitionPruner:\n    \"\"\"\n    Query optimizer component for partition pruning.\n    \n    Eliminates partitions that cannot contain relevant data\n    based on query predicates.\n    \"\"\"\n    \n    def __init__(self, partition_manager: PartitionManager):\n        self.pm = partition_manager\n    \n    def prune_partitions(self, \n                         table_name: str, \n                         query_plan: Dict) -> Dict:\n        \"\"\"\n        Apply partition pruning to query plan.\n        \n        Args:\n            table_name: Table being queried\n            query_plan: Current query plan\n        \n        Returns:\n            Modified query plan with partition pruning\n        \"\"\"\n        scheme = self.pm.schemes.get(table_name.upper())\n        if not scheme:\n            return query_plan\n        \n        # Extract predicates from query plan\n        predicates = self._extract_predicates(query_plan)\n        \n        # Get relevant partitions\n        relevant = self.pm.get_partitions_for_query(table_name, predicates)\n        \n        # Update query plan\n        pruned_plan = query_plan.copy()\n        pruned_plan['partitions'] = [p.name for p in relevant]\n        pruned_plan['partition_pruning'] = {\n            'enabled': True,\n            'total_partitions': len(scheme.partitions),\n            'selected_partitions': len(relevant),\n            'pruned_partitions': len(scheme.partitions) - len(relevant)\n        }\n        \n        return pruned_plan\n    \n    def _extract_predicates(self, query_plan: Dict) -> List[Dict]:\n        \"\"\"Extract WHERE predicates from query plan.\"\"\"\n        predicates = []\n        \n        # Look for filter conditions in plan\n        if 'filter' in query_plan:\n            filter_cond = query_plan['filter']\n            # Parse simple conditions\n            match = re.match(r'(\\w+)\\s*([=<>!]+)\\s*(.+)', filter_cond)\n            if match:\n                predicates.append({\n                    'column': match.group(1),\n                    'operator': match.group(2),\n                    'value': match.group(3).strip().strip(\"'\")\n                })\n        \n        return predicates\n\n\ndef parse_partition_clause(sql: str) -> Dict[str, Any]:\n    \"\"\"\n    Parse PARTITION BY clause from CREATE TABLE.\n    \n    Returns:\n        Dictionary with partition type, key, and definitions\n    \"\"\"\n    # Match PARTITION BY clause\n    pattern = re.compile(\n        r'PARTITION\\s+BY\\s+(RANGE|LIST|HASH)(?:\\s+COLUMNS)?\\s*\\(\\s*([^)]+)\\s*\\)'\n        r'\\s*\\(([^)]+)\\)',\n        re.IGNORECASE | re.DOTALL\n    )\n    \n    match = pattern.search(sql)\n    if not match:\n        return None\n    \n    partition_type = match.group(1).upper()\n    partition_key = [k.strip() for k in match.group(2).split(',')]\n    partition_defs_str = match.group(3)\n    \n    # Parse partition definitions\n    partitions = []\n    \n    if partition_type == 'RANGE':\n        # Parse: PARTITION p1 VALUES LESS THAN ('2024-01-01')\n        part_pattern = re.compile(\n            r'PARTITION\\s+(\\w+)\\s+VALUES\\s+LESS\\s+THAN\\s*\\(([^)]+)\\)',\n            re.IGNORECASE\n        )\n        for part_match in part_pattern.finditer(partition_defs_str):\n            partitions.append({\n                'name': part_match.group(1),\n                'less_than': part_match.group(2).strip().strip(\"'\")\n            })\n    \n    elif partition_type == 'LIST':\n        # Parse: PARTITION p1 VALUES IN (1, 2, 3)\n        part_pattern = re.compile(\n            r'PARTITION\\s+(\\w+)\\s+VALUES\\s+IN\\s*\\(([^)]+)\\)',\n            re.IGNORECASE\n        )\n        for part_match in part_pattern.finditer(partition_defs_str):\n            values = [v.strip().strip(\"'\") for v in part_match.group(2).split(',')]\n            partitions.append({\n                'name': part_match.group(1),\n                'values_list': values\n            })\n    \n    elif partition_type == 'HASH':\n        # Parse: PARTITIONS 4 or individual partitions\n        parts_match = re.search(r'PARTITIONS\\s+(\\d+)', partition_defs_str, re.IGNORECASE)\n        if parts_match:\n            num_partitions = int(parts_match.group(1))\n            for i in range(num_partitions):\n                partitions.append({\n                    'name': f'p{i}',\n                    'modulus': num_partitions,\n                    'remainder': i\n                })\n    \n    return {\n        'type': partition_type,\n        'key': partition_key[0] if len(partition_key) == 1 else partition_key,\n        'partitions': partitions\n    }\n\n\n# Example usage\nif __name__ == '__main__':\n    pm = PartitionManager()\n    \n    # Create range-partitioned table\n    scheme = pm.create_partitioned_table(\n        table_name='sales',\n        partition_type='RANGE',\n        partition_key='sale_date',\n        partition_definitions=[\n            {'name': 'p2023', 'less_than': '2024-01-01'},\n            {'name': 'p2024', 'less_than': '2025-01-01'}\n        ]\n    )\n    \n    print(f\"Created partitioned table: {scheme.table_name}\")\n    print(f\"Partitions: {list(scheme.partitions.keys())}\")\n    \n    # Test partition pruning\n    pruner = PartitionPruner(pm)\n    plan = pruner.prune_partitions('sales', {\n        'filter': \"sale_date < '2024-06-01'\"\n    })\n    \n    print(f\"Pruned plan: {plan.get('partition_pruning')}\")\n