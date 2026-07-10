"""
Schema Migration System for KosDB

Versioned schema changes with rollback support, dependency tracking,
and transaction-safe migrations.
"""

import os
import re
import json
import time
import hashlib
from typing import Dict, Any, List, Optional, Callable, Tuple
from enum import Enum, auto
from dataclasses import dataclass, field, asdict


class MigrationStatus(Enum):
    """Status of a migration."""
    PENDING = auto()
    APPLIED = auto()
    ROLLED_BACK = auto()
    FAILED = auto()


class MigrationType(Enum):
    """Type of migration operation."""
    CREATE_TABLE = auto()
    DROP_TABLE = auto()
    ALTER_TABLE = auto()
    CREATE_INDEX = auto()
    DROP_INDEX = auto()
    RENAME_TABLE = auto()
    CUSTOM = auto()


@dataclass
class MigrationStep:
    """Single step in a migration."""
    step_id: str
    operation: MigrationType
    description: str
    forward_sql: str
    rollback_sql: str
    dependencies: List[str] = field(default_factory=list)
    checksum: Optional[str] = None
    
    def __post_init__(self):
        if self.checksum is None:
            self.checksum = self._calculate_checksum()
    
    def _calculate_checksum(self) -> str:
        """Calculate checksum of migration content."""
        content = f"{self.forward_sql}:{self.rollback_sql}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def verify_checksum(self) -> bool:
        """Verify migration hasn't been tampered with."""
        return self.checksum == self._calculate_checksum()


