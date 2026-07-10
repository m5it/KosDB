"""
Write-Ahead Logging (WAL) for KosDB

Provides durable transaction logging for crash recovery.
Ensures data durability by writing changes to log before applying to database.
"""

import os
import json
import struct
import time
import hashlib
import threading
from typing import Dict, Any, List, Optional, Callable, BinaryIO, Iterator, Set
from enum import Enum, auto
from dataclasses import dataclass, field
from pathlib import Path


class LogRecordType(Enum):
    """Types of WAL records."""
    BEGIN = auto()        # Transaction start
    INSERT = auto()       # Insert operation
    UPDATE = auto()       # Update operation
    DELETE = auto()       # Delete operation
    CREATE_TABLE = auto() # Create table
    DROP_TABLE = auto()   # Drop table
    CREATE_INDEX = auto() # Create index
    DROP_INDEX = auto()   # Drop index
    COMMIT = auto()       # Transaction commit
    ABORT = auto()        # Transaction abort
    CHECKPOINT = auto()   # Checkpoint marker


@dataclass
class LogRecord:
    """
    Single WAL record.
    """
    lsn: int                    # Log sequence number
    txn_id: int                 # Transaction ID
    record_type: LogRecordType
    table: Optional[str] = None        # Table name (if applicable)
    key: Optional[Any] = None          # Record key (if applicable)
    old_data: Optional[Dict] = None    # Old values (for undo)
    new_data: Optional[Dict] = None    # New values (for redo)
    timestamp: float = field(default_factory=time.time)
    checksum: Optional[str] = None
    
    def compute_checksum(self) -> str:
        """Compute checksum for record integrity."""
        data = {
            'lsn': self.lsn,
            'txn_id': self.txn_id,
            'type': self.record_type.name,
            'table': self.table,
            'key': self.key,
            'old_data': self.old_data,
            'new_data': self.new_data,
            'timestamp': self.timestamp
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]
    
    def verify(self) -> bool:
        """Verify record integrity."""
        return self.checksum == self.compute_checksum()
    
    def to_bytes(self) -> bytes:
        """Serialize to bytes."""
        # Header: lsn(8) + txn_id(8) + type(1) + timestamp(8) = 25 bytes
        header = struct.pack('>QQBd',
            self.lsn,
            self.txn_id,
            self.record_type.value,
            self.timestamp
        )
        
        # Body: JSON-encoded data
        body = json.dumps({
            'table': self.table,
            'key': self.key,
            'old_data': self.old_data,
            'new_data': self.new_data,
            'checksum': self.compute_checksum()
        }).encode('utf-8')
        
        # Length prefix (4 bytes) + header + body
        length = len(header) + len(body)
        return struct.pack('>I', length) + header + body
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'LogRecord':
        """Deserialize from bytes."""
        if len(data) < 29:  # 4 (length) + 25 (header)
            raise ValueError("Insufficient data for log record")
        
        # Parse length
        length = struct.unpack('>I', data[:4])[0]
        
        # Parse header
        header = data[4:29]
        lsn, txn_id, type_val, timestamp = struct.unpack('>QQBd', header)
        
        # Parse body
        body = json.loads(data[29:4+length].decode('utf-8'))
        
        record = cls(
            lsn=lsn,
            txn_id=txn_id,
            record_type=LogRecordType(type_val),
            table=body.get('table'),
            key=body.get('key'),
            old_data=body.get('old_data'),
            new_data=body.get('new_data'),
            timestamp=timestamp,
            checksum=body.get('checksum')
        )
        
        return record


