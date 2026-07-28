"""
Sort Backends Package for KosDB

Provides unified interface for multiple sorting implementations:
- BuiltinBackend: Python's built-in sort
- MadS0rtPyBackend: madS0rt Python implementation  
- MadS0rtRustBackend: madS0rt Rust implementation

All backends implement:
    sort(values, key=None, reverse=False, stable=True, topk=None)
    sort_in_place(values, key=None, reverse=False, stable=True)
"""

from typing import List, Callable, Optional, Any


class SortBackend:
    """Abstract base class for sort backends."""
    
    name = 'abstract'
    
    def sort(self,
             values: List[Any],
             key: Optional[Callable] = None,
             reverse: bool = False,
             stable: bool = True,
             topk: Optional[int] = None) -> List[Any]:
        """
        Sort values and return new sorted list.
        
        Args:
            values: Values to sort
            key: Key function
            reverse: Reverse order
            stable: Stable sort
            topk: Return only top K elements
        
        Returns:
            Sorted list
        """
        raise NotImplementedError
    
    def sort_in_place(self,
                      values: List[Any],
                      key: Optional[Callable] = None,
                      reverse: bool = False,
                      stable: bool = True) -> None:
        """
        Sort values in place.
        
        Args:
            values: List to sort in place
            key: Key function
            reverse: Reverse order
            stable: Stable sort
        """
        raise NotImplementedError


__all__ = ['SortBackend']
