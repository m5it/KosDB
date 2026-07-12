
"""
Tests for Batch Time-Series Operations
"""

import unittest
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from batch_timeseries import (
    BatchTimeSeriesManager,
    BulkInsertResult,
    TimeBucketBatchResult,
    DownsampleBatchResult,
    RetentionBatchResult,
    parse_bulk_insert_sql,
    parse_time_bucket_query
)

# Mock timeseries classes for testing
class MockTimeSeriesPoint:
    def __init__(self, timestamp, value, tags=None):
        self.timestamp = timestamp
        self.value = value
        self.tags = tags or {}

class MockPartition:
    def __init__(self, start_time, end_time, chunk_name):
        self.start_time = start_time
        self.end_time = end_time
        self.chunk_name = chunk_name
        self.data = {}
    
    def insert(self, point):
        if self.start_time <= point.timestamp < self.end_time:
            self.data[point.timestamp] = point
            return True
        return False

class MockHypertable:
    def __init__(self, name):
        self.name = name
        self.chunk_interval = 86400
        self.partitions = {}
        self.retention_policy = None
        self._stats = {'total_inserts': 0, 'total_queries': 0, 'total_points': 0}
    
    def _get_partition(self, timestamp):
        start_time = (timestamp // self.chunk_interval) * self.chunk_interval
        end_time = start_time + self.chunk_interval
        chunk_name = f"{self.name}_{int(start_time)}"
        
        if chunk_name not in self.partitions:
            self.partitions[chunk_name] = MockPartition(start_time, end_time, chunk_name)
        return self.partitions[chunk_name]
    
    def insert(self, point):
        partition = self._get_partition(point.timestamp)
        if partition.insert(point):
            self._stats['total_inserts'] += 1
            self._stats['total_points'] += 1
            return True
        return False
    
    def time_bucket(self, bucket_size, time_range, aggregation='avg'):
        # Mock implementation
        return [
            {'timestamp': time_range.start or 0, 'value': 100.0, 'count': 10},
            {'timestamp': (time_range.start or 0) + 3600, 'value': 101.0, 'count': 10},
        ]
    
    def apply_retention_policy(self):
        return 0
    
    def get_stats(self):
        return self._stats


class TestBatchTimeSeriesManager(unittest.TestCase):
    """Test batch time-series manager."""
    
    def setUp(self):
        self.hypertables = {
            'metrics': MockHypertable('metrics'),
            'logs': MockHypertable('logs'),
        }
        self.manager = BatchTimeSeriesManager(self.hypertables)
    
    def test_bulk_insert(self):
        """Test bulk insert."""
        points = [
            MockTimeSeriesPoint(time.time(), 100.0),
            MockTimeSeriesPoint(time.time() + 1, 101.0),
            MockTimeSeriesPoint(time.time() + 2, 102.0),
        ]
        
        result = self.manager.bulk_insert('metrics', points)
        
        self.assertIsInstance(result, BulkInsertResult)
        self.assertEqual(result.inserted, 3)
        self.assertEqual(result.failed, 0)
        self.assertGreater(result.elapsed_ms, 0)
    
    def test_bulk_insert_nonexistent_table(self):
        """Test bulk insert to non-existent table."""
        points = [MockTimeSeriesPoint(time.time(), 100.0)]
        
        result = self.manager.bulk_insert('nonexistent', points)
        
        self.assertEqual(result.inserted, 0)
        self.assertEqual(result.failed, 1)
        self.assertIn('error', result.partition_stats)
    
    def test_time_bucket_batch(self):
        """Test time bucket batch query."""
        from timeseries import TimeRange
        
        time_ranges = [
            TimeRange(start=time.time() - 3600, end=time.time()),
            TimeRange(start=time.time() - 7200, end=time.time() - 3600),
        ]
        
        results = self.manager.time_bucket_batch('metrics', '1h', time_ranges)
        
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertIsInstance(r, TimeBucketBatchResult)
            self.assertEqual(r.bucket_size, '1h')
    
    def test_optimize_time_bucket_query(self):
        """Test optimized time bucket query."""
        from timeseries import TimeRange
        
        time_range = TimeRange(start=time.time() - 3600, end=time.time())
        result = self.manager.optimize_time_bucket_query('metrics', '1h', time_range)
        
        self.assertIn('hypertable', result)
        self.assertIn('bucket_size', result)
        self.assertIn('partitions_scanned', result)
    
    def test_batch_downsample(self):
        """Test batch downsampling."""
        from timeseries import TimeRange
        
        time_ranges = [TimeRange(start=time.time() - 3600, end=time.time())]
        results = self.manager.batch_downsample('metrics', '1m', '1h', time_ranges)
        
        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], DownsampleBatchResult)
    
    def test_apply_retention_batch(self):
        """Test batch retention policy application."""
        result = self.manager.apply_retention_batch(['metrics'])
        
        self.assertIsInstance(result, RetentionBatchResult)
        self.assertEqual(result.hypertables_processed, 1)
    
    def test_get_metrics(self):
        """Test getting metrics."""
        # Do some operations
        points = [MockTimeSeriesPoint(time.time(), 100.0)]
        self.manager.bulk_insert('metrics', points)
        
        metrics = self.manager.get_metrics()
        
        self.assertEqual(metrics['bulk_inserts'], 1)
        self.assertEqual(metrics['total_points_inserted'], 1)
    
    def test_get_hypertable_stats(self):
        """Test getting hypertable stats."""
        # Insert some data first
        points = [MockTimeSeriesPoint(time.time(), 100.0)]
        self.manager.bulk_insert('metrics', points)
        
        stats = self.manager.get_hypertable_stats('metrics')
        
        self.assertIn('total_inserts', stats)
        self.assertIn('total_points', stats)


class TestParseBulkInsertSQL(unittest.TestCase):
    """Test bulk insert SQL parsing."""
    
    def test_parse_bulk_insert(self):
        """Test parsing BULK INSERT command."""
        command = "BULK INSERT INTO metrics VALUES (1234567890, 100.0, {'host': 'server1'}), (1234567891, 101.0, {'host': 'server2'})"
        
        table_name, values = parse_bulk_insert_sql(command)
        
        self.assertEqual(table_name, 'metrics')
        self.assertEqual(len(values), 2)
    
    def test_parse_invalid_command(self):
        """Test parsing invalid command."""
        command = "SELECT * FROM metrics"
        
        table_name, values = parse_bulk_insert_sql(command)
        
        self.assertIsNone(table_name)
        self.assertEqual(values, [])


class TestParseTimeBucketQuery(unittest.TestCase):
    """Test time bucket query parsing."""
    
    def test_parse_time_bucket(self):
        """Test parsing time_bucket query."""
        command = """
            SELECT time_bucket('1h', timestamp), avg(value)
            FROM metrics
            WHERE timestamp BETWEEN '2024-01-01' AND '2024-01-02'
            GROUP BY 1
        """
        
        result = parse_time_bucket_query(command)
        
        self.assertEqual(result['bucket_size'], '1h')
        self.assertEqual(result['table_name'], 'metrics')
    
    def test_parse_without_time_bucket(self):
        """Test parsing query without time_bucket."""
        command = "SELECT * FROM metrics"
        
        result = parse_time_bucket_query(command)
        
        self.assertEqual(result, {})


if __name__ == '__main__':
    unittest.main(verbosity=2)
