"""
Concurrent Index Operations for KosDB

Provides online index building that doesn't block reads/writes.
Supports background construction, hot-swapping, and progress tracking.
"""

import os
import json
import time
import threading
import hashlib
from typing import Dict, Any, List, Optional, Tuple, Callable, Set
from dataclasses import dataclass, field
from enum import Enum, auto
from collections import defaultdict
import queue


class IndexState(Enum):
    """States of index lifecycle."""
    PENDING = auto()
    BUILDING = auto()
    VALIDATING = auto()
    READY = auto()
    ACTIVE = auto()
    FAILED = auto()
    DROPPING = auto()


class IndexType(Enum):
    """Types of indexes."""
    BTREE = auto()
    HASH = auto()
    UNIQUE = auto()
    COMPOSITE = auto()


@dataclass
class IndexEntry:
    """Represents an index entry."""
    key: Any
    row_ids: List[int]
    
    def __hash__(self):
        return hash(self.key)
    
    def __eq__(self, other):
        if isinstance(other, IndexEntry):
            return self.key == other.key
        return self.key == other


@dataclass
class IndexBuildProgress:
    """Tracks index build progress."""
    total_rows: int = 0
    processed_rows: int = 0
    start_time: float = 0.0
    end_time: Optional[float] = None
    
    @property
    def percent_complete(self) -> float:
        if self.total_rows == 0:
            return 0.0
        return (self.processed_rows / self.total_rows) * 100
    
    @property
    def elapsed_time(self) -> float:
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time
    
    @property
    def estimated_remaining(self) -> float:
        if self.processed_rows == 0:
            return 0.0
        rate = self.processed_rows / self.elapsed_time
        remaining = self.total_rows - self.processed_rows
        return remaining / rate if rate > 0 else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_rows': self.total_rows,
            'processed_rows': self.processed_rows,
            'percent_complete': round(self.percent_complete, 2),
            'elapsed_time': round(self.elapsed_time, 2),
            'estimated_remaining': round(self.estimated_remaining, 2)
        }


