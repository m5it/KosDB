"""
Builtin Sort Backend for KosDB

Uses Python's built-in sorted() and list.sort() functions.
Always available, serves as the fallback backend.
"""

import logging
from typing import List, Callable, Optional, Any

from . import SortBackend

logger = logging.getLogger(__name__)


class BuiltinBackend(SortBackend):
    """
    Python built-in sort backend.
    
    Uses Timsort algorithm (O(n log n) worst case, O(n) best case).
    Stable sort. Always available.
    """
    
    name = 'builtin'
    
    def sort(self,
             values: List[Any],
             key: Optional[Callable] = None,
             reverse: bool = False,
             stable: bool = True,
             topk: Optional[int] = None) -> List[Any]:
        """
        Sort using Python's built-in sorted().
        
        Args:
            values: Values to sort
            key: Key function
            reverse: Reverse order
            stable: Ignored (Timsort is always stable)
            topk: If set, use heapq.nlargest/nsmallest for efficiency
        
        Returns:
            New sorted list
        """
        # For top-K optimization, use heapq when beneficial
        if topk is not None and len(values) > topk * 2:
            # Only use heap optimization when it saves work
            import heapq
            
            if reverse:
                # Largest first
                return heapq.nlargest(topk, values, key=key)
            else:
                # Smallest first
                return heapq.nsmallest(topk, values, key=key)
        
        # Standard sort
        return sorted(values, key=key, reverse=reverse)
    
    def sort_in_place(self,
                      values: List[Any],
                      key: Optional[Callable] = None,
                      reverse: bool = False,
                      stable: bool = True) -> None:
        """
        Sort in place using list.sort().
        
        Args:
            values: List to sort in place
            key: Key function
            reverse: Reverse order
            stable: Ignored (Timsort is always stable)
        """
        values.sort(key=key, reverse=reverse)
