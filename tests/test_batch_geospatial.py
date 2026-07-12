
"""
Tests for Batch Geospatial Operations
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock geospatial module
from unittest.mock import MagicMock

mock_geospatial = MagicMock()
mock_geospatial.GEO_AVAILABLE = True

# Mock BoundingBox
class MockBoundingBox:
    def __init__(self, min_lat, min_lon, max_lat, max_lon):
        self.min_lat = min_lat
        self.min_lon = min_lon
        self.max_lat = max_lat
        self.max_lon = max_lon

mock_geospatial.BoundingBox = MockBoundingBox

sys.modules['geospatial'] = mock_geospatial

from batch_geospatial import (
    BatchGeospatialManager,
    BatchGeoAddResult,
    BatchRadiusSearchResult,
    BatchNearestNeighborResult,
    BatchBBoxQueryResult,
    parse_geo_add_batch,
    parse_radius_search_batch,
    parse_bbox_query_batch
)

class MockSpatialIndex:
    def __init__(self):
        self.points = {}
    
    def insert(self, point_id, lat, lon, metadata=None):
        self.points[point_id] = {'lat': lat, 'lon': lon, 'metadata': metadata or {}}
        return True
    
    def radius_search(self, lat, lon, radius, limit=10):
        return [(pid, 100.0) for pid in list(self.points.keys())[:limit]]
    
    def nearest_neighbors(self, lat, lon, k=5):
        return [(pid, 100.0) for pid in list(self.points.keys())[:k]]
    
    def bbox_search(self, bbox):
        return list(self.points.keys())
        return [(pid, 100.0) for pid in list(self.points.keys())[:limit]]
    
    def nearest_neighbors(self, lat, lon, k=5):
        # Mock implementation
        return [(pid, 100.0) for pid in list(self.points.keys())[:k]]
    
    def bbox_search(self, bbox):
        # Mock implementation
        return list(self.points.keys())


class TestBatchGeospatialManager(unittest.TestCase):
    """Test batch geospatial manager."""
    
    def setUp(self):
        self.index = MockSpatialIndex()
        self.manager = BatchGeospatialManager(self.index)
    
    def test_batch_geo_add(self):
        """Test batch geo add."""
        points = [
            ('p1', 40.7128, -74.0060, {'city': 'NYC'}),
            ('p2', 34.0522, -118.2437, {'city': 'LA'}),
            ('p3', 41.8781, -87.6298, {'city': 'Chicago'}),
        ]
        
        result = self.manager.batch_geo_add(points)
        
        self.assertIsInstance(result, BatchGeoAddResult)
        self.assertEqual(result.added, 3)
        self.assertEqual(result.failed, 0)
        self.assertGreater(result.elapsed_ms, 0)
    
    def test_batch_radius_search(self):
        """Test batch radius search."""
        # Add some points first
        points = [('p1', 40.7128, -74.0060), ('p2', 34.0522, -118.2437)]
        self.manager.batch_geo_add(points)
        
        centers = [
            ('c1', 40.7128, -74.0060, 10000),
            ('c2', 34.0522, -118.2437, 10000),
        ]
        
        results = self.manager.batch_radius_search(centers, k=5)
        
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertIsInstance(r, BatchRadiusSearchResult)
            self.assertEqual(len(r.results), 2)  # Mock returns all points
    
    def test_batch_nearest_neighbor(self):
        """Test batch nearest neighbor."""
        points = [('p1', 40.7128, -74.0060), ('p2', 34.0522, -118.2437)]
        self.manager.batch_geo_add(points)
        
        queries = [('q1', 40.7128, -74.0060), ('q2', 34.0522, -118.2437)]
        
        results = self.manager.batch_nearest_neighbor(queries, k=2)
        
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertIsInstance(r, BatchNearestNeighborResult)
    
    def test_batch_bbox_query(self):
        """Test batch bbox query."""
        points = [('p1', 40.7128, -74.0060), ('p2', 34.0522, -118.2437)]
        self.manager.batch_geo_add(points)
        
        bboxes = [
            ('b1', MockBoundingBox(40.0, -75.0, 41.0, -73.0)),
            ('b2', MockBoundingBox(34.0, -119.0, 35.0, -117.0)),
        ]
        
        results = self.manager.batch_bbox_query(bboxes)
        
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertIsInstance(r, BatchBBoxQueryResult)
    
    def test_get_metrics(self):
        """Test getting metrics."""
        # Do some operations
        self.manager.batch_geo_add([('p1', 40.7128, -74.0060)])
        self.manager.batch_radius_search([('c1', 40.7128, -74.0060, 10000)])
        
        metrics = self.manager.get_metrics()
        
        self.assertEqual(metrics['batch_adds'], 1)
        self.assertEqual(metrics['batch_radius_searches'], 1)
        self.assertEqual(metrics['total_points_added'], 1)


class TestParseGeoAddBatch(unittest.TestCase):
    """Test GEO ADD BATCH parsing."""
    
    def test_parse_geo_add_batch(self):
        """Test parsing GEO ADD BATCH command."""
        command = "GEO ADD BATCH my_index [('p1', 40.7128, -74.0060), ('p2', 34.0522, -118.2437)]"
        
        index_name, points = parse_geo_add_batch(command)
        
        self.assertEqual(index_name, 'my_index')

class TestParseBBoxQueryBatch(unittest.TestCase):
    """Test GEO BBOX QUERY BATCH parsing."""
    
    def test_parse_bbox_query_batch(self):
        """Test parsing batch bbox query command."""
        command = "GEO BBOX QUERY BATCH my_index [('b1', 40.0, -75.0, 41.0, -73.0), ('b2', 34.0, -119.0, 35.0, -117.0)]"
        
        result = parse_bbox_query_batch(command)
        
        self.assertEqual(result['index_name'], 'my_index')
        self.assertEqual(len(result['bboxes']), 2)
        
        self.assertEqual(result['k'], 10)  # Default


class TestParseBBoxQueryBatch(unittest.TestCase):
    """Test GEO BBOX QUERY BATCH parsing."""
    
    def test_parse_bbox_query_batch(self):
        """Test parsing batch bbox query command."""
        command = "GEO BBOX QUERY BATCH my_index [('b1', 40.0, -75.0, 41.0, -73.0), ('b2', 34.0, -119.0, 35.0, -117.0)]"
        
        result = parse_bbox_query_batch(command)
        
        self.assertEqual(result['index_name'], 'my_index')
        self.assertEqual(len(result['bboxes']), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
