"""
Persistent Session Recovery System for KosDB

Provides session state persistence to disk with automatic recovery
on restart, state serialization, integrity checking, and graceful
degradation if recovery fails.
"""

import json
import os
import time
import hashlib
import threading
import pickle
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta


class SessionRecoveryError(Exception):
    """Raised when session recovery fails."""
    pass


class IntegrityError(Exception):
    """Raised when session data integrity check fails."""
    pass


@dataclass
class SessionState:
    """Represents a session's state."""
    session_id: str
    username: str
    current_db: Optional[str]
    is_admin: bool
    privileges: Dict[str, Any]
    created_at: float
    last_activity: float
    client_address: Optional[str]
    custom_state: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'session_id': self.session_id,
            'username': self.username,
            'current_db': self.current_db,
            'is_admin': self.is_admin,
            'privileges': self.privileges,
            'created_at': self.created_at,
            'last_activity': self.last_activity,
            'client_address': self.client_address,
            'custom_state': self.custom_state,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionState':
        """Create from dictionary."""
        return cls(
            session_id=data['session_id'],
            username=data['username'],
            current_db=data.get('current_db'),
            is_admin=data.get('is_admin', False),
            privileges=data.get('privileges', {}),
            created_at=data['created_at'],
            last_activity=data['last_activity'],
            client_address=data.get('client_address'),
            custom_state=data.get('custom_state', {})
        )
    
    def is_expired(self, timeout_seconds: float = 1800) -> bool:
        """Check if session has expired (default: 30 minutes)."""
        return time.time() - self.last_activity > timeout_seconds
    
    def touch(self):
        """Update last activity timestamp."""
        self.last_activity = time.time()


class SessionSerializer:
    """
    Handles serialization and deserialization of session data.
    Supports multiple formats: JSON (default), Pickle (for complex objects).
    """
    
    def __init__(self, format: str = 'json'):
        self.format = format.lower()
        if self.format not in ('json', 'pickle'):
            raise ValueError(f"Unsupported format: {format}")
    
    def serialize(self, data: Any) -> bytes:
        """Serialize data to bytes."""
        if self.format == 'json':
            return json.dumps(data, indent=2).encode('utf-8')
        else:  # pickle
            return pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)
    
    def deserialize(self, data: bytes) -> Any:
        """Deserialize bytes to data."""
        if self.format == 'json':
            return json.loads(data.decode('utf-8'))
        else:  # pickle
            return pickle.loads(data)


class IntegrityChecker:
    """
    Provides integrity checking for session data using checksums.
    """
    
    @staticmethod
    def compute_checksum(data: bytes) -> str:
        """Compute SHA-256 checksum of data."""
        return hashlib.sha256(data).hexdigest()
    
    @staticmethod
    def verify_checksum(data: bytes, expected_checksum: str) -> bool:
        """Verify data against expected checksum."""
        actual = IntegrityChecker.compute_checksum(data)
        return actual == expected_checksum
    
    @staticmethod
    def compute_checksum_dict(data: Dict[str, Any]) -> str:
        """Compute checksum from dictionary."""
        # Sort keys for consistent hashing
        canonical = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


