"""
Metrics Collection Module for KosDB v3.2.0

Provides Prometheus-compatible metrics with counters, gauges, and histograms.
Supports query metrics, cache statistics, connection pool stats, and replication lag.
"""

import time
import threading
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from collections import deque


@dataclass
class MetricValue:
    """Single metric value with timestamp."""
    value: float
    timestamp: float
    labels: Dict[str, str] = field(default_factory=dict)


class Counter:
    """
    Counter metric that only increases.
    """
    
    def __init__(self, name: str, description: str, labels: Optional[List[str]] = None):
        self.name = name
        self.description = description
        self.label_names = labels or []
        self.values: Dict[tuple, float] = {}  # label_values -> count
    
    def inc(self, amount: float = 1.0, label_values: Optional[Dict[str, str]] = None):
        """Increment counter."""
        key = self._make_key(label_values)
        self.values[key] = self.values.get(key, 0) + amount
    
    def get(self, label_values: Optional[Dict[str, str]] = None) -> float:
        """Get current counter value."""
        key = self._make_key(label_values)
        return self.values.get(key, 0)
    
    def _make_key(self, label_values: Optional[Dict[str, str]]) -> tuple:
        """Make hashable key from label values."""
        if not label_values:
            return ()
        return tuple(label_values.get(k, '') for k in self.label_names)
    
    def to_prometheus(self) -> str:
        """Export in Prometheus format."""
        lines = [
            f"# HELP {self.name} {self.description}",
            f"# TYPE {self.name} counter"
        ]
        
        for key, value in self.values.items():
            labels_str = self._format_labels(key)
            lines.append(f"{self.name}{labels_str} {value}")
        
        return "\n".join(lines)
    
    def _format_labels(self, key: tuple) -> str:
        """Format labels for Prometheus output."""
        if not key:
            return ""
        
        pairs = []
        for name, value in zip(self.label_names, key):
            if value:  # Only include non-empty labels
                pairs.append(f'{name}="{value}"')
        
        if pairs:
            return "{" + ",".join(pairs) + "}"
        return ""


class Gauge:
    """
    Gauge metric that can go up and down.
    """
    
    def __init__(self, name: str, description: str, labels: Optional[List[str]] = None):
        self.name = name
        self.description = description
        self.label_names = labels or []
        self.values: Dict[tuple, float] = {}
    
    def set(self, value: float, label_values: Optional[Dict[str, str]] = None):
        """Set gauge to specific value."""
        key = self._make_key(label_values)
        self.values[key] = value
    
    def inc(self, amount: float = 1.0, label_values: Optional[Dict[str, str]] = None):
        """Increment gauge."""
        key = self._make_key(label_values)
        self.values[key] = self.values.get(key, 0) + amount
    
    def dec(self, amount: float = 1.0, label_values: Optional[Dict[str, str]] = None):
        """Decrement gauge."""
        self.inc(-amount, label_values)
    
    def get(self, label_values: Optional[Dict[str, str]] = None) -> float:
        """Get current gauge value."""
        key = self._make_key(label_values)
        return self.values.get(key, 0)
    
    def _make_key(self, label_values: Optional[Dict[str, str]]) -> tuple:
        """Make hashable key from label values."""
        if not label_values:
            return ()
        return tuple(label_values.get(k, '') for k in self.label_names)
    
    def to_prometheus(self) -> str:
        """Export in Prometheus format."""
        lines = [
            f"# HELP {self.name} {self.description}",
            f"# TYPE {self.name} gauge"
        ]
        
        for key, value in self.values.items():
            labels_str = self._format_labels(key)
            lines.append(f"{self.name}{labels_str} {value}")
        
        return "\n".join(lines)
    
    def _format_labels(self, key: tuple) -> str:
        """Format labels for Prometheus output."""
        if not key:
            return ""
        
        pairs = []
        for name, value in zip(self.label_names, key):
            if value:
                pairs.append(f'{name}="{value}"')
        
        if pairs:
            return "{" + ",".join(pairs) + "}"
        return ""


