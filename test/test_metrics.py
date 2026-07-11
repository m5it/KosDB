"""
Test Metrics Collection for KosDB v3.2.0

Tests:
- Counter metrics
- Gauge metrics
- Histogram metrics
- Prometheus format export
- Metrics registry
- KosDB-specific metrics
- HTTP endpoints
"""

import unittest
import sys
import os
import time
import threading

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from metrics import (
    Counter, Gauge, Histogram, MetricsRegistry, KosDBMetrics,
    get_metrics, reset_metrics
)


class TestCounter(unittest.TestCase):
    """Test Counter metric."""
    
    def setUp(self):
        self.counter = Counter("test_counter", "Test counter", ["label1"])
    
    def test_counter_inc(self):
        """Test counter increment."""
        self.counter.inc(1, {"label1": "value1"})
        self.assertEqual(self.counter.get({"label1": "value1"}), 1)
        
        self.counter.inc(2, {"label1": "value1"})
        self.assertEqual(self.counter.get({"label1": "value1"}), 3)
    
    def test_counter_default_labels(self):
        """Test counter with no labels."""
        counter = Counter("simple_counter", "Simple counter")
        counter.inc(5)
        self.assertEqual(counter.get(), 5)
    
    def test_counter_prometheus_format(self):
        """Test Prometheus format export."""
        self.counter.inc(10, {"label1": "a"})
        self.counter.inc(20, {"label1": "b"})
        
        output = self.counter.to_prometheus()
        
        self.assertIn("# HELP test_counter Test counter", output)
        self.assertIn("# TYPE test_counter counter", output)
        self.assertIn('test_counter{label1="a"} 10', output)
        self.assertIn('test_counter{label1="b"} 20', output)


class TestGauge(unittest.TestCase):
    """Test Gauge metric."""
    
    def setUp(self):
        self.gauge = Gauge("test_gauge", "Test gauge", ["env"])
    
    def test_gauge_set(self):
        """Test gauge set."""
        self.gauge.set(100, {"env": "prod"})
        self.assertEqual(self.gauge.get({"env": "prod"}), 100)
        
        self.gauge.set(200, {"env": "prod"})
        self.assertEqual(self.gauge.get({"env": "prod"}), 200)
    
    def test_gauge_inc_dec(self):
        """Test gauge increment and decrement."""
        self.gauge.set(100, {"env": "dev"})
        
        self.gauge.inc(10, {"env": "dev"})
        self.assertEqual(self.gauge.get({"env": "dev"}), 110)
        
        self.gauge.dec(20, {"env": "dev"})
        self.assertEqual(self.gauge.get({"env": "dev"}), 90)
    
    def test_gauge_negative(self):
        """Test gauge can be negative."""
        self.gauge.set(-50, {"env": "test"})
        self.assertEqual(self.gauge.get({"env": "test"}), -50)
    
    def test_gauge_prometheus_format(self):
        """Test Prometheus format export."""
        self.gauge.set(42, {"env": "prod"})
        
        output = self.gauge.to_prometheus()
        
        self.assertIn("# HELP test_gauge Test gauge", output)
        self.assertIn("# TYPE test_gauge gauge", output)
        self.assertIn('test_gauge{env="prod"} 42', output)


class TestHistogram(unittest.TestCase):
    """Test Histogram metric."""
    
    def setUp(self):
        self.histogram = Histogram(
            "test_histogram",
            "Test histogram",
            ["method"],
            buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0]
        )
    
    def test_histogram_observe(self):
        """Test histogram observe."""
        self.histogram.observe(0.05, {"method": "GET"})
        self.histogram.observe(0.3, {"method": "GET"})
        self.histogram.observe(1.5, {"method": "GET"})
        
        # Check buckets
        key = self.histogram._make_key({"method": "GET"})
        self.assertEqual(self.histogram.buckets_data[key][0.1], 1)
        self.assertEqual(self.histogram.buckets_data[key][0.5], 2)
        self.assertEqual(self.histogram.buckets_data[key][1.0], 2)
        self.assertEqual(self.histogram.buckets_data[key][2.5], 3)
    
    def test_histogram_sum_and_count(self):
        """Test histogram sum and count."""
        self.histogram.observe(0.1, {"method": "POST"})
        self.histogram.observe(0.2, {"method": "POST"})
        self.histogram.observe(0.3, {"method": "POST"})
        
        key = self.histogram._make_key({"method": "POST"})
        self.assertEqual(self.histogram.sums[key], 0.6)
        self.assertEqual(self.histogram.counts[key], 3)
    
    def test_histogram_prometheus_format(self):
        """Test Prometheus format export."""
        self.histogram.observe(0.5, {"method": "GET"})
        
        output = self.histogram.to_prometheus()
        
        self.assertIn("# HELP test_histogram Test histogram", output)
        self.assertIn("# TYPE test_histogram histogram", output)
        self.assertIn("test_histogram_bucket", output)
        self.assertIn("test_histogram_sum", output)
        self.assertIn("test_histogram_count", output)


