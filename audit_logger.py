"""
Audit Logging System for KosDB

Provides comprehensive audit logging for all database operations with
multiple output targets, log rotation, and filtering capabilities.
"""

import os
import json
import time
import logging
import threading
import socket
import hashlib
import gzip
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable, Set, Union
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from pathlib import Path
import queue

# Try to import syslog
try:
    import syslog
    SYSLOG_AVAILABLE = True
except ImportError:
    SYSLOG_AVAILABLE = False

# Try to import requests for webhook
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# Configure logging
logger = logging.getLogger(__name__)


class AuditLevel(Enum):
    """Audit log levels."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AuditAction(Enum):
    """Types of audit actions."""
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    DATA_READ = "data_read"
    DATA_WRITE = "data_write"
    DATA_DELETE = "data_delete"
    SCHEMA_CHANGE = "schema_change"
    CONFIG_CHANGE = "config_change"
    ADMIN = "admin"


@dataclass
class AuditEntry:
    """Single audit log entry."""
    timestamp: str
    event_id: str
    user: str
    client_ip: str
    action: str
    command: str
    command_type: str
    affected_tables: List[str]
    success: bool
    execution_time_ms: float
    error_message: Optional[str] = None
    session_id: Optional[str] = None
    database: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
class AuditFilter:
    """Filter for audit entries."""
    
    # Sensitive commands that should be excluded or masked
    SENSITIVE_COMMANDS = {'PASS', 'PASSWORD', 'SECRET', 'KEY', 'TOKEN'}
    
    # Commands to completely exclude from audit
    EXCLUDED_COMMANDS = {'PING', 'ECHO'}
    
    def __init__(
        self,
        exclude_commands: Optional[Set[str]] = None,
        exclude_users: Optional[Set[str]] = None,
        exclude_actions: Optional[Set[str]] = None,
        mask_commands: Optional[Set[str]] = None,
        min_level: AuditLevel = AuditLevel.DEBUG
    ):
        """
        Initialize audit filter.
        
        Args:
            exclude_commands: Commands to exclude from logging
            exclude_users: Users to exclude from logging
            exclude_actions: Actions to exclude from logging
            mask_commands: Commands to mask (hide arguments)
            min_level: Minimum audit level to log
        """
        self.exclude_commands = (exclude_commands or set()) | self.EXCLUDED_COMMANDS
        self.exclude_users = exclude_users or set()
        self.exclude_actions = exclude_actions or set()
        self.mask_commands = mask_commands or self.SENSITIVE_COMMANDS
        self.min_level = min_level
    # Commands to completely exclude from audit
    EXCLUDED_COMMANDS = {'PING', 'ECHO'}
    
    def __init__(
        self,
        exclude_commands: Optional[Set[str]] = None,
        exclude_users: Optional[Set[str]] = None,
        exclude_actions: Optional[Set[str]] = None,
        mask_commands: Optional[Set[str]] = None,
        min_level: AuditLevel = AuditLevel.DEBUG
    ):
        """
        Initialize audit filter.
        
        Args:
            exclude_commands: Commands to exclude from logging
            exclude_users: Users to exclude from logging
            exclude_actions: Actions to exclude from logging
            mask_commands: Commands to mask (hide arguments)
            min_level: Minimum audit level to log
        """
        self.exclude_commands = exclude_commands or self.EXCLUDED_COMMANDS
        self.exclude_users = exclude_users or set()
        self.exclude_actions = exclude_actions or set()
        self.mask_commands = mask_commands or self.SENSITIVE_COMMANDS
        self.min_level = min_level
    
    def should_log(self, entry: AuditEntry) -> bool:
        """
        Check if entry should be logged.
        
        Args:
            entry: Audit entry to check
        
        Returns:
            True if should be logged
        """
        # Check excluded commands
        cmd_upper = entry.command.upper()
        if any(cmd in cmd_upper for cmd in self.exclude_commands):
            return False
        
        # Check excluded users
        if entry.user in self.exclude_users:
            return False
        
        # Check excluded actions
        if entry.action in self.exclude_actions:
            return False
        
        return True
    
    def mask_sensitive(self, entry: AuditEntry) -> AuditEntry:
        """
        Mask sensitive information in entry.
        
        Args:
            entry: Audit entry to mask
        
        Returns:
            Masked entry
        """
        cmd_upper = entry.command.upper()
        
        # Check if command should be masked
        if any(cmd in cmd_upper for cmd in self.mask_commands):
            # Create copy with masked command
            masked_entry = AuditEntry(
                timestamp=entry.timestamp,
                event_id=entry.event_id,
                user=entry.user,
                client_ip=entry.client_ip,
                action=entry.action,
                command="[MASKED]",
                command_type=entry.command_type,
                affected_tables=entry.affected_tables,
                success=entry.success,
                execution_time_ms=entry.execution_time_ms,
                error_message=entry.error_message,
                session_id=entry.session_id,
                database=entry.database,
                metadata=entry.metadata
            )
            return masked_entry
        
        return entry


class AuditOutputHandler:
    """Base class for audit output handlers."""
    
    def write(self, entry: AuditEntry):
        """Write audit entry."""
        raise NotImplementedError
    
    def close(self):
        """Close handler."""
        pass
    
    def flush(self):
        """Flush buffered data."""
        pass


class FileAuditHandler(AuditOutputHandler):
    """
    File-based audit handler with rotation support.
    """
    
    def __init__(
        self,
        log_dir: str = "./audit_logs",
        filename_pattern: str = "audit_{date}.jsonl",
        max_size_mb: float = 100,
        max_age_days: int = 30,
        compress: bool = True,
        buffer_size: int = 100
    ):
        """
        Initialize file audit handler.
        
        Args:
            log_dir: Directory for log files
            filename_pattern: Pattern for log filenames
            max_size_mb: Maximum file size before rotation
            max_age_days: Maximum age of log files
            compress: Whether to compress old logs
            buffer_size: Number of entries to buffer before writing
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.filename_pattern = filename_pattern
        self.max_size = max_size_mb * 1024 * 1024
        self.max_age_days = max_age_days
        self.compress = compress
        
        self._current_file: Optional[Path] = None
        self._current_size = 0
        self._buffer: List[AuditEntry] = []
        self._buffer_size = buffer_size
        self._lock = threading.RLock()
        
        self._open_current_file()
    
    def _get_filename(self) -> str:
        """Generate filename for current date."""
        date_str = datetime.now().strftime("%Y%m%d")
        return self.filename_pattern.format(date=date_str)
    
    def _open_current_file(self):
        """Open or create current log file."""
        filename = self._get_filename()
        self._current_file = self.log_dir / filename
        
        # Check if file exists and get size
        if self._current_file.exists():
            self._current_size = self._current_file.stat().st_size
        else:
            self._current_size = 0
        
        logger.info(f"[Audit] Logging to {self._current_file}")
    
    def _rotate_if_needed(self):
        """Rotate log file if size exceeded."""
        if self._current_size >= self.max_size:
            # Close current file
            self._flush_buffer()
            
            # Rotate
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            rotated_name = f"{self._current_file.stem}_{timestamp}.jsonl"
            rotated_path = self.log_dir / rotated_name
            
            try:
                self._current_file.rename(rotated_path)
                
                # Compress if enabled
                if self.compress:
                    self._compress_file(rotated_path)
                
                # Open new file
                self._open_current_file()
                
            except Exception as e:
                logger.error(f"[Audit] Rotation failed: {e}")
    
    def _compress_file(self, filepath: Path):
        """Compress a log file."""
        try:
            compressed_path = filepath.with_suffix('.jsonl.gz')
            with open(filepath, 'rb') as f_in:
                with gzip.open(compressed_path, 'wb') as f_out:
                    f_out.writelines(f_in)
            
            # Remove original
            filepath.unlink()
            logger.info(f"[Audit] Compressed {filepath.name}")
            
        except Exception as e:
            logger.error(f"[Audit] Compression failed: {e}")
    
    def _cleanup_old_logs(self):
        """Remove or compress old log files."""
        cutoff = datetime.now() - timedelta(days=self.max_age_days)
        
        for file_path in self.log_dir.iterdir():
            if file_path.is_file():
                try:
                    mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if mtime < cutoff:
                        file_path.unlink()
                        logger.info(f"[Audit] Removed old log: {file_path.name}")
                except Exception as e:
                    logger.error(f"[Audit] Cleanup failed for {file_path}: {e}")
    
    def _flush_buffer(self):
        """Write buffered entries to file."""
        if not self._buffer:
            return
        
        with self._lock:
            try:
                with open(self._current_file, 'a') as f:
                    for entry in self._buffer:
                        f.write(entry.to_json() + '\n')
                
                self._current_size = self._current_file.stat().st_size
                self._buffer.clear()
                
                # Check rotation
                self._rotate_if_needed()
                
            except Exception as e:
                logger.error(f"[Audit] Write failed: {e}")
    
    def write(self, entry: AuditEntry):
        """Write audit entry."""
        self._buffer.append(entry)
        
        # Flush if buffer full
        if len(self._buffer) >= self._buffer_size:
            self._flush_buffer()
    
    def flush(self):
        """Flush buffered entries."""
        self._flush_buffer()
    
    def close(self):
        """Close handler."""
        self._flush_buffer()
        self._cleanup_old_logs()


