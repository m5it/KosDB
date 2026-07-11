"""
Advanced Index Manager for KosDB v3.4.0

Provides advanced indexing features:
- Composite indexes: Multiple columns with ordering
- Partial indexes: Index subset of rows with WHERE clause
- Expression indexes: Index on computed expressions
- Covering indexes: Include additional columns for index-only scans

Example:
    -- Composite index
    CREATE INDEX idx_name ON users (last_name, first_name);
    
    -- Partial index
    CREATE INDEX idx_active ON users (email) WHERE status = 'active';
    
    -- Expression index
    CREATE INDEX idx_lower_email ON users (LOWER(email));
    
    -- Covering index
    CREATE INDEX idx_covering ON users (id) INCLUDE (name, email);
"""

import re
import hashlib
from typing import Dict, Any, List, Optional, Tuple, Set, Callable, Union
from dataclasses import dataclass, field
from enum import Enum, auto


class IndexType(Enum):
    """Types of advanced indexes."""
    COMPOSITE = "COMPOSITE"      # Multiple columns
    PARTIAL = "PARTIAL"          # With WHERE clause
    EXPRESSION = "EXPRESSION"    # On computed expression
    COVERING = "COVERING"        # Include additional columns
    UNIQUE = "UNIQUE"            # Unique constraint
    FULLTEXT = "FULLTEXT"        # Full-text search


@dataclass
class IndexColumn:
    """Column in an index."""
    name: str
    order: str = "ASC"           # ASC or DESC
    collation: Optional[str] = None
    nulls: str = "FIRST"         # FIRST or LAST
    
    def __hash__(self):
        return hash((self.name, self.order))


@dataclass
class IndexExpression:
    """Expression-based index component."""
    expression: str              # SQL expression
    hash_value: str = field(default="")
    
    def __post_init__(self):
        if not self.hash_value:
            self.hash_value = hashlib.md5(
                self.expression.encode()
            ).hexdigest()[:16]


@dataclass
class AdvancedIndex:
    """Advanced index definition."""
    name: str
    table: str
    index_type: IndexType
    columns: List[IndexColumn]           # Key columns
    expressions: List[IndexExpression] = field(default_factory=list)
    where_clause: Optional[str] = None  # Partial index condition
    include_columns: List[str] = field(default_factory=list)  # Covering columns
    is_unique: bool = False
    is_primary: bool = False
    
    # Statistics
    selectivity: float = 0.0
    index_size: int = 0
    last_analyzed: Optional[float] = None
    
    def matches_query(self, 
                      query_columns: List[str],
                      query_conditions: List[Dict]) -> Tuple[bool, float]:
        """
        Check if index matches query and return match score.
        
        Returns:
            Tuple of (matches, score)
        """
        score = 0.0
        
        # Check if query columns match index columns
        index_col_names = [c.name for c in self.columns]
        
        # Leading column match is most important
        if query_columns and index_col_names:
            if query_columns[0] == index_col_names[0]:
                score += 50  # Leading column match
        
        # Check for partial index condition match
        if self.where_clause:
            if self._condition_matches(query_conditions):
                score += 30
            else:
                # Partial index doesn't apply
                return False, 0.0
        
        # Check for covering index (index-only scan)
        if self._is_covering(query_columns):
            score += 20
        
        # Check expression indexes
        if self.expressions:
            for expr in self.expressions:
                if any(expr.expression.lower() in str(cond).lower() 
                       for cond in query_conditions):
                    score += 25
        
        return score > 0, score
    
    def _condition_matches(self, query_conditions: List[Dict]) -> bool:
        """Check if query conditions match partial index WHERE clause."""
        if not self.where_clause:
            return True
        
        # Simple check - in production would parse and compare
        where_upper = self.where_clause.upper()
        
        for condition in query_conditions:
            cond_str = str(condition).upper()
            if cond_str in where_upper or where_upper in cond_str:
                return True
        
        return False
    
    def _is_covering(self, query_columns: List[str]) -> bool:
        """Check if index covers all query columns (index-only scan possible)."""
        available_cols = set(c.name for c in self.columns)
        available_cols.update(self.include_columns)
        
        return all(col in available_cols for col in query_columns)
    
    def get_column_names(self) -> List[str]:
        """Get list of column names in index."""
        return [c.name for c in self.columns]


