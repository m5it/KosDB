"""
Multi-Tenant Architecture for KosDB

Implements namespace isolation with tenant management, resource quotas,
and row-level security policies.
"""

import time
import json
import logging
import threading
from enum import Enum
from typing import Dict, List, Optional, Any, Set, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class TenantError(Exception):
    """Raised when tenant operations fail."""
    pass


class QuotaExceededError(TenantError):
    """Raised when resource quota is exceeded."""
    pass


class TenantNotFoundError(TenantError):
    """Raised when tenant doesn't exist."""
    pass


class ResourceType(Enum):
    """Types of resources that can be quota-limited."""
    STORAGE = "storage"
    QUERIES_PER_MINUTE = "qpm"
    CONNECTIONS = "connections"
    TABLES = "tables"
    ROWS = "rows"


@dataclass
class ResourceQuota:
    """Resource quota configuration for a tenant."""
    storage_bytes: int = 10 * 1024 * 1024 * 1024
    queries_per_minute: int = 1000
    max_connections: int = 100
    max_tables: int = 100
    max_rows: int = 10_000_000
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'storage_bytes': self.storage_bytes,
            'storage_gb': round(self.storage_bytes / (1024**3), 2),
            'queries_per_minute': self.queries_per_minute,
            'max_connections': self.max_connections,
            'max_tables': self.max_tables,
            'max_rows': self.max_rows
        }


@dataclass
class ResourceUsage:
    """Current resource usage for a tenant."""
    storage_bytes: int = 0
    queries_this_minute: int = 0
    active_connections: int = 0
    table_count: int = 0
    row_count: int = 0
    last_query_time: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'storage_bytes': self.storage_bytes,
            'storage_gb': round(self.storage_bytes / (1024**3), 4),
            'queries_this_minute': self.queries_this_minute,
            'active_connections': self.active_connections,
            'table_count': self.table_count,
            'row_count': self.row_count
        }


@dataclass
class RowLevelPolicy:
    """Row-level security policy."""
    name: str
    table_pattern: str
    condition: Callable[[Dict[str, Any], str], bool]
    enabled: bool = True


