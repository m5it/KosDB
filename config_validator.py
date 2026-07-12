
"""
Configuration Validator for KosDB

Validates configuration files against the v2.3.0 schema.
"""

import json
import os
from typing import Dict, Any, List, Tuple, Optional


class ConfigValidationError(Exception):
    """Configuration validation error."""
    pass


class ConfigValidator:
    """
    Validates KosDB configuration files.
    """
    
    # Valid values for enumerated fields
    VALID_SSL_VERSIONS = ['TLS', 'TLSv1', 'TLSv1_1', 'TLSv1_2']
    VALID_METRICS = ['cosine', 'euclidean', 'dot_product', 'manhattan']
    VALID_ROLES = ['master', 'slave']
    VALID_LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
    
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config: Optional[Dict] = None
        self.errors: List[str] = []
    
    def load(self) -> bool:
        """Load configuration from file."""
        try:
            with open(self.config_path, 'r') as f:
                self.config = json.load(f)
            return True
        except FileNotFoundError:
            self.errors.append(f"Configuration file not found: {self.config_path}")
            return False
        except json.JSONDecodeError as e:
            self.errors.append(f"Invalid JSON: {e}")
            return False
    
    def validate(self) -> Tuple[bool, List[str]]:
        """
        Validate entire configuration.
        
        Returns:
            Tuple of (is_valid, error_messages)
        """
        if self.config is None:
            if not self.load():
                return False, self.errors
        
        self.errors = []
        
        # Validate required sections
        self._validate_server()
        self._validate_batch()
        self._validate_tls()
        self._validate_cache()
        self._validate_gpu()
        self._validate_fulltext()
        self._validate_vector_search()
        self._validate_replication()
        self._validate_failover()
        self._validate_monitoring()
        self._validate_logging()
        
        return len(self.errors) == 0, self.errors
    
    def _validate_server(self):
        """Validate server configuration."""
        server = self.config.get('server', {})
        
        if not isinstance(server.get('port'), int):
            self.errors.append("server.port must be an integer")
        elif not (1 <= server.get('port', 0) <= 65535):
            self.errors.append("server.port must be between 1 and 65535")
        
        if not isinstance(server.get('max_connections'), int):
            self.errors.append("server.max_connections must be an integer")
        elif server.get('max_connections', 0) < 1:
            self.errors.append("server.max_connections must be positive")
    
    def _validate_batch(self):
        """Validate batch command configuration."""
        batch = self.config.get('batch', {})
        
        # Check if batch section exists (backward compatible)
        if not batch:
            return  # Use defaults
        
        if not isinstance(batch.get('enabled'), bool):
            self.errors.append("batch.enabled must be a boolean")
        
        # Validate max_commands_per_batch (default: 100)
        max_commands = batch.get('max_commands_per_batch', 100)
        if not isinstance(max_commands, int):
            self.errors.append("batch.max_commands_per_batch must be an integer")
        elif max_commands < 1:
            self.errors.append("batch.max_commands_per_batch must be positive")
        elif max_commands > 10000:
            self.errors.append("batch.max_commands_per_batch must not exceed 10000")
        
        # Validate max_batch_size_bytes (default: 1MB)
        max_batch_size = batch.get('max_batch_size_bytes', 1048576)
        if not isinstance(max_batch_size, int):
            self.errors.append("batch.max_batch_size_bytes must be an integer")
        elif max_batch_size < 1024:
            self.errors.append("batch.max_batch_size_bytes must be at least 1KB")
        elif max_batch_size > 104857600:
            self.errors.append("batch.max_batch_size_bytes must not exceed 100MB")
        
        # Validate max_response_size_bytes (default: 10MB)
        max_response = batch.get('max_response_size_bytes', 10485760)
        if not isinstance(max_response, int):
            self.errors.append("batch.max_response_size_bytes must be an integer")
        elif max_response < 1024:
            self.errors.append("batch.max_response_size_bytes must be at least 1KB")
        elif max_response > 104857600:
            self.errors.append("batch.max_response_size_bytes must not exceed 100MB")
        
        # Validate batch_timeout_seconds (default: 30)
        timeout = batch.get('batch_timeout_seconds', 30)
        if not isinstance(timeout, int):
            self.errors.append("batch.batch_timeout_seconds must be an integer")
        elif timeout < 1:
            self.errors.append("batch.batch_timeout_seconds must be positive")
        elif timeout > 3600:
            self.errors.append("batch.batch_timeout_seconds must not exceed 3600")
        
        if not isinstance(batch.get('continue_on_error'), bool):
            self.errors.append("batch.continue_on_error must be a boolean")
        
        if not isinstance(batch.get('transaction_support'), bool):
            self.errors.append("batch.transaction_support must be a boolean")
    
    def _validate_tls(self):
        """Validate TLS configuration."""
        tls = self.config.get('tls', {})
        
        if not isinstance(tls.get('enabled'), bool):
            self.errors.append("tls.enabled must be a boolean")
        
        if tls.get('enabled'):
            cert_file = tls.get('cert_file')
            key_file = tls.get('key_file')
            
            if not cert_file:
                self.errors.append("tls.cert_file is required when TLS is enabled")
            elif cert_file and not os.path.exists(cert_file):
                self.errors.append(f"tls.cert_file not found: {cert_file}")
            
            if not key_file:
                self.errors.append("tls.key_file is required when TLS is enabled")
            elif key_file and not os.path.exists(key_file):
                self.errors.append(f"tls.key_file not found: {key_file}")
            
            ca_file = tls.get('ca_file')
            if ca_file and not os.path.exists(ca_file):
                self.errors.append(f"tls.ca_file not found: {ca_file}")
        
        ssl_version = tls.get('ssl_version', 'TLS')
        if ssl_version not in self.VALID_SSL_VERSIONS:
            self.errors.append(f"tls.ssl_version must be one of: {self.VALID_SSL_VERSIONS}")
    
    def _validate_cache(self):
        """Validate cache configuration."""
        cache = self.config.get('cache', {})
        
        if not isinstance(cache.get('enabled'), bool):
            self.errors.append("cache.enabled must be a boolean")
        
        if not isinstance(cache.get('max_size'), int):
            self.errors.append("cache.max_size must be an integer")
        elif cache.get('max_size', 0) < 1:
            self.errors.append("cache.max_size must be positive")
        
        if not isinstance(cache.get('default_ttl'), int):
            self.errors.append("cache.default_ttl must be an integer")
        elif cache.get('default_ttl', 0) < 0:
            self.errors.append("cache.default_ttl must be non-negative")
    
    def _validate_gpu(self):
        """Validate GPU configuration."""
        gpu = self.config.get('gpu', {})
        
        if not isinstance(gpu.get('enabled'), bool):
            self.errors.append("gpu.enabled must be a boolean")
        
        if not isinstance(gpu.get('device_id'), int):
            self.errors.append("gpu.device_id must be an integer")
        elif gpu.get('device_id', 0) < 0:
            self.errors.append("gpu.device_id must be non-negative")
        
        memory_limit = gpu.get('memory_limit_mb')
        if memory_limit is not None:
            if not isinstance(memory_limit, int):
                self.errors.append("gpu.memory_limit_mb must be an integer or null")
            elif memory_limit < 1:
                self.errors.append("gpu.memory_limit_mb must be positive")
        
        if not isinstance(gpu.get('batch_size'), int):
            self.errors.append("gpu.batch_size must be an integer")
        elif gpu.get('batch_size', 0) < 1:
            self.errors.append("gpu.batch_size must be positive")
    
    def _validate_fulltext(self):
        """Validate full-text search configuration."""
        fulltext = self.config.get('fulltext', {})
        
        if not isinstance(fulltext.get('enabled'), bool):
            self.errors.append("fulltext.enabled must be a boolean")
        
        if not isinstance(fulltext.get('stem'), bool):
            self.errors.append("fulltext.stem must be a boolean")
        
        if not isinstance(fulltext.get('min_token_length'), int):
            self.errors.append("fulltext.min_token_length must be an integer")
        elif fulltext.get('min_token_length', 0) < 1:
            self.errors.append("fulltext.min_token_length must be positive")
        
        custom_stop_words = fulltext.get('custom_stop_words', [])
        if not isinstance(custom_stop_words, list):
            self.errors.append("fulltext.custom_stop_words must be a list")
        elif not all(isinstance(w, str) for w in custom_stop_words):
            self.errors.append("fulltext.custom_stop_words must contain only strings")
    
    def _validate_vector_search(self):
        """Validate vector search configuration."""
        vector = self.config.get('vector_search', {})
        
        if not isinstance(vector.get('enabled'), bool):
            self.errors.append("vector_search.enabled must be a boolean")
        
        if not isinstance(vector.get('default_dimension'), int):
            self.errors.append("vector_search.default_dimension must be an integer")
        elif vector.get('default_dimension', 0) < 1:
            self.errors.append("vector_search.default_dimension must be positive")
        
        metric = vector.get('metric', 'cosine')
        if metric not in self.VALID_METRICS:
            self.errors.append(f"vector_search.metric must be one of: {self.VALID_METRICS}")
        
        if not isinstance(vector.get('use_gpu'), bool):
            self.errors.append("vector_search.use_gpu must be a boolean")
    
    def _validate_replication(self):
        """Validate replication configuration."""
        replication = self.config.get('replication', {})
        
        if not isinstance(replication.get('enabled'), bool):
            self.errors.append("replication.enabled must be a boolean")
        
        role = replication.get('role', 'master')
        if role not in self.VALID_ROLES:
            self.errors.append(f"replication.role must be one of: {self.VALID_ROLES}")
        
        slaves = replication.get('slaves', [])
        if not isinstance(slaves, list):
            self.errors.append("replication.slaves must be a list")
    
    def _validate_failover(self):
        """Validate failover configuration."""
        failover = self.config.get('failover', {})
        
        if not isinstance(failover.get('enabled'), bool):
            self.errors.append("failover.enabled must be a boolean")
        
        if not isinstance(failover.get('node_id'), str):
            self.errors.append("failover.node_id must be a string")
        
        peers = failover.get('peers', [])
        if not isinstance(peers, list):
            self.errors.append("failover.peers must be a list")
        
        raft_port = failover.get('raft_port', 9000)
        if not isinstance(raft_port, int):
            self.errors.append("failover.raft_port must be an integer")
        elif not (1 <= raft_port <= 65535):
            self.errors.append("failover.raft_port must be between 1 and 65535")
    
    def _validate_monitoring(self):
        """Validate monitoring configuration."""
        monitoring = self.config.get('monitoring', {})
        
        if not isinstance(monitoring.get('enabled'), bool):
            self.errors.append("monitoring.enabled must be a boolean")
        
        http_port = monitoring.get('http_port', 9090)
        if not isinstance(http_port, int):
            self.errors.append("monitoring.http_port must be an integer")
        elif not (1 <= http_port <= 65535):
            self.errors.append("monitoring.http_port must be between 1 and 65535")
    
    def _validate_logging(self):
        """Validate logging configuration."""
        logging = self.config.get('logging', {})
        
        level = logging.get('level', 'INFO')
        if level not in self.VALID_LOG_LEVELS:
            self.errors.append(f"logging.level must be one of: {self.VALID_LOG_LEVELS}")
        
        max_size = logging.get('max_size_mb', 100)
        if not isinstance(max_size, int):
            self.errors.append("logging.max_size_mb must be an integer")
        elif max_size < 1:
            self.errors.append("logging.max_size_mb must be positive")