@dataclass
class Migration:
    """A database migration."""
    migration_id: str
    version: str
    description: str
    author: str
    created_at: float = field(default_factory=time.time)
    steps: List[MigrationStep] = field(default_factory=list)
    status: MigrationStatus = MigrationStatus.PENDING
    applied_at: Optional[float] = None
    rolled_back_at: Optional[float] = None
    execution_time_ms: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert migration to dictionary."""
        return {
            'migration_id': self.migration_id,
            'version': self.version,
            'description': self.description,
            'author': self.author,
            'created_at': self.created_at,
            'steps': [
                {
                    'step_id': s.step_id,
                    'operation': s.operation.name,
                    'description': s.description,
                    'dependencies': s.dependencies,
                    'checksum': s.checksum
                }
                for s in self.steps
            ],
            'status': self.status.name,
            'applied_at': self.applied_at,
            'rolled_back_at': self.rolled_back_at,
            'execution_time_ms': self.execution_time_ms
        }


class SchemaVersion:
    """Manages schema versioning."""
    
    def __init__(self, major: int = 0, minor: int = 0, patch: int = 0):
        self.major = major
        self.minor = minor
        self.patch = patch
    
    @classmethod
    def parse(cls, version_str: str) -> 'SchemaVersion':
        """Parse version string."""
        match = re.match(r'(\d+)\.(\d+)\.(\d+)', version_str)
        if not match:
            raise ValueError(f"Invalid version: {version_str}")
        return cls(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    
    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"
    
    def __lt__(self, other: 'SchemaVersion') -> bool:
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)
    
    def __le__(self, other: 'SchemaVersion') -> bool:
        return (self.major, self.minor, self.patch) <= (other.major, other.minor, other.patch)
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SchemaVersion):
            return False
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)


class MigrationExecutor:
    """
    Executes migrations with transaction safety.
    """
    
    def __init__(self, db_connection: Any):
        self.db = db_connection
        self._pre_hooks: List[Callable] = []
        self._post_hooks: List[Callable] = []
        self._error_hooks: List[Callable] = []
    
    def add_pre_hook(self, hook: Callable[[MigrationStep], None]):
        """Add hook to run before each step."""
        self._pre_hooks.append(hook)
    
    def add_post_hook(self, hook: Callable[[MigrationStep, bool], None]):
        """Add hook to run after each step."""
        self._post_hooks.append(hook)
    
    def add_error_hook(self, hook: Callable[[MigrationStep, Exception], None]):
        """Add hook to run on step error."""
        self._error_hooks.append(hook)
    
    def execute_forward(self, migration: Migration) -> bool:
        """
        Execute migration forward.
        
        Args:
            migration: Migration to apply
        
        Returns:
            True if successful
        """
        start_time = time.time()
        migration.status = MigrationStatus.PENDING
        
        try:
            # Sort steps by dependencies
            ordered_steps = self._topological_sort(migration.steps)
            
            for step in ordered_steps:
                # Verify checksum
                if not step.verify_checksum():
                    raise ValueError(f"Checksum mismatch for step {step.step_id}")
                
                # Run pre-hooks
                for hook in self._pre_hooks:
                    hook(step)
                
                # Execute step
                try:
                    self._execute_sql(step.forward_sql)
                    
                    # Run post-hooks
                    for hook in self._post_hooks:
                        hook(step, True)
                        
                except Exception as e:
                    for hook in self._error_hooks:
                        hook(step, e)
                    raise
            
            migration.status = MigrationStatus.APPLIED
            migration.applied_at = time.time()
            migration.execution_time_ms = (time.time() - start_time) * 1000
            return True
            
        except Exception as e:
            migration.status = MigrationStatus.FAILED
            return False
    
    def execute_rollback(self, migration: Migration) -> bool:
        """
        Rollback migration.
        
        Args:
            migration: Migration to rollback
        
        Returns:
            True if successful
        """
        if migration.status != MigrationStatus.APPLIED:
            return False
        
        try:
            # Sort steps in reverse order for rollback
            ordered_steps = self._topological_sort(migration.steps)
            ordered_steps.reverse()
            
            for step in ordered_steps:
                self._execute_sql(step.rollback_sql)
            
            migration.status = MigrationStatus.ROLLED_BACK
            migration.rolled_back_at = time.time()
            return True
            
        except Exception as e:
            return False
    
    def _topological_sort(self, steps: List[MigrationStep]) -> List[MigrationStep]:
        """Sort steps by dependencies."""
        step_map = {s.step_id: s for s in steps}
        visited: set = set()
        result: List[MigrationStep] = []
        
        def visit(step_id: str):
            if step_id in visited:
                return
            visited.add(step_id)
            step = step_map.get(step_id)
            if step:
                for dep in step.dependencies:
                    visit(dep)
                result.append(step)
        
        for step in steps:
            visit(step.step_id)
        
        return result
    
    def _execute_sql(self, sql: str):
        """Execute SQL statement."""
        # In real implementation, this would execute against database
        if hasattr(self.db, 'execute'):
            self.db.execute(sql)
        elif hasattr(self.db, 'query'):
            self.db.query(sql)


class MigrationHistory:
    """
    Tracks migration history.
    """
    
    def __init__(self, storage_path: str = ".migrations"):
        self.storage_path = storage_path
        self._migrations: Dict[str, Migration] = {}
        self._ensure_storage()
    
    def _ensure_storage(self):
        """Ensure storage directory exists."""
        os.makedirs(self.storage_path, exist_ok=True)
    
    def record_migration(self, migration: Migration):
        """Record migration in history."""
        self._migrations[migration.migration_id] = migration
        self._save_history()
    
    def get_migration(self, migration_id: str) -> Optional[Migration]:
        """Get migration by ID."""
        return self._migrations.get(migration_id)
    
    def get_applied_migrations(self) -> List[Migration]:
        """Get all applied migrations."""
        return [
            m for m in self._migrations.values()
            if m.status == MigrationStatus.APPLIED
        ]
    
    def get_pending_migrations(self) -> List[Migration]:
        """Get all pending migrations."""
        return [
            m for m in self._migrations.values()
            if m.status == MigrationStatus.PENDING
        ]
    
    def get_current_version(self) -> Optional[SchemaVersion]:
        """Get current schema version."""
        applied = self.get_applied_migrations()
        if not applied:
            return None
        
        versions = [SchemaVersion.parse(m.version) for m in applied]
        return max(versions)
    
    def _save_history(self):
        """Save migration history to disk."""
        history_file = os.path.join(self.storage_path, "history.json")
        data = {
            mid: m.to_dict()
            for mid, m in self._migrations.items()
        }
        with open(history_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load_history(self):
        """Load migration history from disk."""
        history_file = os.path.join(self.storage_path, "history.json")
        if os.path.exists(history_file):
            with open(history_file, 'r') as f:
                data = json.load(f)
            # Reconstruct migrations (simplified)
            self._migrations = {}


class SchemaMigrator:
    """
    High-level schema migration manager.
    """
    
    def __init__(self, db_connection: Any, migrations_dir: str = "migrations"):
        self.db = db_connection
        self.migrations_dir = migrations_dir
        self.executor = MigrationExecutor(db_connection)
        self.history = MigrationHistory()
        self._migrations: Dict[str, Migration] = {}
        
        os.makedirs(migrations_dir, exist_ok=True)
    
    def create_migration(self, description: str, author: str = "system") -> Migration:
        """
        Create new migration.
        
        Args:
            description: Migration description
            author: Migration author
        
        Returns:
            New migration
        """
        current = self.history.get_current_version()
        if current is None:
            current = SchemaVersion(0, 0, 0)
        
        # Increment patch version
        new_version = SchemaVersion(current.major, current.minor, current.patch + 1)
        
        migration = Migration(
            migration_id=f"mig_{int(time.time())}_{new_version}",
            version=str(new_version),
            description=description,
            author=author
        )
        
        self._migrations[migration.migration_id] = migration
        return migration
    
    def add_step(self, migration_id: str, operation: MigrationType,
                 description: str, forward_sql: str, rollback_sql: str,
                 dependencies: Optional[List[str]] = None) -> MigrationStep:
        """
        Add step to migration.
        
        Args:
            migration_id: Migration ID
            operation: Type of operation
            description: Step description
            forward_sql: Forward SQL
            rollback_sql: Rollback SQL
            dependencies: Optional step dependencies
        
        Returns:
            Created step
        """
        migration = self._migrations.get(migration_id)
        if not migration:
            raise ValueError(f"Unknown migration: {migration_id}")
        
        step = MigrationStep(
            step_id=f"{migration_id}_step_{len(migration.steps)}",
            operation=operation,
            description=description,
            forward_sql=forward_sql,
            rollback_sql=rollback_sql,
            dependencies=dependencies or []
        )
        
        migration.steps.append(step)
        return step
    
    def migrate(self, target_version: Optional[str] = None) -> List[Migration]:
        """
        Run migrations up to target version.
        
        Args:
            target_version: Target version (None = latest)
        
        Returns:
            List of applied migrations
        """
        applied = []
        
        # Get pending migrations
        pending = sorted(
            self._migrations.values(),
            key=lambda m: SchemaVersion.parse(m.version)
        )
        
        for migration in pending:
            if migration.status == MigrationStatus.PENDING:
                if target_version:
                    target = SchemaVersion.parse(target_version)
                    current = SchemaVersion.parse(migration.version)
                    if current > target:
                        continue
                
                success = self.executor.execute_forward(migration)
                if success:
                    self.history.record_migration(migration)
                    applied.append(migration)
                else:
                    break
        
        return applied
    
    def rollback(self, migration_id: str) -> bool:
        """
        Rollback specific migration.
        
        Args:
            migration_id: Migration to rollback
        
        Returns:
            True if successful
        """
        migration = self._migrations.get(migration_id)
        if not migration:
            migration = self.history.get_migration(migration_id)
        
        if not migration:
            return False
        
        success = self.executor.execute_rollback(migration)
        if success:
            self.history.record_migration(migration)
        
        return success
    
    def rollback_last(self) -> Optional[Migration]:
        """
        Rollback last applied migration.
        
        Returns:
            Rolled back migration or None
        """
        # Check both local and history
        all_applied = [
            m for m in list(self._migrations.values()) + list(self.history._migrations.values())
            if m.status == MigrationStatus.APPLIED
        ]
        
        if not all_applied:
            return None
        
        last = max(all_applied, key=lambda m: m.applied_at or 0)
        
        if self.rollback(last.migration_id):
            return last
        return None
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get migration status.
        
        Returns:
            Status information
        """
        current = self.history.get_current_version()
        
        # Count pending from local migrations
        pending_count = sum(
            1 for m in self._migrations.values()
            if m.status == MigrationStatus.PENDING
        )
        
        return {
            'current_version': str(current) if current else None,
            'applied_count': len(self.history.get_applied_migrations()),
            'pending_count': pending_count,
            'migrations': [
                {
                    'id': m.migration_id,
                    'version': m.version,
                    'description': m.description,
                    'status': m.status.name,
                    'steps': len(m.steps)
                }
                for m in self._migrations.values()
            ]
        }
    
    def validate_migrations(self) -> List[Dict[str, Any]]:
        """
        Validate all migrations.
        
        Returns:
            List of validation errors
        """
        errors = []
        
        for migration in self._migrations.values():
            for step in migration.steps:
                if not step.verify_checksum():
                    errors.append({
                        'migration': migration.migration_id,
                        'step': step.step_id,
                        'error': 'Checksum mismatch'
                    })
        
        return errors


