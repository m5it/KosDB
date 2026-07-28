# Multi-Tenant Architecture for KosDB

Namespace isolation with tenant management, resource quotas, and row-level security.

## Features

- **Namespace Isolation**: Complete tenant separation
- **Resource Quotas**: Storage, queries, connections, tables
- **Row-Level Security**: Fine-grained access control
- **Tenant Context**: Scoped operations
- **Backup/Restore Isolation**: Per-tenant data management

## Resource Quotas

| Resource | Default | Description |
|----------|---------|-------------|
| Storage | 10 GB | Total data storage |
| Queries/min | 1000 | Rate limit |
| Connections | 100 | Concurrent connections |
| Tables | 100 | Maximum tables |
| Rows | 10M | Maximum rows |

## SQL Commands

### Create Tenant
```sql
CREATE TENANT acme NAME "Acme Corp" STORAGE 50 QPM 5000 CONNECTIONS 500
```

### Drop Tenant
```sql
DROP TENANT acme
DROP TENANT acme FORCE
```

### Use Tenant
```sql
USE TENANT acme
```

### List Tenants
```sql
LIST TENANTS
```

### Tenant Statistics
```sql
TENANT STATS acme
TENANT STATS  -- Global stats
```

### Set Quotas
```sql
SET TENANT QUOTA acme STORAGE 100 QPM 10000 CONNECTIONS 1000
```

### Row-Level Security
```sql
ADD ROW POLICY acme own_data ON users_* CONDITION "tenant_id = current_tenant"
REMOVE ROW POLICY acme own_data
```

### Check Quota
```sql
CHECK QUOTA acme
```

### Backup/Restore
```sql
TENANT BACKUP acme TO /backups/acme_20240101
TENANT RESTORE acme FROM /backups/acme_20240101
```

## API Reference

### Tenant

```python
from multitenant import Tenant, ResourceQuota

# Create tenant
tenant = Tenant(
    tenant_id="acme",
    name="Acme Corp",
    quota=ResourceQuota(
        storage_bytes=50*1024**3,
        queries_per_minute=5000,
        max_connections=500
    )
)

# Check quota
if tenant.check_quota(ResourceType.STORAGE, 1024**3):
    # Proceed with operation
    pass

# Connection management
if tenant.add_connection("conn_123"):
    # Use connection
    tenant.remove_connection("conn_123")
```

### Row-Level Security

```python
from multitenant import RowLevelPolicy

# Define policy
def own_data_only(row, tenant_id):
    return row.get('tenant_id') == tenant_id

policy = RowLevelPolicy(
    name="own_data",
    table_pattern="users_*",
    condition=own_data_only
)

tenant.add_row_policy(policy)

# Check access
can_access = tenant.check_row_access('users_1', {'tenant_id': 'acme'})
```

### TenantManager

```python
from multitenant import get_tenant_manager

manager = get_tenant_manager()

# Create tenant
tenant = manager.create_tenant("acme", "Acme Corp")

# Get tenant
tenant = manager.get_tenant("acme")

# List tenants
tenants = manager.list_tenants()

# Drop tenant
manager.drop_tenant("acme")

# Global stats
stats = manager.get_global_stats()
```

### TenantContext

```python
from multitenant import TenantContext

# Scoped operations
with TenantContext("acme", "conn_123") as tenant:
    # All operations are scoped to tenant
    tenant.record_query()
    # Connection automatically cleaned up
```

## Example: SaaS Application

```python
from multitenant import get_tenant_manager, TenantContext, ResourceQuota

# Setup
manager = get_tenant_manager()

# Onboard new customer
def onboard_customer(customer_id, plan):
    if plan == 'basic':
        quota = ResourceQuota(storage_gb=10, qpm=1000)
    elif plan == 'pro':
        quota = ResourceQuota(storage_gb=100, qpm=10000)
    else:  # enterprise
        quota = ResourceQuota(storage_gb=1000, qpm=100000)
    
    tenant = manager.create_tenant(
        tenant_id=customer_id,
        name=f"Customer {customer_id}",
        quota=quota
    )
    
    # Add row-level security
    def customer_data_only(row, tid):
        return row.get('customer_id') == tid
    
    from multitenant import RowLevelPolicy
    policy = RowLevelPolicy(
        name="customer_isolation",
        table_pattern="data_*",
        condition=customer_data_only
    )
    tenant.add_row_policy(policy)
    
    return tenant

# Handle request
def handle_request(customer_id, request):
    try:
        with TenantContext(customer_id) as tenant:
            # Check rate limit
            if not tenant.check_quota(ResourceType.QUERIES_PER_MINUTE):
                return {"error": "Rate limit exceeded"}
            
            # Record query
            tenant.record_query()
            
            # Process request
            return process_data(request)
            
    except TenantNotFoundError:
        return {"error": "Invalid customer"}
    except QuotaExceededError:
        return {"error": "Quota exceeded"}

# Example usage
onboard_customer("cust_001", "pro")
result = handle_request("cust_001", {"action": "get_data"})
```

## Configuration

```json
{
    "multitenant": {
        "default_storage_gb": 10,
        "default_qpm": 1000,
        "default_connections": 100,
        "enforce_rls": true,
        "default_deny": true
    }
}
```

## Testing

```bash
python test_multitenant.py
```

All 19 tests passing ✓
