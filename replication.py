"""
Replication Protocol for LevelDB Socket Server

Implements master-slave and master-master replication over TCP sockets.
"""

import socket
import threading
import json
import time
from typing import Optional, Dict, Any, List
from database import Database


class ReplicationClient(threading.Thread):
    """
    Replication client that runs on slave servers.
    Connects to master and streams binlog entries.
    """
    
    def __init__(self, master_host: str, master_port: int, 
                 username: str, password: str,
                 db: Database, server_id: int):
        super().__init__(daemon=True)
        self.master_host = master_host
        self.master_port = master_port
        self.username = username
        self.password = password
        self.db = db
        self.server_id = server_id
        
        self.socket: Optional[socket.socket] = None
        self.running = False
        self.connected = False
        self.last_position = 0
        self.reconnect_delay = 5  # seconds
        self.max_reconnect_delay = 60  # max backoff
    
    def load_position(self) -> int:
        """Load last applied position from disk."""
        try:
            if self.db._system_db:
                pos_data = self.db._system_db.get(b"_replication:last_position")
                if pos_data:
                    return int(pos_data.decode())
        except Exception as e:
            print(f"[REPLICATION] Error loading position: {e}")
        return 0
    
    def save_position(self, position: int):
        """Save last applied position to disk."""
        try:
            if self.db._system_db:
                self.db._system_db.put(
                    b"_replication:last_position", 
                    str(position).encode()
                )
                self.last_position = position
        except Exception as e:
            print(f"[REPLICATION] Error saving position: {e}")
    
    def connect(self) -> bool:
        """Connect to master server."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(30)
            self.socket.connect((self.master_host, self.master_port))
            
            # Authenticate as replication user
            auth_msg = f"REPL AUTH {self.username} {self.password}\n"
            self.socket.sendall(auth_msg.encode())
            
            response = self.socket.recv(4096).decode().strip()
            if not response.startswith("OK"):
                print(f"[REPLICATION] Auth failed: {response}")
                return False
            
            # Request binlog stream from last position
            self.last_position = self.load_position()
            stream_msg = f"REPL STREAM FROM {self.last_position}\n"
            self.socket.sendall(stream_msg.encode())
            
            response = self.socket.recv(4096).decode().strip()
            if not response.startswith("OK"):
                print(f"[REPLICATION] Stream request failed: {response}")
                return False
            
            self.connected = True
            self.reconnect_delay = 5  # Reset backoff
            print(f"[REPLICATION] Connected to master at {self.master_host}:{self.master_port}")
            print(f"[REPLICATION] Starting from position {self.last_position}")
            return True
            
        except Exception as e:
            print(f"[REPLICATION] Connection failed: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from master."""
        self.connected = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
    
    def apply_entry(self, entry: Dict) -> bool:
        """
        Apply a binlog entry to local database.
        Skip entries from our own server_id (loop prevention).
        """
        # Skip our own entries (for master-master)
        if entry.get('server_id') == self.server_id:
            return True
        
        try:
            op = entry['operation']
            db_name = entry['database']
            table = entry.get('table')
            data = entry.get('data', {})
            
            # Ensure we're using the correct database
            if db_name and self.db.current_db != db_name:
                self.db.use_database(db_name)
            
            # Apply based on operation type
            if op == 'INSERT':
                if table and 'row' in data:
                    # Reconstruct values from row
                    row = data['row']
                    # Get schema to determine column order
                    schema_key = f"_schema:{table}".encode()
                    schema_data = self.db._db.get(schema_key)
                    if schema_data:
                        schema = json.loads(schema_data.decode())
                        values = [row.get(col) for col in schema['columns']]
                        self.db.insert(table, values)
            
            elif op == 'UPDATE':
                if table and 'set_clause' in data:
                    self.db.update(table, data['set_clause'], data.get('where'))
            
            elif op == 'DELETE':
                if table:
                    self.db.delete(table, data.get('where'))
            
            elif op == 'CREATE_DB':
                if 'db_name' in data:
                    self.db.create_database(data['db_name'])
            
            elif op == 'DROP_DB':
                if 'db_name' in data:
                    self.db.drop_database(data['db_name'])
            
            elif op == 'CREATE_TABLE':
                if 'table_name' in data and 'columns' in data:
                    self.db.create_table(data['table_name'], data['columns'])
            
            elif op == 'DROP_TABLE':
                if 'table_name' in data:
                    self.db.drop_table(data['table_name'])
            
            # Save position after successful apply
            self.save_position(entry['position'])
            return True
            
        except Exception as e:
            print(f"[REPLICATION] Error applying entry {entry.get('position')}: {e}")
            return False
    
    def run(self):
        """Main replication loop."""
        self.running = True
        
        while self.running:
            if not self.connected:
                if not self.connect():
                    # Backoff and retry
                    print(f"[REPLICATION] Retrying in {self.reconnect_delay}s...")
                    time.sleep(self.reconnect_delay)
                    self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)
                    continue
            
            try:
                # Read binlog entry from master
                data = self.socket.recv(4096)
                if not data:
                    print("[REPLICATION] Connection closed by master")
                    self.disconnect()
                    continue
                
                # Parse entry (may be multiple lines)
                lines = data.decode().strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    if line.startswith("REPL ENTRY"):
                        # Parse: REPL ENTRY position timestamp server_id db table op {data}
                        parts = line.split(' ', 7)
                        if len(parts) >= 7:
                            entry = {
                                'position': int(parts[2]),
                                'timestamp': float(parts[3]),
                                'server_id': int(parts[4]),
                                'database': parts[5],
                                'operation': parts[6],
                                'data': json.loads(parts[7]) if len(parts) > 7 else {}
                            }
                            
                            if self.apply_entry(entry):
                                print(f"[REPLICATION] Applied entry {entry['position']}: {entry['operation']}")
                            else:
                                print(f"[REPLICATION] Failed to apply entry {entry['position']}")
                    
                    elif line.startswith("REPL HEARTBEAT"):
                        # Heartbeat from master - update position
                        parts = line.split()
                        if len(parts) >= 3:
                            pos = int(parts[2])
                            self.save_position(pos)
                    
                    elif line.startswith("ERROR"):
                        print(f"[REPLICATION] Master error: {line}")
                        self.disconnect()
                        break
            
            except socket.timeout:
                # Timeout is OK, just continue
                pass
            except Exception as e:
                print(f"[REPLICATION] Error in replication loop: {e}")
                self.disconnect()
        
        self.disconnect()
        print("[REPLICATION] Client stopped")
    
    def stop(self):
        """Stop the replication client."""
        self.running = False
        self.disconnect()


