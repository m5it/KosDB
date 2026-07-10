"""
Automatic Failover and Leader Election for LevelDB Socket Server

Implements Raft-inspired consensus for leader election and automatic failover.
"""

import socket
import threading
import json
import time
import random
from typing import Dict, Any, List, Optional, Tuple, Callable
from enum import Enum, auto
from dataclasses import dataclass, field
from collections import deque
import select


class NodeState(Enum):
    """Raft node states."""
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"


class LogEntry:
    """Single entry in the replicated log."""
    def __init__(self, term: int, index: int, command: Dict[str, Any]):
        self.term = term
        self.index = index
        self.command = command
        self.committed = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'term': self.term,
            'index': self.index,
            'command': self.command,
            'committed': self.committed
        }


@dataclass
class NodeInfo:
    """Information about a cluster node."""
    node_id: str
    host: str
    port: int
    last_heartbeat: float = field(default_factory=time.time)
    is_alive: bool = True
    match_index: int = 0
    next_index: int = 1


class RaftConsensus:
    """
    Raft consensus implementation for leader election and log replication.
    """
    
    def __init__(self, node_id: str, host: str, port: int, 
                 peers: List[Tuple[str, str, int]], 
                 on_leader_elected: Optional[Callable] = None,
                 on_follower_promoted: Optional[Callable] = None):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.peers: Dict[str, NodeInfo] = {}
        
        for peer_id, peer_host, peer_port in peers:
            self.peers[peer_id] = NodeInfo(peer_id, peer_host, peer_port)
        
        self.state = NodeState.FOLLOWER
        self.current_term = 0
        self.voted_for: Optional[str] = None
        self.log: List[LogEntry] = []
        self.commit_index = 0
        self.last_applied = 0
        
        # Volatile state
        self.leader_id: Optional[str] = None
        self.election_timeout = random.uniform(0.15, 0.3)  # 150-300ms
        self.heartbeat_interval = 0.05  # 50ms
        self.last_heartbeat_time = time.time()
        
        # Callbacks
        self.on_leader_elected = on_leader_elected
        self.on_follower_promoted = on_follower_promoted
        
        # Networking
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self._lock = threading.RLock()
        
        # Vote counting
        self.votes_received = 0
        
        # Apply queue
        self._apply_queue: deque = deque()
    
    def start(self):
        """Start the Raft node."""
        self.running = True
        
        # Start server
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(10)
        
        print(f"[RAFT] Node {self.node_id} started on {self.host}:{self.port}")
        
        # Start threads
        threads = [
            threading.Thread(target=self._accept_loop, daemon=True),
            threading.Thread(target=self._election_timer, daemon=True),
            threading.Thread(target=self._heartbeat_sender, daemon=True),
            threading.Thread(target=self._log_applier, daemon=True)
        ]
        
        for t in threads:
            t.start()
        
        return threads
    
    def stop(self):
        """Stop the Raft node."""
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
    
    def _accept_loop(self):
        """Accept incoming connections."""
        while self.running:
            try:
                self.server_socket.settimeout(1.0)
                client_socket, address = self.server_socket.accept()
                handler = threading.Thread(
                    target=self._handle_connection,
                    args=(client_socket, address),
                    daemon=True
                )
                handler.start()
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"[RAFT] Accept error: {e}")
    
    def _handle_connection(self, client_socket: socket.socket, address: Tuple[str, int]):
        """Handle incoming Raft RPC."""
        try:
            data = client_socket.recv(65536)
            if not data:
                return
            
            message = json.loads(data.decode())
            response = self._process_rpc(message)
            
            if response:
                client_socket.sendall(json.dumps(response).encode())
        except Exception as e:
            print(f"[RAFT] Connection handler error: {e}")
        finally:
            client_socket.close()
    
    def _send_rpc(self, node: NodeInfo, message: Dict) -> Optional[Dict]:
        """Send RPC to a node."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            sock.connect((node.host, node.port))
            sock.sendall(json.dumps(message).encode())
            
            sock.settimeout(1.0)
            data = b''
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
            
            sock.close()
            return json.loads(data.decode()) if data else None
        except Exception as e:
            node.is_alive = False
            return None
    
    def _process_rpc(self, message: Dict) -> Optional[Dict]:
        """Process incoming RPC."""
        rpc_type = message.get('type')
        
        if rpc_type == 'RequestVote':
            return self._handle_request_vote(message)
        elif rpc_type == 'AppendEntries':
            return self._handle_append_entries(message)
        elif rpc_type == 'Heartbeat':
            return self._handle_heartbeat(message)
        
        return None
    
    def _handle_request_vote(self, message: Dict) -> Dict:
        """Handle RequestVote RPC."""
        term = message.get('term', 0)
        candidate_id = message.get('candidate_id')
        last_log_index = message.get('last_log_index', 0)
        last_log_term = message.get('last_log_term', 0)
        
        with self._lock:
            # Reply false if term < currentTerm
            if term < self.current_term:
                return {'term': self.current_term, 'vote_granted': False}
            
            # If term > currentTerm, update term and convert to follower
            if term > self.current_term:
                self.current_term = term
                self.voted_for = None
                self.state = NodeState.FOLLOWER
            
            # Check if we can vote for this candidate
            can_vote = (self.voted_for is None or self.voted_for == candidate_id)
            log_is_current = (last_log_term > self._last_log_term() or 
                            (last_log_term == self._last_log_term() and 
                             last_log_index >= len(self.log)))
            
            if can_vote and log_is_current:
                self.voted_for = candidate_id
                self.last_heartbeat_time = time.time()  # Reset timeout
                return {'term': self.current_term, 'vote_granted': True}
            
            return {'term': self.current_term, 'vote_granted': False}
    
    def _handle_append_entries(self, message: Dict) -> Dict:
        """Handle AppendEntries RPC."""
        term = message.get('term', 0)
        leader_id = message.get('leader_id')
        prev_log_index = message.get('prev_log_index', 0)
        prev_log_term = message.get('prev_log_term', 0)
        entries = message.get('entries', [])
        leader_commit = message.get('leader_commit', 0)
        
        with self._lock:
            # Reply false if term < currentTerm
            if term < self.current_term:
                return {'term': self.current_term, 'success': False}
            
            # Update term and convert to follower
            if term > self.current_term:
                self.current_term = term
                self.voted_for = None
            
            self.state = NodeState.FOLLOWER
            self.leader_id = leader_id
            self.last_heartbeat_time = time.time()
            
            # Reply false if log doesn't contain entry at prevLogIndex
            if prev_log_index > 0:
                if prev_log_index > len(self.log):
                    return {'term': self.current_term, 'success': False}
                if self.log[prev_log_index - 1].term != prev_log_term:
                    return {'term': self.current_term, 'success': False}
            
            # Append new entries
            for i, entry_data in enumerate(entries):
                index = prev_log_index + i + 1
                if index <= len(self.log):
                    # Existing entry conflicts with new one
                    if self.log[index - 1].term != entry_data['term']:
                        # Delete existing entry and all that follow it
                        self.log = self.log[:index - 1]
                        self.log.append(LogEntry(
                            entry_data['term'],
                            entry_data['index'],
                            entry_data['command']
                        ))
                else:
                    self.log.append(LogEntry(
                        entry_data['term'],
                        entry_data['index'],
                        entry_data['command']
                    ))
            
            # Update commit index
            if leader_commit > self.commit_index:
                self.commit_index = min(leader_commit, len(self.log))
            
            return {'term': self.current_term, 'success': True}
    
    def _handle_heartbeat(self, message: Dict) -> Dict:
        """Handle heartbeat from leader."""
        term = message.get('term', 0)
        leader_id = message.get('leader_id')
        
        with self._lock:
            if term >= self.current_term:
                self.current_term = term
                self.state = NodeState.FOLLOWER
                self.leader_id = leader_id
                self.last_heartbeat_time = time.time()
                self.voted_for = None
        
        return {'term': self.current_term, 'success': True}
    
    def _election_timer(self):
        """Monitor election timeout."""
        while self.running:
            time.sleep(0.01)  # 10ms check interval
            
            with self._lock:
                if self.state == NodeState.LEADER:
                    continue
                
                elapsed = time.time() - self.last_heartbeat_time
                if elapsed > self.election_timeout:
                    self._start_election()
    
    def _start_election(self):
        """Start a new election."""
        self.state = NodeState.CANDIDATE
        self.current_term += 1
        self.voted_for = self.node_id
        self.votes_received = 1
        self.last_heartbeat_time = time.time()
        
        print(f"[RAFT] {self.node_id} starting election for term {self.current_term}")
        
        # Request votes from all peers
        message = {
            'type': 'RequestVote',
            'term': self.current_term,
            'candidate_id': self.node_id,
            'last_log_index': len(self.log),
            'last_log_term': self._last_log_term()
        }
        
        threads = []
        for node in self.peers.values():
            t = threading.Thread(
                target=self._request_vote,
                args=(node, message),
                daemon=True
            )
            threads.append(t)
            t.start()
        
        # Wait for votes with timeout
        for t in threads:
            t.join(timeout=0.3)
        
        # Check if we won
        with self._lock:
            if self.state == NodeState.CANDIDATE and self.votes_received > (len(self.peers) + 1) / 2:
                self._become_leader()
    
    def _request_vote(self, node: NodeInfo, message: Dict):
        """Request vote from a peer."""
        response = self._send_rpc(node, message)
        
        if response:
            with self._lock:
                if response.get('term') > self.current_term:
                    self.current_term = response['term']
                    self.state = NodeState.FOLLOWER
                    self.voted_for = None
                elif response.get('vote_granted'):
                    self.votes_received += 1
    
    def _become_leader(self):
        """Convert to leader."""
        self.state = NodeState.LEADER
        self.leader_id = self.node_id
        
        # Initialize leader state
        for node in self.peers.values():
            node.next_index = len(self.log) + 1
            node.match_index = 0
        
        print(f"[RAFT] {self.node_id} became leader for term {self.current_term}")
        
        if self.on_leader_elected:
            try:
                self.on_leader_elected(self.node_id)
            except Exception as e:
                print(f"[RAFT] Leader elected callback error: {e}")
    
    def _heartbeat_sender(self):
        """Send heartbeats to followers."""
        while self.running:
            time.sleep(self.heartbeat_interval)
            
            with self._lock:
                if self.state != NodeState.LEADER:
                    continue
            
            # Send heartbeats/AppendEntries to all peers
            for node in self.peers.values():
                threading.Thread(
                    target=self._send_append_entries,
                    args=(node,),
                    daemon=True
                ).start()
    
    def _send_append_entries(self, node: NodeInfo):
        """Send AppendEntries to a follower."""
        with self._lock:
            if self.state != NodeState.LEADER:
                return
            
            prev_index = node.next_index - 1
            prev_term = self.log[prev_index - 1].term if prev_index > 0 and prev_index <= len(self.log) else 0
            
            entries = []
            for i in range(node.next_index - 1, len(self.log)):
                entries.append(self.log[i].to_dict())
            
            message = {
                'type': 'AppendEntries',
                'term': self.current_term,
                'leader_id': self.node_id,
                'prev_log_index': prev_index,
                'prev_log_term': prev_term,
                'entries': entries,
                'leader_commit': self.commit_index
            }
        
        response = self._send_rpc(node, message)
        
        if response:
            with self._lock:
                if response.get('term') > self.current_term:
                    self.current_term = response['term']
                    self.state = NodeState.FOLLOWER
                    self.voted_for = None
                    return
                
                if response.get('success'):
                    node.match_index = prev_index + len(entries)
                    node.next_index = node.match_index + 1
                else:
                    node.next_index = max(1, node.next_index - 1)
    
    def _log_applier(self):
        """Apply committed entries to state machine."""
        while self.running:
            time.sleep(0.01)
            
            with self._lock:
                while self.last_applied < self.commit_index:
                    self.last_applied += 1
                    entry = self.log[self.last_applied - 1]
                    entry.committed = True
                    self._apply_queue.append(entry)
    
    def _last_log_term(self) -> int:
        """Get term of last log entry."""
        if not self.log:
            return 0
        return self.log[-1].term
    
    def propose(self, command: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Propose a command to the log.
        Only works if this node is the leader.
        """
        with self._lock:
            if self.state != NodeState.LEADER:
                if self.leader_id:
                    return False, f"Not leader. Current leader: {self.leader_id}"
                return False, "No leader elected"
            
            entry = LogEntry(
                self.current_term,
                len(self.log) + 1,
                command
            )
            self.log.append(entry)
            
            # Replicate to majority
            return self._replicate_entry(entry)
    
    def _replicate_entry(self, entry: LogEntry) -> Tuple[bool, Optional[str]]:
        """Replicate entry to majority of followers."""
        success_count = 1  # Count self
        
        threads = []
        results = []
        
        def replicate_to(node: NodeInfo):
            response = self._send_append_entries_sync(node, entry)
            results.append(response is not None and response.get('success'))
        
        for node in self.peers.values():
            t = threading.Thread(target=replicate_to, args=(node,), daemon=True)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join(timeout=1.0)
        
        success_count += sum(1 for r in results if r)
        
        if success_count > (len(self.peers) + 1) / 2:
            # Majority achieved, commit
            with self._lock:
                if entry.index > self.commit_index:
                    self.commit_index = entry.index
            return True, None
        
        return False, "Failed to replicate to majority"
    
    def _send_append_entries_sync(self, node: NodeInfo, entry: LogEntry) -> Optional[Dict]:
        """Send single entry to follower synchronously."""
        message = {
            'type': 'AppendEntries',
            'term': self.current_term,
            'leader_id': self.node_id,
            'prev_log_index': entry.index - 1,
            'prev_log_term': self.log[entry.index - 2].term if entry.index > 1 else 0,
            'entries': [entry.to_dict()],
            'leader_commit': self.commit_index
        }
        return self._send_rpc(node, message)
    
    def get_status(self) -> Dict[str, Any]:
        """Get current node status."""
        with self._lock:
            return {
                'node_id': self.node_id,
                'state': self.state.value,
                'term': self.current_term,
                'leader': self.leader_id,
                'log_size': len(self.log),
                'commit_index': self.commit_index,
                'last_applied': self.last_applied,
                'peers': {
                    node_id: {
                        'alive': node.is_alive,
                        'match_index': node.match_index
                    }
                    for node_id, node in self.peers.items()
                }
            }


