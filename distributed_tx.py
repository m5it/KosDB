"""
Distributed Transaction Coordinator for Multi-Node Consistency

Implements Two-Phase Commit (2PC) protocol for distributed transactions.
"""

import socket
import threading
import json
import time
import uuid
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum, auto
from collections import defaultdict
import select


class TransactionState(Enum):
    """States in the 2PC protocol."""
    INIT = "init"
    PREPARING = "preparing"
    PREPARED = "prepared"
    COMMITTING = "committing"
    COMMITTED = "committed"
    ABORTING = "aborting"
    ABORTED = "aborted"
    FAILED = "failed"


class ParticipantState(Enum):
    """Participant states in 2PC."""
    WAITING = "waiting"
    PREPARED = "prepared"
    COMMITTED = "committed"
    ABORTED = "aborted"
    FAILED = "failed"


class DistributedTransaction:
    """Represents a distributed transaction."""
    
    def __init__(self, tx_id: str, coordinator: str, participants: List[str]):
        self.tx_id = tx_id
        self.coordinator = coordinator
        self.participants = participants
        self.state = TransactionState.INIT
        self.participant_states: Dict[str, ParticipantState] = {
            p: ParticipantState.WAITING for p in participants
        }
        self.operations: List[Dict] = []
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.result: Optional[str] = None
        self._lock = threading.Lock()
    
    def update_state(self, new_state: TransactionState):
        """Update transaction state."""
        with self._lock:
            self.state = new_state
            if new_state in (TransactionState.COMMITTED, TransactionState.ABORTED, 
                           TransactionState.FAILED):
                self.end_time = time.time()
    
    def update_participant(self, participant: str, state: ParticipantState):
        """Update participant state."""
        with self._lock:
            self.participant_states[participant] = state
    
    def all_prepared(self) -> bool:
        """Check if all participants are prepared."""
        with self._lock:
            return all(s == ParticipantState.PREPARED 
                      for s in self.participant_states.values())
    
    def any_aborted(self) -> bool:
        """Check if any participant aborted."""
        with self._lock:
            return any(s == ParticipantState.ABORTED 
                      for s in self.participant_states.values())
    
    def any_failed(self) -> bool:
        """Check if any participant failed."""
        with self._lock:
            return any(s == ParticipantState.FAILED 
                      for s in self.participant_states.values())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        with self._lock:
            return {
                'tx_id': self.tx_id,
                'coordinator': self.coordinator,
                'state': self.state.value,
                'participants': self.participants,
                'participant_states': {k: v.value for k, v in self.participant_states.items()},
                'operations': self.operations,
                'start_time': self.start_time,
                'end_time': self.end_time,
                'duration': (self.end_time or time.time()) - self.start_time
            }


class ParticipantConnection:
    """Connection to a remote participant node."""
    
    def __init__(self, node_id: str, host: str, port: int):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self._lock = threading.Lock()
    
    def connect(self) -> bool:
        """Connect to participant."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)
            self.socket.connect((self.host, self.port))
            self.connected = True
            return True
        except Exception as e:
            print(f"[DIST-TX] Failed to connect to {self.node_id}: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from participant."""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        self.socket = None
        self.connected = False
    
    def send(self, message: Dict) -> bool:
        """Send message to participant."""
        with self._lock:
            if not self.connected and not self.connect():
                return False
            
            try:
                data = json.dumps(message).encode()
                self.socket.sendall(len(data).to_bytes(4, 'big') + data)
                return True
            except Exception as e:
                print(f"[DIST-TX] Send failed to {self.node_id}: {e}")
                self.disconnect()
                return False
    
    def receive(self, timeout: float = 30.0) -> Optional[Dict]:
        """Receive response from participant."""
        with self._lock:
            if not self.connected:
                return None
            
            try:
                self.socket.settimeout(timeout)
                
                # Read length prefix
                len_bytes = self.socket.recv(4)
                if len(len_bytes) != 4:
                    return None
                
                msg_len = int.from_bytes(len_bytes, 'big')
                
                # Read message
                data = b''
                while len(data) < msg_len:
                    chunk = self.socket.recv(min(4096, msg_len - len(data)))
                    if not chunk:
                        return None
                    data += chunk
                
                return json.loads(data.decode())
            except Exception as e:
                print(f"[DIST-TX] Receive failed from {self.node_id}: {e}")
                self.disconnect()
                return None
    
    def send_receive(self, message: Dict, timeout: float = 30.0) -> Optional[Dict]:
        """Send message and receive response."""
        if self.send(message):
            return self.receive(timeout)
        return None