def validate_config(config_path: str) -> Tuple[bool, List[str]]:
    """
    Validate a configuration file.
    
    Args:
        config_path: Path to configuration file
    
    Returns:
        Tuple of (is_valid, error_messages)
    """
    validator = ConfigValidator(config_path)
    return validator.validate()


def create_minimal_config() -> Dict[str, Any]:
    """Create minimal valid configuration."""
    return {
        "version": "2.3.0",
        "server": {
            "host": "0.0.0.0",
            "port": 9999,
            "data_dir": "./data",
            "max_connections": 100
        },
        "batch": {
            "enabled": True,
            "max_commands_per_batch": 100,
            "max_batch_size_bytes": 1048576,
            "max_response_size_bytes": 10485760,
            "batch_timeout_seconds": 30,
            "continue_on_error": True,
            "transaction_support": True
        },
        "tls": {
            "enabled": False,
            "cert_file": None,
            "key_file": None,
            "ca_file": None,
            "require_client_cert": False,
            "ssl_version": "TLS"
        },
        "cache": {
            "enabled": True,
            "max_size": 1000,
            "default_ttl": 300,
            "invalidate_on_write": True
        },
        "gpu": {
            "enabled": False,
            "device_id": 0,
            "memory_limit_mb": None,
            "batch_size": 1000,
            "use_mixed_precision": False
        },
        "fulltext": {
            "enabled": True,
            "stem": True,
            "min_token_length": 2,
            "custom_stop_words": []
        },
        "vector_search": {
            "enabled": True,
            "default_dimension": 384,
            "metric": "cosine",
            "use_gpu": False
        },
        "replication": {
            "enabled": False,
            "role": "master",
            "slaves": [],
            "replication_port": None
        },
        "failover": {
            "enabled": False,
            "node_id": "node1",
            "peers": [],
            "raft_port": 9000
        },
        "monitoring": {
            "enabled": True,
            "http_port": 9090,
            "metrics_path": "/metrics",
            "health_path": "/health"
        },
        "logging": {
            "level": "INFO",
            "file": "./logs/kosdb.log",
            "max_size_mb": 100,
            "backup_count": 5
        }
    }


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python config_validator.py <config_file>")
        sys.exit(1)
    
    config_file = sys.argv[1]
    is_valid, errors = validate_config(config_file)
    
    if is_valid:
        print(f"✓ Configuration is valid: {config_file}")
        sys.exit(0)
    else:
        print(f"✗ Configuration errors in {config_file}:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)