class Histogram:
    """
    Histogram metric for measuring distributions.
    """
    
    DEFAULT_BUCKETS = [.005, .01, .025, .05, .075, .1, .25, .5, .75, 1.0, 
                       2.5, 5.0, 7.5, 10.0, float('inf')]
    
    def __init__(self, name: str, description: str, 
                 labels: Optional[List[str]] = None,
                 buckets: Optional[List[float]] = None):
        self.name = name
        self.description = description
        self.label_names = labels or []
        self.buckets = sorted(buckets or self.DEFAULT_BUCKETS)
        
        # bucket_key -> {upper_bound: count}
        self.buckets_data: Dict[tuple, Dict[float, int]] = {}
        self.sums: Dict[tuple, float] = {}
        self.counts: Dict[tuple, int] = {}
    
    def observe(self, value: float, label_values: Optional[Dict[str, str]] = None):
        """Observe a value."""
        key = self._make_key(label_values)
        
        if key not in self.buckets_data:
            self.buckets_data[key] = {b: 0 for b in self.buckets}
            self.sums[key] = 0
            self.counts[key] = 0
        
        # Update buckets
        for bucket in self.buckets:
            if value <= bucket:
                self.buckets_data[key][bucket] += 1
        
        self.sums[key] += value
        self.counts[key] += 1
    
    def _make_key(self, label_values: Optional[Dict[str, str]]) -> tuple:
        """Make hashable key from label values."""
        if not label_values:
            return ()
        return tuple(label_values.get(k, '') for k in self.label_names)
    
    def to_prometheus(self) -> str:
        """Export in Prometheus format."""
        lines = [
            f"# HELP {self.name} {self.description}",
            f"# TYPE {self.name} histogram"
        ]
        
        base_name = self.name
        
        for key in self.buckets_data:
            labels_str = self._format_labels(key)
            
            # Output buckets
            for bucket in self.buckets:
                bucket_label = f'le="{bucket}"' if bucket != float('inf') else 'le="+Inf"'
                if labels_str:
                    full_labels = labels_str[:-1] + "," + bucket_label + "}"
                else:
                    full_labels = "{" + bucket_label + "}"
                
                lines.append(f"{base_name}_bucket{full_labels} {self.buckets_data[key][bucket]}")
            
            # Output sum and count
            lines.append(f"{base_name}_sum{labels_str} {self.sums[key]}")
            lines.append(f"{base_name}_count{labels_str} {self.counts[key]}")
        
        return "\n".join(lines)
    
    def _format_labels(self, key: tuple) -> str:
        """Format labels for Prometheus output."""
        if not key:
            return ""
        
        pairs = []
        for name, value in zip(self.label_names, key):
            if value:
                pairs.append(f'{name}="{value}"')
        
        if pairs:
            return "{" + ",".join(pairs) + "}"
        return ""


class MetricsRegistry:
    """
    Registry for all metrics.
    """
    
    def __init__(self):
        self.counters: Dict[str, Counter] = {}
        self.gauges: Dict[str, Gauge] = {}
        self.histograms: Dict[str, Histogram] = {}
        self._lock = threading.Lock()
    
    def counter(self, name: str, description: str, 
                labels: Optional[List[str]] = None) -> Counter:
        """Create or get counter."""
        with self._lock:
            if name not in self.counters:
                self.counters[name] = Counter(name, description, labels)
            return self.counters[name]
    
    def gauge(self, name: str, description: str, 
              labels: Optional[List[str]] = None) -> Gauge:
        """Create or get gauge."""
        with self._lock:
            if name not in self.gauges:
                self.gauges[name] = Gauge(name, description, labels)
            return self.gauges[name]
    
    def histogram(self, name: str, description: str, 
                  labels: Optional[List[str]] = None,
                  buckets: Optional[List[float]] = None) -> Histogram:
        """Create or get histogram."""
        with self._lock:
            if name not in self.histograms:
                self.histograms[name] = Histogram(name, description, labels, buckets)
            return self.histograms[name]
    
    def to_prometheus(self) -> str:
        """Export all metrics in Prometheus format."""
        lines = []
        
        # Counters
        for counter in self.counters.values():
            lines.append(counter.to_prometheus())
            lines.append("")  # Empty line between metrics
        
        # Gauges
        for gauge in self.gauges.values():
            lines.append(gauge.to_prometheus())
            lines.append("")
        
        # Histograms
        for hist in self.histograms.values():
            lines.append(hist.to_prometheus())
            lines.append("")
        
        return "\n".join(lines)
    
    def get_metric(self, name: str) -> Optional[Any]:
        """Get metric by name."""
        if name in self.counters:
            return self.counters[name]
        if name in self.gauges:
            return self.gauges[name]
        if name in self.histograms:
            return self.histograms[name]
        return None


