"""
Connection Pool for KosDB

Implements database connection pooling for efficient resource utilization
with configurable limits, health checking, and monitoring.
"""

import threading
import time
import logging
import queue
import asyncio
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from contextlib import contextmanager, asynccontextmanager

logger = logging.getLogger(__name__)


class ConnectionError(Exception):
    """Raised when connection operations fail."""
    pass


class ConnectionTimeoutError(ConnectionError):
    """Raised when connection acquisition times out."""
    pass


class PoolExhaustedError(ConnectionError):
    """Raised when pool is exhausted and cannot create more connections."""
    pass


@dataclass
class PooledConnection:
    """Represents a connection in the pool."""
    connection_id: str
    created_at: float
    last_used: float
    use_count: int = 0
    is_active: bool = True
    is_idle: bool = True
    health_check_failures: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def mark_used(self):
        """Mark connection as in use."""
        self.last_used = time.time()
        self.use_count += 1
        self.is_idle = False
    
    def mark_idle(self):
        """Mark connection as idle."""
        self.is_idle = True
        self.last_used = time.time()
    
    def mark_unhealthy(self):
        """Mark connection as unhealthy."""
        self.health_check_failures += 1
        self.is_active = False
    
    def mark_healthy(self):
        """Mark connection as healthy."""
        self.health_check_failures = 0
        self.is_active = True
    
    @property
    def idle_time(self) -> float:
        """Time since last use."""
        return time.time() - self.last_used
    
    @property
    def age(self) -> float:
        """Connection age."""
        return time.time() - self.created_at


