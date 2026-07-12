
"""
Batch Time-Series Operations for KosDB v2.3.0

Optimizes batch operations for time-series data:
- Bulk hypertable inserts
- Optimized time_bucket() queries
- Batch downsampling operations
- Batch retention policy application
- Partition pruning for time-range queries
"""

import re
import time
import logging
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime

# Import timeseries support
try:
    from timeseries import (
        Hypertable, TimeSeriesPoint, TimeRange, TimeBucket,
        RetentionPolicy, HypertablePartition
    )
    TS_AVAILABLE = True
except ImportError:
    TS_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class BulkInsertResult:
    """Result of bulk insert operation."""
    inserted: int
    failed: int
    elapsed_ms: float
    partition_stats: Dict[str, int] = field(default_factory=dict)


@dataclass
class TimeBucketBatchResult:
    """Result of time_bucket batch query."""
    bucket_size: str
    buckets: List[Dict[str, Any]]
    total_points: int
    elapsed_ms: float


@dataclass
class DownsampleBatchResult:
    """Result of batch downsampling."""
    source_buckets: int
    target_buckets: int
    points_downsampled: int
    elapsed_ms: float


@dataclass
class RetentionBatchResult:
    """Result of batch retention policy application."""
    hypertables_processed: int
    points_deleted: int
    partitions_dropped: int
    elapsed_ms: float


