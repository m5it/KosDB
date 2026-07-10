"""
Connection Pool for KosDB CLI Client

Provides connection pooling to improve performance for batch operations
and concurrent database access.
"""

import socket
import ssl
import threading
import time
import logging
import queue
from typing import Optional, Dict, Any, List, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum, auto

# Configure logging
logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """Connection states in the pool."""
    IDLE = auto()
    BUSY = auto()
    CLOSED = auto()
    ERROR = auto()


@dataclass
class PooledConnection:
    """Wrapper for pooled connections."""
    socket: socket.socket
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    use_count: int = 0
    state: ConnectionState = ConnectionState.IDLE
    lock: threading.RLock = field(default_factory=threading.RLock)
    id: int = field(default=0)
    
    def touch(self):
        """Update last used timestamp."""
        self.last_used = time.time()
        self.use_count += 1
    
    def is_expired(self, max_age: float, max_idle: float) -> bool:
        """Check if connection has expired."""
        now = time.time()
        age = now - self.created_at
        idle_time = now - self.last_used
        
        return age > max_age or idle_time > max_idle
    
    def is_healthy(self, timeout: float = 5.0) -> bool:
        """Check if connection is still healthy."""
        try:
            # Try to send a ping (empty data with MSG_DONTWAIT if available)
            self.socket.settimeout(timeout)
            # Check if socket is still connected by peeking
            self.socket.setblocking(0)
            try:
                data = self.socket.recv(1, socket.MSG_PEEK)
                # If we got empty data, connection is closed
                if len(data) == 0:
                    return False
            except BlockingIOError:
                # No data available, connection is still open
                pass
            except socket.error:
                return False
            finally:
                self.socket.setblocking(1)
            
            return True
        except Exception as e:
            logger.debug(f"Connection health check failed: {e}")
            return False
    
    def close(self):
        """Close the connection."""
        with self.lock:
            try:
                self.socket.close()
            except:
                pass
            self.state = ConnectionState.CLOSED


class ConnectionPoolError(Exception):
    """Base exception for connection pool errors."""
    pass


class PoolExhaustedError(ConnectionPoolError):
    """Raised when connection pool is exhausted."""
    pass


class ConnectionTimeoutError(ConnectionPoolError):
    """Raised when connection cannot be obtained within timeout."""
    pass


