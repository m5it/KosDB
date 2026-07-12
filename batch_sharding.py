
"""
Batch Sharding Support for KosDB v2.3.0

Handles batch commands across sharded databases with:
- Shard analysis and grouping
- Cross-shard batch coordination
- Distributed transaction support
- Shard routing cache
- Failure handling
- METRICS for monitoring
"""

import hashlib
import logging
import threading
import time
from typing import Dict, List, Optional, Set, Tuple, Any, Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from collections import defaultdict
import uuid

# METRICS for cross-shard batch operations
METRICS = {
    'batch_sharding': {
        'total_batches': 0,
        'single_shard_batches': 0,
        'cross_shard_batches': 0,
        'failed_commands': 0,
        'shard_failures': 0,
        'retry_attempts': 0,
        'cache_hits': 0,
        'cache_misses': 0,
        '2pc_prepare_time_ms': [],
        '2pc_commit_time_ms': [],
        'successful_commits': 0,
        'failed_commits': 0,
        'timeouts': 0,
        'broadcast_commands': 0
    }
}

logger = logging.getLogger(__name__)
import time
from typing import Dict, List, Optional, Set, Tuple, Any, Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from collections import defaultdict
import uuid

logger = logging.getLogger(__name__)


class ShardRoutingStrategy(Enum):
    """Strategies for routing batch commands to shards."""
    HASH = "hash"           # Hash-based sharding
    RANGE = "range"         # Range-based sharding
    LOOKUP = "lookup"       # Lookup table-based
    CUSTOM = "custom"       # Custom routing function


@dataclass
class ShardTarget:
    """
    Represents a target shard for a batch command.
    
    Attributes:
        shard_id: Unique shard identifier
        weight: Routing weight (for load balancing)
        priority: Failover priority
        is_local: Whether shard is local to this node
    """
    shard_id: str
    weight: float = 1.0
    priority: int = 1
    is_local: bool = False


@dataclass
class BatchShardGroup:
    """
    Group of commands targeting the same shard.
    
    Attributes:
        shard_id: Target shard
        commands: List of (index, command) tuples
        shard_target: Shard target info
    """
    shard_id: str
    commands: List[Tuple[int, Any]] = field(default_factory=list)
    shard_target: Optional[ShardTarget] = None


@dataclass
class CrossShardBatchState:
    """
    State tracking for cross-shard batch execution.
    
    Attributes:
        batch_id: Unique batch identifier
        coordinator_shard: Shard coordinating the batch
        participant_shards: Set of shards participating
        prepared_shards: Set of shards that have prepared
        committed_shards: Set of shards that have committed
        failed_shards: Dict of shard_id -> error
        start_time: Batch start timestamp
        timeout_ms: Timeout in milliseconds
    """
    batch_id: str
    coordinator_shard: str
    participant_shards: Set[str] = field(default_factory=set)
    prepared_shards: Set[str] = field(default_factory=set)
    committed_shards: Set[str] = field(default_factory=set)
    failed_shards: Dict[str, str] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    timeout_ms: int = 30000


class ShardRoutingCache:
    """
    LRU cache for shard routing decisions.
    """
    
    def __init__(self, max_size: int = 10000, ttl_seconds: float = 300.0):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, Tuple[ShardTarget, float]] = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[ShardTarget]:
        """
        Get cached shard target.
        
        Args:
            key: Cache key (typically table:key_value)
        
        Returns:
            ShardTarget if cached and not expired
        """
        with self._lock:
            if key in self._cache:
                target, timestamp = self._cache[key]
                if time.time() - timestamp < self.ttl_seconds:
                    self._hits += 1
                    return target
                else:
                    # Expired
                    del self._cache[key]
            
            self._misses += 1
            return None
    
    def put(self, key: str, target: ShardTarget):
        """
        Cache shard target.
        
        Args:
            key: Cache key
            target: Shard target
        """
        with self._lock:
            # Evict oldest if at capacity
            if len(self._cache) >= self.max_size:
                oldest_key = min(self._cache.keys(), 
                               key=lambda k: self._cache[k][1])
                del self._cache[oldest_key]
            
            self._cache[key] = (target, time.time())
    
    def invalidate(self, key: str):
        """Invalidate cache entry."""
        with self._lock:
            self._cache.pop(key, None)
    
    def invalidate_table(self, table: str):
        """Invalidate all entries for a table."""
        with self._lock:
            keys_to_remove = [k for k in self._cache if k.startswith(f"{table}:")]
            for key in keys_to_remove:
                del self._cache[key]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            hit_rate = self._hits / (self._hits + self._misses) if (self._hits + self._misses) > 0 else 0
            return {
                'size': len(self._cache),
                'max_size': self.max_size,
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': hit_rate,
                'ttl_seconds': self.ttl_seconds
            }


