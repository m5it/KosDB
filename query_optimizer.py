"""
Query Optimizer with Execution Planning for KosDB

Provides query analysis, cost estimation, execution plan generation,
and optimization strategies for database operations.
"""

import re
import json
import time
from typing import Dict, Any, List, Optional, Tuple, Set, Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from collections import defaultdict


class OperatorType(Enum):
    """Types of query operators."""
    SCAN = auto()           # Full table scan
    INDEX_SCAN = auto()     # Index scan
    SELECT = auto()         # Filter/selection
    PROJECT = auto()        # Column projection
    JOIN = auto()           # Join operation
    AGGREGATE = auto()      # Aggregation (COUNT, SUM, etc.)
    SORT = auto()           # Order by
    LIMIT = auto()          # Limit results
    INSERT = auto()         # Insert operation
    UPDATE = auto()         # Update operation
    DELETE = auto()         # Delete operation


class JoinType(Enum):
    """Types of joins."""
    NESTED_LOOP = auto()
    HASH_JOIN = auto()
    MERGE_JOIN = auto()


@dataclass
class Statistics:
    """Table/column statistics for cost estimation."""
    table_name: str
    row_count: int = 0
    column_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    index_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    def get_column_cardinality(self, column: str) -> int:
        """Get number of distinct values in column."""
        stats = self.column_stats.get(column, {})
        return stats.get('distinct_count', self.row_count)
    
    def get_column_selectivity(self, column: str) -> float:
        """Get selectivity (0-1) of column."""
        distinct = self.get_column_cardinality(column)
        if distinct == 0:
            return 1.0
        return min(1.0, 1.0 / distinct)
    
    def has_index(self, column: str) -> bool:
        """Check if column has index."""
        return column in self.index_stats


@dataclass
class Operator:
    """Represents an operation in execution plan."""
    op_type: OperatorType
    table: Optional[str] = None
    columns: Optional[List[str]] = None
    condition: Optional[Dict[str, Any]] = None
    estimated_rows: int = 0
    estimated_cost: float = 0.0
    children: List['Operator'] = field(default_factory=list)
    
    # Join specific
    join_type: Optional[JoinType] = None
    join_condition: Optional[Dict[str, Any]] = None
    left_table: Optional[str] = None
    right_table: Optional[str] = None
    
    # Index specific
    index_name: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        result = {
            'type': self.op_type.name,
            'estimated_rows': self.estimated_rows,
            'estimated_cost': round(self.estimated_cost, 4),
        }
        
        if self.table:
            result['table'] = self.table
        if self.columns:
            result['columns'] = self.columns
        if self.condition:
            result['condition'] = self.condition
        if self.join_type:
            result['join_type'] = self.join_type.name
        if self.index_name:
            result['index'] = self.index_name
        
        if self.children:
            result['children'] = [c.to_dict() for c in self.children]
        
        return result


