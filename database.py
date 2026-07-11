"""LevelDB database layer with CRUD operations, user management and privileges."""

import os
import json
import hashlib
import secrets
import time
import re
import plyvel
from typing import Optional, Dict, Any, List, Tuple
from binlog import Binlog
from json_functions import validate_json, parse_json, json_extract, json_extract_text


class Database:
    """Wrapper for LevelDB providing MySQL-like database operations with auth."""
    
    def __init__(self, data_dir: str, server_id: int = 1):
        self.data_dir = data_dir
        self.server_id = server_id
        self._db = None
        self.current_db = None
        self._transaction_active = False
        self._transaction_changes = {}
        self._transaction_start_time = None
        self._system_db = None
        self._binlog = None
        
        # Initialize
        self._open_system_db()
        self._open_binlog()
    
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
        
        return f"Database '{db_name}' dropped successfully"
    
    def use_database(self, db_name: str) -> str:
        """Switch to a database."""
        if self._transaction_active:
            return "ERROR: Cannot switch database during transaction"
        
        db_path = self._db_path(db_name)
        if not os.path.exists(db_path):
            return f"Database '{db_name}' does not exist"
        
        if self._db:
            self._db.close()
        
        self._db = plyvel.DB(db_path, create_if_missing=True)
        self.current_db = db_name
        return f"Switched to database '{db_name}'"
    
    def create_table(self, table_name: str, columns: List[Dict[str, Any]]) -> str:
        """
        Create a table with support for constraints (FK, UNIQUE, CHECK, etc.).
        
        Args:
            table_name: Name of the table
            columns: List of column definitions from parser (can include constraints)
        """
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        if self._db.get(schema_key):
            return f"Table '{table_name}' already exists"
        
        parsed_columns = []
        column_types = {}  # Store column types for JSON validation
        primary_key = None
        index_columns = []
        foreign_keys = []
        unique_constraints = []
        check_constraints = []
        
        for col_info in columns:
            # Handle constraint definitions
            if isinstance(col_info, dict) and 'constraint_type' in col_info:
                constraint_type = col_info['constraint_type']
                
                if constraint_type == 'PRIMARY_KEY':
                    primary_key = col_info['column']
                elif constraint_type == 'FOREIGN_KEY':
                    foreign_keys.append({
                        'column': col_info['column'],
                        'references_table': col_info['references_table'],
                        'references_column': col_info['references_column'],
                        'on_delete': col_info.get('on_delete', 'RESTRICT'),
                        'on_update': col_info.get('on_update', 'RESTRICT')
                    })
                elif constraint_type == 'UNIQUE':
                    unique_constraints.append(col_info['columns'])
                elif constraint_type == 'CHECK':
                    check_constraints.append(col_info['expression'])
                continue
            
            # Regular column definition
            col_name = col_info.get('name')
            if col_name:
                parsed_columns.append(col_name)
                column_types[col_name] = col_info.get('type', 'TEXT')
                
                # Handle inline constraints
                if col_info.get('primary_key'):
                    primary_key = col_name
                
                if col_info.get('index'):
                    index_columns.append(col_name)
                
                if col_info.get('unique'):
                    # Add to unique constraints (single column)
                    unique_constraints.append([col_name])
                
                # Handle inline foreign key
                fk_info = col_info.get('foreign_key')
                if fk_info and fk_info.get('references_table'):
                    foreign_keys.append({
                        'column': col_name,
                        'references_table': fk_info['references_table'],
                        'references_column': fk_info['references_column'],
                        'on_delete': fk_info.get('on_delete', 'RESTRICT'),
                        'on_update': fk_info.get('on_update', 'RESTRICT')
                    })
                
                # Handle inline check
                check_info = col_info.get('check')
                if check_info:
                    if isinstance(check_info, dict):
                        check_constraints.append(check_info.get('expression', ''))
                    else:
                        check_constraints.append(str(check_info))
        
        schema = {
            "columns": parsed_columns,
            "column_types": column_types,
            "next_id": 1,
            "primary_key": primary_key,
            "indexes": index_columns,
            "foreign_keys": foreign_keys,
            "unique_constraints": unique_constraints,
            "check_constraints": check_constraints
        }
        self._transaction_put(schema_key, json.dumps(schema).encode())
        
        # Create primary key index
        if primary_key:
            idx_key = f"_index:{table_name}:{primary_key}".encode()
            self._transaction_put(idx_key, json.dumps({}).encode())
        
        # Create other indexes
        for idx_col in index_columns:
            idx_key = f"_index:{table_name}:{idx_col}".encode()
            self._transaction_put(idx_key, json.dumps({}).encode())
        
        # Create unique indexes
        for i, unique_cols in enumerate(unique_constraints):
            idx_key = f"_unique_index:{table_name}:{':'.join(unique_cols)}".encode()
            self._transaction_put(idx_key, json.dumps({}).encode())
        
        # Log to binlog
        if self._binlog:
            self._binlog.write_entry(
                server_id=self.server_id,
                database=self.current_db or "",
                operation="CREATE_TABLE",
                table=table_name,
                data={
                    "table_name": table_name,
                    "columns": parsed_columns,
                    "primary_key": primary_key,
                    "indexes": index_columns,
                    "foreign_keys": foreign_keys,
                    "unique_constraints": unique_constraints,
                    "check_constraints": check_constraints
                }
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
    
    # ALTER TABLE operations
    def alter_add_column(self, table_name: str, column_def: Dict[str, Any]) -> str:
        """
        Add a column to an existing table.
        
        Args:
            table_name: Name of the table
            column_def: Column definition from parser
        
        Returns:
            Success or error message
        """
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        schema_data = self._db.get(schema_key)
        if not schema_data:
            return f"Table '{table_name}' does not exist"
        
        schema = json.loads(schema_data.decode())
        
        col_name = column_def.get('name')
        if not col_name:
            return "ERROR: Column name required"
        
        if col_name in schema["columns"]:
            return f"ERROR: Column '{col_name}' already exists"
        
        # Add column to schema
        schema["columns"].append(col_name)
        schema["column_types"][col_name] = column_def.get('type', 'TEXT')
        
        # Handle constraints
        if column_def.get('primary_key'):
            schema["primary_key"] = col_name
        
        if column_def.get('index'):
            if col_name not in schema.get("indexes", []):
                schema.setdefault("indexes", []).append(col_name)
        
        if column_def.get('unique'):
            schema.setdefault("unique_constraints", []).append([col_name])
        
        if column_def.get('check'):
            check_expr = column_def['check']
            if isinstance(check_expr, dict):
                schema.setdefault("check_constraints", []).append(check_expr.get('expression', ''))
            else:
                schema.setdefault("check_constraints", []).append(str(check_expr))
        
        if column_def.get('foreign_key'):
            schema.setdefault("foreign_keys", []).append({
                'column': col_name,
                **column_def['foreign_key']
            })
        
        # Update existing rows with NULL for new column
        prefix = f"{table_name}:".encode()
        for key, value in self._db.iterator(prefix=prefix):
            if key.startswith(f"_schema:{table_name}".encode()):
                continue
            
            row = json.loads(value.decode())
            row[col_name] = None  # Default to NULL
            self._transaction_put(key, json.dumps(row).encode())
        
        self._transaction_put(schema_key, json.dumps(schema).encode())
        
        # Create index if needed
        if column_def.get('index'):
            idx_key = f"_index:{table_name}:{col_name}".encode()
            self._transaction_put(idx_key, json.dumps({}).encode())
        
        return f"Column '{col_name}' added to '{table_name}'"
    
    def alter_drop_column(self, table_name: str, column_name: str, cascade: bool = False) -> str:
        """
        Drop a column from a table.
        
        Args:
            table_name: Name of the table
            column_name: Name of the column to drop
            cascade: Whether to cascade drop dependent objects
        
        Returns:
            Success or error message
        """
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        schema_data = self._db.get(schema_key)
        if not schema_data:
            return f"Table '{table_name}' does not exist"
        
        schema = json.loads(schema_data.decode())
        
        if column_name not in schema["columns"]:
            return f"ERROR: Column '{column_name}' does not exist"
        
        # Check if column is primary key
        if schema.get("primary_key") == column_name and not cascade:
            return f"ERROR: Cannot drop primary key column '{column_name}' without CASCADE"
        
        # Check for foreign key references
        foreign_keys = schema.get("foreign_keys", [])
        for fk in foreign_keys:
            if fk.get('column') == column_name and not cascade:
                return f"ERROR: Cannot drop column '{column_name}' with foreign key constraint without CASCADE"
        
        # Check for unique constraints
        unique_constraints = schema.get("unique_constraints", [])
        for i, unique_cols in enumerate(unique_constraints):
            if column_name in unique_cols:
                if not cascade:
                    return f"ERROR: Cannot drop column '{column_name}' with unique constraint without CASCADE"
                # Remove the constraint
                schema["unique_constraints"].pop(i)
        
        # Check for CHECK constraints
        check_constraints = schema.get("check_constraints", [])
        new_checks = []
        for check_expr in check_constraints:
            if column_name.lower() in check_expr.lower() and not cascade:
                return f"ERROR: Cannot drop column '{column_name}' with CHECK constraint without CASCADE"
            elif column_name.lower() not in check_expr.lower():
                new_checks.append(check_expr)
        schema["check_constraints"] = new_checks
        
        # Check for indexes
        indexes = schema.get("indexes", [])
        if column_name in indexes:
            if cascade:
                schema["indexes"].remove(column_name)
                idx_key = f"_index:{table_name}:{column_name}".encode()
                self._transaction_delete(idx_key)
            else:
                return f"ERROR: Cannot drop indexed column '{column_name}' without CASCADE"
        
        # Remove column from schema
        schema["columns"].remove(column_name)
        if column_name in schema["column_types"]:
            del schema["column_types"][column_name]
        
        # Remove from foreign keys
        schema["foreign_keys"] = [fk for fk in foreign_keys if fk.get('column') != column_name]
        
        # Update existing rows
        prefix = f"{table_name}:".encode()
        for key, value in self._db.iterator(prefix=prefix):
            if key.startswith(f"_schema:{table_name}".encode()):
                continue
            
            row = json.loads(value.decode())
            if column_name in row:
                del row[column_name]
            self._transaction_put(key, json.dumps(row).encode())
        
        self._transaction_put(schema_key, json.dumps(schema).encode())
        
        return f"Column '{column_name}' dropped from '{table_name}'"
    
    def alter_modify_column(self, table_name: str, column_name: str, new_type: str, constraints: str = "") -> str:
        """
        Modify column type and constraints.
        
        Args:
            table_name: Name of the table
            column_name: Name of the column
            new_type: New data type
            constraints: Additional constraints
        
        Returns:
            Success or error message
        """
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        schema_data = self._db.get(schema_key)
        if not schema_data:
            return f"Table '{table_name}' does not exist"
        
        schema = json.loads(schema_data.decode())
        
        if column_name not in schema["columns"]:
            return f"ERROR: Column '{column_name}' does not exist"
        
        old_type = schema["column_types"].get(column_name, "TEXT")
        
        # Validate type conversion
        prefix = f"{table_name}:".encode()
        for key, value in self._db.iterator(prefix=prefix):
            if key.startswith(f"_schema:{table_name}".encode()):
                continue
            
            row = json.loads(value.decode())
            if column_name in row and row[column_name] is not None:
                val = row[column_name]
                try:
                    if new_type.upper() == 'INT':
                        int(val)
                    elif new_type.upper() == 'FLOAT':
                        float(val)
                    elif new_type.upper() == 'TEXT':
                        str(val)
                except (ValueError, TypeError):
                    return f"ERROR: Cannot convert value '{val}' to {new_type}"
        
        # Update type
        schema["column_types"][column_name] = new_type
        
        # Parse additional constraints
        if constraints:
            cons_upper = constraints.upper()
            if 'NOT NULL' in cons_upper:
                # Check for NULL values
                for key, value in self._db.iterator(prefix=prefix):
                    if key.startswith(f"_schema:{table_name}".encode()):
                        continue
                    row = json.loads(value.decode())
                    if column_name in row and row[column_name] is None:
                        return f"ERROR: Cannot set NOT NULL - column '{column_name}' contains NULL values"
        
        self._transaction_put(schema_key, json.dumps(schema).encode())
        
        return f"Column '{column_name}' modified to type {new_type}"
    
    def alter_rename_column(self, table_name: str, old_name: str, new_name: str) -> str:
        """
        Rename a column.
        
        Args:
            table_name: Name of the table
            old_name: Current column name
            new_name: New column name
        
        Returns:
            Success or error message
        """
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        schema_data = self._db.get(schema_key)
        if not schema_data:
            return f"Table '{table_name}' does not exist"
        
        schema = json.loads(schema_data.decode())
        
        if old_name not in schema["columns"]:
            return f"ERROR: Column '{old_name}' does not exist"
        
        if new_name in schema["columns"]:
            return f"ERROR: Column '{new_name}' already exists"
        
        # Rename in columns list
        idx = schema["columns"].index(old_name)
        schema["columns"][idx] = new_name
        
        # Rename in column_types
        if old_name in schema["column_types"]:
            schema["column_types"][new_name] = schema["column_types"].pop(old_name)
        
        # Rename in primary key
        if schema.get("primary_key") == old_name:
            schema["primary_key"] = new_name
        
        # Rename in indexes
        if old_name in schema.get("indexes", []):
            schema["indexes"].remove(old_name)
            schema["indexes"].append(new_name)
        
        # Rename in unique constraints
        for i, unique_cols in enumerate(schema.get("unique_constraints", [])):
            if old_name in unique_cols:
                schema["unique_constraints"][i] = [new_name if c == old_name else c for c in unique_cols]
        
        # Rename in foreign keys
        for fk in schema.get("foreign_keys", []):
            if fk.get('column') == old_name:
                fk['column'] = new_name
        
        # Rename in CHECK constraints
        for i, check_expr in enumerate(schema.get("check_constraints", [])):
            schema["check_constraints"][i] = check_expr.replace(old_name, new_name)
        
        # Rename in CHECK constraints
        for i, check_expr in enumerate(schema.get("check_constraints", [])):
            schema["check_constraints"][i] = check_expr.replace(old_name, new_name)
        
        # Update existing rows
        prefix = f"{table_name}:".encode()
        for key, value in self._db.iterator(prefix=prefix):
            if key.startswith(f"_schema:{table_name}".encode()):
                continue
            
            row = json.loads(value.decode())
            if old_name in row:
                row[new_name] = row.pop(old_name)
            self._transaction_put(key, json.dumps(row).encode())
        
        # Rename index
        old_idx_key = f"_index:{table_name}:{old_name}".encode()
        new_idx_key = f"_index:{table_name}:{new_name}".encode()
        idx_data = self._db.get(old_idx_key)
        if idx_data:
            self._transaction_delete(old_idx_key)
            self._transaction_put(new_idx_key, idx_data)
        
        self._transaction_put(schema_key, json.dumps(schema).encode())
        
        return f"Column '{old_name}' renamed to '{new_name}'"
    
    def alter_add_index(self, table_name: str, columns: List[str]) -> str:
        """
        Add an index to a table.
        
        Args:
            table_name: Name of the table
            columns: List of columns to index
        
        Returns:
            Success or error message
        """
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        schema_data = self._db.get(schema_key)
        if not schema_data:
            return f"Table '{table_name}' does not exist"
        
        schema = json.loads(schema_data.decode())
        
        # Validate columns exist
        for col in columns:
            if col not in schema["columns"]:
                return f"ERROR: Column '{col}' does not exist"
        
        # Add to indexes
        for col in columns:
            if col not in schema.get("indexes", []):
                schema.setdefault("indexes", []).append(col)
        
        self._transaction_put(schema_key, json.dumps(schema).encode())
        
        # Build index from existing data
        for col in columns:
            idx_key = f"_index:{table_name}:{col}".encode()
            index_map = {}
            
            prefix = f"{table_name}:".encode()
            for key, value in self._db.iterator(prefix=prefix):
                if key.startswith(f"_schema:{table_name}".encode()):
                    continue
                
                row = json.loads(value.decode())
                if col in row:
                    val = str(row[col])
                    row_key = key.decode().split(':', 1)[1]
                    if val in index_map:
                        if isinstance(index_map[val], list):
                            index_map[val].append(row_key)
                        else:
                            index_map[val] = [index_map[val], row_key]
                    else:
                        index_map[val] = row_key
            
            self._transaction_put(idx_key, json.dumps(index_map).encode())
        
        return f"Index added on {columns} in '{table_name}'"
    
    def alter_drop_index(self, table_name: str, index_name: str) -> str:
        """
        Drop an index from a table.
        
        Args:
            table_name: Name of the table
            index_name: Name of the index (column name)
        
        Returns:
            Success or error message
        """
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        schema_data = self._db.get(schema_key)
        if not schema_data:
            return f"Table '{table_name}' does not exist"
        
        schema = json.loads(schema_data.decode())
        
        # Remove from indexes list
        if index_name in schema.get("indexes", []):
            schema["indexes"].remove(index_name)
            self._transaction_put(schema_key, json.dumps(schema).encode())
        
        # Delete index data
        idx_key = f"_index:{table_name}:{index_name}".encode()
        self._transaction_delete(idx_key)
        
        return f"Index '{index_name}' dropped from '{table_name}'"
    
    def alter_add_constraint(self, table_name: str, constraint_type: str, constraint_def: Dict[str, Any]) -> str:
        """
        Add a constraint to a table.
        
        Args:
            table_name: Name of the table
            constraint_type: Type of constraint (FOREIGN_KEY, UNIQUE, CHECK)
            constraint_def: Constraint definition
        
        Returns:
            Success or error message
        """
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        schema_data = self._db.get(schema_key)
        if not schema_data:
            return f"Table '{table_name}' does not exist"
        
        schema = json.loads(schema_data.decode())
        
        if constraint_type == 'FOREIGN_KEY':
            # Validate column exists
            col = constraint_def.get('column')
            if col not in schema["columns"]:
                return f"ERROR: Column '{col}' does not exist"
            
            schema.setdefault("foreign_keys", []).append(constraint_def)
            
        elif constraint_type == 'UNIQUE':
            columns = constraint_def.get('columns', [])
            for col in columns:
                if col not in schema["columns"]:
                    return f"ERROR: Column '{col}' does not exist"
            
            schema.setdefault("unique_constraints", []).append(columns)
            
            # Create unique index
            idx_key = f"_unique_index:{table_name}:{':'.join(columns)}".encode()
            self._transaction_put(idx_key, json.dumps({}).encode())
            
        elif constraint_type == 'CHECK':
            schema.setdefault("check_constraints", []).append(constraint_def.get('expression', ''))
        
        self._transaction_put(schema_key, json.dumps(schema).encode())
        
        return f"{constraint_type} constraint added to '{table_name}'"
    
    def alter_drop_constraint(self, table_name: str, constraint_name: str) -> str:
        """
        Drop a constraint from a table.
        
        Args:
            table_name: Name of the table
            constraint_name: Name or identifier of the constraint
        
        Returns:
            Success or error message
        """
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        schema_data = self._db.get(schema_key)
        if not schema_data:
            return f"Table '{table_name}' does not exist"
        
        schema = json.loads(schema_data.decode())
        
        # Try to find and remove constraint
        # Check foreign keys
        foreign_keys = schema.get("foreign_keys", [])
        for i, fk in enumerate(foreign_keys):
            if fk.get('column') == constraint_name:
                schema["foreign_keys"].pop(i)
                self._transaction_put(schema_key, json.dumps(schema).encode())
                return f"Foreign key constraint on '{constraint_name}' dropped"
        
        # Check unique constraints
        unique_constraints = schema.get("unique_constraints", [])
        for i, unique_cols in enumerate(unique_constraints):
            if ':'.join(unique_cols) == constraint_name or unique_cols[0] == constraint_name:
                schema["unique_constraints"].pop(i)
                idx_key = f"_unique_index:{table_name}:{':'.join(unique_cols)}".encode()
                self._transaction_delete(idx_key)
                self._transaction_put(schema_key, json.dumps(schema).encode())
                return f"Unique constraint on '{constraint_name}' dropped"
        
        return f"ERROR: Constraint '{constraint_name}' not found"
        """
        Validate unique constraints for a row.
        
        Args:
            table_name: Name of the table
            row: Row data to validate
            schema: Table schema
            exclude_row_key: Optional row key to exclude (for updates)
        
        Returns:
            (is_valid, error_message)
        """
        unique_constraints = schema.get('unique_constraints', [])
        
        for unique_cols in unique_constraints:
            # Build composite key
            composite_key = tuple(str(row.get(col)) for col in unique_cols)
            
            # Check unique index
            idx_key = f"_unique_index:{table_name}:{':'.join(unique_cols)}".encode()
            idx_data = self._db.get(idx_key)
            
            if idx_data:
                index_map = json.loads(idx_data.decode())
                
                # Check if key exists (excluding current row for updates)
                if str(composite_key) in index_map:
                    existing = index_map[str(composite_key)]
                    if isinstance(existing, list):
                        # If it's a list, check if any entry is not the excluded row
                        if exclude_row_key is None or any(e != exclude_row_key for e in existing):
                            return False, f"Unique constraint violation on {unique_cols}: {composite_key}"
                    elif existing != exclude_row_key:
                        return False, f"Unique constraint violation on {unique_cols}: {composite_key}"
        
        return True, None
    
    def _update_unique_indexes(self, table_name: str, row: Dict, row_key: str, schema: Dict, old_row: Optional[Dict] = None):
        """Update unique indexes for a row."""
        unique_constraints = schema.get('unique_constraints', [])
        
        for unique_cols in unique_constraints:
            idx_key = f"_unique_index:{table_name}:{':'.join(unique_cols)}".encode()
            idx_data = self._db.get(idx_key)
            
            if not idx_data:
                continue
            
            index_map = json.loads(idx_data.decode())
            
            # Remove old entry if updating
            if old_row:
                old_composite_key = tuple(str(old_row.get(col)) for col in unique_cols)
                if str(old_composite_key) in index_map:
                    existing = index_map[str(old_composite_key)]
                    if isinstance(existing, list):
                        index_map[str(old_composite_key)] = [e for e in existing if e != row_key]
                        if not index_map[str(old_composite_key)]:
                            del index_map[str(old_composite_key)]
                    else:
                        del index_map[str(old_composite_key)]
            
            # Add new entry
            composite_key = tuple(str(row.get(col)) for col in unique_cols)
            if str(composite_key) in index_map:
                existing = index_map[str(composite_key)]
                if isinstance(existing, list):
                    if row_key not in existing:
                        existing.append(row_key)
                else:
                    index_map[str(composite_key)] = [existing, row_key]
            else:
                index_map[str(composite_key)] = row_key
            
            self._transaction_put(idx_key, json.dumps(index_map).encode())
    
    def _validate_check_constraints(self, row: Dict, schema: Dict) -> Tuple[bool, Optional[str]]:
        """
        Validate CHECK constraints for a row.
        
        Args:
            row: Row data to validate
            schema: Table schema with check_constraints
        
        Returns:
            (is_valid, error_message)
        """
        check_constraints = schema.get('check_constraints', [])
        
        for check_expr in check_constraints:
            is_valid, error = self._evaluate_check_expression(check_expr, row)
            if not is_valid:
                return False, error
        
        return True, None
    
    def _evaluate_check_expression(self, expression: str, row: Dict) -> Tuple[bool, Optional[str]]:
        """
        Evaluate a CHECK expression against row data.
        
        Supports: =, !=, <>, <, >, <=, >=, IN, BETWEEN, LIKE, IS NULL, IS NOT NULL
        
        Args:
            expression: CHECK expression string
            row: Row data
        
        Returns:
            (is_valid, error_message)
        """
        expression = expression.strip()
        
        # Handle IS NULL / IS NOT NULL
        null_match = re.match(r'(\w+)\s+IS\s+(NOT\s+)?NULL$', expression, re.IGNORECASE)
        if null_match:
            col = null_match.group(1)
            is_not = null_match.group(2) is not None
            val = row.get(col)
            
            if is_not:
                # IS NOT NULL
                if val is None:
                    return False, f"CHECK constraint violation: {col} IS NOT NULL"
                return True, None
            else:
                # IS NULL
                if val is not None:
                    return False, f"CHECK constraint violation: {col} IS NULL"
                return True, None
        
        # Handle IN operator
        in_match = re.match(r'(\w+)\s+IN\s*\(([^)]+)\)$', expression, re.IGNORECASE)
        if in_match:
            col = in_match.group(1)
            values_str = in_match.group(2)
            allowed = [v.strip().strip("'\\\"") for v in values_str.split(',')]
            val = str(row.get(col, ''))
            
            if val not in allowed:
                return False, f"CHECK constraint violation: {col}={val} not in {allowed}"
            return True, None
        
        # Handle BETWEEN
        between_match = re.match(r'(\w+)\s+BETWEEN\s+(\S+)\s+AND\s+(\S+)$', expression, re.IGNORECASE)
        if between_match:
            col = between_match.group(1)
            low = self._parse_check_value(between_match.group(2))
            high = self._parse_check_value(between_match.group(3))
            val = row.get(col)
            
            if val is None:
                return True, None  # NULL passes CHECK constraints
            
            try:
                if not (low <= val <= high):
                    return False, f"CHECK constraint violation: {col}={val} not between {low} and {high}"
            except TypeError:
                return False, f"CHECK constraint violation: cannot compare {col}={val}"
            return True, None
        
        # Handle LIKE
        like_match = re.match(r'(\w+)\s+LIKE\s+[\\'\"]([^\\'\"]+)[\\'\"]$', expression, re.IGNORECASE)
        if like_match:
            col = like_match.group(1)
            pattern = like_match.group(2)
            val = str(row.get(col, ''))
            
            if not self._like_match(val, pattern):
                return False, f"CHECK constraint violation: {col}='{val}' not LIKE '{pattern}'"
            return True, None
        
        # Handle comparison operators
        comp_match = re.match(r'(\w+)\s*(=|!=|<>|<=|>=|<|>)\s*(.+)$', expression)
        if comp_match:
            col = comp_match.group(1)
            op = comp_match.group(2)
            expected_str = comp_match.group(3).strip()
            expected = self._parse_check_value(expected_str)
            actual = row.get(col)
            
            if actual is None:
                return True, None  # NULL passes CHECK constraints
            
            try:
                if op == '=':
                    if actual != expected:
                        return False, f"CHECK constraint violation: {col}={actual} != {expected}"
                elif op in ('!=', '<>'):
                    if actual == expected:
                        return False, f"CHECK constraint violation: {col}={actual} == {expected}"
                elif op == '<':
                    if not (actual < expected):
                        return False, f"CHECK constraint violation: {col}={actual} not < {expected}"
                elif op == '>':
                    if not (actual > expected):
                        return False, f"CHECK constraint violation: {col}={actual} not > {expected}"
                elif op == '<=':
                    if not (actual <= expected):
                        return False, f"CHECK constraint violation: {col}={actual} not <= {expected}"
                elif op == '>=':
                    if not (actual >= expected):
                        return False, f"CHECK constraint violation: {col}={actual} not >= {expected}"
            except TypeError:
                return False, f"CHECK constraint violation: cannot compare {col}={actual} with {expected}"
            
            return True, None
        
        # Unknown expression
        return True, None  # Be permissive for unknown expressions
    
    def _parse_check_value(self, val_str: str) -> Any:
        """Parse value from CHECK expression."""
        val_str = val_str.strip()
        
        # String literal
        if (val_str.startswith("'") and val_str.endswith("'")) or \
           (val_str.startswith('"') and val_str.endswith('"')):
            return val_str[1:-1]
        
        # Number
        try:
            if '.' in val_str:
                return float(val_str)
            return int(val_str)
        except ValueError:
            pass
        
        # Boolean/NULL
        upper = val_str.upper()
        if upper == 'TRUE':
            return True
        if upper == 'FALSE':
            return False
        if upper == 'NULL':
            return None
        
        return val_str
    
    def _like_match(self, value: str, pattern: str) -> bool:
        """Match value against SQL LIKE pattern."""
        # Convert SQL LIKE pattern to regex
        # % matches any sequence, _ matches single character
        regex_pattern = pattern.replace('%', '.*').replace('_', '.')
        regex_pattern = '^' + regex_pattern + '$'
        
        try:
            return bool(re.match(regex_pattern, value, re.IGNORECASE))
        except re.error:
            return False
    
    def _validate_json_column(self, col_name: str, value: Any, column_types: Dict[str, str]) -> Tuple[bool, Optional[str]]:
        """
        Validate JSON column value.
        
        Args:
            col_name: Column name
            value: Value to validate
            column_types: Dictionary of column types
        
        Returns:
            (is_valid, error_message)
        """
        col_type = column_types.get(col_name, 'TEXT')
        if col_type.upper() == 'JSON':
            if value is not None and not validate_json(value):
                return False, f"Invalid JSON value for column '{col_name}'"
        return True, None
    
    def insert(self, table_name: str, values: List[Any]) -> str:
        """Insert a row into a table with FK, CHECK, and JSON validation."""
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
        
        # Validate JSON columns
        column_types = schema.get('column_types', {})
        for col in schema["columns"]:
            if col in row:
                is_valid, error = self._validate_json_column(col, row[col], column_types)
                if not is_valid:
                    return f"ERROR: {error}"
        
        # Validate CHECK constraints
        is_valid, error = self._validate_check_constraints(row, schema)
        if not is_valid:
            return f"ERROR: {error}"
        
        # Validate unique constraints
        is_unique, error = self._validate_unique_constraints(table_name, row, schema)
        if not is_unique:
            return f"ERROR: {error}"
        
        # Validate foreign keys
        foreign_keys = schema.get('foreign_keys', [])
        for fk in foreign_keys:
            fk_column = fk['column']
            if fk_column in row:
                is_valid, error = self._validate_foreign_key(fk, row[fk_column])
                if not is_valid:
                    return f"ERROR: {error}"
        
        primary_key = schema.get("primary_key")
        if primary_key and primary_key in row:
            store_key = str(row[primary_key])
        else:
            store_key = row_id
        
        key = self._make_key(table_name, store_key)
        self._transaction_put(key, json.dumps(row).encode())
        
        self._update_indexes(table_name, row, store_key, schema)
        self._update_unique_indexes(table_name, row, store_key, schema)
        
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
                    if val in index_map:
                        if isinstance(index_map[val], list):
                            if row_key not in index_map[val]:
                                index_map[val].append(row_key)
                        else:
                            index_map[val] = [index_map[val], row_key]
                    else:
                        index_map[val] = row_key
                    self._transaction_put(idx_key, json.dumps(index_map).encode())
    
    def select(self, table_name: str, columns: Optional[List] = None,
               where: Optional[Dict[str, Any]] = None,
               order_by: Optional[str] = None,
               order_desc: bool = False,
               raw: bool = False) -> Any:
        """Select rows from a table with JSON extraction support."""
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        if not self._db.get(schema_key):
            return f"Table '{table_name}' does not exist"
        
        schema = json.loads(self._db.get(schema_key).decode())
        
        select_columns = []
        if columns:
            for col_spec in columns:
                if isinstance(col_spec, dict):
                    col_name = col_spec.get('name')
                    if col_name in schema["columns"] or col_name == "*":
                        select_columns.append(
                            col_spec.get('alias') or col_name
                        )
                    elif col_spec.get('alias'):
                        select_columns.append(col_spec['alias'])
                    else:
                        select_columns.append(col_name)
                else:
                    select_columns.append(col_spec)
        else:
            select_columns = schema["columns"]
        
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
        
        # Apply JSON extractions and format results
        filtered_results = []
        for row in results:
            filtered_row = {}
            
            # Handle regular columns
            for col_spec in columns or [{"name": c} for c in select_columns]:
                if isinstance(col_spec, dict):
                    col_name = col_spec.get('name')
                    
                    if col_spec.get('json_path'):
n                        # JSON extraction
                        json_col = col_spec['name']
                        json_path = col_spec['json_path']
                        as_text = col_spec.get('json_as_text', False)
                        
                        if json_col in row:
                            json_data = row[json_col]
                            if as_text:
                                extracted = json_extract_text(json_data, json_path)
                            else:
                                extracted = json_extract(json_data, json_path)
                            
                            alias = col_spec.get('alias') or f"{json_col}->{json_path}"
                            filtered_row[alias] = extracted if extracted is not None else "NULL"
                        else:
                            alias = col_spec.get('alias') or f"{json_col}->{json_path}"
                            filtered_row[alias] = "NULL"
                    elif col_spec.get('alias'):
                        # Regular column with alias
                        filtered_row[col_spec['alias']] = row.get(col_name, "NULL")
                    else:
                        # Regular column
                        filtered_row[col_name] = row.get(col_name, "NULL")
                else:
                    # Simple column name
                    filtered_row[col_spec] = row.get(col_spec, "NULL")
            
            filtered_results.append(filtered_row)
        
        # Get final column list for formatting
        final_columns = list(filtered_results[0].keys()) if filtered_results else []
        return self._format_results(final_columns, filtered_results)
    
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
        """Update rows in a table with FK, CHECK, unique, and JSON constraint validation."""
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
        
        foreign_keys = schema.get('foreign_keys', [])
        column_types = schema.get('column_types', {})
        
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
            
            # Validate JSON columns in set_clause
            for col, val in set_clause.items():
                is_valid, error = self._validate_json_column(col, val, column_types)
                if not is_valid:
                    return f"ERROR: {error}"
            
            # Build new row for constraint validation
            new_row = row.copy()
            for col, val in set_clause.items():
                new_row[col] = val
            
            # Validate CHECK constraints
            is_valid, error = self._validate_check_constraints(new_row, schema)
            if not is_valid:
                return f"ERROR: {error}"
            
            # Validate unique constraints
            primary_key = schema.get("primary_key")
            store_key = str(row[primary_key]) if primary_key and primary_key in row else row.get("id")
            is_unique, error = self._validate_unique_constraints(table_name, new_row, schema, exclude_row_key=store_key)
            if not is_unique:
                return f"ERROR: {error}"
            
            # Check FK constraints for new values
            for fk in foreign_keys:
                fk_column = fk['column']
                if fk_column in set_clause:
                    is_valid, error = self._validate_foreign_key(fk, set_clause[fk_column])
                    if not is_valid:
                        return f"ERROR: {error}"
            
            old_key_val = None
            if primary_key and primary_key in set_clause:
                old_key_val = row.get(primary_key)
            
            for col, val in set_clause.items():
                row[col] = val
            
            self._transaction_put(key, json.dumps(row).encode())
            
            if old_key_val is not None and primary_key:
                self._update_indexes(table_name, row, str(row[primary_key]), schema)
            
            self._update_unique_indexes(table_name, new_row, store_key, schema, old_row=row)
            
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
        """Delete rows from a table with FK constraint checking."""
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        schema_data = self._db.get(schema_key)
        if not schema_data:
            return f"Table '{table_name}' does not exist"
        
        schema = json.loads(schema_data.decode())
        
        # Check for referencing tables before deleting
        referencing = self._get_referencing_tables(table_name)
        
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
            
            # Check FK constraints - if any referencing rows exist
            for ref in referencing:
                ref_column = ref['fk_def']['references_column']
                if ref_column in schema.get('columns', []):
                    ref_value = row.get(ref_column)
                    # Check if any rows in referencing table reference this value
                    ref_prefix = f"{ref['table']}:".encode()
                    for ref_key, ref_data in self._db.iterator(prefix=ref_prefix):
                        if ref_key.startswith(f"_schema:{ref['table']}".encode()):
                            continue
                        ref_row = json.loads(ref_data.decode())
                        if str(ref_row.get(ref['column'])) == str(ref_value):
                            fk_def = ref['fk_def']
                            on_delete = fk_def.get('on_delete', 'RESTRICT')
                            
                            if on_delete == 'RESTRICT':
                                return f"ERROR: Cannot delete row: referenced by {ref['table']}.{ref['column']} (ON DELETE RESTRICT)"
                            elif on_delete == 'NO_ACTION':
                                return f"ERROR: Cannot delete row: referenced by {ref['table']}.{ref['column']} (ON DELETE NO ACTION)"
                            # CASCADE and SET_NULL handled separately
            
            keys_to_delete.append(key)
            deleted_rows.append(row.copy())
        
        # Handle CASCADE and SET_NULL for referencing tables
        for row in deleted_rows:
            for ref in referencing:
                ref_column = ref['fk_def']['references_column']
                if ref_column in schema.get('columns', []):
                    ref_value = row.get(ref_column)
                    on_delete = ref['fk_def'].get('on_delete', 'RESTRICT')
                    
                    if on_delete == 'CASCADE':
                        # Delete referencing rows
                        self._delete_by_fk_value(ref['table'], ref['column'], ref_value)
                    elif on_delete == 'SET_NULL':
                        # Set referencing column to NULL
                        self._update_by_fk_value(ref['table'], ref['column'], ref_value, {ref['column']: None})
        
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
    
    def _delete_by_fk_value(self, table_name: str, column: str, value: Any):
        """Delete all rows in table where column equals value."""
        prefix = f"{table_name}:".encode()
        keys_to_delete = []
        
        for key, data in self._db.iterator(prefix=prefix):
            if key.startswith(f"_schema:{table_name}".encode()):
                continue
            
            row = json.loads(data.decode())
            if str(row.get(column)) == str(value):
                keys_to_delete.append(key)
        
        for key in keys_to_delete:
            self._transaction_delete(key)
    
    def _update_by_fk_value(self, table_name: str, column: str, value: Any, set_clause: Dict[str, Any]):
        """Update all rows in table where column equals value."""
        prefix = f"{table_name}:".encode()
        
        for key, data in self._db.iterator(prefix=prefix):
            if key.startswith(f"_schema:{table_name}".encode()):
                continue
            
            row = json.loads(data.decode())
            if str(row.get(column)) == str(value):
                for col, val in set_clause.items():
                    row[col] = val
                self._transaction_put(key, json.dumps(row).encode())
    
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
"""LevelDB database layer with CRUD operations, user management and privileges."""

import os
import json
import hashlib
import secrets
import time
import re
import plyvel
from typing import Optional, Dict, Any, List, Tuple
from binlog import Binlog
from json_functions import validate_json, parse_json, json_extract, json_extract_text


class Database:
    """Wrapper for LevelDB providing MySQL-like database operations with auth."""
    
    def __init__(self, data_dir: str, server_id: int = 1):
        self.data_dir = data_dir
        self.server_id = server_id
        self._db = None
        self.current_db = None
        self._transaction_active = False
        self._transaction_changes = {}
        self._transaction_start_time = None
        self._system_db = None
        self._binlog = None
        
        # Initialize
        self._open_system_db()
        self._open_binlog()
    
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
        
        return f"Database '{db_name}' dropped successfully"
    
    def use_database(self, db_name: str) -> str:
        """Switch to a database."""
        if self._transaction_active:
            return "ERROR: Cannot switch database during transaction"
        
        db_path = self._db_path(db_name)
        if not os.path.exists(db_path):
            return f"Database '{db_name}' does not exist"
        
        if self._db:
            self._db.close()
        
        self._db = plyvel.DB(db_path, create_if_missing=True)
        self.current_db = db_name
        return f"Switched to database '{db_name}'"
    
    def create_table(self, table_name: str, columns: List[Dict[str, Any]]) -> str:
        """
        Create a table with support for constraints (FK, UNIQUE, CHECK, etc.).
        
        Args:
            table_name: Name of the table
            columns: List of column definitions from parser (can include constraints)
        """
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        if self._db.get(schema_key):
            return f"Table '{table_name}' already exists"
        
        parsed_columns = []
        column_types = {}  # Store column types for JSON validation
        primary_key = None
        index_columns = []
        foreign_keys = []
        unique_constraints = []
        check_constraints = []
        
        for col_info in columns:
            # Handle constraint definitions
            if isinstance(col_info, dict) and 'constraint_type' in col_info:
                constraint_type = col_info['constraint_type']
                
                if constraint_type == 'PRIMARY_KEY':
                    primary_key = col_info['column']
                elif constraint_type == 'FOREIGN_KEY':
                    foreign_keys.append({
                        'column': col_info['column'],
                        'references_table': col_info['references_table'],
                        'references_column': col_info['references_column'],
                        'on_delete': col_info.get('on_delete', 'RESTRICT'),
                        'on_update': col_info.get('on_update', 'RESTRICT')
                    })
                elif constraint_type == 'UNIQUE':
                    unique_constraints.append(col_info['columns'])
                elif constraint_type == 'CHECK':
                    check_constraints.append(col_info['expression'])
                continue
            
            # Regular column definition
            col_name = col_info.get('name')
            if col_name:
                parsed_columns.append(col_name)
                column_types[col_name] = col_info.get('type', 'TEXT')
                
                # Handle inline constraints
                if col_info.get('primary_key'):
                    primary_key = col_name
                
                if col_info.get('index'):
                    index_columns.append(col_name)
                
                if col_info.get('unique'):
                    # Add to unique constraints (single column)
                    unique_constraints.append([col_name])
                
                # Handle inline foreign key
                fk_info = col_info.get('foreign_key')
                if fk_info and fk_info.get('references_table'):
                    foreign_keys.append({
                        'column': col_name,
                        'references_table': fk_info['references_table'],
                        'references_column': fk_info['references_column'],
                        'on_delete': fk_info.get('on_delete', 'RESTRICT'),
                        'on_update': fk_info.get('on_update', 'RESTRICT')
                    })
                
                # Handle inline check
                check_info = col_info.get('check')
                if check_info:
                    if isinstance(check_info, dict):
                        check_constraints.append(check_info.get('expression', ''))
                    else:
                        check_constraints.append(str(check_info))
        
        schema = {
            "columns": parsed_columns,
            "column_types": column_types,
            "next_id": 1,
            "primary_key": primary_key,
            "indexes": index_columns,
            "foreign_keys": foreign_keys,
            "unique_constraints": unique_constraints,
            "check_constraints": check_constraints
        }
        self._transaction_put(schema_key, json.dumps(schema).encode())
        
        # Create primary key index
        if primary_key:
            idx_key = f"_index:{table_name}:{primary_key}".encode()
            self._transaction_put(idx_key, json.dumps({}).encode())
        
        # Create other indexes
        for idx_col in index_columns:
            idx_key = f"_index:{table_name}:{idx_col}".encode()
            self._transaction_put(idx_key, json.dumps({}).encode())
        
        # Create unique indexes
        for i, unique_cols in enumerate(unique_constraints):
            idx_key = f"_unique_index:{table_name}:{':'.join(unique_cols)}".encode()
            self._transaction_put(idx_key, json.dumps({}).encode())
        
        # Log to binlog
        if self._binlog:
            self._binlog.write_entry(
                server_id=self.server_id,
                database=self.current_db or "",
                operation="CREATE_TABLE",
                table=table_name,
                data={
                    "table_name": table_name,
                    "columns": parsed_columns,
                    "primary_key": primary_key,
                    "indexes": index_columns,
                    "foreign_keys": foreign_keys,
                    "unique_constraints": unique_constraints,
                    "check_constraints": check_constraints
                }
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
    
    # ALTER TABLE operations
    def alter_add_column(self, table_name: str, column_def: Dict[str, Any]) -> str:
        """
        Add a column to an existing table.
        
        Args:
            table_name: Name of the table
            column_def: Column definition from parser
        
        Returns:
            Success or error message
        """
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        schema_data = self._db.get(schema_key)
        if not schema_data:
            return f"Table '{table_name}' does not exist"
        
        schema = json.loads(schema_data.decode())
        
        col_name = column_def.get('name')
        if not col_name:
            return "ERROR: Column name required"
        
        if col_name in schema["columns"]:
            return f"ERROR: Column '{col_name}' already exists"
        
        # Add column to schema
        schema["columns"].append(col_name)
        schema["column_types"][col_name] = column_def.get('type', 'TEXT')
        
        # Handle constraints
        if column_def.get('primary_key'):
            schema["primary_key"] = col_name
        
        if column_def.get('index'):
            if col_name not in schema.get("indexes", []):
                schema.setdefault("indexes", []).append(col_name)
        
        if column_def.get('unique'):
            schema.setdefault("unique_constraints", []).append([col_name])
        
        if column_def.get('check'):
            check_expr = column_def['check']
            if isinstance(check_expr, dict):
                schema.setdefault("check_constraints", []).append(check_expr.get('expression', ''))
            else:
                schema.setdefault("check_constraints", []).append(str(check_expr))
        
        if column_def.get('foreign_key'):
            schema.setdefault("foreign_keys", []).append({
                'column': col_name,
                **column_def['foreign_key']
            })
        
        # Update existing rows with NULL for new column
        prefix = f"{table_name}:".encode()
        for key, value in self._db.iterator(prefix=prefix):
            if key.startswith(f"_schema:{table_name}".encode()):
                continue
            
            row = json.loads(value.decode())
            row[col_name] = None  # Default to NULL
            self._transaction_put(key, json.dumps(row).encode())
        
        self._transaction_put(schema_key, json.dumps(schema).encode())
        
        # Create index if needed
        if column_def.get('index'):
            idx_key = f"_index:{table_name}:{col_name}".encode()
            self._transaction_put(idx_key, json.dumps({}).encode())
        
        return f"Column '{col_name}' added to '{table_name}'"
    
    def alter_drop_column(self, table_name: str, column_name: str, cascade: bool = False) -> str:
        """
        Drop a column from a table.
        
        Args:
            table_name: Name of the table
            column_name: Name of the column to drop
            cascade: Whether to cascade drop dependent objects
        
        Returns:
            Success or error message
        """
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        schema_data = self._db.get(schema_key)
        if not schema_data:
            return f"Table '{table_name}' does not exist"
        
        schema = json.loads(schema_data.decode())
        
        if column_name not in schema["columns"]:
            return f"ERROR: Column '{column_name}' does not exist"
        
        # Check if column is primary key
        if schema.get("primary_key") == column_name and not cascade:
            return f"ERROR: Cannot drop primary key column '{column_name}' without CASCADE"
        
        # Check for foreign key references
        foreign_keys = schema.get("foreign_keys", [])
        for fk in foreign_keys:
            if fk.get('column') == column_name and not cascade:
                return f"ERROR: Cannot drop column '{column_name}' with foreign key constraint without CASCADE"
        
        # Check for unique constraints
        unique_constraints = schema.get("unique_constraints", [])
        for i, unique_cols in enumerate(unique_constraints):
            if column_name in unique_cols:
                if not cascade:
                    return f"ERROR: Cannot drop column '{column_name}' with unique constraint without CASCADE"
                # Remove the constraint
                schema["unique_constraints"].pop(i)
        
        # Check for CHECK constraints
        check_constraints = schema.get("check_constraints", [])
        new_checks = []
        for check_expr in check_constraints:
            if column_name.lower() in check_expr.lower() and not cascade:
                return f"ERROR: Cannot drop column '{column_name}' with CHECK constraint without CASCADE"
            elif column_name.lower() not in check_expr.lower():
                new_checks.append(check_expr)
        schema["check_constraints"] = new_checks
        
        # Check for indexes
        indexes = schema.get("indexes", [])
        if column_name in indexes:
            if cascade:
                schema["indexes"].remove(column_name)
                idx_key = f"_index:{table_name}:{column_name}".encode()
                self._transaction_delete(idx_key)
            else:
                return f"ERROR: Cannot drop indexed column '{column_name}' without CASCADE"
        
        # Remove column from schema
        schema["columns"].remove(column_name)
        if column_name in schema["column_types"]:
            del schema["column_types"][column_name]
        
        # Remove from foreign keys
        schema["foreign_keys"] = [fk for fk in foreign_keys if fk.get('column') != column_name]
        
        # Update existing rows
        prefix = f"{table_name}:".encode()
        for key, value in self._db.iterator(prefix=prefix):
            if key.startswith(f"_schema:{table_name}".encode()):
                continue
            
            row = json.loads(value.decode())
            if column_name in row:
                del row[column_name]
            self._transaction_put(key, json.dumps(row).encode())
        
        self._transaction_put(schema_key, json.dumps(schema).encode())
        
        return f"Column '{column_name}' dropped from '{table_name}'"
    
    def alter_modify_column(self, table_name: str, column_name: str, new_type: str, constraints: str = "") -> str:
        """
        Modify column type and constraints.
        
        Args:
            table_name: Name of the table
            column_name: Name of the column
            new_type: New data type
            constraints: Additional constraints
        
        Returns:
            Success or error message
        """
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        schema_data = self._db.get(schema_key)
        if not schema_data:
            return f"Table '{table_name}' does not exist"
        
        schema = json.loads(schema_data.decode())
        
        if column_name not in schema["columns"]:
            return f"ERROR: Column '{column_name}' does not exist"
        
        old_type = schema["column_types"].get(column_name, "TEXT")
        
        # Validate type conversion
        prefix = f"{table_name}:".encode()
        for key, value in self._db.iterator(prefix=prefix):
            if key.startswith(f"_schema:{table_name}".encode()):
                continue
            
            row = json.loads(value.decode())
            if column_name in row and row[column_name] is not None:
                val = row[column_name]
                try:
                    if new_type.upper() == 'INT':
                        int(val)
                    elif new_type.upper() == 'FLOAT':
                        float(val)
                    elif new_type.upper() == 'TEXT':
                        str(val)
                except (ValueError, TypeError):
                    return f"ERROR: Cannot convert value '{val}' to {new_type}"
        
        # Update type
        schema["column_types"][column_name] = new_type
        
        # Parse additional constraints
        if constraints:
            cons_upper = constraints.upper()
            if 'NOT NULL' in cons_upper:
                # Check for NULL values
                for key, value in self._db.iterator(prefix=prefix):
                    if key.startswith(f"_schema:{table_name}".encode()):
                        continue
                    row = json.loads(value.decode())
                    if column_name in row and row[column_name] is None:
                        return f"ERROR: Cannot set NOT NULL - column '{column_name}' contains NULL values"
        
        self._transaction_put(schema_key, json.dumps(schema).encode())
        
        return f"Column '{column_name}' modified to type {new_type}"
    
    def alter_rename_column(self, table_name: str, old_name: str, new_name: str) -> str:
        """
        Rename a column.
        
        Args:
            table_name: Name of the table
            old_name: Current column name
            new_name: New column name
        
        Returns:
            Success or error message
        """
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        schema_data = self._db.get(schema_key)
        if not schema_data:
            return f"Table '{table_name}' does not exist"
        
        schema = json.loads(schema_data.decode())
        
        if old_name not in schema["columns"]:
            return f"ERROR: Column '{old_name}' does not exist"
        
        if new_name in schema["columns"]:
            return f"ERROR: Column '{new_name}' already exists"
        
        # Rename in columns list
        idx = schema["columns"].index(old_name)
        schema["columns"][idx] = new_name
        
        # Rename in column_types
        if old_name in schema["column_types"]:
            schema["column_types"][new_name] = schema["column_types"].pop(old_name)
        
        # Rename in primary key
        if schema.get("primary_key") == old_name:
            schema["primary_key"] = new_name
        
        # Rename in indexes
        if old_name in schema.get("indexes", []):
            schema["indexes"].remove(old_name)
            schema["indexes"].append(new_name)
        
        # Rename in unique constraints
        for i, unique_cols in enumerate(schema.get("unique_constraints", [])):
            if old_name in unique_cols:
                schema["unique_constraints"][i] = [new_name if c == old_name else c for c in unique_cols]
        
        # Rename in foreign keys
        for fk in schema.get("foreign_keys", []):
            if fk.get('column') == old_name:
                fk['column'] = new_name
        
        # Rename in CHECK constraints
        for i, check_expr in enumerate(schema.get("check_constraints", [])):
            schema["check_constraints"][i] = check_expr.replace(old_name, new_name)
        
        # Rename in CHECK constraints
        for i, check_expr in enumerate(schema.get("check_constraints", [])):
            schema["check_constraints"][i] = check_expr.replace(old_name, new_name)
        
        # Update existing rows
        prefix = f"{table_name}:".encode()
        for key, value in self._db.iterator(prefix=prefix):
            if key.startswith(f"_schema:{table_name}".encode()):
                continue
            
            row = json.loads(value.decode())
            if old_name in row:
                row[new_name] = row.pop(old_name)
            self._transaction_put(key, json.dumps(row).encode())
        
        # Rename index
        old_idx_key = f"_index:{table_name}:{old_name}".encode()
        new_idx_key = f"_index:{table_name}:{new_name}".encode()
        idx_data = self._db.get(old_idx_key)
        if idx_data:
            self._transaction_delete(old_idx_key)
            self._transaction_put(new_idx_key, idx_data)
        
        self._transaction_put(schema_key, json.dumps(schema).encode())
        
        return f"Column '{old_name}' renamed to '{new_name}'"
    
    def alter_add_index(self, table_name: str, columns: List[str]) -> str:
        """
        Add an index to a table.
        
        Args:
            table_name: Name of the table
            columns: List of columns to index
        
        Returns:
            Success or error message
        """
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        schema_data = self._db.get(schema_key)
        if not schema_data:
            return f"Table '{table_name}' does not exist"
        
        schema = json.loads(schema_data.decode())
        
        # Validate columns exist
        for col in columns:
            if col not in schema["columns"]:
                return f"ERROR: Column '{col}' does not exist"
        
        # Add to indexes
        for col in columns:
            if col not in schema.get("indexes", []):
                schema.setdefault("indexes", []).append(col)
        
        self._transaction_put(schema_key, json.dumps(schema).encode())
        
        # Build index from existing data
        for col in columns:
            idx_key = f"_index:{table_name}:{col}".encode()
            index_map = {}
            
            prefix = f"{table_name}:".encode()
            for key, value in self._db.iterator(prefix=prefix):
                if key.startswith(f"_schema:{table_name}".encode()):
                    continue
                
                row = json.loads(value.decode())
                if col in row:
                    val = str(row[col])
                    row_key = key.decode().split(':', 1)[1]
                    if val in index_map:
                        if isinstance(index_map[val], list):
                            index_map[val].append(row_key)
                        else:
                            index_map[val] = [index_map[val], row_key]
                    else:
                        index_map[val] = row_key
            
            self._transaction_put(idx_key, json.dumps(index_map).encode())
        
        return f"Index added on {columns} in '{table_name}'"
    
    def alter_drop_index(self, table_name: str, index_name: str) -> str:
        """
        Drop an index from a table.
        
        Args:
            table_name: Name of the table
            index_name: Name of the index (column name)
        
        Returns:
            Success or error message
        """
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        schema_data = self._db.get(schema_key)
        if not schema_data:
            return f"Table '{table_name}' does not exist"
        
        schema = json.loads(schema_data.decode())
        
        # Remove from indexes list
        if index_name in schema.get("indexes", []):
            schema["indexes"].remove(index_name)
            self._transaction_put(schema_key, json.dumps(schema).encode())
        
        # Delete index data
        idx_key = f"_index:{table_name}:{index_name}".encode()
        self._transaction_delete(idx_key)
        
        return f"Index '{index_name}' dropped from '{table_name}'"
    
    def alter_add_constraint(self, table_name: str, constraint_type: str, constraint_def: Dict[str, Any]) -> str:
        """
        Add a constraint to a table.
        
        Args:
            table_name: Name of the table
            constraint_type: Type of constraint (FOREIGN_KEY, UNIQUE, CHECK)
            constraint_def: Constraint definition
        
        Returns:
            Success or error message
        """
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        schema_data = self._db.get(schema_key)
        if not schema_data:
            return f"Table '{table_name}' does not exist"
        
        schema = json.loads(schema_data.decode())
        
        if constraint_type == 'FOREIGN_KEY':
            # Validate column exists
            col = constraint_def.get('column')
            if col not in schema["columns"]:
                return f"ERROR: Column '{col}' does not exist"
            
            schema.setdefault("foreign_keys", []).append(constraint_def)
            
        elif constraint_type == 'UNIQUE':
            columns = constraint_def.get('columns', [])
            for col in columns:
                if col not in schema["columns"]:
                    return f"ERROR: Column '{col}' does not exist"
            
            schema.setdefault("unique_constraints", []).append(columns)
            
            # Create unique index
            idx_key = f"_unique_index:{table_name}:{':'.join(columns)}".encode()
            self._transaction_put(idx_key, json.dumps({}).encode())
            
        elif constraint_type == 'CHECK':



    # Parallel Query Execution Support (v3.4.0)
    def select_range(self, table_name: str, columns: List[str], 
                    start_row: int, end_row: int, 
                    where_clause: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Select a range of rows for parallel execution.
        
        Args:
            table_name: Table to query
            columns: Columns to select
            start_row: Starting row index
            end_row: Ending row index (exclusive)
            where_clause: Optional WHERE conditions
        
        Returns:
            List of rows in the specified range
        """
        if not self.current_db:
            raise ValueError("No database selected")
        
        # Get all rows for the table
        prefix = f"{self.current_db}:{table_name}:".encode()
        rows = []
        
        for key, value in self._db.iterator(prefix=prefix):
            try:
                row_data = json.loads(value.decode())
                row_data['_key'] = key.decode()
                rows.append(row_data)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
        
        # Sort by key for consistent ordering
        rows.sort(key=lambda x: x['_key'])
        
        # Return the requested range
        range_rows = rows[start_row:end_row]
        
        # Apply column filtering
        if columns != ['*']:
            filtered = []
            for row in range_rows:
                filtered_row = {col: row.get(col) for col in columns if col in row}
                filtered.append(filtered_row)
            range_rows = filtered
        
        # Apply WHERE clause if specified
        if where_clause:
            range_rows = self._apply_where(range_rows, where_clause)
        
        return range_rows
    
    def get_table_row_count(self, table_name: str) -> int:
        """
        Get estimated row count for a table.
        
        Args:
            table_name: Table name
        
        Returns:
            Number of rows in table
        """
        if not self.current_db:
            return 0
        
        prefix = f"{self.current_db}:{table_name}:".encode()
        count = 0
        
        for _ in self._db.iterator(prefix=prefix):
            count += 1
        
        return count
    
    def _apply_where(self, rows: List[Dict], where_clause: str) -> List[Dict]:
        """
        Apply WHERE clause to rows.
        
        Args:
            rows: List of rows
            where_clause: WHERE condition string
        
        Returns:
            Filtered rows
        """
        if not where_clause:
            return rows
        
        # Simple WHERE parsing (equality only)
        match = re.match(r'(\w+)\s*=\s*(.+)', where_clause)
        if not match:
            return rows
        
        column = match.group(1)
        value = match.group(2).strip().strip("'\"")
        
        # Try to convert value
        try:
            if '.' in value:
n                value = float(value)\n            else:\n                value = int(value)\n        except ValueError:\n            pass\n        \n        return [row for row in rows if row.get(column) == value]
    
    def execute_parallel(self, query: str, dop: int = 4) -> List[Dict]:
        """
        Execute query in parallel.
        
        Args:
            query: SQL query string
            dop: Degree of parallelism
        
        Returns:
            Query results
        """
n        try:\n            from parallel_executor import ParallelExecutor\n            \n            if not hasattr(self, '_parallel_executor'):\n                self._parallel_executor = ParallelExecutor(self)\n            \n            # Parse query to determine operation\n            query_upper = query.upper()\n            \n            if 'SELECT' in query_upper:\n                # Extract table and columns\n                match = re.search(r'FROM\\s+(\\w+)', query, re.IGNORECASE)\n                if match:\n                    table = match.group(1)\n                    \n                    # Check for aggregation\n                    if any(func in query_upper for func in ['SUM(', 'COUNT(', 'AVG(', 'MIN(', 'MAX(']):\n                        # Parallel aggregation\n                        return self._parallel_executor.execute_parallel_aggregation(\n                            table, [], None, None, dop\n                        )\n                    else:\n                        # Parallel scan\n                        return list(self._parallel_executor.execute_parallel_scan(\n                            table, ['*'], None, dop\n                        ))\n            \n            # Fall back to regular execution\n            return []\n            \n        except ImportError:\n            # Parallel execution not available\n            return []

            schema.setdefault("check_constraints", []).append(constraint_def.get('expression', ''))
        
        self._transaction_put(schema_key, json.dumps(schema).encode())
        
        return f"{constraint_type} constraint added to '{table_name}'"
    
    def alter_drop_constraint(self, table_name: str, constraint_name: str) -> str:
        """
        Drop a constraint from a table.
        
        Args:
            table_name: Name of the table
            constraint_name: Name or identifier of the constraint
        
        Returns:
            Success or error message
        """
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        schema_data = self._db.get(schema_key)
        if not schema_data:
            return f"Table '{table_name}' does not exist"
        
        schema = json.loads(schema_data.decode())
        
        # Try to find and remove constraint
        # Check foreign keys
        foreign_keys = schema.get("foreign_keys", [])
        for i, fk in enumerate(foreign_keys):
            if fk.get('column') == constraint_name:
                schema["foreign_keys"].pop(i)
                self._transaction_put(schema_key, json.dumps(schema).encode())
                return f"Foreign key constraint on '{constraint_name}' dropped"
        
        # Check unique constraints
        unique_constraints = schema.get("unique_constraints", [])
        for i, unique_cols in enumerate(unique_constraints):
            if ':'.join(unique_cols) == constraint_name or unique_cols[0] == constraint_name:
                schema["unique_constraints"].pop(i)
                idx_key = f"_unique_index:{table_name}:{':'.join(unique_cols)}".encode()
                self._transaction_delete(idx_key)
                self._transaction_put(schema_key, json.dumps(schema).encode())
                return f"Unique constraint on '{constraint_name}' dropped"
        
        return f"ERROR: Constraint '{constraint_name}' not found"
        """
        Validate unique constraints for a row.
        
        Args:
            table_name: Name of the table
            row: Row data to validate
            schema: Table schema
            exclude_row_key: Optional row key to exclude (for updates)
        
        Returns:
            (is_valid, error_message)
        """
        unique_constraints = schema.get('unique_constraints', [])
        
        for unique_cols in unique_constraints:
            # Build composite key
            composite_key = tuple(str(row.get(col)) for col in unique_cols)
            
            # Check unique index
            idx_key = f"_unique_index:{table_name}:{':'.join(unique_cols)}".encode()
            idx_data = self._db.get(idx_key)
            
            if idx_data:
                index_map = json.loads(idx_data.decode())
                
                # Check if key exists (excluding current row for updates)
                if str(composite_key) in index_map:
                    existing = index_map[str(composite_key)]
                    if isinstance(existing, list):
                        # If it's a list, check if any entry is not the excluded row
                        if exclude_row_key is None or any(e != exclude_row_key for e in existing):
                            return False, f"Unique constraint violation on {unique_cols}: {composite_key}"
                    elif existing != exclude_row_key:
                        return False, f"Unique constraint violation on {unique_cols}: {composite_key}"
        
        return True, None
    
    def _update_unique_indexes(self, table_name: str, row: Dict, row_key: str, schema: Dict, old_row: Optional[Dict] = None):
        """Update unique indexes for a row."""
        unique_constraints = schema.get('unique_constraints', [])
        
        for unique_cols in unique_constraints:
            idx_key = f"_unique_index:{table_name}:{':'.join(unique_cols)}".encode()
            idx_data = self._db.get(idx_key)
            
            if not idx_data:
                continue
            
            index_map = json.loads(idx_data.decode())
            
            # Remove old entry if updating
            if old_row:
                old_composite_key = tuple(str(old_row.get(col)) for col in unique_cols)
                if str(old_composite_key) in index_map:
                    existing = index_map[str(old_composite_key)]
                    if isinstance(existing, list):
                        index_map[str(old_composite_key)] = [e for e in existing if e != row_key]
                        if not index_map[str(old_composite_key)]:
                            del index_map[str(old_composite_key)]
                    else:
                        del index_map[str(old_composite_key)]
            
            # Add new entry
            composite_key = tuple(str(row.get(col)) for col in unique_cols)
            if str(composite_key) in index_map:
                existing = index_map[str(composite_key)]
                if isinstance(existing, list):
                    if row_key not in existing:
                        existing.append(row_key)
                else:
                    index_map[str(composite_key)] = [existing, row_key]
            else:
                index_map[str(composite_key)] = row_key
            
            self._transaction_put(idx_key, json.dumps(index_map).encode())
    
    def _validate_check_constraints(self, row: Dict, schema: Dict) -> Tuple[bool, Optional[str]]:
        """
        Validate CHECK constraints for a row.
        
        Args:
            row: Row data to validate
            schema: Table schema with check_constraints
        
        Returns:
            (is_valid, error_message)
        """
        check_constraints = schema.get('check_constraints', [])
        
        for check_expr in check_constraints:
            is_valid, error = self._evaluate_check_expression(check_expr, row)
            if not is_valid:
                return False, error
        
        return True, None
    
    def _evaluate_check_expression(self, expression: str, row: Dict) -> Tuple[bool, Optional[str]]:
        """
        Evaluate a CHECK expression against row data.
        
        Supports: =, !=, <>, <, >, <=, >=, IN, BETWEEN, LIKE, IS NULL, IS NOT NULL
        
        Args:
            expression: CHECK expression string
            row: Row data
        
        Returns:
            (is_valid, error_message)
        """
        expression = expression.strip()
        
        # Handle IS NULL / IS NOT NULL
        null_match = re.match(r'(\w+)\s+IS\s+(NOT\s+)?NULL$', expression, re.IGNORECASE)
        if null_match:
            col = null_match.group(1)
            is_not = null_match.group(2) is not None
            val = row.get(col)
            
            if is_not:
                # IS NOT NULL
                if val is None:
                    return False, f"CHECK constraint violation: {col} IS NOT NULL"
                return True, None
            else:
                # IS NULL
                if val is not None:
                    return False, f"CHECK constraint violation: {col} IS NULL"
                return True, None
        
        # Handle IN operator
        in_match = re.match(r'(\w+)\s+IN\s*\(([^)]+)\)$', expression, re.IGNORECASE)
        if in_match:
            col = in_match.group(1)
            values_str = in_match.group(2)
            allowed = [v.strip().strip("'\\\"") for v in values_str.split(',')]
            val = str(row.get(col, ''))
            
            if val not in allowed:
                return False, f"CHECK constraint violation: {col}={val} not in {allowed}"
            return True, None
        
        # Handle BETWEEN
        between_match = re.match(r'(\w+)\s+BETWEEN\s+(\S+)\s+AND\s+(\S+)$', expression, re.IGNORECASE)
        if between_match:
            col = between_match.group(1)
            low = self._parse_check_value(between_match.group(2))
            high = self._parse_check_value(between_match.group(3))
            val = row.get(col)
            
            if val is None:
                return True, None  # NULL passes CHECK constraints
            
            try:
                if not (low <= val <= high):
                    return False, f"CHECK constraint violation: {col}={val} not between {low} and {high}"
            except TypeError:
                return False, f"CHECK constraint violation: cannot compare {col}={val}"
            return True, None
        
        # Handle LIKE
        like_match = re.match(r'(\w+)\s+LIKE\s+[\\'\"]([^\\'\"]+)[\\'\"]$', expression, re.IGNORECASE)
        if like_match:
            col = like_match.group(1)
            pattern = like_match.group(2)
            val = str(row.get(col, ''))
            
            if not self._like_match(val, pattern):
                return False, f"CHECK constraint violation: {col}='{val}' not LIKE '{pattern}'"
            return True, None
        
        # Handle comparison operators
        comp_match = re.match(r'(\w+)\s*(=|!=|<>|<=|>=|<|>)\s*(.+)$', expression)
        if comp_match:
            col = comp_match.group(1)
            op = comp_match.group(2)
            expected_str = comp_match.group(3).strip()
            expected = self._parse_check_value(expected_str)
            actual = row.get(col)
            
            if actual is None:
                return True, None  # NULL passes CHECK constraints
            
            try:
                if op == '=':
                    if actual != expected:
                        return False, f"CHECK constraint violation: {col}={actual} != {expected}"
                elif op in ('!=', '<>'):
                    if actual == expected:
                        return False, f"CHECK constraint violation: {col}={actual} == {expected}"
                elif op == '<':
                    if not (actual < expected):
                        return False, f"CHECK constraint violation: {col}={actual} not < {expected}"
                elif op == '>':
                    if not (actual > expected):
                        return False, f"CHECK constraint violation: {col}={actual} not > {expected}"
                elif op == '<=':
                    if not (actual <= expected):
                        return False, f"CHECK constraint violation: {col}={actual} not <= {expected}"
                elif op == '>=':
                    if not (actual >= expected):
                        return False, f"CHECK constraint violation: {col}={actual} not >= {expected}"
            except TypeError:
                return False, f"CHECK constraint violation: cannot compare {col}={actual} with {expected}"
            
            return True, None
        
        # Unknown expression
        return True, None  # Be permissive for unknown expressions
    
    def _parse_check_value(self, val_str: str) -> Any:
        """Parse value from CHECK expression."""
        val_str = val_str.strip()
        
        # String literal
        if (val_str.startswith("'") and val_str.endswith("'")) or \
           (val_str.startswith('"') and val_str.endswith('"')):
            return val_str[1:-1]
        
        # Number
        try:
            if '.' in val_str:
                return float(val_str)
            return int(val_str)
        except ValueError:
            pass
        
        # Boolean/NULL
        upper = val_str.upper()
        if upper == 'TRUE':
            return True
        if upper == 'FALSE':
            return False
        if upper == 'NULL':
            return None
        
        return val_str
    
    def _like_match(self, value: str, pattern: str) -> bool:
        """Match value against SQL LIKE pattern."""
        # Convert SQL LIKE pattern to regex
        # % matches any sequence, _ matches single character
        regex_pattern = pattern.replace('%', '.*').replace('_', '.')
        regex_pattern = '^' + regex_pattern + '$'
        
        try:
            return bool(re.match(regex_pattern, value, re.IGNORECASE))
        except re.error:
            return False
    
    def _validate_json_column(self, col_name: str, value: Any, column_types: Dict[str, str]) -> Tuple[bool, Optional[str]]:
        """
        Validate JSON column value.
        
        Args:
            col_name: Column name
            value: Value to validate
            column_types: Dictionary of column types
        
        Returns:
            (is_valid, error_message)
        """
        col_type = column_types.get(col_name, 'TEXT')
        if col_type.upper() == 'JSON':
            if value is not None and not validate_json(value):
                return False, f"Invalid JSON value for column '{col_name}'"
        return True, None
    
    def insert(self, table_name: str, values: List[Any]) -> str:
        """Insert a row into a table with FK, CHECK, and JSON validation."""
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
        
        # Validate JSON columns
        column_types = schema.get('column_types', {})
        for col in schema["columns"]:
            if col in row:
                is_valid, error = self._validate_json_column(col, row[col], column_types)
                if not is_valid:
                    return f"ERROR: {error}"
        
        # Validate CHECK constraints
        is_valid, error = self._validate_check_constraints(row, schema)
        if not is_valid:
            return f"ERROR: {error}"
        
        # Validate unique constraints
        is_unique, error = self._validate_unique_constraints(table_name, row, schema)
        if not is_unique:
            return f"ERROR: {error}"
        
        # Validate foreign keys
        foreign_keys = schema.get('foreign_keys', [])
        for fk in foreign_keys:
            fk_column = fk['column']
            if fk_column in row:
                is_valid, error = self._validate_foreign_key(fk, row[fk_column])
                if not is_valid:
                    return f"ERROR: {error}"
        
        primary_key = schema.get("primary_key")
        if primary_key and primary_key in row:
            store_key = str(row[primary_key])
        else:
            store_key = row_id
        
        key = self._make_key(table_name, store_key)
        self._transaction_put(key, json.dumps(row).encode())
        
        self._update_indexes(table_name, row, store_key, schema)
        self._update_unique_indexes(table_name, row, store_key, schema)
        
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
                    if val in index_map:
                        if isinstance(index_map[val], list):
                            if row_key not in index_map[val]:
                                index_map[val].append(row_key)
                        else:
                            index_map[val] = [index_map[val], row_key]
                    else:
                        index_map[val] = row_key
                    self._transaction_put(idx_key, json.dumps(index_map).encode())
    
    def select(self, table_name: str, columns: Optional[List] = None,
               where: Optional[Dict[str, Any]] = None,
               order_by: Optional[str] = None,
               order_desc: bool = False,
               raw: bool = False) -> Any:
        """Select rows from a table with JSON extraction support."""
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        if not self._db.get(schema_key):
            return f"Table '{table_name}' does not exist"
        
        schema = json.loads(self._db.get(schema_key).decode())
        
        select_columns = []
        if columns:
            for col_spec in columns:
                if isinstance(col_spec, dict):
                    col_name = col_spec.get('name')
                    if col_name in schema["columns"] or col_name == "*":
                        select_columns.append(
                            col_spec.get('alias') or col_name
                        )
                    elif col_spec.get('alias'):
                        select_columns.append(col_spec['alias'])
                    else:
                        select_columns.append(col_name)
                else:
                    select_columns.append(col_spec)
        else:
            select_columns = schema["columns"]
        
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
        
        # Apply JSON extractions and format results
        filtered_results = []
        for row in results:
            filtered_row = {}
            
            # Handle regular columns
            for col_spec in columns or [{"name": c} for c in select_columns]:
                if isinstance(col_spec, dict):
                    col_name = col_spec.get('name')
                    
                    if col_spec.get('json_path'):
n                        # JSON extraction
                        json_col = col_spec['name']
                        json_path = col_spec['json_path']
                        as_text = col_spec.get('json_as_text', False)
                        
                        if json_col in row:
                            json_data = row[json_col]
                            if as_text:
                                extracted = json_extract_text(json_data, json_path)
                            else:
                                extracted = json_extract(json_data, json_path)
                            
                            alias = col_spec.get('alias') or f"{json_col}->{json_path}"
                            filtered_row[alias] = extracted if extracted is not None else "NULL"
                        else:
                            alias = col_spec.get('alias') or f"{json_col}->{json_path}"
                            filtered_row[alias] = "NULL"
                    elif col_spec.get('alias'):
                        # Regular column with alias
                        filtered_row[col_spec['alias']] = row.get(col_name, "NULL")
                    else:
                        # Regular column
                        filtered_row[col_name] = row.get(col_name, "NULL")
                else:
                    # Simple column name
                    filtered_row[col_spec] = row.get(col_spec, "NULL")
            
            filtered_results.append(filtered_row)
        
        # Get final column list for formatting
        final_columns = list(filtered_results[0].keys()) if filtered_results else []
        return self._format_results(final_columns, filtered_results)
    
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
        """Update rows in a table with FK, CHECK, unique, and JSON constraint validation."""
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
        
        foreign_keys = schema.get('foreign_keys', [])
        column_types = schema.get('column_types', {})
        
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
            
            # Validate JSON columns in set_clause
            for col, val in set_clause.items():
                is_valid, error = self._validate_json_column(col, val, column_types)
                if not is_valid:
                    return f"ERROR: {error}"
            
            # Build new row for constraint validation
            new_row = row.copy()
            for col, val in set_clause.items():
                new_row[col] = val
            
            # Validate CHECK constraints
            is_valid, error = self._validate_check_constraints(new_row, schema)
            if not is_valid:
                return f"ERROR: {error}"
            
            # Validate unique constraints
            primary_key = schema.get("primary_key")
            store_key = str(row[primary_key]) if primary_key and primary_key in row else row.get("id")
            is_unique, error = self._validate_unique_constraints(table_name, new_row, schema, exclude_row_key=store_key)
            if not is_unique:
                return f"ERROR: {error}"
            
            # Check FK constraints for new values
            for fk in foreign_keys:
                fk_column = fk['column']
                if fk_column in set_clause:
                    is_valid, error = self._validate_foreign_key(fk, set_clause[fk_column])
                    if not is_valid:
                        return f"ERROR: {error}"
            
            old_key_val = None
            if primary_key and primary_key in set_clause:
                old_key_val = row.get(primary_key)
            
            for col, val in set_clause.items():
                row[col] = val
            
            self._transaction_put(key, json.dumps(row).encode())
            
            if old_key_val is not None and primary_key:
                self._update_indexes(table_name, row, str(row[primary_key]), schema)
            
            self._update_unique_indexes(table_name, new_row, store_key, schema, old_row=row)
            
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
        """Delete rows from a table with FK constraint checking."""
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        schema_data = self._db.get(schema_key)
        if not schema_data:
            return f"Table '{table_name}' does not exist"
        
        schema = json.loads(schema_data.decode())
        
        # Check for referencing tables before deleting
        referencing = self._get_referencing_tables(table_name)
        
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
            
            # Check FK constraints - if any referencing rows exist
            for ref in referencing:
                ref_column = ref['fk_def']['references_column']
                if ref_column in schema.get('columns', []):
                    ref_value = row.get(ref_column)
                    # Check if any rows in referencing table reference this value
                    ref_prefix = f"{ref['table']}:".encode()
                    for ref_key, ref_data in self._db.iterator(prefix=ref_prefix):
                        if ref_key.startswith(f"_schema:{ref['table']}".encode()):
                            continue
                        ref_row = json.loads(ref_data.decode())
                        if str(ref_row.get(ref['column'])) == str(ref_value):
                            fk_def = ref['fk_def']
                            on_delete = fk_def.get('on_delete', 'RESTRICT')
                            
                            if on_delete == 'RESTRICT':
                                return f"ERROR: Cannot delete row: referenced by {ref['table']}.{ref['column']} (ON DELETE RESTRICT)"
                            elif on_delete == 'NO_ACTION':
                                return f"ERROR: Cannot delete row: referenced by {ref['table']}.{ref['column']} (ON DELETE NO ACTION)"
                            # CASCADE and SET_NULL handled separately
            
            keys_to_delete.append(key)
            deleted_rows.append(row.copy())
        
        # Handle CASCADE and SET_NULL for referencing tables
        for row in deleted_rows:
            for ref in referencing:
                ref_column = ref['fk_def']['references_column']
                if ref_column in schema.get('columns', []):
                    ref_value = row.get(ref_column)
                    on_delete = ref['fk_def'].get('on_delete', 'RESTRICT')
                    
                    if on_delete == 'CASCADE':
                        # Delete referencing rows
                        self._delete_by_fk_value(ref['table'], ref['column'], ref_value)
                    elif on_delete == 'SET_NULL':
                        # Set referencing column to NULL
                        self._update_by_fk_value(ref['table'], ref['column'], ref_value, {ref['column']: None})
        
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
    
    def _delete_by_fk_value(self, table_name: str, column: str, value: Any):
        """Delete all rows in table where column equals value."""
        prefix = f"{table_name}:".encode()
        keys_to_delete = []
        
        for key, data in self._db.iterator(prefix=prefix):
            if key.startswith(f"_schema:{table_name}".encode()):
                continue
            
            row = json.loads(data.decode())
            if str(row.get(column)) == str(value):
                keys_to_delete.append(key)
        
        for key in keys_to_delete:
            self._transaction_delete(key)
    
    def _update_by_fk_value(self, table_name: str, column: str, value: Any, set_clause: Dict[str, Any]):
        """Update all rows in table where column equals value."""
        prefix = f"{table_name}:".encode()
        
        for key, data in self._db.iterator(prefix=prefix):
            if key.startswith(f"_schema:{table_name}".encode()):
                continue
            
            row = json.loads(data.decode())
            if str(row.get(column)) == str(value):
                for col, val in set_clause.items():
                    row[col] = val
                self._transaction_put(key, json.dumps(row).encode())
    
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
