
# Security Features for KosDB

Comprehensive security system with audit logging, encryption, RBAC, SQL injection detection, batch command security, and compliance reporting.

## Features

- **Audit Logging**: Tamper-evident logging with hash chains and risk scoring
- **AES-256 Encryption**: Data encryption at rest with PBKDF2 key derivation
- **Column-Level Encryption**: Per-column encryption for sensitive data
- **RBAC**: Role-based access control with hierarchical roles
- **SQL Injection Detection**: Pattern analysis and query validation
- **Batch Command Security**: Privilege checks, rate limiting, and audit logging for multi-command batches
- **Security Policies**: Password, session, and encryption policies

## Audit Event Types

| Event Type | Description |
|------------|-------------|
| LOGIN/LOGOUT | Authentication events |
| QUERY | Database queries |
| INSERT/UPDATE/DELETE | Data modifications |
| CREATE/DROP | Schema changes |
| GRANT/REVOKE | Permission changes |
| ENCRYPTION/DECRYPTION | Encryption operations |
| POLICY_VIOLATION | Security violations |

## Batch Command Security

KosDB v2.3.0 introduces comprehensive security measures for multi-command batch execution:

### Security Features

1. **Individual Privilege Checks**: Each command in a batch is checked for required permissions
2. **SQL Injection Detection**: Every command is analyzed for injection patterns
3. **Rate Limiting**: Batches count as N commands toward rate limits
4. **Batch Size Limits**: Configurable maximum commands per batch and batch size
5. **Audit Logging**: Complete batch execution is logged with results
6. **Security Policy Control**: `allow_batch_commands` setting to disable feature

### Configuration

```json
{
  "batch": {
    "enabled": true,
    "max_commands_per_batch": 100,
    "max_batch_size_bytes": 1048576,
    "max_response_size_bytes": 10485760,
    "batch_timeout_seconds": 30,
    "continue_on_error": true,
    "transaction_support": true
  },
  "security": {
    "allow_batch_commands": true,
    "sql_injection_detection": true
  }
}
```

### Security Behavior

- **Unauthorized Commands**: If a command in the middle of a batch lacks permissions, it's skipped with an error, and remaining commands continue (if `continue_on_error` is true)
- **Injection Detection**: If any command triggers injection detection, the entire batch is rejected
- **Rate Limiting**: Each command in a batch counts against the rate limit
- **Audit Trail**: Batch executions are logged with command count, success/error counts, and user information

### Role Management
```sql
GRANT ROLE user readonly
REVOKE ROLE user readonly
CHECK PERMISSION user SELECT
```

### Encryption
```sql
ENCRYPT COLUMN users ssn '123-45-6789'
DECRYPT COLUMN users ssn 'encrypted_value'
```

### Security Analysis
```sql
VALIDATE PASSWORD 'MyP@ssw0rd!'
CHECK SQL INJECTION 'SELECT * FROM users'
```

### Compliance Reports
```sql
COMPLIANCE REPORT GDPR DAYS 30
COMPLIANCE REPORT SOX
SECURITY STATS
HIGH RISK EVENTS THRESHOLD 50
```

## API Reference

### AuditLogger

```python
from security import AuditLogger, AuditEventType

logger = AuditLogger()

# Log event
event = logger.log(
    event_type=AuditEventType.QUERY,
    user_id="user1",
    resource="users",
    action="SELECT * FROM users",
    client_ip="192.168.1.1"
)

# Query logs
events = logger.query(
    user_id="user1",
    event_type=AuditEventType.QUERY,
    min_risk=50
)

# Export
json_data = logger.export(format="json")
```

### AESEncryption

```python
from security import AESEncryption

crypto = AESEncryption()

# Encrypt data
encrypted = crypto.encrypt("sensitive data", column="users.ssn")

# Decrypt
decrypted = crypto.decrypt(encrypted, column="users.ssn")

# Column-level encryption
encrypted = crypto.encrypt_column("users", "ssn", "123-45-6789")
decrypted = crypto.decrypt_column("users", "ssn", encrypted)
```

### RBACManager

```python
from security import RBACManager

rbac = RBACManager()

# Create role
rbac.create_role("analyst", {"SELECT", "REPORTS"})

# Grant role
rbac.grant_role("user1", "readonly")

# Check permission
if rbac.check_permission("user1", "SELECT"):
    # Allow query
    pass

# Get all permissions
perms = rbac.get_user_permissions("user1")
```

### SQLInjectionDetector

```python
from security import SQLInjectionDetector

detector = SQLInjectionDetector()

# Analyze query
is_safe, confidence, reasons = detector.analyze(
    "SELECT * FROM users WHERE id = 1",
    user_id="user1"
)

# Validate (raises SQLInjectionError if unsafe)
try:
    detector.validate("SELECT * FROM users; DROP TABLE users", "user1")
except SQLInjectionError as e:
    print(f"Injection detected: {e}")
```

### SecurityPolicy

```python
from security import SecurityPolicy

policy = SecurityPolicy()

# Validate password
is_valid, violations = policy.validate_password("WeakPass")
if not is_valid:
    print(f"Violations: {violations}")

# Check session
is_valid = policy.check_session_valid(
    session_start=time.time() - 100,
    last_activity=time.time() - 10
)
```

### ComplianceReporter

```python
from security import ComplianceReporter, AuditLogger

audit_logger = AuditLogger()
reporter = ComplianceReporter(audit_logger)

# Generate GDPR report
report = reporter.generate_report(
    report_type="GDPR",
    start_time=time.time() - 30*24*3600,
    end_time=time.time()
)

print(report['compliance_status'])
print(report['recommendations'])
```

### SecurityManager

```python
from security import get_security_manager

manager = get_security_manager()

# Secure query processing
try:
    query, metadata = manager.secure_query(
        "SELECT * FROM users",
        user_id="user1",
        client_ip="192.168.1.1"
    )
except SQLInjectionError:
    # Handle injection attempt
    pass

# Encrypt sensitive data
encrypted = manager.encrypt_sensitive_data(
    "users", "ssn", "123-45-6789"
)

# Check permission
if manager.check_permission("user1", "SELECT"):
    # Execute query
    pass

# Get security report
report = manager.get_security_report()
```

## Security Policies

### Password Policy
- Minimum length: 8 characters
- Requires uppercase, lowercase, digits, special characters
- Max age: 90 days
- Prevents reuse of last 5 passwords

### Session Policy
- Max duration: 60 minutes
- Idle timeout: 15 minutes
- Max concurrent sessions: 5

### Encryption Policy
- Encrypt at rest: Enabled
- Column-level encryption: Enabled
- Key rotation: 90 days

## Compliance Reports

### GDPR Report
- Data access events count
- Data modification events count
- Encryption operations count
- High-risk events identification
- Compliance status and recommendations

### SOX Report
- Administrative changes tracking
- Failed operations count
- Unauthorized attempts detection
- Segregation of duties assessment

### PCI DSS Report
- Sensitive data access tracking
- Encryption coverage status
- Access control validation

## Testing

```bash
python test_security.py
```

All 31 tests passing ✓
