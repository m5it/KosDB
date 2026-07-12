
# Multi-Tenant Batch Operations Guide

Version: 2.3.0  
Last Updated: 2024-01-15

## Overview

Multi-Tenant Batch Operations ensure batch commands respect tenant boundaries, enforce row-level security, and maintain proper resource isolation. This guide covers tenant verification, quota enforcement, and best practices.

## Features

- **Tenant Boundary Enforcement**: All commands in batch target same tenant
- **USE TENANT Persistence**: Tenant context maintained across batch
- **Row-Level Security (RLS)**: Policies enforced across batch commands
- **Quota Management**: Batch commands count toward tenant quotas
- **CDC Event Tagging**: Events properly tagged with tenant ID

## Quick Start

```python
from batch_multitenant import BatchTenantVerifier, BatchTenantExecutor

# Create verifier
verifier = BatchTenantVerifier(tenant_manager)

# Verify batch respects tenant boundaries
commands = [
    "USE TENANT tenant1;",
    "SELECT * FROM users;",
    "INSERT INTO logs VALUES (1);"
]

result = verifier.verify_batch(commands)
if result['valid']:
    print(f"Batch valid for tenant: {result['tenant_id']}")
```

## SQL Commands

### USE TENANT

```sql
-- Set tenant context for batch
USE TENANT tenant1;

-- Subsequent commands use this tenant
SELECT * FROM users;
INSERT INTO orders VALUES (1, 'item');
```

### Cross-Tenant Detection

```sql
-- This batch is INVALID (switches tenants)
USE TENANT tenant1;
SELECT * FROM users;
USE TENANT tenant2;  -- ERROR: Cannot switch tenants in batch
SELECT * FROM orders;
```

## Tenant Boundary Verification

### Automatic Verification

```python
from batch_multitenant import BatchTenantVerifier

verifier = BatchTenantVerifier(tenant_manager)

# Single tenant batch - valid
commands = [
    "USE TENANT tenant1;",
    "SELECT * FROM table1;",
    "SELECT * FROM table2;"
]
result = verifier.verify_batch(commands)
# result['valid'] == True
# result['tenant_id'] == 'tenant1'

# Multi-tenant batch - invalid
commands = [
    "USE TENANT tenant1;",
    "SELECT * FROM table1;",
    "USE TENANT tenant2;",  # Switch detected
    "SELECT * FROM table2;"
]
result = verifier.verify_batch(commands)
# result['valid'] == False
# result['error'] == 'Batch commands target multiple tenants'
```

### Verification Results

| Field | Type | Description |
|-------|------|-------------|
| `valid` | bool | Whether batch passes verification |
| `tenant_id` | str | Target tenant (or None) |
| `use_tenant_persisted` | bool | USE TENANT command found |
| `command_count` | int | Number of commands |

## Row-Level Security (RLS)

### Policy Enforcement

```python
from batch_multitenant import BatchTenantVerifier

verifier = BatchTenantVerifier(tenant_manager)

# Filter rows based on RLS policies
rows = [
    {'id': 1, 'tenant_id': 'tenant1', 'data': 'a'},
    {'id': 2, 'tenant_id': 'tenant2', 'data': 'b'},
    {'id': 3, 'tenant_id': 'tenant1', 'data': 'c'},
]

filtered = verifier.enforce_rls_policies('tenant1', 'users', rows)
# Returns only rows where tenant_id == 'tenant1'
```

### RLS in Batch Context

```python
# RLS policies are checked for each query in batch
for cmd in batch_commands:
    if is_select(cmd):
        rows = execute_query(cmd)
        filtered = verifier.enforce_rls_policies(
            current_tenant, 
            get_table_name(cmd), 
            rows
        )
        results.append(filtered)
```

## Quota Enforcement

### Batch Quota Check

```python
# Check if batch would exceed quota
result = verifier.check_tenant_quota('tenant1', command_count=100)

if not result['valid']:
    print(f"Quota exceeded: {result['error']}")
    print(f"Limit: {result['limit']}")
    print(f"Current: {result['current']}")
    print(f"Requested: {result['requested']}")
```

