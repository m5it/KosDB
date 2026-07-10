"""
Configuration Loader for KosDB v3.1.0

Provides configuration loading, validation, environment variable substitution,
and hot-reload support for non-critical settings.
"""

import os
import json
import time
import threading
import logging
from typing import Dict, Any, Optional, List, Callable
from pathlib import Path

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Raised when configuration is invalid."""
    pass


class ConfigLoader:
    """
    Configuration loader with validation, environment substitution, and hot-reload.
    """
    
    # Sensitive keys that should be masked in logs
    SENSITIVE_KEYS = {
        'password', 'secret', 'key', 'token', 'passphrase', 'private_key',
        'encryption_key', 'jwt_secret', 'api_key'
    }
    
    def __init__(self, config_path: str = 'config.json'):
        """
        Initialize configuration loader.
        
        Args:
            config_path: Path to configuration file
        """
        self.config_path = Path(config_path)
        self._config: Dict[str, Any] = {}
        self._last_modified: float = 0
        self._last_loaded: float = 0
        self._reload_callbacks: List[Callable] = []
        self._reload_thread: Optional[threading.Thread] = None
        self._stop_reload = threading.Event()
        self._lock = threading.RLock()
    
    def load(self, validate: bool = True, substitute_env: bool = True) -> Dict[str, Any]:
        """
        Load configuration from file.
        
        Args:
            validate: Whether to validate configuration
            substitute_env: Whether to substitute environment variables
        
        Returns:
            Configuration dictionary
        
        Raises:
            ConfigError: If configuration is invalid or file not found
        """
        if not self.config_path.exists():
            raise ConfigError(f"Configuration file not found: {self.config_path}")
        
        try:
            with open(self.config_path, 'r') as f:
                raw_config = f.read()
            
            config = json.loads(raw_config)
            
            # Substitute environment variables
            if substitute_env:
                config = self._substitute_env_vars(config)
            
            # Validate configuration
            if validate:
                errors = self._validate_config(config)
                if errors:
                    raise ConfigError(f"Configuration validation failed: " + "; ".join(errors))
            
            with self._lock:
                self._config = config
                self._last_loaded = time.time()
                self._last_modified = self.config_path.stat().st_mtime
            
            logger.info(f"Configuration loaded from {self.config_path}")
            return config
            
        except json.JSONDecodeError as e:
            raise ConfigError(f"Invalid JSON in configuration file: {e}")
        except Exception as e:
            raise ConfigError(f"Failed to load configuration: {e}")
    
    def _substitute_env_vars(self, config: Any) -> Any:
        """
        Recursively substitute environment variables in configuration.
        
        Supports ${VAR_NAME} or $VAR_NAME syntax.
        """
        import re
        
        if isinstance(config, dict):
            return {k: self._substitute_env_vars(v) for k, v in config.items()}
        elif isinstance(config, list):
            return [self._substitute_env_vars(item) for item in config]
        elif isinstance(config, str):
            # Pattern: ${VAR_NAME} or $VAR_NAME
            pattern = re.compile(r'\$\{(\w+)\}|\$(\w+)')
            
            def replace_env_var(match):
                var_name = match.group(1) or match.group(2)
                value = os.getenv(var_name)
                if value is None:
                    logger.warning(f"Environment variable {var_name} not set")
                    return match.group(0)  # Keep original
                return value
            
            return pattern.sub(replace_env_var, config)
        else:
            return config
    
    def _validate_config(self, config: Dict[str, Any]) -> List[str]:
        """
        Validate configuration against schema.
        
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        # Check required sections
        required_sections = ['server', 'database']
        for section in required_sections:
            if section not in config:
                errors.append(f"Missing required section: {section}")
        
        # Basic validation
        if 'server' in config:
            server = config['server']
            if 'port' in server and not (1 <= server['port'] <= 65535):
                errors.append("server.port must be between 1 and 65535")
        
        if 'database' in config:
            db = config['database']
            if 'encryption' in db and db['encryption'].get('enabled'):
                if not db['encryption'].get('key_file') and not db['encryption'].get('passphrase_env'):
                    errors.append("database.encryption requires key_file or passphrase_env when enabled")
        
        # Cross-field validation
        if 'performance' in config:
            perf = config['performance']
            if 'connection_pool_min' in perf and 'connection_pool_max' in perf:
                if perf['connection_pool_min'] > perf['connection_pool_max']:
                    errors.append("performance.connection_pool_min cannot be greater than connection_pool_max")
        
        return errors
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by dot-notation key.
        
        Args:
            key: Dot-notation key (e.g., 'server.port')
            default: Default value if key not found
        
        Returns:
            Configuration value
        """
        with self._lock:
            keys = key.split('.')
            value = self._config
            
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
            
            return value
    
    def get_all(self) -> Dict[str, Any]:
        """Get full configuration."""
        with self._lock:
            return self._config.copy()
    
    def reload(self) -> bool:
        """
        Reload configuration if file has changed.
        
        Returns:
            True if reloaded, False if unchanged
        """
        if not self.config_path.exists():
            logger.warning(f"Configuration file not found: {self.config_path}")
            return False
        
        current_mtime = self.config_path.stat().st_mtime
        
        with self._lock:
            if current_mtime <= self._last_modified:
                return False
            
            try:
                old_config = self._config.copy()
                self.load(validate=True, substitute_env=True)
                
                # Notify callbacks
                changes = self._detect_changes(old_config, self._config)
                if changes:
                    logger.info(f"Configuration reloaded. Changes: {changes}")
                    for callback in self._reload_callbacks:
                        try:
                            callback(changes)
                        except Exception as e:
                            logger.error(f"Reload callback failed: {e}")
                
                return True
                
            except ConfigError as e:
                logger.error(f"Failed to reload configuration: {e}")
                return False
    
    def _detect_changes(self, old: Dict, new: Dict, prefix: str = '') -> List[str]:
        """Detect changes between old and new configuration."""
        changes = []
        
        all_keys = set(old.keys()) | set(new.keys())
        
        for key in all_keys:
            full_key = f"{prefix}.{key}" if prefix else key
            
            if key not in old:
                changes.append(f"+{full_key}")
            elif key not in new:
                changes.append(f"-{full_key}")
            elif isinstance(old[key], dict) and isinstance(new[key], dict):
                changes.extend(self._detect_changes(old[key], new[key], full_key))
            elif old[key] != new[key]:
                # Mask sensitive values
                if any(s in full_key.lower() for s in self.SENSITIVE_KEYS):
                    changes.append(f"~{full_key}: ***")
                else:
                    changes.append(f"~{full_key}: {old[key]} -> {new[key]}")
        
        return changes
    
    def start_hot_reload(self, interval: int = 30):
        """
        Start hot-reload watcher thread.
        
        Args:
            interval: Check interval in seconds
        """
        if self._reload_thread and self._reload_thread.is_alive():
            logger.warning("Hot-reload already running")
            return
        
        self._stop_reload.clear()
        
        def watcher():
            while not self._stop_reload.wait(interval):
                try:
                    if self.reload():
                        logger.debug("Configuration hot-reloaded")
                except Exception as e:
                    logger.error(f"Hot-reload error: {e}")
        
        self._reload_thread = threading.Thread(target=watcher, daemon=True)
        self._reload_thread.start()
        logger.info(f"Hot-reload started (interval={interval}s)")
    
    def stop_hot_reload(self):
        """Stop hot-reload watcher."""
        self._stop_reload.set()
        if self._reload_thread:
            self._reload_thread.join(timeout=5)
            logger.info("Hot-reload stopped")
    
    def on_reload(self, callback: Callable[[List[str]], None]):
        """
        Register callback for configuration reload.
        
        Args:
            callback: Function accepting list of changes
        """
        self._reload_callbacks.append(callback)
    
    def get_sensitive_value(self, env_var: str) -> Optional[str]:
        """
        Get sensitive value from environment variable.
        
        Args:
            env_var: Environment variable name
        
        Returns:
            Value or None if not set
        """
        return os.getenv(env_var)
    
    def mask_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create masked copy of configuration for logging.
        
        Args:
            config: Configuration dictionary
        
        Returns:
            Masked configuration
        """
        masked = {}
        
        for key, value in config.items():
            if any(s in key.lower() for s in self.SENSITIVE_KEYS):
                masked[key] = '***'
            elif isinstance(value, dict):
                masked[key] = self.mask_config(value)
            elif isinstance(value, list):
                masked[key] = [
                    self.mask_config(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                masked[key] = value
        
        return masked
    
    def print_config(self, mask_sensitive: bool = True):
        """Print current configuration."""
        with self._lock:
            config = self._config
            if mask_sensitive:
                config = self.mask_config(config)
        
        print("=" * 60)
        print("Current Configuration:")
        print("=" * 60)
        print(json.dumps(config, indent=2))
        print("=" * 60)


def load_config(config_path: str = 'config.json',
                validate: bool = True,
                substitute_env: bool = True) -> Dict[str, Any]:
    """
    Convenience function to load configuration.
    
    Args:
        config_path: Path to configuration file
        validate: Whether to validate
        substitute_env: Whether to substitute environment variables
    
    Returns:
        Configuration dictionary
    """
    loader = ConfigLoader(config_path)
    return loader.load(validate=validate, substitute_env=substitute_env)


# Example usage
if __name__ == '__main__':
    # Create sample config
    sample_config = {
        "version": "3.1.0",
        "server": {
            "host": "0.0.0.0",
            "port": 9999,
            "data_dir": "./data"
        },
        "database": {
            "encryption": {
                "enabled": True,
                "passphrase_env": "KOSDB_SECRET"
            }
        }
    }
    
    # Save sample
    with open('config.json', 'w') as f:
        json.dump(sample_config, f, indent=2)
    
    # Load with env substitution
    os.environ['KOSDB_SECRET'] = 'my-secret-key'
    
    loader = ConfigLoader('config.json')
    config = loader.load()
    
    print("Loaded configuration:")
    loader.print_config()
