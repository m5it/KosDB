#!/usr/bin/env python3
"""
Sort Engine Configuration for KosDB

Configuration management for sort engine with support for:
- Environment variables
- Config files (JSON/YAML)
- Runtime configuration
- Per-query overrides

Usage:
    from sort_config import SortConfig
    
    # Load from environment
    config = SortConfig.from_env()
    
    # Load from file
    config = SortConfig.from_file('kosdb.yaml')
    
    # Create with overrides
    config = SortConfig(default_backend='madsort_rust', topk_threshold=0.05)
"""

import os
import json
import logging
from typing import Optional, Dict, Any, Union
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class SortConfig:
    """
    Configuration for sort engine.
    
    Attributes:
        default_backend: Default sort backend ('auto', 'builtin', 'madsort_py', 'madsort_rust')
        auto_fallback: Allow fallback to builtin on failure
        strict_mode: Raise errors instead of falling back
        topk_threshold: Ratio threshold for top-K optimization (e.g., 0.1 = 10%)
        small_dataset_threshold: Rows below this use builtin
        medium_dataset_threshold: Rows below this use madS0rt_py
        large_dataset_threshold: Rows above this prefer madS0rt_rust
        enable_sort_heuristics: Use query optimizer sort heuristics
        enable_index_sort: Use index order when possible
        max_memory_sort_mb: Maximum memory for in-memory sort before external
        parallel_sort_threshold: Minimum rows to use parallel sort
        cache_sort_plans: Cache sort strategy decisions
    """
    
    # Backend selection
    default_backend: str = 'auto'
    auto_fallback: bool = True
    strict_mode: bool = False
    
    # Heuristic thresholds
    topk_threshold: float = 0.1
    small_dataset_threshold: int = 1000
    medium_dataset_threshold: int = 100000
    large_dataset_threshold: int = 1000000
    
    # Feature toggles
    enable_sort_heuristics: bool = True
    enable_index_sort: bool = True
    cache_sort_plans: bool = True
    
    # Resource limits
    max_memory_sort_mb: int = 100
    parallel_sort_threshold: int = 100000
    
    # Advanced options
    custom_params: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_env(cls) -> 'SortConfig':
        """
        Load configuration from environment variables.
        
        Environment variables:
            KOSDB_SORT_BACKEND - Default backend
            KOSDB_SORT_AUTO_FALLBACK - Enable fallback (true/false)
            KOSDB_SORT_STRICT_MODE - Strict mode (true/false)
            KOSDB_SORT_TOPK_THRESHOLD - Top-K threshold (float)
            KOSDB_SORT_SMALL_THRESHOLD - Small dataset threshold
            KOSDB_SORT_MEDIUM_THRESHOLD - Medium dataset threshold
            KOSDB_SORT_ENABLE_HEURISTICS - Enable heuristics (true/false)
            KOSDB_SORT_ENABLE_INDEX - Enable index sort (true/false)
            KOSDB_SORT_MAX_MEMORY_MB - Max memory for sort
        
        Returns:
            SortConfig instance
        """
        config = cls()
        
        # Backend selection
        if 'KOSDB_SORT_BACKEND' in os.environ:
            config.default_backend = os.environ['KOSDB_SORT_BACKEND']
        
        # Boolean flags
        if 'KOSDB_SORT_AUTO_FALLBACK' in os.environ:
            config.auto_fallback = os.environ['KOSDB_SORT_AUTO_FALLBACK'].lower() == 'true'
        
        if 'KOSDB_SORT_STRICT_MODE' in os.environ:
            config.strict_mode = os.environ['KOSDB_SORT_STRICT_MODE'].lower() == 'true'
        
        if 'KOSDB_SORT_ENABLE_HEURISTICS' in os.environ:
            config.enable_sort_heuristics = os.environ['KOSDB_SORT_ENABLE_HEURISTICS'].lower() == 'true'
        
        if 'KOSDB_SORT_ENABLE_INDEX' in os.environ:
            config.enable_index_sort = os.environ['KOSDB_SORT_ENABLE_INDEX'].lower() == 'true'
        
        if 'KOSDB_SORT_CACHE_PLANS' in os.environ:
            config.cache_sort_plans = os.environ['KOSDB_SORT_CACHE_PLANS'].lower() == 'true'
        
        # Numeric thresholds
        try:
            if 'KOSDB_SORT_TOPK_THRESHOLD' in os.environ:
                config.topk_threshold = float(os.environ['KOSDB_SORT_TOPK_THRESHOLD'])
            
            if 'KOSDB_SORT_SMALL_THRESHOLD' in os.environ:
                config.small_dataset_threshold = int(os.environ['KOSDB_SORT_SMALL_THRESHOLD'])
            
            if 'KOSDB_SORT_MEDIUM_THRESHOLD' in os.environ:
                config.medium_dataset_threshold = int(os.environ['KOSDB_SORT_MEDIUM_THRESHOLD'])
            
            if 'KOSDB_SORT_MAX_MEMORY_MB' in os.environ:
                config.max_memory_sort_mb = int(os.environ['KOSDB_SORT_MAX_MEMORY_MB'])
            
            if 'KOSDB_SORT_PARALLEL_THRESHOLD' in os.environ:
                config.parallel_sort_threshold = int(os.environ['KOSDB_SORT_PARALLEL_THRESHOLD'])
        
        except ValueError as e:
            logger.warning(f"Invalid numeric value in environment: {e}")
        
        logger.info(f"Loaded sort config from environment: backend={config.default_backend}")
        return config
    
    @classmethod
    def from_file(cls, filepath: str) -> 'SortConfig':
        """
        Load configuration from file (JSON or YAML).
        
        Args:
            filepath: Path to config file
        
        Returns:
            SortConfig instance
        """
        config = cls()
        
        if not os.path.exists(filepath):
            logger.warning(f"Config file not found: {filepath}")
            return config
        
        try:
            with open(filepath, 'r') as f:
                if filepath.endswith('.yaml') or filepath.endswith('.yml'):
                    try:
                        import yaml
                        data = yaml.safe_load(f)
                    except ImportError:
                        logger.warning("PyYAML not installed, cannot parse YAML")
                        return config
                else:
                    data = json.load(f)
            
            # Extract sort configuration section
            if 'sort' in data:
                sort_data = data['sort']
            elif 'sort_engine' in data:
                sort_data = data['sort_engine']
            else:
                sort_data = data
            
            # Map file keys to config attributes
            key_mapping = {
                'backend': 'default_backend',
                'default_backend': 'default_backend',
                'auto_fallback': 'auto_fallback',
                'strict_mode': 'strict_mode',
                'topk_threshold': 'topk_threshold',
                'small_threshold': 'small_dataset_threshold',
                'medium_threshold': 'medium_dataset_threshold',
                'large_threshold': 'large_dataset_threshold',
                'enable_heuristics': 'enable_sort_heuristics',
                'enable_index_sort': 'enable_index_sort',
                'max_memory_mb': 'max_memory_sort_mb',
                'cache_plans': 'cache_sort_plans',
            }
            
            for file_key, attr_name in key_mapping.items():
                if file_key in sort_data:
                    setattr(config, attr_name, sort_data[file_key])
            
            # Store any extra params
            config.custom_params = {
                k: v for k, v in sort_data.items() 
                if k not in key_mapping
            }
            
            logger.info(f"Loaded sort config from file: {filepath}")
        
        except Exception as e:
            logger.error(f"Failed to load config from {filepath}: {e}")
        
        return config
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SortConfig':
        """
        Create configuration from dictionary.
        
        Args:
            data: Configuration dictionary
        
        Returns:
            SortConfig instance
        """
        config = cls()
        
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
            else:
                config.custom_params[key] = value
        
        return config
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary.
        
        Returns:
            Dictionary representation
        """
        return asdict(self)
    
    def to_file(self, filepath: str, format: str = 'json'):
        """
        Save configuration to file.
        
        Args:
            filepath: Output file path
            format: 'json' or 'yaml'
        """
        data = self.to_dict()
        
        with open(filepath, 'w') as f:
            if format == 'yaml':
                try:
                    import yaml
                    yaml.dump({'sort': data}, f, default_flow_style=False)
                except ImportError:
                    logger.warning("PyYAML not installed, saving as JSON")
                    json.dump(data, f, indent=2)
            else:
                json.dump(data, f, indent=2)
        
        logger.info(f"Saved sort config to {filepath}")
    
    def get_backend_config(self) -> Dict[str, Any]:
        """
        Get configuration for SortEngine initialization.
        
        Returns:
            Dict with backend settings
        """
        return {
            'backend': self.default_backend,
            'strict': self.strict_mode,
        }
    
    def get_heuristic_config(self) -> Dict[str, Any]:
        """
        Get configuration for SortHeuristics.
        
        Returns:
            Dict with heuristic thresholds
        """
        return {
            'small_threshold': self.small_dataset_threshold,
            'medium_threshold': self.medium_dataset_threshold,
            'large_threshold': self.large_dataset_threshold,
            'topk_threshold': self.topk_threshold,
            'enable_index_sort': self.enable_index_sort,
        }
    
    def should_use_topk(self, limit: int, total_rows: int) -> bool:
        """
        Check if top-K optimization should be used.
        
        Args:
            limit: LIMIT value
            total_rows: Estimated total rows
        
        Returns:
            True if top-K optimization recommended
        """
        if limit <= 0 or total_rows <= 0:
            return False
        
        ratio = limit / total_rows
        return ratio < self.topk_threshold
    
    def select_backend_for_size(self, num_rows: int) -> str:
        """
        Select appropriate backend based on data size.
        
        Args:
            num_rows: Number of rows to sort
        
        Returns:
            Recommended backend name
        """
        if num_rows < self.small_dataset_threshold:
            return 'builtin'
        elif num_rows < self.medium_dataset_threshold:
            return 'madsort_py' if self.default_backend == 'auto' else self.default_backend
        else:
            return 'madsort_rust' if self.default_backend == 'auto' else self.default_backend
    
    def validate(self) -> bool:
        """
        Validate configuration values.
        
        Returns:
            True if valid, raises ValueError otherwise
        """
        valid_backends = ['auto', 'builtin', 'madsort_py', 'madsort_rust']
        if self.default_backend not in valid_backends:
            raise ValueError(f"Invalid backend: {self.default_backend}")
        
        if not (0 < self.topk_threshold <= 1):
            raise ValueError(f"Invalid topk_threshold: {self.topk_threshold}")
        
        if self.small_dataset_threshold >= self.medium_dataset_threshold:
            raise ValueError("small_threshold must be less than medium_threshold")
        
        if self.medium_dataset_threshold >= self.large_dataset_threshold:
            raise ValueError("medium_threshold must be less than large_threshold")
        
        return True


class ConfigManager:
    """
    Manages sort configuration with caching and reloading.
    
    Usage:
        manager = ConfigManager()
        config = manager.get_config()  # Loads from env/file/cache
        
        # Force reload
        config = manager.reload()
    """
    
    def __init__(self, config_file: Optional[str] = None):
        """
        Initialize config manager.
        
        Args:
            config_file: Optional path to config file
        """
        self.config_file = config_file
        self._cached_config: Optional[SortConfig] = None
        self._cache_time: float = 0
        self._cache_ttl: float = 60  # 60 second cache
    
    def get_config(self) -> SortConfig:
        """
        Get current configuration (with caching).
        
        Returns:
            SortConfig instance
        """
        import time
        
        # Check cache
        if self._cached_config is not None:
            if time.time() - self._cache_time < self._cache_ttl:
                return self._cached_config
        
        # Load fresh config
        config = self._load_config()
        self._cached_config = config
        self._cache_time = time.time()
        
        return config
    
    def _load_config(self) -> SortConfig:
        """Load configuration from sources."""
        # Start with defaults
        config = SortConfig()
        
        # Apply environment overrides
        env_config = SortConfig.from_env()
        self._merge_config(config, env_config)
        
        # Apply file overrides if specified
        if self.config_file:
            file_config = SortConfig.from_file(self.config_file)
            self._merge_config(config, file_config)
        
        # Validate
        config.validate()
        
        return config
    
    def _merge_config(self, base: SortConfig, override: SortConfig):
        """Merge override config into base."""
        for field_name in base.__dataclass_fields__:
            override_value = getattr(override, field_name)
            base_value = getattr(base, field_name)
            
            # Only override if different from default
            if override_value != base_value:
                setattr(base, field_name, override_value)
    
    def reload(self) -> SortConfig:
        """Force reload configuration."""
        self._cached_config = None
        return self.get_config()
    
    def set_config_file(self, filepath: str):
        """Change config file and reload."""
        self.config_file = filepath
        self.reload()


# Global config manager instance
_config_manager: Optional[ConfigManager] = None


def get_sort_config(config_file: Optional[str] = None) -> SortConfig:
    """
    Get global sort configuration.
    
    Args:
        config_file: Optional config file path
    
    Returns:
        SortConfig instance
    """
    global _config_manager
    
    if _config_manager is None or config_file:
        _config_manager = ConfigManager(config_file)
    
    return _config_manager.get_config()


def reload_sort_config() -> SortConfig:
    """Reload global sort configuration."""
    global _config_manager
    
    if _config_manager is None:
        _config_manager = ConfigManager()
    
    return _config_manager.reload()


# Example configuration file templates
EXAMPLE_JSON_CONFIG = '''{
  "sort": {
    "default_backend": "auto",
    "auto_fallback": true,
    "strict_mode": false,
    "topk_threshold": 0.1,
    "small_threshold": 1000,
    "medium_threshold": 100000,
    "enable_heuristics": true,
    "enable_index_sort": true,
    "max_memory_mb": 100
  }
}'''

EXAMPLE_YAML_CONFIG = '''sort:
  default_backend: auto
  auto_fallback: true
  strict_mode: false
  topk_threshold: 0.1
  small_threshold: 1000
  medium_threshold: 100000
  enable_heuristics: true
  enable_index_sort: true
  max_memory_mb: 100
'''


def create_example_config(filepath: str = 'kosdb_sort_config.json'):
    """Create example configuration file."""
    with open(filepath, 'w') as f:
        f.write(EXAMPLE_JSON_CONFIG)
    print(f"Created example config: {filepath}")


if __name__ == '__main__':
    # Demo configuration loading
    print("SortConfig Demo")
    print("=" * 50)
    
    # Default config
    config = SortConfig()
    print(f"Default backend: {config.default_backend}")
    print(f"Small threshold: {config.small_dataset_threshold}")
    
    # From environment
    print("\nEnvironment variables:")
    print("  KOSDB_SORT_BACKEND=madsort_rust")
    os.environ['KOSDB_SORT_BACKEND'] = 'madsort_rust'
    
    env_config = SortConfig.from_env()
    print(f"  Loaded backend: {env_config.default_backend}")
    
    # Backend selection
    print("\nBackend selection by size:")
    for size in [100, 10000, 1000000]:
        backend = config.select_backend_for_size(size)
        print(f"  {size:,} rows -> {backend}")
    
    # Create example
    print("\nCreating example config file...")
    create_example_config()
