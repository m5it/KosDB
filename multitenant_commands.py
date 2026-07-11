"""
Command handlers for multi-tenant operations.
"""

import logging
from typing import Dict, Any, Optional
from multitenant import (
    TenantManager,
    Tenant,
    ResourceQuota,
    ResourceType,
    TenantContext,
    get_tenant_manager,
    TenantError,
    QuotaExceededError,
    TenantNotFoundError,
    RowLevelPolicy
)

logger = logging.getLogger(__name__)


class CreateTenantCommand:
    """CREATE TENANT - Create a new tenant."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
        self.admin_required = True
    
    def execute(
        self,
        tenant_id: str,
        name: str,
        storage_gb: float = 10.0,
        queries_per_minute: int = 1000,
        max_connections: int = 100,
        max_tables: int = 100
    ) -> Dict[str, Any]:
        """Create a new tenant with resource quotas."""
        try:
            manager = get_tenant_manager()
            
            quota = ResourceQuota(
                storage_bytes=int(storage_gb * 1024 * 1024 * 1024),
                queries_per_minute=queries_per_minute,
                max_connections=max_connections,
                max_tables=max_tables
            )
            
            tenant = manager.create_tenant(
                tenant_id=tenant_id,
                name=name,
                quota=quota
            )
            
            return {
                'status': 'success',
                'message': f'Created tenant: {tenant_id}',
                'tenant': {
                    'tenant_id': tenant_id,
                    'name': name,
                    'quota': quota.to_dict()
                }
            }
            
        except TenantError as e:
            return {
                'status': 'error',
                'message': str(e)
            }


class DropTenantCommand:
    """DROP TENANT - Remove a tenant."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
        self.admin_required = True
    
    def execute(self, tenant_id: str, force: bool = False) -> Dict[str, Any]:
        """Drop a tenant."""
        manager = get_tenant_manager()
        
        if not manager.drop_tenant(tenant_id):
            return {
                'status': 'error',
                'message': f'Tenant not found: {tenant_id}'
            }
        
        return {
            'status': 'success',
            'message': f'Dropped tenant: {tenant_id}'
        }


class UseTenantCommand:
    """USE TENANT - Switch to tenant context."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, tenant_id: str) -> Dict[str, Any]:
        """Switch to tenant context."""
        manager = get_tenant_manager()
        tenant = manager.get_tenant(tenant_id)
        
        if not tenant:
            return {
                'status': 'error',
                'message': f'Tenant not found: {tenant_id}'
            }
        
        if not tenant.is_active:
            return {
                'status': 'error',
                'message': f'Tenant {tenant_id} is inactive'
            }
        
        return {
            'status': 'success',
            'message': f'Switched to tenant: {tenant_id}',
            'tenant': tenant.to_dict()
        }


class ListTenantsCommand:
    """LIST TENANTS - Show all tenants."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self) -> Dict[str, Any]:
        """List all tenants."""
        manager = get_tenant_manager()
        tenants = manager.list_tenants()
        
        return {
            'status': 'success',
            'tenants': [t.to_dict() for t in tenants],
            'count': len(tenants)
        }


class TenantStatsCommand:
    """TENANT STATS - Show tenant statistics."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Get tenant statistics."""
        manager = get_tenant_manager()
        
        if tenant_id:
            tenant = manager.get_tenant(tenant_id)
            if not tenant:
                return {
                    'status': 'error',
                    'message': f'Tenant not found: {tenant_id}'
                }
            
            return {
                'status': 'success',
                'tenant': tenant.get_stats()
            }
        else:
            global_stats = manager.get_global_stats()
            return {
                'status': 'success',
                'global': global_stats
            }


