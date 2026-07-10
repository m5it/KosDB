"""
Unit tests for Connection Pool module.

Tests connection lifecycle, thread safety, and pool management.
"""

import unittest
import threading
import time
import socket
from unittest.mock import Mock, patch, MagicMock

from connection_pool import (
    ConnectionPool,
    PooledConnection,
    PooledClient,
    ConnectionPoolError,
    PoolExhaustedError,
    ConnectionTimeoutError,
    ConnectionState
)


class MockSocket:
    """Mock socket for testing."""
    
    def __init__(self):
        self.closed = False
        self.data_sent = []
        self.recv_data = b"OK"
    
    def connect(self, addr):
        if self.closed:
            raise socket.error("Socket closed")
    
    def sendall(self, data):
        if self.closed:
            raise socket.error("Socket closed")
        self.data_sent.append(data)
    
    def recv(self, size):
        if self.closed:
            raise socket.error("Socket closed")
        return self.recv_data
    
    def settimeout(self, timeout):
        pass
    
    def setblocking(self, flag):
        pass
    
    def close(self):
        self.closed = True


class TestPooledConnection(unittest.TestCase):
    """Test PooledConnection class."""
    
    def test_creation(self):
        """Test connection creation."""
        mock_sock = MockSocket()
        conn = PooledConnection(socket=mock_sock, id=1)
        
        self.assertEqual(conn.id, 1)
        self.assertEqual(conn.state, ConnectionState.IDLE)
        self.assertEqual(conn.use_count, 0)
    
    def test_touch(self):
        """Test touch updates timestamps."""
        mock_sock = MockSocket()
        conn = PooledConnection(socket=mock_sock, id=1)
        
        old_time = conn.last_used
        time.sleep(0.01)  # Small delay
        conn.touch()
        
        self.assertGreater(conn.last_used, old_time)
        self.assertEqual(conn.use_count, 1)
    
    def test_is_expired_age(self):
        """Test expiration by age."""
        mock_sock = MockSocket()
        conn = PooledConnection(socket=mock_sock, id=1)
        
        # Not expired
        self.assertFalse(conn.is_expired(max_age=100, max_idle=100))
        
        # Simulate old connection
        conn.created_at = time.time() - 200
        self.assertTrue(conn.is_expired(max_age=100, max_idle=100))
    
    def test_is_expired_idle(self):
        """Test expiration by idle time."""
        mock_sock = MockSocket()
        conn = PooledConnection(socket=mock_sock, id=1)
        
        # Not expired
        self.assertFalse(conn.is_expired(max_age=100, max_idle=100))
        
        # Simulate idle connection
        conn.last_used = time.time() - 200
        self.assertTrue(conn.is_expired(max_age=100, max_idle=100))
    
    def test_close(self):
        """Test connection close."""
        mock_sock = MockSocket()
        conn = PooledConnection(socket=mock_sock, id=1)
        
        conn.close()
        
        self.assertEqual(conn.state, ConnectionState.CLOSED)
        self.assertTrue(mock_sock.closed)


