"""
Metrics HTTP Server for KosDB v3.2.0

Provides HTTP endpoints for Prometheus metrics and health checks:
- /metrics - Prometheus-compatible metrics
- /health - Health checks (liveness, readiness)
- /status - Detailed server status
"""

import json
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, asdict


@dataclass
class HealthStatus:
    """Health check status."""
    status: str  # "healthy", "unhealthy", "degraded"
    checks: Dict[str, Any]
    timestamp: float


@dataclass
class ServerStatus:
    """Detailed server status."""
    version: str
    uptime: float
    databases: int
    tables: int
    connections: Dict[str, int]
    queries: Dict[str, int]
    memory: Dict[str, Any]
    timestamp: float


class MetricsHandler(BaseHTTPRequestHandler):
    """HTTP request handler for metrics endpoints."""
    
    def __init__(self, metrics_collector: Callable[[], str],
                 health_checker: Callable[[], HealthStatus],
                 status_provider: Callable[[], ServerStatus],
                 *args, **kwargs):
        self.metrics_collector = metrics_collector
        self.health_checker = health_checker
        self.status_provider = status_provider
        super().__init__(*args, **kwargs)
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass
    
    def do_GET(self):
        """Handle GET requests."""
        path = self.path
        
        if path == "/metrics":
            self._handle_metrics()
        elif path == "/health":
            self._handle_health()
        elif path == "/health/live":
            self._handle_liveness()
        elif path == "/health/ready":
            self._handle_readiness()
        elif path == "/status":
            self._handle_status()
        else:
            self._send_404()
    
    def _handle_metrics(self):
        """Handle /metrics endpoint."""
        try:
            metrics_data = self.metrics_collector()
            
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(metrics_data.encode('utf-8'))
        except Exception as e:
            self._send_error(500, str(e))
    
    def _handle_health(self):
        """Handle /health endpoint."""
        try:
            health = self.health_checker()
            
            status_code = 200 if health.status == "healthy" else \
                         503 if health.status == "unhealthy" else 200
            
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(asdict(health)).encode('utf-8'))
        except Exception as e:
            self._send_error(500, str(e))
    
    def _handle_liveness(self):
        """Handle /health/live (liveness probe)."""
        # Simple check - server is running
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()\n        self.wfile.write(json.dumps({\n            "status": "alive",\n            "timestamp": time.time()\n        }).encode('utf-8'))\n    \n    def _handle_readiness(self):\n        \"\"\"Handle /health/ready (readiness probe).\"\"\"\n        try:\n            health = self.health_checker()\n            \n            if health.status == "healthy":\n                self.send_response(200)\n                self.send_header("Content-Type", "application/json")\n                self.end_headers()\n                self.wfile.write(json.dumps({\n                    "status": "ready",\n                    "timestamp": time.time()\n                }).encode('utf-8'))\n            else:\n                self.send_response(503)\n                self.send_header("Content-Type", "application/json")\n                self.end_headers()\n                self.wfile.write(json.dumps({\n                    "status": "not_ready",\n                    "reason": health.status,\n                    "timestamp": time.time()\n                }).encode('utf-8'))\n        except Exception as e:\n            self._send_error(503, str(e))\n    \n    def _handle_status(self):\n        \"\"\"Handle /status endpoint.\"\"\"\n        try:\n            status = self.status_provider()\n            \n            self.send_response(200)\n            self.send_header("Content-Type", "application/json")\n            self.end_headers()\n            self.wfile.write(json.dumps(asdict(status), indent=2).encode('utf-8'))\n        except Exception as e:\n            self._send_error(500, str(e))\n    \n    def _send_404(self):\n        \"\"\"Send 404 Not Found.\"\"\"\n        self.send_response(404)\n        self.send_header("Content-Type", "application/json")\n        self.end_headers()\n        self.wfile.write(json.dumps({\n            "error": "Not Found",\n            "path": self.path\n        }).encode('utf-8'))\n    \n    def _send_error(self, code: int, message: str):\n        \"\"\"Send error response.\"\"\"\n        self.send_response(code)\n        self.send_header("Content-Type", "application/json")\n        self.end_headers()\n        self.wfile.write(json.dumps({\n            "error": message\n        }).encode('utf-8'))\n\n\nclass MetricsServer:\n    \"\"\"\n    HTTP server for metrics and health endpoints.\n    \"\"\"\n    \n    def __init__(self, host: str = "0.0.0.0", port: int = 9090,\n                 db=None, config: Optional[Dict[str, Any]] = None):\n        self.host = host\n        self.port = port\n        self.db = db\n        self.config = config or {}\n        self.server: Optional[HTTPServer] = None\n        self.thread: Optional[threading.Thread] = None\n        self.start_time = time.time()\n        self.running = False\n        \n        # Import metrics\n        try:\n            from metrics import get_metrics\n            self.metrics = get_metrics()\n        except ImportError:\n            self.metrics = None\n    \n    def _create_handler(self):\n        \"\"\"Create request handler with bound methods.\"\"\"\n        metrics_collector = self._collect_metrics\n        health_checker = self._check_health\n        status_provider = self._get_status\n        \n        def handler(*args, **kwargs):\n            return MetricsHandler(metrics_collector, health_checker, \n                                  status_provider, *args, **kwargs)\n        \n        return handler\n    \n    def start(self):\n        \"\"\"Start the metrics server.\"\"\"\n        if self.running:\n            return\n        \n        handler_class = self._create_handler()\n        self.server = HTTPServer((self.host, self.port), handler_class)\n        \n        self.thread = threading.Thread(target=self.server.serve_forever, \n                                       daemon=True)\n        self.thread.start()\n        self.running = True\n        \n        print(f"[Metrics] Server started on {self.host}:{self.port}\")\n    \n    def stop(self):\n        \"\"\"Stop the metrics server.\"\"\"\n        if not self.running:\n            return\n        \n        if self.server:\n            self.server.shutdown()\n            self.server.server_close()\n        \n        self.running = False\n        print("[Metrics] Server stopped")\n    \n    def _collect_metrics(self) -> str:\n        \"\"\"Collect Prometheus metrics.\"\"\"\n        if self.metrics:\n            return self.metrics.get_prometheus_metrics()\n        return "# No metrics available\\n"\n    \n    def _check_health(self) -> HealthStatus:\n        \"\"\"Check server health.\"\"\"\n        checks = {}\n        healthy = True\n        \n        # Check database\n        if self.db:\n            try:\n                # Simple check - can we list databases?\n                dbs = self.db.list_databases()\n                checks["database"] = {"status": "ok", "databases": len(dbs)}\n            except Exception as e:\n                checks["database"] = {"status": "error", "message": str(e)}\n                healthy = False\n        else:\n            checks["database"] = {"status": "unknown"}\n        \n        # Check memory (basic)\n        try:\n            import psutil\n            mem = psutil.virtual_memory()\n            checks["memory"] = {\n                "status": "ok" if mem.percent < 90 else "warning",\n                "percent": mem.percent\n            }\n            if mem.percent > 95:\n                healthy = False\n        except ImportError:\n            checks["memory"] = {"status": "unknown"}\n        \n        # Check disk\n        try:\n            import psutil\n            disk = psutil.disk_usage('.')\n            checks["disk"] = {\n                "status": "ok" if disk.percent < 90 else "warning",\n                "percent": disk.percent\n            }\n            if disk.percent > 95:\n                healthy = False\n        except ImportError:\n            checks["disk"] = {"status": "unknown"}\n        \n        status = "healthy" if healthy else "unhealthy"\n        \n        return HealthStatus(\n            status=status,\n            checks=checks,\n            timestamp=time.time()\n        )\n    \n    def _get_status(self) -> ServerStatus:\n        \"\"\"Get detailed server status.\"\"\"\n        databases = 0\n        tables = 0\n        \n        if self.db:\n            try:\n                databases = len(self.db.list_databases())\n                tables = len(self.db.list_tables())\n            except:\n                pass\n        \n        # Memory info\n        memory = {}\n        try:\n            import psutil\n            mem = psutil.virtual_memory()\n            memory = {\n                "total": mem.total,\n                "available": mem.available,\n                "percent": mem.percent,\n                "used": mem.used\n            }\n        except ImportError:\n            memory = {"status": "unknown"}\n        \n        # Query stats\n        queries = {}\n        if self.metrics:\n            try:\n                queries = {\n                    "total": self.metrics.query_total.get(),\n                    "errors": self.metrics.errors_total.get()\n                }\n            except:\n                pass\n        \n        return ServerStatus(\n            version="3.2.0\",\n            uptime=time.time() - self.start_time,\n            databases=databases,\n            tables=tables,\n            connections={\n                "active": self.metrics.connections_active.get() if self.metrics else 0\n            },\n            queries=queries,\n            memory=memory,\n            timestamp=time.time()\n        )\n\n\ndef create_metrics_server(db=None, config: Optional[Dict[str, Any]] = None) -> MetricsServer:\n    \"\"\"\n    Create and configure metrics server.\n    \n    Args:\n        db: Database instance\n        config: Configuration dictionary\n    \n    Returns:\n        Configured MetricsServer instance\n    \"\"\"\n    if config is None:\n        config = {}\n    \n    metrics_config = config.get('metrics', {})\n    \n    host = metrics_config.get('host', '0.0.0.0')\n    port = metrics_config.get('port', 9090)\n    \n    return MetricsServer(host=host, port=port, db=db, config=config)\n\n\n# Example usage\nif __name__ == '__main__':\n    server = MetricsServer(port=9090)\n    server.start()\n    \n    try:\n        while True:\n            time.sleep(1)\n    except KeyboardInterrupt:\n        server.stop()\n