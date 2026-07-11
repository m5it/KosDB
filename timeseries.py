"""
Time-Series Data Support for KosDB
"""

import time
import json
import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)


class TimeSeriesError(Exception):
    pass


@dataclass
class TimeSeriesPoint:
    timestamp: float
    value: Union[float, int, str, Dict[str, Any]]
    tags: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        if isinstance(self.value, dict):
            self.value = json.dumps(self.value)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp,
            'value': self.value,
            'tags': self.tags
        }


@dataclass 
class TimeRange:
    start: Optional[float] = None
    end: Optional[float] = None
    
    def contains(self, timestamp: float) -> bool:
        if self.start is not None and timestamp < self.start:
            return False
        if self.end is not None and timestamp > self.end:
            return False
        return True


class TimeBucket:
    BUCKET_SIZES = {
        '1m': 60,
        '5m': 300,
        '15m': 900,
        '1h': 3600,
        '6h': 21600,
        '1d': 86400,
        '1w': 604800,
        '30d': 2592000
    }
    
    def __init__(self, bucket_size: str):
        if bucket_size not in self.BUCKET_SIZES:
            raise ValueError(f"Invalid bucket size: {bucket_size}")
        self.bucket_size = bucket_size
        self.seconds = self.BUCKET_SIZES[bucket_size]
    
    def get_bucket_start(self, timestamp: float) -> float:
        return (timestamp // self.seconds) * self.seconds
    
    def iterate_buckets(self, start: float, end: float) -> List[Tuple[float, float]]:
        buckets = []
        current = self.get_bucket_start(start)
        while current < end:
            bucket_end = current + self.seconds
            buckets.append((current, min(bucket_end, end)))
            current = bucket_end
        return buckets


@dataclass
class RetentionPolicy:
    raw_ttl: int
    downsample_interval: int
    downsample_ttl: int
    enabled: bool = True
    
    def should_delete(self, timestamp: float, is_downsampled: bool = False) -> bool:
        now = time.time()
        if is_downsampled:
            return (now - timestamp) > self.downsample_ttl
        return (now - timestamp) > self.raw_ttl


class HypertablePartition:
    def __init__(self, start_time: float, end_time: float, chunk_name: str):
        self.start_time = start_time
        self.end_time = end_time
        self.chunk_name = chunk_name
        self.data: Dict[float, TimeSeriesPoint] = {}
        self._lock = threading.RLock()
        self.created_at = time.time()
    
    def insert(self, point: TimeSeriesPoint) -> bool:
        if not (self.start_time <= point.timestamp < self.end_time):
            return False
        with self._lock:
            self.data[point.timestamp] = point
        return True
    
    def query(self, time_range: TimeRange, tags: Optional[Dict[str, str]] = None) -> List[TimeSeriesPoint]:
        results = []
        with self._lock:
            for ts, point in self.data.items():
                if time_range.contains(ts):
                    if tags is None or all(point.tags.get(k) == v for k, v in tags.items()):
                        results.append(point)
        return sorted(results, key=lambda p: p.timestamp)
    
    def delete(self, time_range: TimeRange) -> int:
        count = 0
        with self._lock:
            to_delete = [ts for ts in self.data if time_range.contains(ts)]
            for ts in to_delete:
                del self.data[ts]
                count += 1
        return count
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'chunk_name': self.chunk_name,
                'start_time': self.start_time,
                'end_time': self.end_time,
                'point_count': len(self.data)
            }


