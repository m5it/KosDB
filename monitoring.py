
"""
Monitoring and Metrics System for LevelDB Socket Server

Provides performance metrics, health checks, and monitoring endpoints.
Includes multi-command batch execution metrics (v2.3.0).
"""

import time
import threading
import json
import statistics
from typing import Dict, Any, List, Optional, Callable
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
import psutil
import os


class MetricType(Enum):
    """Types of metrics."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"
import os

from commands import Command
from dataclasses import dataclass, field
from enum import Enum
import psutil
import os


class MetricType(Enum):
    """Types of metrics."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


@dataclass
class Metric:
    """Single metric data point."""
    name: str
    metric_type: MetricType
    value: float
    timestamp: float
    labels: Dict[str, str] = field(default_factory=dict)


class MetricsRegistry:
    """
    Central registry for all metrics.
    Thread-safe storage and retrieval of metrics.
    """
    
    def __init__(self, max_history: int = 10000):
        self._metrics: Dict[str, List[Metric]] = {}
        self._counters: Dict[str, float] = {}
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = {}
        self._max_history = max_history
        self._lock = threading.RLock()
        
        # Callbacks for metric events
        self._callbacks: List[Callable[[Metric], None]] = []
    
    def register_callback(self, callback: Callable[[Metric], None]):
        """Register a callback for metric events."""
        self._callbacks.append(callback)
    
    def increment_counter(self, name: str, value: float = 1.0, 
                          labels: Optional[Dict[str, str]] = None):
        """Increment a counter metric."""
        with self._lock:
            key = self._make_key(name, labels)
            self._counters[key] = self._counters.get(key, 0) + value
            
            metric = Metric(
                name=name,
                metric_type=MetricType.COUNTER,
                value=self._counters[key],
                timestamp=time.time(),
                labels=labels or {}
            )
            self._store_metric(metric)
    
    def set_gauge(self, name: str, value: float, 
                  labels: Optional[Dict[str, str]] = None):
        """Set a gauge metric."""
        with self._lock:
            key = self._make_key(name, labels)
            self._gauges[key] = value
            
            metric = Metric(
                name=name,
                metric_type=MetricType.GAUGE,
                value=value,
                timestamp=time.time(),
                labels=labels or {}
            )
            self._store_metric(metric)
    
    def record_histogram(self, name: str, value: float,
                       labels: Optional[Dict[str, str]] = None):
        """Record a value in a histogram."""
        with self._lock:
            key = self._make_key(name, labels)
            if key not in self._histograms:
                self._histograms[key] = []
            self._histograms[key].append(value)
            
            # Keep only last 1000 values
            if len(self._histograms[key]) > 1000:
                self._histograms[key] = self._histograms[key][-1000:]
            
            metric = Metric(
                name=name,
                metric_type=MetricType.HISTOGRAM,
                value=value,
                timestamp=time.time(),
                labels=labels or {}
            )
            self._store_metric(metric)
    
    def record_timer(self, name: str, duration: float,
                     labels: Optional[Dict[str, str]] = None):
        """Record a timer duration."""
        self.record_histogram(name, duration, labels)
        
        with self._lock:
            metric = Metric(
                name=name,
                metric_type=MetricType.TIMER,
                value=duration,
                timestamp=time.time(),
                labels=labels or {}
            )
            self._store_metric(metric)
    
    def _make_key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        """Create storage key from name and labels."""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"
    
    def _store_metric(self, metric: Metric):
        """Store metric in history."""
        key = self._make_key(metric.name, metric.labels)
        if key not in self._metrics:
            self._metrics[key] = deque(maxlen=self._max_history)
        self._metrics[key].append(metric)
        
        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(metric)
            except Exception:
                pass
    
    def get_counter(self, name: str, labels: Optional[Dict[str, str]] = None) -> float:
        """Get current counter value."""
        key = self._make_key(name, labels)
        return self._counters.get(key, 0)
    
    def get_gauge(self, name: str, labels: Optional[Dict[str, str]] = None) -> float:
        """Get current gauge value."""
        key = self._make_key(name, labels)
        return self._gauges.get(key, 0)
    
    def get_histogram_stats(self, name: str, 
                           labels: Optional[Dict[str, str]] = None) -> Dict[str, float]:
        """Get histogram statistics."""
        key = self._make_key(name, labels)
        values = self._histograms.get(key, [])
        
        if not values:
            return {'count': 0, 'sum': 0, 'min': 0, 'max': 0, 'avg': 0, 'p95': 0, 'p99': 0}
        
        sorted_values = sorted(values)
        count = len(sorted_values)
        
        return {
            'count': count,
            'sum': sum(sorted_values),
            'min': sorted_values[0],
            'max': sorted_values[-1],
            'avg': statistics.mean(sorted_values),
            'p95': sorted_values[int(count * 0.95)] if count > 1 else sorted_values[0],
            'p99': sorted_values[int(count * 0.99)] if count > 1 else sorted_values[0]
        }
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all current metrics."""
        with self._lock:
            result = {
                'counters': dict(self._counters),
                'gauges': dict(self._gauges),
                'histograms': {}
            }
            
            for key in self._histograms:
                name_labels = self._parse_key(key)
                result['histograms'][key] = self.get_histogram_stats(
                    name_labels['name'], 
                    name_labels.get('labels')
                )
            
            return result
    
    def _parse_key(self, key: str) -> Dict[str, Any]:
        """Parse key into name and labels."""
        if '{' not in key:
            return {'name': key, 'labels': {}}
        
        name, labels_str = key.split('{', 1)
        labels_str = labels_str.rstrip('}')
        
        labels = {}
        for part in labels_str.split(','):
            if '=' in part:
                k, v = part.split('=', 1)
                labels[k] = v
        
        return {'name': name, 'labels': labels}
    
    def export_prometheus(self) -> str:
        """Export metrics in Prometheus format."""
        lines = []
        
        with self._lock:
            # Counters
            for key, value in self._counters.items():
                name_labels = self._parse_key(key)
                name = name_labels['name'].replace('.', '_')
                labels = name_labels.get('labels', {})
                label_str = self._format_labels(labels)
                lines.append(f"# TYPE {name} counter")
                lines.append(f"{name}{label_str} {value}")
            
            # Gauges
            for key, value in self._gauges.items():
                name_labels = self._parse_key(key)
                name = name_labels['name'].replace('.', '_')
                labels = name_labels.get('labels', {})
                label_str = self._format_labels(labels)
                lines.append(f"# TYPE {name} gauge")
                lines.append(f"{name}{label_str} {value}")
            
            # Histograms
            for key, values in self._histograms.items():
                if not values:
                    continue
                name_labels = self._parse_key(key)
                name = name_labels['name'].replace('.', '_')
                labels = name_labels.get('labels', {})
                
                stats = self.get_histogram_stats(name_labels['name'], 
                                                  name_labels.get('labels'))
                
                lines.append(f"# TYPE {name} histogram")
                lines.append(f"{name}_count{self._format_labels(labels)} {stats['count']}")
                lines.append(f"{name}_sum{self._format_labels(labels)} {stats['sum']}")
                lines.append(f"{name}_bucket{{le=\"+Inf\"}}{self._format_labels(labels)} {stats['count']}")
        
        return "\n".join(lines)
    
    def _format_labels(self, labels: Dict[str, str]) -> str:
        """Format labels for Prometheus."""
        if not labels:
            return ""
        label_pairs = [f'{k}="{v}"' for k, v in sorted(labels.items())]
        return "{" + ",".join(label_pairs) + "}"


class SystemMetricsCollector:
    """
    Collects system-level metrics.
    """
    
    def __init__(self, registry: MetricsRegistry):
        self.registry = registry
        self.process = psutil.Process(os.getpid())
        self._running = False
        self._thread: Optional[threading.Thread] = None
    
    def start(self, interval: float = 10.0):
        """Start collecting system metrics."""
        self._running = True
        self._thread = threading.Thread(target=self._collect_loop, 
                                          args=(interval,), daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop collecting system metrics."""
        self._running = False
    
    def _collect_loop(self, interval: float):
        """Collect metrics in a loop."""
        while self._running:
            try:
                self._collect_once()
            except Exception as e:
                print(f"[METRICS] Collection error: {e}")
            
            time.sleep(interval)
    
    def _collect_once(self):
        """Collect metrics once."""
        # CPU
        cpu_percent = self.process.cpu_percent()
        self.registry.set_gauge('system.cpu_percent', cpu_percent)
        
        # Memory
        memory_info = self.process.memory_info()
        self.registry.set_gauge('system.memory_rss_bytes', memory_info.rss)
        self.registry.set_gauge('system.memory_vms_bytes', memory_info.vms)
        
        # Disk
        disk_io = self.process.io_counters()
        self.registry.set_gauge('system.disk_read_bytes', disk_io.read_bytes)
        self.registry.set_gauge('system.disk_write_bytes', disk_io.write_bytes)
        
        # Network
        net_io = psutil.net_io_counters()
        self.registry.set_gauge('system.net_sent_bytes', net_io.bytes_sent)
        self.registry.set_gauge('system.net_recv_bytes', net_io.bytes_recv)
        
        # Open files
        open_files = len(self.process.open_files())
        self.registry.set_gauge('system.open_files', open_files)
        
        # Thread count
        self.registry.set_gauge('system.threads', self.process.num_threads())
        
        # Load average (Unix only)
        try:
            load1, load5, load15 = os.getloadavg()
            self.registry.set_gauge('system.load1', load1)
            self.registry.set_gauge('system.load5', load5)
            self.registry.set_gauge('system.load15', load15)
        except AttributeError:
            pass  # Windows doesn't have getloadavg


