
"""
Batch Multi-Tenant Verification for KosDB v2.3.0

Ensures batch commands respect tenant boundaries:
- Single tenant enforcement across batch
- USE TENANT persistence
- Row-level security policy enforcement
- Tenant quota verification
- CDC event tenant tagging
"""

import re
import time
import logging
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum

# Import multitenant support
try:
    from multitenant import TenantManager, Tenant, ResourceType, QuotaExceededError
    MULTITENANT_AVAILABLE = True
except ImportError:
    MULTITENANT_AVAILABLE = False

# Import CDC support
try:
    from cdc import CDCEvent
    CDC_AVAILABLE = True
except ImportError:
    CDC_AVAILABLE = False

logger = logging.getLogger(__name__)


class BatchTenantError(Exception):
    """Raised when batch violates tenant boundaries."""
    pass


class TenantBoundaryViolation(BatchTenantError):
    """Raised when batch commands target multiple tenants."""
    pass


class TenantQuotaExceeded(BatchTenantError):
    """Raised when batch exceeds tenant quota."""
    pass


@dataclass
class BatchTenantContext:
    """Context for batch tenant verification."""
    tenant_id: Optional[str] = None
    use_tenant_persisted: bool = False
    command_count: int = 0
    rls_policies_applied: int = 0
    cdc_events_tagged: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'tenant_id': self.tenant_id,
            'use_tenant_persisted': self.use_tenant_persisted,
            'command_count': self.command_count,
            'rls_policies_applied': self.rls_policies_applied,
            'cdc_events_tagged': self.cdc_events_tagged
        }