class WriteAheadLog:
    """
    Write-ahead log manager.
    Handles log writing, reading, and recovery.
    """
    
    def __init__(self, log_dir: str, max_log_size: int = 10 * 1024 * 1024):
        self.log_dir = Path(log_dir)
        self.max_log_size = max_log_size
        
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.current_lsn = 0
        self.current_txn_id = 0
        self.current_log_file: Optional[BinaryIO] = None
        self.current_log_path: Optional[Path] = None
        self.current_log_size = 0
        
        self._lock = threading.RLock()
        self._txn_start_lsn: Dict[int, int] = {}  # txn_id -> start LSN
        
        # Initialize
        self._recover_lsn()
        self._open_new_log()
    
    def _recover_lsn(self):
        """Recover LSN from existing log files."""
        log_files = sorted(self.log_dir.glob('wal-*.log'))
        if log_files:
            # Read last record from latest log
            last_file = log_files[-1]
            try:
                with open(last_file, 'rb') as f:
                    f.seek(0, 2)  # End of file
                    pos = f.tell()
                    
                    # Find last record
                    while pos > 4:
                        f.seek(pos - 4)
                        length = struct.unpack('>I', f.read(4))[0]
                        if pos >= 4 + length:
                            f.seek(pos - 4 - length)
                            data = f.read(length + 4)
                            try:
                                record = LogRecord.from_bytes(data)
                                self.current_lsn = record.lsn
                                break
                            except:
                                pass
                        pos -= 1
            except:
                pass
    
    def _open_new_log(self):
        """Open a new log file."""
        if self.current_log_file:
            self.current_log_file.close()
        
        timestamp = int(time.time())
        self.current_log_path = self.log_dir / f'wal-{timestamp:010d}-{self.current_lsn:016d}.log'
        self.current_log_file = open(self.current_log_path, 'ab')
        self.current_log_size = self.current_log_file.tell()
    
    def _rotate_if_needed(self, record_size: int):
        """Rotate log file if it would exceed max size."""
        if self.current_log_size + record_size + 4 > self.max_log_size:
            self._open_new_log()
    
    def _write_record(self, record: LogRecord) -> int:
        """
        Write record to log.
        
        Returns:
            LSN of written record
        """
        with self._lock:
            self.current_lsn += 1
            record.lsn = self.current_lsn
            
            # Ensure checksum is computed
            if record.checksum is None:
                record.checksum = record.compute_checksum()
            
            data = record.to_bytes()
            
            # Rotate if needed
            self._rotate_if_needed(len(data))
            
            # Write to log
            self.current_log_file.write(data)
            self.current_log_file.flush()
            os.fsync(self.current_log_file.fileno())  # Ensure durability
            
            self.current_log_size += len(data)
            
            return record.lsn
    
    def begin_transaction(self) -> int:
        """
        Begin new transaction.
        
        Returns:
            Transaction ID
        """
        with self._lock:
            self.current_txn_id += 1
            txn_id = self.current_txn_id
            
            record = LogRecord(
                lsn=0,  # Will be assigned
                txn_id=txn_id,
                record_type=LogRecordType.BEGIN
            )
            
            lsn = self._write_record(record)
            self._txn_start_lsn[txn_id] = lsn
            
            return txn_id
    
    def log_insert(self, txn_id: int, table: str, key: Any, data: Dict):
        """Log insert operation."""
        record = LogRecord(
            lsn=0,
            txn_id=txn_id,
            record_type=LogRecordType.INSERT,
            table=table,
            key=key,
            new_data=data
        )
        self._write_record(record)
    
    def log_update(self, txn_id: int, table: str, key: Any,
                   old_data: Dict, new_data: Dict):
        """Log update operation."""
        record = LogRecord(
            lsn=0,
            txn_id=txn_id,
            record_type=LogRecordType.UPDATE,
            table=table,
            key=key,
            old_data=old_data,
            new_data=new_data
        )
        self._write_record(record)
    
    def log_delete(self, txn_id: int, table: str, key: Any, old_data: Dict):
        """Log delete operation."""
        record = LogRecord(
            lsn=0,
            txn_id=txn_id,
            record_type=LogRecordType.DELETE,
            table=table,
            key=key,
            old_data=old_data
        )
        self._write_record(record)
    
    def commit_transaction(self, txn_id: int):
        """Commit transaction."""
        record = LogRecord(
            lsn=0,
            txn_id=txn_id,
            record_type=LogRecordType.COMMIT
        )
        self._write_record(record)
        
        with self._lock:
            self._txn_start_lsn.pop(txn_id, None)
    
    def abort_transaction(self, txn_id: int):
        """Abort transaction."""
        record = LogRecord(
            lsn=0,
            txn_id=txn_id,
            record_type=LogRecordType.ABORT
        )
        self._write_record(record)
        
        with self._lock:
            self._txn_start_lsn.pop(txn_id, None)
    
    def log_checkpoint(self, active_txns: List[int]):
        """Write checkpoint record."""
        record = LogRecord(
            lsn=0,
            txn_id=0,
            record_type=LogRecordType.CHECKPOINT,
            new_data={'active_transactions': active_txns}
        )
        self._write_record(record)
    
    def flush(self):
        """Flush log to disk."""
        with self._lock:
            if self.current_log_file:
                self.current_log_file.flush()
                os.fsync(self.current_log_file.fileno())
    
    def close(self):
        """Close log."""
        with self._lock:
            if self.current_log_file:
                self.current_log_file.close()
                self.current_log_file = None
    
    def read_log(self, start_lsn: int = 0) -> Iterator[LogRecord]:
        """
        Read log records from specified LSN.
        
        Args:
            start_lsn: Starting LSN (inclusive)
        
        Yields:
            LogRecord objects
        """
        log_files = sorted(self.log_dir.glob('wal-*.log'))
        
        for log_file in log_files:
            with open(log_file, 'rb') as f:
                while True:
                    # Read length prefix
                    length_bytes = f.read(4)
                    if len(length_bytes) < 4:
                        break
                    
                    length = struct.unpack('>I', length_bytes)[0]
                    
                    # Read record data
                    data = f.read(length)
                    if len(data) < length:
                        break  # Incomplete record
                    
                    try:
                        record = LogRecord.from_bytes(length_bytes + data)
                        if record.lsn >= start_lsn:
                            yield record
                    except Exception as e:
                        # Corrupt record, skip
                        print(f"Warning: corrupt log record at {log_file}: {e}")
                        break