### Quota Types

| Resource | Description |
|----------|-------------|
| `QUERIES_PER_MINUTE` | Rate limit for queries |
| `STORAGE` | Storage space limit |
| `CONNECTIONS` | Concurrent connection limit |
| `TABLES` | Table count limit |
| `ROWS` | Row count limit |

### Batch Quota Calculation

```python
# Batch counts as N commands against quota
batch_size = len(commands)  # Each command counts separately

# Check before execution
quota_check = verifier.check_tenant_quota(tenant_id, batch_size)
if quota_check['valid']:
    # Execute batch
    results = execute_batch(commands)
    # Record usage
    for _ in commands:
        tenant.record_query()
```

## CDC Event Tagging

### Automatic Tagging

```python
from batch_multitenant import BatchTenantVerifier

verifier = BatchTenantVerifier(tenant_manager)

# Tag CDC events with tenant
events = [
    {'table': 'users', 'operation': 'INSERT', 'data': {...}},
    {'table': 'orders', 'operation': 'UPDATE', 'data': {...}},
]

tagged_events = verifier.tag_cdc_events('tenant1', events)
# Each event now has 'tenant_id': 'tenant1'
```

### CDC in Batch Context

```python
# CDC events generated during batch are automatically tagged
def execute_batch_with_cdc(commands, tenant_id):
    cdc_events = []
    
    for cmd in commands:
        result = execute(cmd)
        if generates_cdc(cmd):
            event = create_cdc_event(cmd, result)
            event['tenant_id'] = tenant_id
            cdc_events.append(event)
    
    return cdc_events
```

## Best Practices

### 1. Always Use USE TENANT

```sql
-- Good: Explicit tenant context
USE TENANT tenant1;
SELECT * FROM users;
UPDATE orders SET status = 'shipped';

-- Bad: Implicit tenant (may fail)
SELECT * FROM users;
UPDATE orders SET status = 'shipped';
```

### 2. Verify Before Execute

```python
# Always verify batch before execution
verification = verifier.verify_batch(commands)
if not verification['valid']:
    handle_error(verification['error'])
    return

# Then check quota
quota = verifier.check_tenant_quota(
    verification['tenant_id'], 
    len(commands)
)
if not quota['valid']:
    handle_quota_error(quota)
    return

# Finally execute
results = execute_batch(commands)
```

### 3. Handle Tenant Switch Errors

```python
result = executor.execute_with_tenant_check(commands, executor_fn)

if not result['success']:
    if 'tenant switch' in result['error'].lower():
        # Split into separate batches per tenant
        batches = split_by_tenant(commands)
        for batch in batches:
            execute_batch(batch)
```

### 4. Monitor Quota Usage

```python
# Check quota before large batches
if len(commands) > 100:
    quota_check = verifier.check_tenant_quota(tenant_id, len(commands))
    if not quota_check['valid']:
        # Split batch or request quota increase
        split_and_execute(commands)
```

### 5. Test RLS Policies

```python
# Always test RLS with sample data
test_rows = [
    {'tenant_id': 'tenant1', 'data': 'visible'},
    {'tenant_id': 'tenant2', 'data': 'hidden'},
]

filtered = verifier.enforce_rls_policies('tenant1', 'table', test_rows)
assert len(filtered) == 1
assert filtered[0]['tenant_id'] == 'tenant1'
```

## Error Handling

### Tenant Boundary Violation

```python
result = verifier.verify_batch(commands)

if not result['valid']:
    error_type = result['error']
    
    if 'multiple tenants' in error_type:
        # Split batch by tenant
        batches = split_by_tenant(commands)
        for batch in batches:
            execute_batch(batch)
    
    elif 'tenant not found' in error_type:
        raise TenantNotFoundError(result['tenant_id'])
```

### Quota Exceeded

