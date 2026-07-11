#!/usr/bin/env python3
"""Unit tests for the monitoring module."""

import unittest
from monitoring import (
    MetricsRegistry,
    HealthChecker,
    MonitoringCommands,
    MetricType
)


class TestMetricsRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = MetricsRegistry()

    def test_counter(self):
        self.registry.increment_counter('queries.total', 1, {'type': 'SELECT'})
        self.assertEqual(self.registry.get_counter('queries.total', {'type': 'SELECT'}), 1)
        self.registry.increment_counter('queries.total', 2, {'type': 'SELECT'})
        self.assertEqual(self.registry.get_counter('queries.total', {'type': 'SELECT'}), 3)

    def test_gauge(self):
        self.registry.set_gauge('connections.active', 5)
        self.assertEqual(self.registry.get_gauge('connections.active'), 5)

    def test_histogram_stats(self):
        for v in [1, 2, 3, 4, 5]:
            self.registry.record_histogram('latency', v)
        stats = self.registry.get_histogram_stats('latency')
        self.assertEqual(stats['count'], 5)
        self.assertEqual(stats['min'], 1)
        self.assertEqual(stats['max'], 5)

    def test_record_timer(self):
        self.registry.record_timer('query_time', 0.123)
        stats = self.registry.get_histogram_stats('query_time')
        self.assertEqual(stats['count'], 1)

    def test_get_all_metrics(self):
        self.registry.increment_counter('c', 1)
        self.registry.set_gauge('g', 2)
        self.registry.record_histogram('h', 3)
        all_metrics = self.registry.get_all_metrics()
        self.assertIn('c', all_metrics['counters'])
        self.assertIn('g', all_metrics['gauges'])
        self.assertIn('h', all_metrics['histograms'])

    def test_export_prometheus(self):
        self.registry.increment_counter('queries_total', 5)
        self.registry.set_gauge('active', 3)
        self.registry.record_histogram('latency', 0.1)
        output = self.registry.export_prometheus()
        self.assertIn('queries_total', output)
        self.assertIn('active', output)
        self.assertIn('latency_count', output)

    def test_callback(self):
        received = []
        def cb(metric):
            received.append(metric)
        self.registry.register_callback(cb)
        self.registry.set_gauge('x', 1)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].name, 'x')


class TestHealthChecker(unittest.TestCase):
    def setUp(self):
        self.checker = HealthChecker()

    def test_unknown_check(self):
        result = self.checker.run_check('missing')
        self.assertEqual(result['status'], 'unknown')

    def test_healthy_check(self):
        self.checker.add_check('db', lambda: (True, 'connected'))
        result = self.checker.run_check('db')
        self.assertEqual(result['status'], 'healthy')
        self.assertEqual(result['message'], 'connected')

    def test_unhealthy_check(self):
        self.checker.add_check('db', lambda: (False, 'down'))
        result = self.checker.run_check('db')
        self.assertEqual(result['status'], 'unhealthy')

    def test_run_all_checks(self):
        self.checker.add_check('a', lambda: (True, 'ok'))
        self.checker.add_check('b', lambda: (False, 'bad'))
        result = self.checker.run_all_checks()
        self.assertEqual(result['status'], 'unhealthy')
        self.assertEqual(result['checks']['a']['status'], 'healthy')
        self.assertEqual(result['checks']['b']['status'], 'unhealthy')


class TestMonitoringCommands(unittest.TestCase):
    def test_metrics_show_no_registry(self):
        mc = MonitoringCommands()
        result = mc.metrics_show()
        self.assertIn('not available', result)

    def test_health_check_no_checker(self):
        mc = MonitoringCommands()
        result = mc.health_check()
        self.assertIn('not available', result)

    def test_prometheus_no_registry(self):
        mc = MonitoringCommands()
        result = mc.metrics_prometheus()
        self.assertIn('not available', result)

    def test_metrics_show_with_registry(self):
        registry = MetricsRegistry()
        registry.set_gauge('active', 5)
        mc = MonitoringCommands(registry=registry)
        result = mc.metrics_show()
        self.assertIn('active', result)

    def test_health_check_with_checker(self):
        checker = HealthChecker()
        checker.add_check('db', lambda: (True, 'ok'))
        mc = MonitoringCommands(health_checker=checker)
        result = mc.health_check()
        self.assertIn('healthy', result)

    def test_prometheus_with_registry(self):
        registry = MetricsRegistry()
        registry.increment_counter('c', 1)
        mc = MonitoringCommands(registry=registry)
        result = mc.metrics_prometheus()
        self.assertIn('c', result)


if __name__ == '__main__':
    unittest.main()