class AdvancedIndexManager:
    """
    Manages advanced indexes for KosDB.
    """
    
    def __init__(self):
        self.indexes: Dict[str, AdvancedIndex] = {}
        self._table_indexes: Dict[str, List[str]] = {}
        self._statistics: Dict[str, Dict] = {}
    
    def create_index(self,
                     name: str,
                     table: str,
                     columns: List[Union[str, IndexColumn]],
                     index_type: IndexType = IndexType.COMPOSITE,
                     where_clause: Optional[str] = None,
                     include_columns: Optional[List[str]] = None,
                     expressions: Optional[List[str]] = None,
                     is_unique: bool = False) -> AdvancedIndex:
        """
        Create an advanced index.
        
        Args:
            name: Index name
            table: Table name
            columns: Column definitions
            index_type: Type of index
            where_clause: Partial index condition
            include_columns: Columns to include (covering index)
            expressions: Expression definitions
            is_unique: Whether index enforces uniqueness
        
        Returns:
            Created AdvancedIndex
        """
        # Normalize columns
        index_columns = []
        for col in columns:
            if isinstance(col, str):
                index_columns.append(IndexColumn(name=col))
            else:
                index_columns.append(col)
        
        # Normalize expressions
        index_expressions = []
        if expressions:
            for expr in expressions:
                index_expressions.append(IndexExpression(expression=expr))
        
        # Create index
        index = AdvancedIndex(
            name=name,
            table=table,
            index_type=index_type,
            columns=index_columns,
            expressions=index_expressions,
            where_clause=where_clause,
            include_columns=include_columns or [],
            is_unique=is_unique
        )
        
        # Register
        self.indexes[name.upper()] = index
        if table.upper() not in self._table_indexes:
            self._table_indexes[table.upper()] = []
        self._table_indexes[table.upper()].append(name.upper())
        
        return index
    
    def drop_index(self, name: str) -> bool:
        """Drop an index."""
        name_upper = name.upper()
        if name_upper not in self.indexes:
            return False
        
        index = self.indexes[name_upper]
        
        # Remove from table index list
        table_key = index.table.upper()
        if table_key in self._table_indexes:
            self._table_indexes[table_key].remove(name_upper)
        
        del self.indexes[name_upper]
        return True
    
    def get_indexes_for_table(self, table: str) -> List[AdvancedIndex]:
        """Get all indexes for a table."""
        table_key = table.upper()
        index_names = self._table_indexes.get(table_key, [])
        return [self.indexes[name] for name in index_names if name in self.indexes]
    
    def find_best_index(self,
                       table: str,
                       query_columns: List[str],
                       query_conditions: List[Dict],
                       order_by: Optional[List[Tuple]] = None) -> Optional[AdvancedIndex]:
        """
        Find the best index for a query.
        
        Args:
            table: Table name
            query_columns: Columns in SELECT
            query_conditions: WHERE conditions
            order_by: ORDER BY columns
        
        Returns:
            Best matching index or None
        """
        candidates = self.get_indexes_for_table(table)
        
        if not candidates:
            return None
        
        # Score each candidate
        scored = []
        for idx in candidates:
            matches, score = idx.matches_query(query_columns, query_conditions)
            if matches:
                # Bonus for matching ORDER BY
                if order_by:
                    idx_cols = idx.get_column_names()
                    if all(col[0] in idx_cols for col in order_by):
                        score += 15
                
                scored.append((idx, score))
        
        if not scored:
            return None
        
        # Return highest scoring index
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0]
    
    def get_index_selectivity(self, index_name: str) -> float:
        """Get index selectivity (0-1, higher is more selective)."""
        index = self.indexes.get(index_name.upper())
        if not index:
            return 0.0
        return index.selectivity
    
    def analyze_index(self, index_name: str, table_data: List[Dict]):
        """
        Analyze index statistics from table data.
        
        Args:
            index_name: Index to analyze
            table_data: Sample of table data
        """
        index = self.indexes.get(index_name.upper())
        if not index:
            return
        
        # Calculate selectivity
        if not table_data:
            index.selectivity = 0.0
            return
        
        unique_values = set()
        for row in table_data:
            key = tuple(row.get(col.name) for col in index.columns)
            unique_values.add(key)
        
        index.selectivity = len(unique_values) / len(table_data)
        index.index_size = len(table_data) * len(index.columns) * 8  # Rough estimate
        import time
        index.last_analyzed = time.time()
    
    def get_index_info(self, name: str) -> Optional[Dict]:
        """Get index information."""
        index = self.indexes.get(name.upper())
        if not index:
            return None
        
        return {
            'name': index.name,
            'table': index.table,
            'type': index.index_type.value,
            'columns': [c.name for c in index.columns],
            'expressions': [e.expression for e in index.expressions],
            'where_clause': index.where_clause,
            'include_columns': index.include_columns,
            'is_unique': index.is_unique,
            'selectivity': index.selectivity,
            'size_bytes': index.index_size
        }
    
    def list_indexes(self, table: Optional[str] = None) -> List[Dict]:
        """List indexes, optionally filtered by table."""
        result = []
        for name, index in self.indexes.items():
            if table and index.table.upper() != table.upper():
                continue
            result.append(self.get_index_info(name))
        return result


