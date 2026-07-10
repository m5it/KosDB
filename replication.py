"""
Replication Protocol for LevelDB Socket Server

Implements master-slave and master-master replication over TCP sockets.
Features: automatic reconnection, conflict detection, health monitoring
"""

import socket
import threading
import json
import time
import hashlib
from typing import Optional, Dict, Any, List, Tuple
from database import Database
from collections import deque
import select


class ReplicationError(Exception):
    """Base exception for replication errors."""
    pass


class ConflictResolutionError(ReplicationError):
    """Raised when conflict cannot be resolved."""
    pass


class VectorClock:
    """
    Vector clock for conflict detection in multi-master replication.
    Tracks logical timestamps from each server.
    """
    
    def __init__(self, server_id: int, initial: Optional[Dict[int, int]] = None):
        self.server_id = server_id
        self.clock = initial or {}
        if server_id not in self.clock:
            self.clock[server_id] = 0
    
    def increment(self) -> 'VectorClock':
        """Increment this server's clock."""
        self.clock[self.server_id] = self.clock.get(self.server_id, 0) + 1
        return self
    
    def merge(self, other: 'VectorClock') -> 'VectorClock':
        """Merge another vector clock into this one."""
        for server_id, timestamp in other.clock.items():
            self.clock[server_id] = max(self.clock.get(server_id, 0), timestamp)
        return self
    
    def compare(self, other: 'VectorClock') -> int:
        """
        Compare with another vector clock.
        Returns: -1 (before), 0 (concurrent/conflict), 1 (after)
        """
        if not isinstance(other, VectorClock):
            return 0
        
        dominates = False
        dominated = False
        
        all_servers = set(self.clock.keys()) | set(other.clock.keys())
        
        for server_id in all_servers:
            self_ts = self.clock.get(server_id, 0)
            other_ts = other.clock.get(server_id, 0)
            
            if self_ts > other_ts:
                dominates = True
            elif other_ts > self_ts:
                dominated = True
        
        if dominates and not dominated:
            return 1  # self happened after other
        elif dominated and not dominates:
            return -1  # self happened before other
        else:
            return 0  # concurrent or equal
    
    def to_dict(self) -> Dict[str, int]:
        """Convert to dictionary for serialization."""
        return {str(k): v for k, v in self.clock.items()}
    
    @classmethod
    def from_dict(cls, server_id: int, data: Dict[str, int]) -> 'VectorClock':
        """Create from dictionary."""
        return cls(server_id, {int(k): v for k, v in data.items()})
    
    def __repr__(self):
        return f"VC({self.server_id}: {self.clock})"


class ConflictResolver:
    """
    Resolves conflicts in multi-master replication.
    Strategies: last-write-wins, server-id-priority, timestamp
    """
    
    def __init__(self, server_id: int, strategy: str = 'server_id_priority'):
        self.server_id = server_id
        self.strategy = strategy
        self.conflict_log: deque = deque(maxlen=1000)  # Recent conflicts
    
    def resolve(self, local_entry: Dict, remote_entry: Dict) -> Dict:
        """
        Resolve conflict between two entries.
        Returns the winning entry.
        """
        local_vc = VectorClock.from_dict(self.server_id, local_entry.get('vector_clock', {}))
        remote_vc = VectorClock.from_dict(self.server_id, remote_entry.get('vector_clock', {}))
        
        comparison = local_vc.compare(remote_vc)
        
        if comparison == 1:
            # Local is newer
            return local_entry
        elif comparison == -1:
            # Remote is newer
            return remote_entry
        
        # Concurrent/conflict - apply strategy
        winner = self._apply_strategy(local_entry, remote_entry)
        
        # Log conflict
        self.conflict_log.append({
            'timestamp': time.time(),
            'local_entry': local_entry,
            'remote_entry': remote_entry,
            'winner': 'local' if winner is local_entry else 'remote',
            'strategy': self.strategy
        })
        
        return winner
    
    def _apply_strategy(self, local_entry: Dict, remote_entry: Dict) -> Dict:
        """Apply conflict resolution strategy."""
        if self.strategy == 'last_write_wins':
            # Use higher timestamp
            local_ts = local_entry.get('timestamp', 0)
            remote_ts = remote_entry.get('timestamp', 0)
            return local_entry if local_ts >= remote_ts else remote_entry
        
        elif self.strategy == 'server_id_priority':
            # Lower server ID wins (deterministic)
            local_sid = local_entry.get('server_id', float('inf'))
            remote_sid = remote_entry.get('server_id', float('inf'))
            return local_entry if local_sid < remote_sid else remote_entry
        
        elif self.strategy == 'hash':
            # Deterministic hash comparison
            local_hash = hashlib.sha256(str(local_entry).encode()).hexdigest()
            remote_hash = hashlib.sha256(str(remote_entry).encode()).hexdigest()
            return local_entry if local_hash < remote_hash else remote_entry
        
        # Default: keep local
        return local_entry


