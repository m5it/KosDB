
"""
Batch Connection Pool for KosDB v2.3.0

Optimizes batch execution with connection pooling:
- Respects pool limits
- Connection reuse within batches
- Pool exhaustion handling
- Batch-specific metrics
- Wait timeouts
"""

import threading
import time
import logging
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from collections import deque
from contextlib import contextmanager
import queue

logger = logging.getLogger(__name__)


@dataclass
class PoolMetrics:
    """Metrics for connection pool."""
    total_connections: int = 0
    active_connections: int = 0
    idle_connections: int = 0
    waiting_requests: int = 0
    batch_active_connections: int = 0
    total_requests: int = 0
    total_timeouts: int = 0
    total_wait_time_ms: float = 0
    avg_wait_time_ms: float = 0
    pool_exhaustion_events: int = 0


@dataclass
class PooledConnection:
    """Wrapper for pooled connections."""
    connection: Any
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    use_count: int = 0
    in_batch: bool = False
    batch_id: Optional[str] = None
    
    def mark_used(self):
        """Mark connection as used."""
        self.last_used = time.time()
        self.use_count += 1
    
    def mark_batch_start(self, batch_id: str):
        """Mark connection as being used for batch."""
        self.in_batch = True
        self.batch_id = batch_id
    
    def mark_batch_end(self):
        """Mark batch usage complete."""
        self.in_batch = False
        self.batch_id = None


