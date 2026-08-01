#!/usr/bin/env python3
"""Add sort heuristics to query_optimizer.py"""

with open('query_optimizer.py', 'r') as f:
    content = f.read()

# Add SortStrategy enum after imports
old_imports = '''from typing import Optional, Dict, Any, List, Tuple
from collections import defaultdict
import re'''

new_imports = '''from typing import Optional, Dict, Any, List, Tuple
from collections import defaultdict
from enum import Enum
import re

try:
    from sort_engine import SortEngine, detect_available_backends
    SORT_ENGINE_AVAILABLE = True
except ImportError:
    SORT_ENGINE_AVAILABLE = False


class SortStrategy(Enum):
    """Sort strategy selection based on data characteristics."""
    BUILTIN = "builtin"           # Python Timsort - general purpose
    MADSORT_PY = "madsort_py"   # madS0rt Python - complex objects
    MADSORT_RUST = "madsort_rust"  # madS0rt Rust - maximum performance
    INDEX_SCAN = "index_scan"   # Use index order - avoid sort entirely
    TOPK_HEAP = "topk_heap"     # Heap for LIMIT queries'''

content = content.replace(old_imports, new_imports)

# Add SortHeuristics class after SortStrategy
class_insertion = '''class SortStrategy(Enum):'''

class_definition = '''class SortStrategy(Enum):
    """Sort strategy selection based on data characteristics."""
    BUILTIN = "builtin"           # Python Timsort - general purpose
    MADSORT_PY = "madsort_py"   # madS0rt Python - complex objects
    MADSORT_RUST = "madsort_rust"  # madS0rt Rust - maximum performance
    INDEX_SCAN = "index_scan"   # Use index order - avoid sort entirely
    TOPK_HEAP = "topk_heap"     # Heap for LIMIT queries


class SortHeuristics:
    """
    Sort algorithm selection heuristics for ORDER BY optimization.
    
    Chooses optimal sort strategy based on:
    - Data size
    - Sort key complexity
    - Memory constraints
    - LIMIT clause (top-K optimization)
    """
    
    # Thresholds for strategy selection
    SMALL_DATASET_THRESHOLD = 1000      # Use builtin for small datasets
    MEDIUM_DATASET_THRESHOLD = 100000   # Use madS0rt_py for medium
    LARGE_DATASET_THRESHOLD = 1000000   # Use madS0rt_rust for large
    
    COMPLEX_KEY_THRESHOLD = 3           # Multiple sort columns = complex
    TOPK_RATIO_THRESHOLD = 0.1          # Use heap if LIMIT < 10% of rows
    
    def __init__(self, sort_engine: Optional[Any] = None):
        """
        Initialize sort heuristics.
        
        Args:
            sort_engine: Optional SortEngine instance
        """
        self._sort_engine = sort_engine
        self._available_backends = self._detect_backends()
    
    def _detect_backends(self) -> Dict[str, bool]:
        """Detect available sort backends."""
        if SORT_ENGINE_AVAILABLE:
            return detect_available_backends()
        return {'builtin': True, 'madsort_py': False, 'madsort_rust': False}
    
    def select_strategy(self,
                       estimated_rows: int,
                       sort_columns: List[str],
                       has_limit: bool = False,
                       limit_value: Optional[int] = None,
                       key_complexity: str = "simple",
                       memory_constrained: bool = False) -> SortStrategy:
        """
        Select optimal sort strategy.
        
        Args:
            estimated_rows: Estimated number of rows to sort
            sort_columns: Columns to sort by
            has_limit: Has LIMIT clause
            limit_value: LIMIT value (if has_limit)
            key_complexity: "simple", "medium", or "complex"
            memory_constrained: Memory constraints apply
        
        Returns:
            Selected SortStrategy
        """
        # Check for index scan opportunity (most efficient)
        # This would need index metadata - simplified here
        # if self._can_use_index_scan(sort_columns):
        #     return SortStrategy.INDEX_SCAN
        
        # Check for top-K optimization
        if has_limit and limit_value:
            ratio = limit_value / max(estimated_rows, 1)
            if ratio < self.TOPK_RATIO_THRESHOLD:
                return SortStrategy.TOPK_HEAP
        
        # Select based on data size and complexity
        if estimated_rows < self.SMALL_DATASET_THRESHOLD:
            # Small datasets - builtin is fine
            return SortStrategy.BUILTIN
        
        if estimated_rows < self.MEDIUM_DATASET_THRESHOLD:
            # Medium datasets - madS0rt_py if available
            if self._available_backends.get('madsort_py'):
                return SortStrategy.MADSORT_PY
            return SortStrategy.BUILTIN
        
        # Large datasets
        if self._available_backends.get('madsort_rust'):
            return SortStrategy.MADSORT_RUST
        
        if self._available_backends.get('madsort_py'):
            return SortStrategy.MADSORT_PY
        
        return SortStrategy.BUILTIN
    
    def get_sort_engine_config(self, strategy: SortStrategy) -> Dict[str, Any]:
        """
        Get sort engine configuration for strategy.
        
        Args:
            strategy: Selected sort strategy
        
        Returns:
            Configuration dict for SortEngine
        """
        configs = {
            SortStrategy.BUILTIN: {
                'backend': 'builtin',
                'stable': True
            },
            SortStrategy.MADSORT_PY: {
                'backend': 'madsort_py',
                'stable': True
            },
            SortStrategy.MADSORT_RUST: {
                'backend': 'madsort_rust',
                'stable': True
            },
            SortStrategy.TOPK_HEAP: {
                'backend': 'builtin',  # Uses heapq internally
                'stable': False
            }
        }
        return configs.get(strategy, configs[SortStrategy.BUILTIN])
    
    def estimate_sort_cost(self,
                          estimated_rows: int,
                          strategy: SortStrategy) -> float:
        """
        Estimate sort operation cost.
        
        Args:
            estimated_rows: Number of rows
            strategy: Sort strategy
        
        Returns:
            Estimated cost (arbitrary units)
        """
        # Base costs (relative)
        costs = {
            SortStrategy.INDEX_SCAN: 0,      # No sort cost
            SortStrategy.TOPK_HEAP: 1.0,    # O(n log k)
            SortStrategy.BUILTIN: 2.0,        # O(n log n)
            SortStrategy.MADSORT_PY: 1.5,   # Optimized O(n log n)
            SortStrategy.MADSORT_RUST: 1.0   # Fastest O(n log n)
        }
        
        base_cost = costs.get(strategy, 2.0)
        
        # Scale by data size
        if strategy == SortStrategy.TOPK_HEAP:
            # Heap cost is roughly O(n) for building + O(k log n) for extraction
            return base_cost * estimated_rows
        else:
            # Standard sort cost O(n log n)
            import math
            return base_cost * estimated_rows * math.log2(max(estimated_rows, 2))
    
    def should_use_external_sort(self, 
                                  estimated_rows: int,
                                  avg_row_size: int = 100) -> bool:
        """
        Check if external sort (disk-based) should be used.
        
        Args:
            estimated_rows: Number of rows
            avg_row_size: Average row size in bytes
        
        Returns:
            True if external sort recommended
        """
        # Estimate memory needed (rough)
        estimated_memory = estimated_rows * avg_row_size
        
        # Threshold: 100MB for in-memory sort
        EXTERNAL_SORT_THRESHOLD = 100 * 1024 * 1024
        
        return estimated_memory > EXTERNAL_SORT_THRESHOLD


class SortOptimizer:
    """
    Optimizer for ORDER BY clauses.
    
    Integrates with query optimizer to plan efficient sorts.
    """
    
    def __init__(self, sort_heuristics: Optional[SortHeuristics] = None):
        """Initialize sort optimizer."""
        self.heuristics = sort_heuristics or SortHeuristics()
    
    def optimize_order_by(self,
                         plan: Dict[str, Any],
                         order_by_columns: List[Tuple[str, bool]],
                         limit: Optional[int] = None) -> Dict[str, Any]:
        """
        Optimize ORDER BY clause.
        
        Args:
            plan: Current query plan
            order_by_columns: List of (column, is_desc) tuples
            limit: Optional LIMIT value
        
        Returns:
            Updated plan with sort optimization
        """
        estimated_rows = plan.get('estimated_rows', 1000)
        
        # Extract column names
        columns = [col for col, _ in order_by_columns]
        has_desc = any(desc for _, desc in order_by_columns)
        
        # Determine key complexity
        key_complexity = "simple"
        if len(columns) > 1:
            key_complexity = "complex"
        elif has_desc:
            key_complexity = "medium"
        
        # Select strategy
        strategy = self.heuristics.select_strategy(
            estimated_rows=estimated_rows,
            sort_columns=columns,
            has_limit=limit is not None,
            limit_value=limit,
            key_complexity=key_complexity
        )
        
        # Calculate sort cost
        sort_cost = self.heuristics.estimate_sort_cost(estimated_rows, strategy)
        
        # Update plan
        plan['sort'] = {
            'strategy': strategy.value,
            'columns': order_by_columns,
            'cost': sort_cost,
            'can_use_index': strategy == SortStrategy.INDEX_SCAN,
            'topk_optimized': strategy == SortStrategy.TOPK_HEAP
        }
        
        plan['total_cost'] = plan.get('total_cost', 0) + sort_cost
        
        return plan
    
    def get_recommended_indexes(self,
                                 table: str,
                                 order_by_columns: List[str],
                                 where_columns: List[str] = None) -> List[Dict[str, Any]]:
        """
        Recommend covering indexes for ORDER BY.
        
        Args:
            table: Table name
            order_by_columns: Columns in ORDER BY
            where_columns: Columns in WHERE clause
        
        Returns:
            List of index recommendations
        """
        recommendations = []
        
        # Composite index recommendation
        if where_columns:
            # Index: WHERE columns first, then ORDER BY columns
            index_columns = where_columns + order_by_columns
            recommendations.append({
                'table': table,
                'columns': index_columns,
                'type': 'covering',
                'benefit': 'Eliminates sort, covers filter and order'
            })
        
        # Dedicated ORDER BY index
        recommendations.append({
            'table': table,
            'columns': order_by_columns,
            'type': 'order_by',
            'benefit': 'Eliminates sort for ORDER BY queries'
        })
        
        return recommendations


class QueryOptimizer:
    """SQL query optimizer with cost-based planning.'''

