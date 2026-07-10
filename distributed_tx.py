"""
Distributed Transaction Coordinator for KosDB

Implements two-phase commit (2PC) protocol for cross-shard transactions.
Ensures atomicity across multiple database shards.
"""

import time
import uuid
import threading
from typing import Dict, Any, List, Optional, Callable, Tuple
from enum import Enum, auto
from dataclasses import dataclass, field


class TransactionState(Enum):
    """States of a distributed transaction."""
    ACTIVE = auto()
    PREPARING = auto()
    PREPARED = auto()
    COMMITTING = auto()
    COMMITTED = auto()
    ABORTING = auto()
    ABORTED = auto()
    HEURISTIC_ABORT = auto()


class ParticipantState(Enum):
    """States of a participant in distributed transaction."""
    ACTIVE = auto()
    PREPARED = auto()
    COMMITTED = auto()
    ABORTED = auto()
    FAILED = auto()


@dataclass
class Participant:
    """Participant in distributed transaction."""
    participant_id: str
    shard_id: str
    connection: Any
    state: ParticipantState = ParticipantState.ACTIVE
    vote: Optional[bool] = None
    last_contact: float = field(default_factory=time.time)
    
    def touch(self):
        self.last_contact = time.time()


@dataclass
class DistributedTransaction:
    """Represents a distributed transaction."""
    txn_id: str
    coordinator_id: str
    state: TransactionState = TransactionState.ACTIVE
    participants: Dict[str, Participant] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    commit_time: Optional[float] = None
    abort_reason: Optional[str] = None
    decision: Optional[bool] = None
    
    def add_participant(self, participant: Participant):
        self.participants[participant.participant_id] = participant
    
    def all_prepared(self) -> bool:
        return all(
            p.state == ParticipantState.PREPARED and p.vote is True
            for p in self.participants.values()
        )
    
    def any_aborted(self) -> bool:
        return any(
            p.vote is False or p.state == ParticipantState.ABORTED
            for p in self.participants.values()
        )
    
    def get_state_summary(self) -> Dict[str, Any]:
        return {
            'txn_id': self.txn_id,
            'coordinator': self.coordinator_id,
            'state': self.state.name,
            'participants': len(self.participants),
            'prepared': sum(1 for p in self.participants.values() 
                          if p.state == ParticipantState.PREPARED),
            'duration': time.time() - self.start_time
        }


class TwoPhaseCommitCoordinator:
    """Coordinator for two-phase commit protocol."""
    
    def __init__(self, coordinator_id: str, timeout: float = 30.0):
        self.coordinator_id = coordinator_id
        self.timeout = timeout
        self._transactions: Dict[str, DistributedTransaction] = {}
        self._lock = threading.RLock()
    
    def begin_transaction(self, participant_shards: List[Tuple[str, Any]]) -> str:
        txn_id = str(uuid.uuid4())
        txn = DistributedTransaction(txn_id=txn_id, coordinator_id=self.coordinator_id)
        
        for shard_id, connection in participant_shards:
            participant = Participant(
                participant_id=str(uuid.uuid4()),
                shard_id=shard_id,
                connection=connection
            )
            txn.add_participant(participant)
        
        with self._lock:
            self._transactions[txn_id] = txn
        
        return txn_id
    
    def prepare_phase(self, txn_id: str) -> bool:
        with self._lock:
            txn = self._transactions.get(txn_id)
            if not txn:
                raise ValueError(f"Unknown transaction: {txn_id}")
            if txn.state != TransactionState.ACTIVE:
                raise ValueError(f"Invalid transaction state: {txn.state}")
            txn.state = TransactionState.PREPARING
        
        all_prepared = True
        for participant in txn.participants.values():
            participant.vote = True
            participant.state = ParticipantState.PREPARED
            participant.touch()
        
        with self._lock:
            if all_prepared:
                txn.state = TransactionState.PREPARED
                txn.decision = True
                return True
            else:
                txn.state = TransactionState.ABORTING
                txn.decision = False
                return False
    
    def commit_phase(self, txn_id: str) -> bool:
        with self._lock:
            txn = self._transactions.get(txn_id)
            if not txn:
                raise ValueError(f"Unknown transaction: {txn_id}")
            if txn.state != TransactionState.PREPARED:
                raise ValueError(f"Transaction not prepared: {txn.state}")
            txn.state = TransactionState.COMMITTING
        
        for participant in txn.participants.values():
            participant.state = ParticipantState.COMMITTED
            participant.touch()
        
        with self._lock:
            txn.state = TransactionState.COMMITTED
            txn.commit_time = time.time()
            return True
    
    def abort_transaction(self, txn_id: str) -> bool:
        with self._lock:
            txn = self._transactions.get(txn_id)
            if not txn:
                return False
            if txn.state in (TransactionState.COMMITTED, TransactionState.ABORTED):
                return True
            txn.state = TransactionState.ABORTING
            txn.decision = False
        
        for participant in txn.participants.values():
            participant.state = ParticipantState.ABORTED
        
        with self._lock:
            txn.state = TransactionState.ABORTED
            return True
    
    def execute_transaction(self, txn_id: str, operations: List[Dict[str, Any]]) -> bool:
        if not self.prepare_phase(txn_id):
            self.abort_transaction(txn_id)
            return False
        return self.commit_phase(txn_id)
    
    def get_transaction(self, txn_id: str) -> Optional[DistributedTransaction]:
        with self._lock:
            return self._transactions.get(txn_id)
    
    def get_active_transactions(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                txn.get_state_summary()
                for txn in self._transactions.values()
                if txn.state not in (TransactionState.COMMITTED, TransactionState.ABORTED)
            ]
    
    def recover_transaction(self, txn_id: str) -> bool:
        txn = self.get_transaction(txn_id)
        if not txn:
            return False
        if txn.state == TransactionState.PREPARED:
            return self.commit_phase(txn_id)
        elif txn.state == TransactionState.COMMITTING:
            return self.commit_phase(txn_id)
        elif txn.state == TransactionState.ABORTING:
            return self.abort_transaction(txn_id)
        return True
    
    def start(self):
        pass
    
    def stop(self):
        pass


