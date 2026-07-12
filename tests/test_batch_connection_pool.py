
"""
Tests for Batch Connection Pool

Tests:
- Pool limit enforcement
- Batch connection affinity
- Pool exhaustion handling
- Wait timeouts
- Metrics collection
- Batch status reporting
"""

import unittest
import sys
import os
import time
import threading

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from batch_connection_pool import (
    BatchConnectionPool,
    BatchConnectionPoolManager,
    PooledConnection,
    PoolMetrics
)


class MockConnection:
    """Mock database connection."""
    
    _id_counter = 0
    _lock = threading.Lock()
    
    def __init__(self):
        with MockConnection._lock:
            MockConnection._id_counter += 1
            self.id = MockConnection._id_counter
        self.connected = True
        self.queries = []
    
    def execute(self, query):
        """Execute query."""
        self.queries.append(query)
        return f"Result of {query}"
    
    def is_connected(self):
        """Check if connected."""
        return self.connected
    
    def close(self):
        """Close connection."""
        self.connected = False


class TestBatchConnectionPool(unittest.TestCase):
    """Test suite for batch connection pool."""
    
    def setUp(self):
        """Set up test pool."""
        MockConnection._id_counter = 0
        
        def factory():
            return MockConnection()
        
        self.pool = BatchConnectionPool(
            min_connections=1,
            max_connections=5,
            max_batch_connections=3,
            pool_wait_timeout_ms=1000,
            connection_timeout_ms=5000,
            idle_timeout_ms=30000,
            connection_factory=factory
        )
    
    def tearDown(self):
        """Clean up pool."""
        self.pool.close()
    
    def test_pool_initialization(self):
        """Test pool initializes with minimum connections."""
        metrics = self.pool.get_metrics()
        self.assertGreaterEqual(metrics['total_connections'], 1)
    
    def test_acquire_release(self):
        """Test basic acquire and release."""
        conn = self.pool.acquire()
        self.assertIsNotNone(conn)
        self.assertIn(conn, self.pool._active)
        
        self.pool.release(conn)
        self.assertNotIn(conn, self.pool._active)
    
    def test_connection_context_manager(self):
        """Test context manager for connections."""
        with self.pool.connection() as conn:
            self.assertIn(conn, self.pool._active)
            result = conn.connection.execute("SELECT 1")
            self.assertEqual(result, "Result of SELECT 1")
        
        self.assertNotIn(conn, self.pool._active)
    
    def test_batch_connection_affinity(self):
        """Test batch connections stay consistent."""
        batch_id = "batch_001"
        
        conn1 = self.pool.acquire(for_batch=True, batch_id=batch_id)
        conn2 = self.pool.acquire(for_batch=True, batch_id=batch_id)
        
        self.assertEqual(conn1, conn2)
        
        self.pool.release_batch(batch_id)
    
    def test_pool_limits_enforced(self):
        """Test pool respects max connections."""
        connections = []
        
        for _ in range(5):
            conn = self.pool.acquire()
            connections.append(conn)
        
        with self.assertRaises(TimeoutError):
            self.pool.acquire(timeout_ms=100)
        
        for conn in connections:
            self.pool.release(conn)
    
    def test_batch_connection_limits(self):
        """Test batch connection limits."""
        batch_ids = ["batch_001", "batch_002", "batch_003", "batch_004"]
        
        conns = []
        for batch_id in batch_ids[:3]:
            conn = self.pool.acquire(for_batch=True, batch_id=batch_id)
            conns.append((batch_id, conn))
        
        with self.assertRaises(TimeoutError):
            self.pool.acquire(for_batch=True, batch_id=batch_ids[3])
        
        for batch_id, conn in conns:
            self.pool.release_batch(batch_id)
    
    def test_wait_timeout(self):
        """Test wait timeout."""
        connections = []
        
        for _ in range(5):
            conn = self.pool.acquire()
            connections.append(conn)
        
        start = time.time()
        with self.assertRaises(TimeoutError):
            self.pool.acquire(timeout_ms=100)
        elapsed = (time.time() - start) * 1000
        
        self.assertLess(elapsed, 200)
        
        for conn in connections:
            self.pool.release(conn)
    
    def test_metrics_collection(self):
        """Test metrics are collected."""
        metrics = self.pool.get_metrics()
        self.assertIn('total_connections', metrics)
        self.assertIn('active_connections', metrics)
        
        conn = self.pool.acquire()
        metrics = self.pool.get_metrics()
        self.assertEqual(metrics['active_connections'], 1)
        
        self.pool.release(conn)
        metrics = self.pool.get_metrics()
        self.assertEqual(metrics['active_connections'], 0)
    
    def test_pool_status_output(self):
        """Test status output format."""
        status = self.pool.get_status()
        self.assertIn("BATCH CONNECTION POOL STATUS", status)
        self.assertIn("Total Connections:", status)
    
    def test_connection_health_check(self):
        """Test unhealthy connections are removed."""
        conn = self.pool.acquire()
        conn.connection.connected = False
        self.pool.release(conn)
        self.assertEqual(len(self.pool._pool), 0)
    
    def test_concurrent_access(self):
        """Test concurrent access to pool."""
        results = []
        errors = []
        
        def worker():
            try:
                with self.pool.connection() as conn:
                    time.sleep(0.01)
                    results.append(conn.connection.id)
            except Exception as e:
                errors.append(str(e))
        
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(results), 10)
    
    def test_batch_release_on_complete(self):
        """Test batch connections released on complete."""
        batch_id = "batch_002"
        
        conn = self.pool.acquire(for_batch=True, batch_id=batch_id)
        self.assertTrue(conn.in_batch)
        
        self.pool.release_batch(batch_id)
        
        self.assertFalse(conn.in_batch)
        self.assertIsNone(conn.batch_id)


