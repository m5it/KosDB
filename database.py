"""LevelDB database layer with CRUD operations."""

import os
import json
import plyvel
from typing import Optional, Dict, Any, List


class LevelDBWrapper:
    """Wrapper for LevelDB providing MySQL-like database operations."""
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.current_db: Optional[str] = None
        self._db: Optional[plyvel.DB] = None
        self._ensure_data_dir()
    
    def _ensure_data_dir(self):
        """Ensure data directory exists."""
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
    
    def _db_path(self, db_name: str) -> str:
        """Get path for a database."""
        return os.path.join(self.data_dir, db_name)
    
    def _make_key(self, table: str, key: str) -> bytes:
        """Create a composite key for table storage."""
        return f"{table}:{key}".encode()
    
    def create_database(self, db_name: str) -> str:
        """Create a new database (LevelDB instance)."""
        db_path = self._db_path(db_name)
        if os.path.exists(db_path):
            return f"Database '{db_name}' already exists"
        
        # Create the database by opening and closing it
        db = plyvel.DB(db_path, create_if_missing=True)
        db.close()
        return f"Database '{db_name}' created successfully"
    
    def drop_database(self, db_name: str) -> str:
        """Delete a database."""
        db_path = self._db_path(db_name)
        if not os.path.exists(db_path):
            return f"Database '{db_name}' does not exist"
        
        # Close current db if it's the one being dropped
        if self.current_db == db_name and self._db:
            self._db.close()
            self._db = None
            self.current_db = None
        
        # Remove database directory
        import shutil
        shutil.rmtree(db_path)
        return f"Database '{db_name}' dropped successfully"
    
    def use_database(self, db_name: str) -> str:
        """Switch to a database."""
        db_path = self._db_path(db_name)
        if not os.path.exists(db_path):
            return f"Database '{db_name}' does not exist"
        
        # Close current database if open
        if self._db:
            self._db.close()
        
        # Open new database
        self._db = plyvel.DB(db_path, create_if_missing=True)
        self.current_db = db_name
        return f"Switched to database '{db_name}'"
    
    def create_table(self, table_name: str, columns: List[str]) -> str:
        """Create a table (stores schema metadata)."""
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        if self._db.get(schema_key):
            return f"Table '{table_name}' already exists"
        
        schema = {"columns": columns, "next_id": 1}
        self._db.put(schema_key, json.dumps(schema).encode())
        return f"Table '{table_name}' created successfully"
    
    def drop_table(self, table_name: str) -> str:
        """Drop a table and all its data."""
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        if not self._db.get(schema_key):
            return f"Table '{table_name}' does not exist"
        
        # Delete all entries for this table
        prefix = f"{table_name}:".encode()
        for key, _ in self._db.iterator(prefix=prefix):
            self._db.delete(key)
        
        # Delete schema
        self._db.delete(schema_key)
        return f"Table '{table_name}' dropped successfully"
    
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
        
        # Create row data
        row = {"id": row_id}
        for i, col in enumerate(schema["columns"]):
            if i < len(values):
                row[col] = values[i]
        
        # Store row
        key = self._make_key(table_name, row_id)
        self._db.put(key, json.dumps(row).encode())
        
        # Update next_id
        schema["next_id"] += 1
        self._db.put(schema_key, json.dumps(schema).encode())
        
        return f"Inserted 1 row into '{table_name}'"
    
    def select(self, table_name: str, columns: Optional[List[str]] = None, 
               where: Optional[Dict[str, Any]] = None) -> str:
        """Select rows from a table."""
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        schema_data = self._db.get(schema_key)
        if not schema_data:
            return f"Table '{table_name}' does not exist"
        
        schema = json.loads(schema_data.decode())
        if columns is None or "*" in columns:
            columns = ["id"] + schema["columns"]
        
        results = []
        prefix = f"{table_name}:".encode()
        
        for key, value in self._db.iterator(prefix=prefix):
            if key.startswith(f"_schema:{table_name}".encode()):
                continue
            
            row = json.loads(value.decode())
            
            # Apply WHERE clause
            if where:
                match = True
                for col, val in where.items():
                    if str(row.get(col)) != str(val):
                        match = False
                        break
                if not match:
                    continue
            
            # Select only requested columns
            selected_row = {col: row.get(col, "NULL") for col in columns}
            results.append(selected_row)
        
        if not results:
            return "Empty set"
        
        # Format results as table
        return self._format_results(columns, results)
    
    def update(self, table_name: str, set_clause: Dict[str, Any], 
               where: Optional[Dict[str, Any]] = None) -> str:
        """Update rows in a table."""
        if not self._db:
            return "No database selected. Use USE <database>"
        
        schema_key = f"_schema:{table_name}".encode()
        schema_data = self._db.get(schema_key)
        if not schema_data:
            return f"Table '{table_name}' does not exist"
        
        updated = 0
        prefix = f"{table_name}:".encode()
        
        for key, value in self._db.iterator(prefix=prefix):
            if key.startswith(f"_schema:{table_name}".encode()):
                continue
            
            row = json.loads(value.decode())
            
            # Apply WHERE clause
            if where:
                match = True
                for col, val in where.items():
                    if str(row.get(col)) != str(val):
                        match = False
                        break
                if not match:
                    continue
            
            # Update row
            for col, val in set_clause.items():
                row[col] = val
            
            self._db.put(key, json.dumps(row).encode())
            updated += 1
        
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
        prefix = f"{table_name}:".encode()
        
        for key, value in self._db.iterator(prefix=prefix):
            if key.startswith(f"_schema:{table_name}".encode()):
                continue
            
            row = json.loads(value.decode())
            
            # Apply WHERE clause
            if where:
                match = True
                for col, val in where.items():
                    if str(row.get(col)) != str(val):
                        match = False
                        break
                if not match:
                    continue
            
            keys_to_delete.append(key)
        
        for key in keys_to_delete:
            self._db.delete(key)
            deleted += 1
        
        return f"Deleted {deleted} row(s) from '{table_name}'"
    
    def _format_results(self, columns: List[str], results: List[Dict]) -> str:
        """Format query results as a table string."""
        if not results:
            return "Empty set"
        
        # Calculate column widths
        widths = {}
        for col in columns:
            widths[col] = len(col)
        
        for row in results:
            for col in columns:
                val_str = str(row.get(col, "NULL"))
                widths[col] = max(widths[col], len(val_str))
        
        # Build output
        lines = []
        
        # Header
        header = "| " + " | ".join(col.ljust(widths[col]) for col in columns) + " |"
        separator = "+" + "+".join("-" * (widths[col] + 2) for col in columns) + "+"
        
        lines.append(separator)
        lines.append(header)
        lines.append(separator)
        
        # Rows
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
        if self._db:
            self._db.close()
            self._db = None
            self.current_db = None