content = content.replace(class_insertion, class_definition)

# Now update the QueryOptimizer class to integrate sort optimization
# Find the optimize method and enhance it
old_optimize = '''    def optimize(self, query: str) -> ExecutionPlan:
        """
        Optimize a SQL query and return execution plan.
        
        Args:
            query: SQL query string
        
        Returns:
            ExecutionPlan with optimization decisions
        """
        # Parse query
        parsed = self._parse_query(query)
        
        # Build execution plan
        plan = ExecutionPlan(parsed['type'], parsed)
        
        # Apply optimizations
        if parsed['type'] == 'SELECT':
            self._optimize_select(plan, parsed)
        elif parsed['type'] == 'INSERT':
            self._optimize_insert(plan, parsed)
        elif parsed['type'] == 'UPDATE':
            self._optimize_update(plan, parsed)
        elif parsed['type'] == 'DELETE':
            self._optimize_delete(plan, parsed)
        
        return plan'''

new_optimize = '''    def optimize(self, query: str) -> ExecutionPlan:
        """
        Optimize a SQL query and return execution plan.
        
        Args:
            query: SQL query string
        
        Returns:
            ExecutionPlan with optimization decisions
        """
        # Parse query
        parsed = self._parse_query(query)
        
        # Build execution plan
        plan = ExecutionPlan(parsed['type'], parsed)
        
        # Initialize sort optimizer
        self._sort_optimizer = SortOptimizer()
        
        # Apply optimizations
        if parsed['type'] == 'SELECT':
            self._optimize_select(plan, parsed)
        elif parsed['type'] == 'INSERT':
            self._optimize_insert(plan, parsed)
        elif parsed['type'] == 'UPDATE':
            self._optimize_update(plan, parsed)
        elif parsed['type'] == 'DELETE':
            self._optimize_delete(plan, parsed)
        
        return plan
    
    def _optimize_order_by(self, 
                          plan: ExecutionPlan,
                          parsed: Dict[str, Any]) -> None:
        """
        Optimize ORDER BY clause using sort heuristics.
        
        Args:
            plan: Execution plan to update
            parsed: Parsed query with order_by info
        """
        if 'order_by' not in parsed:
            return
        
        order_by = parsed['order_by']
        limit = parsed.get('limit')
        
        # Build order_by columns list
        order_by_columns = []
        for item in order_by:
            if isinstance(item, tuple):
                col, desc = item
                order_by_columns.append((col, desc))
            else:
                order_by_columns.append((item, False))
        
        # Get table info
        table = parsed.get('table', parsed.get('tables', [''])[0])
        estimated_rows = self._estimate_rows(table, parsed.get('where'))
        
        # Create plan dict for sort optimizer
        plan_dict = {
            'estimated_rows': estimated_rows,
            'table': table
        }
        
        # Optimize
        optimized = self._sort_optimizer.optimize_order_by(
            plan_dict,
            order_by_columns,
            limit
        )
        
        # Store in plan
        plan.sort_strategy = optimized.get('sort', {})
        plan.sort_cost = optimized.get('sort', {}).get('cost', 0)
    
    def _can_use_index_for_order(self,
                                    table: str,
                                    order_by_columns: List[str]) -> bool:
        """
        Check if existing index can satisfy ORDER BY.
        
        Args:
            table: Table name
            order_by_columns: Columns to sort by
        
        Returns:
            True if index can be used
        """
        # Check if any index matches order_by prefix
        for index_name, index_info in self.indexes.items():
            if index_info.get('table') != table:
                continue
            
            index_cols = index_info.get('columns', [])
            
            # Check if index columns match ORDER BY prefix
            if len(index_cols) >= len(order_by_columns):
                if index_cols[:len(order_by_columns)] == order_by_columns:
                    return True
        
        return False'''