class QueryMetricsCollector:
    """
    Collects database query metrics.
    """
    
    def __init__(self, registry: MetricsRegistry):
        self.registry = registry
    
    def record_query(self, query_type: str, duration: float, 
                     success: bool = True, rows_affected: int = 0):
        """Record a query execution."""
        labels = {'type': query_type, 'status': 'success' if success else 'error'}
        
        # Counter for total queries
        self.registry.increment_counter('queries.total', 1, labels)
        
        # Counter for errors
        if not success:
            self.registry.increment_counter('queries.errors', 1, {'type': query_type})
        
        # Timer for duration
        self.registry.record_timer('queries.duration_seconds', duration, labels)
        
        # Gauge for rows affected (for INSERT/UPDATE/DELETE)
        if rows_affected > 0:
            self.registry.set_gauge('queries.rows_affected', rows_affected, 
                                     {'type': query_type})
    
    def record_connection(self, event: str):
        """Record connection event."""
        self.registry.increment_counter('connections.total', 1, {'event': event})


class HealthChecker:
    """
    Health check system for the database server.
    """
    
    def __init__(self, db=None):
        self.db = db
        self.checks: Dict[str, Callable[[], Tuple[bool, str]]] = {}
        self._last_results: Dict[str, Dict[str, Any]] = {}
    
    def add_check(self, name: str, check_func: Callable[[], Tuple[bool, str]]):
        """Add a health check."""
        self.checks[name] = check_func
    
    def run_check(self, name: str) -> Dict[str, Any]:
        """Run a single health check."""
        if name not in self.checks:
            return {'name': name, 'status': 'unknown', 'message': 'Check not found'}
        
        try:
            healthy, message = self.checks[name]()
            result = {
                'name': name,
                'status': 'healthy' if healthy else 'unhealthy',
                'message': message,
                'timestamp': time.time()
            }
        except Exception as e:
            result = {
                'name': name,
                'status': 'error',
                'message': str(e),
                'timestamp': time.time()
            }
        
        self._last_results[name] = result
        return result
    
    def run_all_checks(self) -> Dict[str, Any]:
        """Run all health checks."""
        results = {}
        overall_healthy = True
        
        for name in self.checks:
            result = self.run_check(name)
            results[name] = result
            if result['status'] != 'healthy':
                overall_healthy = False
        
        return {
            'status': 'healthy' if overall_healthy else 'unhealthy',
            'checks': results,
            'timestamp': time.time()
        }
    
    def get_last_result(self, name: str) -> Optional[Dict[str, Any]]:
        """Get last result for a check."""
        return self._last_results.get(name)