class KosDBMetrics:
    """
    KosDB-specific metrics collection.
    """
    
    def __init__(self):
        self.registry = MetricsRegistry()
        
        # Query metrics
        self.query_total = self.registry.counter(
            "kosdb_queries_total",
            "Total number of queries executed",
            ["command", "status"]
        )
        
        self.query_duration = self.registry.histogram(
            "kosdb_query_duration_seconds",
            "Query execution time in seconds",
            ["command"]
        )
        
        # Cache metrics
        self.cache_hits = self.registry.counter(
            "kosdb_cache_hits_total",
            "Total number of cache hits",
            ["cache_type"]
        )
        
        self.cache_misses = self.registry.counter(
            "kosdb_cache_misses_total",
            "Total number of cache misses",
            ["cache_type"]
        )
        
        self.cache_size = self.registry.gauge(
            "kosdb_cache_size",
            "Current cache size",
            ["cache_type"]
        )
        
        # Connection metrics
        self.connections_active = self.registry.gauge(
            "kosdb_connections_active",
            "Number of active connections"
        )
        
        self.connections_total = self.registry.counter(
            "kosdb_connections_total",
            "Total number of connections accepted"
        )
        
        # Replication metrics
        self.replication_lag = self.registry.gauge(
            "kosdb_replication_lag_seconds",
            "Replication lag in seconds",
            ["role"]
        )
        
        # Storage metrics
        self.storage_size = self.registry.gauge(
            "kosdb_storage_size_bytes",
            "Storage size in bytes",
            ["database"]
        )
        
        self.table_rows = self.registry.gauge(
            "kosdb_table_rows",
            "Number of rows in table",
            ["database", "table"]
        )
        
        # Error metrics
        self.errors_total = self.registry.counter(
            "kosdb_errors_total",
            "Total number of errors",
            ["type"]
        )
    
    def record_query(self, command: str, duration: float, success: bool = True):
        """Record query execution."""
        status = "success" if success else "error"
        self.query_total.inc(1, {"command": command, "status": status})
        self.query_duration.observe(duration, {"command": command})
    
    def record_cache_hit(self, cache_type: str = "plan"):
        """Record cache hit."""
        self.cache_hits.inc(1, {"cache_type": cache_type})
    
    def record_cache_miss(self, cache_type: str = "plan"):
        """Record cache miss."""
        self.cache_misses.inc(1, {"cache_type": cache_type})
    
    def update_cache_size(self, size: int, cache_type: str = "plan"):
        """Update cache size gauge."""
        self.cache_size.set(size, {"cache_type": cache_type})
    
    def record_connection_opened(self):
        """Record new connection."""
        self.connections_total.inc()
        self.connections_active.inc()
    
    def record_connection_closed(self):
        """Record closed connection."""
        self.connections_active.dec()
    
    def update_replication_lag(self, lag_seconds: float, role: str = "slave"):
        """Update replication lag."""
        self.replication_lag.set(lag_seconds, {"role": role})
    
    def record_error(self, error_type: str):
        """Record error."""
        self.errors_total.inc(1, {"type": error_type})
    
    def get_prometheus_metrics(self) -> str:
        """Get all metrics in Prometheus format."""
        return self.registry.to_prometheus()


# Global metrics instance
_metrics_instance: Optional[KosDBMetrics] = None


def get_metrics() -> KosDBMetrics:
    """Get or create global metrics instance."""
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = KosDBMetrics()
    return _metrics_instance


def reset_metrics():
    """Reset global metrics (useful for testing)."""
    global _metrics_instance
    _metrics_instance = None