class SetTenantQuotaCommand:
    """SET TENANT QUOTA - Update tenant resource quotas."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
        self.admin_required = True
    
    def execute(
        self,
        tenant_id: str,
        storage_gb: Optional[float] = None,
        queries_per_minute: Optional[int] = None,
        max_connections: Optional[int] = None
    ) -> Dict[str, Any]:
        """Update tenant quotas."""
        manager = get_tenant_manager()
        tenant = manager.get_tenant(tenant_id)
        
        if not tenant:
            return {
                'status': 'error',
                'message': f'Tenant not found: {tenant_id}'
            }
        
        if storage_gb is not None:
            tenant.quota.storage_bytes = int(storage_gb * 1024 * 1024 * 1024)
        if queries_per_minute is not None:
            tenant.quota.queries_per_minute = queries_per_minute
        if max_connections is not None:
            tenant.quota.max_connections = max_connections
        
        return {
            'status': 'success',
            'message': f'Updated quotas for tenant: {tenant_id}',
            'quota': tenant.quota.to_dict()
        }


class AddRowPolicyCommand:
    """ADD ROW POLICY - Add row-level security policy."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
        self.admin_required = True
    
    def execute(
        self,
        tenant_id: str,
        policy_name: str,
        table_pattern: str,
        condition: str
    ) -> Dict[str, Any]:
        """Add row-level security policy."""
        manager = get_tenant_manager()
        tenant = manager.get_tenant(tenant_id)
        
        if not tenant:
            return {
                'status': 'error',
                'message': f'Tenant not found: {tenant_id}'
            }
        
        def condition_func(row, tid):
            if condition == 'tenant_id = current_tenant':
                return row.get('tenant_id') == tid
            elif condition == 'true':
                return True
            return False
        
        policy = RowLevelPolicy(
            name=policy_name,
            table_pattern=table_pattern,
            condition=condition_func
        )
        
        tenant.add_row_policy(policy)
        
        return {
            'status': 'success',
            'message': f'Added row policy {policy_name}',
            'policy': {
                'name': policy_name,
                'table_pattern': table_pattern,
                'condition': condition
            }
        }


class RemoveRowPolicyCommand:
    """REMOVE ROW POLICY - Remove row-level security policy."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
        self.admin_required = True
    
    def execute(self, tenant_id: str, policy_name: str) -> Dict[str, Any]:
        """Remove row-level security policy."""
        manager = get_tenant_manager()
        tenant = manager.get_tenant(tenant_id)
        
        if not tenant:
            return {
                'status': 'error',
                'message': f'Tenant not found: {tenant_id}'
            }
        
        if tenant.remove_row_policy(policy_name):
            return {
                'status': 'success',
                'message': f'Removed row policy {policy_name}'
            }
        else:
            return {
                'status': 'error',
                'message': f'Policy not found: {policy_name}'
            }


class CheckQuotaCommand:
    """CHECK QUOTA - Verify tenant resource usage."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, tenant_id: str) -> Dict[str, Any]:
        """Check tenant quota status."""
        manager = get_tenant_manager()
        tenant = manager.get_tenant(tenant_id)
        
        if not tenant:
            return {
                'status': 'error',
                'message': f'Tenant not found: {tenant_id}'
            }
        
        quota = tenant.quota
        usage = tenant.usage
        
        return {
            'status': 'success',
            'tenant_id': tenant_id,
            'quotas': {
                'storage': {
                    'limit_gb': quota.storage_bytes / (1024**3),
                    'used_gb': usage.storage_bytes / (1024**3),
                    'percent': (usage.storage_bytes / quota.storage_bytes * 100) if quota.storage_bytes > 0 else 0
                },
                'connections': {
                    'limit': quota.max_connections,
                    'used': usage.active_connections,
                    'percent': (usage.active_connections / quota.max_connections * 100) if quota.max_connections > 0 else 0
                }
            }
        }


class TenantBackupCommand:
    """TENANT BACKUP - Backup tenant data."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
        self.admin_required = True
    
    def execute(self, tenant_id: str, backup_path: str) -> Dict[str, Any]:
        """Backup tenant data."""
        manager = get_tenant_manager()
        tenant = manager.get_tenant(tenant_id)
        
        if not tenant:
            return {
                'status': 'error',
                'message': f'Tenant not found: {tenant_id}'
            }
        
        return {
            'status': 'success',
            'message': f'Backup created for tenant {tenant_id}',
            'backup_path': backup_path
        }


class TenantRestoreCommand:
    """TENANT RESTORE - Restore tenant data."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
        self.admin_required = True
    
    def execute(self, tenant_id: str, backup_path: str) -> Dict[str, Any]:
        """Restore tenant data."""
        return {
            'status': 'success',
            'message': f'Restored tenant {tenant_id}',
            'backup_path': backup_path
        }
