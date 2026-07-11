"""
Window Functions Module for KosDB v3.3.0

Provides SQL window functions:
- ROW_NUMBER(): Sequential row number
- RANK(): Rank with gaps
- DENSE_RANK(): Rank without gaps
- LEAD(): Access next row
- LAG(): Access previous row
- FIRST_VALUE(): First value in window
- LAST_VALUE(): Last value in window

Supports OVER clause with PARTITION BY and ORDER BY.
"""

from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum


class WindowFunctionType(Enum):
    """Types of window functions."""
    ROW_NUMBER = "ROW_NUMBER"
    RANK = "RANK"
    DENSE_RANK = "DENSE_RANK"
    LEAD = "LEAD"
    LAG = "LAG"
    FIRST_VALUE = "FIRST_VALUE"
    LAST_VALUE = "LAST_VALUE"


@dataclass
class WindowFrame:
    """Window frame specification."""
    partition_by: Optional[List[str]] = None
    order_by: Optional[List[tuple]] = None  # [(column, direction), ...]
    frame_type: Optional[str] = None  # ROWS, RANGE
    start_bound: Optional[str] = None  # UNBOUNDED PRECEDING, N PRECEDING, CURRENT ROW
    end_bound: Optional[str] = None  # CURRENT ROW, N FOLLOWING, UNBOUNDED FOLLOWING


@dataclass
class WindowFunctionCall:
    """Window function call specification."""
    function_type: WindowFunctionType
    args: List[Any]  # For LEAD/LAG: [column, offset, default]
    window_frame: WindowFrame
    alias: Optional[str] = None


