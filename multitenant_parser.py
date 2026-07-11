"""
Parser extensions for multi-tenant commands.

Adds CREATE TENANT, DROP TENANT, USE TENANT, LIST TENANTS,
TENANT STATS, SET QUOTA, and ROW POLICY commands.
"""

import re
from typing import Dict, Any, Optional


class MultitenantParser:
    """
    Parser for multi-tenant commands.
    
    Supports:
    - CREATE TENANT id NAME name [STORAGE n] [QPM n] [CONNECTIONS n]
    - DROP TENANT id
    - USE TENANT id
    - LIST TENANTS
    - TENANT STATS [id]
    - SET TENANT QUOTA id STORAGE n
    - ADD ROW POLICY tenant_id name ON table CONDITION expr
    - REMOVE ROW POLICY tenant_id name
    - CHECK QUOTA tenant_id
    - TENANT BACKUP id TO path
    - TENANT RESTORE id FROM path
    """
    
    CREATE_TENANT_PATTERN = re.compile(
        r'CREATE\s+TENANT\s+(\w+)'
        r'\s+NAME\s+(\w+)'
        r'(?:\s+STORAGE\s+(\d+\.?\d*))?'
        r'(?:\s+QPM\s+(\d+))?'
        r'(?:\s+CONNECTIONS\s+(\d+))?'
        r'(?:\s+TABLES\s+(\d+))?',
        re.IGNORECASE
    )
    
    DROP_TENANT_PATTERN = re.compile(
        r'DROP\s+TENANT\s+(\w+)(?:\s+FORCE)?',
        re.IGNORECASE
    )
    
    USE_TENANT_PATTERN = re.compile(
        r'USE\s+TENANT\s+(\w+)',
        re.IGNORECASE
    )
    
    LIST_TENANTS_PATTERN = re.compile(
        r'LIST\s+TENANTS(?:\s+ALL)?',
        re.IGNORECASE
    )
    
    TENANT_STATS_PATTERN = re.compile(
        r'TENANT\s+STATS(?:\s+(\w+))?',
        re.IGNORECASE
    )
    
    SET_QUOTA_PATTERN = re.compile(
        r'SET\s+TENANT\s+QUOTA\s+(\w+)'
        r'(?:\s+STORAGE\s+(\d+\.?\d*))?'
        r'(?:\s+QPM\s+(\d+))?'
        r'(?:\s+CONNECTIONS\s+(\d+))?',
        re.IGNORECASE
    )
    
    ADD_ROW_POLICY_PATTERN = re.compile(
        r'ADD\s+ROW\s+POLICY\s+(\w+)'
        r'\s+(\w+)'
        r'\s+ON\s+(\S+)'
        r'\s+CONDITION\s+(.+)',
        re.IGNORECASE
    )
    
    REMOVE_ROW_POLICY_PATTERN = re.compile(
        r'REMOVE\s+ROW\s+POLICY\s+(\w+)\s+(\w+)',
        re.IGNORECASE
    )
    
    CHECK_QUOTA_PATTERN = re.compile(
        r'CHECK\s+QUOTA\s+(\w+)',
        re.IGNORECASE
    )
    
    TENANT_BACKUP_PATTERN = re.compile(
        r'TENANT\s+BACKUP\s+(\w+)\s+TO\s+(\S+)',
        re.IGNORECASE
    )
    
    TENANT_RESTORE_PATTERN = re.compile(
        r'TENANT\s+RESTORE\s+(\w+)\s+FROM\s+(\S+)',
        re.IGNORECASE
    )
    
    def parse(self, query: str) -> Optional[Dict[str, Any]]:
        """Parse a multi-tenant command."""
        query = query.strip()
        upper = query.upper()
        
        # CREATE TENANT
        match = self.CREATE_TENANT_PATTERN.match(query)
        if match:
            return {
                'type': 'CREATE_TENANT',
                'command': 'create_tenant',
                'tenant_id': match.group(1),
                'name': match.group(2),
                'storage_gb': float(match.group(3)) if match.group(3) else 10.0,
                'queries_per_minute': int(match.group(4)) if match.group(4) else 1000,
                'max_connections': int(match.group(5)) if match.group(5) else 100,
                'max_tables': int(match.group(6)) if match.group(6) else 100
            }
        
        # DROP TENANT
        match = self.DROP_TENANT_PATTERN.match(query)
        if match:
            return {
                'type': 'DROP_TENANT',
                'command': 'drop_tenant',
                'tenant_id': match.group(1),
                'force': 'FORCE' in upper
            }
        
        # USE TENANT
        match = self.USE_TENANT_PATTERN.match(query)
        if match:
            return {
                'type': 'USE_TENANT',
                'command': 'use_tenant',
                'tenant_id': match.group(1)
            }
        
        # LIST TENANTS
        if self.LIST_TENANTS_PATTERN.match(query):
            return {
                'type': 'LIST_TENANTS',
                'command': 'list_tenants'
            }
        
        # TENANT STATS
        match = self.TENANT_STATS_PATTERN.match(query)
        if match:
            return {
                'type': 'TENANT_STATS',
                'command': 'tenant_stats',
                'tenant_id': match.group(1)
            }
        
        # SET TENANT QUOTA
        match = self.SET_QUOTA_PATTERN.match(query)
        if match:
            return {
                'type': 'SET_QUOTA',
                'command': 'set_tenant_quota',
                'tenant_id': match.group(1),
                'storage_gb': float(match.group(2)) if match.group(2) else None,
                'queries_per_minute': int(match.group(3)) if match.group(3) else None,
                'max_connections': int(match.group(4)) if match.group(4) else None
            }
        
        # ADD ROW POLICY
        match = self.ADD_ROW_POLICY_PATTERN.match(query)
        if match:
            return {
                'type': 'ADD_ROW_POLICY',
                'command': 'add_row_policy',
                'tenant_id': match.group(1),
                'policy_name': match.group(2),
                'table_pattern': match.group(3),
                'condition': match.group(4)
            }
        
        # REMOVE ROW POLICY
        match = self.REMOVE_ROW_POLICY_PATTERN.match(query)
        if match:
            return {
                'type': 'REMOVE_ROW_POLICY',
                'command': 'remove_row_policy',
                'tenant_id': match.group(1),
                'policy_name': match.group(2)
            }
        
        # CHECK QUOTA
        match = self.CHECK_QUOTA_PATTERN.match(query)
        if match:
            return {
                'type': 'CHECK_QUOTA',
                'command': 'check_quota',
                'tenant_id': match.group(1)
            }
        
        # TENANT BACKUP
        match = self.TENANT_BACKUP_PATTERN.match(query)
        if match:
            return {
                'type': 'TENANT_BACKUP',
                'command': 'tenant_backup',
                'tenant_id': match.group(1),
                'backup_path': match.group(2)
            }
        
        # TENANT RESTORE
        match = self.TENANT_RESTORE_PATTERN.match(query)
        if match:
            return {
                'type': 'TENANT_RESTORE',
                'command': 'tenant_restore',
                'tenant_id': match.group(1),
                'backup_path': match.group(2)
            }
        
        return None


_multitenant_parser = None


def get_multitenant_parser():
    global _multitenant_parser
    if _multitenant_parser is None:
        _multitenant_parser = MultitenantParser()
    return _multitenant_parser
