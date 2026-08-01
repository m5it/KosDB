#!/usr/bin/env python3
"""Integrate sort engine into database.py"""

import re

with open('database.py', 'r') as f:
    content = f.read()

# Add sort_engine import at the top (after other imports)
old_imports = '''from typing import Optional, Dict, Any, List
from binlog import Binlog'''

new_imports = '''from typing import Optional, Dict, Any, List
from binlog import Binlog

try:
    from sort_engine import SortEngine, get_sort_engine
    SORT_ENGINE_AVAILABLE = True
except ImportError:
    SORT_ENGINE_AVAILABLE = False'''

content = content.replace(old_imports, new_imports)

# Update __init__ to accept sort_engine parameter
old_init = '''    def __init__(self, data_dir: str = "data", server_id: int = 1, 
                 cache_size: int = 8*1024*1024,  # 8MB default block cache
                 write_buffer_size: int = 4*1024*1024,  # 4MB default
                 max_open_files: int = 1000,
                 compression: str = 'snappy',
                 bloom_filter_bits: int = 10,
                 sync_writes: bool = False,  # fsync on every write
                 disable_wal: bool = False):  # Disable WAL for bulk load'''

new_init = '''    def __init__(self, data_dir: str = "data", server_id: int = 1, 
                 cache_size: int = 8*1024*1024,  # 8MB default block cache
                 write_buffer_size: int = 4*1024*1024,  # 4MB default
                 max_open_files: int = 1000,
                 compression: str = 'snappy',
                 bloom_filter_bits: int = 10,
                 sync_writes: bool = False,  # fsync on every write
                 disable_wal: bool = False,  # Disable WAL for bulk load
                 sort_engine: Optional[Any] = None):  # Sort engine for ORDER BY'''

content = content.replace(old_init, new_init)

# Add sort_engine initialization in __init__
old_init_body = '''        self._transaction_active = False
        self._transaction_changes: Dict[bytes, Optional[bytes]] = {}

        self._db_lock = threading.Lock()'''

new_init_body = '''        self._transaction_active = False
        self._transaction_changes: Dict[bytes, Optional[bytes]] = {}

        # Initialize sort engine for ORDER BY operations
        if SORT_ENGINE_AVAILABLE:
            if sort_engine is not None:
                self._sort_engine = sort_engine
            else:
                self._sort_engine = get_sort_engine()
        else:
            self._sort_engine = None

        self._db_lock = threading.Lock()'''

content = content.replace(old_init_body, new_init_body)

# Add sort_engine property
old_close_method = '''    def close(self):
        """Close the database connection."""'''

new_close_method = '''    @property
    def sort_engine(self):
        """Get the sort engine for ORDER BY operations."""
        return self._sort_engine
    
    def _sort_results(self, results: List[Dict], order_by: str, order_desc: bool = False) -> List[Dict]:
        """
        Sort results using configured sort engine.
        
        Args:
            results: List of row dictionaries
            order_by: Column to sort by
            order_desc: Reverse order if True
        
        Returns:
            Sorted results
        """
        if not results or len(results) < 2:
            return results
        
        # Use sort engine if available
        if self._sort_engine is not None:
            try:
                return self._sort_engine.sort(
                    results,
                    key=lambda r: r.get(order_by, ""),
                    reverse=order_desc
                )
            except Exception as e:
                # Log warning and fall back to built-in sort
                import logging
                logging.getLogger(__name__).warning(
                    f"Sort engine failed, falling back to built-in: {e}"
                )
        
        # Built-in fallback
        return sorted(results, key=lambda r: r.get(order_by, ""), reverse=order_desc)

    def close(self):
        """Close the database connection."""'''

content = content.replace(old_close_method, new_close_method)

# Update select method to use sort engine
old_select_sort = '''            if order_by == "id":
                results.sort(key=lambda r: r.get("id", ""), reverse=order_desc)'''

new_select_sort = '''            if order_by == "id":
                results = self._sort_results(results, "id", order_desc)'''

content = content.replace(old_select_sort, new_select_sort)

# Update _select_with_index to use sort engine
old_index_sort = '''            results.sort(key=lambda r: r.get(order_by, ""), reverse=order_desc)'''

new_index_sort = '''            results = self._sort_results(results, order_by, order_desc)'''

content = content.replace(old_index_sort, new_index_sort)

with open('database.py', 'w') as f:
    f.write(content)

print("✅ Sort engine integrated into database.py")
print("Changes:")
print("  - Added SortEngine import with fallback")
print("  - __init__ accepts sort_engine parameter")
print("  - _sort_engine property added")
print("  - _sort_results() method for sorting with fallback")
print("  - select() uses sort engine for ORDER BY")
print("  - _select_with_index() uses sort engine")