class BatchConnectionPool:
    """
    Connection pool optimized for batch operations.
    
    Features:
    - Separate tracking for batch connections
    - Connection affinity within batches
    - Configurable wait timeouts
    - Exhaustion handling
    - Comprehensive metrics
    """
    
    def __init__(
        self,
        min_connections: int = 5,
        max_connections: int = 50,
        max_batch_connections: int = 20,
        pool_wait_timeout_ms: int = 5000,
        connection_timeout_ms: int = 30000,
        idle_timeout_ms: int = 300000,
        connection_factory: Optional[callable] = None
    ):
        """
        Initialize batch connection pool.
        
        Args:
            min_connections: Minimum connections to maintain
            max_connections: Maximum connections allowed
            max_batch_connections: Max connections for batch operations
            pool_wait_timeout_ms: Timeout for waiting on pool
            connection_timeout_ms: Connection establishment timeout
            idle_timeout_ms: Idle connection timeout
            connection_factory: Factory function for new connections
        """
        self.min_connections = min_connections
        self.max_connections = max_connections
        self.max_batch_connections = max_batch_connections
        self.pool_wait_timeout_ms = pool_wait_timeout_ms
        self.connection_timeout_ms = connection_timeout_ms
        self.idle_timeout_ms = idle_timeout_ms
        self.connection_factory = connection_factory
        
        # Pool state
        self._pool: deque = deque()
        self._active: Set[PooledConnection] = set()
        self._batch_connections: Dict[str, PooledConnection] = {}
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        
        # Metrics
        self._metrics = PoolMetrics()
        self._metrics_lock = threading.Lock()
        
        # Initialize minimum connections
        self._initialize_min_connections()
        
        # Start maintenance thread
        self._running = True
        self._maintenance_thread = threading.Thread(
            target=self._maintenance_loop,
            daemon=True
        )
        self._maintenance_thread.start()
    
    def _initialize_min_connections(self):
        """Create minimum required connections."""
        for _ in range(self.min_connections):
            try:
                conn = self._create_connection()
                self._pool.append(conn)
                self._metrics.total_connections += 1
            except Exception as e:
                logger.error(f"Failed to create initial connection: {e}")
    
    def _create_connection(self) -> PooledConnection:
        """Create new pooled connection."""
        if not self.connection_factory:
            raise ValueError("Connection factory not set")
        
        raw_conn = self.connection_factory()
        return PooledConnection(connection=raw_conn)
    
    def _destroy_connection(self, pooled_conn: PooledConnection):
        """Destroy a connection."""
        try:
            if hasattr(pooled_conn.connection, 'close'):
                pooled_conn.connection.close()
        except Exception as e:
            logger.warning(f"Error closing connection: {e}")
        
        with self._metrics_lock:
            self._metrics.total_connections -= 1
    
    def acquire(
        self,
        timeout_ms: Optional[int] = None,
        for_batch: bool = False,
        batch_id: Optional[str] = None
    ) -> PooledConnection:
        """
        Acquire connection from pool.
        
        Args:
            timeout_ms: Wait timeout (uses default if None)
            for_batch: Whether for batch operation
            batch_id: Batch identifier for connection affinity
        
        Returns:
            PooledConnection
        
        Raises:
            TimeoutError: If cannot acquire within timeout
        """
        timeout_ms = timeout_ms or self.pool_wait_timeout_ms
        deadline = time.time() + (timeout_ms / 1000)
        wait_start = time.time()
        
        with self._condition:
            while True:
                # Check for batch connection affinity
                if batch_id and batch_id in self._batch_connections:
                    conn = self._batch_connections[batch_id]
                    if conn in self._active:
                        conn.mark_used()
                        return conn
                
                # Try to get idle connection
                if self._pool:
                    conn = self._pool.popleft()
                    conn.mark_used()
                    self._active.add(conn)
                    
                    if for_batch and batch_id:
                        conn.mark_batch_start(batch_id)
                        self._batch_connections[batch_id] = conn
                        self._metrics.batch_active_connections += 1
                    
                    self._update_metrics(acquired=True, wait_time=0)
                    return conn
                
                # Try to create new connection if under limit
                total = len(self._pool) + len(self._active)
                if total < self.max_connections:
                    try:
                        conn = self._create_connection()
                        conn.mark_used()
                        self._active.add(conn)
                        
                        if for_batch and batch_id:
                            conn.mark_batch_start(batch_id)
                            self._batch_connections[batch_id] = conn
                            self._metrics.batch_active_connections += 1
                        
                        self._metrics.total_connections += 1
                        self._update_metrics(acquired=True, wait_time=0)
                        return conn
                    except Exception as e:
                        logger.error(f"Failed to create connection: {e}")
                
                # Check if we can wait
                remaining = deadline - time.time()
                if remaining <= 0:
                    self._metrics.total_timeouts += 1
                    self._metrics.pool_exhaustion_events += 1
                    raise TimeoutError(
                        f"Could not acquire connection within {timeout_ms}ms. "
                        f"Pool: {len(self._pool)} idle, {len(self._active)} active"
                    )
                
                # Check batch connection limit
                if for_batch and self._metrics.batch_active_connections >= self.max_batch_connections:
                    self._metrics.pool_exhaustion_events += 1
                    raise TimeoutError(
                        f"Batch connection limit ({self.max_batch_connections}) reached"
                    )
                
                # Wait for connection to become available
                self._metrics.waiting_requests += 1
                self._condition.wait(timeout=remaining)
                self._metrics.waiting_requests -= 1
        
        wait_time = (time.time() - wait_start) * 1000
        self._update_metrics(acquired=True, wait_time=wait_time)
    
    def release(self, pooled_conn: PooledConnection, batch_complete: bool = False):
        """
        Release connection back to pool.
        
        Args:
            pooled_conn: Connection to release
            batch_complete: Whether batch using this connection is complete
        """
        with self._condition:
            if pooled_conn in self._active:
                self._active.remove(pooled_conn)
                
                # Handle batch connection cleanup
                if pooled_conn.in_batch:
                    if batch_complete or pooled_conn.batch_id:
                        self._metrics.batch_active_connections -= 1
                        if pooled_conn.batch_id in self._batch_connections:
                            del self._batch_connections[pooled_conn.batch_id]
                        pooled_conn.mark_batch_end()
                
                # Return to pool if healthy
                if self._is_healthy(pooled_conn):
                    self._pool.append(pooled_conn)
                else:
                    self._destroy_connection(pooled_conn)
                
                self._condition.notify()
    
    def _is_healthy(self, pooled_conn: PooledConnection) -> bool:
        """Check if connection is healthy."""
        # Check if connection is still valid
        if hasattr(pooled_conn.connection, 'is_connected'):
            return pooled_conn.connection.is_connected()
        
        # Check idle timeout
        idle_time = time.time() - pooled_conn.last_used
        if idle_time > (self.idle_timeout_ms / 1000):
            return False
        
        return True
    
    @contextmanager
    def connection(
        self,
        timeout_ms: Optional[int] = None,
        for_batch: bool = False,
        batch_id: Optional[str] = None
    ):
        """
        Context manager for acquiring/releasing connections.
        
        Usage:
            with pool.connection(for_batch=True, batch_id="batch_001") as conn:
                # Use connection
                pass
        """
        conn = None
        try:
            conn = self.acquire(timeout_ms, for_batch, batch_id)
            yield conn
        finally:
            if conn:
                self.release(conn)
    
    def release_batch(self, batch_id: str):
        """
        Release all connections associated with a batch.
        
        Args:
            batch_id: Batch identifier
        """
        with self._condition:
            if batch_id in self._batch_connections:
                conn = self._batch_connections[batch_id]
                self.release(conn, batch_complete=True)
    
    def _update_metrics(self, acquired: bool, wait_time: float):
        """Update pool metrics."""
        with self._metrics_lock:
            if acquired:
                self._metrics.total_requests += 1
                self._metrics.total_wait_time_ms += wait_time
            
            self._metrics.active_connections = len(self._active)
            self._metrics.idle_connections = len(self._pool)
            
            if self._metrics.total_requests > 0:
                self._metrics.avg_wait_time_ms = (
                    self._metrics.total_wait_time_ms / self._metrics.total_requests
                )
    
    def _maintenance_loop(self):
        """Background maintenance thread."""
        while self._running:
            try:
                time.sleep(30)  # Run every 30 seconds
                
                with self._lock:
                    # Remove stale connections
                    now = time.time()
                    stale = []
                    
                    for conn in list(self._pool):
                        if now - conn.last_used > (self.idle_timeout_ms / 1000):
                            stale.append(conn)
                    
                    for conn in stale:
                        self._pool.remove(conn)
                        self._destroy_connection(conn)
                        logger.debug("Removed stale connection")
                    
                    # Ensure minimum connections
                    while len(self._pool) + len(self._active) < self.min_connections:
                        try:
                            conn = self._create_connection()
                            self._pool.append(conn)
                            self._metrics.total_connections += 1
                        except Exception as e:
                            logger.error(f"Failed to create maintenance connection: {e}")
                            break
                            
            except Exception as e:
                logger.error(f"Maintenance loop error: {e}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current pool metrics."""
        with self._metrics_lock:
            return {
                'total_connections': self._metrics.total_connections,
                'active_connections': self._metrics.active_connections,
                'idle_connections': self._metrics.idle_connections,
                'waiting_requests': self._metrics.waiting_requests,
                'batch_active_connections': self._metrics.batch_active_connections,
                'total_requests': self._metrics.total_requests,
                'total_timeouts': self._metrics.total_timeouts,
                'avg_wait_time_ms': round(self._metrics.avg_wait_time_ms, 2),
                'pool_exhaustion_events': self._metrics.pool_exhaustion_events,
                'utilization_percent': round(
                    (self._metrics.active_connections / self.max_connections) * 100, 2
                ) if self.max_connections > 0 else 0,
            }
    
    def get_status(self) -> str:
        """Get human-readable pool status."""
        metrics = self.get_metrics()
        
        status = f"""
========================================
BATCH CONNECTION POOL STATUS
========================================
Total Connections:    {metrics['total_connections']}
Active Connections:   {metrics['active_connections']}
Idle Connections:     {metrics['idle_connections']}
Waiting Requests:     {metrics['waiting_requests']}
Batch Connections:    {metrics['batch_active_connections']}

Performance Metrics:
  Total Requests:     {metrics['total_requests']}
  Timeouts:           {metrics['total_timeouts']}
  Avg Wait Time:      {metrics['avg_wait_time_ms']} ms
  Exhaustion Events:  {metrics['pool_exhaustion_events']}
  
Utilization:          {metrics['utilization_percent']}%
========================================
"""
        return status
    
    def get_batch_status(self) -> Dict[str, Any]:
        """Get status of batch connections."""
        with self._lock:
            batch_info = {}
            for batch_id, conn in self._batch_connections.items():
                batch_info[batch_id] = {
                    'use_count': conn.use_count,
                    'created_at': conn.created_at,
                    'last_used': conn.last_used,
                }
            return batch_info
    
    def close(self):
        """Close pool and all connections."""
        self._running = False
        
        with self._condition:
            # Close all idle connections
            while self._pool:
                conn = self._pool.popleft()
                self._destroy_connection(conn)
            
            # Close active connections
            for conn in list(self._active):
                self._destroy_connection(conn)
            self._active.clear()
            
            self._batch_connections.clear()
        
        if self._maintenance_thread.is_alive():
            self._maintenance_thread.join(timeout=5)
        
        logger.info("Connection pool closed")


class BatchConnectionPoolManager:
    """
    Manager for multiple connection pools (e.g., per shard).
    """
    
    def __init__(self):
        self._pools: Dict[str, BatchConnectionPool] = {}
        self._lock = threading.RLock()
    
    def create_pool(
        self,
        name: str,
        **kwargs
    ) -> BatchConnectionPool:
        """Create named connection pool."""
        with self._lock:
            if name in self._pools:
                raise ValueError(f"Pool '{name}' already exists")
            
            pool = BatchConnectionPool(**kwargs)
            self._pools[name] = pool
            return pool
    
    def get_pool(self, name: str) -> Optional[BatchConnectionPool]:
        """Get pool by name."""
        with self._lock:
            return self._pools.get(name)
    
    def remove_pool(self, name: str):
        """Remove and close a pool."""
        with self._lock:
            pool = self._pools.pop(name, None)
            if pool:
                pool.close()
    
    def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get metrics from all pools."""
        with self._lock:
            return {
                name: pool.get_metrics()
                for name, pool in self._pools.items()
            }
    
    def get_all_status(self) -> str:
        """Get status of all pools."""
        with self._lock:
            statuses = []
            for name, pool in self._pools.items():
                status = pool.get_status()
                statuses.append(f"Pool: {name}\n{status}")
            return "\n".join(statuses)
    
    def close_all(self):
        """Close all pools."""
        with self._lock:
            for pool in self._pools.values():
                pool.close()
            self._pools.clear()


# Global pool manager
_pool_manager = BatchConnectionPoolManager()


def get_pool_manager() -> BatchConnectionPoolManager:
    """Get global pool manager."""
    return _pool_manager


def create_batch_pool(
    name: str,
    connection_factory: callable,
    min_connections: int = 5,
    max_connections: int = 50,
    max_batch_connections: int = 20,
    pool_wait_timeout_ms: int = 5000
) -> BatchConnectionPool:
    """
    Create batch connection pool with common defaults.
    
    Args:
        name: Pool name
        connection_factory: Factory for creating connections
        min_connections: Minimum connections
        max_connections: Maximum connections
        max_batch_connections: Max connections for batches
        pool_wait_timeout_ms: Wait timeout
    
    Returns:
        BatchConnectionPool instance
    """
    return get_pool_manager().create_pool(
        name=name,
        connection_factory=connection_factory,
        min_connections=min_connections,
        max_connections=max_connections,
        max_batch_connections=max_batch_connections,
        pool_wait_timeout_ms=pool_wait_timeout_ms
    )