class SyslogAuditHandler(AuditOutputHandler):
    """
    Syslog-based audit handler.
    """
    
    def __init__(
        self,
        facility: int = syslog.LOG_LOCAL0 if SYSLOG_AVAILABLE else 0,
        priority: int = syslog.LOG_INFO if SYSLOG_AVAILABLE else 0,
        tag: str = "kosdb-audit"
    ):
        """
        Initialize syslog handler.
        
        Args:
            facility: Syslog facility
            priority: Default priority
            tag: Syslog tag
        """
        if not SYSLOG_AVAILABLE:
            raise ImportError("syslog module not available")
        
        self.facility = facility
        self.priority = priority
        self.tag = tag
        
        # Open syslog
        syslog.openlog(tag, syslog.LOG_PID, facility)
        
        logger.info("[Audit] Syslog handler initialized")
    
    def write(self, entry: AuditEntry):
        """Write to syslog."""
        try:
            message = f"{entry.event_id} {entry.user}@{entry.client_ip} {entry.command} success={entry.success}"
            syslog.syslog(self.priority, message)
        except Exception as e:
            logger.error(f"[Audit] Syslog write failed: {e}")
    
    def close(self):
        """Close syslog."""
        syslog.closelog()


class WebhookAuditHandler(AuditOutputHandler):
    """
    HTTP webhook audit handler.
    """
    
    def __init__(
        self,
        webhook_url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 5.0,
        retry_count: int = 3,
        batch_size: int = 10
    ):
        """
        Initialize webhook handler.
        
        Args:
            webhook_url: URL to POST audit entries
            headers: Additional headers
            timeout: Request timeout
            retry_count: Number of retries on failure
            batch_size: Number of entries to batch
        """
        if not REQUESTS_AVAILABLE:
            raise ImportError("requests module not available")
        
        self.webhook_url = webhook_url
        self.headers = headers or {}
        self.timeout = timeout
        self.retry_count = retry_count
        self.batch_size = batch_size
        
        self._buffer: List[AuditEntry] = []
        self._lock = threading.RLock()
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False
        
        self._start_worker()
        
        logger.info(f"[Audit] Webhook handler initialized: {webhook_url}")
    
    def _start_worker(self):
        """Start background worker thread."""
        self._running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()
    
    def _worker_loop(self):
        """Background worker for sending webhooks."""
        while self._running:
            time.sleep(1)  # Send every second
            
            entries = []
            with self._lock:
                if self._buffer:
                    entries = self._buffer[:self.batch_size]
                    self._buffer = self._buffer[self.batch_size:]
            
            if entries:
                self._send_batch(entries)
    
    def _send_batch(self, entries: List[AuditEntry]):
        """Send batch of entries to webhook."""
        payload = {
            'timestamp': datetime.now().isoformat(),
            'entries': [e.to_dict() for e in entries]
        }
        
        for attempt in range(self.retry_count):
            try:
                response = requests.post(
                    self.webhook_url,
                    json=payload,
                    headers=self.headers,
                    timeout=self.timeout
                )
                response.raise_for_status()
                logger.debug(f"[Audit] Webhook sent {len(entries)} entries")
                return
                
            except Exception as e:
                logger.warning(f"[Audit] Webhook attempt {attempt + 1} failed: {e}")
                time.sleep(2 ** attempt)  # Exponential backoff
        
        logger.error(f"[Audit] Webhook failed after {self.retry_count} attempts")
    
    def write(self, entry: AuditEntry):
        """Add entry to webhook buffer."""
        with self._lock:
            self._buffer.append(entry)
    
    def flush(self):
        """Force send all buffered entries."""
        with self._lock:
            entries = self._buffer.copy()
            self._buffer.clear()
        
        if entries:
            self._send_batch(entries)
    
    def close(self):
        """Close handler."""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5.0)
        self.flush()


