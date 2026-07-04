#!/usr/bin/env python3
"""
LevelDB Socket Server - Python Client Library

A comprehensive Python client for connecting to the LevelDB Socket Server.
Supports synchronous and asynchronous operations, connection pooling,
and result parsing.

Author: LevelDB Team
Version: 1.0.0
"""

import socket
import json
import re
from typing import List, Dict, Optional, Union, Any
from contextlib import contextmanager


class LevelDBClient:
    """
    Synchronous client for LevelDB Socket Server.
    
    Example:
        client = LevelDBClient('localhost', 9999)
        client.connect()
        client.auth('admin', 'admin')
        client.create_database('myapp')
        client.use('myapp')
        result = client.query("SELECT * FROM users")
    """
    
    def __init__(self, host: str = 'localhost', port: int = 9999, 
                 timeout: int = 30, encoding: str = 'utf-8'):
        """
        Initialize client.
        
        Args:
            host: Server hostname
            port: Server port
            timeout: Connection timeout in seconds
            encoding: Character encoding
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.encoding = encoding
        self.socket: Optional[socket.socket] = None
        self._connected = False
        self._authenticated = False
        self._current_db: Optional[str] = None
    
    def connect(self) -> 'LevelDBClient':
        """
        Connect to the server.
        
        Returns:
            self for method chaining
            
        Raises:
            ConnectionError: If connection fails
        """
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.timeout)
            self.socket.connect((self.host, self.port))
            
            # Read welcome banner
            self._read_lines(6)
            
            self._connected = True
            return self
            
        except Exception as e:
            raise ConnectionError(f"Failed to connect: {e}")
    
    def auth(self, username: str, password: str) -> bool:
        """
        Authenticate with the server.
        
        Args:
            username: Username
            password: Password
            
        Returns:
            True if authentication successful
            
        Raises:
            AuthenticationError: If authentication fails
        """
        if not self._connected:
            raise ConnectionError("Not connected")
        
        # Send USER command
        self._send(f"USER {username}")
        response = self._read_line()
        
        if not response.startswith("OK"):
            raise AuthenticationError(f"USER command failed: {response}")
        
        # Send PASS command
        self._send(f"PASS {password}")
        response = self._read_line()
        
        if not response.startswith("OK"):
            raise AuthenticationError(f"Authentication failed: {response}")
        
        self._authenticated = True
        return True
    
    def execute(self, sql: str) -> str:
        """
        Execute a SQL-like command.
        
        Args:
            sql: Command to execute
            
        Returns:
            Raw response string
            
        Raises:
            ConnectionError: If not authenticated
        """
        if not self._authenticated:
            raise ConnectionError("Not authenticated")
        
        self._send(sql)
        return self._read_response()
    
    def query(self, sql: str) -> List[Dict[str, Any]]:
        """
        Execute a SELECT query and return parsed results.
        
        Args:
            sql: SELECT query
            
        Returns:
            List of dictionaries representing rows
        """
        result = self.execute(sql)
        return self._parse_select_result(result)
    
    # Convenience methods
    
    def create_database(self, name: str) -> str:
        """Create a database."""
        return self.execute(f"CREATE DATABASE {name}")
    
    def drop_database(self, name: str) -> str:
        """Drop a database."""
        result = self.execute(f"DROP DATABASE {name}")
        if self._current_db == name:
            self._current_db = None
        return result
    
    def use(self, name: str) -> str:
        """Select database to use."""
        result = self.execute(f"USE {name}")
        self._current_db = name
        return result
    
    def create_table(self, name: str, columns: List[str]) -> str:
        """
        Create a table.
        
        Args:
            name: Table name
            columns: List of column definitions
        """
        cols = ", ".join(columns)
        return self.execute(f"CREATE TABLE {name} ({cols})")
    
    def drop_table(self, name: str) -> str:
        """Drop a table."""
        return self.execute(f"DROP TABLE {name}")
    
    def insert(self, table: str, values: List[Any]) -> str:
        """
        Insert values into table.
        
        Args:
            table: Table name
            values: List of values
        """
        vals = []
        for v in values:
            if isinstance(v, str):
                vals.append(f"'{v}'")
            else:
                vals.append(str(v))
        val_str = ", ".join(vals)
        return self.execute(f"INSERT INTO {table} VALUES ({val_str})")
    
    def select(self, table: str, where: Optional[str] = None,
               columns: Optional[List[str]] = None,
               order_by: Optional[str] = None,
               desc: bool = False) -> List[Dict[str, Any]]:
        """
        Select from table.
        
        Args:
            table: Table name
            where: Optional WHERE clause
            columns: Optional column list (default: all)
            order_by: Optional ORDER BY column
            desc: Sort descending
            
        Returns:
            List of row dictionaries
        """
        cols = ", ".join(columns) if columns else "*"
        sql = f"SELECT {cols} FROM {table}"
        
        if where:
            sql += f" WHERE {where}"
        
        if order_by:
            sql += f" ORDER BY {order_by}"
            if desc:
                sql += " DESC"
        
        return self.query(sql)
    
    def update(self, table: str, set_clause: str, where: Optional[str] = None) -> str:
        """
        Update rows.
        
        Args:
            table: Table name
            set_clause: SET clause (e.g., "name='New'")
            where: Optional WHERE clause
        """
        sql = f"UPDATE {table} SET {set_clause}"
        if where:
            sql += f" WHERE {where}"
        return self.execute(sql)
    
    def delete(self, table: str, where: Optional[str] = None) -> str:
        """
        Delete rows.
        
        Args:
            table: Table name
            where: Optional WHERE clause
        """
        sql = f"DELETE FROM {table}"
        if where:
            sql += f" WHERE {where}"
        return self.execute(sql)
    
    def list_databases(self) -> List[str]:
        """List all databases."""
        result = self.execute("SHOW DATABASES")
        return self._parse_list_result(result)
    
    def list_tables(self) -> List[str]:
        """List tables in current database."""
        result = self.execute("SHOW TABLES")
        return self._parse_list_result(result)
    
    def show_master_status(self) -> str:
        """Show replication master status."""
        return self.execute("SHOW MASTER STATUS")
    
    def show_slave_status(self) -> str:
        """Show replication slave status."""
        return self.execute("SHOW SLAVE STATUS")
    
    def start_slave(self) -> str:
        """Start replication slave."""
        return self.execute("START SLAVE")
    
    def stop_slave(self) -> str:
        """Stop replication slave."""
        return self.execute("STOP SLAVE")
    
    def reset_slave(self) -> str:
        """Reset replication slave."""
        return self.execute("RESET SLAVE")
    
    def create_replication_user(self, username: str, password: str) -> str:
        """Create replication user."""
        return self.execute(f"CREATE REPLICATION USER {username} IDENTIFIED BY {password}")
    
    def close(self) -> None:
        """Close connection."""
        if self.socket:
            try:
                self._send("QUIT")
            except:
                pass
            finally:
                self.socket.close()
                self.socket = None
                self._connected = False
                self._authenticated = False
    
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected
    
    def is_authenticated(self) -> bool:
        """Check if authenticated."""
        return self._authenticated
    
    def current_database(self) -> Optional[str]:
        """Get current database name."""
        return self._current_db
    
    # Private methods
    
    def _send(self, cmd: str) -> None:
        """Send command to server."""
        self.socket.sendall(f"{cmd}\n".encode(self.encoding))
    
    def _read_line(self) -> str:
        """Read a line from socket."""
        data = self.socket.recv(4096)
        if not data:
            raise ConnectionError("Connection closed by server")
        return data.decode(self.encoding).strip()
    
    def _read_lines(self, count: int) -> List[str]:
        """Read multiple lines."""
        return [self._read_line() for _ in range(count)]
    
    def _read_response(self) -> str:
        """Read complete response."""
        response = []
        start_time = __import__('time').time()
        
        while True:
            # Timeout check
            if __import__('time').time() - start_time > self.timeout:
                raise TimeoutError("Read timeout")
            
            line = self._read_line()
            
            if not line:
                continue
            
            response.append(line)
            
            # End markers
            if (line.startswith(("OK:", "ERROR:", "BYE")) or
                "row(s) in set" in line or
                line == "Empty set"):
                break
        
        return "\n".join(response)
    
    def _parse_select_result(self, text: str) -> List[Dict[str, Any]]:
        """
        Parse SELECT result into list of dictionaries.
        
        Args:
            text: Raw response text
            
        Returns:
            List of row dictionaries
        """
        lines = text.strip().split("\n")
        rows = []
        headers = []
        
        for line in lines:
            line = line.strip()
            
            # Skip separators
            if line.startswith("+-"):
                continue
            
            # Parse header
            if line.startswith("|") and not headers:
                headers = [h.strip() for h in line.split("|")[1:-1]]
                continue
            
            # Parse data row
            if line.startswith("|") and headers:
                values = [v.strip() for v in line.split("|")[1:-1]]
                if len(values) == len(headers):
                    row = {}
                    for i, header in enumerate(headers):
                        # Try to convert to int/float
                        val = values[i]
                        if val == "NULL":
                            row[header] = None
                        else:
                            try:
                                row[header] = int(val)
                            except ValueError:
                                try:
                                    row[header] = float(val)
                                except ValueError:
                                    row[header] = val
                    rows.append(row)
        
        return rows
    
    def _parse_list_result(self, text: str) -> List[str]:
        """Parse SHOW DATABASES/TABLES result."""
        lines = text.strip().split("\n")
        items = []
        for line in lines:
            if line.startswith("OK:"):
                continue
            if line.strip():
                items.append(line.strip())
        return items
    
    def __enter__(self) -> 'LevelDBClient':
        """Context manager entry."""
        return self.connect()
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Context manager exit."""
        self.close()
        return False
    
    def __repr__(self) -> str:
        return f"LevelDBClient({self.host}:{self.port})"