@dataclass
class ExecutionPlan:
    """Complete execution plan for a query."""
    root: Operator
    total_cost: float
    estimated_rows: int
    statistics: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'plan': self.root.to_dict(),
            'total_cost': round(self.total_cost, 4),
            'estimated_rows': self.estimated_rows,
            'statistics': self.statistics
        }
    
    def explain(self) -> str:
        """Generate human-readable explanation."""
        lines = ["Execution Plan:", "=" * 50]
        self._explain_operator(self.root, 0, lines)
        lines.append(f"\nTotal Cost: {self.total_cost:.4f}")
        lines.append(f"Estimated Rows: {self.estimated_rows}")
        return "\n".join(lines)
    
    def _explain_operator(self, op: Operator, depth: int, lines: List[str]):
        """Recursively explain operators."""
        indent = "  " * depth
        cost_info = f" (cost={op.estimated_cost:.2f}, rows={op.estimated_rows})"
        
        if op.op_type == OperatorType.SCAN:
            lines.append(f"{indent}→ Seq Scan on {op.table}{cost_info}")
        elif op.op_type == OperatorType.INDEX_SCAN:
            lines.append(f"{indent}→ Index Scan using {op.index_name} on {op.table}{cost_info}")
        elif op.op_type == OperatorType.SELECT:
            lines.append(f"{indent}→ Filter: {op.condition}{cost_info}")
        elif op.op_type == OperatorType.PROJECT:
            cols = ", ".join(op.columns) if op.columns else "*"
            lines.append(f"{indent}→ Project: {cols}{cost_info}")
        elif op.op_type == OperatorType.JOIN:
            join = f"{op.join_type.name} Join" if op.join_type else "Join"
            lines.append(f"{indent}→ {join}{cost_info}")
        elif op.op_type == OperatorType.SORT:
            lines.append(f"{indent}→ Sort{cost_info}")
        elif op.op_type == OperatorType.LIMIT:
            lines.append(f"{indent}→ Limit{cost_info}")
        elif op.op_type == OperatorType.AGGREGATE:
            lines.append(f"{indent}→ Aggregate{cost_info}")
        
        for child in op.children:
            self._explain_operator(child, depth + 1, lines)