class SessionPersistence:
    """
    Handles persistence of sessions to disk.
    Supports atomic writes and automatic backup creation.
    """
    
    def __init__(self, data_dir: str = './sessions',
                 serializer: Optional[SessionSerializer] = None,
                 max_backups: int = 5):
        self.data_dir = data_dir
        self.serializer = serializer or SessionSerializer('json')
        self.max_backups = max_backups
        
        # Ensure directory exists
        os.makedirs(data_dir, exist_ok=True)
        
        self._lock = threading.RLock()
        self._write_queue: List[SessionState] = []
        self._shutdown = False
        self._flush_thread: Optional[threading.Thread] = None
    
    def start(self):
        """Start background flush thread."""
        self._flush_thread = threading.Thread(target=self._flush_loop)
        self._flush_thread.daemon = True
        self._flush_thread.start()
    
    def stop(self):
        """Stop background flush thread and flush remaining data."""
        self._shutdown = True
        if self._flush_thread:
            self._flush_thread.join(timeout=5.0)
        
        # Final flush
        self._flush_all()
    
    def _flush_loop(self):
        """Background thread for periodic flushing."""
        while not self._shutdown:
            time.sleep(5.0)  # Flush every 5 seconds
            self._flush_all()
    
    def _flush_all(self):
        """Flush all queued sessions to disk."""
        with self._lock:
            queue = self._write_queue.copy()
            self._write_queue.clear()
        
        for session in queue:
            self._write_session_sync(session)
    
    def _get_session_path(self, session_id: str) -> str:
        """Get file path for session."""
        # Use first 2 chars as subdirectory for distribution
        subdir = session_id[:2] if len(session_id) >= 2 else 'xx'
        dir_path = os.path.join(self.data_dir, subdir)
        os.makedirs(dir_path, exist_ok=True)
        return os.path.join(dir_path, f"{session_id}.session")
    
    def _write_session_sync(self, session: SessionState) -> bool:
        """Write session to disk synchronously."""
        try:
            file_path = self._get_session_path(session.session_id)
            temp_path = file_path + '.tmp'
            
            # Serialize session
            data = self.serializer.serialize(session.to_dict())
            
            # Compute checksum
            checksum = IntegrityChecker.compute_checksum(data)
            
            # Write with checksum
            envelope = {
                'version': '1.0',
                'checksum': checksum,
                'timestamp': time.time(),
                'data': session.to_dict() if self.serializer.format == 'json' else None,
                'format': self.serializer.format
            }
            
            if self.serializer.format == 'pickle':
                # For pickle, store data separately
                envelope['data'] = data.hex() if isinstance(data, bytes) else data
            
            # Write to temp file
            with open(temp_path, 'wb') as f:
                if self.serializer.format == 'json':
                    f.write(json.dumps(envelope).encode('utf-8'))
                else:
                    f.write(self.serializer.serialize(envelope))
            
            # Atomic rename
            os.replace(temp_path, file_path)
            
            # Create backup
            self._create_backup(file_path)
            
            return True
            
        except Exception as e:
            print(f"[SESSION] Failed to persist session {session.session_id}: {e}")
            return False
    
    def _create_backup(self, file_path: str):
        """Create backup copy of session file."""
        backup_dir = os.path.join(self.data_dir, '.backups')
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = os.path.basename(file_path)
        backup_path = os.path.join(backup_dir, f"{filename}.{timestamp}")
        
        try:
            import shutil
            shutil.copy2(file_path, backup_path)
            
            # Clean old backups
            self._cleanup_old_backups(filename)
        except Exception:
            pass  # Backup failure shouldn't block main operation
    
    def _cleanup_old_backups(self, filename: str):
        """Remove old backups keeping only max_backups."""
        backup_dir = os.path.join(self.data_dir, '.backups')
        
        try:
            backups = sorted([
                f for f in os.listdir(backup_dir)
                if f.startswith(filename + '.')
            ])
            
            while len(backups) > self.max_backups:
                old_backup = os.path.join(backup_dir, backups.pop(0))
                os.remove(old_backup)
        except Exception:
            pass
    
    def queue_session_write(self, session: SessionState):
        """Queue session for writing to disk."""
        with self._lock:
            # Remove existing entry for this session
            self._write_queue = [
                s for s in self._write_queue
                if s.session_id != session.session_id
            ]
            self._write_queue.append(session)
    
    def load_session(self, session_id: str) -> Optional[SessionState]:
        """Load session from disk."""
        file_path = self._get_session_path(session_id)
        
        if not os.path.exists(file_path):
            return None
        
        try:
            with open(file_path, 'rb') as f:
                data = f.read()
            
            # Parse envelope
            if self.serializer.format == 'json':
                envelope = json.loads(data.decode('utf-8'))
            else:
                envelope = self.serializer.deserialize(data)
            
            # Verify checksum
            if 'checksum' in envelope:
                session_data = envelope['data']
                canonical = json.dumps(session_data, sort_keys=True, separators=(',', ':'))
                if not IntegrityChecker.verify_checksum(
                    canonical.encode('utf-8'), envelope['checksum']
                ):
                    raise IntegrityError(f"Session {session_id} checksum mismatch")
            
            # Reconstruct session
            session = SessionState.from_dict(envelope['data'])
            return session
            
        except IntegrityError:
            raise
        except Exception as e:
            print(f"[SESSION] Failed to load session {session_id}: {e}")
            return None
    
    def delete_session(self, session_id: str) -> bool:
        """Delete session from disk."""
        file_path = self._get_session_path(session_id)
        
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            return True
        except Exception as e:
            print(f"[SESSION] Failed to delete session {session_id}: {e}")
            return False
    
    def list_sessions(self) -> List[str]:
        """List all persisted session IDs."""
        sessions = []
        
        try:
            for subdir in os.listdir(self.data_dir):
                subdir_path = os.path.join(self.data_dir, subdir)
                if os.path.isdir(subdir_path) and not subdir.startswith('.'):
                    for filename in os.listdir(subdir_path):
                        if filename.endswith('.session'):
                            session_id = filename[:-8]  # Remove .session
                            sessions.append(session_id)
        except Exception:
            pass
        
        return sessions
    
    def get_stats(self) -> Dict[str, Any]:
        """Get persistence statistics."""
        return {
            'total_sessions': len(self.list_sessions()),
            'queued_writes': len(self._write_queue),
            'data_dir': self.data_dir,
            'format': self.serializer.format
        }