class ConnectionPool:
    """
    Thread-safe connection pool for KosDB client.
    
    Features:
    - Configurable min/max connections
    - Connection lifecycle management
    - Health checking and validation
    - Idle timeout handling
    - Thread-safe borrowing/returning
    """
    
    def __init__(
        self,
        host: str = 'localhost',
        port: int = 9999,
        use_tls: bool = False,
        ssl_context: Optional[ssl.SSLContext] = None,
        min_connections: int = 1,
        max_connections: int = 10,
        max_age: float = 3600.0,  # 1 hour
        max_idle: float = 300.0,  # 5 minutes
        connection_timeout: float = 30.0,
        acquire_timeout: float = 10.0,
        health_check_interval: float = 60.0,
        validate_on_borrow: bool = True
    ):
        """
        Initialize connection pool.
        
        Args:
            host: Server host
            port: Server port
            use_tls: Whether to use TLS
            ssl_context: SSL context for TLS connections
            min_connections: Minimum connections to maintain
            max_connections: Maximum connections allowed
            max_age: Maximum connection age in seconds
            max_idle: Maximum idle time before closing
            connection_timeout: Timeout for creating connections
            acquire_timeout: Timeout for acquiring connection from pool
            health_check_interval: Interval between health checks
            validate_on_borrow: Whether to validate connections before lending
        """
        self.host = host
        self.port = port
        self.use_tls = use_tls
        self.ssl_context = ssl_context
        
        self.min_connections = min(min_connections, max_connections)
        self.max_connections = max_connections
        self.max_age = max_age
        self.max_idle = max_idle
        self.connection_timeout = connection_timeout
        self.acquire_timeout = acquire_timeout
        self.health_check_interval = health_check_interval
        self.validate_on_borrow = validate_on_borrow
        
        # Pool state
        self._pool: queue.Queue[PooledConnection] = queue.Queue()
        self._all_connections: Dict[int, PooledConnection] = {}
        self._connection_count = 0
        self._connection_id_counter = 0
        
        # Threading
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._running = False
        self._maintenance_thread: Optional[threading.Thread] = None
        
        # Statistics
        self._stats = {
            'created': 0,
            'destroyed': 0,
            'borrowed': 0,
            'returned': 0,
            'validation_failures': 0,
            'timeout_errors': 0
        }
    
    def start(self):
        """Start the connection pool."""
        with self._lock:
            if self._running:
                return
            
            self._running = True
            logger.info(f"[Pool] Starting with {self.min_connections} min connections")
            
            # Create initial connections
            for _ in range(self.min_connections):
                try:
                    conn = self._create_connection()
                    if conn:
                        self._pool.put(conn)
                except Exception as e:
                    logger.error(f"[Pool] Failed to create initial connection: {e}")
            
            # Start maintenance thread
            self._maintenance_thread = threading.Thread(
                target=self._maintenance_loop,
                daemon=True
            )
            self._maintenance_thread.start()
            
            logger.info(f"[Pool] Started with {self._connection_count} connections")
    
    def stop(self):
        """Stop the connection pool and close all connections."""
        with self._lock:
            if not self._running:
                return
            
            self._running = False
            self._condition.notify_all()
        
        # Wait for maintenance thread
        if self._maintenance_thread:
            self._maintenance_thread.join(timeout=5.0)
        
        # Close all connections
        with self._lock:
            # Close pooled connections
            while not self._pool.empty():
                try:
                    conn = self._pool.get_nowait()
                    conn.close()
                    self._stats['destroyed'] += 1
                except queue.Empty:
                    break
            
            # Close all tracked connections
            for conn in list(self._all_connections.values()):
                conn.close()
                self._stats['destroyed'] += 1
            
            self._all_connections.clear()
            self._connection_count = 0
        
        logger.info("[Pool] Stopped and all connections closed")
    
    def _create_connection(self) -> Optional[PooledConnection]:
        """
        Create a new connection.
        
        Returns:
            PooledConnection or None if creation failed
        """
        try:
            # Create socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.connection_timeout)
            
            # Wrap with TLS if needed
            if self.use_tls:
                if self.ssl_context:
                    sock = self.ssl_context.wrap_socket(
                        sock,
                        server_hostname=self.host
                    )
                else:
                    context = ssl.create_default_context()
                    sock = context.wrap_socket(sock, server_hostname=self.host)
            
            # Connect
            sock.connect((self.host, self.port))
            
            # Create pooled connection
            with self._lock:
                self._connection_id_counter += 1
                conn_id = self._connection_id_counter
            
            conn = PooledConnection(
                socket=sock,
                id=conn_id
            )
            
            with self._lock:
                self._all_connections[conn_id] = conn
                self._connection_count += 1
                self._stats['created'] += 1
            
            logger.debug(f"[Pool] Created connection {conn_id}")
            return conn
            
        except Exception as e:
            logger.error(f"[Pool] Connection creation failed: {e}")
            return None
    
    def _destroy_connection(self, conn: PooledConnection):
        """Destroy a connection."""
        conn.close()
        
        with self._lock:
            if conn.id in self._all_connections:
                del self._all_connections[conn.id]
                self._connection_count -= 1
                self._stats['destroyed'] += 1
        
        logger.debug(f"[Pool] Destroyed connection {conn.id}")
    
    def acquire(self, timeout: Optional[float] = None) -> PooledConnection:
        """
        Acquire a connection from the pool.
        
        Args:
            timeout: Maximum time to wait for connection
        
        Returns:
            PooledConnection
        
        Raises:
            PoolExhaustedError: If pool is at max capacity and all connections busy
            ConnectionTimeoutError: If cannot acquire within timeout
        """
        timeout = timeout or self.acquire_timeout
        deadline = time.time() + timeout
        
        while time.time() < deadline:
            # Try to get from pool
            try:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                
                conn = self._pool.get(timeout=min(remaining, 1.0))
                
                # Validate connection if enabled
                if self.validate_on_borrow and not conn.is_healthy():
                    logger.debug(f"[Pool] Connection {conn.id} failed validation")
                    self._destroy_connection(conn)
                    with self._lock:
                        self._stats['validation_failures'] += 1
                    continue
                
                # Mark as busy
                with conn.lock:
                    conn.state = ConnectionState.BUSY
                    conn.touch()
                
                with self._lock:
                    self._stats['borrowed'] += 1
                
                logger.debug(f"[Pool] Acquired connection {conn.id}")
                return conn
                
            except queue.Empty:
                # Pool empty, try to create new connection
                with self._lock:
                    if self._connection_count < self.max_connections:
                        conn = self._create_connection()
                        if conn:
                            with conn.lock:
                                conn.state = ConnectionState.BUSY
                                conn.touch()
                            self._stats['borrowed'] += 1
                            logger.debug(f"[Pool] Created and acquired connection {conn.id}")
                            return conn
                        else:
                            # Creation failed, wait a bit
                            time.sleep(0.1)
                    else:
                        # At max capacity, wait for connection to be returned
                        with self._condition:
                            self._condition.wait(timeout=0.1)
        
        # Timeout
        with self._lock:
            self._stats['timeout_errors'] += 1
        
        raise ConnectionTimeoutError(
            f"Could not acquire connection within {timeout}s "
            f"(pool: {self._pool.qsize()}/{self._connection_count})"
        )
    
    def release(self, conn: PooledConnection, healthy: bool = True):
        """
        Return a connection to the pool.
        
        Args:
            conn: Connection to return
            healthy: Whether connection is still healthy
        """
        if not healthy:
            # Destroy unhealthy connections
            self._destroy_connection(conn)
            with self._lock:
                self._stats['validation_failures'] += 1
            return
        
        with conn.lock:
            # Check if connection is expired
            if conn.is_expired(self.max_age, self.max_idle):
                logger.debug(f"[Pool] Connection {conn.id} expired")
                self._destroy_connection(conn)
                return
            
            # Mark as idle
            conn.state = ConnectionState.IDLE
            conn.touch()
        
        # Return to pool
        try:
            self._pool.put_nowait(conn)
            with self._lock:
                self._stats['returned'] += 1
            
            # Notify waiting threads
            with self._condition:
                self._condition.notify()
            
            logger.debug(f"[Pool] Released connection {conn.id}")
            
        except queue.Full:
            # Pool is full, destroy connection
            self._destroy_connection(conn)
    
    def _maintenance_loop(self):
        """Background thread for pool maintenance."""
        while self._running:
            try:
                self._do_maintenance()
            except Exception as e:
                logger.error(f"[Pool] Maintenance error: {e}")
            
            # Sleep with interrupt check
            for _ in range(int(self.health_check_interval)):
                if not self._running:
                    break
                time.sleep(1)
    
    def _do_maintenance(self):
        """Perform pool maintenance."""
        with self._lock:
            # Check minimum connections
            current = self._connection_count
            if current < self.min_connections:
                needed = self.min_connections - current
                logger.debug(f"[Pool] Creating {needed} connections to reach minimum")
                
                for _ in range(needed):
                    if self._connection_count >= self.max_connections:
                        break
                    conn = self._create_connection()
                    if conn:
                        try:
                            self._pool.put_nowait(conn)
                        except queue.Full:
                            self._destroy_connection(conn)
            
            # Check existing connections for expiry
            to_remove = []
            for conn_id, conn in self._all_connections.items():
                if conn.state == ConnectionState.IDLE:
                    if conn.is_expired(self.max_age, self.max_idle):
                        to_remove.append(conn)
            
            # Remove expired connections
            for conn in to_remove:
                self._destroy_connection(conn)
                # Remove from pool if present
                try:
                    # Note: This is inefficient for large pools
                    # A production implementation would use a better data structure
                    temp_queue = queue.Queue()
                    removed = False
                    while not self._pool.empty():
                        try:
                            c = self._pool.get_nowait()
                            if c.id == conn.id and not removed:
                                removed = True
                                continue
                            temp_queue.put(c)
                        except queue.Empty:
                            break
                    
                    # Restore pool
                    while not temp_queue.empty():
                        self._pool.put(temp_queue.get())
                        
                except Exception as e:
                    logger.debug(f"[Pool] Error removing expired connection: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics."""
        with self._lock:
            return {
                'host': self.host,
                'port': self.port,
                'use_tls': self.use_tls,
                'min_connections': self.min_connections,
                'max_connections': self.max_connections,
                'current_connections': self._connection_count,
                'available_connections': self._pool.qsize(),
                'running': self._running,
                'stats': self._stats.copy()
            }
    
    def execute_with_connection(self, func: Callable[[socket.socket], Any], 
                                  timeout: Optional[float] = None) -> Any:
        """
        Execute a function with a pooled connection.
        
        Args:
            func: Function that takes a socket and returns a result
            timeout: Timeout for acquiring connection
        
        Returns:
            Result from func
        
        Raises:
            ConnectionPoolError: If execution fails
        """
        conn = None
        healthy = True
        
        try:
            conn = self.acquire(timeout)
            result = func(conn.socket)
            return result
            
        except (socket.error, ssl.SSLError) as e:
            # Connection error, mark as unhealthy
            healthy = False
            raise ConnectionPoolError(f"Connection error: {e}") from e
            
        except Exception as e:
            # Other errors, connection may still be healthy
            raise
            
        finally:
            if conn:
                self.release(conn, healthy=healthy)
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
        return False


class PooledClient:
    """
    Client that uses connection pooling for improved performance.
    
    Usage:
        with PooledClient(host, port) as client:
            result = client.execute("SELECT * FROM table")
    """
    
    def __init__(
        self,
        host: str = 'localhost',
        port: int = 9999,
        use_tls: bool = False,
        ssl_context: Optional[ssl.SSLContext] = None,
        pool_size: int = 5,
        **pool_kwargs
    ):
        """
        Initialize pooled client.
        
        Args:
            host: Server host
            port: Server port
            use_tls: Whether to use TLS
            ssl_context: SSL context
            pool_size: Number of connections in pool
            **pool_kwargs: Additional pool configuration
        """
        self.pool = ConnectionPool(
            host=host,
            port=port,
            use_tls=use_tls,
            ssl_context=ssl_context,
            min_connections=1,
            max_connections=pool_size,
            **pool_kwargs
        )
        self._lock = threading.RLock()
    
    def start(self):
        """Start the client and pool."""
        self.pool.start()
    
    def stop(self):
        """Stop the client and pool."""
        self.pool.stop()
    
    def execute(self, command: str, timeout: Optional[float] = None) -> str:
        """
        Execute a command using pooled connection.
        
        Args:
            command: Command to execute
            timeout: Timeout for operation
        
        Returns:
            Server response
        """
        def send_and_receive(sock: socket.socket) -> str:
            sock.sendall(command.encode() + b'\n')
            response = sock.recv(16384).decode().strip()
            return response
        
        return self.pool.execute_with_connection(send_and_receive, timeout)
    
    def execute_batch(self, commands: List[str], 
                      timeout: Optional[float] = None) -> List[str]:
        """
        Execute multiple commands efficiently using pooled connections.
        
        Args:
            commands: List of commands
            timeout: Timeout per command
        
        Returns:
            List of responses
        """
        results = []
        
        for cmd in commands:
            try:
                result = self.execute(cmd, timeout)
                results.append(result)
            except Exception as e:
                results.append(f"ERROR: {e}")
        
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics."""
        return self.pool.get_stats()
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
        return False


# Convenience functions
def create_connection_pool(
    host: str = 'localhost',
    port: int = 9999,
    size: int = 5,
    use_tls: bool = False
) -> ConnectionPool:
    """
    Create a connection pool with sensible defaults.
    
    Args:
        host: Server host
        port: Server port
        size: Pool size
        use_tls: Whether to use TLS
    
    Returns:
        Configured ConnectionPool
    """
    pool = ConnectionPool(
        host=host,
        port=port,
        min_connections=1,
        max_connections=size,
        use_tls=use_tls
    )
    pool.start()
    return pool
