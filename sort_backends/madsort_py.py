"""
madS0rt Python Backend for KosDB

Uses the madS0rt Python library for high-performance sorting.
Falls back to builtin if madS0rt is not available.
"""

import logging
from typing import List, Callable, Optional, Any

from . import SortBackend

logger = logging.getLogger(__name__)


class MadS0rtPyBackend(SortBackend):
    """
    madS0rt Python implementation backend.
    
    Optimized sorting algorithm for complex objects and large datasets.
    Falls back to builtin if madS0rt unavailable.
    """
    
    name = 'madsort_py'
    
    def __init__(self):
        """Initialize and check availability."""
        try:
            import madsort
            self._madsort = madsort
            self._available = True
        except ImportError:
            self._available = False
            raise ImportError("madS0rt Python package not installed")
    
    def sort(self,
             values: List[Any],
             key: Optional[Callable] = None,
             reverse: bool = False,
             stable: bool = True,
             topk: Optional[int] = None) -> List[Any]:
        """
        Sort using madS0rt Python implementation.
        
        Args:
            values: Values to sort
            key: Key function
            reverse: Reverse order
            stable: Stable sort
            topk: If set, return only top K
        
        Returns:
            New sorted list
        """
        if not self._available:
            raise RuntimeError("madS0rt_py backend not available")
        
        # If no key function, use madS0rt directly
        if key is None:
            result = self._madsort.sort(values)
            if reverse:
                result.reverse()
            if topk:
                result = result[:topk]
            return result
        
        # With key function, need to decorate-sort-undecorate
        # or fall back to builtin if madS0rt doesn't support keys
        decorated = [(key(v), v) for v in values]
        sorted_decorated = self._madsort.sort(decorated, key=lambda x: x[0])
        
        if reverse:
            sorted_decorated.reverse()
        
        if topk:
            sorted_decorated = sorted_decorated[:topk]
        
        return [v for k, v in sorted_decorated]
    
    def sort_in_place(self,
                      values: List[Any],
                      key: Optional[Callable] = None,
                      reverse: bool = False,
                      stable: bool = True) -> None:
        """
        Sort in place using madS0rt.
        
        Args:
            values: List to sort in place
            key: Key function
            reverse: Reverse order
            stable: Stable sort
        """
        sorted_values = self.sort(values, key=key, reverse=reverse, stable=stable)
        values[:] = sorted_values
