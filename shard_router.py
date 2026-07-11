"""
Shard Router for KosDB

Provides key-to-shard mapping for automatic hash and range sharding.
Supports consistent hashing, range partitioning, and cross-region routing.
"""

import hashlib
import json
import threading
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict


class ShardingError(Exception):
    """Base exception for sharding errors."""
    pass


class ShardNotFoundError(ShardingError):
    """Raised when no shard can be found for a key."""
    pass


@dataclass
class Shard:
    """Represents a single shard node."""
    shard_id: str
    host: str
    port: int
    region: str = "default"
    role: str = "primary"  # primary, replica
    weight: int = 100
    active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Shard':
        return cls(**data)

    @property
    def address(self) -> Tuple[str, int]:
        return (self.host, self.port)

    def __hash__(self):
        return hash(self.shard_id)

    def __eq__(self, other):
        return isinstance(other, Shard) and other.shard_id == self.shard_id


class ConsistentHashRing:
    """Consistent hash ring for distributing keys across shards."""

    def __init__(self, replicas: int = 150):
        self.replicas = replicas
        self.ring: Dict[int, Shard] = {}
        self.sorted_keys: List[int] = []
        self._lock = threading.RLock()

    def _hash(self, key: str) -> int:
        return int(hashlib.md5(key.encode()).hexdigest(), 16)

    def add_shard(self, shard: Shard):
        with self._lock:
            for i in range(self.replicas):
                virtual_key = f"{shard.shard_id}:{i}"
                h = self._hash(virtual_key)
                self.ring[h] = shard
            self._rebuild_sorted_keys()

    def remove_shard(self, shard_id: str):
        with self._lock:
            to_remove = [h for h, s in self.ring.items() if s.shard_id == shard_id]
            for h in to_remove:
                del self.ring[h]
            self._rebuild_sorted_keys()

    def _rebuild_sorted_keys(self):
        self.sorted_keys = sorted(self.ring.keys())

    def get_shard(self, key: str) -> Shard:
        with self._lock:
            if not self.ring:
                raise ShardNotFoundError("No shards available in hash ring")

            h = self._hash(key)
            for ring_key in self.sorted_keys:
                if ring_key >= h:
                    return self.ring[ring_key]
            return self.ring[self.sorted_keys[0]]

    def get_shards(self) -> List[Shard]:
        with self._lock:
            seen = set()
            result = []
            for s in self.ring.values():
                if s.shard_id not in seen:
                    seen.add(s.shard_id)
                    result.append(s)
            return result


class RangePartitioner:
    """Range-based partitioning for ordered keys."""

    def __init__(self):
        self.ranges: List[Tuple[Optional[str], Optional[str], Shard]] = []
        self._lock = threading.RLock()

    def add_range(self, start: Optional[str], end: Optional[str], shard: Shard):
        with self._lock:
            self.ranges.append((start, end, shard))
            self.ranges.sort(key=lambda x: (x[0] or "", x[1] or ""))

    def remove_shard(self, shard_id: str):
        with self._lock:
            self.ranges = [r for r in self.ranges if r[2].shard_id != shard_id]

    def get_shard(self, key: str) -> Shard:
        with self._lock:
            for start, end, shard in self.ranges:
                if start is None or key >= start:
                    if end is None or key < end:
                        return shard
            if self.ranges:
                return self.ranges[-1][2]
            raise ShardNotFoundError("No range shards available")

    def get_shards(self) -> List[Shard]:
        with self._lock:
            seen = set()
            result = []
            for _, _, s in self.ranges:
                if s.shard_id not in seen:
                    seen.add(s.shard_id)
                    result.append(s)
            return result


class ShardRouter:
    """
    Routes keys to shards using either consistent hashing or range partitioning.
    """

    STRATEGIES = ('hash', 'range')

    def __init__(self, strategy: str = 'hash', replicas: int = 150):
        if strategy not in self.STRATEGIES:
            raise ValueError(f"Unknown sharding strategy: {strategy}")
        self.strategy = strategy
        self.hash_ring = ConsistentHashRing(replicas=replicas)
        self.range_partitioner = RangePartitioner()
        self.shards: Dict[str, Shard] = {}
        self._lock = threading.RLock()

    def add_shard(self, shard: Shard, start: Optional[str] = None, end: Optional[str] = None):
        with self._lock:
            self.shards[shard.shard_id] = shard
            if self.strategy == 'hash':
                self.hash_ring.add_shard(shard)
            else:
                self.range_partitioner.add_range(start, end, shard)

    def remove_shard(self, shard_id: str):
        with self._lock:
            if shard_id in self.shards:
                del self.shards[shard_id]
            if self.strategy == 'hash':
                self.hash_ring.remove_shard(shard_id)
            else:
                self.range_partitioner.remove_shard(shard_id)

    def get_shard_for_key(self, key: str) -> Shard:
        with self._lock:
            if self.strategy == 'hash':
                return self.hash_ring.get_shard(key)
            return self.range_partitioner.get_shard(key)

    def get_shard_for_table(self, table_name: str, key_value: Optional[str] = None) -> Shard:
        """Route a table/key to a shard. If no key value, route by table name."""
        routing_key = f"{table_name}:{key_value}" if key_value else table_name
        return self.get_shard_for_key(routing_key)

    def get_all_shards(self) -> List[Shard]:
        with self._lock:
            return list(self.shards.values())

    def get_active_shards(self) -> List[Shard]:
        return [s for s in self.get_all_shards() if s.active]

    def get_shards_in_region(self, region: str) -> List[Shard]:
        return [s for s in self.get_all_shards() if s.region == region]

    def get_replica_shards(self, primary_id: str) -> List[Shard]:
        return [s for s in self.get_all_shards() if s.metadata.get('primary') == primary_id]

    def set_shard_active(self, shard_id: str, active: bool):
        with self._lock:
            if shard_id in self.shards:
                self.shards[shard_id].active = active

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'strategy': self.strategy,
                'shards': {sid: s.to_dict() for sid, s in self.shards.items()}
            }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ShardRouter':
        router = cls(strategy=data.get('strategy', 'hash'))
        for sid, shard_data in data.get('shards', {}).items():
            shard = Shard.from_dict(shard_data)
            start = shard.metadata.pop('range_start', None)
            end = shard.metadata.pop('range_end', None)
            router.add_shard(shard, start, end)
        return router


def _extract_primary_key_value(params: Dict[str, Any]) -> Optional[str]:
    """Extract a routing key value from parsed command parameters."""
    where = params.get('where')
    if isinstance(where, dict):
        # Prefer id or primary key equality
        for key in ('id', 'pk', 'key', 'row_id'):
            if key in where:
                return str(where[key])
        if where:
            return str(next(iter(where.values())))

    values = params.get('values')
    if isinstance(values, list) and values:
        return str(values[0])

    return None
