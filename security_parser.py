"""
Parser extensions for security commands.
"""

import re
from typing import Dict, Any, Optional


class SecurityParser:
    """
    Parser for security commands.
    
    Supports:
    - AUDIT LOG [USER user] [TYPE type] [RISK min_risk]
    - EXPORT AUDIT LOG [FORMAT json|csv]
    - GRANT ROLE user role
    - REVOKE ROLE user role
    - CHECK PERMISSION user permission
    - ENCRYPT COLUMN table column value
    - DECRYPT COLUMN table column ciphertext
    - VALIDATE PASSWORD password
    - CHECK SQL INJECTION query
    - COMPLIANCE REPORT type [DAYS n]
    - SECURITY STATS
    - HIGH RISK EVENTS [THRESHOLD n]
    """
    
    AUDIT_LOG_PATTERN = re.compile(
        r'AUDIT\s+LOG'
        r'(?:\s+USER\s+(\w+))?'
        r'(?:\s+TYPE\s+(\w+))?'
        r'(?:\s+RISK\s+(\d+))?',
        re.IGNORECASE
    )
    
    EXPORT_AUDIT_PATTERN = re.compile(
        r'EXPORT\s+AUDIT\s+LOG'
        r'(?:\s+FORMAT\s+(\w+))?',
        re.IGNORECASE
    )
    
    GRANT_ROLE_PATTERN = re.compile(
        r'GRANT\s+ROLE\s+(\w+)\s+(\w+)',
        re.IGNORECASE
    )
    
    REVOKE_ROLE_PATTERN = re.compile(
        r'REVOKE\s+ROLE\s+(\w+)\s+(\w+)',
        re.IGNORECASE
    )
    
    CHECK_PERMISSION_PATTERN = re.compile(
        r'CHECK\s+PERMISSION\s+(\w+)\s+(\w+)',
        re.IGNORECASE
    )
    
    ENCRYPT_COLUMN_PATTERN = re.compile(
        r'ENCRYPT\s+COLUMN\s+(\w+)\s+(\w+)\s+(.+)',
        re.IGNORECASE
    )
    
    DECRYPT_COLUMN_PATTERN = re.compile(
        r'DECRYPT\s+COLUMN\s+(\w+)\s+(\w+)\s+(.+)',
        re.IGNORECASE
    )
    
    VALIDATE_PASSWORD_PATTERN = re.compile(
        r'VALIDATE\s+PASSWORD\s+(.+)',
        re.IGNORECASE
    )
    
    CHECK_SQL_INJECTION_PATTERN = re.compile(
        r'CHECK\s+SQL\s+INJECTION\s+(.+)',
        re.IGNORECASE
    )
    
    COMPLIANCE_REPORT_PATTERN = re.compile(
        r'COMPLIANCE\s+REPORT\s+(\w+)'
        r'(?:\s+DAYS\s+(\d+))?',
        re.IGNORECASE
    )
    
    SECURITY_STATS_PATTERN = re.compile(
        r'SECURITY\s+STATS',
        re.IGNORECASE
    )
    
    HIGH_RISK_EVENTS_PATTERN = re.compile(
        r'HIGH\s+RISK\s+EVENTS'
        r'(?:\s+THRESHOLD\s+(\d+))?',
        re.IGNORECASE
    )
    
    def parse(self, query: str) -> Optional[Dict[str, Any]]:
        """Parse a security command."""
        query = query.strip()
        upper = query.upper()
        
        # AUDIT LOG
        match = self.AUDIT_LOG_PATTERN.match(query)
        if match:
            return {
                'type': 'AUDIT_LOG',
                'command': 'audit_log',
                'user_id': match.group(1),
                'event_type': match.group(2),
                'min_risk': int(match.group(3)) if match.group(3) else 0
            }
        
        # EXPORT AUDIT LOG
        match = self.EXPORT_AUDIT_PATTERN.match(query)
        if match:
            return {
                'type': 'EXPORT_AUDIT_LOG',
                'command': 'export_audit_log',
                'format': match.group(1) or 'json'
            }
        
        # GRANT ROLE
        match = self.GRANT_ROLE_PATTERN.match(query)
        if match:
            return {
                'type': 'GRANT_ROLE',
                'command': 'grant_role',
                'user_id': match.group(1),
                'role': match.group(2)
            }
        
        # REVOKE ROLE
        match = self.REVOKE_ROLE_PATTERN.match(query)
        if match:
            return {
                'type': 'REVOKE_ROLE',
                'command': 'revoke_role',
                'user_id': match.group(1),
                'role': match.group(2)
            }
        
        # CHECK PERMISSION
        match = self.CHECK_PERMISSION_PATTERN.match(query)
        if match:
            return {
                'type': 'CHECK_PERMISSION',
                'command': 'check_permission',
                'user_id': match.group(1),
                'permission': match.group(2)
            }
        
        # ENCRYPT COLUMN
        match = self.ENCRYPT_COLUMN_PATTERN.match(query)
        if match:
            return {
                'type': 'ENCRYPT_COLUMN',
                'command': 'encrypt_column',
                'table': match.group(1),
                'column': match.group(2),
                'value': match.group(3)
            }
        
        # DECRYPT COLUMN
        match = self.DECRYPT_COLUMN_PATTERN.match(query)
        if match:
            return {
                'type': 'DECRYPT_COLUMN',
                'command': 'decrypt_column',
                'table': match.group(1),
                'column': match.group(2),
                'ciphertext': match.group(3)
            }
        
        # VALIDATE PASSWORD
        match = self.VALIDATE_PASSWORD_PATTERN.match(query)
        if match:
            return {
                'type': 'VALIDATE_PASSWORD',
                'command': 'validate_password',
                'password': match.group(1)
            }
        
        # CHECK SQL INJECTION
        match = self.CHECK_SQL_INJECTION_PATTERN.match(query)
        if match:
            return {
                'type': 'CHECK_SQL_INJECTION',
                'command': 'sql_injection_check',
                'query': match.group(1)
            }
        
        # COMPLIANCE REPORT
        match = self.COMPLIANCE_REPORT_PATTERN.match(query)
        if match:
            return {
                'type': 'COMPLIANCE_REPORT',
                'command': 'compliance_report',
                'report_type': match.group(1),
                'days': int(match.group(2)) if match.group(2) else 30
            }
        
        # SECURITY STATS
        if self.SECURITY_STATS_PATTERN.match(query):
            return {
                'type': 'SECURITY_STATS',
                'command': 'security_stats'
            }
        
        # HIGH RISK EVENTS
        match = self.HIGH_RISK_EVENTS_PATTERN.match(query)
        if match:
            return {
                'type': 'HIGH_RISK_EVENTS',
                'command': 'high_risk_events',
                'threshold': int(match.group(1)) if match.group(1) else 50
            }
        
        return None


_security_parser = None


def get_security_parser():
    global _security_parser
    if _security_parser is None:
        _security_parser = SecurityParser()
    return _security_parser