class WALRecovery:
    """
    Recovery manager using WAL.
    Implements ARIES-style recovery with analysis, redo, and undo phases.
    """
    
    def __init__(self, wal: WriteAheadLog, db: Any):
        self.wal = wal
        self.db = db
        
        self.last_checkpoint_lsn = 0
        self.active_transactions: Dict[int, int] = {}  # txn_id -> start_lsn
        self.committed_transactions: Set[int] = set()  # txn_id of committed
        self.aborted_transactions: Set[int] = set()  # txn_id of aborted
        self.dirty_pages: Dict[str, int] = {}  # page_id -> rec_lsn
    
    def analyze(self) -> Dict[int, int]:
        """
        Analysis phase: scan log to find active transactions and dirty pages.
        
        Returns:
            Dictionary of active transactions (txn_id -> start_lsn)
        """
        self.active_transactions.clear()
        self.committed_transactions.clear()
        self.aborted_transactions.clear()
        self.dirty_pages.clear()
        
        for record in self.wal.read_log():
            if record.record_type == LogRecordType.BEGIN:
                self.active_transactions[record.txn_id] = record.lsn
            elif record.record_type == LogRecordType.COMMIT:
                self.committed_transactions.add(record.txn_id)
                self.active_transactions.pop(record.txn_id, None)
            elif record.record_type == LogRecordType.ABORT:
                self.aborted_transactions.add(record.txn_id)
                self.active_transactions.pop(record.txn_id, None)
            elif record.record_type == LogRecordType.CHECKPOINT:
                self.last_checkpoint_lsn = record.lsn
                if record.new_data and 'active_transactions' in record.new_data:
                    for txn_id in record.new_data['active_transactions']:
                        if txn_id not in self.active_transactions:
                            self.active_transactions[txn_id] = record.lsn
        
        return self.active_transactions
    
    def redo(self, redo_callback: Callable[[LogRecord], None]):
        """
        Redo phase: reapply all committed changes.
        
        Args:
            redo_callback: Function to apply record to database
        """
        for record in self.wal.read_log(self.last_checkpoint_lsn):
            if record.record_type in (LogRecordType.INSERT, 
                                       LogRecordType.UPDATE,
                                       LogRecordType.DELETE):
                # Only redo if transaction committed (not active and not aborted)
                if record.txn_id in self.committed_transactions:
                    redo_callback(record)
    
    def undo(self, undo_callback: Callable[[LogRecord], None]):
        """
        Undo phase: rollback uncommitted transactions.
        
        Args:
            undo_callback: Function to undo record from database
        """
        # Process active transactions in reverse LSN order
        txn_records: Dict[int, List[LogRecord]] = {}
        
        for record in self.wal.read_log():
            if record.txn_id in self.active_transactions:
                if record.txn_id not in txn_records:
                    txn_records[record.txn_id] = []
                txn_records[record.txn_id].append(record)
        
        # Undo in reverse order
        for txn_id, records in txn_records.items():
            for record in reversed(records):
                if record.record_type in (LogRecordType.INSERT,
                                          LogRecordType.UPDATE,
                                          LogRecordType.DELETE):
                    undo_callback(record)
    
    def recover(self, 
                redo_callback: Callable[[LogRecord], None],
                undo_callback: Callable[[LogRecord], None]) -> bool:
        """
        Full recovery process.
        
        Args:
            redo_callback: Function to redo a record
            undo_callback: Function to undo a record
        
        Returns:
            True if recovery was successful
        """
        print("[WAL] Starting recovery...")
        
        # Analysis phase
        active = self.analyze()
        print(f"[WAL] Analysis: {len(active)} active transactions")
        
        # Redo phase
        print("[WAL] Redo phase...")
        self.redo(redo_callback)
        
        # Undo phase
        if active:
            print(f"[WAL] Undo phase for {len(active)} transactions...")
            self.undo(undo_callback)
        
        print("[WAL] Recovery complete")
        return True