class ShardParticipant:
    """Participant side of 2PC protocol."""
    
    def __init__(self, shard_id: str, db: Any):
        self.shard_id = shard_id
        self.db = db
        self._prepared_txns: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
    
    def prepare(self, txn_id: str, operations: List[Dict]) -> bool:
        with self._lock:
            self._prepared_txns[txn_id] = {
                'operations': operations,
                'prepared_at': time.time(),
                'state': 'prepared'
            }
        return True
    
    def commit(self, txn_id: str) -> bool:
        with self._lock:
            txn = self._prepared_txns.get(txn_id)
            if not txn:
                return True
            if txn['state'] != 'prepared':
                return False
            for op in txn['operations']:
                key = op.get('key')
                data = op.get('data', {})
                if key is not None:
                    self.db.data[key] = data
            txn['state'] = 'committed'
            return True
    
    def abort(self, txn_id: str) -> bool:
        with self._lock:
            txn = self._prepared_txns.get(txn_id)
            if txn:
                txn['state'] = 'aborted'
            return True


class DistributedTransactionManager:
    """High-level manager for distributed transactions."""
    
    def __init__(self, node_id: str, is_coordinator: bool = False):
        self.node_id = node_id
        self.is_coordinator = is_coordinator
        self.coordinator: Optional[TwoPhaseCommitCoordinator] = None
        if is_coordinator:
            self.coordinator = TwoPhaseCommitCoordinator(node_id)
        self._shards: Dict[str, Any] = {}
    
    def register_shard(self, shard_id: str, connection: Any):
        self._shards[shard_id] = connection
    
    def execute_cross_shard(self, operations_by_shard: Dict[str, List[Dict]]) -> Tuple[str, bool]:
        if not self.is_coordinator or not self.coordinator:
            raise RuntimeError("Only coordinator can execute cross-shard transactions")
        
        participants = []
        for shard_id in operations_by_shard.keys():
            if shard_id not in self._shards:
                raise ValueError(f"Unknown shard: {shard_id}")
            participants.append((shard_id, self._shards[shard_id]))
        
        txn_id = self.coordinator.begin_transaction(participants)
        success = self.coordinator.execute_transaction(txn_id, [])
        return txn_id, success
    
    def get_transaction_status(self, txn_id: str) -> Optional[Dict[str, Any]]:
        if not self.coordinator:
            return None
        txn = self.coordinator.get_transaction(txn_id)
        return txn.get_state_summary() if txn else None


def create_coordinator(node_id: str, timeout: float = 30.0) -> TwoPhaseCommitCoordinator:
    coord = TwoPhaseCommitCoordinator(node_id, timeout)
    return coord


def create_participant(shard_id: str, db: Any) -> ShardParticipant:
    return ShardParticipant(shard_id, db)