class Hypertable:
    DEFAULT_CHUNK_INTERVAL = 86400
    
    def __init__(self, name: str, chunk_interval: int = DEFAULT_CHUNK_INTERVAL, retention_policy: Optional[RetentionPolicy] = None):
        self.name = name
        self.chunk_interval = chunk_interval
        self.retention_policy = retention_policy
        self.partitions: Dict[str, HypertablePartition] = {}
        self._lock = threading.RLock()
        self.created_at = time.time()
        self._stats = {'total_inserts': 0, 'total_queries': 0, 'total_points': 0}
        
        if retention_policy and retention_policy.enabled:
            self._start_retention_worker()
    
    def _get_partition(self, timestamp: float) -> HypertablePartition:
        start_time = (timestamp // self.chunk_interval) * self.chunk_interval
        end_time = start_time + self.chunk_interval
        chunk_name = f"{self.name}_{int(start_time)}"
        
        with self._lock:
            if chunk_name not in self.partitions:
                self.partitions[chunk_name] = HypertablePartition(start_time, end_time, chunk_name)
            return self.partitions[chunk_name]
    
    def insert(self, point: TimeSeriesPoint) -> bool:
        partition = self._get_partition(point.timestamp)
        if partition.insert(point):
            with self._lock:
                self._stats['total_inserts'] += 1
                self._stats['total_points'] += 1
            return True
        return False
    
    def query(self, time_range: TimeRange, tags: Optional[Dict[str, str]] = None, limit: Optional[int] = None) -> List[TimeSeriesPoint]:
        results = []
        with self._lock:
            partitions_to_check = list(self.partitions.values())
        
        for partition in partitions_to_check:
            if time_range.start and partition.end_time < time_range.start:
                continue
            if time_range.end and partition.start_time > time_range.end:
                continue
            results.extend(partition.query(time_range, tags))
        
        results.sort(key=lambda p: p.timestamp)
        if limit:
            results = results[:limit]
        
        with self._lock:
            self._stats['total_queries'] += 1
        return results
    
    def time_bucket(self, bucket_size: str, time_range: TimeRange, aggregation: str = 'avg') -> List[Dict[str, Any]]:
        bucket = TimeBucket(bucket_size)
        points = self.query(time_range)
        
        buckets = defaultdict(list)
        for point in points:
            bucket_start = bucket.get_bucket_start(point.timestamp)
            buckets[bucket_start].append(point)
        
        results = []
        for bucket_start in sorted(buckets.keys()):
            bucket_points = buckets[bucket_start]
            values = []
            for point in bucket_points:
                try:
                    values.append(float(point.value))
                except (ValueError, TypeError):
                    continue
            
            if not values:
                continue
            
            result = {
                'timestamp': bucket_start,
                'datetime': datetime.fromtimestamp(bucket_start).isoformat(),
                'count': len(bucket_points)
            }
            
            if aggregation == 'avg':
                result['value'] = sum(values) / len(values)
            elif aggregation == 'sum':
                result['value'] = sum(values)
            elif aggregation == 'min':
                result['value'] = min(values)
            elif aggregation == 'max':
                result['value'] = max(values)
            elif aggregation == 'first':
                result['value'] = values[0]
            elif aggregation == 'last':
                result['value'] = values[-1]
            elif aggregation == 'count':
                result['value'] = len(values)
            
            results.append(result)
        
        return results
    
    def downsample(self, source_bucket: str, target_bucket: str, time_range: TimeRange, aggregation: str = 'avg') -> List[Dict[str, Any]]:
        source_data = self.time_bucket(source_bucket, time_range, aggregation)
        target = TimeBucket(target_bucket)
        
        buckets = defaultdict(list)
        for point in source_data:
            bucket_start = target.get_bucket_start(point['timestamp'])
            buckets[bucket_start].append(point['value'])
        
        results = []
        for bucket_start in sorted(buckets.keys()):
            values = buckets[bucket_start]
            results.append({
                'timestamp': bucket_start,
                'datetime': datetime.fromtimestamp(bucket_start).isoformat(),
                'value': sum(values) / len(values) if values else 0,
                'count': len(values)
            })
        return results
    
    def apply_retention_policy(self) -> int:
        if not self.retention_policy or not self.retention_policy.enabled:
            return 0
        
        deleted = 0
        now = time.time()
        raw_cutoff = now - self.retention_policy.raw_ttl
        raw_range = TimeRange(end=raw_cutoff)
        
        with self._lock:
            for partition in list(self.partitions.values()):
                deleted += partition.delete(raw_range)
        
        logger.info(f"Retention policy deleted {deleted} points from {self.name}")
        return deleted
    
    def _start_retention_worker(self):
        def worker():
            while True:
                time.sleep(3600)
                try:
                    self.apply_retention_policy()
                except Exception as e:
                    logger.error(f"Retention policy error: {e}")
        
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            partition_stats = [p.get_stats() for p in self.partitions.values()]
            total_points = sum(p['point_count'] for p in partition_stats)
            
            rp_enabled = False
            rp_raw_ttl = None
            if self.retention_policy:
                rp_enabled = self.retention_policy.enabled
                rp_raw_ttl = self.retention_policy.raw_ttl
            
            return {
                'name': self.name,
                'created_at': self.created_at,
                'chunk_interval': self.chunk_interval,
                'partition_count': len(self.partitions),
                'total_points': total_points,
                'retention_policy': {
                    'enabled': rp_enabled,
                    'raw_ttl': rp_raw_ttl
                },
                'partitions': partition_stats,
                **self._stats
            }


class TimeSeriesEngine:
    def __init__(self):
        self.hypertables: Dict[str, Hypertable] = {}
        self._lock = threading.RLock()
    
    def create_hypertable(self, name: str, chunk_interval: int = Hypertable.DEFAULT_CHUNK_INTERVAL, retention_policy: Optional[RetentionPolicy] = None) -> Hypertable:
        with self._lock:
            if name in self.hypertables:
                raise TimeSeriesError(f"Hypertable {name} already exists")
            table = Hypertable(name, chunk_interval, retention_policy)
            self.hypertables[name] = table
            logger.info(f"Created hypertable: {name}")
            return table
    
    def get_hypertable(self, name: str) -> Optional[Hypertable]:
        with self._lock:
            return self.hypertables.get(name)
    
    def drop_hypertable(self, name: str) -> bool:
        with self._lock:
            if name in self.hypertables:
                del self.hypertables[name]
                logger.info(f"Dropped hypertable: {name}")
                return True
            return False
    
    def list_hypertables(self) -> List[str]:
        with self._lock:
            return list(self.hypertables.keys())
    
    def get_all_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {name: table.get_stats() for name, table in self.hypertables.items()}


_timeseries_engine = TimeSeriesEngine()

def get_timeseries_engine() -> TimeSeriesEngine:
    return _timeseries_engine