class ReplicationHandler(threading.Thread):
    """
    Handles replication connections on the master server.
    Streams binlog entries to connected slaves.
    """
    
    def __init__(self, client_socket: socket.socket, address: tuple,
                 db: Database, authenticator):
        super().__init__(daemon=True)
        self.client_socket = client_socket
        self.address = address
        self.db = db
        self.authenticator = authenticator
        self.running = True
        self.authenticated = False
        self.username = None
        self.start_position = 0
    
    def send(self, message: str):
        """Send message to slave."""
        try:
            self.client_socket.sendall((message + '\n').encode())
        except Exception as e:
            print(f"[REPLICATION] Send error to {self.address}: {e}")
            self.running = False
    
    def handle_auth(self, line: str) -> bool:
        """Handle REPL AUTH command."""
        parts = line.split()
        if len(parts) >= 4 and parts[0] == "REPL" and parts[1] == "AUTH":
            username = parts[2]
            password = parts[3]
            
            # Authenticate
            success, token, user_info = self.authenticator.authenticate(username, password)
            if success:
                # Check if user has REPLICATION_SLAVE privilege
                if self.authenticator.is_replication_user(token):
                    self.authenticated = True
                    self.username = username
                    self.send("OK: Authentication successful")
                    return True
            
            self.send("ERROR: Authentication failed or insufficient privileges")
            return False
        
        self.send("ERROR: Expected REPL AUTH")
        return False
    
    def handle_stream_request(self, line: str) -> bool:
        """Handle REPL STREAM FROM command."""
        parts = line.split()
        if len(parts) >= 4 and parts[0] == "REPL" and parts[1] == "STREAM" and parts[2] == "FROM":
            try:
                self.start_position = int(parts[3])
                self.send(f"OK: Starting stream from position {self.start_position}")
                print(f"[REPLICATION] Slave {self.address} ({self.username}) starting from position {self.start_position}")
                return True
            except ValueError:
                self.send("ERROR: Invalid position")
                return False
        
        self.send("ERROR: Expected REPL STREAM FROM")
        return False
    
    def stream_binlog(self):
        """Stream binlog entries to slave."""
        last_sent_position = self.start_position
        
        while self.running and self.authenticated:
            try:
                # Get entries from binlog
                if self.db._binlog:
                    entries = self.db._binlog.get_entries(last_sent_position, limit=100)
                    
                    if entries:
                        for entry in entries:
                            # Format: REPL ENTRY position timestamp server_id db op {data}
                            data_json = json.dumps(entry.get('data', {}))
                            msg = (f"REPL ENTRY {entry['position']} {entry['timestamp']} "
                                   f"{entry['server_id']} {entry['database']} "
                                   f"{entry['operation']} {data_json}")
                            self.send(msg)
                            last_sent_position = entry['position']
                    else:
                        # No new entries, send heartbeat
                        current_pos = self.db._binlog.get_latest_position()
                        if current_pos > last_sent_position:
                            # There might be new entries, try again
                            continue
                        self.send(f"REPL HEARTBEAT {current_pos}")
                
                # Small delay to prevent busy-waiting
                time.sleep(0.1)
                
            except Exception as e:
                print(f"[REPLICATION] Stream error for {self.address}: {e}")
                self.running = False
                break
    
    def run(self):
        """Handle the replication connection."""
        print(f"[REPLICATION] Slave connected from {self.address}")
        
        try:
            # Set timeout for initial handshake
            self.client_socket.settimeout(60)
            
            # Wait for authentication
            data = self.client_socket.recv(4096)
            if not data:
                return
            
            line = data.decode().strip()
            if not self.handle_auth(line):
                return
            
            # Wait for stream request
            data = self.client_socket.recv(4096)
            if not data:
                return
            
            line = data.decode().strip()
            if not self.handle_stream_request(line):
                return
            
            # Start streaming
            self.client_socket.settimeout(None)  # No timeout during streaming
            self.stream_binlog()
            
        except Exception as e:
            print(f"[REPLICATION] Handler error for {self.address}: {e}")
        finally:
            print(f"[REPLICATION] Slave {self.address} disconnected")
            try:
                self.client_socket.close()
            except:
                pass


class ReplicationServer(threading.Thread):
    """
    Server that listens for replication connections on a separate port.
    Runs on master servers.
    """
    
    def __init__(self, host: str, port: int, db: Database, authenticator):
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.db = db
        self.authenticator = authenticator
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self.handlers: List[ReplicationHandler] = []
    
    def run(self):
        """Start listening for replication connections."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.running = True
        
        print(f"[REPLICATION] Server listening on {self.host}:{self.port}")
        
        try:
            while self.running:
                self.server_socket.settimeout(1.0)
                try:
                    client_socket, address = self.server_socket.accept()
                    handler = ReplicationHandler(client_socket, address, self.db, self.authenticator)
                    self.handlers.append(handler)
                    handler.start()
                except socket.timeout:
                    continue
        except Exception as e:
            print(f"[REPLICATION] Server error: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """Stop the replication server."""
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        # Stop all handlers
        for handler in self.handlers:
            handler.running = False
        
        print("[REPLICATION] Server stopped")