"""
Tests for time-series module.
"""

import unittest
import time
from timeseries import (
    TimeSeriesPoint,
    TimeRange,
    TimeBucket,
    Hypertable,
    HypertablePartition,
    RetentionPolicy,
    TimeSeriesEngine,
    get_timeseries_engine
)


class TestTimeSeriesPoint(unittest.TestCase):
    
    def test_create_point(self):
        """Test creating time-series point."""
        point = TimeSeriesPoint(
            timestamp=1234567890.0,
            value=42.5,
            tags={'sensor': 'temp1'}
        )
        
        self.assertEqual(point.timestamp, 1234567890.0)
        self.assertEqual(point.value, 42.5)
        self.assertEqual(point.tags['sensor'], 'temp1')


class TestTimeRange(unittest.TestCase):
    
    def test_contains(self):
        """Test time range containment."""
        tr = TimeRange(start=1000, end=2000)
        
        self.assertTrue(tr.contains(1500))
        self.assertTrue(tr.contains(1000))
        self.assertFalse(tr.contains(2500))


class TestTimeBucket(unittest.TestCase):
    
    def test_get_bucket_start(self):
        """Test bucket start calculation."""
        bucket = TimeBucket('1h')
        
        start = bucket.get_bucket_start(7500)
        self.assertEqual(start, 7200)
    
    def test_iterate_buckets(self):
        """Test bucket iteration."""
        bucket = TimeBucket('1h')
        buckets = bucket.iterate_buckets(0, 7200)
        
        self.assertEqual(len(buckets), 2)


class TestHypertablePartition(unittest.TestCase):
    
    def test_insert_and_query(self):
        """Test insert and query operations."""
        partition = HypertablePartition(
            start_time=0,
            end_time=3600,
            chunk_name="test_0"
        )
        
        point = TimeSeriesPoint(timestamp=1800, value=42.0)
        self.assertTrue(partition.insert(point))
        
        results = partition.query(TimeRange(start=0, end=3600))
        self.assertEqual(len(results), 1)


class TestHypertable(unittest.TestCase):
    
    def setUp(self):
        self.table = Hypertable("test_table", chunk_interval=3600)
    
    def test_insert(self):
        """Test basic insert."""
        point = TimeSeriesPoint(
            timestamp=time.time(),
            value=42.0,
            tags={'sensor': 'temp1'}
        )
        
        self.assertTrue(self.table.insert(point))
    
    def test_query(self):
        """Test query operation."""
        now = time.time()
        
        for i in range(5):
            point = TimeSeriesPoint(
                timestamp=now + i,
                value=float(i)
            )
            self.table.insert(point)
        
        results = self.table.query(TimeRange(start=now, end=now + 10))
        self.assertEqual(len(results), 5)
    
    def test_time_bucket(self):
        """Test time bucket aggregation."""
        now = time.time()
        
        for i in range(10):
            point = TimeSeriesPoint(
                timestamp=now + i * 3600,
                value=float(i * 10)
            )
            self.table.insert(point)
        
        results = self.table.time_bucket('1d', TimeRange(start=now, end=now + 40000))
        self.assertGreater(len(results), 0)
    
    def test_stats(self):
        """Test statistics."""
        point = TimeSeriesPoint(timestamp=time.time(), value=42.0)
        self.table.insert(point)
        
        stats = self.table.get_stats()
        self.assertEqual(stats['name'], 'test_table')


class TestTimeSeriesEngine(unittest.TestCase):
    
    def setUp(self):
        self.engine = TimeSeriesEngine()
        for name in list(self.engine.list_hypertables()):
            self.engine.drop_hypertable(name)
    
    def test_create_hypertable(self):
        """Test creating hypertable."""
        table = self.engine.create_hypertable("metrics")
        self.assertIsNotNone(table)
    
    def test_global_engine(self):
        """Test global engine singleton."""
        engine1 = get_timeseries_engine()
        engine2 = get_timeseries_engine()
        self.assertIs(engine1, engine2)


class TestRetentionPolicy(unittest.TestCase):
    
    def test_should_delete(self):
        """Test TTL check."""
        policy = RetentionPolicy(
            raw_ttl=3600,
            downsample_interval=3600,
            downsample_ttl=7200
        )
        
        now = time.time()
        self.assertFalse(policy.should_delete(now - 100))
        self.assertTrue(policy.should_delete(now - 4000))


if __name__ == '__main__':
    unittest.main(verbosity=2)