class ConnectionPool:
    """
    Database connection pool with health checking and monitoring.
    
    Features:
    - Min/max connection limits
    - Connection timeout
    - Idle timeout with cleanup
    - Health checking
    - Statistics tracking
    - Thread-safe operations
    - Async support
    """
    
    def __init__(
        self,
        min_connections: int = 5,
        max_connections: int = 20,
        connection_timeout: float = 30.0,
        idle_timeout: float = 300.0,
        health_check_interval: float = 60.0,
        connection_factory: Optional[Callable] = None,
        pool_name: str = "default"
    ):
        """
        Initialize connection pool.
        
        Args:
            min_connections: Minimum connections to maintain
            max_connections: Maximum connections allowed
            connection_timeout: Max seconds to wait for connection
            idle_timeout: Max seconds a connection can be idle
            health_check_interval: Seconds between health checks
            connection_factory: Callable to create new connections
            pool_name: Name for this pool (for monitoring)
        """
        self.min_connections = min_connections
        self.max_connections = max_connections
        self.connection_timeout = connection_timeout
        self.idle_timeout = idle_timeout
        self.health_check_interval = health_check_interval
        self.connection_factory = connection_factory
        self.pool_name = pool_name
        
        # Connection storage
        self._connections: Dict[str, PooledConnection] = {}
        self._idle_queue: queue.Queue = queue.Queue()
        self._connection_counter = 0
        
        # Synchronization
        self._lock = threading.RLock()
        self._available = threading.Semaphore(0)
        self._shutdown = False
        
        # Statistics
        self._stats = {
            'total_created': 0,
            'total_destroyed': 0,
            'total_borrowed': 0,
            'total_returned': 0,
            'total_timeout': 0,
            'health_check_failures': 0
        }
        
        # Background threads
        self._health_check_thread: Optional[threading.Thread] = None
        self._cleanup_thread: Optional[threading.Thread] = None
        
        # Initialize minimum connections
        self._initialize_pool()
        self._start_background_tasks()
    
    def _initialize_pool(self):
        """Create minimum connections."""
        for _ in range(self.min_connections):
            conn = self._create_connection()
            if conn:
                self._idle_queue.put(conn.connection_id)
                self._available.release()
    
    def _start_background_tasks(self):
        """Start background health check and cleanup threads."""
        self._health_check_thread = threading.Thread(
            target=self._health_check_loop,
            daemon=True
        )
        self._health_check_thread.start()
        
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True
        )
        self._cleanup_thread.start()
    
    def _create_connection(self) -> Optional[PooledConnection]:
        """Create a new pooled connection."""
        with self._lock:
            if len(self._connections) >= self.max_connections:
                return None
            
            self._connection_counter += 1
            conn_id = f"{self.pool_name}_conn_{self._connection_counter}"
            
            # Create actual connection using factory
            if self.connection_factory:
                try:
                    raw_conn = self.connection_factory()
                except Exception as e:
                    logger.error(f"Failed to create connection: {e}")
                    return None
            else:
                raw_conn = None
            
            conn = PooledConnection(
                connection_id=conn_id,
                created_at=time.time(),
                last_used=time.time(),
                metadata={'raw_connection': raw_conn}
            )
            
            self._connections[conn_id] = conn
            self._stats['total_created'] += 1
            
            logger.debug(f"Created connection {conn_id}")
            return conn
    
    def _destroy_connection(self, conn_id: str):
        """Destroy a connection."""
        with self._lock:
            if conn_id not in self._connections:
                return
            
            conn = self._connections.pop(conn_id)
            
            # Close raw connection
            raw_conn = conn.metadata.get('raw_connection')
            if raw_conn and hasattr(raw_conn, 'close'):
                try:
                    raw_conn.close()
                except Exception as e:
                    logger.warning(f"Error closing connection: {e}")
            
            self._stats['total_destroyed'] += 1
            logger.debug(f"Destroyed connection {conn_id}")
    
    def get_connection(self, timeout: Optional[float] = None) -> str:
        """
        Get a connection from the pool.
        
        Args:
            timeout: Override default timeout (seconds)
        
        Returns:
            Connection ID
        
        Raises:
            ConnectionTimeoutError: If cannot get connection in time
            PoolExhaustedError: If pool is at capacity and exhausted
        """
        if self._shutdown:
            raise ConnectionError("Pool is shutdown")
        
        timeout = timeout or self.connection_timeout
        
        # Try to get from idle queue
        if self._available.acquire(timeout=timeout):
            conn_id = self._idle_queue.get()
            
            with self._lock:
                if conn_id in self._connections:
                    conn = self._connections[conn_id]
                    
                    # Validate connection
                    if not self._validate_connection(conn):
                        self._destroy_connection(conn_id)
                        self._stats['health_check_failures'] += 1
                        # Try again
                        return self.get_connection(timeout=timeout)
                    
                    conn.mark_used()
                    self._stats['total_borrowed'] += 1
                    return conn_id
        
        # Try to create new connection
        conn = self._create_connection()
        if conn:
            with self._lock:
                conn.mark_used()
                self._stats['total_borrowed'] += 1
            return conn.connection_id
        
        self._stats['total_timeout'] += 1
        raise ConnectionTimeoutError(
            f"Could not get connection within {timeout}s"
        )
    
    def return_connection(self, conn_id: str, is_healthy: bool = True):
        """
        Return a connection to the pool.
        
        Args:
            conn_id: Connection ID to return
            is_healthy: Whether connection is still healthy
        """
        with self._lock:
            if conn_id not in self._connections:
                logger.warning(f"Attempted to return unknown connection: {conn_id}")
                return
            
            conn = self._connections[conn_id]
            
            if not is_healthy:
                self._destroy_connection(conn_id)
                # Create replacement if below minimum
                if len(self._connections) < self.min_connections:
                    self._create_connection()
                return
            
            conn.mark_idle()
            self._stats['total_returned'] += 1
            
            # Return to pool
            self._idle_queue.put(conn_id)
            self._available.release()
    
    def _validate_connection(self, conn: PooledConnection) -> bool:
        """Validate a connection is healthy."""
        if not conn.is_active:
            return False
        
        if conn.health_check_failures > 3:
            return False
        
        # Custom health check via factory
        if self.connection_factory and hasattr(self.connection_factory, 'validate'):
            raw_conn = conn.metadata.get('raw_connection')
            if raw_conn:
                try:
                    return self.connection_factory.validate(raw_conn)
                except Exception:
                    return False
        
        return True
    
    def _health_check_loop(self):
        """Background health check loop."""
        while not self._shutdown:
            try:
                time.sleep(self.health_check_interval)
                self._perform_health_checks()
            except Exception as e:
                logger.error(f"Health check error: {e}")
    
    def _perform_health_checks(self):
        """Check health of all connections."""
        with self._lock:
            for conn_id, conn in list(self._connections.items()):
                if conn.is_idle:
                    if not self._validate_connection(conn):
                        conn.mark_unhealthy()
                        logger.warning(f"Connection {conn_id} failed health check")
    
    def _cleanup_loop(self):
        """Background cleanup loop for idle connections."""
        while not self._shutdown:
            try:
                time.sleep(30)  # Check every 30 seconds
                self._cleanup_idle_connections()
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
    
    def _cleanup_idle_connections(self):
        """Remove idle connections beyond minimum."""
        with self._lock:
            to_remove = []
            
            for conn_id, conn in self._connections.items():
                if conn.is_idle and conn.idle_time > self.idle_timeout:
                    # Keep minimum connections
                    if len(self._connections) > self.min_connections:
                        to_remove.append(conn_id)
            
            for conn_id in to_remove:
                self._destroy_connection(conn_id)
                logger.debug(f"Cleaned up idle connection {conn_id}")
    
    @contextmanager
    def connection(self, timeout: Optional[float] = None):
        """
        Context manager for connection handling.
        
        Usage:
            with pool.connection() as conn_id:
                # Use connection
                pass
        """
        conn_id = None
        try:
            conn_id = self.get_connection(timeout)
            yield conn_id
        finally:
            if conn_id:
                self.return_connection(conn_id)
    
    # Async support
    async def get_connection_async(self, timeout: Optional[float] = None) -> str:
        """
        Async version of get_connection.
        
        Args:
            timeout: Override default timeout
        
        Returns:
            Connection ID
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, 
            self.get_connection, 
            timeout
        )
    
    async def return_connection_async(self, conn_id: str, is_healthy: bool = True):
        """Async version of return_connection."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            self.return_connection,
            conn_id,
            is_healthy
        )
    
    @asynccontextmanager
    async def connection_async(self, timeout: Optional[float] = None):
        """Async context manager for connection handling."""
        conn_id = None
        try:
            conn_id = await self.get_connection_async(timeout)
            yield conn_id
        finally:
            if conn_id:
                await self.return_connection_async(conn_id)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get pool statistics.
        
        Returns:
            Dictionary with pool statistics
        """
        with self._lock:
            active = sum(1 for c in self._connections.values() if not c.is_idle)
            idle = len(self._connections) - active
            
            return {
                'pool_name': self.pool_name,
                'total_connections': len(self._connections),
                'active_connections': active,
                'idle_connections': idle,
                'min_connections': self.min_connections,
                'max_connections': self.max_connections,
                'connection_timeout': self.connection_timeout,
                'idle_timeout': self.idle_timeout,
                **self._stats
            }
    
    def shutdown(self, wait: bool = True, timeout: float = 30.0):
        """
        Shutdown the pool and close all connections.
        
        Args:
            wait: Wait for connections to be returned
            timeout: Max seconds to wait
        """
        self._shutdown = True
        
        if wait:
            # Wait for active connections to be returned
            start = time.time()
            while time.time() - start < timeout:
                with self._lock:
                    active = sum(1 for c in self._connections.values() if not c.is_idle)
                    if active == 0:
                        break
                time.sleep(0.1)
        
        # Close all connections
        with self._lock:
            for conn_id in list(self._connections.keys()):
                self._destroy_connection(conn_id)
        
        logger.info(f"Pool {self.pool_name} shutdown complete")


# Global pool registry
_pool_registry: Dict[str, ConnectionPool] = {}
_registry_lock = threading.Lock()


def create_pool(
    pool_name: str,
    min_connections: int = 5,
    max_connections: int = 20,
    connection_factory: Optional[Callable] = None,
    **kwargs
) -> ConnectionPool:
    """
    Create a named connection pool.
    
    Args:
        pool_name: Unique name for the pool
        min_connections: Minimum connections
        max_connections: Maximum connections
        connection_factory: Factory function for connections
        **kwargs: Additional pool options
    
    Returns:
        ConnectionPool instance
    """
    with _registry_lock:
        if pool_name in _pool_registry:
            raise ValueError(f"Pool {pool_name} already exists")
        
        pool = ConnectionPool(
            min_connections=min_connections,
            max_connections=max_connections,
            connection_factory=connection_factory,
            pool_name=pool_name,
            **kwargs
        )
        
        _pool_registry[pool_name] = pool
        return pool


def get_pool(pool_name: str) -> Optional[ConnectionPool]:
    """Get pool by name."""
    with _registry_lock:
        return _pool_registry.get(pool_name)


def shutdown_pool(pool_name: str, **kwargs):
    """Shutdown a specific pool."""
    with _registry_lock:
        if pool_name in _pool_registry:
            pool = _pool_registry.pop(pool_name)
            pool.shutdown(**kwargs)


def shutdown_all_pools(**kwargs):
    """Shutdown all pools."""
    with _registry_lock:
        for pool in list(_pool_registry.values()):
            pool.shutdown(**kwargs)
        _pool_registry.clear()


def list_pools() -> List[str]:
    """List all pool names."""
    with _registry_lock:
        return list(_pool_registry.keys())


def get_all_stats() -> Dict[str, Dict[str, Any]]:
    """Get statistics for all pools."""
    with _registry_lock:
        return {
            name: pool.get_stats()
            for name, pool in _pool_registry.items()
        }