class AuthenticationError(Exception):
    """Authentication failed."""
    pass


# Context manager for easy connection handling
@contextmanager
def connect(host: str = 'localhost', port: int = 9999,
            username: str = 'admin', password: str = 'admin'):
    """
    Context manager for database connections.
    
    Example:
        with connect('localhost', 9999, 'admin', 'admin') as db:
            db.create_database('test')
            result = db.select('users')
    """
    client = LevelDBClient(host, port)
    try:
        client.connect()
        client.auth(username, password)
        yield client
    finally:
        client.close()


# Async client for high-performance applications
class AsyncLevelDBClient:
    """
    Async client for LevelDB Socket Server.
    Requires Python 3.7+ with asyncio.
    """
    
    def __init__(self, host: str = 'localhost', port: int = 9999):
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None
    
    async def connect(self):
        """Connect to server."""
        self.reader, self.writer = await __import__('asyncio').open_connection(
            self.host, self.port
        )
        # Read welcome
        for _ in range(6):
            await self.reader.readline()
        return self
    
    async def auth(self, username: str, password: str) -> bool:
        """Authenticate."""
        self.writer.write(f"USER {username}\n".encode())
        await self.writer.drain()
        await self.reader.readline()
        
        self.writer.write(f"PASS {password}\n".encode())
        await self.writer.drain()
        response = (await self.reader.readline()).decode()
        return response.startswith("OK")
    
    async def execute(self, sql: str) -> str:
        """Execute command."""
        self.writer.write(f"{sql}\n".encode())
        await self.writer.drain()
        
        response = []
        while True:
            line = (await self.reader.readline()).decode().strip()
            response.append(line)
            if line.startswith(("OK:", "ERROR:")):
                break
        return "\n".join(response)
    
    async def close(self):
        """Close connection."""
        if self.writer:
            self.writer.write(b"QUIT\n")
            await self.writer.drain()
            self.writer.close()
            await self.writer.wait_closed()
    
    async def __aenter__(self):
        return await self.connect()
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        return False


if __name__ == '__main__':
    # Demo usage
    print("LevelDB Python Client Library")
    print("=" * 50)
    print("\nExample usage:")
    print("  from leveldb_client import LevelDBClient, connect")
    print("  ")
    print("  # Method 1: Direct")
    print("  client = LevelDBClient('localhost', 9999)")
    print("  client.connect()")
    print("  client.auth('admin', 'admin')")
    print("  result = client.query('SELECT * FROM users')")
    print("  client.close()")
    print("  ")
    print("  # Method 2: Context manager (recommended)")
    print("  with connect('localhost', 9999, 'admin', 'admin') as db:")
    print("      result = db.select('users')")
    print("      print(result)")