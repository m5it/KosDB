"""
Parallel Query Executor for KosDB v3.4.0

Provides parallel query execution for:
- Parallel table scans: Divide table into chunks processed concurrently
- Parallel aggregations: Partial aggregation per worker, then combine
- Parallel joins: Partition and join in parallel
- Worker pool management with load balancing
- Result merging and coordination

Example:
    SELECT /*+ PARALLEL(4) */ * FROM large_table WHERE amount > 1000;
    
    SELECT /*+ PARALLEL(8) */ region, SUM(sales) 
    FROM sales_table 
    GROUP BY region;
"""

import os
import time
import threading
import multiprocessing as mp
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from typing import Dict, Any, List, Optional, Tuple, Callable, Union, Iterator
from dataclasses import dataclass, field
from enum import Enum, auto
import queue
import heapq


class ParallelStrategy(Enum):
    """Strategies for parallel query execution."""
    NONE = "none"              # Sequential execution
    SCAN = "scan"              # Parallel table scan
    AGGREGATION = "aggregation"  # Parallel aggregation with partial results
    HASH_JOIN = "hash_join"    # Parallel hash join
    MERGE_JOIN = "merge_join"  # Parallel merge join
    PARTITION_WISE = "partition_wise"  # Leverage table partitioning


@dataclass
class WorkerTask:
    """Task assigned to a worker."""
    task_id: int
    operation: str           # 'scan', 'aggregate', 'join', etc.
    data_range: Tuple[int, int]  # Row range (start, end) or partition keys
    query_params: Dict[str, Any]
    worker_id: Optional[int] = None
    
    # Results
    result: Any = None
    execution_time: float = 0.0
    rows_processed: int = 0
    error: Optional[str] = None


@dataclass
class ParallelPlan:
    """Execution plan for parallel query."""
    strategy: ParallelStrategy
    degree_of_parallelism: int  # Number of workers
    tasks: List[WorkerTask] = field(default_factory=list)
    
    # Cost estimates
    estimated_rows: int = 0
    estimated_time_sequential: float = 0.0
    estimated_time_parallel: float = 0.0
    speedup_factor: float = 1.0
    
    # Execution stats
    actual_time: float = 0.0
    actual_rows: int = 0


class WorkerPool:
    """
    Manages a pool of workers for parallel execution.
    Supports both thread-based and process-based workers.
    """
    
    def __init__(self, 
                 max_workers: int = None,
                 use_processes: bool = False):
        self.max_workers = max_workers or mp.cpu_count()
        self.use_processes = use_processes
        self.executor = None
        self._lock = threading.Lock()
        self._active_tasks = 0
        self._task_queue = queue.Queue()
        self._results = {}
        self._worker_stats = {i: {'tasks': 0, 'rows': 0} 
                             for i in range(self.max_workers)}
    
    def __enter__(self):
        if self.use_processes:
            self.executor = ProcessPoolExecutor(max_workers=self.max_workers)
        else:
            self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.executor:
            self.executor.shutdown(wait=True)
        return False
    
    def submit(self, 
               func: Callable, 
               task: WorkerTask) -> 'concurrent.futures.Future':
        """Submit a task to the worker pool."""
        with self._lock:
            self._active_tasks += 1
        
        future = self.executor.submit(self._wrap_task, func, task)
        return future
    
    def _wrap_task(self, func: Callable, task: WorkerTask) -> WorkerTask:
        """Wrap task execution with timing and error handling."""
        start_time = time.time()
        task.worker_id = threading.current_thread().ident % self.max_workers
        
        try:
            task.result = func(task)
            task.execution_time = time.time() - start_time
            
            with self._lock:
                self._worker_stats[task.worker_id]['tasks'] += 1
                self._worker_stats[task.worker_id]['rows'] += task.rows_processed
                
        except Exception as e:
            task.error = str(e)
            task.execution_time = time.time() - start_time
        
        with self._lock:
            self._active_tasks -= 1
        
        return task
    
    def get_worker_stats(self) -> Dict[int, Dict]:
        """Get statistics for each worker."""
        with self._lock:
            return self._worker_stats.copy()
    
    def get_load_balance(self) -> float:
        """
        Calculate load balance metric (1.0 = perfect balance).
        """
        with self._lock:
            if not self._worker_stats:
                return 1.0
            
            tasks_per_worker = [s['tasks'] for s in self._worker_stats.values()]
            if not tasks_per_worker or sum(tasks_per_worker) == 0:
                return 1.0
            
            avg_tasks = sum(tasks_per_worker) / len(tasks_per_worker)
            variance = sum((t - avg_tasks) ** 2 for t in tasks_per_worker) / len(tasks_per_worker)
            std_dev = variance ** 0.5
            
            # Coefficient of variation (lower is better)
            if avg_tasks == 0:
                return 1.0
            
            cv = std_dev / avg_tasks
            return max(0, 1 - cv)  # Convert to 0-1 scale where 1 is perfect