class TestBatchConnectionPoolManager(unittest.TestCase):
    """Test pool manager."""
    
    def setUp(self):
        self.manager = BatchConnectionPoolManager()
    
    def tearDown(self):
        self.manager.close_all()
    
    def test_create_pool(self):
        def factory():
            return MockConnection()
        
        pool = self.manager.create_pool(
            name="test_pool",
            connection_factory=factory,
            min_connections=1,
            max_connections=3
        )
        
        self.assertIsNotNone(pool)
        self.assertEqual(self.manager.get_pool("test_pool"), pool)
    
    def test_duplicate_pool_name(self):
        def factory():
            return MockConnection()
        
        self.manager.create_pool(name="dup_pool", connection_factory=factory)
        
        with self.assertRaises(ValueError):
            self.manager.create_pool(name="dup_pool", connection_factory=factory)
    
    def test_remove_pool(self):
        def factory():
            return MockConnection()
        
        self.manager.create_pool(name="removable", connection_factory=factory)
        self.manager.remove_pool("removable")
        self.assertIsNone(self.manager.get_pool("removable"))
    
    def test_all_metrics(self):
        def factory():
            return MockConnection()
        
        self.manager.create_pool(name="pool1", connection_factory=factory)
        self.manager.create_pool(name="pool2", connection_factory=factory)
        
        metrics = self.manager.get_all_metrics()
        self.assertIn("pool1", metrics)
        self.assertIn("pool2", metrics)
    
    def test_all_status(self):
        def factory():
            return MockConnection()
        
        self.manager.create_pool(name="status_pool", connection_factory=factory)
        status = self.manager.get_all_status()
        self.assertIn("status_pool", status)


class TestPoolMetrics(unittest.TestCase):
    """Test pool metrics."""
    
    def test_metrics_initialization(self):
        metrics = PoolMetrics()
        self.assertEqual(metrics.total_connections, 0)
        self.assertEqual(metrics.active_connections, 0)
    
    def test_utilization_calculation(self):
        pool = BatchConnectionPool(
            min_connections=1,
            max_connections=10,
            connection_factory=lambda: MockConnection()
        )
        
        conns = []
        for _ in range(5):
            conns.append(pool.acquire())
        
        metrics = pool.get_metrics()
        self.assertEqual(metrics['utilization_percent'], 50.0)
        
        for conn in conns:
            pool.release(conn)
        
        pool.close()


class TestPoolExhaustion(unittest.TestCase):
    """Test pool exhaustion scenarios."""
    
    def setUp(self):
        def factory():
            return MockConnection()
        
        self.pool = BatchConnectionPool(
            min_connections=1,
            max_connections=2,
            pool_wait_timeout_ms=500,
            connection_factory=factory
        )
    
    def tearDown(self):
        self.pool.close()
    
    def test_exhaustion_metrics(self):
        conn1 = self.pool.acquire()
        conn2 = self.pool.acquire()
        
        try:
            self.pool.acquire(timeout_ms=100)
        except TimeoutError:
            pass
        
        metrics = self.pool.get_metrics()
        self.assertGreaterEqual(metrics['pool_exhaustion_events'], 1)
        
        self.pool.release(conn1)
        self.pool.release(conn2)
    
    def test_graceful_degradation(self):
        conn1 = self.pool.acquire()
        conn2 = self.pool.acquire()
        
        with self.assertRaises(TimeoutError) as ctx:
            self.pool.acquire(timeout_ms=100)
        
        self.assertIn("Could not acquire connection", str(ctx.exception))
        
        self.pool.release(conn1)
        self.pool.release(conn2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