class TestMetricsRegistry(unittest.TestCase):
    """Test MetricsRegistry."""
    
    def setUp(self):
        self.registry = MetricsRegistry()
    
    def test_registry_counter(self):
        """Test registry counter creation."""
        counter = self.registry.counter("requests", "Total requests", ["status"])
        self.assertIsInstance(counter, Counter)
        
        # Get same counter again
        counter2 = self.registry.counter("requests", "Total requests", ["status"])
        self.assertIs(counter, counter2)
    
    def test_registry_gauge(self):
        """Test registry gauge creation."""
        gauge = self.registry.gauge("temperature", "Current temperature")
        self.assertIsInstance(gauge, Gauge)
    
    def test_registry_histogram(self):
        """Test registry histogram creation."""
        hist = self.registry.histogram("latency", "Request latency")
        self.assertIsInstance(hist, Histogram)
    
    def test_registry_prometheus_export(self):
        """Test full registry export."""
        counter = self.registry.counter("total", "Total")
        counter.inc(10)
        
        gauge = self.registry.gauge("current", "Current")
        gauge.set(5)
        
        output = self.registry.to_prometheus()
        
        self.assertIn("total", output)
        self.assertIn("current", output)
    
    def test_registry_get_metric(self):
        """Test getting metric by name."""
        self.registry.counter("test", "Test")
        
        metric = self.registry.get_metric("test")
        self.assertIsNotNone(metric)
        
        missing = self.registry.get_metric("nonexistent")
        self.assertIsNone(missing)


class TestKosDBMetrics(unittest.TestCase):
    """Test KosDB-specific metrics."""
    
    def setUp(self):
        reset_metrics()
        self.metrics = get_metrics()
    
    def test_query_metrics(self):
        """Test query recording."""
        self.metrics.record_query("SELECT", 0.05, True)
        self.metrics.record_query("INSERT", 0.1, True)
        self.metrics.record_query("SELECT", 0.2, False)
        
        # Check counters
        select_success = self.metrics.query_total.get({
            "command": "SELECT", "status": "success"
        })
        self.assertEqual(select_success, 1)
        
        select_error = self.metrics.query_total.get({
            "command": "SELECT", "status": "error"
        })
        self.assertEqual(select_error, 1)
    
    def test_cache_metrics(self):
        """Test cache metrics."""
        self.metrics.record_cache_hit("plan")
        self.metrics.record_cache_hit("plan")
        self.metrics.record_cache_miss("plan")
        
        hits = self.metrics.cache_hits.get({"cache_type": "plan"})
        misses = self.metrics.cache_misses.get({"cache_type": "plan"})
        
        self.assertEqual(hits, 2)
        self.assertEqual(misses, 1)
    
    def test_connection_metrics(self):
        """Test connection metrics."""
        self.metrics.record_connection_opened()
        self.metrics.record_connection_opened()
        self.metrics.record_connection_closed()
        
        active = self.metrics.connections_active.get()
        total = self.metrics.connections_total.get()
        
        self.assertEqual(active, 1)
        self.assertEqual(total, 2)
    
    def test_error_metrics(self):
        """Test error recording."""
        self.metrics.record_error("syntax")
        self.metrics.record_error("syntax")
        self.metrics.record_error("connection")
        
        syntax_errors = self.metrics.errors_total.get({"type": "syntax"})
        conn_errors = self.metrics.errors_total.get({"type": "connection"})
        
        self.assertEqual(syntax_errors, 2)
        self.assertEqual(conn_errors, 1)
    
    def test_prometheus_export(self):
        """Test full Prometheus export."""
        # Generate some metrics
        self.metrics.record_query("SELECT", 0.1, True)
        self.metrics.record_cache_hit("plan")
        self.metrics.record_connection_opened()
        
        output = self.metrics.get_prometheus_metrics()
        
        self.assertIn("kosdb_queries_total", output)
        self.assertIn("kosdb_cache_hits_total", output)
        self.assertIn("kosdb_connections_active", output)
        self.assertIn("# HELP", output)
        self.assertIn("# TYPE", output)


class TestMetricsEdgeCases(unittest.TestCase):
    """Test edge cases."""
    
    def test_empty_labels(self):
        """Test metrics with empty labels."""
        counter = Counter("test", "Test", ["a", "b"])
        counter.inc(1, {"a": "x", "b": ""})
        counter.inc(1, {"a": "x"})
        
        # Should be treated as same key
        self.assertEqual(counter.get({"a": "x", "b": ""}), 2)
    
    def test_thread_safety(self):
        """Test basic thread safety."""
        counter = Counter("thread_test", "Thread test")
        
        def increment():
            for _ in range(100):
                counter.inc()
        
        threads = [threading.Thread(target=increment) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        self.assertEqual(counter.get(), 500)
    
    def test_histogram_large_values(self):
        """Test histogram with large values."""
        hist = Histogram("large", "Large values")
        hist.observe(1000.0)
        hist.observe(10000.0)
        
        # Should go into +Inf bucket
        key = hist._make_key(None)
        self.assertEqual(hist.buckets_data[key][float('inf')], 2)
    
    def test_histogram_zero_values(self):
        """Test histogram with zero."""
        hist = Histogram("zero", "Zero values")
        hist.observe(0.0)
        
        key = hist._make_key(None)
        # Should be in first bucket
        first_bucket = hist.buckets[0]
        self.assertEqual(hist.buckets_data[key][first_bucket], 1)


class TestMetricsServer(unittest.TestCase):
    """Test metrics HTTP server."""
    
    def setUp(self):
        try:
            from metrics_server import MetricsServer, HealthStatus, ServerStatus
            self.server_class = MetricsServer
            self.has_server = True
        except ImportError:
            self.has_server = False
    
    def test_server_creation(self):
        """Test metrics server creation."""
        if not self.has_server:
            self.skipTest("Metrics server not available")
        
        server = self.server_class(host="127.0.0.1", port=19090)
        self.assertEqual(server.host, "127.0.0.1")
        self.assertEqual(server.port, 19090)
    
    def test_health_status(self):
        """Test health status creation."""
        if not self.has_server:
            self.skipTest("Metrics server not available")
        
        from metrics_server import HealthStatus
        
        health = HealthStatus(
            status="healthy",
            checks={"database": {"status": "ok"}},
            timestamp=time.time()
        )
        
        self.assertEqual(health.status, "healthy")
        self.assertIn("database", health.checks)


if __name__ == '__main__':
    unittest.main(verbosity=2)