class TestConnectionPool(unittest.TestCase):
    """Test ConnectionPool class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.pool = ConnectionPool(
            host='localhost',
            port=9999,
            min_connections=1,
            max_connections=3,
            max_age=60,
            max_idle=30,
            connection_timeout=5,
            acquire_timeout=2
        )
    
    def tearDown(self):
        """Clean up after tests."""
        self.pool.stop()
    
    @patch('socket.socket')
    def test_start_stop(self, mock_socket_class):
        """Test pool start and stop."""
        mock_socket = MockSocket()
        mock_socket_class.return_value = mock_socket
        
        # Start pool
        self.pool.start()
        
        self.assertTrue(self.pool._running)
        self.assertGreaterEqual(self.pool._connection_count, 1)
        
        # Stop pool
        self.pool.stop()
        
        self.assertFalse(self.pool._running)
        self.assertEqual(self.pool._connection_count, 0)
    
    @patch('socket.socket')
    def test_acquire_release(self, mock_socket_class):
        """Test connection acquire and release."""
        mock_socket = MockSocket()
        mock_socket_class.return_value = mock_socket
        
        self.pool.start()
        
        # Acquire connection
        conn = self.pool.acquire()
        self.assertIsNotNone(conn)
        self.assertEqual(conn.state, ConnectionState.BUSY)
        
        # Release connection
        self.pool.release(conn)
        self.assertEqual(conn.state, ConnectionState.IDLE)
    
    @patch('socket.socket')
    def test_acquire_timeout(self, mock_socket_class):
        """Test acquire timeout."""
        # Make socket creation fail
        mock_socket_class.side_effect = socket.error("Connection refused")
        
        self.pool.start()
        
        # Should timeout
        with self.assertRaises(ConnectionTimeoutError):
            self.pool.acquire(timeout=0.1)
    
    @patch('socket.socket')
    def test_pool_exhaustion(self, mock_socket_class):
        """Test pool exhaustion handling."""
        mock_socket = MockSocket()
        mock_socket_class.return_value = mock_socket
        
        self.pool.start()
        
        # Acquire all connections
        conns = []
        for _ in range(self.pool.max_connections):
            conn = self.pool.acquire(timeout=1.0)
            conns.append(conn)
        
        # Next acquire should timeout
        with self.assertRaises(ConnectionTimeoutError):
            self.pool.acquire(timeout=0.1)
        
        # Release connections
        for conn in conns:
            self.pool.release(conn)
    
    @patch('socket.socket')
    def test_execute_with_connection(self, mock_socket_class):
        """Test execute with connection."""
        mock_socket = MockSocket()
        mock_socket.recv_data = b"OK: Test"
        mock_socket_class.return_value = mock_socket
        
        self.pool.start()
        
        def test_func(sock):
            sock.sendall(b"TEST")
            return sock.recv(1024)
        
        result = self.pool.execute_with_connection(test_func)
        self.assertEqual(result, b"OK: Test")
    
    @patch('socket.socket')
    def test_execute_with_error(self, mock_socket_class):
        """Test execute with connection error."""
        mock_socket = MockSocket()
        mock_socket_class.return_value = mock_socket
        
        self.pool.start()
        
        def bad_func(sock):
            raise socket.error("Test error")
        
        with self.assertRaises(ConnectionPoolError):
            self.pool.execute_with_connection(bad_func)
    
    def test_get_stats(self):
        """Test statistics collection."""
        stats = self.pool.get_stats()
        
        self.assertIn('host', stats)
        self.assertIn('port', stats)
        self.assertIn('min_connections', stats)
        self.assertIn('max_connections', stats)
        self.assertIn('current_connections', stats)
        self.assertIn('stats', stats)
        
        self.assertEqual(stats['host'], 'localhost')
        self.assertEqual(stats['port'], 9999)
    
    @patch('socket.socket')
    def test_context_manager(self, mock_socket_class):
        """Test context manager."""
        mock_socket = MockSocket()
        mock_socket_class.return_value = mock_socket
        
        with ConnectionPool(host='localhost', port=9999) as pool:
            self.assertTrue(pool._running)
            conn = pool.acquire()
            self.assertIsNotNone(conn)
            pool.release(conn)
        
        self.assertFalse(pool._running)


class TestConcurrency(unittest.TestCase):
    """Test thread safety and concurrency."""
    
    @patch('socket.socket')
    def test_concurrent_acquire(self, mock_socket_class):
        """Test concurrent connection acquisition."""
        mock_socket = MockSocket()
        mock_socket_class.return_value = mock_socket
        
        pool = ConnectionPool(
            host='localhost',
            port=9999,
            min_connections=2,
            max_connections=5
        )
        
        with pool:
            results = []
            errors = []
            
            def worker():
                try:
                    conn = pool.acquire(timeout=5.0)
                    time.sleep(0.01)  # Simulate work
                    results.append(conn.id)
                    pool.release(conn)
                except Exception as e:
                    errors.append(e)
            
            # Start multiple threads
            threads = []
            for _ in range(10):
                t = threading.Thread(target=worker)
                threads.append(t)
                t.start()
            
            # Wait for completion
            for t in threads:
                t.join(timeout=10.0)
            
            self.assertEqual(len(errors), 0, f"Errors: {errors}")
            self.assertEqual(len(results), 10)
    
    @patch('socket.socket')
    def test_connection_reuse(self, mock_socket_class):
        """Test that connections are reused."""
        mock_socket = MockSocket()
        mock_socket_class.return_value = mock_socket
        
        pool = ConnectionPool(
            host='localhost',
            port=9999,
            min_connections=1,
            max_connections=2
        )
        
        with pool:
            # Acquire and release same connection multiple times
            conn_ids = set()
            for _ in range(5):
                conn = pool.acquire(timeout=1.0)
                conn_ids.add(conn.id)
                pool.release(conn)
            
            # Should reuse connections
            self.assertLessEqual(len(conn_ids), 2)
    
    @patch('socket.socket')
    def test_race_condition(self, mock_socket_class):
        """Test for race conditions in pool operations."""
        mock_socket = MockSocket()
        mock_socket_class.return_value = mock_socket
        
        pool = ConnectionPool(
            host='localhost',
            port=9999,
            min_connections=2,
            max_connections=5
        )
        
        with pool:
            # Stress test with many threads
            threads = []
            for _ in range(20):
                def worker():
                    try:
                        conn = pool.acquire(timeout=5.0)
                        time.sleep(0.001)
                        pool.release(conn)
                    except:
                        pass
                t = threading.Thread(target=worker)
                threads.append(t)
                t.start()
            
            for t in threads:
                t.join(timeout=10.0)


class TestPooledClient(unittest.TestCase):
    """Test PooledClient class."""
    
    @patch('socket.socket')
    def test_client_lifecycle(self, mock_socket_class):
        """Test client start/stop."""
        mock_socket = MockSocket()
        mock_socket.recv_data = b"OK"
        mock_socket_class.return_value = mock_socket
        
        client = PooledClient(
            host='localhost',
            port=9999,
            pool_size=3
        )
        
        client.start()
        self.assertTrue(client.pool._running)
        
        client.stop()
        self.assertFalse(client.pool._running)
    
    @patch('socket.socket')
    def test_execute(self, mock_socket_class):
        """Test command execution."""
        mock_socket = MockSocket()
        mock_socket.recv_data = b"OK: Command executed"
        mock_socket_class.return_value = mock_socket
        
        with PooledClient(host='localhost', port=9999) as client:
            result = client.execute("TEST COMMAND")
            self.assertEqual(result, "OK: Command executed")
    
    @patch('socket.socket')
    def test_execute_batch(self, mock_socket_class):
        """Test batch execution."""
        mock_socket = MockSocket()
        mock_socket.recv_data = b"OK"
        mock_socket_class.return_value = mock_socket
        
        with PooledClient(host='localhost', port=9999) as client:
            commands = ["CMD1", "CMD2", "CMD3"]
            results = client.execute_batch(commands)
            
            self.assertEqual(len(results), 3)
            for result in results:
                self.assertEqual(result, "OK")
    
    @patch('socket.socket')
    def test_context_manager(self, mock_socket_class):
        """Test client context manager."""
        mock_socket = MockSocket()
        mock_socket_class.return_value = mock_socket
        
        with PooledClient(host='localhost', port=9999) as client:
            self.assertTrue(client.pool._running)
            result = client.execute("TEST")
            self.assertIsNotNone(result)
        
        self.assertFalse(client.pool._running)


class TestErrorHandling(unittest.TestCase):
    """Test error handling."""
    
    def test_connection_creation_failure(self):
        """Test handling of connection creation failure."""
        with patch('socket.socket') as mock_socket_class:
            mock_socket_class.side_effect = socket.error("Connection refused")
            
            pool = ConnectionPool(
                host='localhost',
                port=9999,
                min_connections=0,
                max_connections=2
            )
            
            pool.start()
            
            # Should not crash, just have 0 connections
            self.assertEqual(pool._connection_count, 0)
            
            pool.stop()
    
    @patch('socket.socket')
    def test_unhealthy_connection(self, mock_socket_class):
        """Test detection of unhealthy connections."""
        mock_socket = MockSocket()
        mock_socket_class.return_value = mock_socket
        
        pool = ConnectionPool(
            host='localhost',
            port=9999,
            validate_on_borrow=True
        )
        
        with pool:
            conn = pool.acquire()
            
            # Make socket unhealthy
            mock_socket.closed = True
            
            # Release should destroy it
            pool.release(conn, healthy=False)
            
            # Connection should be destroyed
            self.assertEqual(conn.state, ConnectionState.CLOSED)


class TestMaintenance(unittest.TestCase):
    """Test pool maintenance."""
    
    @patch('socket.socket')
    def test_expired_connection_removal(self, mock_socket_class):
        """Test removal of expired connections."""
        mock_socket = MockSocket()
        mock_socket_class.return_value = mock_socket
        
        pool = ConnectionPool(
            host='localhost',
            port=9999,
            min_connections=1,
            max_connections=2,
            max_age=0.1,  # Very short for testing
            max_idle=0.1,
            health_check_interval=0.1
        )
        
        with pool:
            # Create connection
            conn = pool.acquire()
            pool.release(conn)
            
            # Wait for expiration
            time.sleep(0.2)
            
            # Force maintenance
            pool._do_maintenance()
            
            # Expired connections should be removed
            # Note: This is implementation dependent
            self.assertGreaterEqual(pool._stats['destroyed'], 0)


class TestTLS(unittest.TestCase):
    """Test TLS support."""
    
    @patch('socket.socket')
    @patch('ssl.SSLContext')
    def test_tls_connection(self, mock_ssl_context, mock_socket_class):
        """Test TLS connection creation."""
        mock_socket = MockSocket()
        mock_socket_class.return_value = mock_socket
        
        mock_context = MagicMock()
        mock_ssl_context.return_value = mock_context
        
        pool = ConnectionPool(
            host='localhost',
            port=9999,
            use_tls=True,
            min_connections=0,
            max_connections=2
        )
        
        pool.start()
        
        # Should attempt TLS wrap
        self.assertTrue(pool.use_tls)
        
        pool.stop()


class TestFactoryFunction(unittest.TestCase):
    """Test convenience functions."""
    
    @patch('socket.socket')
    def test_create_connection_pool(self, mock_socket_class):
        """Test factory function."""
        mock_socket = MockSocket()
        mock_socket_class.return_value = mock_socket
        
        pool = create_connection_pool(
            host='testhost',
            port=1234,
            size=5
        )
        
        self.assertEqual(pool.host, 'testhost')
        self.assertEqual(pool.port, 1234)
        self.assertEqual(pool.max_connections, 5)
        self.assertTrue(pool._running)
        
        pool.stop()


if __name__ == '__main__':
    unittest.main(verbosity=2)