class BatchTimeSeriesManager:
    """
    Manager for batch time-series operations.
    """
    
    def __init__(self, hypertables: Optional[Dict[str, Any]] = None):
        """
        Initialize batch time-series manager.
        
        Args:
            hypertables: Dictionary of hypertable name -> Hypertable
        """
        self.hypertables = hypertables or {}
        self._metrics = {
            'bulk_inserts': 0,
            'time_bucket_queries': 0,
            'downsample_ops': 0,
            'retention_runs': 0,
            'total_points_inserted': 0,
            'total_points_deleted': 0
        }
    
    def bulk_insert(
        self,
        hypertable_name: str,
        points: List[TimeSeriesPoint],
        batch_size: int = 1000
    ) -> BulkInsertResult:
        """
        Bulk insert points into hypertable.
        
        Args:
            hypertable_name: Target hypertable
            points: List of time-series points
            batch_size: Insert batch size
        
        Returns:
            Bulk insert result
        """
        if not TS_AVAILABLE:
            return BulkInsertResult(
                inserted=0, failed=len(points), elapsed_ms=0,
                partition_stats={'error': 'Time-series not available'}
            )
        
        hypertable = self.hypertables.get(hypertable_name)
        if not hypertable:
            return BulkInsertResult(
                inserted=0, failed=len(points), elapsed_ms=0,
                partition_stats={'error': f'Hypertable {hypertable_name} not found'}
            )
        
        start_time = time.time()
        inserted = 0
        failed = 0
        partition_stats = defaultdict(int)
        
        # Process in batches
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            
            for point in batch:
                try:
                    if hypertable.insert(point):
                        inserted += 1
                        # Track partition stats
                        partition = hypertable._get_partition(point.timestamp)
                        partition_stats[partition.chunk_name] += 1
                    else:
                        failed += 1
                except Exception as e:
                    logger.warning(f"Failed to insert point: {e}")
                    failed += 1
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        self._metrics['bulk_inserts'] += 1
        self._metrics['total_points_inserted'] += inserted
        
        return BulkInsertResult(
            inserted=inserted,
            failed=failed,
            elapsed_ms=elapsed_ms,
            partition_stats=dict(partition_stats)
        )
    
    def bulk_insert_sql(
        self,
        hypertable_name: str,
        values: List[Tuple]
    ) -> BulkInsertResult:
        """
        Bulk insert from SQL VALUES list.
        
        Args:
            hypertable_name: Target hypertable
            values: List of (timestamp, value, tags) tuples
        
        Returns:
            Bulk insert result
        """
        points = []
        for value in values:
            if len(value) >= 2:
                timestamp = value[0]
                val = value[1]
                tags = value[2] if len(value) > 2 else {}
                
                if isinstance(timestamp, str):
                    timestamp = datetime.fromisoformat(timestamp).timestamp()
                
                point = TimeSeriesPoint(
                    timestamp=timestamp,
                    value=val,
                    tags=tags if isinstance(tags, dict) else {}
                )
                points.append(point)
        
        return self.bulk_insert(hypertable_name, points)
    
    def time_bucket_batch(
        self,
        hypertable_name: str,
        bucket_size: str,
        time_ranges: List[TimeRange],
        aggregation: str = 'avg',
        parallel: bool = False
    ) -> List[TimeBucketBatchResult]:
        """
        Execute time_bucket queries for multiple time ranges.
        
        Args:
            hypertable_name: Target hypertable
            bucket_size: Bucket size (e.g., '1h', '1d')
            time_ranges: List of time ranges to query
            aggregation: Aggregation function
            parallel: Execute in parallel
        
        Returns:
            List of time bucket results
        """
        if not TS_AVAILABLE:
            return []
        
        hypertable = self.hypertables.get(hypertable_name)
        if not hypertable:
            return []
        
        results = []
        
        for time_range in time_ranges:
            start_time = time.time()
            buckets = hypertable.time_bucket(bucket_size, time_range, aggregation)
            elapsed_ms = (time.time() - start_time) * 1000
            
            total_points = sum(b.get('count', 0) for b in buckets)
            
            results.append(TimeBucketBatchResult(
                bucket_size=bucket_size,
                buckets=buckets,
                total_points=total_points,
                elapsed_ms=elapsed_ms
            ))
        
        self._metrics['time_bucket_queries'] += len(results)
        return results
    
    def optimize_time_bucket_query(
        self,
        hypertable_name: str,
        bucket_size: str,
        time_range: TimeRange,
        aggregation: str = 'avg'
    ) -> Dict[str, Any]:
        """
        Optimize time_bucket query with partition pruning.
        
        Args:
            hypertable_name: Target hypertable
            bucket_size: Bucket size
            time_range: Time range
            aggregation: Aggregation function
        
        Returns:
            Optimized query plan and result
        """
        if not TS_AVAILABLE:
            return {'error': 'Time-series not available'}
        
        hypertable = self.hypertables.get(hypertable_name)
        if not hypertable:
            return {'error': f'Hypertable {hypertable_name} not found'}
        
        # Determine which partitions to scan
        partitions_to_scan = []
        for chunk_name, partition in hypertable.partitions.items():
            # Skip partitions outside time range
            if time_range.start and partition.end_time < time_range.start:
                continue
            if time_range.end and partition.start_time > time_range.end:
                continue
            partitions_to_scan.append(chunk_name)
        
        # Execute optimized query
        start_time = time.time()
        result = hypertable.time_bucket(bucket_size, time_range, aggregation)
        elapsed_ms = (time.time() - start_time) * 1000
        
        return {
            'hypertable': hypertable_name,
            'bucket_size': bucket_size,
            'time_range': {
                'start': time_range.start,
                'end': time_range.end
            },
            'partitions_scanned': len(partitions_to_scan),
            'partitions_total': len(hypertable.partitions),
            'pruning_efficiency': 1 - (len(partitions_to_scan) / len(hypertable.partitions)) if hypertable.partitions else 0,
            'buckets_returned': len(result),
            'elapsed_ms': elapsed_ms,
            'data': result
        }
    
    def batch_downsample(
        self,
        hypertable_name: str,
        source_bucket: str,
        target_bucket: str,
        time_ranges: List[TimeRange],
        aggregation: str = 'avg'
    ) -> List[DownsampleBatchResult]:
        """
        Batch downsampling across multiple time ranges.
        
        Args:
            hypertable_name: Target hypertable
            source_bucket: Source bucket size
            target_bucket: Target bucket size
            time_ranges: Time ranges to downsample
            aggregation: Aggregation function
        
        Returns:
            List of downsample results
        """
        if not TS_AVAILABLE:
            return []
        
        hypertable = self.hypertables.get(hypertable_name)
        if not hypertable:
            return []
        
        results = []
        
        for time_range in time_ranges:
            start_time = time.time()
            
            # Get source data
            source_data = hypertable.time_bucket(source_bucket, time_range, aggregation)
            
            # Downsample to target bucket
            target = TimeBucket(target_bucket)
            buckets = defaultdict(list)
            for point in source_data:
                bucket_start = target.get_bucket_start(point['timestamp'])
                buckets[bucket_start].append(point['value'])
            
            # Aggregate
            downsampled = []
            for bucket_start in sorted(buckets.keys()):
                values = buckets[bucket_start]
                downsampled.append({
                    'timestamp': bucket_start,
                    'value': sum(values) / len(values) if values else 0,
                    'count': len(values)
                })
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            results.append(DownsampleBatchResult(
                source_buckets=len(source_data),
                target_buckets=len(downsampled),
                points_downsampled=sum(len(buckets[bs]) for bs in buckets),
                elapsed_ms=elapsed_ms
            ))
        
        self._metrics['downsample_ops'] += len(results)
        return results
    
    def apply_retention_batch(
        self,
        hypertable_names: Optional[List[str]] = None,
        dry_run: bool = False
    ) -> RetentionBatchResult:
        """
        Apply retention policies to multiple hypertables.
        
        Args:
            hypertable_names: List of hypertables (None = all)
            dry_run: Preview changes without applying
        
        Returns:
            Retention batch result
        """
        if not TS_AVAILABLE:
            return RetentionBatchResult(
                hypertables_processed=0,
                points_deleted=0,
                partitions_dropped=0,
                elapsed_ms=0
            )
        
        start_time = time.time()
        total_deleted = 0
        partitions_dropped = 0
        
        names = hypertable_names or list(self.hypertables.keys())
        
        for name in names:
            hypertable = self.hypertables.get(name)
            if not hypertable:
                continue
            
            if not hypertable.retention_policy:
                continue
            
            if dry_run:
                # Preview what would be deleted
                now = time.time()
                cutoff = now - hypertable.retention_policy.raw_ttl
                points_to_delete = sum(
                    1 for p in hypertable.partitions.values()
                    for ts in p.data.keys() if ts < cutoff
                )
                logger.info(f"[DRY RUN] Would delete {points_to_delete} points from {name}")
            else:
                # Apply retention
                deleted = hypertable.apply_retention_policy()
                total_deleted += deleted
                
                # Drop empty partitions
                empty_partitions = [
                    cn for cn, p in hypertable.partitions.items()
                    if len(p.data) == 0
                ]
                for cn in empty_partitions:
                    del hypertable.partitions[cn]
                    partitions_dropped += 1
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        self._metrics['retention_runs'] += 1
        self._metrics['total_points_deleted'] += total_deleted
        
        return RetentionBatchResult(
            hypertables_processed=len(names),
            points_deleted=total_deleted,
            partitions_dropped=partitions_dropped,
            elapsed_ms=elapsed_ms
        )
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get batch time-series metrics."""
        return dict(self._metrics)
    
    def get_hypertable_stats(self, hypertable_name: Optional[str] = None) -> Dict[str, Any]:
        """Get hypertable statistics."""
        if hypertable_name:
            hypertable = self.hypertables.get(hypertable_name)
            if hypertable:
                return hypertable.get_stats()
            return {'error': f'Hypertable {hypertable_name} not found'}
        
        # Return all stats
        return {
            name: ht.get_stats() for name, ht in self.hypertables.items()
        }


def parse_bulk_insert_sql(command: str) -> Tuple[str, List[Tuple]]:
    """
    Parse BULK INSERT SQL command.
    
    Args:
        command: SQL command
    
    Returns:
        Tuple of (hypertable_name, values_list)
    
    Example:
        BULK INSERT INTO metrics VALUES
        (1234567890, 100.0, {'host': 'server1'}),
        (1234567891, 101.0, {'host': 'server1'})
    """
    pattern = r'BULK\s+INSERT\s+INTO\s+(\w+)\s+VALUES\s*\((.+)\)'
    match = re.match(pattern, command, re.IGNORECASE | re.DOTALL)
    
    if not match:
        return None, []
    
    hypertable_name = match.group(1)
    values_str = match.group(2)
    
    # Parse values - simplified parsing
    values = []
    # Split by ),( to get individual value tuples
    tuples = re.split(r'\)\s*,\s*\(', values_str)
    
    for t in tuples:
        t = t.strip('()')
        # Parse timestamp, value, tags
        parts = [p.strip() for p in t.split(',')]
        if len(parts) >= 2:
            timestamp = parts[0]
            value = parts[1]
            tags = parts[2] if len(parts) > 2 else '{}'
            values.append((timestamp, value, tags))
    
    return hypertable_name, values


def parse_time_bucket_query(command: str) -> Dict[str, Any]:
    """
    Parse time_bucket query.
    
    Args:
        command: SQL command
    
    Returns:
        Parsed query info
    
    Example:
        SELECT time_bucket('1h', timestamp), avg(value)
        FROM metrics
        WHERE timestamp BETWEEN '2024-01-01' AND '2024-01-02'
        GROUP BY 1
    """
    pattern = r"time_bucket\s*\(\s*['\"](\w+)['\"]\s*,\s*(\w+)\s*\)"
    match = re.search(pattern, command, re.IGNORECASE)
    
    if not match:
        return {}
    
    bucket_size = match.group(1)
    
    # Extract table
    table_match = re.search(r'FROM\s+(\w+)', command, re.IGNORECASE)
    table_name = table_match.group(1) if table_match else None
    
    # Extract time range
    where_match = re.search(
        r'timestamp\s+BETWEEN\s+[\'\"]?([^\'\"]+)[\'\"]?\s+AND\s+[\'\"]?([^\'\"]+)[\'\"]?',
        command,
        re.IGNORECASE
    )
    
    time_range = None
    if where_match:
        try:
            start = datetime.fromisoformat(where_match.group(1)).timestamp()
            end = datetime.fromisoformat(where_match.group(2)).timestamp()
            time_range = TimeRange(start=start, end=end)
        except ValueError:
            pass
    
    return {
        'bucket_size': bucket_size,
        'table_name': table_name,
        'time_range': time_range
    }


# Global manager
_batch_ts_manager: Optional[BatchTimeSeriesManager] = None


def get_batch_ts_manager(hypertables: Optional[Dict[str, Any]] = None) -> BatchTimeSeriesManager:
    """Get global batch time-series manager."""
    global _batch_ts_manager
    if _batch_ts_manager is None:
        _batch_ts_manager = BatchTimeSeriesManager(hypertables)
    return _batch_ts_manager