class IndexAdvisor:
    """
    Recommends indexes based on query patterns.
    """
    
    def __init__(self, index_manager: AdvancedIndexManager):
        self.manager = index_manager
        self.query_patterns: Dict[str, Dict] = {}
    
    def record_query(self, 
                     table: str,
                     columns: List[str],
                     conditions: List[Dict],
                     execution_time: float):
        """Record a query pattern for analysis."""
        key = f"{table}:{','.join(sorted(columns))}"
        
        if key not in self.query_patterns:
            self.query_patterns[key] = {
                'count': 0,
                'columns': columns,\n                'conditions': conditions,\n                'total_time': 0.0\n            }\n        \n        self.query_patterns[key]['count'] += 1\n        self.query_patterns[key]['total_time'] += execution_time
    
    def recommend_indexes(self, min_frequency: int = 5) -> List[Dict]:
        """
        Recommend new indexes based on recorded patterns.
        
        Returns:
            List of index recommendations
        """
n        recommendations = []\n        \n        for pattern, data in self.query_patterns.items():\n            if data['count'] < min_frequency:\n                continue\n            \n            table = pattern.split(':')[0]\n            \n            # Check if suitable index exists\n            existing = self.manager.find_best_index(\n                table, data['columns'], data['conditions']\n            )\n            \n            if existing:\n                continue  # Good index already exists\n            \n            # Recommend composite index on query columns\n            recommendations.append({\n                'table': table,\n                'columns': data['columns'],\n                'reason': f\"Used in {data['count']} queries, avg time {data['total_time']/data['count']:.2f}ms\",\n                'priority': 'HIGH' if data['count'] > 50 else 'MEDIUM',\n                'estimated_benefit': data['total_time'] * 0.3  # Assume 30% improvement\n            })\n        \n        # Sort by estimated benefit\n        recommendations.sort(key=lambda x: x['estimated_benefit'], reverse=True)\n        \n        return recommendations[:10]  # Top 10 recommendations