class ConcurrentIndex:
    """
    Thread-safe concurrent index implementation.
    Supports online building with concurrent reads/writes.
    """
    
    def __init__(self, name: str, table: str, columns: List[str],
                 index_type: IndexType = IndexType.BTREE,
                 unique: bool = False):
        self.name = name
        self.table = table
        self.columns = columns
        self.index_type = index_type
        self.unique = unique
        
        self.state = IndexState.PENDING
        self.data: Dict[Any, List[int]] = {}
        self.progress = IndexBuildProgress()
        
        self._lock = threading.RLock()
        self._pending_writes: List[Tuple[str, Any, int]] = []
        self._build_thread: Optional[threading.Thread] = None
        self._source_table: Optional[Any] = None
    
    def start_build(self, source_table: Any, 
                    callback: Optional[Callable] = None):
        """Start background index build."""
        with self._lock:
            if self.state != IndexState.PENDING:
                raise RuntimeError(f"Cannot start build from state {self.state}")
            
            self.state = IndexState.BUILDING
            self._source_table = source_table
            self.progress.start_time = time.time()
            self.progress.total_rows = len(source_table.data)
        
        self._build_thread = threading.Thread(
            target=self._build_worker,
            args=(callback,),
            daemon=True
        )
        self._build_thread.start()
    
    def _build_worker(self, callback: Optional[Callable]):
        """Background worker for index building."""
        try:
            with self._source_table._lock:
                snapshot = list(enumerate(self._source_table.data))
            
            batch_size = 1000
            for i in range(0, len(snapshot), batch_size):
                batch = snapshot[i:i + batch_size]
                
                for row_idx, row in batch:
                    self._index_row(row_idx, row)
                
                with self._lock:
                    self.progress.processed_rows += len(batch)
                
                time.sleep(0.001)
            
            self._apply_pending_writes()
            self._validate_index()
            
            with self._lock:
                self.state = IndexState.READY
                self.progress.end_time = time.time()
            
            if callback:
                callback(self.name, True)
                
        except Exception as e:
            with self._lock:
                self.state = IndexState.FAILED
                self.progress.end_time = time.time()
            
            if callback:
                callback(self.name, False, str(e))
    
    def _index_row(self, row_idx: int, row: Dict[str, Any]):
        """Index a single row."""
        if len(self.columns) == 1:
            key = row.get(self.columns[0])
        else:
            key = tuple(row.get(c) for c in self.columns)
        
        if key is None:
            return
        
        with self._lock:
            if key not in self.data:
                self.data[key] = []
            
            if self.unique and self.data[key]:
                raise ValueError(f"Duplicate key '{key}' in unique index")
            
            self.data[key].append(row_idx)
    
    def _apply_pending_writes(self):
        """Apply writes that occurred during build."""
        with self._lock:
            pending = self._pending_writes.copy()
            self._pending_writes.clear()
        
        for op, key, row_id in pending:
            if op == 'INSERT':
                self.insert(key, row_id)
            elif op == 'DELETE':
                self.delete(key, row_id)
    
    def _validate_index(self):
        """Validate index against source data."""
        self.state = IndexState.VALIDATING
        
        sample_size = min(100, len(self.data))
        import random
        samples = random.sample(list(self.data.items()), sample_size)
        
        for key, row_ids in samples:
            for row_id in row_ids:
                row = self._source_table.data[row_id]
                if len(self.columns) == 1:
                    actual_key = row.get(self.columns[0])
                else:
                    actual_key = tuple(row.get(c) for c in self.columns)
                
                if actual_key != key:
                    raise ValueError(f"Index validation failed for row {row_id}")
    
    def insert(self, key: Any, row_id: int):
        """Insert entry into index."""
        with self._lock:
            if self.state in (IndexState.BUILDING, IndexState.VALIDATING):
                self._pending_writes.append(('INSERT', key, row_id))
                return
            
            if key not in self.data:
                self.data[key] = []
            
            if self.unique and self.data[key]:
                raise ValueError(f"Duplicate key '{key}'")
            
            self.data[key].append(row_id)
    
    def delete(self, key: Any, row_id: int):
        """Delete entry from index."""
        with self._lock:
            if self.state in (IndexState.BUILDING, IndexState.VALIDATING):
                self._pending_writes.append(('DELETE', key, row_id))
                return
            
            if key in self.data:
                if row_id in self.data[key]:
                    self.data[key].remove(row_id)
                
                if not self.data[key]:
                    del self.data[key]
    
    def update(self, old_key: Any, new_key: Any, row_id: int):
        """Update key in index."""
        self.delete(old_key, row_id)
        self.insert(new_key, row_id)
    
    def lookup(self, key: Any) -> List[int]:
        """Lookup row IDs by key."""
        with self._lock:
            return self.data.get(key, []).copy()
    
    def range_scan(self, start_key: Any, end_key: Any) -> List[int]:
        """Range scan for B-tree indexes."""
        if self.index_type != IndexType.BTREE:
            raise ValueError("Range scan only supported for BTREE indexes")
        
        with self._lock:
            results = []
            for key, row_ids in self.data.items():
                if start_key <= key <= end_key:
                    results.extend(row_ids)
            return results
    
    def get_progress(self) -> IndexBuildProgress:
        """Get current build progress."""
        with self._lock:
            return IndexBuildProgress(
                total_rows=self.progress.total_rows,
                processed_rows=self.progress.processed_rows,
                start_time=self.progress.start_time,
                end_time=self.progress.end_time
            )
    
    def wait_for_ready(self, timeout: Optional[float] = None) -> bool:
        """Wait for index to be ready."""
        start = time.time()
        while True:
            with self._lock:
                if self.state in (IndexState.READY, IndexState.ACTIVE):
                    return True
                if self.state == IndexState.FAILED:
                    return False
            
            if timeout and time.time() - start > timeout:
                return False
            
            time.sleep(0.1)
    
    def activate(self):
        """Activate index for use."""
        with self._lock:
            if self.state != IndexState.READY:
                raise RuntimeError(f"Cannot activate from state {self.state}")
            self.state = IndexState.ACTIVE
    
    def deactivate(self):
        """Deactivate index."""
        with self._lock:
            self.state = IndexState.PENDING
    
    def drop(self):
        """Mark index for dropping."""
        with self._lock:
            self.state = IndexState.DROPPING
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize index metadata."""
        with self._lock:
            return {
                'name': self.name,
                'table': self.table,
                'columns': self.columns,
                'type': self.index_type.name,
                'unique': self.unique,
                'state': self.state.name,
                'entries': len(self.data),
                'progress': self.progress.to_dict()
            }


class IndexManager:
    """Manages multiple concurrent indexes."""
    
    def __init__(self):
        self._indexes: Dict[str, ConcurrentIndex] = {}
        self._table_indexes: Dict[str, Set[str]] = defaultdict(set)
        self._lock = threading.RLock()
        self._build_queue: queue.Queue = queue.Queue()
        self._worker_thread: Optional[threading.Thread] = None
        self._shutdown = False
    
    def start(self):
        """Start background index builder."""
        self._worker_thread = threading.Thread(target=self._build_worker)
        self._worker_thread.daemon = True
        self._worker_thread.start()
    
    def stop(self):
        """Stop background index builder."""
        self._shutdown = True
        if self._worker_thread:
            self._worker_thread.join(timeout=5.0)
    
    def _build_worker(self):
        """Background worker for queued index builds."""
        while not self._shutdown:
            try:
                index_name = self._build_queue.get(timeout=1.0)
                index = self._indexes.get(index_name)
                if index and index.state == IndexState.PENDING:
                    pass
            except queue.Empty:
                continue
    
    def create_index(self, name: str, table: str, columns: List[str],
                     table_ref: Any,
                     index_type: IndexType = IndexType.BTREE,
                     unique: bool = False,
                     online: bool = True) -> ConcurrentIndex:
        """Create new index."""
        with self._lock:
            if name in self._indexes:
                raise ValueError(f"Index '{name}' already exists")
            
            index = ConcurrentIndex(name, table, columns, index_type, unique)
            self._indexes[name] = index
            self._table_indexes[table].add(name)
            
            if online:
                index.start_build(table_ref, self._on_build_complete)
            else:
                index.start_build(table_ref, None)
                index.wait_for_ready()
                index.activate()
            
            return index
    
    def _on_build_complete(self, name: str, success: bool, error: Optional[str] = None):
        """Callback when index build completes."""
        if success:
            print(f"[INDEX] Build complete: {name}")
            index = self._indexes.get(name)
            if index:
                try:
                    index.activate()
                except Exception as e:
                    print(f"[INDEX] Failed to activate {name}: {e}")
        else:
            print(f"[INDEX] Build failed: {name} - {error}")
    
    def get_index(self, name: str) -> Optional[ConcurrentIndex]:
        """Get index by name."""
        with self._lock:
            return self._indexes.get(name)
    
    def get_table_indexes(self, table: str, 
                          active_only: bool = True) -> List[ConcurrentIndex]:
        """Get all indexes for a table."""
        with self._lock:
            index_names = self._table_indexes.get(table, set())
            indexes = []
            for name in index_names:
                idx = self._indexes.get(name)
                if idx:
                    if not active_only or idx.state == IndexState.ACTIVE:
                        indexes.append(idx)
            return indexes
    
    def drop_index(self, name: str) -> bool:
        """Drop an index."""
        with self._lock:
            index = self._indexes.get(name)
            if not index:
                return False
            
            index.drop()
            self._table_indexes[index.table].discard(name)
            del self._indexes[name]
            return True
    
    def update_indexes_for_insert(self, table: str, 
                                    row: Dict[str, Any],
                                    row_id: int):
        """Update all indexes for table on insert."""
        indexes = self.get_table_indexes(table, active_only=False)
        
        for index in indexes:
            if index.state in (IndexState.ACTIVE, IndexState.BUILDING, 
                               IndexState.VALIDATING, IndexState.READY):
                if len(index.columns) == 1:
                    key = row.get(index.columns[0])
                else:
                    key = tuple(row.get(c) for c in index.columns)
                
                if key is not None:
                    index.insert(key, row_id)
    
    def update_indexes_for_delete(self, table: str,
                                    row: Dict[str, Any],
                                    row_id: int):
        """Update all indexes for table on delete."""
        indexes = self.get_table_indexes(table, active_only=False)
        
        for index in indexes:
            if len(index.columns) == 1:
                key = row.get(index.columns[0])
            else:
                key = tuple(row.get(c) for c in index.columns)
            
            if key is not None:
                index.delete(key, row_id)
    
    def update_indexes_for_update(self, table: str,
                                    old_row: Dict[str, Any],
                                    new_row: Dict[str, Any],
                                    row_id: int):
        """Update all indexes for table on update."""
        indexes = self.get_table_indexes(table, active_only=False)
        
        for index in indexes:
            if len(index.columns) == 1:
                old_key = old_row.get(index.columns[0])
                new_key = new_row.get(index.columns[0])
            else:
                old_key = tuple(old_row.get(c) for c in index.columns)
                new_key = tuple(new_row.get(c) for c in index.columns)
            
            if old_key != new_key:
                index.update(old_key, new_key, row_id)
    
    def get_build_progress(self, name: str) -> Optional[IndexBuildProgress]:
        """Get build progress for an index."""
        index = self.get_index(name)
        if index:
            return index.get_progress()
        return None
    
    def list_indexes(self, table: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all indexes."""
        with self._lock:
            if table:
                names = self._table_indexes.get(table, set())
            else:
                names = self._indexes.keys()
            
            return [self._indexes[n].to_dict() for n in names]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get index manager statistics."""
        with self._lock:
            states = defaultdict(int)
            for idx in self._indexes.values():
                states[idx.state.name] += 1
            
            return {
                'total_indexes': len(self._indexes),
                'by_state': dict(states),
                'tables_with_indexes': len(self._table_indexes)
            }


class OnlineIndexBuilder:
    """High-level interface for online index operations."""
    
    def __init__(self, index_manager: IndexManager):
        self.index_manager = index_manager
        self._operations: Dict[str, Any] = {}
    
    def create_index_online(self, name: str, table: str, 
                            columns: List[str],
                            table_ref: Any,
                            unique: bool = False) -> str:
        """Create index online (non-blocking)."""
        op_id = hashlib.md5(
            f"{name}:{table}:{time.time()}".encode()
        ).hexdigest()[:8]
        
        index = self.index_manager.create_index(
            name, table, columns, table_ref,
            IndexType.BTREE, unique, online=True
        )
        
        self._operations[op_id] = {
            'index_name': name,
            'start_time': time.time(),
            'status': 'BUILDING'
        }
        
        return op_id
    
    def get_operation_status(self, op_id: str) -> Optional[Dict[str, Any]]:
        """Get status of online operation."""
        op = self._operations.get(op_id)
        if not op:
            return None
        
        index = self.index_manager.get_index(op['index_name'])
        if index:
            op['progress'] = index.get_progress().to_dict()
            op['state'] = index.state.name
        
        return op
    
    def wait_for_completion(self, op_id: str, 
                            timeout: Optional[float] = None) -> bool:
        """Wait for online operation to complete."""
        op = self._operations.get(op_id)
        if not op:
            return False
        
        index = self.index_manager.get_index(op['index_name'])
        if not index:
            return False
        
        return index.wait_for_ready(timeout)


def create_index_manager() -> IndexManager:
    """Create and start index manager."""
    manager = IndexManager()
    manager.start()
    return manager


def build_index_online(table_data: List[Dict[str, Any]],
                       columns: List[str],
                       unique: bool = False) -> ConcurrentIndex:
    """Build index online for table data."""
    class MockTable:
        def __init__(self, data):
            self.data = data
            self._lock = threading.RLock()
    
    table_ref = MockTable(table_data)
    
    manager = IndexManager()
    index = manager.create_index(
        f"idx_{'_'.join(columns)}",
        "temp_table",
        columns,
        table_ref,
        IndexType.BTREE,
        unique,
        online=True
    )
    
    return index