```python
quota_check = verifier.check_tenant_quota(tenant_id, command_count)

if not quota_check['valid']:
    # Options:
    # 1. Split batch into smaller chunks
    # 2. Delay execution until quota resets
    # 3. Request quota increase
    # 4. Fail with clear error
    
    raise QuotaExceededError(
        f"Tenant {tenant_id} quota exceeded: "
        f"{quota_check['current']}/{quota_check['limit']}"
    )
```

## Integration with Batch Executor

```python
from batch_executor import BatchExecutor
from batch_multitenant import BatchTenantVerifier

# Create executor with tenant verification
config = {
    'multitenant_enabled': True,
    'tenant_verification': 'strict'
}

executor = BatchExecutor(parser, registry, config=config)
verifier = BatchTenantVerifier(tenant_manager)

# Execute with tenant check
commands = [
    "USE TENANT tenant1;",
    "SELECT * FROM users;",
    "INSERT INTO logs VALUES (1);"
]

# Verify first
verification = verifier.verify_batch(commands)
if verification['valid']:
    result = executor.execute_batch(
        commands, 
        client_state={'tenant_id': verification['tenant_id']}
    )
```

## Metrics

### Available Metrics

```python
metrics = verifier.get_metrics()

print(f"Batches verified: {metrics['batches_verified']}")
print(f"Tenant violations: {metrics['tenant_violations']}")
print(f"RLS checks: {metrics['rls_checks']}")
print(f"Quota checks: {metrics['quota_checks']}")
```

### Monitoring

```python
# Alert on violations
if metrics['tenant_violations'] > 0:
    logger.warning(f"Tenant violations detected: {metrics['tenant_violations']}")

# Track quota usage
for tenant_id in tenant_manager.list_tenants():
    tenant = tenant_manager.get_tenant(tenant_id)
    usage_pct = tenant.usage.queries_this_minute / tenant.quota.queries_per_minute
    if usage_pct > 0.8:
        logger.warning(f"Tenant {tenant_id} at {usage_pct:.1%} quota")
```

## Testing

### Unit Tests

```python
# Test tenant verification
def test_single_tenant_batch():
    commands = ["USE TENANT t1;", "SELECT 1;"]
    result = verifier.verify_batch(commands)
    assert result['valid']
    assert result['tenant_id'] == 't1'

# Test multi-tenant detection
def test_multiple_tenants_rejected():
    commands = ["USE TENANT t1;", "USE TENANT t2;"]
    result = verifier.verify_batch(commands)
    assert not result['valid']
```

### Integration Tests

```python
# Test full batch execution with tenant
def test_batch_with_tenant():
    commands = [
        "USE TENANT tenant1;",
        "CREATE TABLE test (id INT);",
        "INSERT INTO test VALUES (1);",
        "SELECT * FROM test;"
    ]
    
    result = executor.execute_with_tenant_check(
        commands, 
        mock_executor
    )
    
    assert result['success']
    assert result['tenant_id'] == 'tenant1'
```

## Troubleshooting

### Issue: Tenant Switch Not Detected

**Symptoms**: Batch with multiple USE TENANT commands passes verification

**Check**:
1. Verify `verify_batch` is called
2. Check command parsing extracts USE TENANT correctly
3. Ensure tenant IDs are normalized (lowercase)

### Issue: RLS Not Enforced

**Symptoms**: Tenant sees data from other tenants

**Check**:
1. RLS policies defined for table
2. Policies enabled
3. `enforce_rls_policies` called after query execution
4. Row has correct `tenant_id` column

### Issue: Quota Not Enforced

**Symptoms**: Tenant exceeds quota without error

**Check**:
1. `check_tenant_quota` called before execution
2. Quota values set correctly
3. Usage tracking accurate
4. Batch size calculation correct

## See Also

- [Multi-Tenant Architecture](MULTITENANT_README.md)
- [Batch Operations](OPERATIONS.md)
- [CDC Integration](CDC_README.md)
