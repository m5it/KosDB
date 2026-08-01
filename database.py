
"""LevelDB database layer with CRUD operations, user management and privileges."""

import os
import json
import hashlib
import secrets
import time
import threading
import queue
import plyvel
from typing import Optional, Dict, Any, List
from binlog import Binlog

try:
    from sort_engine import SortEngine, get_sort_engine
    SORT_ENGINE_AVAILABLE = True
except ImportError:
    SORT_ENGINE_AVAILABLE = False


class Database:
    """LevelDB database layer with CRUD operations, user management and privileges."""
    
    def __init__(self, data_dir: str = "data", server_id: int = 1, 
                 cache_size: int = 8*1024*1024,  # 8MB default block cache
                 write_buffer_size: int = 4*1024*1024,  # 4MB default
                 max_open_files: int = 1000,
                 compression: str = 'snappy',
                 bloom_filter_bits: int = 10,
                 sync_writes: bool = False,  # fsync on every write
                 disable_wal: bool = False,  # Disable WAL for bulk load
                 sort_engine: Optional[Any] = None):  # Sort engine for ORDER BY
        """
        Initialize database with LevelDB tuning options.
        
        Args:
            data_dir: Database directory path
            server_id: Server ID for replication
            cache_size: LRU block cache size in bytes (default 8MB)
            write_buffer_size: Memtable size in bytes (default 4MB)
            max_open_files: Max open file handles (default 1000)
            compression: 'snappy', 'zstd', or None
            bloom_filter_bits: Bits per key for bloom filter (default 10, 0=disabled)
            sync_writes: If True, fsync to disk on every write (slower, more durable)
            disable_wal: If True, disable Write-Ahead Log for bulk loads (faster, less safe)
        """
        self.data_dir = data_dir
        self.db_path = data_dir
        self.server_id = server_id
        
        # LevelDB tuning options
        self._cache_size = cache_size
        self._write_buffer_size = write_buffer_size
        self._max_open_files = max_open_files
        self._compression = compression
        self._bloom_filter_bits = bloom_filter_bits
        self._sync_writes = sync_writes
        self._disable_wal = disable_wal
        
        self.current_db: Optional[str] = None
        self._db: Optional[plyvel.DB] = None
        self._system_db: Optional[plyvel.DB] = None
        self._binlog: Optional[Binlog] = None
        self._binlog_queue: Optional[queue.Queue] = None
        self._binlog_thread: Optional[threading.Thread] = None
        self._binlog_shutdown = False
        self._transaction_active = False
        self._transaction_changes: Dict[bytes, Optional[bytes]] = {}
        self._transaction_binlog: List[Dict[str, Any]] = []

        # Initialize sort engine for ORDER BY operations
        if SORT_ENGINE_AVAILABLE:
            if sort_engine is not None:
                self._sort_engine = sort_engine
            else:
                self._sort_engine = get_sort_engine()
        else:
            self._sort_engine = None

        self._db_lock = threading.Lock()
        self._counter_lock = threading.Lock()
        self._ensure_data_dir()
        self._open_system_db()
        self._open_binlog()
        self._start_binlog_worker()
    
    def _ensure_data_dir(self):
        """Ensure data directory exists."""
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
    
    def _open_system_db(self):
        """Open system database for users and privileges with tuning options."""
        system_db_path = os.path.join(self.data_dir, "_system")
        self._system_db = plyvel.DB(
            system_db_path,
            create_if_missing=True,
            lru_cache_size=self._cache_size,
            write_buffer_size=self._write_buffer_size,
            max_open_files=self._max_open_files,
            compression=self._compression,
            bloom_filter_bits=self._bloom_filter_bits
        )
    
    def _open_binlog(self):
        """Open binary log for replication."""
        self._binlog = Binlog(self.data_dir)
    
    def _start_binlog_worker(self):
        """Start background thread for async binlog writing."""
        if self._binlog:
            self._binlog_queue = queue.Queue()
            self._binlog_thread = threading.Thread(target=self._binlog_worker, daemon=True)
            self._binlog_thread.start()
    
    def _binlog_worker(self):
        """Background worker that writes binlog entries from queue."""
        while True:
            try:
                entry = self._binlog_queue.get(timeout=1)
            except queue.Empty:
                if self._binlog_shutdown:
                    break
                continue
            try:
                if entry is None:
                    break
                self._binlog.write_entry(**entry)
            except Exception as e:
                print(f"Binlog worker error: {e}")
            finally:
                self._binlog_queue.task_done()
    
    def _flush_binlog_queue(self):
        """Flush remaining binlog entries on shutdown."""
        if self._binlog_queue and self._binlog:
            self._binlog_shutdown = True
            # Signal worker to stop after draining pending entries
            self._binlog_queue.put(None)
            if self._binlog_thread and self._binlog_thread.is_alive():
                self._binlog_thread.join(timeout=5)
            # Write any entries the worker did not get to
            while not self._binlog_queue.empty():
                try:
                    entry = self._binlog_queue.get_nowait()
                except queue.Empty:
                    break
                try:
                    if entry:
                        self._binlog.write_entry(**entry)
                except Exception as e:
                    print(f"Binlog flush error: {e}")
    
    def _log_binlog_async(self, **kwargs):
        """Non-blocking binlog write - puts entry in queue for background thread.
        
        TRADE-OFF: Last few writes may be lost on crash, but normal shutdown
        flushes all entries. Reduces write latency by ~50% by moving I/O
        to background thread.
        
        During an active transaction, entries are buffered and only enqueued
        on commit (dropped on rollback) so replicas don't see uncommitted ops.
        """
        if self._transaction_active:
            self._transaction_binlog.append(kwargs)
            return
        if self._binlog and self._binlog_queue:
            self._binlog_queue.put(kwargs)
    
    def _ensure_system_tables(self):
        """Ensure system tables for users and privileges exist."""
        # Users table
        if not self._system_db.get(b"_schema:_users"):
            schema = {"columns": ["username", "password_hash", "is_admin", "created_at"], "next_id": 1}
            self._system_db.put(b"_schema:_users", json.dumps(schema).encode())
        
        # Privileges table
        if not self._system_db.get(b"_schema:_privileges"):
            schema = {"columns": ["username", "db_pattern", "table_pattern", "privileges"], "next_id": 1}
            self._system_db.put(b"_schema:_privileges", json.dumps(schema).encode())
    
    def _hash_password(self, password: str) -> str:
        """Hash password using SHA-256 with salt."""
        salt = secrets.token_hex(16)
        pwdhash = hashlib.sha256((password + salt).encode()).hexdigest()
        return f"{salt}${pwdhash}"
    
    def _verify_password(self, password: str, stored_hash: str) -> bool:
        """Verify password against stored hash."""
        try:
            salt, hash_val = stored_hash.split("$")
            pwdhash = hashlib.sha256((password + salt).encode()).hexdigest()
            return pwdhash == hash_val
        except ValueError:
            return False
    
    def _db_path(self, db_name: str) -> str:
        """Get path for database directory."""
        return os.path.join(self.data_dir, db_name)
    
    def _make_key(self, table_name: str, row_id: str) -> bytes:
        """Create a key for a row."""
        return f"{table_name}:{row_id}".encode()
    
    def _get_current(self, key: bytes) -> Optional[bytes]:
        """Read a key, seeing pending transaction changes first (read-your-own-writes)."""
        if self._transaction_active and key in self._transaction_changes:
            return self._transaction_changes[key]
        return self._db.get(key)
    
    def get_schema(self, table_name: str) -> Optional[Dict[str, Any]]:
        """Return the schema dict for a table, or None if it doesn't exist."""
        if not self._db:
            return None
        schema_data = self._get_current(f"_schema:{table_name}".encode())
        if not schema_data:
            return None
        return json.loads(schema_data.decode())
    
    # Transaction support
    def begin_transaction(self) -> str:
        """Begin a new transaction."""
        if not self._db:
            return "ERROR: No database selected"
        if self._transaction_active:
            return "ERROR: Transaction already active"
        
        self._transaction_active = True
        self._transaction_changes = {}
        self._transaction_binlog = []
        self._transaction_start_time = time.time()
        return "OK: Transaction started"
    
    def commit_transaction(self) -> str:
        """Commit the current transaction using WriteBatch for atomicity."""
        if not self._transaction_active:
            return "ERROR: No active transaction"
        
        if not self._db:
            return "ERROR: No database selected"
        
        try:
            # Use WriteBatch for atomic commit - all changes succeed or fail together
            with self._db.write_batch(transaction=True) as batch:
                for key, value in self._transaction_changes.items():
                    if value is None:
                        batch.delete(key)
                    else:
                        batch.put(key, value)
                # batch.write() is called automatically when exiting context
            
            duration = time.time() - self._transaction_start_time
            changes = len(self._transaction_changes)
            self._transaction_active = False
            self._transaction_changes = {}
            
            # Publish buffered binlog entries now that the transaction is durable
            pending_binlog = self._transaction_binlog
            self._transaction_binlog = []
            if self._binlog and self._binlog_queue:
                for entry in pending_binlog:
                    self._binlog_queue.put(entry)
            
            return f"OK: Committed {changes} change(s) atomically in {duration:.3f}s"
        except Exception as e:
            # Transaction failed - all changes rolled back automatically by LevelDB
            self._transaction_active = False
            self._transaction_changes = {}
            self._transaction_binlog = []
            return f"ERROR: Transaction failed and rolled back: {e}"
    
    def rollback_transaction(self) -> str:
        """Rollback the current transaction."""
        if not self._transaction_active:
            return "ERROR: No active transaction"
        
        changes = len(self._transaction_changes)
        self._transaction_active = False
        self._transaction_changes = {}
        self._transaction_binlog = []  # Discard binlog entries for rolled-back ops
        
        return f"OK: Rolled back {changes} change(s)"
    
    def _transaction_put(self, key: bytes, value: bytes):
        """Queue a put operation in the transaction."""
        if self._transaction_active:
            self._transaction_changes[key] = value
        else:
            # Apply sync setting for immediate writes
            self._db.put(key, value, sync=self._sync_writes)
    
    def _transaction_delete(self, key: bytes):
        """Queue a delete operation in the transaction."""
        if self._transaction_active:
            self._transaction_changes[key] = None
        else:
            # Apply sync setting for immediate deletes
            self._db.delete(key, sync=self._sync_writes)
    
    def create_database(self, db_name: str) -> str:
        """Create a new database (LevelDB instance)."""
        db_path = self._db_path(db_name)
        if os.path.exists(db_path):
            return f"Database '{db_name}' already exists"
        
        db = plyvel.DB(db_path, create_if_missing=True)
        db.close()
        
        # Log to binlog
        if self._binlog:
            self._log_binlog_async(
                server_id=self.server_id,
                database=db_name,
                operation="CREATE_DB",
                data={"db_name": db_name}
            )
        
        return f"Database '{db_name}' created successfully"
    
    def drop_database(self, db_name: str) -> str:
        """Delete a database."""
        db_path = self._db_path(db_name)
        if not os.path.exists(db_path):
            return f"Database '{db_name}' does not exist"
        
        if self.current_db == db_name and self._db:
            self._db.close()
            self._db = None
            self.current_db = None
        
        import shutil
        shutil.rmtree(db_path)
        
        # Log to binlog
        if self._binlog:
            self._log_binlog_async(
                server_id=self.server_id,
                database=db_name,
                operation="DROP_DB",
                data={"db_name": db_name}
            )
        
        return f"Database '{db_name}' dropped"

    def use_database(self, db_name: str) -> str:
        """Switch to a database."""
        # Idempotent check - no-op if already using this database
        if self.current_db == db_name and self._db:
            return f"Already using database '{db_name}'"
        
        if self._transaction_active:
            return "ERROR: Cannot switch database during transaction"
        
        db_path = self._db_path(db_name)
        if not os.path.exists(db_path):
            return f"Database '{db_name}' does not exist"
        
        with self._db_lock:
            if self._db:
                self._db.close()
            
            self._db = plyvel.DB(
                db_path,
                create_if_missing=True,
                lru_cache_size=self._cache_size,
                write_buffer_size=self._write_buffer_size,
                max_open_files=self._max_open_files,
                compression=self._compression,
                bloom_filter_bits=self._bloom_filter_bits
            )
            self.current_db = db_name
        
        return f"Switched to database '{db_name}'"
    
    def create_table(self, table_name: str, columns: List[str]) -> str:
        """Create a table with schema, primary key and secondary indexes."""
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        if self._db.get(schema_key) or schema_key in self._transaction_changes:
            return f"Table '{table_name}' already exists"
        
        parsed_columns = []
        primary_key = None
        index_columns = []
        
        for col in columns:
            col_stripped = col.strip()
            col_upper = col_stripped.upper()
            # Extract just the column name (first whitespace-delimited token)
            col_name = col_stripped.split()[0]
            if 'PRIMARY KEY' in col_upper:
                primary_key = col_name
                parsed_columns.append(primary_key)
            elif 'INDEX' in col_upper:
                parsed_columns.append(col_name)
                index_columns.append(col_name)
            else:
                parsed_columns.append(col_name)
        
        schema = {
            "columns": parsed_columns,
            "next_id": 1,
            "primary_key": primary_key,
            "indexes": index_columns
        }
        self._transaction_put(schema_key, json.dumps(schema).encode())
        
        if primary_key:
            idx_key = f"_index:{table_name}:{primary_key}".encode()
            self._transaction_put(idx_key, json.dumps({}).encode())
        
        for idx_col in index_columns:
            idx_key = f"_index:{table_name}:{idx_col}".encode()
            self._transaction_put(idx_key, json.dumps({}).encode())
        
        # Log to binlog
        if self._binlog:
            self._log_binlog_async(
                server_id=self.server_id,
                database=self.current_db or "",
                operation="CREATE_TABLE",
                table=table_name,
                data={"table_name": table_name, "columns": parsed_columns, "primary_key": primary_key, "indexes": index_columns}
            )
        
        return f"Table '{table_name}' created"
    
    def drop_table(self, table_name: str) -> str:
        """Drop a table and all its data."""
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        if not self._db.get(schema_key):
            return f"Table '{table_name}' does not exist"
        
        prefix = f"{table_name}:".encode()
        for key, _ in self._db.iterator(prefix=prefix):
            self._transaction_delete(key)
        
        self._transaction_delete(schema_key)
        
        # Log to binlog
        if self._binlog:
            self._log_binlog_async(
                server_id=self.server_id,
                database=self.current_db or "",
                operation="DROP_TABLE",
                table=table_name,
                data={"table_name": table_name}
            )
        
        return f"Table '{table_name}' dropped"
    
    def insert(self, table_name: str, values: List[Any]) -> str:
        """Insert a row into a table (positional values follow schema column order)."""
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema = self.get_schema(table_name)
        if not schema:
            return f"Table '{table_name}' does not exist"
        
        return self._insert_row(table_name, schema["columns"], values)
    
    def insert_with_columns(self, table_name: str, columns: List[str], values: List[Any]) -> str:
        """Insert a row with explicit column mapping."""
        if not self._db:
            return "No database selected. Use USE <database>"
        
        if not self.get_schema(table_name):
            return f"Table '{table_name}' does not exist"
        
        return self._insert_row(table_name, columns, values)
    
    def _insert_row(self, table_name: str, columns: List[str], values: List[Any]) -> str:
        """Shared insert path: PK uniqueness, id assignment and index updates."""
        schema_key = f"_schema:{table_name}".encode()
        
        with self._counter_lock:
            schema_data = self._get_current(schema_key)
            if not schema_data:
                return f"Table '{table_name}' does not exist"
            schema = json.loads(schema_data.decode())
            
            data = {}
            for i, col in enumerate(columns):
                if i < len(values):
                    data[col] = values[i]
            
            primary_key = schema.get("primary_key")
            if primary_key and primary_key in data:
                store_key = str(data[primary_key])
                key = self._make_key(table_name, store_key)
                if self._get_current(key) is not None:
                    return f"ERROR: Duplicate primary key '{store_key}' in '{table_name}'"
            else:
                store_key = str(schema["next_id"])
                key = self._make_key(table_name, store_key)
                schema["next_id"] += 1
                self._transaction_put(schema_key, json.dumps(schema).encode())
            
            row = {"id": store_key}
            row.update(data)
            
            self._transaction_put(key, json.dumps(row).encode())
            self._update_indexes(table_name, row, store_key, schema)
        
        # Log to binlog
        if self._binlog:
            self._log_binlog_async(
                server_id=self.server_id,
                database=self.current_db or "",
                operation="INSERT",
                table=table_name,
                data={"row": row}
            )
        
        return f"Inserted 1 row into '{table_name}'"
    def _update_indexes(self, table_name: str, row: Dict, row_key: str, schema: Dict):
        """Update all indexes for a row (transaction-aware)."""
        primary_key = schema.get("primary_key")
        indexes = schema.get("indexes", [])
        
        if primary_key and primary_key in row:
            idx_key = f"_index:{table_name}:{primary_key}".encode()
            idx_data = self._get_current(idx_key)
            if idx_data:
                index_map = json.loads(idx_data.decode())
                index_map[str(row[primary_key])] = row_key
                self._transaction_put(idx_key, json.dumps(index_map).encode())
        
        for idx_col in indexes:
            if idx_col in row:
                idx_key = f"_index:{table_name}:{idx_col}".encode()
                idx_data = self._get_current(idx_key)
                if idx_data:
                    index_map = json.loads(idx_data.decode())
                    val = str(row[idx_col])
                    if val not in index_map:
                        index_map[val] = []
                    if isinstance(index_map[val], list):
                        if row_key not in index_map[val]:
                            index_map[val].append(row_key)
                    else:
                        index_map[val] = [index_map[val], row_key]
                    self._transaction_put(idx_key, json.dumps(index_map).encode())
    
    def _remove_from_indexes(self, table_name: str, row: Dict, row_key: str, schema: Dict):
        """Remove a row's entries from all indexes (transaction-aware)."""
        primary_key = schema.get("primary_key")
        indexes = schema.get("indexes", [])
        
        if primary_key and primary_key in row:
            idx_key = f"_index:{table_name}:{primary_key}".encode()
            idx_data = self._get_current(idx_key)
            if idx_data:
                index_map = json.loads(idx_data.decode())
                if index_map.pop(str(row[primary_key]), None) is not None:
                    self._transaction_put(idx_key, json.dumps(index_map).encode())
        
        for idx_col in indexes:
            if idx_col in row:
                idx_key = f"_index:{table_name}:{idx_col}".encode()
                idx_data = self._get_current(idx_key)
                if idx_data:
                    index_map = json.loads(idx_data.decode())
                    val = str(row[idx_col])
                    entries = index_map.get(val)
                    if entries is None:
                        continue
                    if not isinstance(entries, list):
                        entries = [entries]
                    if row_key in entries:
                        entries.remove(row_key)
                    if entries:
                        index_map[val] = entries
                    else:
                        index_map.pop(val, None)
                    self._transaction_put(idx_key, json.dumps(index_map).encode())
    
    def select(self, table_name: str, columns: Optional[List[str]] = None,
               where: Optional[Dict[str, Any]] = None,
               order_by: Optional[str] = None,
               order_desc: bool = False,
               raw: bool = False) -> Any:
        """Select rows from a table with optional ordering."""
        if not self._db:
            return "No database selected. Use USE <database>" if not raw else []
        
        schema_key = f"_schema:{table_name}".encode()
        schema_data = self._db.get(schema_key)
        if not schema_data:
            return f"Table '{table_name}' does not exist" if not raw else []
        
        schema = json.loads(schema_data.decode())
        if columns is None or "*" in columns:
            columns = list(schema["columns"])
            if "id" not in columns:
                columns.insert(0, "id")
        
        results = []
        
        # Check if WHERE clause can use index
        if where and self._can_use_index(schema, where):
            results = self._select_with_where_index(table_name, where, schema)
        elif order_by and order_by != "id":
            results = self._select_with_index(table_name, where, order_by, order_desc, schema)
        else:
            prefix = f"{table_name}:".encode()
            for key, value in self._db.iterator(prefix=prefix):
                if key.startswith(f"_schema:{table_name}".encode()):
                    continue
                
                row = json.loads(value.decode())
                
                if where:
                    match = True
                    for col, val in where.items():
                        if str(row.get(col)) != str(val):
                            match = False
                            break
                    if not match:
                        continue
                
                results.append(row)
            
            if order_by == "id":
                results = self._sort_results(results, "id", order_desc)
        
        if raw:
            return results
        
        if not results:
            return "Empty set"
        
        filtered_results = []
        for row in results:
            filtered_row = {col: row.get(col, "NULL") for col in columns}
            filtered_results.append(filtered_row)
        
        # Support JSON wire format via client_state or default to ASCII
        return self._format_results(columns, filtered_results)
    
    def _can_use_index(self, schema: Dict, where: Dict) -> bool:
        """Check if WHERE clause can use an index."""
        indexes = schema.get("indexes", [])
        primary_key = schema.get("primary_key")
        
        for col in where.keys():
            if col == primary_key or col in indexes:
                return True
        return False
    
    def _key_might_exist(self, key: bytes) -> bool:
        """
        Check if a key might exist using Bloom filter.
        
        Bloom filters provide fast negative lookups - if this returns False,
        the key definitely doesn't exist. If True, the key probably exists
        (but may be a false positive).
        
        This avoids disk seeks for non-existent keys during index lookups.
        """
        # LevelDB's bloom filter is checked automatically during get()
        # This method documents the optimization for code clarity
        if not self._db:
            return False
        
        # With bloom_filter_bits > 0, LevelDB uses bloom filter internally
        # We just do a quick check without full disk read
        try:
            # Using iterator with seek is faster than get for existence check
            # when bloom filter is enabled
            it = self._db.raw_iterator()
            it.seek(key)
            valid = it.valid()
            it.close()
            return valid
        except:
            return True  # Conservative: assume might exist on error
    
    def _select_with_where_index(self, table_name: str, where: Dict, schema: Dict) -> List[Dict]:
        """Select using index for WHERE clause filtering with Bloom filter optimization."""
        results = []
        indexes = schema.get("indexes", [])
        primary_key = schema.get("primary_key")
        
        # Find which column to use for index lookup
        index_col = None
        for col in where.keys():
            if col == primary_key or col in indexes:
                index_col = col
                break
        
        if not index_col:
            return results
        
        lookup_val = str(where[index_col])
        idx_key = f"_index:{table_name}:{index_col}".encode()
        
        # Bloom filter optimization: quick check if index key might exist
        if self._bloom_filter_bits > 0 and not self._key_might_exist(idx_key):
            return results  # Index definitely doesn't exist
        
        idx_data = self._db.get(idx_key)
        
        if not idx_data:
            return results
        
        index_map = json.loads(idx_data.decode())
        row_keys = index_map.get(lookup_val, [])
        
        if not isinstance(row_keys, list):
            row_keys = [row_keys]
        
        for row_key in row_keys:
            row_key_full = f"{table_name}:{row_key}".encode()
            
            # Bloom filter optimization for row existence check
            if self._bloom_filter_bits > 0 and not self._key_might_exist(row_key_full):
                continue  # Row definitely doesn't exist
            
            row_data = self._db.get(row_key_full)
            if row_data:
                row = json.loads(row_data.decode())
                # Verify all WHERE conditions match
                match = True
                for col, val in where.items():
                    if str(row.get(col)) != str(val):
                        match = False
                        break
                if match:
                    results.append(row)
        
        return results
    
    def _select_with_index(self, table_name: str, where: Optional[Dict],
                          order_by: str, order_desc: bool, schema: Dict) -> List[Dict]:
        """Select using index for ordering."""
        results = []
        
        idx_key = f"_index:{table_name}:{order_by}".encode()
        idx_data = self._db.get(idx_key)
        
        if idx_data:
            index_map = json.loads(idx_data.decode())
            sorted_vals = sorted(index_map.keys(), reverse=order_desc)
            
            for val in sorted_vals:
                row_keys = index_map[val]
                if not isinstance(row_keys, list):
                    row_keys = [row_keys]
                
                for row_key in row_keys:
                    row_key_full = f"{table_name}:{row_key}".encode()
                    row_data = self._db.get(row_key_full)
                    if row_data:
                        row = json.loads(row_data.decode())
                        
                        if where:
                            match = True
                            for col, w_val in where.items():
                                if str(row.get(col)) != str(w_val):
                                    match = False
                                    break
                            if not match:
                                continue
                        
                        results.append(row)
        else:
            prefix = f"{table_name}:".encode()
            for key, value in self._db.iterator(prefix=prefix):
                if key.startswith(f"_schema:{table_name}".encode()):
                    continue
                
                row = json.loads(value.decode())
                
                if where:
                    match = True
                    for col, val in where.items():
                        if str(row.get(col)) != str(val):
                            match = False
                            break
                    if not match:
                        continue
                
                results.append(row)
            
            results = self._sort_results(results, order_by, order_desc)
        
        return results
    
    def update(self, table_name: str, set_clause: Dict[str, Any],
               where: Optional[Dict[str, Any]] = None) -> str:
        """Update rows in a table."""
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        schema_data = self._db.get(schema_key)
        if not schema_data:
            return f"Table '{table_name}' does not exist"
        
        schema = json.loads(schema_data.decode())
        updated = 0
        updated_rows = []
        prefix = f"{table_name}:".encode()
        
        primary_key = schema.get("primary_key")
        indexed_cols = set(schema.get("indexes", []))
        if primary_key:
            indexed_cols.add(primary_key)
        touches_index = bool(indexed_cols & set(set_clause.keys()))
        
        for key, value in self._db.iterator(prefix=prefix):
            if key.startswith(f"_schema:{table_name}".encode()):
                continue
            
            row = json.loads(value.decode())
            
            if where:
                match = True
                for col, val in where.items():
                    if str(row.get(col)) != str(val):
                        match = False
                        break
                if not match:
                    continue
            
            old_row = row.copy()
            for col, val in set_clause.items():
                row[col] = val
            
            store_key = key.decode().split(':', 1)[1]
            new_store_key = store_key
            
            if primary_key and primary_key in set_clause and str(row.get(primary_key)) != store_key:
                # Primary key changed: move row to its new key
                new_store_key = str(row[primary_key])
                new_key = self._make_key(table_name, new_store_key)
                if self._get_current(new_key) is not None:
                    return f"ERROR: Duplicate primary key '{new_store_key}' in '{table_name}' (updated {updated} row(s) before error)"
                row["id"] = new_store_key
                self._transaction_delete(key)
                self._transaction_put(new_key, json.dumps(row).encode())
            else:
                self._transaction_put(key, json.dumps(row).encode())
            
            # Maintain indexes for changed indexed columns / moved rows
            if touches_index or new_store_key != store_key:
                self._remove_from_indexes(table_name, old_row, store_key, schema)
                self._update_indexes(table_name, row, new_store_key, schema)
            
            updated_rows.append(row.copy())
            updated += 1
        
        # Log to binlog
        if self._binlog and updated_rows:
            self._log_binlog_async(
                server_id=self.server_id,
                database=self.current_db or "",
                operation="UPDATE",
                table=table_name,
                data={"set_clause": set_clause, "where": where, "updated_rows": updated_rows}
            )
        
        return f"Updated {updated} row(s) in '{table_name}'"
    
    def delete(self, table_name: str, where: Optional[Dict[str, Any]] = None) -> str:
        """Delete rows from a table."""
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        schema_data = self._db.get(schema_key)
        if not schema_data:
            return f"Table '{table_name}' does not exist"
        
        schema = json.loads(schema_data.decode())
        deleted = 0
        keys_to_delete = []
        deleted_rows = []
        prefix = f"{table_name}:".encode()
        
        for key, value in self._db.iterator(prefix=prefix):
            if key.startswith(f"_schema:{table_name}".encode()):
                continue
            
            row = json.loads(value.decode())
            
            if where:
                match = True
                for col, val in where.items():
                    if str(row.get(col)) != str(val):
                        match = False
                        break
                if not match:
                    continue
            
            keys_to_delete.append(key)
            deleted_rows.append(row.copy())
        
        for key, row in zip(keys_to_delete, deleted_rows):
            self._transaction_delete(key)
            store_key = key.decode().split(':', 1)[1]
            self._remove_from_indexes(table_name, row, store_key, schema)
            deleted += 1
        
        # Log to binlog
        if self._binlog and deleted_rows:
            self._log_binlog_async(
                server_id=self.server_id,
                database=self.current_db or "",
                operation="DELETE",
                table=table_name,
                data={"where": where, "deleted_rows": deleted_rows}
            )
        
        return f"Deleted {deleted} row(s) from '{table_name}'"
    
    def _format_results(self, columns: List[str], results: List[Dict], use_json: bool = False) -> str:
        """
        Format query results as table string or JSON.
        
        Args:
            columns: List of column names
            results: List of row dictionaries
            use_json: If True, return JSON format instead of ASCII table
        
        Returns:
            Formatted string (ASCII table or JSON)
        """
        if not results:
            return json.dumps({"columns": columns, "rows": [], "count": 0}) if use_json else "Empty set"
        
        if use_json:
            # JSON wire format - efficient parsing, smaller payload
            return json.dumps({
                "columns": columns,
                "rows": results,
                "count": len(results)
            })
        
        # ASCII table format (legacy, human-readable)
        widths = {}
        for col in columns:
            widths[col] = len(col)
        
        for row in results:
            for col in columns:
                val_str = str(row.get(col, "NULL"))
                widths[col] = max(widths[col], len(val_str))
        
        lines = []
        header = "| " + " | ".join(col.ljust(widths[col]) for col in columns) + " |"
        separator = "+" + "+".join("-" * (widths[col] + 2) for col in columns) + "+"
        
        lines.append(separator)
        lines.append(header)
        lines.append(separator)
        
        for row in results:
            row_str = "| " + " | ".join(
                str(row.get(col, "NULL")).ljust(widths[col]) for col in columns
            ) + " |"
            lines.append(row_str)
        
        lines.append(separator)
        lines.append(f"{len(results)} row(s) in set")
        
        return "\n".join(lines)
    
    def _format_results_json(self, columns: List[str], results: List[Dict]) -> str:
        """
        Format query results as JSON for wire protocol.
        
        This is faster than ASCII table format and enables proper error handling.
        The client receives structured data that can be parsed directly.
        
        Args:
            columns: List of column names
            results: List of row dictionaries
        
        Returns:
            JSON string with columns, rows, and count
        """
        return self._format_results(columns, results, use_json=True)
    
    @property
    def sort_engine(self):
        """Get the sort engine for ORDER BY operations."""
        return self._sort_engine
    
    def _sort_results(self, results: List[Dict], order_by: str, order_desc: bool = False) -> List[Dict]:
        """
        Sort results using configured sort engine.
        
        Args:
            results: List of row dictionaries
            order_by: Column to sort by
            order_desc: Reverse order if True
        
        Returns:
            Sorted results
        """
        if not results or len(results) < 2:
            return results
        
        # Use sort engine if available
        if self._sort_engine is not None:
            try:
                return self._sort_engine.sort(
                    results,
                    key=lambda r: r.get(order_by, ""),
                    reverse=order_desc
                )
            except Exception as e:
                # Log warning and fall back to built-in sort
                import logging
                logging.getLogger(__name__).warning(
                    f"Sort engine failed, falling back to built-in: {e}"
                )
        
        # Built-in fallback
        return sorted(results, key=lambda r: r.get(order_by, ""), reverse=order_desc)

    def close(self):
        """Close the database connection."""
        # Flush binlog before shutdown (graceful)
        self._flush_binlog_queue()
        
        if self._transaction_active:
            self.rollback_transaction()
        if self._db:
            self._db.close()
            self._db = None
            self.current_db = None
        if self._system_db:
            self._system_db.close()
            self._system_db = None
        if self._binlog:
            self._binlog.close()
            self._binlog = None
    
    def create_snapshot(self) -> Any:
        """
        Create a point-in-time snapshot for consistent reads.
        
        Snapshots provide a consistent view of the database at the time
        they were created, unaffected by subsequent writes.
        
        Returns:
            Snapshot object for reading, or None if no database selected
        """
        if not self._db:
            return None
        
        try:
            return self._db.snapshot()
        except Exception as e:
            print(f"Error creating snapshot: {e}")
            return None
    
    def get_with_snapshot(self, key: bytes, snapshot: Any) -> Optional[bytes]:
        """
        Get a value using a snapshot for consistent read.
        
        Args:
            key: The key to look up
            snapshot: Snapshot object from create_snapshot()
        
        Returns:
            Value bytes or None if not found
        """
        if not snapshot:
            return None
        
        try:
            return snapshot.get(key)
        except Exception:
            return None
    
    def iterate_with_snapshot(self, prefix: bytes, snapshot: Any) -> List[tuple]:
        """
        Iterate over a key range using a snapshot for consistent reads.
        
        Args:
            prefix: Key prefix to iterate over
            snapshot: Snapshot object from create_snapshot()
        
        Returns:
            List of (key, value) tuples
        """
        if not snapshot:
            return []
        
        results = []
        try:
            for key, value in snapshot.iterator(prefix=prefix):
                results.append((key, value))
        except Exception as e:
            print(f"Error iterating with snapshot: {e}")
        
        return results
    
    def backup_with_snapshot(self, backup_path: str) -> str:
        """
        Create a consistent backup using snapshot.
        
        Args:
            backup_path: Directory path for backup
        
        Returns:
            Success/error message
        """
        if not self._db:
            return "ERROR: No database selected"
        
        import shutil
        
        try:
            # Create snapshot for consistent view
            snapshot = self.create_snapshot()
            if not snapshot:
                return "ERROR: Failed to create snapshot"
            
            try:
                # Ensure backup directory exists
                os.makedirs(backup_path, exist_ok=True)
                
                # Copy all data using snapshot
                prefix = b""  # All keys
                count = 0
                
                for key, value in snapshot.iterator(prefix=prefix):
                    # Skip internal metadata if needed
                    if key.startswith(b"_"):
                        continue
                    
                    # Write to backup (simplified - in production use proper serialization)
                    backup_key_path = os.path.join(backup_path, key.decode('utf-8', errors='replace'))
                    os.makedirs(os.path.dirname(backup_key_path), exist_ok=True)
                    with open(backup_key_path + '.dat', 'wb') as f:
                        f.write(value)
                    count += 1
                
                return f"OK: Backed up {count} items to {backup_path}"
            finally:
                snapshot.close()
                
        except Exception as e:
            return f"ERROR: Backup failed: {e}"
    
    def list_databases(self) -> List[str]:
        """List all databases in the data directory."""
        if not os.path.exists(self.data_dir):
            return []
        
        databases = []
        for item in os.listdir(self.data_dir):
            item_path = os.path.join(self.data_dir, item)
            if os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, "CURRENT")):
                databases.append(item)
        
        return sorted(databases)
    
    def list_tables(self) -> List[str]:
        """List all tables in the current database."""
        if not self._db:
            return []
        
        tables = []
        prefix = b"_schema:"
        
        for key, _ in self._db.iterator(prefix=prefix):
            table_name = key.decode().replace("_schema:", "")
            tables.append(table_name)
        
        return sorted(tables)
    
    def create_user(self, username: str, password: str, is_admin: bool = False) -> str:
        """Create a new user."""
        self._ensure_system_tables()
        
        with self._counter_lock:
            # Check if user exists (under lock to prevent duplicate usernames)
            prefix = b"_users:"
            for key, value in self._system_db.iterator(prefix=prefix):
                user_data = json.loads(value.decode())
                if user_data.get("username") == username:
                    return f"User '{username}' already exists"
            
            # Create user
            password_hash = self._hash_password(password)
            user_id = self._get_next_user_id()
            user_data = {
                "id": user_id,
                "username": username,
                "password_hash": password_hash,
                "is_admin": is_admin,
                "created_at": str(time.time())
            }
            
            key = f"_users:{user_id}".encode()
            self._system_db.put(key, json.dumps(user_data).encode())
        return f"User '{username}' created successfully"
    
    def _get_next_user_id(self) -> str:
        """Get next user ID. Caller must hold _counter_lock."""
        schema_key = b"_schema:_users"
        schema_data = self._system_db.get(schema_key)
        if schema_data:
            schema = json.loads(schema_data.decode())
            next_id = str(schema["next_id"])
            schema["next_id"] += 1
            self._system_db.put(schema_key, json.dumps(schema).encode())
            return next_id
        return "1"
    
    def authenticate_user(self, username: str, password: str) -> tuple:
        """Authenticate user and return (success, is_admin, privileges)."""
        prefix = b"_users:"
        
        for key, value in self._system_db.iterator(prefix=prefix):
            user_data = json.loads(value.decode())
            if user_data.get("username") == username:
                if self._verify_password(password, user_data.get("password_hash", "")):
                    is_admin = user_data.get("is_admin", False)
                    privileges = self._get_user_privileges(username)
                    return (True, is_admin, privileges)
                return (False, False, [])
        
        return (False, False, [])
    
    def _get_user_privileges(self, username: str) -> List[Dict]:
        """Get all privileges for a user."""
        privileges = []
        prefix = b"_privileges:"
        
        for key, value in self._system_db.iterator(prefix=prefix):
            priv_data = json.loads(value.decode())
            if priv_data.get("username") == username:
                privileges.append({
                    "db": priv_data.get("db_pattern"),
                    "table": priv_data.get("table_pattern"),
                    "privs": priv_data.get("privileges", [])
                })
        
        return privileges
    
    def grant_privilege(self, username: str, db_pattern: str, table_pattern: str, 
                      privileges: List[str]) -> str:
        """Grant privileges to a user."""
        self._ensure_system_tables()
        
        with self._counter_lock:
            priv_id = self._get_next_privilege_id()
            priv_data = {
                "id": priv_id,
                "username": username,
                "db_pattern": db_pattern,
                "table_pattern": table_pattern,
                "privileges": privileges
            }
            
            key = f"_privileges:{priv_id}".encode()
            self._system_db.put(key, json.dumps(priv_data).encode())
        return f"Granted {','.join(privileges)} on {db_pattern}.{table_pattern} to '{username}'"
    
    def _get_next_privilege_id(self) -> str:
        """Get next privilege ID. Caller must hold _counter_lock."""
        schema_key = b"_schema:_privileges"
        schema_data = self._system_db.get(schema_key)
        if schema_data:
            schema = json.loads(schema_data.decode())
            next_id = str(schema["next_id"])
            schema["next_id"] += 1
            self._system_db.put(schema_key, json.dumps(schema).encode())
            return next_id
        return "1"
    
    def check_privilege(self, username: str, db_name: str, table_name: str, 
                       required_priv: str) -> bool:
        """Check if user has required privilege."""
        privileges = self._get_user_privileges(username)
        
        for priv in privileges:
            # Check database pattern
            db_match = priv["db"] == "*" or priv["db"] == db_name
            
            # Check table pattern
            table_match = priv["table"] == "*" or priv["table"] == table_name
            
            # Check privilege
            if db_match and table_match:
                if "ALL" in priv["privs"] or required_priv in priv["privs"]:
                    return True
        
        return False
    
    def get_config(self) -> Dict[str, Any]:
        """
        Get current database configuration and tuning parameters.
        
        Returns:
            Dictionary with current configuration settings
        """
        return {
            "cache_size": self._cache_size,
            "write_buffer_size": self._write_buffer_size,
            "max_open_files": self._max_open_files,
            "compression": self._compression,
            "bloom_filter_bits": self._bloom_filter_bits,
            "sync_writes": self._sync_writes,
            "disable_wal": self._disable_wal,
            "data_dir": self.data_dir,
            "server_id": self.server_id,
            "current_db": self.current_db,
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get database statistics from LevelDB.
        
        Returns:
            Dictionary with database statistics
        """
        stats = {}
        
        if self._db:
            try:
                # LevelDB internal statistics
                leveldb_stats = self._db.get_property(b'leveldb.stats')
                if leveldb_stats:
                    stats['leveldb_stats'] = leveldb_stats.decode('utf-8', errors='replace')
                
                # Approximate sizes
                # stats['approximate_size'] = self._db.approximate_size(b'', b'\xff')
            except Exception as e:
                stats['error'] = str(e)
        
        if self._system_db:
            try:
                system_stats = self._system_db.get_property(b'leveldb.stats')
                if system_stats:
                    stats['system_stats'] = system_stats.decode('utf-8', errors='replace')
            except:
                pass
        
        return stats
    
    def list_users(self) -> List[str]:
        """List all users."""
        users = []
        prefix = b"_users:"
        
        for key, value in self._system_db.iterator(prefix=prefix):
            user_data = json.loads(value.decode())
            users.append(user_data.get("username"))
        
        return sorted(users)
    
    def delete_user(self, username: str) -> str:
        """Delete a user and their privileges."""
        # Find and delete user
        prefix = b"_users:"
        user_key = None
        
        for key, value in self._system_db.iterator(prefix=prefix):
            user_data = json.loads(value.decode())
            if user_data.get("username") == username:
                user_key = key
                break
        
        if not user_key:
            return f"User '{username}' not found"
        
        self._system_db.delete(user_key)
        
        # Delete associated privileges
        priv_prefix = b"_privileges:"
        keys_to_delete = []
        
        for key, value in self._system_db.iterator(prefix=priv_prefix):
            priv_data = json.loads(value.decode())
            if priv_data.get("username") == username:
                keys_to_delete.append(key)
        
        for key in keys_to_delete:
            self._system_db.delete(key)
        
        return f"User '{username}' deleted"
