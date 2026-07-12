
"""
Enhanced Binary Log (Binlog) System with Batch Support for Replication

Stores all write operations including batch commands with proper tracking
for replication. Each entry has a position number and batch metadata.

Features:
- Individual command logging within batches
- Batch markers for atomic group tracking
- Batch position tracking for lag reporting
- Optimized batch entry storage
"""

import os
import json
import time
import threading
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import plyvel


class BatchMarker(Enum):
    """Batch marker types for binlog entries."""
    BATCH_START = "batch_start"
    BATCH_END = "batch_end"
    BATCH_COMMAND = "batch_command"
    SINGLE = "single"  # Non-batch command


@dataclass
class BatchBinlogEntry:
    """Extended binlog entry with batch support."""
    position: int
    timestamp: float
    server_id: int
    database: str
    operation: str
    table: Optional[str]
    data: Optional[Dict]
    
    # Batch metadata
    batch_id: Optional[str] = None
    batch_marker: str = BatchMarker.SINGLE.value
    batch_command_index: Optional[int] = None
    batch_total_commands: Optional[int] = None
    batch_error_mode: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'BatchBinlogEntry':
        """Create from dictionary."""
        return cls(**data)


class BatchBinlog:
    """
    Binary log with batch operation support for database replication.
    
    Features:
    - Each command in a batch is logged individually
    - Batch markers track atomic groups
    - Batch position tracking for lag reporting
    - Optimized storage for batch operations
    """
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.binlog_dir = os.path.join(data_dir, "_binlog")
        self._db: Optional[plyvel.DB] = None
        self._current_position = 0
        self._lock = threading.RLock()
        self._ensure_db()
        self._load_current_position()
        
        # Batch tracking
        self._active_batches: Dict[str, Dict] = {}  # batch_id -> batch info
        self._batch_positions: Dict[str, List[int]] = {}  # batch_id -> [positions]
    
    def _ensure_db(self):
        """Ensure binlog database exists."""
        if not os.path.exists(self.binlog_dir):
            os.makedirs(self.binlog_dir)
        self._db = plyvel.DB(self.binlog_dir, create_if_missing=True)
    
    def _load_current_position(self):
        """Load the current binlog position."""
        pos_data = self._db.get(b"_meta:position")
        if pos_data:
            self._current_position = int(pos_data.decode())
        else:
            self._current_position = 0
    
    def _save_position(self):
        """Save current position to disk."""
        self._db.put(b"_meta:position", str(self._current_position).encode())
    
    def _next_position(self) -> int:
        """Get next position number."""
        with self._lock:
            self._current_position += 1
            return self._current_position
    
    def write_entry(self, server_id: int, database: str, operation: str,
                    table: Optional[str] = None, data: Optional[Dict] = None,
                    batch_id: Optional[str] = None,
                    batch_marker: BatchMarker = BatchMarker.SINGLE,
                    batch_command_index: Optional[int] = None,
                    batch_total_commands: Optional[int] = None,
                    batch_error_mode: Optional[str] = None) -> int:
        """
        Write a new entry to the binlog.
        
        Args:
            server_id: ID of the server that made the change
            database: Database name where change occurred
            operation: Type of operation (INSERT, UPDATE, DELETE, etc.)
            table: Table name (if applicable)
            data: Operation data (row values, conditions, etc.)
            batch_id: Unique batch identifier (for batch operations)
            batch_marker: Type of batch marker
            batch_command_index: Index within batch (0-based)
            batch_total_commands: Total commands in batch
            batch_error_mode: Error handling mode for batch
        
        Returns:
            Position number of this entry
        """
        position = self._next_position()
        
        entry = BatchBinlogEntry(
            position=position,
            timestamp=time.time(),
            server_id=server_id,
            database=database,
            operation=operation,
            table=table,
            data=data,
            batch_id=batch_id,
            batch_marker=batch_marker.value,
            batch_command_index=batch_command_index,
            batch_total_commands=batch_total_commands,
            batch_error_mode=batch_error_mode
        )
        
        key = f"entry:{position:012d}".encode()
        self._db.put(key, json.dumps(entry.to_dict()).encode())
        self._save_position()
        
        # Track batch positions
        if batch_id:
            with self._lock:
                if batch_id not in self._batch_positions:
                    self._batch_positions[batch_id] = []
                self._batch_positions[batch_id].append(position)
        
        return position
    
    def write_batch_start(self, server_id: int, database: str, 
                          batch_id: str, total_commands: int,
                          error_mode: str = "continue") -> int:
        """
        Write batch start marker to binlog.
        
        Args:
            server_id: Server ID
            database: Database name
            batch_id: Unique batch identifier
            total_commands: Expected number of commands in batch
            error_mode: Batch error handling mode
        
        Returns:
            Position of batch start marker
        """
        return self.write_entry(
            server_id=server_id,
            database=database,
            operation="BATCH_START",
            table=None,
            data={"batch_id": batch_id, "total_commands": total_commands},
            batch_id=batch_id,
            batch_marker=BatchMarker.BATCH_START,
            batch_total_commands=total_commands,
            batch_error_mode=error_mode
        )
    
    def write_batch_command(self, server_id: int, database: str,
                           batch_id: str, operation: str, table: str,
                           data: Dict, command_index: int,
                           total_commands: int, error_mode: str) -> int:
        """
        Write individual batch command to binlog.
        
        Args:
            server_id: Server ID
            database: Database name
            batch_id: Batch identifier
            operation: Command operation type
            table: Table name
            data: Command data
            command_index: Index within batch (0-based)
            total_commands: Total commands in batch
            error_mode: Error handling mode
        
        Returns:
            Position of this command entry
        """
        return self.write_entry(
            server_id=server_id,
            database=database,
            operation=operation,
            table=table,
            data=data,
            batch_id=batch_id,
            batch_marker=BatchMarker.BATCH_COMMAND,
            batch_command_index=command_index,
            batch_total_commands=total_commands,
            batch_error_mode=error_mode
        )
    
    def write_batch_end(self, server_id: int, database: str,
                        batch_id: str, commands_executed: int,
                        commands_failed: int) -> int:
        """
        Write batch end marker to binlog.
        
        Args:
            server_id: Server ID
            database: Database name
            batch_id: Batch identifier
            commands_executed: Number of commands that were executed
            commands_failed: Number of commands that failed
        
        Returns:
            Position of batch end marker
        """
        return self.write_entry(
            server_id=server_id,
            database=database,
            operation="BATCH_END",
            table=None,
            data={
                "batch_id": batch_id,
                "commands_executed": commands_executed,
                "commands_failed": commands_failed
            },
            batch_id=batch_id,
            batch_marker=BatchMarker.BATCH_END,
            batch_total_commands=commands_executed
        )
    
    def get_entries(self, from_position: int, limit: int = 100) -> List[Dict]:
        """
        Get binlog entries starting from a specific position.
        
        Args:
            from_position: Start from this position (exclusive)
            limit: Maximum number of entries to return
        
        Returns:
            List of binlog entries
        """
        entries = []
        start_key = f"entry:{from_position:012d}".encode()
        
        for key, value in self._db.iterator(start=start_key):
            if key.startswith(b"_meta:"):
                continue
            
            entry = json.loads(value.decode())
            if entry["position"] > from_position:
                entries.append(entry)
                if len(entries) >= limit:
                    break
        
        return entries
    
    def get_batch_entries(self, batch_id: str) -> List[Dict]:
        """
        Get all entries for a specific batch.
        
        Args:
            batch_id: Batch identifier
        
        Returns:
            List of batch entries (start, commands, end)
        """
        with self._lock:
            positions = self._batch_positions.get(batch_id, [])
        
        entries = []
        for pos in positions:
            entry = self.get_entry(pos)
            if entry:
                entries.append(entry)
        
        return entries
    
    def get_batch_position(self, batch_id: str) -> Optional[int]:
        """
        Get the position of the batch end marker.
        
        Args:
            batch_id: Batch identifier
        
        Returns:
            Position of batch end, or None if batch not complete
        """
        entries = self.get_batch_entries(batch_id)
        for entry in entries:
            if entry.get('batch_marker') == BatchMarker.BATCH_END.value:
                return entry['position']
        return None
    
    def get_batch_lag(self, batch_id: str, current_position: int) -> Optional[int]:
        """
        Calculate replication lag for a batch.
        
        Args:
            batch_id: Batch identifier
            current_position: Current replication position
        
        Returns:
            Number of entries behind, or None if batch not found
        """
        batch_end_pos = self.get_batch_position(batch_id)
        if batch_end_pos is None:
            return None
        
        return batch_end_pos - current_position
    
    def get_entry(self, position: int) -> Optional[Dict]:
        """Get a specific binlog entry by position."""
        key = f"entry:{position:012d}".encode()
        data = self._db.get(key)
        if data:
            return json.loads(data.decode())
        return None
    
    def get_latest_position(self) -> int:
        """Get the current/latest binlog position."""
        with self._lock:
            return self._current_position
    
    def get_batch_status(self, batch_id: str) -> Optional[Dict]:
        """
        Get status of a batch.
        
        Returns:
            Dict with batch status, or None if batch not found
        """
        entries = self.get_batch_entries(batch_id)
        if not entries:
            return None
        
        start_entry = None
        end_entry = None
        commands = []
        
        for entry in entries:
            marker = entry.get('batch_marker')
            if marker == BatchMarker.BATCH_START.value:
                start_entry = entry
            elif marker == BatchMarker.BATCH_END.value:
                end_entry = entry
            elif marker == BatchMarker.BATCH_COMMAND.value:
                commands.append(entry)
        
        return {
            'batch_id': batch_id,
            'started': start_entry is not None,
            'completed': end_entry is not None,
            'start_position': start_entry['position'] if start_entry else None,
            'end_position': end_entry['position'] if end_entry else None,
            'commands_logged': len(commands),
            'total_commands': start_entry.get('batch_total_commands') if start_entry else None,
            'commands_executed': end_entry.get('data', {}).get('commands_executed') if end_entry else None,
            'commands_failed': end_entry.get('data', {}).get('commands_failed') if end_entry else None
        }
    
    def list_active_batches(self) -> List[Dict]:
        """
        List all active (incomplete) batches.
        
        Returns:
            List of batch status dictionaries
        """
        active = []
        seen_batches = set()
        
        # Scan recent entries for active batches
        latest = self.get_latest_position()
        entries = self.get_entries(max(0, latest - 10000), limit=10000)
        
        for entry in entries:
            batch_id = entry.get('batch_id')
            if not batch_id or batch_id in seen_batches:
                continue
            
            status = self.get_batch_status(batch_id)
            if status and not status['completed']:
                active.append(status)
                seen_batches.add(batch_id)
        
        return active
    
    def truncate_before(self, position: int):
        """
        Delete all entries before the given position.
        Used for log rotation/cleanup.
        """
        keys_to_delete = []
        end_key = f"entry:{position:012d}".encode()
        
        for key, _ in self._db.iterator(stop=end_key):
            if key.startswith(b"_meta:"):
                continue
            keys_to_delete.append(key)
        
        for key in keys_to_delete:
            self._db.delete(key)
    
    def close(self):
        """Close the binlog database."""
        if self._db:
            self._save_position()
            self._db.close()
            self._db = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