class AuditLogger:
    """
    Main audit logger that manages multiple output handlers.
    """
    
    def __init__(
        self,
        filter_config: Optional[AuditFilter] = None,
        async_mode: bool = True,
        queue_size: int = 10000
    ):
        """
        Initialize audit logger.
        
        Args:
            filter_config: Audit filter configuration
            async_mode: Whether to log asynchronously
            queue_size: Size of async queue
        """
        self.filter = filter_config or AuditFilter()
        self.handlers: List[AuditOutputHandler] = []
        self.async_mode = async_mode
        
        self._queue: Optional[queue.Queue] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False
        
        if async_mode:
            self._queue = queue.Queue(maxsize=queue_size)
            self._start_worker()
        
        logger.info("[Audit] Logger initialized")
    
    def add_handler(self, handler: AuditOutputHandler):
        """Add output handler."""
        self.handlers.append(handler)
        logger.info(f"[Audit] Added handler: {type(handler).__name__}")
    
    def remove_handler(self, handler: AuditOutputHandler):
        """Remove output handler."""
        if handler in self.handlers:
            self.handlers.remove(handler)
            handler.close()
    
    def _start_worker(self):
        """Start async worker thread."""
        self._running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()
    
    def _worker_loop(self):
        """Async worker loop."""
        while self._running:
            try:
                entry = self._queue.get(timeout=1.0)
                self._write_to_handlers(entry)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"[Audit] Worker error: {e}")
    
    def _write_to_handlers(self, entry: AuditEntry):
        """Write entry to all handlers."""
        for handler in self.handlers:
            try:
                handler.write(entry)
            except Exception as e:
                logger.error(f"[Audit] Handler error: {e}")
    
    def log(
        self,
        user: str,
        client_ip: str,
        command: str,
        command_type: str = "UNKNOWN",
        affected_tables: Optional[List[str]] = None,
        success: bool = True,
        execution_time_ms: float = 0.0,
        error_message: Optional[str] = None,
        session_id: Optional[str] = None,
        database: Optional[str] = None,
        action: str = "UNKNOWN",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[AuditEntry]:
        """
        Log an audit entry.
        
        Args:
            user: Username
            client_ip: Client IP address
            command: Command executed
            command_type: Type of command
            affected_tables: Tables affected
            success: Whether command succeeded
            execution_time_ms: Execution time in milliseconds
            error_message: Error message if failed
            session_id: Session ID
            database: Current database
            action: Action type
            metadata: Additional metadata
        
        Returns:
            Created audit entry or None if filtered
        """
        # Generate event ID
        event_data = f"{time.time()}{user}{command}"
        event_id = hashlib.sha256(event_data.encode()).hexdigest()[:16]
        
        entry = AuditEntry(
            timestamp=datetime.now().isoformat(),
            event_id=event_id,
            user=user,
            client_ip=client_ip,
            action=action,
            command=command,
            command_type=command_type,
            affected_tables=affected_tables or [],
            success=success,
            execution_time_ms=execution_time_ms,
            error_message=error_message,
            session_id=session_id,
            database=database,
            metadata=metadata or {}
        )
        
        # Apply filter
        if not self.filter.should_log(entry):
            return None
        
        # Mask sensitive data
        entry = self.filter.mask_sensitive(entry)
        
        # Write entry
        if self.async_mode and self._queue:
            try:
                self._queue.put_nowait(entry)
            except queue.Full:
                logger.warning("[Audit] Queue full, dropping entry")
        else:
            self._write_to_handlers(entry)
        
        return entry
    
    def query(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        user: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100
    ) -> List[AuditEntry]:
        """
        Query audit log entries.
        
        Note: This is a basic implementation. For production, use a database.
        
        Args:
            start_time: Start time filter
            end_time: End time filter
            user: User filter
            action: Action filter
            limit: Maximum entries to return
        
        Returns:
            List of matching entries
        """
        results = []
        
        # Find file handlers
        for handler in self.handlers:
            if isinstance(handler, FileAuditHandler):
                # Read from log files
                for log_file in handler.log_dir.glob("*.jsonl"):
                    try:
                        with open(log_file, 'r') as f:
                            for line in f:
                                data = json.loads(line.strip())
                                entry = AuditEntry.from_dict(data)
                                
                                # Apply filters
                                if start_time and entry.timestamp < start_time.isoformat():
                                    continue
                                if end_time and entry.timestamp > end_time.isoformat():
                                    continue
                                if user and entry.user != user:
                                    continue
                                if action and entry.action != action:
                                    continue
                                
                                results.append(entry)
                                
                                if len(results) >= limit:
                                    break
                                    
                    except Exception as e:
                        logger.error(f"[Audit] Query failed for {log_file}: {e}")
        
        # Sort by timestamp
        results.sort(key=lambda x: x.timestamp, reverse=True)
        
        return results[:limit]
    
    def flush(self):
        """Flush all handlers."""
        for handler in self.handlers:
            handler.flush()
    
    def close(self):
        """Close logger and all handlers."""
        self._running = False
        
        if self._worker_thread:
            self._worker_thread.join(timeout=5.0)
        
        self.flush()
        
        for handler in self.handlers:
            handler.close()
        
        logger.info("[Audit] Logger closed")


# Convenience function
def create_audit_logger(
    log_dir: str = "./audit_logs",
    use_syslog: bool = False,
    webhook_url: Optional[str] = None,
    **filter_kwargs
) -> AuditLogger:
    """
    Create audit logger with common configuration.
    
    Args:
        log_dir: Directory for log files
        use_syslog: Whether to use syslog
        webhook_url: Webhook URL for remote logging
        **filter_kwargs: Filter configuration
    
    Returns:
        Configured AuditLogger
    """
    audit_logger = AuditLogger(filter_config=AuditFilter(**filter_kwargs))
    
    # Add file handler
    file_handler = FileAuditHandler(log_dir=log_dir)
    audit_logger.add_handler(file_handler)
    
    # Add syslog if requested
    if use_syslog and SYSLOG_AVAILABLE:
        try:
            syslog_handler = SyslogAuditHandler()
            audit_logger.add_handler(syslog_handler)
        except Exception as e:
            logger.warning(f"[Audit] Syslog not available: {e}")
    
    # Add webhook if provided
    if webhook_url and REQUESTS_AVAILABLE:
        try:
            webhook_handler = WebhookAuditHandler(webhook_url=webhook_url)
            audit_logger.add_handler(webhook_handler)
        except Exception as e:
            logger.warning(f"[Audit] Webhook not available: {e}")
    
    return audit_logger