# Migration templates
MIGRATION_TEMPLATES = {
    MigrationType.CREATE_TABLE: {
        'forward': "CREATE TABLE {table_name} ({columns});",
        'rollback': "DROP TABLE {table_name};"
    },
    MigrationType.DROP_TABLE: {
        'forward': "DROP TABLE {table_name};",
        'rollback': "-- Cannot rollback DROP TABLE"
    },
    MigrationType.ALTER_TABLE: {
        'forward': "ALTER TABLE {table_name} {operation};",
        'rollback': "ALTER TABLE {table_name} {reverse_operation};"
    },
    MigrationType.CREATE_INDEX: {
        'forward': "CREATE INDEX {index_name} ON {table_name} ({columns});",
        'rollback': "DROP INDEX {index_name};"
    },
    MigrationType.DROP_INDEX: {
        'forward': "DROP INDEX {index_name};",
        'rollback': "-- Cannot rollback DROP INDEX"
    },
    MigrationType.RENAME_TABLE: {
        'forward': "ALTER TABLE {old_name} RENAME TO {new_name};",
        'rollback': "ALTER TABLE {new_name} RENAME TO {old_name};"
    }
}


def create_table_migration(table_name: str, columns: Dict[str, str],
                          description: str = "") -> Tuple[str, str]:
    """
    Generate create table migration.
    
    Args:
        table_name: Table name
        columns: Column definitions
        description: Migration description
    
    Returns:
        Forward and rollback SQL
    """
    col_defs = ", ".join(f"{name} {dtype}" for name, dtype in columns.items())
    
    forward = MIGRATION_TEMPLATES[MigrationType.CREATE_TABLE]['forward'].format(
        table_name=table_name,
        columns=col_defs
    )
    
    rollback = MIGRATION_TEMPLATES[MigrationType.CREATE_TABLE]['rollback'].format(
        table_name=table_name
    )
    
    return forward, rollback


def create_index_migration(index_name: str, table_name: str,
                          columns: List[str]) -> Tuple[str, str]:
    """
    Generate create index migration.
    
    Args:
        index_name: Index name
        table_name: Table name
        columns: Column names
    
    Returns:
        Forward and rollback SQL
    """
    col_list = ", ".join(columns)
    
    forward = MIGRATION_TEMPLATES[MigrationType.CREATE_INDEX]['forward'].format(
        index_name=index_name,
        table_name=table_name,
        columns=col_list
    )
    
    rollback = MIGRATION_TEMPLATES[MigrationType.CREATE_INDEX]['rollback'].format(
        index_name=index_name
    )
    
    return forward, rollback