class CostModel:
    """
    Cost model for query operations.
    Assigns costs based on I/O and CPU estimates.
    """
    
    # Base costs
    SEQ_PAGE_COST = 1.0           # Cost to read one page sequentially
    RANDOM_PAGE_COST = 4.0        # Cost to read one page randomly (index)
    CPU_TUPLE_COST = 0.01         # Cost to process one tuple
    CPU_INDEX_TUPLE_COST = 0.005  # Cost to process index tuple
    CPU_OPERATOR_COST = 0.0025    # Cost to execute one operator
    
    def __init__(self):
        self.statistics: Dict[str, Statistics] = {}
    
    def add_statistics(self, table: str, stats: Statistics):
        """Add statistics for a table."""
        self.statistics[table] = stats
    
    def estimate_scan_cost(self, table: str, 
                          use_index: bool = False,
                          index_column: Optional[str] = None) -> Tuple[float, int]:
        """
        Estimate cost of table scan.
        
        Returns: (cost, estimated_rows)
        """
        stats = self.statistics.get(table)
        if not stats:
            return (self.SEQ_PAGE_COST * 10, 1000)  # Default estimate
        
        rows = stats.row_count
        
        if use_index and index_column and stats.has_index(index_column):
            # Index scan - fewer pages, more random access
            selectivity = stats.get_column_selectivity(index_column)
            estimated_rows = max(1, int(rows * selectivity))
            
            # Cost: random page reads + index processing
            index_pages = max(1, estimated_rows / 100)  # Assume 100 rows per page
            cost = (index_pages * self.RANDOM_PAGE_COST + 
                   estimated_rows * self.CPU_INDEX_TUPLE_COST +
                   estimated_rows * self.CPU_TUPLE_COST)
        else:
            # Sequential scan
            pages = max(1, rows / 100)  # Assume 100 rows per page
            cost = pages * self.SEQ_PAGE_COST + rows * self.CPU_TUPLE_COST
            estimated_rows = rows
        
        return (cost, estimated_rows)
    
    def estimate_filter_cost(self, input_rows: int, 
                            condition: Dict[str, Any]) -> Tuple[float, int]:
        """Estimate cost of filter operation."""
        # Simple selectivity estimate
        selectivity = 0.1  # Default: 10% pass through
        
        if 'column' in condition and 'op' in condition:
            col = condition['column']
            op = condition['op']
            
            if op == '=':
                selectivity = 0.01  # Equality is very selective
            elif op in ('>', '<', '>=', '<='):
                selectivity = 0.3   # Range is moderately selective
            elif op == 'LIKE':
                selectivity = 0.2   # Pattern match
        
        estimated_rows = max(1, int(input_rows * selectivity))
        cost = input_rows * self.CPU_OPERATOR_COST
        
        return (cost, estimated_rows)
    
    def estimate_join_cost(self, left_rows: int, right_rows: int,
                          join_type: JoinType) -> Tuple[float, int]:
        """Estimate cost of join operation."""
        if join_type == JoinType.NESTED_LOOP:
            cost = left_rows * right_rows * self.CPU_OPERATOR_COST
            rows = left_rows * right_rows
        elif join_type == JoinType.HASH_JOIN:
            # Build hash table + probe
            cost = (left_rows + right_rows) * self.CPU_OPERATOR_COST * 2
            rows = min(left_rows, right_rows)  # Assume some reduction
        elif join_type == JoinType.MERGE_JOIN:
            # Sort + merge
            cost = (left_rows * 0.1 + right_rows * 0.1 + 
                   (left_rows + right_rows) * self.CPU_OPERATOR_COST)
            rows = min(left_rows, right_rows)
        else:
            cost = left_rows * right_rows * self.CPU_OPERATOR_COST
            rows = left_rows * right_rows
        
        return (cost, max(1, rows))
    
    def estimate_sort_cost(self, input_rows: int) -> Tuple[float, int]:
        """Estimate cost of sort operation."""
        # O(n log n) complexity
        import math
        cost = input_rows * math.log2(max(2, input_rows)) * self.CPU_OPERATOR_COST
        return (cost, input_rows)
    
    def estimate_aggregate_cost(self, input_rows: int, 
                                 group_by: Optional[List[str]] = None) -> Tuple[float, int]:
        """Estimate cost of aggregation."""
        cost = input_rows * self.CPU_OPERATOR_COST
        
        if group_by:
            # Assume reduction by grouping
            output_rows = max(1, input_rows // 10)
        else:
            # Scalar aggregate - single result
            output_rows = 1
        
        return (cost, output_rows)


class QueryParser:
    """
    Parses SQL-like queries into structured representation.
    """
    
    def __init__(self):
        self.parsed: Optional[Dict[str, Any]] = None
    
    def parse(self, query: str) -> Dict[str, Any]:
        """Parse query string into structured form."""
        query = query.strip()
        upper = query.upper()
        
        if upper.startswith('SELECT'):
            return self._parse_select(query)
        elif upper.startswith('INSERT'):
            return self._parse_insert(query)
        elif upper.startswith('UPDATE'):
            return self._parse_update(query)
        elif upper.startswith('DELETE'):
            return self._parse_delete(query)
        else:
            raise ValueError(f"Unsupported query type: {query[:50]}...")
    
    def _parse_select(self, query: str) -> Dict[str, Any]:
        """Parse SELECT statement."""
        result = {
            'type': 'SELECT',
            'columns': [],
            'table': None,
            'where': None,
            'order_by': None,
            'order_desc': False,
            'limit': None
        }
        
        # Extract columns
        match = re.search(r'SELECT\s+(.+?)\s+FROM', query, re.IGNORECASE)
        if match:
            cols_str = match.group(1).strip()
            if cols_str == '*':
                result['columns'] = ['*']
            else:
                result['columns'] = [c.strip() for c in cols_str.split(',')]
        
        # Extract table
        match = re.search(r'FROM\s+(\w+)', query, re.IGNORECASE)
        if match:
            result['table'] = match.group(1)
        
        # Extract WHERE
        match = re.search(r'WHERE\s+(.+?)(?:ORDER BY|LIMIT|$)', query, re.IGNORECASE)
        if match:
            result['where'] = self._parse_where(match.group(1).strip())
        
        # Extract ORDER BY
        match = re.search(r'ORDER BY\s+(\w+)\s*(ASC|DESC)?', query, re.IGNORECASE)
        if match:
            result['order_by'] = match.group(1)
            result['order_desc'] = match.group(2) and match.group(2).upper() == 'DESC'
        
        # Extract LIMIT
        match = re.search(r'LIMIT\s+(\d+)', query, re.IGNORECASE)
        if match:
            result['limit'] = int(match.group(1))
        
        return result
    
    def _parse_insert(self, query: str) -> Dict[str, Any]:
        """Parse INSERT statement."""
        result = {'type': 'INSERT', 'table': None, 'values': []}
        
        match = re.search(r'INTO\s+(\w+)', query, re.IGNORECASE)
        if match:
            result['table'] = match.group(1)
        
        match = re.search(r'VALUES\s*\(([^)]+)\)', query, re.IGNORECASE)
        if match:
            values_str = match.group(1)
            result['values'] = self._parse_values(values_str)
        
        return result
    
    def _parse_update(self, query: str) -> Dict[str, Any]:
        """Parse UPDATE statement."""
        result = {'type': 'UPDATE', 'table': None, 'set': {}, 'where': None}
        
        match = re.search(r'UPDATE\s+(\w+)', query, re.IGNORECASE)
        if match:
            result['table'] = match.group(1)
        
        match = re.search(r'SET\s+(.+?)(?:WHERE|$)', query, re.IGNORECASE)
        if match:
            result['set'] = self._parse_set_clause(match.group(1).strip())
        
        match = re.search(r'WHERE\s+(.+)$', query, re.IGNORECASE)
        if match:
            result['where'] = self._parse_where(match.group(1).strip())
        
        return result
    
    def _parse_delete(self, query: str) -> Dict[str, Any]:
        """Parse DELETE statement."""
        result = {'type': 'DELETE', 'table': None, 'where': None}
        
        match = re.search(r'FROM\s+(\w+)', query, re.IGNORECASE)
        if match:
            result['table'] = match.group(1)
        
        match = re.search(r'WHERE\s+(.+)$', query, re.IGNORECASE)
        if match:
            result['where'] = self._parse_where(match.group(1).strip())
        
        return result
    
    def _parse_where(self, where_str: str) -> Dict[str, Any]:
        """Parse WHERE clause."""
        # Simple condition parsing
        where_str = where_str.strip()
        
        # Try equality
        match = re.match(r'(\w+)\s*=\s*(.+)', where_str)
        if match:
            return {
                'column': match.group(1),
                'op': '=',
                'value': self._parse_value(match.group(2))
            }
        
        # Try comparison operators
        match = re.match(r'(\w+)\s*(>=?|<=?)\s*(.+)', where_str)
        if match:
            return {
                'column': match.group(1),
                'op': match.group(2),
                'value': self._parse_value(match.group(3))
            }
        
        # Try LIKE
        match = re.match(r'(\w+)\s+LIKE\s+(.+)', where_str, re.IGNORECASE)
        if match:
            return {
                'column': match.group(1),
                'op': 'LIKE',
                'value': self._parse_value(match.group(2))
            }
        
        return {'raw': where_str}
    
    def _parse_values(self, values_str: str) -> List[Any]:
        """Parse VALUES clause."""
        values = []
        for val in values_str.split(','):
            val = val.strip()
            values.append(self._parse_value(val))
        return values
    
    def _parse_value(self, val: str) -> Any:
        """Parse a single value."""
        val = val.strip()
        
        # String literal
        if (val.startswith("'") and val.endswith("'")) or \
           (val.startswith('"') and val.endswith('"')):
            return val[1:-1]
        
        # Number
        try:
            if '.' in val:
                return float(val)
            return int(val)
        except ValueError:
            pass
        
        # Boolean/NULL
        upper = val.upper()
        if upper == 'TRUE':
            return True
        if upper == 'FALSE':
            return False
        if upper == 'NULL':
            return None
        
        return val
    
    def _parse_set_clause(self, set_str: str) -> Dict[str, Any]:
        """Parse SET clause."""
        result = {}
        assignments = set_str.split(',')
        
        for assignment in assignments:
            match = re.match(r'(\w+)\s*=\s*(.+)', assignment.strip())
            if match:
                result[match.group(1)] = self._parse_value(match.group(2))
        
        return result


class QueryOptimizer:
    """
    Main query optimizer class.
    Generates optimal execution plans for queries.
    """
    
    def __init__(self):
        self.cost_model = CostModel()
        self.parser = QueryParser()
        self.plan_cache: Dict[str, ExecutionPlan] = {}
        self.cache_hits = 0
        self.cache_misses = 0
    
    def add_statistics(self, table: str, stats: Statistics):
        """Add table statistics."""
        self.cost_model.add_statistics(table, stats)
    
    def optimize(self, query: str, use_cache: bool = True) -> ExecutionPlan:
        """
        Optimize a query and return execution plan.
        
        Args:
            query: SQL query string
            use_cache: Whether to use plan cache
        
        Returns:
            ExecutionPlan with optimal operations
        """
        # Check cache
        cache_key = self._get_cache_key(query)
        if use_cache and cache_key in self.plan_cache:
            self.cache_hits += 1
            return self.plan_cache[cache_key]
        
        self.cache_misses += 1
        
        # Parse query
        parsed = self.parser.parse(query)
        
        # Generate plan based on query type
        if parsed['type'] == 'SELECT':
            plan = self._optimize_select(parsed)
        elif parsed['type'] == 'INSERT':
            plan = self._optimize_insert(parsed)
        elif parsed['type'] == 'UPDATE':
            plan = self._optimize_update(parsed)
        elif parsed['type'] == 'DELETE':
            plan = self._optimize_delete(parsed)
        else:
            raise ValueError(f"Unsupported query type: {parsed['type']}")
        
        # Cache plan
        if use_cache:
            self.plan_cache[cache_key] = plan
        
        return plan
    
    def _get_cache_key(self, query: str) -> str:
        """Generate cache key for query."""
        # Normalize query for caching
        normalized = ' '.join(query.split()).lower()
        import hashlib
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def _optimize_select(self, parsed: Dict[str, Any]) -> ExecutionPlan:
        """Generate execution plan for SELECT."""
        table = parsed['table']
        where = parsed.get('where')
        order_by = parsed.get('order_by')
        limit = parsed.get('limit')
        columns = parsed.get('columns', ['*'])
        
        # Build plan bottom-up
        
        # 1. Scan operation
        scan_op = self._create_scan_operator(table, where)
        
        # 2. Filter if WHERE clause
        current = scan_op
        if where:
            filter_op = Operator(
                op_type=OperatorType.SELECT,
                table=table,
                condition=where,
                children=[current]
            )
            filter_op.estimated_cost, filter_op.estimated_rows = \
                self.cost_model.estimate_filter_cost(
                    current.estimated_rows, where
                )
            current = filter_op
        
        # 3. Projection
        project_op = Operator(
            op_type=OperatorType.PROJECT,
            table=table,
            columns=columns,
            children=[current]
        )
        project_op.estimated_rows = current.estimated_rows
        project_op.estimated_cost = current.estimated_cost + \
            current.estimated_rows * self.cost_model.CPU_TUPLE_COST * 0.5
        current = project_op
        
        # 4. Sort if ORDER BY
        if order_by:
            sort_op = Operator(
                op_type=OperatorType.SORT,
                table=table,
                children=[current]
            )
            sort_op.estimated_cost, sort_op.estimated_rows = \
                self.cost_model.estimate_sort_cost(current.estimated_rows)
            current = sort_op
        
        # 5. Limit if specified
        if limit is not None:
            limit_op = Operator(
                op_type=OperatorType.LIMIT,
                table=table,
                children=[current]
            )
            limit_op.estimated_rows = min(limit, current.estimated_rows)
            limit_op.estimated_cost = current.estimated_cost + \
                self.cost_model.CPU_OPERATOR_COST
            current = limit_op
        
        # Calculate total cost
        total_cost = self._calculate_total_cost(current)
        
        return ExecutionPlan(
            root=current,
            total_cost=total_cost,
            estimated_rows=current.estimated_rows,
            statistics={
                'table': table,
                'has_where': where is not None,
                'has_order_by': order_by is not None,
                'has_limit': limit is not None
            }
        )
    
    def _create_scan_operator(self, table: str, 
                               where: Optional[Dict[str, Any]]) -> Operator:
        """Create optimal scan operator."""
        stats = self.cost_model.statistics.get(table)
        
        # Check if we can use index
        use_index = False
        index_column = None
        
        if where and 'column' in where and stats:
            col = where['column']
            if stats.has_index(col) and where.get('op') == '=':
                use_index = True
                index_column = col
        
        # Create operator
        scan = Operator(
            op_type=OperatorType.INDEX_SCAN if use_index else OperatorType.SCAN,
            table=table
        )
        
        if use_index:
            scan.index_name = f"idx_{table}_{index_column}"
        
        scan.estimated_cost, scan.estimated_rows = \
            self.cost_model.estimate_scan_cost(table, use_index, index_column)
        
        return scan
    
    def _optimize_insert(self, parsed: Dict[str, Any]) -> ExecutionPlan:
        """Generate execution plan for INSERT."""
        table = parsed['table']
        
        op = Operator(
            op_type=OperatorType.INSERT,
            table=table,
            columns=parsed.get('columns'),
        )
        
        # Estimate cost
        op.estimated_rows = 1
        op.estimated_cost = (self.cost_model.SEQ_PAGE_COST + 
                            self.cost_model.CPU_TUPLE_COST)
        
        return ExecutionPlan(
            root=op,
            total_cost=op.estimated_cost,
            estimated_rows=1,
            statistics={'table': table}
        )
    
    def _optimize_update(self, parsed: Dict[str, Any]) -> ExecutionPlan:
        """Generate execution plan for UPDATE."""
        table = parsed['table']
        where = parsed.get('where')
        
        # Start with scan
        scan = self._create_scan_operator(table, where)
        
        # Filter if WHERE
        current = scan
        if where:
            filter_op = Operator(
                op_type=OperatorType.SELECT,
                table=table,
                condition=where,
                children=[current]
            )
            filter_op.estimated_cost, filter_op.estimated_rows = \
                self.cost_model.estimate_filter_cost(
                    current.estimated_rows, where
                )
            current = filter_op
        
        # Update operation
        update_op = Operator(
            op_type=OperatorType.UPDATE,
            table=table,
            condition=parsed.get('set'),
            children=[current]
        )
        update_op.estimated_rows = current.estimated_rows
        update_op.estimated_cost = (current.estimated_cost + 
                                    current.estimated_rows * 
                                    self.cost_model.CPU_TUPLE_COST * 2)
        
        return ExecutionPlan(
            root=update_op,
            total_cost=update_op.estimated_cost,
            estimated_rows=update_op.estimated_rows,
            statistics={'table': table}
        )
    
    def _optimize_delete(self, parsed: Dict[str, Any]) -> ExecutionPlan:
        """Generate execution plan for DELETE."""
        table = parsed['table']
        where = parsed.get('where')
        
        # Similar to update
        scan = self._create_scan_operator(table, where)
        
        current = scan
        if where:
            filter_op = Operator(
                op_type=OperatorType.SELECT,
                table=table,
                condition=where,
                children=[current]
            )
            filter_op.estimated_cost, filter_op.estimated_rows = \
                self.cost_model.estimate_filter_cost(
                    current.estimated_rows, where
                )
            current = filter_op
        
        delete_op = Operator(
            op_type=OperatorType.DELETE,
            table=table,
            children=[current]
        )
        delete_op.estimated_rows = current.estimated_rows
        delete_op.estimated_cost = (current.estimated_cost + 
                                    current.estimated_rows * 
                                    self.cost_model.CPU_TUPLE_COST)
        
        return ExecutionPlan(
            root=delete_op,
            total_cost=delete_op.estimated_cost,
            estimated_rows=delete_op.estimated_rows,
            statistics={'table': table}
        )
    
    def _calculate_total_cost(self, root: Operator) -> float:
        """Calculate total cost of plan."""
        total = 0.0
        
        def sum_costs(op: Operator):
            nonlocal total
            total += op.estimated_cost
            for child in op.children:
                sum_costs(child)
        
        sum_costs(root)
        return total
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get plan cache statistics."""
        return {
            'cache_size': len(self.plan_cache),
            'hits': self.cache_hits,
            'misses': self.cache_misses,
            'hit_rate': self.cache_hits / (self.cache_hits + self.cache_misses) 
                       if (self.cache_hits + self.cache_misses) > 0 else 0
        }
    
    def clear_cache(self):
        """Clear plan cache."""
        self.plan_cache.clear()
        self.cache_hits = 0
        self.cache_misses = 0


class IndexAdvisor:
    """
    Recommends indexes based on query patterns.
    """
    
    def __init__(self):
        self.query_patterns: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {'count': 0, 'columns': set()}
        )
    
    def record_query(self, query: str, table: str, 
                     where_columns: List[str]):
        """Record query pattern for analysis."""
        key = f"{table}:{','.join(sorted(where_columns))}"
        self.query_patterns[key]['count'] += 1
        self.query_patterns[key]['columns'].update(where_columns)
    
    def recommend_indexes(self, min_frequency: int = 5) -> List[Dict[str, Any]]:
        """
        Recommend indexes based on recorded patterns.
        
        Args:
            min_frequency: Minimum query count to recommend index
        
        Returns:
            List of index recommendations
        """
        recommendations = []
        
        for pattern, data in self.query_patterns.items():
            if data['count'] >= min_frequency:
                table, cols = pattern.split(':', 1)
                columns = cols.split(',') if cols else []
                
                recommendations.append({
                    'table': table,
                    'columns': columns,
                    'query_count': data['count'],
                    'reason': f"Used in {data['count']} queries",
                    'priority': 'HIGH' if data['count'] > 20 else 'MEDIUM'
                })
        
        # Sort by frequency
        recommendations.sort(key=lambda x: x['query_count'], reverse=True)
        
        return recommendations
    
    def get_stats(self) -> Dict[str, Any]:
        """Get advisor statistics."""
        return {
            'patterns_tracked': len(self.query_patterns),
            'recommendations': len(self.recommend_indexes(min_frequency=1))
        }


# Convenience functions
def create_optimizer() -> QueryOptimizer:
    """Create and configure query optimizer."""
    return QueryOptimizer()


def explain_query(query: str, stats: Optional[Dict[str, Statistics]] = None) -> str:
    """
    Explain execution plan for a query.
    
    Args:
        query: SQL query
        stats: Optional table statistics
    
    Returns:
        Human-readable execution plan
    """
    optimizer = create_optimizer()
    
    if stats:
        for table, stat in stats.items():
            optimizer.add_statistics(table, stat)
    
    plan = optimizer.optimize(query)
    return plan.explain()


def analyze_query(query: str, 
                  stats: Optional[Dict[str, Statistics]] = None) -> Dict[str, Any]:
    """
    Analyze query and return detailed statistics.
    
    Args:
        query: SQL query
        stats: Optional table statistics
    
    Returns:
        Dictionary with analysis results
    """
    optimizer = create_optimizer()
    
    if stats:
        for table, stat in stats.items():
            optimizer.add_statistics(table, stat)
    
    plan = optimizer.optimize(query)
    
    return {
        'plan': plan.to_dict(),
        'explanation': plan.explain(),
        'estimated_cost': plan.total_cost,
        'estimated_rows': plan.estimated_rows,
        'cache_stats': optimizer.get_cache_stats()
    }
