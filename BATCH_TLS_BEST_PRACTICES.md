
# TLS Best Practices for Batch Operations

Version: 2.3.0  
Last Updated: 2024-01-15

## Overview

This document provides comprehensive guidance for securing batch operations with TLS in KosDB, including configuration recommendations, performance optimizations, and operational procedures.

## Table of Contents

1. [TLS Configuration for Batch Operations](#tls-configuration-for-batch-operations)
2. [Certificate Management](#certificate-management)
3. [Performance Optimization](#performance-optimization)
4. [Session Management](#session-management)
5. [Security Hardening](#security-hardening)
6. [Monitoring and Alerting](#monitoring-and-alerting)
7. [Troubleshooting](#troubleshooting)

---

## TLS Configuration for Batch Operations

### Recommended TLS Settings

```python
# config/tls_batch_config.py

import ssl

BATCH_TLS_CONFIG = {
    # Minimum TLS version
    'min_version': ssl.TLSVersion.TLSv1_2,
    
    # Cipher suites - prioritized for batch operations
    'cipher_suites': [
        'ECDHE-RSA-AES256-GCM-SHA384',   # Preferred for large payloads
        'ECDHE-RSA-AES128-GCM-SHA256',   # Good performance/security balance
        'ECDHE-RSA-CHACHA20-POLY1305',   # Mobile-friendly
        'DHE-RSA-AES256-GCM-SHA384',     # Fallback with FS
    ],
    
    # Certificate verification
    'cert_required': True,
    'verify_mode': ssl.CERT_REQUIRED,
    
    # Session management
    'session_timeout': 3600,  # 1 hour
    'session_tickets': True,
    
    # Performance settings
    'enable_compression': False,  # Security risk
    'enable_session_resumption': True,
}
```

### Server Configuration

```python
import ssl
import socket

def create_batch_tls_server(certfile, keyfile, cafile):
    """Create TLS server optimized for batch operations."""
    
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    
    # Load certificates
    context.load_cert_chain(certfile, keyfile)
    context.load_verify_locations(cafile)
    
    # Require client certificates for batch operations
    context.verify_mode = ssl.CERT_REQUIRED
    
    # Set strong cipher suites
    context.set_ciphers(':'.join([
        'ECDHE-RSA-AES256-GCM-SHA384',
        'ECDHE-RSA-AES128-GCM-SHA256',
        'ECDHE-RSA-CHACHA20-POLY1305',
    ]))
    
    # Enable session resumption
    context.maximum_version = ssl.TLSVersion.MAXIMUM_SUPPORTED
    
    return context
```

### Client Configuration

```python
def create_batch_tls_client(certfile, keyfile, cafile):
    """Create TLS client for batch operations."""
    
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    
    # Load client certificate
    context.load_cert_chain(certfile, keyfile)
    context.load_verify_locations(cafile)
    
    # Verify server certificate
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    
    return context
```

---

## Certificate Management

### Client Certificate Requirements

For batch operations, client certificates provide:
- **Authentication**: Verify client identity
- **Authorization**: Map certificates to batch permissions
- **Audit Trail**: Non-repudiation of batch execution

#### Certificate Structure

```bash
# Generate client certificate for batch operations
openssl req -new -newkey rsa:4096 -nodes \
  -keyout batch-client.key \
  -out batch-client.csr \
  -subj "/C=US/O=YourOrg/CN=batch-client"

# Sign with CA
openssl x509 -req -in batch-client.csr \
  -CA ca.crt -CAkey ca.key \
  -CAcreateserial -out batch-client.crt \
  -days 365 -sha256
```

### Certificate Validation

```python
def validate_batch_client_cert(cert):
    """Validate client certificate for batch operations."""
    
    # Check certificate attributes
    subject = cert.get_subject()
    
    # Verify organization
    if subject.O != 'YourOrg':
        raise ValueError("Invalid organization")
    
    # Check certificate purpose
    if not cert.get_extension('keyUsage').value.digitalSignature:
        raise ValueError("Certificate not valid for signing")
    
    # Verify not expired
    if cert.has_expired():
        raise ValueError("Certificate expired")
    
    return True
```

### Certificate Rotation

```python
class CertificateRotator:
    """Handle certificate rotation without downtime."""
    
    def __init__(self, cert_path, key_path):
        self.cert_path = cert_path
        self.key_path = key_path
        self.current_context = None
        self.new_context = None
    
    def rotate(self, new_cert, new_key):
        """Rotate to new certificate."""
        # Create new context with new certificate
        self.new_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.new_context.load_cert_chain(new_cert, new_key)
        
        # Gradually migrate connections
        self.current_context = self.new_context
    
    def get_context(self):
        """Get current TLS context."""
        return self.current_context or self.new_context
```

---

## Performance Optimization

### Session Resumption

Enable TLS session resumption to avoid full handshakes for subsequent batches:

```python
# Enable session caching
context.options |= ssl.OP_NO_TICKET  # Use session IDs instead of tickets

# Configure session cache
context.set_session_cache_mode(ssl.SESS_CACHE_SERVER)
context.set_session_id(b'kosdb-batch-1.0')
```

### Connection Pooling with TLS

```python
class TLSConnectionPool:
    """Connection pool with TLS session reuse."""
    
    def __init__(self, host, port, ssl_context, max_size=10):
        self.host = host
        self.port = port
        self.ssl_context = ssl_context
        self.max_size = max_size
        self.pool = []
        self.sessions = {}  # Session cache
    
    def get_connection(self):
        """Get connection from pool."""
        if self.pool:
            conn = self.pool.pop()
            # Reuse session if available
            if conn.session in self.sessions:
                conn.session = self.sessions[conn.session]
            return conn
        
        # Create new connection
        sock = socket.create_connection((self.host, self.port))
        conn = self.ssl_context.wrap_socket(
            sock,
            server_hostname=self.host,
            session=self.sessions.get('default')
        )
        return conn
    
    def return_connection(self, conn):
        """Return connection to pool."""
        if len(self.pool) < self.max_size:
            # Save session for reuse
            self.sessions['default'] = conn.session
            self.pool.append(conn)
        else:
            conn.close()
```

### Large Payload Optimization

For batches with large responses:

```python
def send_large_batch_response(conn, data, chunk_size=65536):
    """Send large batch response in chunks."""
    
    total_sent = 0
    while total_sent < len(data):
        chunk = data[total_sent:total_sent + chunk_size]
        sent = conn.send(chunk)
        total_sent += sent
        
        # Yield to allow other operations
        if total_sent % (chunk_size * 10) == 0:
            time.sleep(0.001)
    
    return total_sent
```

### TLS False Start

Enable TLS False Start for reduced latency:

```python
# Enable False Start (client-side)
context.options |= ssl.OP_ENABLE_MIDDLEBOX_COMPAT

# Server-side optimization
context.options |= ssl.OP_SINGLE_DH_USE
context.options |= ssl.OP_SINGLE_ECDH_USE
```

---

## Session Management

### Session Cache Configuration

```python
class BatchTLSSessionCache:
    """Session cache optimized for batch operations."""
    
    def __init__(self, max_size=10000, ttl=3600):
        self.cache = {}
        self.max_size = max_size
        self.ttl = ttl
    
    def get_session(self, session_id):
        """Get cached session."""
        session = self.cache.get(session_id)
        if session and time.time() - session['time'] < self.ttl:
            return session['data']
        return None
    
    def store_session(self, session_id, session_data):
        """Store session in cache."""
        # Evict oldest if at capacity
        if len(self.cache) >= self.max_size:
            oldest = min(self.cache.items(), key=lambda x: x[1]['time'])
            del self.cache[oldest[0]]
        
        self.cache[session_id] = {
            'data': session_data,
            'time': time.time()
        }
```

### Session Ticket Rotation

```python
def rotate_session_tickets(context, new_key):
    """Rotate session ticket keys."""
    # Add new key while keeping old key valid
    context.set_session_ticket_keys([new_key, old_key])
    
    # After grace period, remove old key
    time.sleep(3600)  # 1 hour
    context.set_session_ticket_keys([new_key])
```

---

## Security Hardening

### Cipher Suite Selection

Recommended cipher priority for batch operations:

1. **ECDHE-RSA-AES256-GCM-SHA384** - Best security, good performance
2. **ECDHE-RSA-AES128-GCM-SHA256** - Good balance
3. **ECDHE-RSA-CHACHA20-POLY1305** - Mobile-optimized

Avoid:
- RC4 (broken)
- DES/3DES (weak)
- MD5 (broken)
- RSA key exchange (no forward secrecy)

### Certificate Pinning

```python
class PinnedTLSContext:
    """TLS context with certificate pinning."""
    
    def __init__(self, pinned_hashes):
        self.pinned_hashes = pinned_hashes
    
    def verify_pin(self, cert):
        """Verify certificate against pinned hashes."""
        cert_hash = hashlib.sha256(cert).hexdigest()
        
        if cert_hash not in self.pinned_hashes:
            raise ssl.SSLError("Certificate pin mismatch")
        
        return True
```

### Perfect Forward Secrecy

Ensure all cipher suites provide forward secrecy:

```python
def check_forward_secrecy(cipher):
    """Check if cipher provides forward secrecy."""
    fs_ciphers = ['ECDHE', 'DHE', 'EDH']
    return any(c in cipher for c in fs_ciphers)

# Filter cipher list
secure_ciphers = [c for c in all_ciphers if check_forward_secrecy(c)]
```

### OCSP Stapling

Enable OCSP stapling for certificate revocation checks:

```python
# Enable OCSP stapling
context.ocsp_response_cb = lambda conn, ocsp_response, ocsp_response_cb_ctx: True
```

---

## Monitoring and Alerting

### TLS Metrics to Monitor

| Metric | Warning | Critical |
|--------|---------|----------|
| TLS handshake time | > 100ms | > 500ms |
| Session cache hit rate | < 80% | < 50% |
| Certificate expiry | < 30 days | < 7 days |
| Failed handshakes | > 1% | > 5% |
| Weak cipher usage | > 0 | > 0 |

### Prometheus Metrics

```python
from prometheus_client import Counter, Histogram, Gauge

# TLS handshake metrics
tls_handshakes_total = Counter(
    'tls_handshakes_total',
    'Total TLS handshakes',
    ['version', 'cipher']
)

tls_handshake_duration = Histogram(
    'tls_handshake_duration_seconds',
    'TLS handshake duration'
)

# Session metrics
tls_session_hits = Counter(
    'tls_session_cache_hits_total',
    'Session cache hits'
)

tls_session_misses = Counter(
    'tls_session_cache_misses_total',
    'Session cache misses'
)

# Certificate metrics
tls_cert_expiry = Gauge(
    'tls_certificate_expiry_timestamp',
    'Certificate expiry timestamp'
)
```

### Alerting Rules

```yaml
# prometheus-alerts.yml
groups:
  - name: tls_alerts
    rules:
      - alert: TLSHandshakeSlow
        expr: histogram_quantile(0.95, tls_handshake_duration_seconds) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "TLS handshakes are slow"
          
      - alert: CertificateExpiringSoon
        expr: (tls_certificate_expiry_timestamp - time()) < 86400 * 30
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "TLS certificate expiring in 30 days"
          
      - alert: WeakCipherUsed
        expr: tls_handshakes_total{cipher=~".*RC4.*|.*DES.*"} > 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Weak TLS cipher detected"
```

---

## Troubleshooting

### Slow TLS Handshakes

**Symptoms:**
- High latency for first batch command
- TLS handshake taking > 100ms

**Diagnosis:**
```bash
# Check handshake time
openssl s_client -connect localhost:443 -tlsextdebug 2>&1 | grep -i handshake

# Profile TLS operations
python -m cProfile -o tls_profile.stats your_script.py
```

**Solutions:**
1. Enable session resumption
2. Use ECDSA certificates (faster than RSA)
3. Enable TLS False Start
4. Check certificate chain length

### Session Cache Misses

**Symptoms:**
- Full handshakes for every batch
- High CPU usage

**Diagnosis:**
```python
# Check cache hit rate
hit_rate = session_hits / (session_hits + session_misses)
print(f"Session cache hit rate: {hit_rate:.2%}")
```

**Solutions:**
1. Increase session cache size
2. Extend session timeout
3. Enable session tickets
4. Check for cache invalidation

### Certificate Errors

**Symptoms:**
- `ssl.SSLError: certificate verify failed`
- Client connections rejected

**Diagnosis:**
```bash
# Verify certificate chain
openssl verify -CAfile ca.crt -untrusted intermediate.crt client.crt

# Check certificate dates
openssl x509 -in client.crt -noout -dates
```

**Solutions:**
1. Update CA bundle
2. Check certificate expiry
3. Verify hostname matches
4. Check certificate chain completeness

### Large Payload Failures

**Symptoms:**
- `ssl.SSLError: [SSL: BAD_LENGTH] bad length`
- Connection reset during large batches

**Diagnosis:**
```python
# Check maximum TLS record size
max_record_size = 16384  # 16KB default

# Check if payload exceeds limit
if len(payload) > max_record_size:
    print("Payload exceeds TLS record size")
```

**Solutions:**
1. Implement chunked sending
2. Increase TLS record size (if supported)
3. Use application-level fragmentation
4. Check for MTU issues

### Memory Issues

**Symptoms:**
- High memory usage during TLS operations
- OOM errors with large batches

**Diagnosis:**
```python
import tracemalloc

tracemalloc.start()
# ... TLS operations ...
current, peak = tracemalloc.get_traced_memory()
print(f"Current memory: {current / 1024 / 1024:.2f} MB")
print(f"Peak memory: {peak / 1024 / 1024:.2f} MB")
```

**Solutions:**
1. Enable memory-mapped TLS buffers
2. Use streaming for large payloads
3. Implement connection pooling
4. Check for memory leaks in SSL context

---

## Command Reference

### OpenSSL Commands

```bash
# Test TLS connection
openssl s_client -connect localhost:443 -tls1_2

# Check supported ciphers
openssl ciphers -v 'HIGH:!aNULL:!MD5'

# Verify certificate
openssl x509 -in cert.pem -text -noout

# Test session resumption
openssl s_client -connect localhost:443 -reconnect
```

### Python SSL Debugging

```python
import ssl
import logging

# Enable SSL debug logging
ssl.SSLContext.debug = True

# Or set environment variable
# export SSLKEYLOGFILE=/tmp/ssl-keys.log
```

---

## Checklist

### Pre-Deployment

- [ ] TLS 1.2 or higher configured
- [ ] Strong cipher suites selected
- [ ] Client certificates required for batch operations
- [ ] Session resumption enabled
- [ ] Certificate expiry monitoring configured
- [ ] OCSP stapling enabled
- [ ] Performance benchmarks completed

### Post-Deployment

- [ ] TLS handshake time < 100ms
- [ ] Session cache hit rate > 80%
- [ ] No weak cipher usage
- [ ] Certificate expiry > 30 days
- [ ] Audit logs encrypted
- [ ] Monitoring dashboards active
- [ ] Alert rules tested

---

## See Also

- [Security Considerations](SECURITY_README.md)
- [Batch Operations Guide](OPERATIONS.md)
- [Load Testing](LOAD_TESTING.md)
- [OpenSSL Documentation](https://www.openssl.org/docs/)
- [Python SSL Documentation](https://docs.python.org/3/library/ssl.html)