class SessionRecoveryManager:
    """
    Main interface for session recovery.
    Integrates with authentication and provides automatic recovery.
    """
    
    def __init__(self, persistence: Optional[SessionPersistence] = None,
                 data_dir: str = './sessions',
                 session_timeout: float = 1800,  # 30 minutes
                 recovery_enabled: bool = True):
        self.persistence = persistence or SessionPersistence(data_dir)
        self.session_timeout = session_timeout
        self.recovery_enabled = recovery_enabled
        
        self._active_sessions: Dict[str, SessionState] = {}
        self._lock = threading.RLock()
        self._cleanup_thread: Optional[threading.Thread] = None
        self._shutdown = False
    
    def start(self):
        """Start session recovery manager."""
        self.persistence.start()
        
        if self.recovery_enabled:
            self._recover_sessions()
        
        # Start cleanup thread
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop)
        self._cleanup_thread.daemon = True
        self._cleanup_thread.start()
    
    def stop(self):
        """Stop session recovery manager."""
        self._shutdown = True
        
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5.0)
        
        # Persist all active sessions
        self._persist_all()
        
        self.persistence.stop()
    
    def _recover_sessions(self):
        """Recover sessions from disk."""
        print("[SESSION] Recovering sessions from disk...")
        
        recovered = 0
        expired = 0
        failed = 0
        
        for session_id in self.persistence.list_sessions():
            try:
                session = self.persistence.load_session(session_id)
                
                if session is None:
                    failed += 1
                    continue
                
                # Check if expired
                if session.is_expired(self.session_timeout):
                    self.persistence.delete_session(session_id)
                    expired += 1
                    continue
                
                # Restore to active sessions
                with self._lock:
                    self._active_sessions[session_id] = session
                
                recovered += 1
                print(f"[SESSION] Recovered session for {session.username}")
                
            except IntegrityError as e:
                print(f"[SESSION] Integrity check failed for {session_id}: {e}")
                # Try to restore from backup
                if self._recover_from_backup(session_id):
                    recovered += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"[SESSION] Failed to recover {session_id}: {e}")
                failed += 1
        
        print(f"[SESSION] Recovery complete: {recovered} recovered, "
              f"{expired} expired, {failed} failed")
    
    def _recover_from_backup(self, session_id: str) -> bool:
        """Attempt to recover from backup file."""
        backup_dir = os.path.join(self.persistence.data_dir, '.backups')
        
        try:
            # Find backups for this session
            backups = sorted([
                f for f in os.listdir(backup_dir)
                if f.startswith(session_id + '.')
            ], reverse=True)
            
            for backup_file in backups:
                try:
                    backup_path = os.path.join(backup_dir, backup_file)
                    with open(backup_path, 'rb') as f:
                        data = f.read()
                    
                    # Try to parse without strict checksum
                    envelope = json.loads(data.decode('utf-8'))
                    session = SessionState.from_dict(envelope['data'])
                    
                    with self._lock:
                        self._active_sessions[session_id] = session
                    
                    print(f"[SESSION] Recovered {session_id} from backup")
                    return True
                    
                except Exception:
                    continue
            
            return False
            
        except Exception:
            return False
    
    def _cleanup_loop(self):
        """Background thread for session cleanup."""
        while not self._shutdown:
            time.sleep(60.0)  # Check every minute
            self._cleanup_expired()
    
    def _cleanup_expired(self):
        """Remove expired sessions."""
        expired_sessions = []
        
        with self._lock:
            for session_id, session in self._active_sessions.items():
                if session.is_expired(self.session_timeout):
                    expired_sessions.append(session_id)
            
            for session_id in expired_sessions:
                del self._active_sessions[session_id]
        
        # Also delete from disk
        for session_id in expired_sessions:
            self.persistence.delete_session(session_id)
            print(f"[SESSION] Cleaned up expired session {session_id}")
    
    def _persist_all(self):
        """Persist all active sessions."""
        with self._lock:
            sessions = list(self._active_sessions.values())
        
        for session in sessions:
            self.persistence.queue_session_write(session)
        
        # Force immediate flush
        self.persistence._flush_all()
    
    def create_session(self, session_id: str, username: str,
                       is_admin: bool = False,
                       privileges: Optional[Dict] = None,
                       client_address: Optional[str] = None) -> SessionState:
        """Create new session."""
        now = time.time()
        
        session = SessionState(
            session_id=session_id,
            username=username,
            current_db=None,
            is_admin=is_admin,
            privileges=privileges or {},
            created_at=now,
            last_activity=now,
            client_address=client_address,
            custom_state={}
        )
        
        with self._lock:
            self._active_sessions[session_id] = session
        
        # Persist immediately
        self.persistence.queue_session_write(session)
        
        return session
    
    def get_session(self, session_id: str) -> Optional[SessionState]:
        """Get session by ID."""
        with self._lock:
            session = self._active_sessions.get(session_id)
            
            if session:
                # Update activity
                session.touch()
                # Queue for persistence
                self.persistence.queue_session_write(session)
            
            return session
    
    def update_session(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """Update session state."""
        with self._lock:
            session = self._active_sessions.get(session_id)
            
            if not session:
                return False
            
            # Update fields
            if 'current_db' in updates:
                session.current_db = updates['current_db']
            if 'custom_state' in updates:
                session.custom_state.update(updates['custom_state'])
            
            session.touch()
        
        # Persist
        self.persistence.queue_session_write(session)
        return True
    
    def end_session(self, session_id: str) -> bool:
        """End and remove session."""
        with self._lock:
            if session_id in self._active_sessions:
                del self._active_sessions[session_id]
        
        # Delete from disk
        return self.persistence.delete_session(session_id)
    
    def list_active_sessions(self) -> List[SessionState]:
        """List all active sessions."""
        with self._lock:
            return list(self._active_sessions.values())
    
    def get_session_count(self) -> int:
        """Get number of active sessions."""
        with self._lock:
            return len(self._active_sessions)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get recovery manager statistics."""
        return {
            'active_sessions': self.get_session_count(),
            'persisted_sessions': len(self.persistence.list_sessions()),
            'session_timeout': self.session_timeout,
            'recovery_enabled': self.recovery_enabled,
            'persistence_stats': self.persistence.get_stats()
        }


# Integration with existing Authenticator
class PersistentAuthenticator:
    """
    Drop-in replacement for Authenticator with session persistence.
    """
    
    def __init__(self, db, session_recovery: Optional[SessionRecoveryManager] = None,
                 data_dir: str = './sessions'):
        self.db = db
        self.session_recovery = session_recovery or SessionRecoveryManager(
            data_dir=data_dir
        )
        self._original_sessions: Dict[str, Any] = {}  # For compatibility
    
    def start(self):
        """Start persistent session management."""
        self.session_recovery.start()
    
    def stop(self):
        """Stop persistent session management."""
        self.session_recovery.stop()
    
    def authenticate(self, username: str, password: str) -> tuple:
        """
        Authenticate user and create persistent session.
        
        Returns: (success, session_token, user_info)
        """
        # Use existing database authentication
        success, is_admin, privileges = self.db.authenticate_user(username, password)
        
        if not success:
            return False, None, None
        
        # Create session token
        import secrets
        token = secrets.token_hex(16)
        
        # Create persistent session
        session = self.session_recovery.create_session(
            session_id=token,
            username=username,
            is_admin=is_admin,
            privileges=privileges
        )
        
        user_info = {
            'username': username,
            'is_admin': is_admin,
            'privileges': privileges
        }
        
        return True, token, user_info
    
    def validate_session(self, token: str) -> bool:
        """Check if session token is valid."""
        session = self.session_recovery.get_session(token)
        return session is not None
    
    def get_user_info(self, token: str) -> Optional[Dict[str, Any]]:
        """Get user info from session token."""
        session = self.session_recovery.get_session(token)
        
        if not session:
            return None
        
        return {
            'username': session.username,
            'is_admin': session.is_admin,
            'privileges': session.privileges
        }
    
    def end_session(self, token: str):
        """End a session."""
        self.session_recovery.end_session(token)
    
    def check_privilege(self, token: str, db_name: str, table_name: str,
                       required_priv: str) -> bool:
        """Check if user has required privilege."""
        session = self.session_recovery.get_session(token)
        
        if not session:
            return False
        
        # Admins have all privileges
        if session.is_admin:
            return True
        
        # Check database privileges
        return self.db.check_privilege(
            session.username, db_name, table_name, required_priv
        )
    
    def set_current_db(self, token: str, db_name: str):
        """Set current database for session."""
        self.session_recovery.update_session(token, {'current_db': db_name})
    
    def get_current_db(self, token: str) -> Optional[str]:
        """Get current database for session."""
        session = self.session_recovery.get_session(token)
        return session.current_db if session else None


# Convenience functions
def create_session_recovery(data_dir: str = './sessions',
                            session_timeout: float = 1800) -> SessionRecoveryManager:
    """
    Create and configure session recovery manager.
    
    Args:
        data_dir: Directory for session persistence
        session_timeout: Session timeout in seconds (default: 30 min)
    
    Returns:
        Configured SessionRecoveryManager instance
    """
    persistence = SessionPersistence(data_dir)
    manager = SessionRecoveryManager(
        persistence=persistence,
        session_timeout=session_timeout,
        recovery_enabled=True
    )
    return manager


def migrate_to_persistent_auth(authenticator, data_dir: str = './sessions') -> PersistentAuthenticator:
    """
    Migrate existing Authenticator to use persistent sessions.
    
    Args:
        authenticator: Existing Authenticator instance
        data_dir: Directory for session persistence
    
    Returns:
        PersistentAuthenticator instance
    """
    return PersistentAuthenticator(
        db=authenticator.db,
        data_dir=data_dir
    )
