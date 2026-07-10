# Security Hardening Guide for KosDB v3.1.0

This guide provides comprehensive security hardening recommendations for production deployments of KosDB.

## Table of Contents

1. [TLS/SSL Setup](#tlsssl-setup)
2. [At-Rest Encryption](#at-rest-encryption)
3. [Authentication & Authorization](#authentication--authorization)
4. [Audit Logging](#audit-logging)
5. [Network Security](#network-security)
6. [Backup Security](#backup-security)
7. [Monitoring & Alerting](#monitoring--alerting)

## TLS/SSL Setup

### Generating Certificates

#### Option 1: Self-Signed Certificates (Development)

```bash
# Generate private CA
openssl req -x509 -newkey rsa:4096 -keyout ca.key -out ca.crt \
    -days 365 -nodes -subj "/C=US/O=MyOrg/CN=KosDB CA"

# Generate server certificate
openssl req -newkey rsa:4096 -keyout server.key -out server.csr \
    -nodes -subj "/C=US/O=MyOrg/CN=localhost"

# Sign with CA
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key \
    -CAcreateserial -out server.crt -days 365

# Set permissions
chmod 600 server.key ca.key
chmod 644 server.crt ca.crt
```

#### Option 2: Let's Encrypt (Production)

```bash
# Install certbot
sudo apt-get install certbot

# Obtain certificate
sudo certbot certonly --standalone -d db.example.com

# Certificates will be in /etc/letsencrypt/live/db.example.com/
```

#### Option 3: Corporate CA

```bash
# Generate CSR
openssl req -newkey rsa:4096 -keyout server.key -out server.csr \
    -nodes -subj "/C=US/O=MyCompany/CN=db.example.com"

# Submit CSR to your CA
# Receive: server.crt and ca-chain.crt
```

### Server Configuration

```json
{
  "tls": {
    "enabled": true,
    "cert_file": "/etc/kosdb/server.crt",
    "key_file": "/etc/kosdb/server.key",
    "ca_file": "/etc/kosdb/ca.crt",
    "generate_self_signed": false,
    "client_auth": false,
    "protocols": ["TLSv1.2", "TLSv1.3"],
    "ciphers": "ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384"
  }
}
```

### Client Authentication (mTLS)

For maximum security, require client certificates:

```json
{
  "tls": {
    "enabled": true,
    "client_auth": true,
    "cert_file": "/etc/kosdb/server.crt",
    "key_file": "/etc/kosdb/server.key",
    "ca_file": "/etc/kosdb/ca.crt"
  }
}
```

Generate client certificates:

```bash
# Client certificate
openssl req -newkey rsa:2048 -keyout client.key -out client.csr \
    -nodes -subj "/C=US/O=MyOrg/CN=client1"

openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key \
    -CAcreateserial -out client.crt -days 365
```

Connect with client certificate:

```bash
python cli.py --tls \
    --ca-cert ca.crt \
    --client-cert client.crt \
    --client-key client.key \
    -u admin -P secret123
```

## At-Rest Encryption

### Enabling Encryption

⚠️ **Warning**: Enabling encryption on existing data requires re-encryption. Plan for maintenance window.

1. **Set strong passphrase in environment**:
```bash
export KOSDB_ENCRYPTION_PASSPHRASE=$(openssl rand -base64 32)
echo "KOSDB_ENCRYPTION_PASSPHRASE=$KOSDB_ENCRYPTION_PASSPHRASE" >> ~/.bashrc
```

2. **Configure encryption**:
```json
{
  "database": {
    "encryption": {
      "enabled": true,
      "passphrase_env": "KOSDB_ENCRYPTION_PASSPHRASE"
    }
  }
}
```

3. **Start server** - it will automatically encrypt new data

### Key Management Best Practices

1. **Use Hardware Security Modules (HSM)** for production:
```json
{
  "database": {
    "encryption": {
      "enabled": true,
      "key_file": "/dev/hsm/kosdb-key"
    }
  }
}
```

2. **Rotate keys regularly**:
```sql
-- Rotate encryption key (requires server restart)
-- 1. Update passphrase
-- 2. Restart server
-- 3. Run rotation
ROTATE ENCRYPTION KEY;
```

3. **Backup keys separately** from data:
```bash
# Backup encryption key
cp /etc/kosdb/encryption.key /secure/backup/location/
chmod 400 /secure/backup/location/encryption.key
```

## Authentication & Authorization

### Strong Password Policy

```json
{
  "authentication": {
    "method": "database",
    "max_failed_attempts": 3,
    "lockout_duration_minutes": 30,
    "session_ttl_minutes": 60
  }
}
```

### Role-Based Access Control

Create minimal privilege roles:

```sql
-- Read-only role
CREATE ROLE readonly DESCRIPTION 'Read-only data access';
GRANT SELECT ON *.* TO readonly;

-- Read-write role
CREATE ROLE readwrite DESCRIPTION 'Read and write data';
GRANT SELECT, INSERT, UPDATE, DELETE ON *.* TO readwrite;

-- Admin role (full access)
CREATE ROLE admin DESCRIPTION 'Full database access';
GRANT ALL ON *.* TO admin;

-- Assign roles to users
GRANT ROLE readonly TO analyst;
GRANT ROLE readwrite TO app_user;
GRANT ROLE admin TO dba;
```

### Column-Level Security

```sql
-- Restrict access to sensitive columns
GRANT SELECT (id, name, email) ON users TO app_user;
REVOKE SELECT (ssn, salary) ON users FROM app_user;
```

## Audit Logging

### Comprehensive Audit Configuration

```json
{
  "audit_logging": {
    "enabled": true,
    "log_dir": "/var/log/kosdb/audit",
    "max_size_mb": 500,
    "max_age_days": 90,
    "compress": true,
    "targets": ["file", "syslog"],
    "syslog_facility": "local0",
    "exclude_commands": ["PING", "ECHO"],
    "mask_commands": ["PASS", "PASSWORD", "SECRET", "KEY", "TOKEN"]
  }
}
```

### Syslog Integration

```bash
# Configure rsyslog
echo "local0.* /var/log/kosdb/audit.log" >> /etc/rsyslog.d/kosdb.conf
systemctl restart rsyslog

# Log rotation
cat > /etc/logrotate.d/kosdb <<EOF
/var/log/kosdb/*.log {
    daily
    rotate 90
    compress
    delaycompress
    missingok
    notifempty
    create 640 kosdb kosdb
}
EOF
```

### Webhook for SIEM Integration

```json
{
  "audit_logging": {
    "webhook_url": "https://siem.example.com/api/events",
    "webhook_headers": {
      "Authorization": "Bearer ${SIEM_API_TOKEN}",
      "Content-Type": "application/json"
    }
  }
}
```

## Network Security

### Firewall Configuration

```bash
# Allow only specific IPs
iptables -A INPUT -p tcp -s 10.0.0.0/24 --dport 9999 -j ACCEPT
iptables -A INPUT -p tcp --dport 9999 -j DROP

# For replication port
iptables -A INPUT -p tcp -s 10.0.0.0/24 --dport 9998 -j ACCEPT
iptables -A INPUT -p tcp --dport 9998 -j DROP
```

### Binding to Specific Interface

```json
{
  "server": {
    "host": "10.0.0.1",
    "port": 9999
  }
}
```

### Disable Unnecessary Features

```json
{
  "monitoring": {
    "enabled": false
  },
  "backup": {
    "auto_backup": false
  }
}
```

## Backup Security

### Encrypted Backups

```bash
# Create encrypted backup
python cli.py -c "BACKUP DATABASE mydb TO /backups/mydb.enc WITH ENCRYPTION '$(cat /etc/kosdb/backup-passphrase)' COMPRESSION gzip"

# Store passphrase securely
echo "backup-passphrase" | gpg --encrypt --recipient security@example.com > /secure/backup-passphrase.gpg
```

### Backup Verification

```bash
# Verify backup integrity
python -c "
from backup_utils import verify_backup_integrity
valid, error = verify_backup_integrity('/backups/mydb.enc', passphrase='your-passphrase')
print(f'Valid: {valid}, Error: {error}')
"
```

### Offsite Backup

```bash
# Encrypt and upload to S3
aws s3 cp /backups/mydb.enc s3://my-backup-bucket/kosdb/ \
    --server-side-encryption AES256
```

## Monitoring & Alerting

### Failed Login Alerts

```bash
# Check audit logs for failed logins
grep "AUTHENTICATION.*success=False" /var/log/kosdb/audit/audit_*.jsonl

# Alert script
#!/bin/bash
FAILED=$(grep "AUTHENTICATION.*success=False" /var/log/kosdb/audit/audit_$(date +%Y%m%d).jsonl | wc -l)
if [ $FAILED -gt 10 ]; then
    echo "ALERT: $FAILED failed login attempts" | mail -s "KosDB Security Alert" admin@example.com
fi
```

### Replication Lag Monitoring

```bash
# Check replication status
python cli.py -c "SHOW REPLICATION STATUS"

# Alert if lag > 60 seconds
```

### File Integrity Monitoring

```bash
# Monitor config file changes
auditctl -w /etc/kosdb/config.json -p wa -k kosdb_config

# Monitor binary changes
auditctl -w /usr/local/bin/kosdb -p x -k kosdb_binary
```

## Security Checklist

### Pre-Deployment

- [ ] TLS certificates generated and valid
- [ ] Strong encryption passphrase set
- [ ] Firewall rules configured
- [ ] Audit logging enabled
- [ ] File permissions set correctly (600 for keys)
- [ ] Backup encryption configured
- [ ] Admin user password is strong (>16 chars)
- [ ] Default roles created with minimal privileges
- [ ] Monitoring and alerting configured

### Post-Deployment

- [ ] Verify TLS connection works
- [ ] Test failed login lockout
- [ ] Verify audit logs are written
- [ ] Test backup and restore
- [ ] Confirm replication is secure
- [ ] Review access logs regularly
- [ ] Schedule regular security audits

## Incident Response

### Suspected Breach

1. **Immediate Actions**:
   ```bash
   # Stop server
   pkill -f "python server.py"
   
   # Preserve logs
   cp -r /var/log/kosdb /secure/incident-$(date +%Y%m%d)/
   
   # Check for unauthorized access
   grep "success=True" /var/log/kosdb/audit/audit_*.jsonl | tail -100
   ```

2. **Rotate all credentials**
3. **Review audit logs for suspicious activity**
4. **Restore from known-good backup if necessary**

## Compliance

### GDPR Compliance

- Enable audit logging to track data access
- Use column-level encryption for PII
- Implement data retention policies
- Enable right-to-erasure support

### HIPAA Compliance

- Enable TLS for all connections
- Enable at-rest encryption
- Implement access controls
- Enable comprehensive audit logging
- Regular backup with encryption

### SOC 2 Compliance

- Document all security controls
- Regular penetration testing
- Access review procedures
- Incident response plan

## Additional Resources

- [OWASP Database Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Database_Security_Cheat_Sheet.html)
- [NIST Database Security Guidelines](https://csrc.nist.gov/publications/detail/sp/800-73/4/final)
- [PCI DSS Database Requirements](https://www.pcisecuritystandards.org/)

For questions or security concerns, contact: security@example.com