class MetricsHTTPExporter:
    """
    HTTP server for exporting metrics.
    Supports Prometheus format and JSON.
    """
    
    def __init__(self, registry: MetricsRegistry, host: str = "0.0.0.0", 
                 port: int = 9090, health_checker: Optional[HealthChecker] = None):
        self.registry = registry
        self.host = host
        self.port = port
        self.health_checker = health_checker
        self.server = None
        self._running = False
    
    def start(self):
        """Start the HTTP server."""
        try:
            from http.server import HTTPServer, BaseHTTPRequestHandler
            
            registry = self.registry
            health_checker = self.health_checker
            
            class MetricsHandler(BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path == '/metrics':
                        self.send_response(200)
                        self.send_header('Content-Type', 'text/plain')
                        self.end_headers()
                        self.wfile.write(registry.export_prometheus().encode())
                    
                    elif self.path == '/health':
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        if health_checker:
                            health = health_checker.run_all_checks()
                        else:
                            health = {'status': 'healthy'}
                        self.wfile.write(json.dumps(health, indent=2).encode())
                    
                    elif self.path == '/api/metrics':
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps(registry.get_all_metrics(), indent=2).encode())
                    
                    else:
                        self.send_response(404)
                        self.end_headers()
                        self.wfile.write(b'Not found')
                
                def log_message(self, format, *args):
                    pass  # Suppress logs
            
            self.server = HTTPServer((self.host, self.port), MetricsHandler)
            self._running = True
            
            print(f"[METRICS] HTTP exporter started on {self.host}:{self.port}")
            
            thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            thread.start()
            
        except Exception as e:
            print(f"[METRICS] Failed to start HTTP exporter: {e}")
    
    def stop(self):
        """Stop the HTTP server."""
        if self.server:
            self.server.shutdown()
            self._running = False