class FailoverManager:
    """
    Manages automatic failover using Raft consensus.
    Coordinates with replication for seamless failover.
    """
    
    def __init__(self, node_id: str, host: str, port: int,
                 peers: List[Tuple[str, str, int]],
                 db=None, replication_client=None):
        self.node_id = node_id
        self.db = db
        self.replication_client = replication_client
        
        self.raft = RaftConsensus(
            node_id, host, port, peers,
            on_leader_elected=self._on_leader_elected,
            on_follower_promoted=self._on_follower_promoted
        )
        
        self.is_primary = False
        self.health_check_interval = 5.0
        self._health_thread: Optional[threading.Thread] = None
        self.running = False
    
    def start(self):
        """Start failover manager."""
        self.running = True
        self.raft.start()
        
        # Start health monitoring
        self._health_thread = threading.Thread(target=self._health_monitor, daemon=True)
        self._health_thread.start()
        
        print(f"[FAILOVER] Manager started for node {self.node_id}")
    
    def stop(self):
        """Stop failover manager."""
        self.running = False
        self.raft.stop()
    
    def _on_leader_elected(self, leader_id: str):
        """Called when this node becomes leader."""
        self.is_primary = True
        print(f"[FAILOVER] Node {self.node_id} became PRIMARY")
        
        # Start accepting writes
        if self.db:
            # Promote to read-write mode
            pass
    
    def _on_follower_promoted(self, leader_id: str):
        """Called when another node becomes leader."""
        self.is_primary = False
        print(f"[FAILOVER] Node {self.node_id} is now FOLLOWER of {leader_id}")
        
        # Switch to read-only or replica mode
        if self.replication_client:
            # Ensure replication is running
            pass
    
    def _health_monitor(self):
        """Monitor cluster health."""
        while self.running:
            time.sleep(self.health_check_interval)
            
            status = self.raft.get_status()
            
            # Log status periodically
            print(f"[FAILOVER] Status: {status['state']}, "
                  f"Leader: {status['leader']}, "
                  f"Term: {status['term']}")
    
    def execute_command(self, command: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Execute a command through Raft consensus.
        Only succeeds if this node is the leader.
        """
        success, error = self.raft.propose(command)
        
        if success:
            # Apply command locally
            return self._apply_command(command)
        
        if error:
            return False, error
        
        return False, "Command failed"
    
    def _apply_command(self, command: Dict[str, Any]) -> Tuple[bool, str]:
        """Apply command to local database."""
        try:
            cmd_type = command.get('type')
            
            if cmd_type == 'INSERT':
                if self.db:
                    self.db.insert(command['table'], command['values'])
                    return True, "OK"
            
            elif cmd_type == 'UPDATE':
                if self.db:
                    self.db.update(command['table'], command['set'], command.get('where'))
                    return True, "OK"
            
            elif cmd_type == 'DELETE':
                if self.db:
                    self.db.delete(command['table'], command.get('where'))
                    return True, "OK"
            
            return True, "OK"
            
        except Exception as e:
            return False, str(e)
    
    def get_cluster_status(self) -> Dict[str, Any]:
        """Get complete cluster status."""
        raft_status = self.raft.get_status()
        
        return {
            'node_id': self.node_id,
            'is_primary': self.is_primary,
            'raft': raft_status,
            'replication': {
                'connected': self.replication_client.connected if self.replication_client else False
            } if self.replication_client else None
        }


# Commands for CLI integration
class FailoverCommands:
    """Commands for failover management."""
    
    def __init__(self, failover_manager: Optional[FailoverManager] = None):
        self.manager = failover_manager
    
    def failover_status(self) -> str:
        """Get failover status."""
        if not self.manager:
            return "ERROR: Failover manager not available"
        
        status = self.manager.get_cluster_status()
        lines = [
            "Failover Status:",
            "-" * 50,
            f"Node ID: {status['node_id']}",
            f"Is Primary: {status['is_primary']}",
            f"Raft State: {status['raft']['state']}",
            f"Current Term: {status['raft']['term']}",
            f"Leader: {status['raft']['leader']}",
            f"Log Size: {status['raft']['log_size']}",
            f"Commit Index: {status['raft']['commit_index']}",
            "-" * 50,
            "Peers:"
        ]
        
        for peer_id, peer_info in status['raft']['peers'].items():
            lines.append(f"  {peer_id}: alive={peer_info['alive']}, match={peer_info['match_index']}")
        
        return "\n".join(lines)
    
    def propose_command(self, command_json: str) -> str:
        """Propose a command through Raft."""
        if not self.manager:
            return "ERROR: Failover manager not available"
        
        try:
            command = json.loads(command_json)
            success, result = self.manager.execute_command(command)
            
            if success:
                return f"OK: {result}"
            return f"ERROR: {result}"
            
        except json.JSONDecodeError:
            return "ERROR: Invalid JSON"
        except Exception as e:
            return f"ERROR: {e}"