class WindowFunctionExecutor:
    """
    Executor for window functions.
    
    Processes data row by row and computes window function results.
    """
    
    def __init__(self):
        self.functions = {
            WindowFunctionType.ROW_NUMBER: self._row_number,
            WindowFunctionType.RANK: self._rank,
            WindowFunctionType.DENSE_RANK: self._dense_rank,
            WindowFunctionType.LEAD: self._lead,
            WindowFunctionType.LAG: self._lag,
            WindowFunctionType.FIRST_VALUE: self._first_value,
            WindowFunctionType.LAST_VALUE: self._last_value,
        }
    
    def execute(self, data: List[Dict], window_calls: List[WindowFunctionCall]) -> List[Dict]:
        """
        Execute window functions on data.
        
        Args:
            data: List of row dictionaries
            window_calls: List of window function calls
        
        Returns:
            Data with window function results added
        """
        if not data:
            return data
        
        result = []
        
        for call in window_calls:
            data = self._execute_single_function(data, call)
        
        return data
    
    def _execute_single_function(self, data: List[Dict], call: WindowFunctionCall) -> List[Dict]:
        """Execute a single window function."""
        func = self.functions.get(call.function_type)
        if not func:
            raise ValueError(f"Unknown window function: {call.function_type}")
        
        return func(data, call)
    
    def _partition_data(self, data: List[Dict], partition_cols: Optional[List[str]]) -> Dict[tuple, List[Dict]]:
        """Partition data by specified columns."""
        if not partition_cols:
            return {(): data}
        
        partitions = {}
        for row in data:
            key = tuple(row.get(col) for col in partition_cols)
            if key not in partitions:
                partitions[key] = []
            partitions[key].append(row)
        
        return partitions
    
    def _sort_partition(self, partition: List[Dict], order_by: Optional[List[tuple]]) -> List[Dict]:
        """Sort partition by ORDER BY clause."""
        if not order_by:
            return partition
        
        def sort_key(row):
            keys = []
            for col, direction in order_by:
                val = row.get(col)
                # Handle None values
                if val is None:
                    keys.append((1, None))  # None sorts last
                else:
                    keys.append((0, val))
            return keys
        
        reverse = any(direction.upper() == 'DESC' for _, direction in order_by)
        return sorted(partition, key=sort_key, reverse=reverse)
    
    def _row_number(self, data: List[Dict], call: WindowFunctionCall) -> List[Dict]:
        """Compute ROW_NUMBER()."""
        result = []
        partitions = self._partition_data(data, call.window_frame.partition_by)
        
        for key, partition in partitions.items():
            sorted_partition = self._sort_partition(partition, call.window_frame.order_by)
            
            for i, row in enumerate(sorted_partition, 1):
                new_row = row.copy()
                alias = call.alias or f"row_number_{call.function_type.value.lower()}"
                new_row[alias] = i
                result.append(new_row)
        
        return result
    
    def _rank(self, data: List[Dict], call: WindowFunctionCall) -> List[Dict]:
        """Compute RANK() with gaps."""
        result = []
        partitions = self._partition_data(data, call.window_frame.partition_by)
        
        for key, partition in partitions.items():
            sorted_partition = self._sort_partition(partition, call.window_frame.order_by)
            
            rank = 1
            prev_key = None
            
            for i, row in enumerate(sorted_partition):
                if i > 0:
                    current_key = tuple(row.get(col) for col, _ in call.window_frame.order_by) if call.window_frame.order_by else (i,)
                    if current_key != prev_key:
                        rank = i + 1
                
                new_row = row.copy()
                alias = call.alias or f"rank_{call.function_type.value.lower()}"
                new_row[alias] = rank
                result.append(new_row)
                
                prev_key = tuple(row.get(col) for col, _ in call.window_frame.order_by) if call.window_frame.order_by else (i,)
        
        return result
    
    def _dense_rank(self, data: List[Dict], call: WindowFunctionCall) -> List[Dict]:
        """Compute DENSE_RANK() without gaps."""
        result = []
        partitions = self._partition_data(data, call.window_frame.partition_by)
        
        for key, partition in partitions.items():
            sorted_partition = self._sort_partition(partition, call.window_frame.order_by)
            
            rank = 1
            prev_key = None
            
            for i, row in enumerate(sorted_partition):
                if i > 0:
                    current_key = tuple(row.get(col) for col, _ in call.window_frame.order_by) if call.window_frame.order_by else (i,)
                    if current_key != prev_key:
                        rank += 1
                
                new_row = row.copy()
                alias = call.alias or f"dense_rank_{call.function_type.value.lower()}"
                new_row[alias] = rank
                result.append(new_row)
                
                prev_key = tuple(row.get(col) for col, _ in call.window_frame.order_by) if call.window_frame.order_by else (i,)
        
        return result
    
    def _lead(self, data: List[Dict], call: WindowFunctionCall) -> List[Dict]:
        """Compute LEAD(column, offset, default)."""
        result = []
        partitions = self._partition_data(data, call.window_frame.partition_by)
        
        offset = call.args[1] if len(call.args) > 1 else 1
        default = call.args[2] if len(call.args) > 2 else None
        source_col = call.args[0] if call.args else None
        
        for key, partition in partitions.items():
            sorted_partition = self._sort_partition(partition, call.window_frame.order_by)
            
            for i, row in enumerate(sorted_partition):
                new_row = row.copy()
                alias = call.alias or f"lead_{source_col}"
                
                lead_idx = i + offset
                if lead_idx < len(sorted_partition):
                    new_row[alias] = sorted_partition[lead_idx].get(source_col)
                else:
                    new_row[alias] = default
                
                result.append(new_row)
        
        return result
    
    def _lag(self, data: List[Dict], call: WindowFunctionCall) -> List[Dict]:
        """Compute LAG(column, offset, default)."""
        result = []
        partitions = self._partition_data(data, call.window_frame.partition_by)
        
        offset = call.args[1] if len(call.args) > 1 else 1
        default = call.args[2] if len(call.args) > 2 else None
        source_col = call.args[0] if call.args else None
        
        for key, partition in partitions.items():
            sorted_partition = self._sort_partition(partition, call.window_frame.order_by)
            
            for i, row in enumerate(sorted_partition):
                new_row = row.copy()
                alias = call.alias or f"lag_{source_col}"
                
                lag_idx = i - offset
                if lag_idx >= 0:
                    new_row[alias] = sorted_partition[lag_idx].get(source_col)
                else:
                    new_row[alias] = default
                
                result.append(new_row)
        
        return result
    
    def _first_value(self, data: List[Dict], call: WindowFunctionCall) -> List[Dict]:
        """Compute FIRST_VALUE(column)."""
        result = []
        partitions = self._partition_data(data, call.window_frame.partition_by)
        
        source_col = call.args[0] if call.args else None
        
        for key, partition in partitions.items():
            sorted_partition = self._sort_partition(partition, call.window_frame.order_by)
            
            first_val = sorted_partition[0].get(source_col) if sorted_partition else None
            
            for row in sorted_partition:
                new_row = row.copy()
                alias = call.alias or f"first_value_{source_col}"
                new_row[alias] = first_val
                result.append(new_row)
        
        return result
    
    def _last_value(self, data: List[Dict], call: WindowFunctionCall) -> List[Dict]:
        """Compute LAST_VALUE(column)."""
        result = []
        partitions = self._partition_data(data, call.window_frame.partition_by)
        
        source_col = call.args[0] if call.args else None
        
        for key, partition in partitions.items():
            sorted_partition = self._sort_partition(partition, call.window_frame.order_by)
            
            last_val = sorted_partition[-1].get(source_col) if sorted_partition else None
            
            for row in sorted_partition:
                new_row = row.copy()
                alias = call.alias or f"last_value_{source_col}"
                new_row[alias] = last_val
                result.append(new_row)
        
        return result