class Tenant:
    """Represents a tenant in the multi-tenant system."""
    
    def __init__(
        self,
        tenant_id: str,
        name: str,
        quota: Optional[ResourceQuota] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.tenant_id = tenant_id
        self.name = name
        self.quota = quota or ResourceQuota()
        self.usage = ResourceUsage()
        self.metadata = metadata or {}
        self.created_at = time.time()
        self.is_active = True
        
        self.row_policies: List[RowLevelPolicy] = []
        self.default_deny = True
        
        self._connections: Set[str] = set()
        self._lock = threading.RLock()
        self._query_timestamps: List[float] = []
    
    def check_quota(self, resource_type: ResourceType, amount: int = 1) -> bool:
        """Check if operation would exceed quota."""
        with self._lock:
            if resource_type == ResourceType.STORAGE:
                return (self.usage.storage_bytes + amount) <= self.quota.storage_bytes
            elif resource_type == ResourceType.QUERIES_PER_MINUTE:
                self._cleanup_old_queries()
                return (len(self._query_timestamps) + amount) <= self.quota.queries_per_minute
            elif resource_type == ResourceType.CONNECTIONS:
                return (self.usage.active_connections + amount) <= self.quota.max_connections
            elif resource_type == ResourceType.TABLES:
                return (self.usage.table_count + amount) <= self.quota.max_tables
            elif resource_type == ResourceType.ROWS:
                return (self.usage.row_count + amount) <= self.quota.max_rows
            return True
    
    def _cleanup_old_queries(self):
        """Remove query timestamps older than 1 minute."""
        now = time.time()
        cutoff = now - 60
        self._query_timestamps = [ts for ts in self._query_timestamps if ts > cutoff]
    
    def record_query(self):
        """Record a query for rate limiting."""
        with self._lock:
            self._cleanup_old_queries()
            self._query_timestamps.append(time.time())
            self.usage.queries_this_minute = len(self._query_timestamps)
    
    def add_connection(self, connection_id: str) -> bool:
        """Add a connection for this tenant."""
        with self._lock:
            if len(self._connections) >= self.quota.max_connections:
                return False
            
            self._connections.add(connection_id)
            self.usage.active_connections = len(self._connections)
            return True
    
    def remove_connection(self, connection_id: str):
        """Remove a connection."""
        with self._lock:
            self._connections.discard(connection_id)
            self.usage.active_connections = len(self._connections)
    
    def update_usage(self, resource_type: ResourceType, delta: int):
        """Update resource usage."""
        with self._lock:
            if resource_type == ResourceType.STORAGE:
                self.usage.storage_bytes = max(0, self.usage.storage_bytes + delta)
            elif resource_type == ResourceType.TABLES:
                self.usage.table_count = max(0, self.usage.table_count + delta)
            elif resource_type == ResourceType.ROWS:
                self.usage.row_count = max(0, self.usage.row_count + delta)
    
    def add_row_policy(self, policy: RowLevelPolicy):
        """Add row-level security policy."""
        with self._lock:
            self.row_policies.append(policy)
            logger.info(f"Added row policy {policy.name} for tenant {self.tenant_id}")
    
    def remove_row_policy(self, policy_name: str) -> bool:
        """Remove row-level security policy."""
        with self._lock:
            for i, policy in enumerate(self.row_policies):
                if policy.name == policy_name:
                    self.row_policies.pop(i)
                    logger.info(f"Removed row policy {policy_name}")
                    return True
            return False
    
    def check_row_access(self, table_name: str, row: Dict[str, Any]) -> bool:
        """Check if tenant can access a row based on RLS policies."""
        with self._lock:
            applicable_policies = [
                p for p in self.row_policies
                if p.enabled and self._matches_pattern(table_name, p.table_pattern)
            ]
            
            if not applicable_policies:
                return not self.default_deny
            
            for policy in applicable_policies:
                try:
                    if policy.condition(row, self.tenant_id):
                        return True
                except Exception as e:
                    logger.warning(f"Policy {policy.name} error: {e}")
            
            return False
    
    def _matches_pattern(self, table_name: str, pattern: str) -> bool:
        """Check if table name matches pattern."""
        import fnmatch
        return fnmatch.fnmatch(table_name, pattern)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get tenant statistics."""
        with self._lock:
            return {
                'tenant_id': self.tenant_id,
                'name': self.name,
                'created_at': self.created_at,
                'is_active': self.is_active,
                'quota': self.quota.to_dict(),
                'usage': self.usage.to_dict(),
                'row_policies': len(self.row_policies),
                'active_connections': len(self._connections)
            }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'tenant_id': self.tenant_id,
            'name': self.name,
            'created_at': self.created_at,
            'is_active': self.is_active,
            'metadata': self.metadata
        }


class TenantManager:
    """Manages all tenants in the system."""
    
    def __init__(self):
        self._tenants: Dict[str, Tenant] = {}
        self._default_tenant: Optional[str] = None
        self._lock = threading.RLock()
    
    def create_tenant(
        self,
        tenant_id: str,
        name: str,
        quota: Optional[ResourceQuota] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tenant:
        """Create a new tenant."""
        with self._lock:
            if tenant_id in self._tenants:
                raise TenantError(f"Tenant {tenant_id} already exists")
            
            tenant = Tenant(tenant_id, name, quota, metadata)
            self._tenants[tenant_id] = tenant
            
            logger.info(f"Created tenant: {tenant_id} ({name})")
            return tenant
    
    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """Get tenant by ID."""
        with self._lock:
            return self._tenants.get(tenant_id)
    
    def drop_tenant(self, tenant_id: str) -> bool:
        """Drop a tenant and all associated data."""
        with self._lock:
            if tenant_id not in self._tenants:
                return False
            
            tenant = self._tenants.pop(tenant_id)
            
            for conn_id in list(tenant._connections):
                tenant.remove_connection(conn_id)
            
            logger.info(f"Dropped tenant: {tenant_id}")
            return True
    
    def list_tenants(self, include_inactive: bool = False) -> List[Tenant]:
        """List all tenants."""
        with self._lock:
            tenants = list(self._tenants.values())
            if not include_inactive:
                tenants = [t for t in tenants if t.is_active]
            return tenants
    
    def set_default_tenant(self, tenant_id: str):
        """Set default tenant for new connections."""
        with self._lock:
            if tenant_id not in self._tenants:
                raise TenantNotFoundError(f"Tenant {tenant_id} not found")
            self._default_tenant = tenant_id
    
    def get_default_tenant(self) -> Optional[str]:
        """Get default tenant ID."""
        with self._lock:
            return self._default_tenant
    
    def get_global_stats(self) -> Dict[str, Any]:
        """Get global statistics across all tenants."""
        with self._lock:
            total_storage = sum(t.usage.storage_bytes for t in self._tenants.values())
            total_tables = sum(t.usage.table_count for t in self._tenants.values())
            total_rows = sum(t.usage.row_count for t in self._tenants.values())
            
            return {
                'tenant_count': len(self._tenants),
                'active_tenants': sum(1 for t in self._tenants.values() if t.is_active),
                'total_storage_bytes': total_storage,
                'total_storage_gb': round(total_storage / (1024**3), 2),
                'total_tables': total_tables,
                'total_rows': total_rows
            }


_tenant_manager = TenantManager()


def get_tenant_manager() -> TenantManager:
    """Get global tenant manager."""
    return _tenant_manager


class TenantContext:
    """Context manager for tenant-scoped operations."""
    
    def __init__(self, tenant_id: str, connection_id: Optional[str] = None):
        self.tenant_id = tenant_id
        self.connection_id = connection_id
        self.tenant: Optional[Tenant] = None
    
    def __enter__(self) -> Tenant:
        manager = get_tenant_manager()
        self.tenant = manager.get_tenant(self.tenant_id)
        
        if not self.tenant:
            raise TenantNotFoundError(f"Tenant {self.tenant_id} not found")
        
        if self.connection_id:
            if not self.tenant.add_connection(self.connection_id):
                raise QuotaExceededError("Connection limit exceeded")
        
        return self.tenant
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.tenant and self.connection_id:
            self.tenant.remove_connection(self.connection_id)