class TransactionManager:
    """
    Transaction manager with WAL integration.
    """
    
    def __init__(self, wal: WriteAheadLog, db: Any):
        self.wal = wal
        self.db = db
        
        self._active_transactions: Dict[int, Dict] = {}
        self._lock = threading.RLock()
    
    def begin(self) -> int:
        """Begin transaction."""
        txn_id = self.wal.begin_transaction()
        
        with self._lock:
            self._active_transactions[txn_id] = {
                'start_time': time.time(),
                'operations': []
            }
        
        return txn_id
    
    def commit(self, txn_id: int):
        """Commit transaction."""
        self.wal.commit_transaction(txn_id)
        
        with self._lock:
            self._active_transactions.pop(txn_id, None)
    
    def abort(self, txn_id: int):
        """Abort transaction."""
        self.wal.abort_transaction(txn_id)
        
        with self._lock:
            self._active_transactions.pop(txn_id, None)
    
    def insert(self, txn_id: int, table: str, key: Any, data: Dict):
        """Insert with logging."""
        self.wal.log_insert(txn_id, table, key, data)
    
    def update(self, txn_id: int, table: str, key: Any,
               old_data: Dict, new_data: Dict):
        """Update with logging."""
        self.wal.log_update(txn_id, table, key, old_data, new_data)
    
    def delete(self, txn_id: int, table: str, key: Any, old_data: Dict):
        """Delete with logging."""
        self.wal.log_delete(txn_id, table, key, old_data)
    
    def checkpoint(self):
        """Create checkpoint."""
        with self._lock:
            active_txns = list(self._active_transactions.keys())
        
        self.wal.log_checkpoint(active_txns)
        self.wal.flush()
        
        print(f"[WAL] Checkpoint created with {len(active_txns)} active transactions")


# Convenience functions
def create_wal(log_dir: str, max_log_size: int = 10 * 1024 * 1024) -> WriteAheadLog:
    """
    Create WAL instance.
    
    Args:
        log_dir: Directory for log files
        max_log_size: Maximum size of each log file
    
    Returns:
        Configured WriteAheadLog instance
    """
    return WriteAheadLog(log_dir, max_log_size)


def recover_database(wal: WriteAheadLog, db: Any,
                    redo_fn: Callable, undo_fn: Callable) -> bool:
    """
    Recover database from WAL.
    
    Args:
        wal: WriteAheadLog instance
        db: Database to recover
        redo_fn: Function to redo operations
        undo_fn: Function to undo operations
    
    Returns:
        True if recovery successful
    """
    recovery = WALRecovery(wal, db)
    return recovery.recover(redo_fn, undo_fn)