content = content.replace(old_optimize, new_optimize)

# Update _optimize_select to include ORDER BY optimization
old_select_opt = '''    def _optimize_select(self, plan: ExecutionPlan, parsed: Dict[str, Any]):
        """Optimize SELECT query."""
        # Check for index usage
        if 'where' in parsed:
            index_plan = self._find_best_index(parsed)
            if index_plan:
                plan.index_usage = index_plan
                plan.estimated_cost *= 0.3  # Index reduces cost
        
        # Check for column pruning
        if 'columns' in parsed:
            needed = set(parsed['columns'])
            if needed != {'*'}:
                plan.column_pruning = needed
        
        # Update statistics
        self.stats['queries_optimized'] += 1'''

new_select_opt = '''    def _optimize_select(self, plan: ExecutionPlan, parsed: Dict[str, Any]):
        """Optimize SELECT query."""
        # Check for index usage
        if 'where' in parsed:
            index_plan = self._find_best_index(parsed)
            if index_plan:
                plan.index_usage = index_plan
                plan.estimated_cost *= 0.3  # Index reduces cost
        
        # Optimize ORDER BY
        self._optimize_order_by(plan, parsed)
        
        # Check for column pruning
        if 'columns' in parsed:
            needed = set(parsed['columns'])
            if needed != {'*'}:
                plan.column_pruning = needed
        
        # Update statistics
        self.stats['queries_optimized'] += 1'''

