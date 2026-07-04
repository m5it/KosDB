"""
Binary Log (Binlog) System for Replication

Stores all write operations in LevelDB for replication purposes.
Each entry has a position number for tracking replication progress.
"""

import os
import json
import time
from typing import Optional, Dict, Any, List
import plyvel


class Binlog:
    """
    Binary log for database replication.
    Stores all write operations with sequential position numbers.
    """
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.binlog_dir = os.path.join(data_dir, "_binlog")
        self._db: Optional[plyvel.DB] = None
        self._current_position = 0
        self._ensure_db()
        self._load_current_position()
    
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
    
    def write_entry(self, server_id: int, database: str, operation: str,
                    table: Optional[str] = None, data: Optional[Dict] = None) -> int:
        """
        Write a new entry to the binlog.
        
        Args:
            server_id: ID of the server that made the change
            database: Database name where change occurred
            operation: Type of operation (INSERT, UPDATE, DELETE, etc.)
            table: Table name (if applicable)
            data: Operation data (row values, conditions, etc.)
        
        Returns:
            Position number of this entry
        """
        self._current_position += 1
        position = self._current_position
        
        entry = {
            "position": position,
            "timestamp": time.time(),
            "server_id": server_id,
            "database": database,
            "operation": operation,
            "table": table,
            "data": data
        }
        
        key = f"entry:{position:012d}".encode()
        self._db.put(key, json.dumps(entry).encode())
        self._save_position()
        
        return position
    
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
    
    def get_entry(self, position: int) -> Optional[Dict]:
        """Get a specific binlog entry by position."""
        key = f"entry:{position:012d}".encode()
        data = self._db.get(key)
        if data:
            return json.loads(data.decode())
        return None
    
    def get_latest_position(self) -> int:
        """Get the current/latest binlog position."""
        return self._current_position
    
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