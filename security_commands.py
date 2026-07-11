\"\"\"
Command handlers for security operations.
\"\"\"

import time
import logging
from typing import Dict, Any, Optional, List
from security import (
    SecurityManager,
    AuditEventType,
    get_security_manager,
    SQLInjectionError,
    PermissionDeniedError
)

logger = logging.getLogger(__name__)
)

logger = logging.getLogger(__name__)


class AuditLogCommand:
    """AUDIT LOG - Query audit log."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
        self.admin_required = True
    
    def execute(
        self,
        user_id: Optional[str] = None,
        event_type: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        min_risk: int = 0,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Query audit log."""
        manager = get_security_manager()
        
        # Convert event_type string to enum if provided
        event_type_enum = None
        if event_type:
            try:
                event_type_enum = AuditEventType(event_type.lower())
            except ValueError:
                return {
                    'status': 'error',
                    'message': f'Invalid event type: {event_type}'
                }
        
        events = manager.audit_logger.query(
            user_id=user_id,
            event_type=event_type_enum,
            start_time=start_time,
            end_time=end_time,
            min_risk=min_risk
        )
        
        # Apply limit
        events = events[:limit]
        
        return {
            'status': 'success',
            'events': [e.to_dict() for e in events],
            'count': len(events)
        }


class ExportAuditLogCommand:
    """EXPORT AUDIT LOG - Export audit data."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
        self.admin_required = True
    
    def execute(self, format: str = "json") -> Dict[str, Any]:
        """Export audit log."""
        manager = get_security_manager()
        
        if format not in ["json", "csv"]:
            return {
                'status': 'error',
                'message': 'Format must be json or csv'
            }
        
        data = manager.audit_logger.export(format)
        
        return {
            'status': 'success',
            'format': format,
            'data': data
        }


class GrantRoleCommand:
    """GRANT ROLE - Assign role to user."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
        self.admin_required = True
    
    def execute(self, user_id: str, role: str) -> Dict[str, Any]:
        """Grant role to user."""
        manager = get_security_manager()
        
        try:
            manager.rbac.grant_role(user_id, role)
            
            # Log the grant
            manager.audit_logger.log(
                event_type=AuditEventType.GRANT,
                user_id=self.auth.current_user if hasattr(self.auth, 'current_user') else 'admin',
                resource=f"user:{user_id}",
                action=f"grant_role:{role}",
                details={'granted_to': user_id, 'role': role}
            )
            
            return {
                'status': 'success',
                'message': f'Granted role {role} to {user_id}'
            }
            
        except ValueError as e:
            return {
                'status': 'error',
                'message': str(e)
            }


class RevokeRoleCommand:
    """REVOKE ROLE - Remove role from user."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
        self.admin_required = True
    
    def execute(self, user_id: str, role: str) -> Dict[str, Any]:
        """Revoke role from user."""
        manager = get_security_manager()
        
        manager.rbac.revoke_role(user_id, role)
        
        # Log the revoke
        manager.audit_logger.log(
            event_type=AuditEventType.REVOKE,
            user_id=self.auth.current_user if hasattr(self.auth, 'current_user') else 'admin',
            resource=f"user:{user_id}",
            action=f"revoke_role:{role}",
            details={'revoked_from': user_id, 'role': role}
        )
        
        return {
            'status': 'success',
            'message': f'Revoked role {role} from {user_id}'
        }


class CheckPermissionCommand:
    """CHECK PERMISSION - Verify user permissions."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, user_id: str, permission: str) -> Dict[str, Any]:
        """Check if user has permission."""
        manager = get_security_manager()
        
        has_permission = manager.check_permission(user_id, permission)
        all_permissions = manager.rbac.get_user_permissions(user_id)
        
        return {
            'status': 'success',
            'user_id': user_id,
            'permission': permission,
            'has_permission': has_permission,
            'all_permissions': list(all_permissions)
        }


class EncryptColumnCommand:
    """ENCRYPT COLUMN - Encrypt sensitive column."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
        self.admin_required = True
    
    def execute(self, table: str, column: str, value: str) -> Dict[str, Any]:
        """Encrypt column value."""
        manager = get_security_manager()
        
        encrypted = manager.encrypt_sensitive_data(table, column, value)
        
        return {
            'status': 'success',
            'table': table,
            'column': column,
            'encrypted': encrypted
        }


class DecryptColumnCommand:
    """DECRYPT COLUMN - Decrypt sensitive column."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
        self.admin_required = True
    
    def execute(self, table: str, column: str, ciphertext: str) -> Dict[str, Any]:
        """Decrypt column value."""
        manager = get_security_manager()
        
        try:
            decrypted = manager.decrypt_sensitive_data(table, column, ciphertext)
            
            return {
                'status': 'success',
                'table': table,
                'column': column,
                'decrypted': decrypted
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Decryption failed: {e}'
            }


class ValidatePasswordCommand:
    """VALIDATE PASSWORD - Check password against policy."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, password: str) -> Dict[str, Any]:
        """Validate password."""
        manager = get_security_manager()
        
        is_valid, violations = manager.policy.validate_password(password)
        
        return {
            'status': 'success' if is_valid else 'error',
            'is_valid': is_valid,
            'violations': violations
        }


class SQLInjectionCheckCommand:
    """CHECK SQL INJECTION - Analyze query for injection."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, query: str) -> Dict[str, Any]:
        """Check query for SQL injection."""
        manager = get_security_manager()
        
        is_safe, confidence, reasons = manager.injection_detector.analyze(query)
        
        return {
            'status': 'success',
            'is_safe': is_safe,
            'confidence': confidence,
            'reasons': reasons
        }


class ComplianceReportCommand:
    """COMPLIANCE REPORT - Generate compliance report."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
        self.admin_required = True
    
    def execute(
        self,
        report_type: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """Generate compliance report."""
        manager = get_security_manager()
        
        end_time = time.time()
        start_time = end_time - (days * 24 * 60 * 60)
        
        try:
            report = manager.compliance.generate_report(
                report_type=report_type.upper(),
                start_time=start_time,
                end_time=end_time
            )
            
            return {
                'status': 'success',
                'report_type': report_type,
                'report': report
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': str(e)
            }


class SecurityStatsCommand:
    """SECURITY STATS - Show security statistics."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self) -> Dict[str, Any]:
        """Get security statistics."""
        manager = get_security_manager()
        
        return {
            'status': 'success',
            'security': manager.get_security_report()
        }


class HighRiskEventsCommand:
    """HIGH RISK EVENTS - Show high-risk audit events."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
        self.admin_required = True
    
    def execute(self, threshold: int = 50) -> Dict[str, Any]:
        """Get high-risk events."""
        manager = get_security_manager()
        
        events = manager.audit_logger.get_high_risk_events(threshold)
        
        return {
            'status': 'success',
            'threshold': threshold,
            'events': [e.to_dict() for e in events],
            'count': len(events)
        }