class BatchShardAnalyzer:
    """
    Analyzes batch commands to determine target shards.
    """
    
    def __init__(
        self,
        shard_manager: Any,
        routing_strategy: ShardRoutingStrategy = ShardRoutingStrategy.HASH,
        routing_cache: Optional[ShardRoutingCache] = None
    ):
        self.shard_manager = shard_manager
        self.routing_strategy = routing_strategy
        self.routing_cache = routing_cache or ShardRoutingCache()
        self._custom_router: Optional[Callable] = None
    
    def set_custom_router(self, router: Callable[[Any], List[ShardTarget]]):
        """Set custom routing function."""
        self._custom_router = router
        self.routing_strategy = ShardRoutingStrategy.CUSTOM
    
    def analyze_batch(self, commands: List[Any]) -> Dict[str, BatchShardGroup]:
        """
        Analyze batch and group commands by target shard.
        
        Args:
            commands: List of batch commands
        
        Returns:
            Dict mapping shard_id to BatchShardGroup
        """
        shard_groups: Dict[str, BatchShardGroup] = {}
        
        for idx, cmd in enumerate(commands):
            targets = self._determine_shards(cmd)
            
            for target in targets:
                shard_id = target.shard_id
                
                if shard_id not in shard_groups:
                    shard_groups[shard_id] = BatchShardGroup(
                        shard_id=shard_id,
                        shard_target=target
                    )
                
                shard_groups[shard_id].commands.append((idx, cmd))
        
        return shard_groups
    
    def _determine_shards(self, command: Any) -> List[ShardTarget]:
        """
        Determine target shard(s) for a command.
        
        Args:
            command: Database command
        
        Returns:
            List of ShardTarget (may be multiple for broadcast)
        """
        # Extract table and key from command
        table = getattr(command, 'table', None) or command.get('table')
        key = getattr(command, 'key', None) or command.get('key')
        
        if not table or key is None:
            # Broadcast to all shards
            return self._get_all_shards()
        
        cache_key = f"{table}:{key}"
        cached = self.routing_cache.get(cache_key)
        
        if cached:
            return [cached]
        
        # Determine shard based on strategy
        if self.routing_strategy == ShardRoutingStrategy.HASH:
            target = self._hash_route(table, key)
        elif self.routing_strategy == ShardRoutingStrategy.RANGE:
            target = self._range_route(table, key)
        elif self.routing_strategy == ShardRoutingStrategy.LOOKUP:
            target = self._lookup_route(table, key)
        elif self.routing_strategy == ShardRoutingStrategy.CUSTOM:
            targets = self._custom_router(command)
            self.routing_cache.put(cache_key, targets[0])
            return targets
        else:
            target = self._hash_route(table, key)
        
        self.routing_cache.put(cache_key, target)
        return [target]
    
    def _hash_route(self, table: str, key: Any) -> ShardTarget:
        """Hash-based routing."""
        # Get available shards from shard manager
        shards = self._get_shard_list()
        
        if not shards:
            raise ValueError("No shards available")
        
        # Consistent hashing
        hash_val = hashlib.md5(f"{table}:{key}".encode()).hexdigest()
        shard_idx = int(hash_val, 16) % len(shards)
        
        return ShardTarget(
            shard_id=shards[shard_idx],
            weight=1.0,
            priority=1,
            is_local=(shards[shard_idx] == self._get_local_shard())
        )
    
    def _range_route(self, table: str, key: Any) -> ShardTarget:
        """Range-based routing."""
        # Query shard manager for range mapping
        shard_id = self.shard_manager.get_shard_for_range(table, key)
        
        return ShardTarget(
            shard_id=shard_id,
            weight=1.0,
            priority=1,
            is_local=(shard_id == self._get_local_shard())
        )
    
    def _lookup_route(self, table: str, key: Any) -> ShardTarget:
        """Lookup table-based routing."""
        shard_id = self.shard_manager.lookup_shard(table, key)
        
        return ShardTarget(
            shard_id=shard_id,
            weight=1.0,
            priority=1,
            is_local=(shard_id == self._get_local_shard())
        )
    
    def _get_all_shards(self) -> List[ShardTarget]:
        """Get all shards (for broadcast)."""
        shards = self._get_shard_list()
        local_shard = self._get_local_shard()
        
        return [
            ShardTarget(
                shard_id=s,
                weight=1.0,
                priority=1,
                is_local=(s == local_shard)
            )
            for s in shards
        ]
    
    def _get_shard_list(self) -> List[str]:
        """Get list of available shard IDs."""
        if hasattr(self.shard_manager, 'get_shards'):
            return self.shard_manager.get_shards()
        return []
    
    def _get_local_shard(self) -> Optional[str]:
        """Get local shard ID."""
        if hasattr(self.shard_manager, 'get_local_shard'):
            return self.shard_manager.get_local_shard()
        return None