# Commands for CLI integration
class MonitoringCommands:
    """Commands for monitoring and metrics."""
    
    def __init__(self, registry: Optional[MetricsRegistry] = None,
                 health_checker: Optional[HealthChecker] = None):
        self.registry = registry
        self.health_checker = health_checker
    
    def metrics_show(self) -> str:
        """Show current metrics."""
        if not self.registry:
            return "ERROR: Metrics registry not available"
        
        metrics = self.registry.get_all_metrics()
        
        lines = ["System Metrics:", "-" * 50]
        
        # Counters
        if metrics['counters']:
            lines.append("\nCounters:")
            for name, value in sorted(metrics['counters'].items()):
                lines.append(f"  {name}: {value}")
        
        # Gauges
        if metrics['gauges']:
            lines.append("\nGauges:")
            for name, value in sorted(metrics['gauges'].items()):
                if 'bytes' in name:
                    lines.append(f"  {name}: {self._format_bytes(value)}")
                elif 'percent' in name:
                    lines.append(f"  {name}: {value:.1f}%")
                else:
                    lines.append(f"  {name}: {value:.2f}")
        
        # Histograms
        if metrics['histograms']:
            lines.append("\nHistograms:")
            for name, stats in sorted(metrics['histograms'].items()):
                lines.append(f"  {name}:")
                lines.append(f"    count: {stats['count']}, "
                           f"avg: {stats['avg']:.3f}, "
                           f"p95: {stats['p95']:.3f}, "
                           f"p99: {stats['p99']:.3f}")
        
        return "\n".join(lines)
    
    def _format_bytes(self, bytes_val: float) -> str:
        """Format bytes to human readable."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_val < 1024:
                return f"{bytes_val:.2f} {unit}"
            bytes_val /= 1024
        return f"{bytes_val:.2f} TB"
    
    def health_check(self) -> str:
        """Run health checks."""
        if not self.health_checker:
            return "ERROR: Health checker not available"
        
        result = self.health_checker.run_all_checks()
        
        lines = ["Health Check Results:", "-" * 50]
        lines.append(f"Overall Status: {result['status'].upper()}")
        lines.append("")
        
        for name, check in result['checks'].items():
            status_icon = "✓" if check['status'] == 'healthy' else "✗"
            lines.append(f"{status_icon} {name}: {check['status']}")
            lines.append(f"  {check['message']}")
        
        return "\n".join(lines)
    
    def metrics_prometheus(self) -> str:
        """Export metrics in Prometheus format."""
        if not self.registry:
            return "ERROR: Metrics registry not available"
        
        return self.registry.export_prometheus()


class MetricsCommand(Command):
    """METRICS - Show current metrics."""
    def execute(self, params, client_state):
        if not client_state.get('is_admin'):
            return "ERROR: Admin only"
        
        try:
            from monitoring import MonitoringCommands
            mc = MonitoringCommands()
            if hasattr(self.db, '_metrics_registry'):
                mc.registry = self.db._metrics_registry
            return mc.metrics_show()
        except Exception as e:
            return f"ERROR: {e}"


class HealthCommand(Command):
    """HEALTH - Run health checks."""
    def execute(self, params, client_state):
        if not client_state.get('is_admin'):
            return "ERROR: Admin only"
        
        try:
            from monitoring import MonitoringCommands
            mc = MonitoringCommands()
            if hasattr(self.db, '_health_checker'):
                mc.health_checker = self.db._health_checker
            return mc.health_check()
        except Exception as e:
            return f"ERROR: {e}"


class PrometheusCommand(Command):
    """PROMETHEUS - Export metrics in Prometheus format."""
    def execute(self, params, client_state):
        if not client_state.get('is_admin'):
            return "ERROR: Admin only"
        
        try:
            from monitoring import MonitoringCommands
            mc = MonitoringCommands()
            if hasattr(self.db, '_metrics_registry'):
                mc.registry = self.db._metrics_registry
            return mc.metrics_prometheus()
        except Exception as e:
            return f"ERROR: {e}"