class DistributedTransactionCoordinator:
    """
    Coordinator for distributed transactions using 2PC.
    Runs on a dedicated node or as part of the database server.
    """
    
    def __init__(self, node_id: str, host: str = "0.0.0.0", port: int = 9000):
        self.node_id = node_id
        self.host = host
        self.port = port
        
        self.participants: Dict[str, ParticipantConnection] = {}
        self.transactions: Dict[str, DistributedTransaction] = {}
        self.tx_log: List[Dict] = []  # Write-ahead log
        
        self.running = False
        self.server_socket: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._recovery_thread: Optional[threading.Thread] = None
    
    def add_participant(self, node_id: str, host: str, port: int):
        """Add a participant node."""
        self.participants[node_id] = ParticipantConnection(node_id, host, port)
        print(f"[DIST-TX] Added participant {node_id} at {host}:{port}")
    
    def start(self):
        """Start the coordinator."""
        self.running = True
        
        # Start recovery thread
        self._recovery_thread = threading.Thread(target=self._recovery_worker, daemon=True)
        self._recovery_thread.start()
        
        # Start server
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(10)
        
        print(f"[DIST-TX] Coordinator listening on {self.host}:{self.port}")
        
        # Accept connections in main thread
        while self.running:
            try:
                self.server_socket.settimeout(1.0)
                client_socket, address = self.server_socket.accept()
                handler = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, address),
                    daemon=True
                )
                handler.start()
            except socket.timeout:
                continue
            except Exception as e:
                print(f"[DIST-TX] Server error: {e}")
                break
        
        self.stop()
    
    def stop(self):
        """Stop the coordinator."""
        self.running = False
        
        # Disconnect all participants
        for conn in self.participants.values():
            conn.disconnect()
        
        # Close server socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        print("[DIST-TX] Coordinator stopped")
    
    def _handle_client(self, client_socket: socket.socket, address: Tuple[str, int]):
        """Handle incoming client connection."""
        try:
            while self.running:
                # Read message length
                client_socket.settimeout(1.0)
                try:
                    len_bytes = client_socket.recv(4)
                    if not len_bytes or len(len_bytes) != 4:
                        break
                except socket.timeout:
                    continue
                
                msg_len = int.from_bytes(len_bytes, 'big')
                
                # Read message
                data = b''
                while len(data) < msg_len:
                    chunk = client_socket.recv(min(4096, msg_len - len(data)))
                    if not chunk:
                        break
                    data += chunk
                
                if len(data) != msg_len:
                    break
                
                message = json.loads(data.decode())
                response = self._process_message(message)
                
                # Send response
                resp_data = json.dumps(response).encode()
                client_socket.sendall(len(resp_data).to_bytes(4, 'big') + resp_data)
                
        except Exception as e:
            print(f"[DIST-TX] Client handler error: {e}")
        finally:
            try:
                client_socket.close()
            except:
                pass
    
    def _process_message(self, message: Dict) -> Dict:
        """Process incoming message."""
        msg_type = message.get('type')
        tx_id = message.get('tx_id')
        
        if msg_type == 'PREPARE_ACK':
            return self._handle_prepare_ack(tx_id, message.get('node_id'), 
                                           message.get('success'))
        
        elif msg_type == 'COMMIT_ACK':
            return self._handle_commit_ack(tx_id, message.get('node_id'))
        
        elif msg_type == 'ABORT_ACK':
            return self._handle_abort_ack(tx_id, message.get('node_id'))
        
        elif msg_type == 'GET_STATUS':
            return self._get_status(tx_id)
        
        return {'status': 'ERROR', 'message': 'Unknown message type'}
    
    def _handle_prepare_ack(self, tx_id: str, node_id: str, success: bool) -> Dict:
        """Handle prepare acknowledgement from participant."""
        tx = self.transactions.get(tx_id)
        if not tx:
            return {'status': 'ERROR', 'message': 'Transaction not found'}
        
        if success:
            tx.update_participant(node_id, ParticipantState.PREPARED)
        else:
            tx.update_participant(node_id, ParticipantState.ABORTED)
        
        return {'status': 'OK'}
    
    def _handle_commit_ack(self, tx_id: str, node_id: str) -> Dict:
        """Handle commit acknowledgement from participant."""
        tx = self.transactions.get(tx_id)
        if not tx:
            return {'status': 'ERROR', 'message': 'Transaction not found'}
        
        tx.update_participant(node_id, ParticipantState.COMMITTED)
        return {'status': 'OK'}
    
    def _handle_abort_ack(self, tx_id: str, node_id: str) -> Dict:
        """Handle abort acknowledgement from participant."""
        tx = self.transactions.get(tx_id)
        if not tx:
            return {'status': 'ERROR', 'message': 'Transaction not found'}
        
        tx.update_participant(node_id, ParticipantState.ABORTED)
        return {'status': 'OK'}
    
    def _get_status(self, tx_id: str) -> Dict:
        """Get transaction status."""
        tx = self.transactions.get(tx_id)
        if not tx:
            return {'status': 'ERROR', 'message': 'Transaction not found'}
        
        return {
            'status': 'OK',
            'transaction': tx.to_dict()
        }
    
    def begin_transaction(self, operations: List[Dict]) -> str:
        """
        Begin a new distributed transaction.
        Returns transaction ID.
        """
        tx_id = str(uuid.uuid4())
        participants = list(self.participants.keys())
        
        tx = DistributedTransaction(tx_id, self.node_id, participants)
        tx.operations = operations
        
        with self._lock:
            self.transactions[tx_id] = tx
        
        # Log transaction start
        self._log_transaction(tx, 'BEGIN')
        
        print(f"[DIST-TX] Started transaction {tx_id} with {len(participants)} participants")
        return tx_id
    
    def prepare_phase(self, tx_id: str) -> bool:
        """
        Phase 1: Prepare all participants.
        Returns True if all participants are prepared.
        """
        tx = self.transactions.get(tx_id)
        if not tx:
            return False
        
        tx.update_state(TransactionState.PREPARING)
        self._log_transaction(tx, 'PREPARING')
        
        # Send PREPARE to all participants
        prepare_msg = {
            'type': 'PREPARE',
            'tx_id': tx_id,
            'coordinator': self.node_id,
            'operations': tx.operations
        }
        
        threads = []
        for node_id, conn in self.participants.items():
            t = threading.Thread(
                target=self._send_prepare,
                args=(tx, node_id, conn, prepare_msg),
                daemon=True
            )
            threads.append(t)
            t.start()
        
        # Wait for all responses with timeout
        for t in threads:
            t.join(timeout=30)
        
        # Check results
        if tx.any_aborted() or tx.any_failed():
            tx.update_state(TransactionState.ABORTING)
            self._log_transaction(tx, 'ABORTING')
            return False
        
        if tx.all_prepared():
            tx.update_state(TransactionState.PREPARED)
            self._log_transaction(tx, 'PREPARED')
            return True
        
        # Timeout or incomplete
        tx.update_state(TransactionState.ABORTING)
        self._log_transaction(tx, 'ABORTING_TIMEOUT')
        return False
    
    def _send_prepare(self, tx: DistributedTransaction, node_id: str, 
                     conn: ParticipantConnection, message: Dict):
        """Send prepare message to a participant."""
        response = conn.send_receive(message, timeout=30)
        
        if response and response.get('status') == 'PREPARED':
            tx.update_participant(node_id, ParticipantState.PREPARED)
        elif response and response.get('status') == 'NO':
            tx.update_participant(node_id, ParticipantState.ABORTED)
        else:
            tx.update_participant(node_id, ParticipantState.FAILED)
    
    def commit_phase(self, tx_id: str) -> bool:
        """
        Phase 2: Commit the transaction.
        Returns True if commit successful.
        """
        tx = self.transactions.get(tx_id)
        if not tx:
            return False
        
        tx.update_state(TransactionState.COMMITTING)
        self._log_transaction(tx, 'COMMITTING')
        
        # Send COMMIT to all participants
        commit_msg = {
            'type': 'COMMIT',
            'tx_id': tx_id,
            'coordinator': self.node_id
        }
        
        threads = []
        for node_id, conn in self.participants.items():
            t = threading.Thread(
                target=self._send_commit,
                args=(tx, node_id, conn, commit_msg),
                daemon=True
            )
            threads.append(t)
            t.start()
        
        # Wait for acknowledgements
        for t in threads:
            t.join(timeout=30)
        
        tx.update_state(TransactionState.COMMITTED)
        self._log_transaction(tx, 'COMMITTED')
        
        print(f"[DIST-TX] Transaction {tx_id} committed")
        return True
    
    def _send_commit(self, tx: DistributedTransaction, node_id: str,
                    conn: ParticipantConnection, message: Dict):
        """Send commit message to a participant."""
        # Retry up to 3 times
        for attempt in range(3):
            response = conn.send_receive(message, timeout=30)
            if response and response.get('status') == 'ACK':
                tx.update_participant(node_id, ParticipantState.COMMITTED)
                return
            time.sleep(0.5 * (2 ** attempt))  # Exponential backoff
        
        # Mark as failed but don't stop - participant will check status
        tx.update_participant(node_id, ParticipantState.FAILED)
    
    def abort_transaction(self, tx_id: str):
        """Abort a transaction."""
        tx = self.transactions.get(tx_id)
        if not tx:
            return
        
        tx.update_state(TransactionState.ABORTING)
        self._log_transaction(tx, 'ABORTING')
        
        # Send ABORT to all participants
        abort_msg = {
            'type': 'ABORT',
            'tx_id': tx_id,
            'coordinator': self.node_id
        }
        
        threads = []
        for node_id, conn in self.participants.items():
            t = threading.Thread(
                target=self._send_abort,
                args=(tx, node_id, conn, abort_msg),
                daemon=True
            )
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join(timeout=10)
        
        tx.update_state(TransactionState.ABORTED)
        self._log_transaction(tx, 'ABORTED')
        
        print(f"[DIST-TX] Transaction {tx_id} aborted")
    
    def _send_abort(self, tx: DistributedTransaction, node_id: str,
                   conn: ParticipantConnection, message: Dict):
        """Send abort message to a participant."""
        conn.send_receive(message, timeout=10)
        tx.update_participant(node_id, ParticipantState.ABORTED)
    
    def execute_transaction(self, operations: List[Dict]) -> Tuple[bool, str]:
        """
        Execute a complete distributed transaction.
        Returns (success, tx_id or error message).
        """
        tx_id = self.begin_transaction(operations)
        
        try:
            # Phase 1: Prepare
            if not self.prepare_phase(tx_id):
                self.abort_transaction(tx_id)
                return False, f"Transaction {tx_id} aborted during prepare"
            
            # Phase 2: Commit
            if not self.commit_phase(tx_id):
                return False, f"Transaction {tx_id} failed during commit"
            
            return True, tx_id
            
        except Exception as e:
            self.abort_transaction(tx_id)
            return False, f"Transaction {tx_id} failed: {e}"
    
    def _log_transaction(self, tx: DistributedTransaction, event: str):
        """Write transaction event to log."""
        log_entry = {
            'timestamp': time.time(),
            'tx_id': tx.tx_id,
            'event': event,
            'state': tx.state.value,
            'participants': tx.participant_states
        }
        self.tx_log.append(log_entry)
    
    def _recovery_worker(self):
        """Background thread for transaction recovery."""
        while self.running:
            time.sleep(10)
            
            # Check for incomplete transactions
            with self._lock:
                for tx_id, tx in self.transactions.items():
                    if tx.state in (TransactionState.PREPARING, TransactionState.PREPARED,
                                  TransactionState.COMMITTING):
                        # Transaction may be incomplete - check participant status
                        self._recover_transaction(tx_id)
    
    def _recover_transaction(self, tx_id: str):
        """Recover a potentially incomplete transaction."""
        tx = self.transactions.get(tx_id)
        if not tx:
            return
        
        print(f"[DIST-TX] Recovering transaction {tx_id} in state {tx.state.value}")
        
        # Query participants for their state
        for node_id, conn in self.participants.items():
            status_msg = {'type': 'GET_TX_STATUS', 'tx_id': tx_id}
            response = conn.send_receive(status_msg, timeout=10)
            
            if response:
                participant_state = response.get('state')
                
                # If any participant committed, we must commit
                if participant_state == 'COMMITTED':
                    self.commit_phase(tx_id)
                    return
                
                # If any participant doesn't know about transaction and we're past PREPARING,
                # we should abort
                if participant_state == 'UNKNOWN' and tx.state == TransactionState.PREPARING:
                    self.abort_transaction(tx_id)
                    return
        
        # Default: try to complete based on coordinator state
        if tx.state == TransactionState.PREPARED:
            self.commit_phase(tx_id)
        elif tx.state == TransactionState.PREPARING:
            self.abort_transaction(tx_id)
    
    def get_transaction_status(self, tx_id: str) -> Optional[Dict]:
        """Get status of a transaction."""
        tx = self.transactions.get(tx_id)
        if tx:
            return tx.to_dict()
        return None
    
    def get_all_transactions(self) -> List[Dict]:
        """Get all transactions."""
        return [tx.to_dict() for tx in self.transactions.values()]