class CrossShardCoordinator:
    """
    Coordinates distributed transactions across shards.
    Implements 2-phase commit for cross-shard batches.
    """
    
    def __init__(self, shard_manager: Any):
        self.shard_manager = shard_manager
        self._active_batches: Dict[str, CrossShardBatchState] = {}
        self._lock = threading.RLock()
        self._metrics = {
            'total_cross_shard_batches': 0,
            'successful_commits': 0,
            'failed_commits': 0,
            'timeouts': 0
        }
    
    def begin_cross_shard_batch(
        self,
        batch_id: str,
        participant_shards: Set[str],

    def get(self, key: str) -> Optional[ShardTarget]:
        """
        Get cached shard target.
        
        Args:
            key: Cache key (typically table:key_value)
        
        Returns:
            ShardTarget if cached and not expired
        """
        with self._lock:
            if key in self._cache:
                target, timestamp = self._cache[key]
                if time.time() - timestamp < self.ttl_seconds:
                    self._hits += 1
                    METRICS['batch_sharding']['cache_hits'] += 1
                    return target
                else:
                    # Expired
                    del self._cache[key]
            
            self._misses += 1
            METRICS['batch_sharding']['cache_misses'] += 1
            return None
            )
            
            self._active_batches[batch_id] = state
            self._metrics['total_cross_shard_batches'] += 1
            
            # Send PREPARE to all participants
            for shard_id in participant_shards:
                try:
                    self._send_prepare(shard_id, batch_id)
                except Exception as e:
                    logger.error(f"Failed to prepare shard {shard_id}: {e}")
                    state.failed_shards[shard_id] = str(e)
            
            return state
    
    def prepare_shard(self, batch_id: str, shard_id: str):
        """
        Mark shard as prepared.
        
        Args:
            batch_id: Batch identifier
            shard_id: Shard that prepared
        """
        with self._lock:
            if batch_id in self._active_batches:
                self._active_batches[batch_id].prepared_shards.add(shard_id)
    
    def commit_batch(self, batch_id: str) -> bool:
        """
        Commit cross-shard batch (2-phase commit).
        
        Args:
            batch_id: Batch identifier
        
        Returns:
            True if committed successfully
        """
        with self._lock:
            if batch_id not in self._active_batches:
                raise ValueError(f"Unknown batch: {batch_id}")
            
            state = self._active_batches[batch_id]
            
            # Check if all participants prepared
            if state.prepared_shards != state.participant_shards:
                missing = state.participant_shards - state.prepared_shards
                logger.warning(f"Batch {batch_id}: shards not prepared: {missing}")
                
                # Check for timeout
                elapsed = (time.time() - state.start_time) * 1000
                if elapsed > state.timeout_ms:
                    self._metrics['timeouts'] += 1
                    self._rollback_batch(batch_id)
                    return False
                
                return False
            
            # Phase 2: COMMIT
            committed = set()
            for shard_id in state.participant_shards:
                try:
                    self._send_commit(shard_id, batch_id)
                    committed.add(shard_id)
                except Exception as e:
                    logger.error(f"Failed to commit shard {shard_id}: {e}")
            
            state.committed_shards = committed
            
            if committed == state.participant_shards:
                self._metrics['successful_commits'] += 1
                del self._active_batches[batch_id]
                return True
            else:
                self._metrics['failed_commits'] += 1
                # Some shards committed, some didn't - requires recovery
                return False
    
    def _rollback_batch(self, batch_id: str):
        """Rollback batch on all prepared shards."""
        with self._lock:
            if batch_id not in self._active_batches:
                return
            
            state = self._active_batches[batch_id]
            
            for shard_id in state.prepared_shards:
                try:
                    self._send_rollback(shard_id, batch_id)
                except Exception as e:
                    logger.error(f"Failed to rollback shard {shard_id}: {e}")
            
            del self._active_batches[batch_id]
    
    def _get_coordinator_shard(self) -> str:
        """Get coordinator shard ID."""
        if hasattr(self.shard_manager, 'get_coordinator'):
            return self.shard_manager.get_coordinator()
        return "coordinator"
    
    def _send_prepare(self, shard_id: str, batch_id: str):
        """Send prepare message to shard."""
        # Implementation depends on shard manager protocol
        if hasattr(self.shard_manager, 'send_prepare'):
            self.shard_manager.send_prepare(shard_id, batch_id)
    
    def _send_commit(self, shard_id: str, batch_id: str):
        """Send commit message to shard."""
        if hasattr(self.shard_manager, 'send_commit'):
            self.shard_manager.send_commit(shard_id, batch_id)
    
    def _send_rollback(self, shard_id: str, batch_id: str):
        """Send rollback message to shard."""
        if hasattr(self.shard_manager, 'send_rollback'):
            self.shard_manager.send_rollback(shard_id, batch_id)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get coordinator metrics."""
        with self._lock:
            return self._metrics.copy()


class BatchShardExecutor:
    """
    Executes batch commands across shards with failure handling.
    """
    
    def __init__(
        self,
        shard_analyzer: BatchShardAnalyzer,
        coordinator: Optional[CrossShardCoordinator] = None
    ):
        self.shard_analyzer = shard_analyzer
        self.coordinator = coordinator
        self._metrics = {
            'total_batches': 0,
            'single_shard_batches': 0,
            'cross_shard_batches': 0,
            'failed_commands': 0,
            'shard_failures': 0,
            'retry_attempts': 0
        }
    
    def execute_batch(
        self,
        commands: List[Any],
        error_mode: str = "continue",
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Execute batch across shards.
        
        Args:
            commands: List of commands to execute
            error_mode: Error handling mode
            max_retries: Maximum retry attempts
        
        Returns:
            Execution results
        """
        self._metrics['total_batches'] += 1
        
        # Analyze and group by shard
        shard_groups = self.shard_analyzer.analyze_batch(commands)
        
        # Check if cross-shard
        is_cross_shard = len(shard_groups) > 1
        
        if is_cross_shard:
            self._metrics['cross_shard_batches'] += 1
            return self._execute_cross_shard(
                shard_groups, commands, error_mode, max_retries
            )
        else:
            self._metrics['single_shard_batches'] += 1
            return self._execute_single_shard(
                shard_groups, commands, error_mode, max_retries
            )
    
    def _execute_single_shard(
        self,
        shard_groups: Dict[str, BatchShardGroup],
        commands: List[Any],
        error_mode: str,
        max_retries: int
    ) -> Dict[str, Any]:
        """Execute batch on single shard."""
        shard_id = list(shard_groups.keys())[0]
        group = shard_groups[shard_id]
        
        results = []
        failed = []
        
        for idx, cmd in group.commands:
            for attempt in range(max_retries):
                try:
                    result = self._execute_on_shard(shard_id, cmd)
                    results.append((idx, result))
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        failed.append((idx, str(e)))
                        self._metrics['failed_commands'] += 1
                        if error_mode == "rollback_all":
                            # Rollback already executed commands
                            self._rollback_shard_commands(shard_id, results)
                            return {
                                'success': False,
                                'executed': len(results),
                                'failed': len(failed),
                                'errors': failed
                            }
                    else:
                        self._metrics['retry_attempts'] += 1
                        time.sleep(0.1 * (2 ** attempt))  # Exponential backoff
        
        return {
            'success': len(failed) == 0,
            'executed': len(results),
            'failed': len(failed),
            'errors': failed,
            'shard': shard_id
        }
    
    def _execute_cross_shard(
        self,
        shard_groups: Dict[str, BatchShardGroup],
        commands: List[Any],
        error_mode: str,
        max_retries: int
    ) -> Dict[str, Any]:
        """Execute batch across multiple shards."""
        if not self.coordinator:
            raise RuntimeError("Cross-shard coordinator not configured")
        
        batch_id = str(uuid.uuid4())[:16]
        participant_shards = set(shard_groups.keys())
        
        # Begin distributed transaction
        state = self.coordinator.begin_cross_shard_batch(
            batch_id, participant_shards
        )
        
        try:
            # Execute on each shard
            shard_results = {}
            failed_shards = {}
            
            for shard_id, group in shard_groups.items():
                try:
                    results = self._execute_shard_group(
                        shard_id, group, max_retries
                    )
                    shard_results[shard_id] = results
                    self.coordinator.prepare_shard(batch_id, shard_id)
                except Exception as e:
                    failed_shards[shard_id] = str(e)
                    self._metrics['shard_failures'] += 1
            
            # Check if all shards prepared
            if failed_shards:
                if error_mode == "rollback_all":
                    return {
                        'success': False,
                        'batch_id': batch_id,
                        'executed': 0,
                        'failed_shards': failed_shards
                    }
                # Continue mode: proceed with successful shards
            
            # Commit distributed transaction
            committed = self.coordinator.commit_batch(batch_id)
            
            return {
                'success': committed and not failed_shards,
                'batch_id': batch_id,
                'is_cross_shard': True,
                'shards': len(shard_groups),
                'shard_results': shard_results,
                'failed_shards': failed_shards
            }
            
        except Exception as e:
            logger.error(f"Cross-shard batch failed: {e}")
            return {
                'success': False,
                'batch_id': batch_id,
                'error': str(e)
            }
    
    def _execute_shard_group(
        self,
        shard_id: str,
        group: BatchShardGroup,
        max_retries: int
    ) -> List[Tuple[int, Any]]:
        """Execute commands on a specific shard."""
        results = []
        
        for idx, cmd in group.commands:
            for attempt in range(max_retries):
                try:
                    result = self._execute_on_shard(shard_id, cmd)
                    results.append((idx, result))
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    self._metrics['retry_attempts'] += 1
                    time.sleep(0.1 * (2 ** attempt))
        
        return results
    
    def _execute_on_shard(self, shard_id: str, command: Any) -> Any:
        """Execute command on specific shard."""
        # Delegate to shard manager
        shard_manager = self.shard_analyzer.shard_manager
        
        if hasattr(shard_manager, 'execute_command'):
            return shard_manager.execute_command(shard_id, command)
        
        raise NotImplementedError("Shard manager must implement execute_command")
    
    def _rollback_shard_commands(
        self,
        shard_id: str,
        executed: List[Tuple[int, Any]]
    ):
        """Rollback executed commands on a shard."""
        shard_manager = self.shard_analyzer.shard_manager
        
        if hasattr(shard_manager, 'rollback_commands'):
            shard_manager.rollback_commands(shard_id, executed)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get executor metrics."""
        return self._metrics.copy()


class ShardedBatchManager:
    """
    High-level manager for batch operations on sharded databases.
    """
    
    def __init__(self, shard_manager: Any):
        self.shard_manager = shard_manager
        self.routing_cache = ShardRoutingCache()
        self.analyzer = BatchShardAnalyzer(
            shard_manager=shard_manager,
            routing_cache=self.routing_cache
        )
        self.coordinator = CrossShardCoordinator(shard_manager)
        self.executor = BatchShardExecutor(self.analyzer, self.coordinator)
    
    def execute_batch(
        self,
        commands: List[Any],
        error_mode: str = "continue",
        timeout_ms: int = 30000
    ) -> Dict[str, Any]:
        """
        Execute batch on sharded database.
        
        Args:
            commands: List of commands
            error_mode: Error handling mode
            timeout_ms: Execution timeout
        
        Returns:
            Execution results
        """
        return self.executor.execute_batch(
            commands=commands,
            error_mode=error_mode,
            max_retries=3
        )
    
    def get_routing_cache_stats(self) -> Dict[str, Any]:
        """Get routing cache statistics."""
        return self.routing_cache.get_stats()
    
    def get_coordinator_metrics(self) -> Dict[str, Any]:
        """Get cross-shard coordinator metrics."""
        return self.coordinator.get_metrics()
    
    def get_executor_metrics(self) -> Dict[str, Any]:
        """Get executor metrics."""
        return self.executor.get_metrics()
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all sharded batch metrics."""
        return {
            'routing_cache': self.get_routing_cache_stats(),
            'coordinator': self.get_coordinator_metrics(),
            'executor': self.get_executor_metrics()
        }
    
    def invalidate_routing_cache(self, table: Optional[str] = None):
        """
        Invalidate routing cache.
        
        Args:
            table: Specific table to invalidate, or None for all
        """
        if table:
            self.routing_cache.invalidate_table(table)
        else:
            # Clear all (reinitialize)
            self.routing_cache = ShardRoutingCache()
            self.analyzer.routing_cache = self.routing_cache