class BatchTenantVerifier:
    """
    Verifies batch commands respect tenant boundaries.
    """
    
    def __init__(self, tenant_manager: Optional[Any] = None):
        """
        Initialize batch tenant verifier.
        
        Args:
            tenant_manager: TenantManager instance
        """
        self.tenant_manager = tenant_manager
        self._current_tenant: Optional[str] = None
        self._tenant_switches: List[Tuple[int, str, str]] = []  # (cmd_idx, from, to)
        self._rls_violations: List[Dict[str, Any]] = []
        self._metrics = {
            'batches_verified': 0,
            'tenant_violations': 0,
            'rls_checks': 0,
            'quota_checks': 0
        }
    
    def verify_batch(
        self,
        commands: List[str],
        initial_tenant: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Verify batch commands respect tenant boundaries.
        
        Args:
            commands: List of SQL commands
            initial_tenant: Starting tenant context
        
        Returns:
            Verification result
        """
        if not MULTITENANT_AVAILABLE or not self.tenant_manager:
            return {
                'valid': True,
                'tenant_id': None,
                'warnings': ['Multi-tenant support not available']
            }
        
        self._current_tenant = initial_tenant
        self._tenant_switches = []
        
        tenant_commands: Dict[str, List[int]] = {}  # tenant -> [command_indices]
        
        for idx, cmd in enumerate(commands):
            cmd_tenant = self._extract_target_tenant(cmd)
            
            if cmd_tenant:
                if cmd_tenant not in tenant_commands:
                    tenant_commands[cmd_tenant] = []
                tenant_commands[cmd_tenant].append(idx)
        
        # Check for multiple tenants
        unique_tenants = set(tenant_commands.keys())
        if len(unique_tenants) > 1:
            self._metrics['tenant_violations'] += 1
            return {
                'valid': False,
                'error': 'Batch commands target multiple tenants',
                'tenants': list(unique_tenants),
                'tenant_commands': {
                    t: idxs for t, idxs in tenant_commands.items()
                }
            }
        
        # Check USE TENANT persistence
        use_tenant_cmd = self._find_use_tenant(commands)
        
        self._metrics['batches_verified'] += 1
        
        return {
            'valid': True,
            'tenant_id': list(unique_tenants)[0] if unique_tenants else initial_tenant,
            'use_tenant_persisted': use_tenant_cmd is not None,
            'command_count': len(commands)
        }
    
    def _extract_target_tenant(self, command: str) -> Optional[str]:
        """
        Extract target tenant from command.
        
        Args:
            command: SQL command
        
        Returns:
            Tenant ID or None
        """
        cmd_upper = command.upper().strip()
        
        # USE TENANT command
        use_match = re.match(r'USE\s+TENANT\s+(\w+)', cmd_upper)
        if use_match:
            tenant_id = use_match.group(1).lower()
            self._current_tenant = tenant_id
            return tenant_id
        
        # Check for explicit tenant references
        tenant_patterns = [
            r'TENANT\s*=\s*[\'"]?(\w+)[\'"]?',
            r'TENANT_ID\s*=\s*[\'"]?(\w+)[\'"]?',
        ]
        
        for pattern in tenant_patterns:
            match = re.search(pattern, cmd_upper)
            if match:
                return match.group(1).lower()
        
        # Return current tenant context
        return self._current_tenant
    
    def _find_use_tenant(self, commands: List[str]) -> Optional[int]:
        """Find index of USE TENANT command."""
        for idx, cmd in enumerate(commands):
            if re.match(r'USE\s+TENANT\s+', cmd.upper().strip()):
                return idx
        return None
    
    def check_tenant_quota(
        self,
        tenant_id: str,
        command_count: int
    ) -> Dict[str, Any]:
        """
        Check if batch would exceed tenant quota.
        
        Args:
            tenant_id: Tenant ID
            command_count: Number of commands in batch
        
        Returns:
            Quota check result
        """
        if not MULTITENANT_AVAILABLE or not self.tenant_manager:
            return {'valid': True}
        
        tenant = self.tenant_manager.get_tenant(tenant_id)
        if not tenant:
            return {
                'valid': False,
                'error': f'Tenant {tenant_id} not found'
            }
        
        self._metrics['quota_checks'] += 1
        
        # Check queries per minute
        if not tenant.check_quota(ResourceType.QUERIES_PER_MINUTE, command_count):
            return {
                'valid': False,
                'error': 'Tenant quota exceeded: queries per minute',
                'tenant_id': tenant_id,
                'requested': command_count,
                'limit': tenant.quota.queries_per_minute,
                'current': tenant.usage.queries_this_minute
            }
        
        return {
            'valid': True,
            'tenant_id': tenant_id,
            'commands_allowed': command_count
        }
    
    def enforce_rls_policies(
        self,
        tenant_id: str,
        table_name: str,
        rows: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Enforce row-level security policies for tenant.
        
        Args:
            tenant_id: Tenant ID
            table_name: Table being accessed
            rows: Rows to filter
        
        Returns:
            Filtered rows
        """
        if not MULTITENANT_AVAILABLE or not self.tenant_manager:
            return rows
        
        tenant = self.tenant_manager.get_tenant(tenant_id)
        if not tenant:
            return []
        
        self._metrics['rls_checks'] += 1
        
        filtered = []
        for row in rows:
            if tenant.check_row_access(table_name, row):
                filtered.append(row)
        
        return filtered
    
    def tag_cdc_events(
        self,
        tenant_id: str,
        events: List[Any]
    ) -> List[Dict[str, Any]]:
        """
        Tag CDC events with tenant ID.
        
        Args:
            tenant_id: Tenant ID
            events: CDC events
        
        Returns:
            Tagged events
        """
        tagged = []
        for event in events:
            tagged_event = dict(event) if hasattr(event, '__dict__') else event
            if isinstance(tagged_event, dict):
                tagged_event['tenant_id'] = tenant_id
            tagged.append(tagged_event)
        
        return tagged
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get verification metrics."""
        return dict(self._metrics)
    
    def get_tenant_switches(self) -> List[Tuple[int, str, str]]:
        """Get list of tenant switches in batch."""
        return self._tenant_switches


class BatchTenantExecutor:
    """
    Executes batches with tenant boundary enforcement.
    """
    
    def __init__(
        self,
        tenant_manager: Optional[Any] = None,
        verifier: Optional[BatchTenantVerifier] = None
    ):
        self.tenant_manager = tenant_manager
        self.verifier = verifier or BatchTenantVerifier(tenant_manager)
        self._context = BatchTenantContext()
    
    def execute_with_tenant_check(
        self,
        commands: List[str],
        executor: callable,
        initial_tenant: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute batch with tenant verification.
        
        Args:
            commands: SQL commands
            executor: Function to execute commands
            initial_tenant: Starting tenant
        
        Returns:
            Execution result
        """
        # Verify tenant boundaries
        verification = self.verifier.verify_batch(commands, initial_tenant)
        
        if not verification['valid']:
            return {
                'success': False,
                'error': verification['error'],
                'verification': verification
            }
        
        tenant_id = verification['tenant_id']
        
        # Check quota
        quota_check = self.verifier.check_tenant_quota(
            tenant_id or 'system',
            len(commands)
        )
        
        if not quota_check['valid']:
            return {
                'success': False,
                'error': quota_check['error'],
                'quota_check': quota_check
            }
        
        # Execute commands
        results = []
        current_tenant = initial_tenant
        
        for idx, cmd in enumerate(commands):
            # Check for USE TENANT
            new_tenant = self._extract_use_tenant(cmd)
            if new_tenant:
                if current_tenant and new_tenant != current_tenant:
                    # Tenant switch detected
                    return {
                        'success': False,
                        'error': f'Tenant switch not allowed in batch: '
                                f'{current_tenant} -> {new_tenant}',
                        'command_index': idx
                    }
                current_tenant = new_tenant
            
            # Execute
            try:
                result = executor(cmd)
                results.append({
                    'index': idx,
                    'command': cmd,
                    'status': 'success',
                    'result': result
                })
            except Exception as e:
                results.append({
                    'index': idx,
                    'command': cmd,
                    'status': 'error',
                    'error': str(e)
                })
        
        self._context.tenant_id = current_tenant
        self._context.command_count = len(commands)
        self._context.use_tenant_persisted = verification.get('use_tenant_persisted', False)
        
        return {
            'success': True,
            'tenant_id': current_tenant,
            'results': results,
            'context': self._context.to_dict()
        }
    
    def _extract_use_tenant(self, command: str) -> Optional[str]:
        """Extract tenant from USE TENANT command."""
        cmd_upper = command.upper().strip()
        match = re.match(r'USE\s+TENANT\s+(\w+)', cmd_upper)
        if match:
            return match.group(1).lower()
        return None


def parse_use_tenant(command: str) -> Tuple[str, Optional[str]]:
    """
    Parse USE TENANT command.
    
    Args:
        command: SQL command
    
    Returns:
        Tuple of (clean_command, tenant_id)
    """
    cmd_upper = command.upper().strip()
    match = re.match(r'USE\s+TENANT\s+(\w+)\s*;?\s*(.*)', cmd_upper, re.DOTALL)
    
    if match:
        tenant_id = match.group(1).lower()
        remaining = match.group(2).strip() if match.group(2) else None
        return remaining or '', tenant_id
    
    return command, None


def is_tenant_command(command: str) -> bool:
    """Check if command is tenant-related."""
    cmd_upper = command.upper().strip()
    return (
        cmd_upper.startswith('USE TENANT') or
        cmd_upper.startswith('CREATE TENANT') or
        cmd_upper.startswith('DROP TENANT') or
        'TENANT_ID' in cmd_upper
    )


# Global verifier
_batch_tenant_verifier: Optional[BatchTenantVerifier] = None


def get_batch_tenant_verifier(tenant_manager: Optional[Any] = None) -> BatchTenantVerifier:
    """Get global batch tenant verifier."""
    global _batch_tenant_verifier
    if _batch_tenant_verifier is None:
        _batch_tenant_verifier = BatchTenantVerifier(tenant_manager)
    return _batch_tenant_verifier