class DistributedTransactionParticipant:
    """
    Participant in distributed transactions.
    Runs on each database node.
    """
    
    def __init__(self, node_id: str, db, host: str = "0.0.0.0", port: int = 9001):
        self.node_id = node_id
        self.db = db
        self.host = host
        self.port = port
        
        self.prepared_transactions: Dict[str, Dict] = {}
        self.committed_transactions: set = set()
        self.aborted_transactions: set = set()
        
        self.running = False
        self.server_socket: Optional[socket.socket] = None
        self._lock = threading.Lock()
    
    def start(self):
        """Start the participant server."""
        self.running = True
        
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(10)
        
        print(f"[DIST-TX] Participant {self.node_id} listening on {self.host}:{self.port}")
        
        while self.running:
            try:
                self.server_socket.settimeout(1.0)
                client_socket, address = self.server_socket.accept()
                handler = threading.Thread(
                    target=self._handle_coordinator,
                    args=(client_socket, address),
                    daemon=True
                )
                handler.start()
            except socket.timeout:
                continue
            except Exception as e:
                print(f"[DIST-TX] Participant error: {e}")
                break
        
        self.stop()
    
    def stop(self):
        """Stop the participant."""
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        print(f"[DIST-TX] Participant {self.node_id} stopped")
    
    def _handle_coordinator(self, client_socket: socket.socket, address: Tuple[str, int]):
        """Handle connection from coordinator."""
        try:
            while self.running:
                # Read message length
                client_socket.settimeout(30.0)
                len_bytes = client_socket.recv(4)
                if not len_bytes or len(len_bytes) != 4:
                    break
                
                msg_len = int.from_bytes(len_bytes, 'big')
                
                # Read message
                data = b''
                while len(data) < msg_len:
                    chunk = client_socket.recv(min(4096, msg_len - len(data)))
                    if not chunk:
                        break
                    data += chunk
                
                if len(data) != msg_len:
                    break
                
                message = json.loads(data.decode())
                response = self._process_coordinator_message(message)
                
                # Send response
                resp_data = json.dumps(response).encode()
                client_socket.sendall(len(resp_data).to_bytes(4, 'big') + resp_data)
                
        except Exception as e:
            print(f"[DIST-TX] Coordinator handler error: {e}")
        finally:
            try:
                client_socket.close()
            except:
                pass
    
    def _process_coordinator_message(self, message: Dict) -> Dict:
        """Process message from coordinator."""
        msg_type = message.get('type')
        tx_id = message.get('tx_id')
        
        if msg_type == 'PREPARE':
            return self._handle_prepare(tx_id, message.get('operations', []))
        
        elif msg_type == 'COMMIT':
            return self._handle_commit(tx_id)
        
        elif msg_type == 'ABORT':
            return self._handle_abort(tx_id)
        
        elif msg_type == 'GET_TX_STATUS':
            return self._get_tx_status(tx_id)
        
        return {'status': 'ERROR', 'message': 'Unknown message type'}
    
    def _handle_prepare(self, tx_id: str, operations: List[Dict]) -> Dict:
        """Handle PREPARE request from coordinator."""
        try:
            # Validate operations can be executed
            for op in operations:
                op_type = op.get('type')
                table = op.get('table')
                
                if op_type == 'INSERT':
                    # Check if table exists
                    schema_key = f"_schema:{table}".encode()
                    if not self.db._db.get(schema_key):
                        return {'status': 'NO', 'reason': f'Table {table} does not exist'}
            
            # Prepare transaction (write to WAL)
            with self._lock:
                self.prepared_transactions[tx_id] = {
                    'operations': operations,
                    'prepared_at': time.time()
                }
            
            print(f"[DIST-TX] Prepared transaction {tx_id}")
            return {'status': 'PREPARED'}
            
        except Exception as e:
            print(f"[DIST-TX] Prepare failed: {e}")
            return {'status': 'NO', 'reason': str(e)}
    
    def _handle_commit(self, tx_id: str) -> Dict:
        """Handle COMMIT request from coordinator."""
        try:
            with self._lock:
                if tx_id not in self.prepared_transactions:
                    if tx_id in self.committed_transactions:
                        return {'status': 'ACK'}  # Already committed
                    return {'status': 'ERROR', 'message': 'Transaction not prepared'}
                
                tx_data = self.prepared_transactions.pop(tx_id)
            
            # Execute operations
            for op in tx_data['operations']:
                self._execute_operation(op)
            
            with self._lock:
                self.committed_transactions.add(tx_id)
            
            print(f"[DIST-TX] Committed transaction {tx_id}")
            return {'status': 'ACK'}
            
        except Exception as e:
            print(f"[DIST-TX] Commit failed: {e}")
            return {'status': 'ERROR', 'message': str(e)}
    
    def _handle_abort(self, tx_id: str) -> Dict:
        """Handle ABORT request from coordinator."""
        with self._lock:
            if tx_id in self.prepared_transactions:
                del self.prepared_transactions[tx_id]
            self.aborted_transactions.add(tx_id)
        
        print(f"[DIST-TX] Aborted transaction {tx_id}")
        return {'status': 'ACK'}
    
    def _get_tx_status(self, tx_id: str) -> Dict:
        """Get transaction status."""
        with self._lock:
            if tx_id in self.committed_transactions:
                return {'status': 'OK', 'state': 'COMMITTED'}
            if tx_id in self.aborted_transactions:
                return {'status': 'OK', 'state': 'ABORTED'}
            if tx_id in self.prepared_transactions:
                return {'status': 'OK', 'state': 'PREPARED'}
        
        return {'status': 'OK', 'state': 'UNKNOWN'}
    
    def _execute_operation(self, operation: Dict):
        """Execute a single operation."""
        op_type = operation.get('type')
        table = operation.get('table')
        
        if op_type == 'INSERT':
            values = operation.get('values', [])
            self.db.insert(table, values)
        elif op_type == 'UPDATE':
            set_clause = operation.get('set', {})
            where = operation.get('where')
            self.db.update(table, set_clause, where)
        elif op_type == 'DELETE':
            where = operation.get('where')
            self.db.delete(table, where)