def parse_create_index(sql: str) -> Dict[str, Any]:
n    \"\"\"\n    Parse CREATE INDEX statement with advanced features.\n    \n    Returns:\n        Dictionary with index components\n    \"\"\"\n    # Match CREATE [UNIQUE] INDEX [name] ON table (columns)\n    # Optional: WHERE condition, INCLUDE columns\n    \n    pattern = re.compile(\n        r'CREATE\\s+(?:(?P<unique>UNIQUE)\\s+)?INDEX\\s+(?P<name>\\w+)\\s*'\n        r'ON\\s+(?P<table>\\w+)\\s*\\((?P<columns>[^)]+)\\)'\n        r'(?:\\s*WHERE\\s*(?P<where>.+?))?'\n        r'(?:\\s*INCLUDE\\s*\\((?P<include>[^)]+)\\))?'\n        r'(?:\\s*;)?\\s*$',\n        re.IGNORECASE | re.DOTALL\n    )\n    \n    match = pattern.match(sql.strip())\n    if not match:\n        raise ValueError(\"Invalid CREATE INDEX syntax\")\n    \n    result = match.groupdict()\n    \n    # Parse columns\n    columns = []\n    for col_def in result['columns'].split(','):\n        col_def = col_def.strip()\n        \n        # Check for expression\n        if '(' in col_def:\n            columns.append({\n                'type': 'expression',\n                'expression': col_def\n            })\n        else:\n            # Regular column with optional ordering\n            parts = col_def.split()\n            col_name = parts[0]\n            order = parts[1].upper() if len(parts) > 1 else 'ASC'\n            columns.append({\n                'type': 'column',\n                'name': col_name,\n                'order': order\n            })\n    \n    result['parsed_columns'] = columns\n    \n    # Parse INCLUDE columns\n    if result.get('include'):\n        result['include_columns'] = [\n            c.strip() for c in result['include'].split(',')\n        ]\n    \n    return result\n\n\nclass IndexCostEstimator:\n \"\"\"\n    Estimate cost of using an index vs sequential scan.\n    \"\"\"\n    \n    def __init__(self):\n        self.page_size = 8192  # bytes\n        self.random_page_cost = 4.0\n        self.seq_page_cost = 1.0\n    \n    def estimate_index_scan_cost(self,\n                                   index: AdvancedIndex,\n                                   selectivity: float,\n                                   table_pages: int) -> float:\n        \"\"\"\n        Estimate cost of index scan.\n        \n        Args:\n            index: Index to use\n            selectivity: Fraction of rows matching (0-1)\n            table_pages: Number of pages in table\n        \n        Returns:\n            Estimated cost\n        \"\"\"\n        # Index pages to read (B-tree height + leaf pages)\n        index_pages = max(1, int(index.index_size / self.page_size / 100))\n        \n        # Table pages to read\n        data_pages = int(table_pages * selectivity)\n        \n        # Cost calculation\n        index_cost = index_pages * self.random_page_cost\n        data_cost = data_pages * self.random_page_cost\n        \n        return index_cost + data_cost\n    \n    def estimate_seq_scan_cost(self, table_pages: int) -> float:\n        \"\"\"Estimate cost of sequential scan.\"\"\"\n        return table_pages * self.seq_page_cost\n    \n    def should_use_index(self,\n                        index: AdvancedIndex,\n                        selectivity: float,\n                        table_pages: int) -> bool:\n        \"\"\"Determine if index scan is better than sequential scan.\"\"\"\n        index_cost = self.estimate_index_scan_cost(index, selectivity, table_pages)\n        seq_cost = self.estimate_seq_scan_cost(table_pages)\n        \n        return index_cost < seq_cost\n\n\n# Example usage\nif __name__ == '__main__':\n    manager = AdvancedIndexManager()\n    \n    # Create composite index\n    idx1 = manager.create_index(\n        name='idx_name',\n        table='users',\n        columns=['last_name', 'first_name'],\n        index_type=IndexType.COMPOSITE\n    )\n    \n    # Create partial index\n    idx2 = manager.create_index(\n        name='idx_active',\n        table='users',\n        columns=['email'],\n        index_type=IndexType.PARTIAL,\n        where_clause=\"status = 'active'\"\n    )\n    \n    # Create covering index\n    idx3 = manager.create_index(\n        name='idx_covering',\n        table='users',\n        columns=['id'],\n        index_type=IndexType.COVERING,\n        include_columns=['name', 'email']\n    )\n    \n    print(f\"Created {len(manager.indexes)} indexes\")\n    \n    # Test index matching\n    best = manager.find_best_index(\n        'users',\n        query_columns=['id', 'name', 'email'],\n        query_conditions=[{'column': 'id', 'op': '=', 'value': 1}]\n    )\n    \n    if best:\n        print(f\"Best index: {best.name} (type: {best.index_type.value})\")\n