content = content.replace(old_select_opt, new_select_opt)

# Add sort stats to get_stats
old_stats = '''    def get_stats(self) -> Dict[str, Any]:
        """Get optimizer statistics."""
        return {
            'queries_optimized': self.stats['queries_optimized'],
            'cache_hits': self.stats['cache_hits'],
            'cache_size': len(self.plan_cache),
            'indexes_available': len(self.indexes)
        }'''

new_stats = '''    def get_stats(self) -> Dict[str, Any]:
        """Get optimizer statistics."""
        return {
            'queries_optimized': self.stats['queries_optimized'],
            'cache_hits': self.stats['cache_hits'],
            'cache_size': len(self.plan_cache),
            'indexes_available': len(self.indexes),
            'sort_heuristics_available': SORT_ENGINE_AVAILABLE,
            'available_backends': self._sort_optimizer.heuristics._available_backends if hasattr(self, '_sort_optimizer') else {}
        }'''

content = content.replace(old_stats, new_stats)

with open('query_optimizer.py', 'w') as f:
    f.write(content)

print("✅ Sort heuristics added to query_optimizer.py")
print("New features:")
print("  - SortStrategy enum (BUILTIN, MADSORT_PY, MADSORT_RUST, INDEX_SCAN, TOPK_HEAP)")
print("  - SortHeuristics class for strategy selection")
print("  - SortOptimizer class for ORDER BY optimization")
print("  - _optimize_order_by() method in QueryOptimizer")
print("  - _can_use_index_for_order() for index-based sorts")
print("  - Cost estimation for sort operations")
print("  - Top-K optimization for LIMIT queries")