class BatchReplicationLagDetector:
    """
    Detects replication lag for batch operations.
    
    Monitors batch progress and alerts when lag exceeds thresholds.
    """
    
    def __init__(self, binlog: BatchBinlog, 
                 lag_threshold_ms: int = 1000,
                 check_interval: int = 5):
        self.binlog = binlog
        self.lag_threshold_ms = lag_threshold_ms
        self.check_interval = check_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
    
    def start(self):
        """Start lag detection monitoring."""
        self._running = True
        self._thread = threading.Thread(target=self._monitor, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop lag detection monitoring."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
    
    def _monitor(self):
        """Monitor loop for batch lag detection."""
        while self._running:
            try:
                active_batches = self.binlog.list_active_batches()
                
                for batch in active_batches:
                    if batch['started'] and not batch['completed']:
                        start_pos = batch['start_position']
                        current_pos = self.binlog.get_latest_position()
                        
                        # Calculate lag in entries
                        lag_entries = current_pos - start_pos
                        
                        if lag_entries > 100:  # More than 100 entries behind
                            print(f"[BATCH LAG] Batch {batch['batch_id']}: "
                                  f"{lag_entries} entries behind")
                
                time.sleep(self.check_interval)
                
            except Exception as e:
                print(f"[BATCH LAG] Monitor error: {e}")
                time.sleep(self.check_interval)
    
    def get_batch_lag_report(self, batch_id: str, slave_position: int) -> Dict:
        """
        Generate lag report for a specific batch.
        
        Args:
            batch_id: Batch identifier
            slave_position: Current slave position
        
        Returns:
            Lag report dictionary
        """
        batch_end = self.binlog.get_batch_position(batch_id)
        
        if batch_end is None:
            return {
                'batch_id': batch_id,
                'status': 'unknown',
                'lag_entries': None,
                'lag_ms': None
            }
        
        lag_entries = batch_end - slave_position
        
        # Estimate lag time (rough estimate based on typical entry rate)
        lag_ms = lag_entries * 10  # Assume 10ms per entry
        
        return {
            'batch_id': batch_id,
            'status': 'lagging' if lag_entries > 100 else 'current',
            'lag_entries': lag_entries,
            'lag_ms': lag_ms,
            'batch_end_position': batch_end,
            'slave_position': slave_position
        }