class ReplicationMetrics:
    """Track replication performance metrics."""
    
    def __init__(self):
        self.entries_applied = 0
        self.entries_failed = 0
        self.conflicts_resolved = 0
        self.reconnects = 0
        self.last_entry_time = 0
        self.lag_ms = 0
        self.errors: deque = deque(maxlen=100)
        self._lock = threading.Lock()
    
    def record_apply(self, success: bool, lag_ms: float = 0):
        """Record an apply attempt."""
        with self._lock:
            if success:
                self.entries_applied += 1
                self.last_entry_time = time.time()
                self.lag_ms = lag_ms
            else:
                self.entries_failed += 1
    
    def record_conflict(self):
        """Record a resolved conflict."""
        with self._lock:
            self.conflicts_resolved += 1
    
    def record_reconnect(self):
        """Record a reconnection."""
        with self._lock:
            self.reconnects += 1
    
    def record_error(self, error: str):
        """Record an error."""
        with self._lock:
            self.errors.append({
                'time': time.time(),
                'error': error
            })
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current statistics."""
        with self._lock:
            return {
                'entries_applied': self.entries_applied,
                'entries_failed': self.entries_failed,
                'conflicts_resolved': self.conflicts_resolved,
                'reconnects': self.reconnects,
                'last_entry_time': self.last_entry_time,
                'lag_ms': self.lag_ms,
                'recent_errors': list(self.errors)[-5:]
            }


class ReplicationClient(threading.Thread):
    """
    Replication client that runs on slave servers.
    Connects to master and streams binlog entries.
    Features: automatic reconnection, health monitoring, conflict resolution
    """
    
    def __init__(self, master_host: str, master_port: int, 
                 username: str, password: str,
                 db: Database, server_id: int,
                 conflict_strategy: str = 'server_id_priority'):
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
        self.reconnect_delay = 5
        self.max_reconnect_delay = 300  # 5 minutes max
        
        self.conflict_resolver = ConflictResolver(server_id, conflict_strategy)
        self.metrics = ReplicationMetrics()
        self._pending_entries: deque = deque(maxlen=10000)
        self._apply_lock = threading.Lock()
    
    def load_position(self) -> int:
        """Load last applied position from disk."""
        try:
            if self.db._system_db:
                pos_data = self.db._system_db.get(b"_replication:last_position")
                if pos_data:
                    return int(pos_data.decode())
        except Exception as e:
            print(f"[REPLICATION] Error loading position: {e}")
            self.metrics.record_error(f"Load position: {e}")
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
            self.metrics.record_error(f"Save position: {e}")
    
    def connect(self) -> bool:
        """Connect to master server with retry logic."""
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
                self.metrics.record_error(f"Auth failed: {response}")
                return False
            
            # Request binlog stream from last position
            self.last_position = self.load_position()
            stream_msg = f"REPL STREAM FROM {self.last_position}\n"
            self.socket.sendall(stream_msg.encode())
            
            response = self.socket.recv(4096).decode().strip()
            if not response.startswith("OK"):
                print(f"[REPLICATION] Stream request failed: {response}")
                self.metrics.record_error(f"Stream request failed: {response}")
                return False
            
            self.connected = True
            self.reconnect_delay = 5  # Reset backoff
            self.metrics.record_reconnect()
            print(f"[REPLICATION] Connected to master at {self.master_host}:{self.master_port}")
            print(f"[REPLICATION] Starting from position {self.last_position}")
            return True
            
        except socket.timeout:
            print(f"[REPLICATION] Connection timeout")
            self.metrics.record_error("Connection timeout")
            return False
        except Exception as e:
            print(f"[REPLICATION] Connection failed: {e}")
            self.metrics.record_error(f"Connection failed: {e}")
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
    
    def check_conflict(self, entry: Dict) -> Optional[Dict]:
        """
        Check if entry conflicts with local data.
        Returns conflicting local entry or None.
        """
        # For UPDATE/DELETE operations, check if row was modified
        op = entry.get('operation')
        if op not in ('UPDATE', 'DELETE'):
            return None
        
        table = entry.get('table')
        data = entry.get('data', {})
        where = data.get('where', {})
        
        if not table or not where:
            return None
        
        # Check if we have a newer version of this row
        try:
            # Get current row data
            current = self.db.select(table, ['*'], where, raw=True)
            if current and len(current) > 0:
                # Check vector clocks
                local_vc = VectorClock.from_dict(self.server_id, current[0].get('_vc', {}))
                entry_vc = VectorClock.from_dict(self.server_id, entry.get('vector_clock', {}))
                
                if local_vc.compare(entry_vc) > 0:
                    # Local is newer - conflict!
                    return {'row': current[0], 'vector_clock': local_vc.to_dict()}
        except Exception:
            pass
        
        return None
    
    def apply_entry(self, entry: Dict) -> bool:
        """
        Apply a binlog entry to local database.
        Skip entries from our own server_id (loop prevention).
        Handle conflicts in multi-master setup.
        """
        # Skip our own entries (for master-master)
        if entry.get('server_id') == self.server_id:
            return True
        
        start_time = time.time()
        
        try:
            op = entry['operation']
            db_name = entry['database']
            table = entry.get('table')
            data = entry.get('data', {})
            
            # Check for conflicts
            conflict = self.check_conflict(entry)
            if conflict:
                resolved = self.conflict_resolver.resolve(conflict, entry)
                if resolved is conflict:
                    # Local wins, skip this entry
                    self.metrics.record_conflict()
                    print(f"[REPLICATION] Conflict detected - local wins for {table}")
                    self.save_position(entry['position'])
                    return True
            
            # Ensure we're using the correct database
            if db_name and self.db.current_db != db_name:
                self.db.use_database(db_name)
            
            # Apply based on operation type
            with self._apply_lock:
                if op == 'INSERT':
                    if table and 'row' in data:
                        row = data['row']
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
            
            # Calculate lag
            entry_time = entry.get('timestamp', 0)
            lag_ms = (time.time() - entry_time) * 1000 if entry_time > 0 else 0
            
            # Save position after successful apply
            self.save_position(entry['position'])
            self.metrics.record_apply(True, lag_ms)
            return True
            
        except Exception as e:
            print(f"[REPLICATION] Error applying entry {entry.get('position')}: {e}")
            self.metrics.record_error(f"Apply entry {entry.get('position')}: {e}")
            self.metrics.record_apply(False)
            return False
    
    def run(self):
        """Main replication loop with health monitoring."""
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
                # Use select for non-blocking read with timeout
                ready, _, _ = select.select([self.socket], [], [], 1.0)
                
                if ready:
                    data = self.socket.recv(8192)
                    if not data:
                        print("[REPLICATION] Connection closed by master")
                        self.disconnect()
                        continue
                    
                    # Parse entries
                    lines = data.decode().strip().split('\n')
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        
                        self._process_line(line)
                
                # Send periodic heartbeat
                if time.time() % 10 < 1:
                    self._send_heartbeat()
                    
            except select.error as e:
                print(f"[REPLICATION] Select error: {e}")
                self.disconnect()
            except Exception as e:
                print(f"[REPLICATION] Error in replication loop: {e}")
                self.metrics.record_error(f"Replication loop: {e}")
                self.disconnect()
        
        self.disconnect()
        print("[REPLICATION] Client stopped")
    
    def _process_line(self, line: str):
        """Process a single replication line."""
        if line.startswith("REPL ENTRY"):
            entry = self._parse_entry(line)
            if entry:
                if self.apply_entry(entry):
                    print(f"[REPLICATION] Applied entry {entry['position']}: {entry['operation']}")
                else:
                    print(f"[REPLICATION] Failed to apply entry {entry['position']}")
        
        elif line.startswith("REPL HEARTBEAT"):
            parts = line.split()
            if len(parts) >= 3:
                try:
                    pos = int(parts[2])
                    self.save_position(pos)
                except ValueError:
                    pass
        
        elif line.startswith("ERROR"):
            print(f"[REPLICATION] Master error: {line}")
            self.metrics.record_error(f"Master: {line}")
            self.disconnect()
    
    def _parse_entry(self, line: str) -> Optional[Dict]:
        """Parse REPL ENTRY line."""
        parts = line.split(' ', 7)
        if len(parts) >= 7:
            return {
                'position': int(parts[2]),
                'timestamp': float(parts[3]),
                'server_id': int(parts[4]),
                'database': parts[5],
                'operation': parts[6],
                'data': json.loads(parts[7]) if len(parts) > 7 else {},
                'table': parts[6] if len(parts) > 6 else None
            }
        return None
    
    def _send_heartbeat(self):
        """Send heartbeat to master."""
        try:
            if self.connected and self.socket:
                self.socket.sendall(f"REPL HEARTBEAT {self.last_position}\n".encode())
        except:
            pass
    
    def get_status(self) -> Dict[str, Any]:
        """Get current replication status."""
        return {
            'connected': self.connected,
            'master_host': self.master_host,
            'master_port': self.master_port,
            'last_position': self.last_position,
            'reconnect_delay': self.reconnect_delay,
            'metrics': self.metrics.get_stats()
        }
    
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
        self.last_activity = time.time()
        self._send_lock = threading.Lock()
    
    def send(self, message: str):
        """Send message to slave."""
        with self._send_lock:
            try:
                self.client_socket.sendall((message + '\n').encode())
                self.last_activity = time.time()
            except Exception as e:
                print(f"[REPLICATION] Send error to {self.address}: {e}")
                self.running = False
    
    def handle_auth(self, line: str) -> bool:
        """Handle REPL AUTH command."""
        parts = line.split()
        if len(parts) >= 4 and parts[0] == "REPL" and parts[1] == "AUTH":
            username = parts[2]
            password = parts[3]
            
            success, token, user_info = self.authenticator.authenticate(username, password)
            if success:
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
        """Stream binlog entries to slave with flow control."""
        last_sent_position = self.start_position
        batch_size = 100
        
        while self.running and self.authenticated:
            try:
                if self.db._binlog:
                    entries = self.db._binlog.get_entries(last_sent_position, limit=batch_size)
                    
                    if entries:
                        for entry in entries:
                            data_json = json.dumps(entry.get('data', {}))
                            msg = (f"REPL ENTRY {entry['position']} {entry['timestamp']} "
                                   f"{entry['server_id']} {entry['database']} "
                                   f"{entry['operation']} {data_json}")
                            self.send(msg)
                            last_sent_position = entry['position']
                        
                        # Small delay to prevent overwhelming slave
                        time.sleep(0.01)
                    else:
                        # No new entries, send heartbeat
                        current_pos = self.db._binlog.get_latest_position()
                        if current_pos > last_sent_position:
                            continue
                        self.send(f"REPL HEARTBEAT {current_pos}")
                        time.sleep(1)
                else:
                    time.sleep(1)
                
                # Check for client heartbeat
                ready, _, _ = select.select([self.client_socket], [], [], 0.1)
                if ready:
                    data = self.client_socket.recv(1024)
                    if data:
                        line = data.decode().strip()
                        if line.startswith("REPL HEARTBEAT"):
                            self.last_activity = time.time()
                
                # Timeout check
                if time.time() - self.last_activity > 60:
                    print(f"[REPLICATION] Timeout for {self.address}")
                    self.running = False
                    break
                    
            except Exception as e:
                print(f"[REPLICATION] Stream error for {self.address}: {e}")
                self.running = False
                break
    
    def run(self):
        """Handle the replication connection."""
        print(f"[REPLICATION] Slave connected from {self.address}")
        
        try:
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
            self.client_socket.settimeout(None)
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
    Server that listens for replication connections.
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
        self._handlers_lock = threading.Lock()
    
    def run(self):
        """Start listening for replication connections."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(10)
        self.running = True
        
        print(f"[REPLICATION] Server listening on {self.host}:{self.port}")
        
        try:
            while self.running:
                self.server_socket.settimeout(1.0)
                try:
                    client_socket, address = self.server_socket.accept()
                    handler = ReplicationHandler(client_socket, address, self.db, self.authenticator)
                    with self._handlers_lock:
                        self.handlers.append(handler)
                    handler.start()
                except socket.timeout:
                    # Clean up dead handlers
                    with self._handlers_lock:
                        self.handlers = [h for h in self.handlers if h.is_alive()]
                    continue
        except Exception as e:
            print(f"[REPLICATION] Server error: {e}")
        finally:
            self.stop()
    
    def get_slave_count(self) -> int:
        """Get number of connected slaves."""
        with self._handlers_lock:
            return len([h for h in self.handlers if h.is_alive() and h.authenticated])
    
    def stop(self):
        """Stop the replication server."""
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        with self._handlers_lock:
            for handler in self.handlers:
                handler.running = False
        
        print("[REPLICATION] Server stopped")


class MultiMasterManager:
    """
    Manages multi-master replication topology.
    Handles conflict detection and resolution.
    """
    
    def __init__(self, server_id: int, peers: List[Tuple[str, int, str, str]],
                 db: Database, strategy: str = 'server_id_priority'):
        self.server_id = server_id
        self.peers = peers
        self.db = db
        self.strategy = strategy
        self.clients: List[ReplicationClient] = []
        self.conflict_resolver = ConflictResolver(server_id, strategy)
    
    def start(self):
        """Start replication to all peers."""
        for host, port, username, password in self.peers:
            client = ReplicationClient(
                host, port, username, password,
                self.db, self.server_id, self.strategy
            )
            client.start()
            self.clients.append(client)
            print(f"[MULTI-MASTER] Started replication to {host}:{port}")
    
    def stop(self):
        """Stop all replication clients."""
        for client in self.clients:
            client.stop()
        self.clients.clear()
    
    def get_status(self) -> List[Dict]:
        """Get status of all peer connections."""
        return [client.get_status() for client in self.clients]