class ParallelExecutor:
    """
    Main parallel query executor for KosDB.
    """
    
    def __init__(self, 
                 db_interface: Any,
                 max_workers: int = None,
                 use_processes: bool = False):
        self.db = db_interface
        self.max_workers = max_workers or mp.cpu_count()
        self.use_processes = use_processes
        self.stats = {
            'queries_executed': 0,
            'parallel_queries': 0,
            'total_workers_used': 0,
            'total_time_saved': 0.0
        }
    
    def execute_parallel_scan(self,
                            table: str,
                            columns: List[str],
                            where_clause: Optional[str],
                            dop: int = 4) -> Iterator[Dict]:
        """
        Execute parallel table scan.
        
        Args:
            table: Table name
            columns: Columns to select
            where_clause: WHERE conditions
            dop: Degree of parallelism
        
        Yields:
            Rows from the table
        """
        # Get table size
        total_rows = self._estimate_table_size(table)
        
        if total_rows == 0 or dop <= 1:
            # Fall back to sequential
            yield from self._sequential_scan(table, columns, where_clause)
            return
        
        # Divide table into chunks
        chunk_size = max(1, total_rows // dop)
        tasks = []
        
        for i in range(dop):
            start_row = i * chunk_size
            end_row = start_row + chunk_size if i < dop - 1 else total_rows
            
            task = WorkerTask(
                task_id=i,
                operation='scan',
                data_range=(start_row, end_row),
                query_params={
                    'table': table,
                    'columns': columns,
                    'where': where_clause
                }
            )
            tasks.append(task)
        
        # Execute in parallel
        with WorkerPool(max_workers=dop, use_processes=self.use_processes) as pool:
            futures = [pool.submit(self._scan_chunk, t) for t in tasks]
            
            # Merge results in order (maintain sort order if any)
            result_heap = []
            for future in as_completed(futures):
                task = future.result()
                if task.error:
                    raise RuntimeError(f"Worker {task.task_id} failed: {task.error}")
                
                # Add results to heap for ordered merging
                for row in task.result or []:
                    heapq.heappush(result_heap, (task.task_id, row))
            
            # Yield results in order
            while result_heap:
                _, row = heapq.heappop(result_heap)
                yield row
        
        self.stats['queries_executed'] += 1
        self.stats['parallel_queries'] += 1
    
    def _scan_chunk(self, task: WorkerTask) -> WorkerTask:
        """Scan a chunk of the table."""
        params = task.query_params
        table = params['table']
        columns = params['columns']
        where = params['where']
        start, end = task.data_range
        
        # Execute scan on chunk
        rows = self.db.select_range(table, columns, start, end, where)
        task.result = rows
        task.rows_processed = len(rows)
        
        return task
    
    def execute_parallel_aggregation(self,
                                   table: str,
                                   agg_columns: List[str],
                                   group_by: Optional[List[str]],
                                   where_clause: Optional[str],
                                   dop: int = 4) -> List[Dict]:
        """
        Execute parallel aggregation with partial results.
        
        Args:
            table: Table name
            agg_columns: Aggregation expressions (e.g., 'SUM(amount)')
            group_by: GROUP BY columns
            where_clause: WHERE conditions
            dop: Degree of parallelism
        
        Returns:
            Aggregated results
        """
        # Get table size
        total_rows = self._estimate_table_size(table)
        
        if total_rows == 0 or dop <= 1:
            return self._sequential_aggregation(
                table, agg_columns, group_by, where_clause
            )
        
        # Divide into chunks
        chunk_size = max(1, total_rows // dop)
        tasks = []
        
        for i in range(dop):
            start_row = i * chunk_size
            end_row = start_row + chunk_size if i < dop - 1 else total_rows
            
            task = WorkerTask(
                task_id=i,
                operation='aggregate',
                data_range=(start_row, end_row),
                query_params={
                    'table': table,
                    'agg_columns': agg_columns,
                    'group_by': group_by,
                    'where': where_clause
                }
            )
            tasks.append(task)
        
        # Execute partial aggregations in parallel
        partial_results = []
        
        with WorkerPool(max_workers=dop, use_processes=self.use_processes) as pool:
            futures = [pool.submit(self._partial_aggregate, t) for t in tasks]
            
            for future in as_completed(futures):
                task = future.result()
                if task.error:
                    raise RuntimeError(f"Worker failed: {task.error}")
                partial_results.append(task.result)
        
        # Merge partial results
        final_result = self._merge_aggregations(
            partial_results, agg_columns, group_by
        )
        
        self.stats['queries_executed'] += 1
        self.stats['parallel_queries'] += 1
        
        return final_result
    
    def _partial_aggregate(self, task: WorkerTask) -> WorkerTask:
        """Compute partial aggregation for a chunk."""
        params = task.query_params
        table = params['table']
        agg_cols = params['agg_columns']
        group_by = params['group_by']
        where = params['where']
        start, end = task.data_range
        
        # Get data for chunk
        rows = self.db.select_range(table, ['*'], start, end, where)
        
        # Compute partial aggregates
        partial = {}
        
        for row in rows:
            # Build group key
            if group_by:
                key = tuple(row.get(col) for col in group_by)
            else:
                key = '_total_'
            
            if key not in partial:
                partial[key] = {'_count_': 0}
                for col in group_by or []:
                    partial[key][col] = row.get(col)
            
            partial[key]['_count_'] += 1
            
            # Apply aggregation functions
            for agg_col in agg_cols:
                agg_type, col_name = self._parse_aggregation(agg_col)
                
                if agg_type == 'SUM':
                    val = row.get(col_name, 0)
                    partial[key][agg_col] = partial[key].get(agg_col, 0) + val
                elif agg_type == 'COUNT':
                    partial[key][agg_col] = partial[key].get(agg_col, 0) + 1
                elif agg_type == 'MIN':
                    val = row.get(col_name)
                    current = partial[key].get(agg_col, float('inf'))
                    partial[key][agg_col] = min(current, val) if val is not None else current
                elif agg_type == 'MAX':
                    val = row.get(col_name)
                    current = partial[key].get(agg_col, float('-inf'))
                    partial[key][agg_col] = max(current, val) if val is not None else current
        
        task.result = partial
        task.rows_processed = len(rows)
        
        return task
    
    def _merge_aggregations(self,
                          partial_results: List[Dict],
                          agg_columns: List[str],
                          group_by: Optional[List[str]]) -> List[Dict]:
        """Merge partial aggregation results."""
        merged = {}
        
        for partial in partial_results:
            for key, values in partial.items():
                if key not in merged:
                    merged[key] = {}
                    if group_by:
                        for col in group_by:
                            merged[key][col] = values.get(col)
                
                # Merge aggregation values
                for agg_col in agg_columns:
                    agg_type, col_name = self._parse_aggregation(agg_col)
                    
                    if agg_type in ('SUM', 'COUNT'):
                        merged[key][agg_col] = merged[key].get(agg_col, 0) + values.get(agg_col, 0)
                    elif agg_type == 'MIN':
                        current = merged[key].get(agg_col, float('inf'))
                        new_val = values.get(agg_col, float('inf'))
                        merged[key][agg_col] = min(current, new_val)
                    elif agg_type == 'MAX':
                        current = merged[key].get(agg_col, float('-inf'))
                        new_val = values.get(agg_col, float('-inf'))
                        merged[key][agg_col] = max(current, new_val)
        
        # Convert to list format
        result = []
        for key, values in merged.items():
            row = {}
            if group_by:
                for col in group_by:
                    row[col] = values.get(col)
            for agg_col in agg_columns:
                row[agg_col] = values.get(agg_col)
            result.append(row)
        
        return result
    
    def _parse_aggregation(self, agg_expr: str) -> Tuple[str, str]:
        """Parse aggregation expression like 'SUM(amount)'."""
        agg_expr = agg_expr.strip().upper()
        
        for agg_type in ['SUM', 'COUNT', 'AVG', 'MIN', 'MAX']:
            if agg_expr.startswith(agg_type + '('):
                col = agg_expr[len(agg_type)+1:-1].strip()
                return agg_type, col
        
        return 'SUM', agg_expr  # Default
    
    def execute_parallel_join(self,
                           left_table: str,
                           right_table: str,
                           join_type: str,
                           join_condition: str,
                           dop: int = 4) -> Iterator[Dict]:
        """
        Execute parallel hash join.
        
        Args:
            left_table: Left table name
            right_table: Right table name
            join_type: INNER, LEFT, RIGHT, FULL
            join_condition: Join condition (e.g., 't1.id = t2.id')
            dop: Degree of parallelism
        
        Yields:
            Joined rows
        """
        # Build hash table for smaller relation
        left_size = self._estimate_table_size(left_table)
        right_size = self._estimate_table_size(right_table)
        
        # Choose build side (smaller table)
        if left_size <= right_size:
            build_table, probe_table = left_table, right_table
        else:
            build_table, probe_table = right_table, left_table
        
        # Build hash table in parallel
        hash_table = self._build_hash_table(build_table, join_condition, dop)
        
        # Probe in parallel
        yield from self._probe_hash_table(
            probe_table, hash_table, join_condition, join_type, dop
        )
        
        self.stats['queries_executed'] += 1
        self.stats['parallel_queries'] += 1
    
    def _build_hash_table(self,
                         table: str,
                         join_condition: str,
                         dop: int) -> Dict:
        """Build hash table from build relation."""
        # Parse join keys
        left_key, right_key = self._parse_join_condition(join_condition)
        
        # Scan and build hash table
        hash_table = {}
        
        for row in self._sequential_scan(table, ['*'], None):
            key = row.get(left_key if table in join_condition else right_key)
            if key not in hash_table:
                hash_table[key] = []
            hash_table[key].append(row)
        
        return hash_table
    
    def _probe_hash_table(self,
                         table: str,
                         hash_table: Dict,
                         join_condition: str,
                         join_type: str,
                         dop: int) -> Iterator[Dict]:
        """Probe hash table in parallel."""
        # For simplicity, sequential probe
        # Full implementation would partition probe side
        
        left_key, right_key = self._parse_join_condition(join_condition)
        
        for row in self._sequential_scan(table, ['*'], None):
            key = row.get(right_key if table in join_condition else left_key)
            matches = hash_table.get(key, [])
            
            if matches:
                for match in matches:
                    joined = {**match, **row}
                    yield joined
            elif join_type in ('LEFT', 'FULL') and table == 'right':
                # Preserve left row with NULL right
                yield match
    
    def _parse_join_condition(self, condition: str) -> Tuple[str, str]:
        """Parse join condition to extract keys."""
        # Simple parser for 't1.col = t2.col'
        parts = condition.split('=')
        left = parts[0].strip().split('.')[-1]
        right = parts[1].strip().split('.')[-1]
        return left, right
    
    def should_parallelize(self,
                          table: str,
                          operation: str,
                          estimated_rows: int) -> Tuple[bool, int]:
        """
        Determine if query should be parallelized.
        
        Returns:
            Tuple of (should_parallelize, recommended_dop)
        """
        # Minimum threshold for parallelization
        MIN_ROWS_FOR_PARALLEL = 10000
        
        if estimated_rows < MIN_ROWS_FOR_PARALLEL:
            return False, 1
        
        # Calculate recommended DOP based on table size
        if estimated_rows < 100000:
            recommended_dop = 2
        elif estimated_rows < 1000000:
            recommended_dop = 4
        elif estimated_rows < 10000000:
            recommended_dop = 8
        else:
            recommended_dop = min(16, self.max_workers)
        
        # Consider operation type
        if operation in ('aggregation', 'sort'):
            # These benefit more from parallelism
            recommended_dop = min(recommended_dop * 2, self.max_workers)
        
        return True, recommended_dop
    
    def _estimate_table_size(self, table: str) -> int:
        """Estimate number of rows in table."""
        # Would query actual statistics
        return self.db.get_table_row_count(table) if hasattr(self.db, 'get_table_row_count') else 1000
    
    def _sequential_scan(self, table: str, columns: List[str], where: Optional[str]):
        """Fallback sequential scan."""
        return self.db.select(table, columns, where)
    
    def _sequential_aggregation(self, table: str, agg_cols: List[str], 
                               group_by: Optional[List[str]], where: Optional[str]):
        """Fallback sequential aggregation."""
        # Would implement actual aggregation
        return []
    
    def get_stats(self) -> Dict[str, Any]:
        """Get execution statistics."""
        return {
            **self.stats,
            'max_workers': self.max_workers,
            'use_processes': self.use_processes
        }


class ParallelQueryOptimizer:
    """
    Optimizer extension for parallel query planning.
    """
    
    def __init__(self, executor: ParallelExecutor):
        self.executor = executor
    
    def optimize(self, query: Dict[str, Any]) -> ParallelPlan:
        """
        Create parallel execution plan for query.
        
        Args:
            query: Parsed query structure
        
        Returns:
            ParallelPlan with execution strategy
        """
        table = query.get('table')
        operation = query.get('operation', 'scan')
        estimated_rows = query.get('estimated_rows', 0)
        
        # Determine if parallelization is beneficial
        should_parallel, dop = self.executor.should_parallelize(
            table, operation, estimated_rows
        )
        
        if not should_parallel:
            return ParallelPlan(
                strategy=ParallelStrategy.NONE,
                degree_of_parallelism=1
            )
        
        # Choose strategy
        if operation == 'aggregation':
            strategy = ParallelStrategy.AGGREGATION
        elif operation == 'join':
            strategy = ParallelStrategy.HASH_JOIN
        else:
            strategy = ParallelStrategy.SCAN
        
        # Estimate costs
        seq_time = self._estimate_sequential_time(estimated_rows, operation)
        par_time = seq_time / (dop * 0.8)  # Assume 80% efficiency
        
        return ParallelPlan(
            strategy=strategy,
            degree_of_parallelism=dop,
            estimated_rows=estimated_rows,
            estimated_time_sequential=seq_time,
            estimated_time_parallel=par_time,
            speedup_factor=seq_time / par_time if par_time > 0 else 1.0
        )
    
    def _estimate_sequential_time(self, rows: int, operation: str) -> float:
        """Estimate sequential execution time in seconds."""
        # Rough estimates
        base_time = 0.001  # 1ms overhead
        
        if operation == 'scan':
            per_row = 0.00001  # 10 microseconds per row
        elif operation == 'aggregation':
            per_row = 0.00005  # 50 microseconds per row
        elif operation == 'join':
            per_row = 0.0001   # 100 microseconds per row
        else:
            per_row = 0.00001
        
        return base_time + rows * per_row


# Example usage
if __name__ == '__main__':
    class MockDB:
        def select(self, table, columns, where):
            return [{'id': i, 'value': i*10} for i in range(100)]
        
        def select_range(self, table, columns, start, end, where):
            return [{'id': i, 'value': i*10} for i in range(start, min(end, 100))]
        
        def get_table_row_count(self, table):
            return 100
    
    # Create executor
    db = MockDB()
    executor = ParallelExecutor(db, max_workers=4)
    
    # Test parallel scan
    print("Testing parallel scan...")
    results = list(executor.execute_parallel_scan(
        'test_table', ['id', 'value'], None, dop=4
    ))
    print(f"Scanned {len(results)} rows")
    
    # Test parallel aggregation
    print("\nTesting parallel aggregation...")
    agg_result = executor.execute_parallel_aggregation(
        'test_table', ['SUM(value)'], None, None, dop=4
    )
    print(f"Aggregation result: {agg_result}")
    
    # Get stats
    print(f"\nExecution stats: {executor.get_stats()}")
