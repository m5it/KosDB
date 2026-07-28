#!/usr/bin/env python3
"""
Sort Engine Factory for KosDB

Provides a unified interface for pluggable sorting backends:
- builtin: Python's built-in sorted()/list.sort()
- madsort_py: madS0rt Python implementation
- madsort_rust: madS0rt Rust implementation with Python bindings

Usage:
    from sort_engine import SortEngine
    
    # Auto-detect best available backend
    engine = SortEngine()
    
    # Or specify backend explicitly
    engine = SortEngine(backend='madsort_rust')
    
    # Sort data
    result = engine.sort(data, key=lambda x: x['name'], reverse=True)
"""

import logging
import os
from typing import List, Callable, Optional, Any, Dict

logger = logging.getLogger(__name__)


class SortEngine:
    """
    Pluggable sort engine supporting multiple backends.
    
    Backends (in priority order):
    1. madsort_rust - Fastest, Rust implementation
    2. madsort_py - Pure Python madS0rt algorithm
    3. builtin - Python's built-in sort (always available)
    """
    
    BACKENDS = ['madsort_rust', 'madsort_py', 'builtin']
    
    def __init__(self, backend: str = 'auto', strict: bool = False):
        """
        Initialize sort engine.
        
        Args:
            backend: 'auto', 'madsort_rust', 'madsort_py', or 'builtin'
            strict: If True, raise error when configured backend unavailable
        """
        self.strict = strict
        self._requested_backend = backend
        self._backend = None
        self._fallback_count = 0
        
        if backend == 'auto':
            self._backend = self._auto_select_backend()
        else:
            self._backend = self._load_backend(backend)
    
    def _auto_select_backend(self) -> Any:
        """Auto-select best available backend."""
        for name in self.BACKENDS:
            try:
                backend = self._load_backend(name)
                logger.info(f"SortEngine auto-selected backend: {name}")
                return backend
            except ImportError:
                continue
        
        # Should never reach here (builtin always available)
        raise RuntimeError("No sort backend available")
    
    def _load_backend(self, name: str) -> Any:
        """Load specific backend by name."""
        if name == 'builtin':
            from sort_backends.builtin import BuiltinBackend
            return BuiltinBackend()
        
        elif name == 'madsort_py':
            from sort_backends.madsort_py import MadS0rtPyBackend
            return MadS0rtPyBackend()
        
        elif name == 'madsort_rust':
            from sort_backends.madsort_rust import MadS0rtRustBackend
            return MadS0rtRustBackend()
        
        else:
            raise ValueError(f"Unknown backend: {name}")
    
    @property
    def backend_name(self) -> str:
        """Get actual backend name being used."""
        return self._backend.name if self._backend else 'unknown'
    
    @property
    def fallback_count(self) -> int:
        """Get number of fallbacks that occurred."""
        return self._fallback_count
    
    def sort(self, 
             values: List[Any], 
             key: Optional[Callable] = None,
             reverse: bool = False,
             stable: bool = True,
             topk: Optional[int] = None) -> List[Any]:
        """
        Sort values using selected backend.
        
        Args:
            values: List of values to sort
            key: Key function for sort (like Python's sorted key)
            reverse: Sort in reverse order
            stable: Stable sort (preserve equal element order)
            topk: If set, return only top K elements (optimization)
        
        Returns:
            Sorted list (or top K if specified)
        """
        try:
            return self._backend.sort(values, key=key, reverse=reverse, 
                                      stable=stable, topk=topk)
        except Exception as e:
            if self.strict:
                raise
            
            logger.warning(f"Sort backend {self.backend_name} failed: {e}")
            self._fallback_count += 1
            
            # Fallback to builtin
            from sort_backends.builtin import BuiltinBackend
            builtin = BuiltinBackend()
            logger.info("Falling back to builtin backend")
            
            return builtin.sort(values, key=key, reverse=reverse,
                               stable=stable, topk=topk)
    
    def sort_in_place(self,
                      values: List[Any],
                      key: Optional[Callable] = None,
                      reverse: bool = False,
                      stable: bool = True) -> None:
        """
        Sort values in place (when possible).
        
        Args:
            values: List to sort in place
            key: Key function
            reverse: Reverse order
            stable: Stable sort
        """
        try:
            self._backend.sort_in_place(values, key=key, reverse=reverse, stable=stable)
        except Exception as e:
            if self.strict:
                raise
            
            logger.warning(f"Sort backend {self.backend_name} failed: {e}")
            self._fallback_count += 1
            
            # Fallback to builtin
            from sort_backends.builtin import BuiltinBackend
            builtin = BuiltinBackend()
            logger.info("Falling back to builtin backend")
            builtin.sort_in_place(values, key=key, reverse=reverse, stable=stable)


def detect_available_backends() -> Dict[str, bool]:
    """
    Detect which sort backends are available.
    
    Returns:
        Dict mapping backend name to availability
    """
    available = {}
    
    # builtin is always available
    available['builtin'] = True
    
    # Check madsort_py
    try:
        import madsort
        available['madsort_py'] = True
    except ImportError:
        available['madsort_py'] = False
    
    # Check madsort_rust
    try:
        import madsort_rust
        available['madsort_rust'] = True
    except ImportError:
        available['madsort_rust'] = False
    
    return available


def get_sort_engine(config: Optional[Dict] = None) -> SortEngine:
    """
    Factory function to create sort engine from config.
    
    Args:
        config: Configuration dict with 'sort_engine' key, or None for auto
    
    Returns:
        Configured SortEngine instance
    """
    # Check environment variable first
    env_backend = os.environ.get('KOSDB_SORT_ENGINE')
    if env_backend:
        logger.info(f"Using sort engine from environment: {env_backend}")
        return SortEngine(backend=env_backend)
    
    # Check config
    if config and 'sort_engine' in config:
        backend = config['sort_engine']
        logger.info(f"Using sort engine from config: {backend}")
        return SortEngine(backend=backend)
    
    # Default to auto
    return SortEngine(backend='auto')
