"""
madS0rt Rust Backend for KosDB

Uses the madS0rt-rust Python bindings for maximum performance.
Falls back to madsort_py or builtin if not available.
"""

import logging
from typing import List, Callable, Optional, Any

from . import SortBackend

logger = logging.getLogger(__name__)


class MadS0rtRustBackend(SortBackend):
    """
    madS0rt Rust implementation backend.
    
    High-performance Rust-based sorting with Python bindings.
    Preferred backend when available.
    """
    
    name = 'madsort_rust'
    
    def __init__(self):
        """Initialize and check availability."""
        try:
            import madsort_rust
            self._madsort = madsort_rust
            self._available = True
        except ImportError:
            self._available = False
            raise ImportError("madS0rt-rust package not installed")
    
    def sort(self,
             values: List[Any],
             key: Optional[Callable] = None,
             reverse: bool = False,
             stable: bool = True,
             topk: Optional[int] = None) -> List[Any]:
        """
        Sort using madS0rt Rust implementation.
        
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
            raise RuntimeError("madsort_rust backend not available")
        
        # Use Rust implementation's sort function
        # Check if it supports key function natively
        if hasattr(self._madsort, 'sort_with_key'):
            result = self._madsort.sort_with_key(
                values, 
                key=key,
                reverse=reverse,
                stable=stable
            )
            if topk:
                result = result[:topk]
            return result
        
        # Fallback to basic sort with decorate-sort-undecorate
        if key is not None:
            decorated = [(key(v), i, v) for i, v in enumerate(values)]
            sorted_decorated = self._madsort.sort(decorated)
            
            if reverse:
                sorted_decorated.reverse()
            
            if topk:
                sorted_decorated = sorted_decorated[:topk]
            
            return [v for k, i, v in sorted_decorated]
        
        # No key function - direct sort
        result = self._madsort.sort(values)
        if reverse:
            result.reverse()
        if topk:
            result = result[:topk]
        return result
    
    def sort_in_place(self,
                      values: List[Any],
                      key: Optional[Callable] = None,
                      reverse: bool = False,
                      stable: bool = True) -> None:
        """
        Sort in place using madS0rt Rust.
        
        Args:
            values: List to sort in place
            key: Key function
            reverse: Reverse order
            stable: Stable sort
        """
        sorted_values = self.sort(values, key=key, reverse=reverse, stable=stable)
        values[:] = sorted_values
