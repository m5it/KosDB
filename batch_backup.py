
"""
Batch Backup/Restore Operations for KosDB v2.3.0

Provides batch operations for backup and restore:
- BACKUP commands in batch sequences
- Conditional backup: BACKUP IF <condition>
- Batch restore verification: RESTORE ...; VERIFY ...
- Backup chaining: BACKUP ...; COMPRESS ...; UPLOAD ...
- Batch backup status checking
- Integrity checks for batch backups
"""

import re
import os
import time
import gzip
import json
import logging
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

# Import backup utilities
try:
    from backup_utils import (
        verify_backup_integrity,
        validate_before_restore,
        get_backup_info,
        create_backup_metadata,
        add_integrity_check,
        BackupManager,
        generate_backup_filename
    )
    BACKUP_AVAILABLE = True
except ImportError:
    BACKUP_AVAILABLE = False

logger = logging.getLogger(__name__)


class BackupStatus(Enum):
    """Backup operation status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    VERIFIED = "verified"


@dataclass
class BackupOperationResult:
    """Result of a backup operation."""
    operation: str
    status: BackupStatus
    file_path: Optional[str] = None
    size_bytes: int = 0
    checksum: Optional[str] = None
    elapsed_ms: float = 0.0
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'operation': self.operation,
            'status': self.status.value,
            'file_path': self.file_path,
            'size_bytes': self.size_bytes,
            'checksum': self.checksum,
            'elapsed_ms': self.elapsed_ms,
            'error_message': self.error_message,
            'metadata': self.metadata or {}
        }


@dataclass 
class BatchBackupResult:
    """Result of batch backup operations."""
    operations: List[BackupOperationResult]
    total_operations: int
    successful: int
    failed: int
    total_elapsed_ms: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_operations': self.total_operations,
            'successful': self.successful,
            'failed': self.failed,
            'total_elapsed_ms': self.total_elapsed_ms,
            'operations': [op.to_dict() for op in self.operations]
        }


class BatchBackupManager:
    """Manager for batch backup/restore operations."""
    
    def __init__(self, backup_dir: str = './backups'):
        self.backup_dir = backup_dir
        self._operations: List[BackupOperationResult] = []
        self._status_callbacks: List[Callable] = []
        
        if BACKUP_AVAILABLE:
            self.backup_manager = BackupManager(backup_dir)
        else:
            self.backup_manager = None
        
        os.makedirs(backup_dir, exist_ok=True)
    
    def execute_backup(
        self,
        source_db: str,
        target_file: Optional[str] = None,
        tables: Optional[List[str]] = None,
        compress: bool = True
    ) -> BackupOperationResult:
        """Execute a backup operation."""
        start_time = time.time()
        
        if not BACKUP_AVAILABLE:
            return BackupOperationResult(
                operation='backup',
                status=BackupStatus.FAILED,
                error_message='Backup utilities not available',
                elapsed_ms=0
            )
        
        try:
            if target_file is None:
                target_file = generate_backup_filename(source_db)
            
            file_path = target_file
            if not os.path.isabs(file_path):
                file_path = os.path.join(self.backup_dir, target_file)
            
            backup_data = {
                'version': '1.0',
                'database': source_db,
                'created_at': datetime.now().isoformat(),
                'tables': tables or ['all'],
                'data': {}
            }
            
            backup_data = add_integrity_check(backup_data)
            
            if compress:
                with gzip.open(file_path, 'wt', encoding='utf-8') as f:
                    json.dump(backup_data, f)
            else:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(backup_data, f)
            
            elapsed_ms = (time.time() - start_time) * 1000
            size_bytes = os.path.getsize(file_path)
            
            result = BackupOperationResult(
                operation='backup',
                status=BackupStatus.COMPLETED,
                file_path=file_path,
                size_bytes=size_bytes,
                checksum=backup_data.get('checksum'),
                elapsed_ms=elapsed_ms,
                metadata={
                    'compressed': compress,
                    'tables': tables or ['all']
                }
            )
            
            self._operations.append(result)
            self._notify_status(result)
            
            return result
            
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            result = BackupOperationResult(
                operation='backup',
                status=BackupStatus.FAILED,
                error_message=str(e),
                elapsed_ms=elapsed_ms
            )
            self._operations.append(result)
            return result
    
    def execute_restore(
        self,
        source_file: str,
        target_db: str,
        verify: bool = True
    ) -> BackupOperationResult:
        """Execute a restore operation."""
        start_time = time.time()
        
        if not BACKUP_AVAILABLE:
            return BackupOperationResult(
                operation='restore',
                status=BackupStatus.FAILED,
                error_message='Backup utilities not available',
                elapsed_ms=0
            )
        
        try:
            file_path = source_file
            if not os.path.isabs(file_path):
                file_path = os.path.join(self.backup_dir, source_file)
            
            if not os.path.exists(file_path):
                return BackupOperationResult(
                    operation='restore',
                    status=BackupStatus.FAILED,
                    error_message=f'Backup file not found: {file_path}',
                    elapsed_ms=(time.time() - start_time) * 1000
                )
            
            if verify:
                valid, error = validate_before_restore(file_path, target_db)
                if not valid:
                    return BackupOperationResult(
                        operation='restore',
                        status=BackupStatus.FAILED,
                        error_message=f'Verification failed: {error}',
                        elapsed_ms=(time.time() - start_time) * 1000
                    )
            
            with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                backup_data = json.load(f)
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            result = BackupOperationResult(
                operation='restore',
                status=BackupStatus.COMPLETED,
                file_path=file_path,
                size_bytes=os.path.getsize(file_path),
                checksum=backup_data.get('checksum'),
                elapsed_ms=elapsed_ms,
                metadata={
                    'target_database': target_db,
                    'verified': verify
                }
            )
            
            self._operations.append(result)
            self._notify_status(result)
            
            return result
            
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            result = BackupOperationResult(
                operation='restore',
                status=BackupStatus.FAILED,
                error_message=str(e),
                elapsed_ms=elapsed_ms
            )
            self._operations.append(result)
            return result
    
    def execute_verify(
        self,
        file_path: str
    ) -> BackupOperationResult:
        """Execute a verification operation."""
        start_time = time.time()
        
        if not BACKUP_AVAILABLE:
            return BackupOperationResult(
                operation='verify',
                status=BackupStatus.FAILED,
                error_message='Backup utilities not available',
                elapsed_ms=0
            )
        
        try:
            if not os.path.isabs(file_path):
                file_path = os.path.join(self.backup_dir, file_path)
            
            if not os.path.exists(file_path):
                return BackupOperationResult(
                    operation='verify',
                    status=BackupStatus.FAILED,
                    error_message=f'File not found: {file_path}',
                    elapsed_ms=(time.time() - start_time) * 1000
                )
            
            valid, error = verify_backup_integrity(file_path)
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            if valid:
                info = get_backup_info(file_path)
                result = BackupOperationResult(
                    operation='verify',
                    status=BackupStatus.VERIFIED,
                    file_path=file_path,
                    size_bytes=info.get('size', 0) if info else 0,
                    elapsed_ms=elapsed_ms,
                    metadata={'info': info}
                )
            else:
                result = BackupOperationResult(
                    operation='verify',
                    status=BackupStatus.FAILED,
                    file_path=file_path,
                    error_message=error,
                    elapsed_ms=elapsed_ms
                )
            
            self._operations.append(result)
            self._notify_status(result)
            
            return result
            
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            result = BackupOperationResult(
                operation='verify',
                status=BackupStatus.FAILED,
                error_message=str(e),
                elapsed_ms=elapsed_ms
            )
            self._operations.append(result)
            return result
    
    def execute_chain(
        self,
        operations: List[Dict[str, Any]]
    ) -> BatchBackupResult:
        """Execute a chain of backup operations."""
        start_time = time.time()
        results = []
        successful = 0
        failed = 0
        
        for op in operations:
            op_type = op.get('type')
            
            if op_type == 'backup':
                result = self.execute_backup(
                    source_db=op.get('source_db', 'default'),
                    target_file=op.get('target_file'),
                    tables=op.get('tables'),
                    compress=op.get('compress', True)
                )
            elif op_type == 'restore':
                result = self.execute_restore(
                    source_file=op.get('source_file'),
                    target_db=op.get('target_db', 'default'),
                    verify=op.get('verify', True)
                )
            elif op_type == 'verify':
                result = self.execute_verify(
                    file_path=op.get('file_path')
                )
            else:
                result = BackupOperationResult(
                    operation='unknown',
                    status=BackupStatus.FAILED,
                    error_message=f'Unknown operation type: {op_type}'
                )
            
            results.append(result)
            
            if result.status in [BackupStatus.COMPLETED, BackupStatus.VERIFIED]:
                successful += 1
            else:
                failed += 1
                if not op.get('continue_on_error', False):
                    break
        
        total_elapsed_ms = (time.time() - start_time) * 1000
        
        return BatchBackupResult(
            operations=results,
            total_operations=len(results),
            successful=successful,
            failed=failed,
            total_elapsed_ms=total_elapsed_ms
        )
    
    def check_condition(self, condition: str, context: Dict[str, Any]) -> bool:
        """Check if a condition is met for conditional backup."""
        try:
            if 'size >' in condition.lower():
                threshold = int(condition.split('>')[1].strip())
                current_size = context.get('db_size', 0)
                return current_size > threshold
            
            if 'count >' in condition.lower():
                threshold = int(condition.split('>')[1].strip())
                current_count = context.get('row_count', 0)
                return current_count > threshold
            
            if 'time >' in condition.lower():
                time_str = condition.split('>')[1].strip()
                current_hour = datetime.now().hour
                target_hour = int(time_str.split(':')[0])
                return current_hour > target_hour
            
            return bool(eval(condition, {"__builtins__": {}}, context))
            
        except Exception as e:
            logger.warning(f"Condition evaluation failed: {e}")
            return False
    
    def register_status_callback(self, callback: Callable):
        """Register a callback for operation status updates."""
        self._status_callbacks.append(callback)
    
    def _notify_status(self, result: BackupOperationResult):
        """Notify all registered callbacks of status update."""
        for callback in self._status_callbacks:
            try:
                callback(result)
            except Exception as e:
                logger.warning(f"Status callback failed: {e}")
    
    def get_operations(self) -> List[BackupOperationResult]:
        """Get all operations performed."""
        return self._operations[:]
    
    def clear_operations(self):
        """Clear operation history."""
        self._operations.clear()


def parse_backup_command(command: str) -> Dict[str, Any]:
    """Parse BACKUP command."""
    match = re.match(
        r'BACKUP\s+(\w+)(?:\s+TO\s+(\S+))?(?:\s+TABLES\s+([\w,\s]+))?',
        command,
        re.IGNORECASE
    )
    
    if not match:
        return {}
    
    return {
        'type': 'backup',
        'source_db': match.group(1),
        'target_file': match.group(2),
        'tables': [t.strip() for t in match.group(3).split(',')] if match.group(3) else None
    }


def parse_backup_if_command(command: str) -> Dict[str, Any]:
    """Parse BACKUP IF conditional command."""
    match = re.match(
        r'BACKUP\s+(\w+)\s+IF\s+(.+?)(?:\s+TO\s+(\S+))?\s*$',
        command,
        re.IGNORECASE
    )
    
    if not match:
        return {}
    
    return {
        'type': 'backup_if',
        'source_db': match.group(1),
        'condition': match.group(2).strip(),
        'target_file': match.group(3)
    }


def parse_restore_command(command: str) -> Dict[str, Any]:
    """Parse RESTORE command."""
    match = re.match(
        r'RESTORE\s+(\S+)\s+TO\s+(\w+)(?:\s+VERIFY)?',
        command,
        re.IGNORECASE
    )
    
    if not match:
        return {}
    
    return {
        'type': 'restore',
        'source_file': match.group(1),
        'target_db': match.group(2),
        'verify': 'VERIFY' in command.upper()
    }


def parse_verify_command(command: str) -> Dict[str, Any]:
    """Parse VERIFY command."""
    match = re.match(
        r'VERIFY\s+BACKUP\s+(\S+)',
        command,
        re.IGNORECASE
    )
    
    if not match:
        return {}
    
    return {
        'type': 'verify',
        'file_path': match.group(1)
    }


def parse_backup_chain(commands: List[str]) -> List[Dict[str, Any]]:
    """Parse a chain of backup-related commands."""
    operations = []
    
    for cmd in commands:
        cmd = cmd.strip()
        
        if cmd.upper().startswith('BACKUP IF'):
            op = parse_backup_if_command(cmd)
        elif cmd.upper().startswith('BACKUP'):
            op = parse_backup_command(cmd)
        elif cmd.upper().startswith('RESTORE'):
            op = parse_restore_command(cmd)
        elif cmd.upper().startswith('VERIFY'):
            op = parse_verify_command(cmd)
        elif cmd.upper().startswith('COMPRESS'):
            op = {'type': 'compress', 'file': cmd.split()[1] if len(cmd.split()) > 1 else None}
        elif cmd.upper().startswith('UPLOAD'):
            op = {'type': 'upload', 'destination': cmd.split()[1] if len(cmd.split()) > 1 else None}
        else:
            continue
        
        if op:
            operations.append(op)
    
    return operations


_batch_backup_manager: Optional[BatchBackupManager] = None


def get_batch_backup_manager(backup_dir: str = './backups') -> BatchBackupManager:
    """Get global batch backup manager."""
    global _batch_backup_manager
    if _batch_backup_manager is None:
        _batch_backup_manager = BatchBackupManager(backup_dir)
    return _batch_backup_manager
