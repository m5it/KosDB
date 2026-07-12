
"""
Batch Migration Operations for KosDB v2.3.0

Provides batch operations for schema migrations:
- MIGRATE commands in batch sequences
- Conditional migrations: MIGRATE UP IF PENDING
- Batch rollback capabilities
- Migration dry-run in batch: MIGRATE DRY-RUN
- Migration verification after batch
- Migration status reporting for batches
"""

import re
import time
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from enum import Enum

# Import migration support
try:
    from schema_migration import (
        Migration, MigrationStep, MigrationStatus, MigrationType,
        MigrationExecutor, MigrationHistory, SchemaVersion
    )
    MIGRATION_AVAILABLE = True
except ImportError:
    MIGRATION_AVAILABLE = False

logger = logging.getLogger(__name__)


class BatchMigrationStatus(Enum):
    """Status of batch migration operation."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    VERIFIED = "verified"
    ROLLED_BACK = "rolled_back"


@dataclass
class BatchMigrationResult:
    """Result of a batch migration operation."""
    migration_id: str
    status: BatchMigrationStatus
    direction: str
    steps_executed: int
    steps_total: int
    elapsed_ms: float
    error_message: Optional[str] = None
    dry_run: bool = False
    verification_passed: Optional[bool] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'migration_id': self.migration_id,
            'status': self.status.value,
            'direction': self.direction,
            'steps_executed': self.steps_executed,
            'steps_total': self.steps_total,
            'elapsed_ms': self.elapsed_ms,
            'error_message': self.error_message,
            'dry_run': self.dry_run,
            'verification_passed': self.verification_passed
        }


@dataclass
class BatchMigrationReport:
    """Report for batch migration operations."""
    total_migrations: int
    successful: int
    failed: int
    rolled_back: int
    pending: int
    total_elapsed_ms: float
    results: List[BatchMigrationResult]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_migrations': self.total_migrations,
            'successful': self.successful,
            'failed': self.failed,
            'rolled_back': self.rolled_back,
            'pending': self.pending,
            'total_elapsed_ms': self.total_elapsed_ms,
            'results': [r.to_dict() for r in self.results]
        }


class BatchMigrationManager:
    """Manager for batch migration operations."""
    
    def __init__(self, db_connection: Optional[Any] = None, 
                 history_path: str = ".migrations"):
        self.db = db_connection
        self.history_path = history_path
        self._results: List[BatchMigrationResult] = []
        self._status_callbacks: List[Callable] = []
        
        if MIGRATION_AVAILABLE:
            self.executor = MigrationExecutor(db_connection) if db_connection else None
            self.history = MigrationHistory(history_path)
        else:
            self.executor = None
            self.history = None
    
    def migrate_up(
        self,
        migration_id: Optional[str] = None,
        dry_run: bool = False,
        verify: bool = True
    ) -> BatchMigrationResult:
        """Execute migration up (forward)."""
        start_time = time.time()
        
        if not MIGRATION_AVAILABLE or not self.executor:
            return BatchMigrationResult(
                migration_id=migration_id or 'unknown',
                status=BatchMigrationStatus.FAILED,
                direction='up',
                steps_executed=0,
                steps_total=0,
                elapsed_ms=0,
                error_message='Migration system not available',
                dry_run=dry_run
            )
        
        try:
            if migration_id:
                migration = self.history.get_migration(migration_id)
                if not migration:
                    return BatchMigrationResult(
                        migration_id=migration_id,
                        status=BatchMigrationStatus.FAILED,
                        direction='up',
                        steps_executed=0,
                        steps_total=0,
                        elapsed_ms=(time.time() - start_time) * 1000,
                        error_message=f'Migration {migration_id} not found',
                        dry_run=dry_run
                    )
                migrations = [migration]
            else:
                migrations = self.history.get_pending_migrations()
            
            total_steps = sum(len(m.steps) for m in migrations)
            executed_steps = 0
            
            for migration in migrations:
                if dry_run:
                    executed_steps += len(migration.steps)
                    continue
                
                success = self.executor.execute_forward(migration)
                if success:
                    self.history.record_migration(migration)
                    executed_steps += len(migration.steps)
                else:
                    elapsed_ms = (time.time() - start_time) * 1000
                    result = BatchMigrationResult(
                        migration_id=migration.migration_id,
                        status=BatchMigrationStatus.FAILED,
                        direction='up',
                        steps_executed=executed_steps,
                        steps_total=total_steps,
                        elapsed_ms=elapsed_ms,
                        error_message='Migration execution failed',
                        dry_run=dry_run
                    )
                    self._results.append(result)
                    self._notify_status(result)
                    return result
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            verification_passed = None
            if verify and not dry_run and migrations:
                verification_passed = self._verify_migration(migrations[-1])
            
            result = BatchMigrationResult(
                migration_id=migrations[-1].migration_id if migrations else 'none',
                status=BatchMigrationStatus.COMPLETED,
                direction='up',
                steps_executed=executed_steps,
                steps_total=total_steps,
                elapsed_ms=elapsed_ms,
                dry_run=dry_run,
                verification_passed=verification_passed
            )
            
            self._results.append(result)
            self._notify_status(result)
            
            return result
            
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            result = BatchMigrationResult(
                migration_id=migration_id or 'unknown',
                status=BatchMigrationStatus.FAILED,
                direction='up',
                steps_executed=0,
                steps_total=0,
                elapsed_ms=elapsed_ms,
                error_message=str(e),
                dry_run=dry_run
            )
            self._results.append(result)
            return result
    
    def migrate_down(
        self,
        migration_id: str,
        dry_run: bool = False
    ) -> BatchMigrationResult:
        """Execute migration down (rollback)."""
        start_time = time.time()
        
        if not MIGRATION_AVAILABLE or not self.executor:
            return BatchMigrationResult(
                migration_id=migration_id,
                status=BatchMigrationStatus.FAILED,
                direction='down',
                steps_executed=0,
                steps_total=0,
                elapsed_ms=0,
                error_message='Migration system not available',
                dry_run=dry_run
            )
        
        try:
            migration = self.history.get_migration(migration_id)
            if not migration:
                return BatchMigrationResult(
                    migration_id=migration_id,
                    status=BatchMigrationStatus.FAILED,
                    direction='down',
                    steps_executed=0,
                    steps_total=0,
                    elapsed_ms=(time.time() - start_time) * 1000,
                    error_message=f'Migration {migration_id} not found',
                    dry_run=dry_run
                )
            
            if dry_run:
                result = BatchMigrationResult(
                    migration_id=migration_id,
                    status=BatchMigrationStatus.COMPLETED,
                    direction='down',
                    steps_executed=len(migration.steps),
                    steps_total=len(migration.steps),
                    elapsed_ms=(time.time() - start_time) * 1000,
                    dry_run=True
                )
            else:
                success = self.executor.execute_rollback(migration)
                elapsed_ms = (time.time() - start_time) * 1000
                
                if success:
                    self.history.record_migration(migration)
                    result = BatchMigrationResult(
                        migration_id=migration_id,
                        status=BatchMigrationStatus.ROLLED_BACK,
                        direction='down',
                        steps_executed=len(migration.steps),
                        steps_total=len(migration.steps),
                        elapsed_ms=elapsed_ms,
                        dry_run=False
                    )
                else:
                    result = BatchMigrationResult(
                        migration_id=migration_id,
                        status=BatchMigrationStatus.FAILED,
                        direction='down',
                        steps_executed=0,
                        steps_total=len(migration.steps),
                        elapsed_ms=elapsed_ms,
                        error_message='Rollback failed',
                        dry_run=False
                    )
            
            self._results.append(result)
            self._notify_status(result)
            
            return result
            
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            result = BatchMigrationResult(
                migration_id=migration_id,
                status=BatchMigrationStatus.FAILED,
                direction='down',
                steps_executed=0,
                steps_total=0,
                elapsed_ms=elapsed_ms,
                error_message=str(e),
                dry_run=dry_run
            )
            self._results.append(result)
            return result
    
    def check_pending(self) -> bool:
        """Check if there are pending migrations."""
        if not MIGRATION_AVAILABLE or not self.history:
            return False
        
        pending = self.history.get_pending_migrations()
        return len(pending) > 0
    
    def get_pending_count(self) -> int:
        """Get number of pending migrations."""
        if not MIGRATION_AVAILABLE or not self.history:
            return 0
        
        return len(self.history.get_pending_migrations())
    
    def get_current_version(self) -> Optional[str]:
        """Get current schema version."""
        if not MIGRATION_AVAILABLE or not self.history:
            return None
        
        version = self.history.get_current_version()
        return str(version) if version else None
    
    def _verify_migration(self, migration: Any) -> bool:
        """Verify migration was applied correctly."""
        if not MIGRATION_AVAILABLE:
            return False
        
        for step in migration.steps:
            if not step.verify_checksum():
                return False
        
        return True
    
    def generate_report(self) -> BatchMigrationReport:
        """Generate report of all batch migration operations."""
        successful = sum(1 for r in self._results 
                        if r.status == BatchMigrationStatus.COMPLETED)
        failed = sum(1 for r in self._results 
                    if r.status == BatchMigrationStatus.FAILED)
        rolled_back = sum(1 for r in self._results 
                         if r.status == BatchMigrationStatus.ROLLED_BACK)
        pending = sum(1 for r in self._results 
                     if r.status == BatchMigrationStatus.PENDING)
        
        total_elapsed = sum(r.elapsed_ms for r in self._results)
        
        return BatchMigrationReport(
            total_migrations=len(self._results),
            successful=successful,
            failed=failed,
            rolled_back=rolled_back,
            pending=pending,
            total_elapsed_ms=total_elapsed,
            results=self._results[:]
        )
    
    def register_status_callback(self, callback: Callable):
        """Register callback for status updates."""
        self._status_callbacks.append(callback)
    
    def _notify_status(self, result: BatchMigrationResult):
        """Notify status callbacks."""
        for callback in self._status_callbacks:
            try:
                callback(result)
            except Exception as e:
                logger.warning(f"Status callback failed: {e}")
    
    def clear_results(self):
        """Clear migration results history."""
        self._results.clear()


def parse_migrate_up(command: str) -> Dict[str, Any]:
    """Parse MIGRATE UP command."""
    match = re.match(
        r'MIGRATE\s+UP(?:\s+(\w+))?(?:\s+DRY-RUN)?(?:\s+VERIFY)?',
        command,
        re.IGNORECASE
    )
    
    if not match:
        return {}
    
    return {
        'type': 'migrate_up',
        'migration_id': match.group(1),
        'dry_run': 'DRY-RUN' in command.upper(),
        'verify': 'VERIFY' in command.upper()
    }


def parse_migrate_up_if(command: str) -> Dict[str, Any]:
    """Parse MIGRATE UP IF conditional command."""
    match = re.match(
        r'MIGRATE\s+UP\s+IF\s+(PENDING|VERSION\s*[<>=]+\s*[\d.]+)',
        command,
        re.IGNORECASE
    )
    
    if not match:
        return {}
    
    condition = match.group(1)
    return {
        'type': 'migrate_up_if',
        'condition': condition,
        'dry_run': False,
        'verify': True
    }


def parse_migrate_down(command: str) -> Dict[str, Any]:
    """Parse MIGRATE DOWN (rollback) command."""
    match = re.match(
        r'MIGRATE\s+DOWN\s+(\w+)(?:\s+DRY-RUN)?',
        command,
        re.IGNORECASE
    )
    
    if not match:
        return {}
    
    return {
        'type': 'migrate_down',
        'migration_id': match.group(1),
        'dry_run': 'DRY-RUN' in command.upper()
    }


def parse_migrate_dry_run(command: str) -> Dict[str, Any]:
    """Parse MIGRATE DRY-RUN command."""
    match = re.match(
        r'MIGRATE\s+DRY-RUN(?:\s+(UP|DOWN))?(?:\s+(\w+))?',
        command,
        re.IGNORECASE
    )
    
    if not match:
        return {}
    
    direction = (match.group(1) or 'UP').lower()
    
    return {
        'type': f'migrate_{direction}',
        'migration_id': match.group(2),
        'dry_run': True,
        'verify': False
    }


def parse_migrate_status(command: str) -> Dict[str, Any]:
    """Parse MIGRATE STATUS command."""
    if re.match(r'MIGRATE\s+STATUS', command, re.IGNORECASE):
        return {'type': 'migrate_status'}
    return {}


def parse_migration_commands(commands: List[str]) -> List[Dict[str, Any]]:
    """Parse a list of migration commands."""
    operations = []
    
    for cmd in commands:
        cmd = cmd.strip()
        
        if re.match(r'MIGRATE\s+UP\s+IF', cmd, re.IGNORECASE):
            op = parse_migrate_up_if(cmd)
        elif re.match(r'MIGRATE\s+UP', cmd, re.IGNORECASE):
            op = parse_migrate_up(cmd)
        elif re.match(r'MIGRATE\s+DOWN', cmd, re.IGNORECASE):
            op = parse_migrate_down(cmd)
        elif re.match(r'MIGRATE\s+DRY-RUN', cmd, re.IGNORECASE):
            op = parse_migrate_dry_run(cmd)
        elif re.match(r'MIGRATE\s+STATUS', cmd, re.IGNORECASE):
            op = parse_migrate_status(cmd)
        else:
            continue
        
        if op:
            operations.append(op)
    
    return operations


_batch_migration_manager: Optional[BatchMigrationManager] = None


def get_batch_migration_manager(
    db_connection: Optional[Any] = None,
    history_path: str = ".migrations"
) -> BatchMigrationManager:
    """Get global batch migration manager."""
    global _batch_migration_manager
    if _batch_migration_manager is None:
        _batch_migration_manager = BatchMigrationManager(db_connection, history_path)
    return _batch_migration_manager
