
"""LevelDB database layer with CRUD operations, user management and privileges."""

import os
import json
import hashlib
import secrets
import time
import threading
import plyvel
from typing import Optional, Dict, Any, List
from binlog import Binlog



    def __init__(self, data_dir: str = "data", server_id: int = 1):
        self.data_dir = data_dir
        self.db_path = data_dir
        self.server_id = server_id
        self.current_db: Optional[str] = None
        self._db: Optional[plyvel.DB] = None
        self._system_db: Optional[plyvel.DB] = None  # For users/privileges
        self._binlog: Optional[Binlog] = None
        self._transaction_active = False
        self._transaction_changes: Dict[bytes, Optional[bytes]] = {}
        self._transaction_start_time: float = 0
        self._db_lock = threading.Lock()  # Thread safety for database switching
        self._ensure_data_dir()
        self._open_system_db()
        self._open_binlog()
        self._ensure_data_dir()
        self._open_system_db()
        self._open_binlog()
    
    def _ensure_data_dir(self):
        """Ensure data directory exists."""
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
    
    def _open_system_db(self):
        """Open system database for users and privileges."""
        system_db_path = os.path.join(self.data_dir, "_system")
        self._system_db = plyvel.DB(system_db_path, create_if_missing=True)
    
    def _open_binlog(self):
        """Open binary log for replication."""
        self._binlog = Binlog(self.data_dir)
    
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
    
    # Transaction support
    def begin_transaction(self) -> str:
        """Begin a new transaction."""
        if not self._db:
            return "ERROR: No database selected"
        if self._transaction_active:
            return "ERROR: Transaction already active"
        
        self._transaction_active = True
        self._transaction_changes = {}
        self._transaction_start_time = time.time()
        return "OK: Transaction started"
    
    def commit_transaction(self) -> str:
        """Commit the current transaction."""
        if not self._transaction_active:
            return "ERROR: No active transaction"
        
        try:
            # Apply all changes
            for key, value in self._transaction_changes.items():
                if value is None:
                    self._db.delete(key)
                else:
                    self._db.put(key, value)
            
            duration = time.time() - self._transaction_start_time
            changes = len(self._transaction_changes)
            self._transaction_active = False
            self._transaction_changes = {}
            
            return f"OK: Committed {changes} change(s) in {duration:.3f}s"
        except Exception as e:
            return f"ERROR: Commit failed: {e}"
    
    def rollback_transaction(self) -> str:
        """Rollback the current transaction."""
        if not self._transaction_active:
            return "ERROR: No active transaction"
        
        changes = len(self._transaction_changes)
        self._transaction_active = False
        self._transaction_changes = {}
        
        return f"OK: Rolled back {changes} change(s)"
    
    def _transaction_put(self, key: bytes, value: bytes):
        """Queue a put operation in the transaction."""
        if self._transaction_active:
            self._transaction_changes[key] = value
        else:
            self._db.put(key, value)
    
    def _transaction_delete(self, key: bytes):
        """Queue a delete operation in the transaction."""
        if self._transaction_active:
            self._transaction_changes[key] = None
        else:
            self._db.delete(key)
    
    def create_database(self, db_name: str) -> str:
        """Create a new database (LevelDB instance)."""
        db_path = self._db_path(db_name)
        if os.path.exists(db_path):
            return f"Database '{db_name}' already exists"
        
        db = plyvel.DB(db_path, create_if_missing=True)
        db.close()
        
        # Log to binlog
        if self._binlog:
            self._binlog.write_entry(
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
            self._binlog.write_entry(
                server_id=self.server_id,
                database=db_name,
                operation="DROP_DB",
                data={"db_name": db_name}
            )



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
            
            self._db = plyvel.DB(db_path, create_if_missing=True)
            self.current_db = db_name
        
        return f"Switched to database '{db_name}'"
        
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
            self._binlog.write_entry(
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
            self._binlog.write_entry(
                server_id=self.server_id,
                database=self.current_db or "",
                operation="DROP_TABLE",
                table=table_name,
                data={"table_name": table_name}
            )
        
        return f"Table '{table_name}' dropped"
    
    def insert(self, table_name: str, values: List[Any]) -> str:
        """Insert a row into a table."""
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        schema_data = self._db.get(schema_key)
        if not schema_data:
            return f"Table '{table_name}' does not exist"
        
        schema = json.loads(schema_data.decode())
        row_id = str(schema["next_id"])
        
        row = {"id": row_id}
        for i, col in enumerate(schema["columns"]):
            if i < len(values):
                row[col] = values[i]
        
        primary_key = schema.get("primary_key")
        if primary_key and primary_key in row:
            store_key = str(row[primary_key])
        else:
            store_key = row_id
        
        key = self._make_key(table_name, store_key)
        self._transaction_put(key, json.dumps(row).encode())
        
        self._update_indexes(table_name, row, store_key, schema)
        
        if not primary_key:
            schema["next_id"] += 1
            self._transaction_put(schema_key, json.dumps(schema).encode())
        
        # Log to binlog
        if self._binlog:
            self._binlog.write_entry(
                server_id=self.server_id,
                database=self.current_db or "",
                operation="INSERT",
                table=table_name,
                data={"row": row}
            )
        
        return f"Inserted 1 row into '{table_name}'"
    
    def _update_indexes(self, table_name: str, row: Dict, row_key: str, schema: Dict):
        """Update all indexes for a row."""
        primary_key = schema.get("primary_key")
        indexes = schema.get("indexes", [])
        
        if primary_key and primary_key in row:
            idx_key = f"_index:{table_name}:{primary_key}".encode()
            idx_data = self._db.get(idx_key)
            if idx_data:
                index_map = json.loads(idx_data.decode())
                index_map[str(row[primary_key])] = row_key
                self._transaction_put(idx_key, json.dumps(index_map).encode())
        
        for idx_col in indexes:
            if idx_col in row:
                idx_key = f"_index:{table_name}:{idx_col}".encode()
                idx_data = self._db.get(idx_key)
                if idx_data:
                    index_map = json.loads(idx_data.decode())
                    val = str(row[idx_col])
                    if val not in index_map:
                        index_map[val] = []
                    if isinstance(index_map[val], list):
                        index_map[val].append(row_key)
                    else:
                        index_map[val] = [index_map[val], row_key]
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
        
        if order_by and order_by != "id":
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
                results.sort(key=lambda r: r.get("id", ""), reverse=order_desc)
        
        if raw:
            return results
        
        if not results:
            return "Empty set"
        
        filtered_results = []
        for row in results:
            filtered_row = {col: row.get(col, "NULL") for col in columns}
            filtered_results.append(filtered_row)
        
        return self._format_results(columns, filtered_results)
    
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
            
            results.sort(key=lambda r: r.get(order_by, ""), reverse=order_desc)
        
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
            
            old_key_val = None
            primary_key = schema.get("primary_key")
            if primary_key and primary_key in set_clause:
                old_key_val = row.get(primary_key)
            
            for col, val in set_clause.items():
                row[col] = val
            
            self._transaction_put(key, json.dumps(row).encode())
            
            if old_key_val is not None and primary_key:
                self._update_indexes(table_name, row, str(row[primary_key]), schema)
            
            updated_rows.append(row.copy())
            updated += 1
        
        # Log to binlog
        if self._binlog and updated_rows:
            self._binlog.write_entry(
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
        
        for key in keys_to_delete:
            self._transaction_delete(key)
            deleted += 1
        
        # Log to binlog
        if self._binlog and deleted_rows:
            self._binlog.write_entry(
                server_id=self.server_id,
                database=self.current_db or "",
                operation="DELETE",
                table=table_name,
                data={"where": where, "deleted_rows": deleted_rows}
            )
        
        return f"Deleted {deleted} row(s) from '{table_name}'"
    
    def _format_results(self, columns: List[str], results: List[Dict]) -> str:
        """Format query results as a table string."""
        if not results:
            return "Empty set"
        
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
    
    def close(self):
        """Close the database connection."""
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
        
        # Check if user exists
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
        """Get next user ID."""
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
        """Get next privilege ID."""
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