# Commands for CLI integration
class DistributedTxCommands:
    """Commands for distributed transaction management."""
    
    def __init__(self, coordinator: Optional[DistributedTransactionCoordinator] = None):
        self.coordinator = coordinator
    
    def dist_tx_begin(self, operations_json: str) -> str:
        """Begin a distributed transaction."""
        if not self.coordinator:
            return "ERROR: Distributed transaction coordinator not available"
        
        try:
            operations = json.loads(operations_json)
            tx_id = self.coordinator.begin_transaction(operations)
            return f"OK: Started distributed transaction {tx_id}"
        except Exception as e:
            return f"ERROR: {e}"
    
    def dist_tx_status(self, tx_id: str) -> str:
        """Get distributed transaction status."""
        if not self.coordinator:
            return "ERROR: Distributed transaction coordinator not available"
        
        status = self.coordinator.get_transaction_status(tx_id)
        if status:
            return json.dumps(status, indent=2)
        return f"ERROR: Transaction {tx_id} not found"
    
    def dist_tx_list(self) -> str:
        """List all distributed transactions."""
        if not self.coordinator:
            return "ERROR: Distributed transaction coordinator not available"
        
        transactions = self.coordinator.get_all_transactions()
        if not transactions:
            return "OK: No distributed transactions"
        
        lines = ["Distributed Transactions:", "-" * 60]
        for tx in transactions:
            lines.append(f"{tx['tx_id'][:8]}... | {tx['state']:<12} | {len(tx['participants'])} participants | {tx['duration']:.2f}s")
        
        return "\n".join(lines)