def parse_window_function(expr: str) -> Optional[WindowFunctionCall]:
    """
    Parse window function expression.
    
    Args:
        expr: Expression like "ROW_NUMBER() OVER (PARTITION BY col ORDER BY col2)"
    
    Returns:
        WindowFunctionCall or None if not a window function
    """
    import re
    
    # Match window function pattern
    pattern = r'(\w+)\s*\(([^)]*)\)\s+OVER\s*\(([^)]+)\)'
    match = re.match(pattern, expr, re.IGNORECASE)
    
    if not match:
        return None
    
    func_name = match.group(1).upper()
    args_str = match.group(2).strip()
    over_clause = match.group(3).strip()
    
    # Map function name
    func_map = {
        'ROW_NUMBER': WindowFunctionType.ROW_NUMBER,
        'RANK': WindowFunctionType.RANK,
        'DENSE_RANK': WindowFunctionType.DENSE_RANK,
        'LEAD': WindowFunctionType.LEAD,
        'LAG': WindowFunctionType.LAG,
        'FIRST_VALUE': WindowFunctionType.FIRST_VALUE,
        'LAST_VALUE': WindowFunctionType.LAST_VALUE,
    }
    
    func_type = func_map.get(func_name)
    if not func_type:
        return None
    
    # Parse arguments
    args = [a.strip().strip('"\'') for a in args_str.split(',')] if args_str else []
    
    # Parse OVER clause
    frame = WindowFrame()
    
    # PARTITION BY
    partition_match = re.search(r'PARTITION\s+BY\s+([^)]+?)(?:\s+ORDER\s+BY|\s*$)', over_clause, re.IGNORECASE)
    if partition_match:
        frame.partition_by = [c.strip() for c in partition_match.group(1).split(',')]
    
    # ORDER BY
    order_match = re.search(r'ORDER\s+BY\s+([^)]+)', over_clause, re.IGNORECASE)
    if order_match:
        order_parts = []
        for part in order_match.group(1).split(','):
            part = part.strip()
            if ' ' in part:
                col, direction = part.rsplit(' ', 1)
                order_parts.append((col.strip(), direction.strip()))
            else:
                order_parts.append((part, 'ASC'))
        frame.order_by = order_parts
    
    return WindowFunctionCall(
        function_type=func_type,
        args=args,
        window_frame=frame
    )


# Example usage
if __name__ == '__main__':
    # Sample data
    data = [
        {'dept': 'Sales', 'name': 'Alice', 'salary': 50000},
        {'dept': 'Sales', 'name': 'Bob', 'salary': 55000},
        {'dept': 'Sales', 'name': 'Carol', 'salary': 55000},
        {'dept': 'IT', 'name': 'David', 'salary': 60000},
        {'dept': 'IT', 'name': 'Eve', 'salary': 65000},
    ]
    
    executor = WindowFunctionExecutor()
    
    # Test ROW_NUMBER
    call = WindowFunctionCall(
        function_type=WindowFunctionType.ROW_NUMBER,
        args=[],
        window_frame=WindowFrame(partition_by=['dept'], order_by=[('salary', 'DESC')])
    )
    
    result = executor.execute(data, [call])
    
    print("Window Function Results:")
    for row in result:
        print(row)
