"""
Tests for geospatial module.
"""

import unittest
import math
from geospatial import (
    Point,
    BoundingBox,
    PointGeometry,
    CircleGeometry,
    PolygonGeometry,
    RTreeIndex,
    haversine_distance,
    geohash_encode,
    geohash_decode,
    geohash_neighbors
)


class TestPoint(unittest.TestCase):
    
    def test_valid_point(self):
        """Test creating valid point."""
        p = Point(40.7128, -74.0060)
        self.assertEqual(p.lat, 40.7128)
        self.assertEqual(p.lon, -74.0060)
    
    def test_invalid_latitude(self):
        """Test invalid latitude."""
        with self.assertRaises(ValueError):
            Point(91, 0)
        with self.assertRaises(ValueError):
            Point(-91, 0)
    
    def test_invalid_longitude(self):
        """Test invalid longitude."""
        with self.assertRaises(ValueError):
            Point(0, 181)
        with self.assertRaises(ValueError):
            Point(0, -181)


class TestBoundingBox(unittest.TestCase):
    
    def test_contains_point(self):
        """Test point containment."""
        bbox = BoundingBox(0, 0, 10, 10)
        self.assertTrue(bbox.contains(Point(5, 5)))
        self.assertFalse(bbox.contains(Point(15, 5)))
        self.assertFalse(bbox.contains(Point(5, 15)))
    
    def test_intersects(self):
        """Test bbox intersection."""
        bbox1 = BoundingBox(0, 0, 10, 10)
        bbox2 = BoundingBox(5, 5, 15, 15)
        bbox3 = BoundingBox(20, 20, 30, 30)
        
        self.assertTrue(bbox1.intersects(bbox2))
        self.assertFalse(bbox1.intersects(bbox3))
    
    def test_expand(self):
        """Test expanding bbox with point."""
        bbox = BoundingBox(0, 0, 10, 10)
        expanded = bbox.expand(Point(15, 15))
        
        self.assertEqual(expanded.max_lat, 15)
        self.assertEqual(expanded.max_lon, 15)


class TestPointGeometry(unittest.TestCase):
    
    def test_contains(self):
        """Test point containment."""
        p = PointGeometry(40.7128, -74.0060)
        
        self.assertTrue(p.contains(Point(40.7128, -74.0060)))
        self.assertFalse(p.contains(Point(40.7129, -74.0060)))
    
    def test_distance_to(self):
        """Test distance calculation."""
        p1 = PointGeometry(40.7128, -74.0060)  # NYC
        p2 = Point(51.5074, -0.1278)  # London
        
        distance = p1.distance_to(p2)
        # Should be approximately 5570 km
        self.assertAlmostEqual(distance, 5570000, delta=50000)


class TestCircleGeometry(unittest.TestCase):
    
    def test_contains(self):
        """Test circle containment."""
        circle = CircleGeometry(0, 0, 1000)
        
        # Point at center
        self.assertTrue(circle.contains(Point(0, 0)))
        
        # Point 500m away
        self.assertTrue(circle.contains(Point(0.0045, 0)))
        
        # Point far away
        self.assertFalse(circle.contains(Point(1, 0)))
    
    def test_bbox(self):
        """Test circle bbox."""
        circle = CircleGeometry(0, 0, 1000)
        bbox = circle.bbox
        
        self.assertLess(bbox.min_lat, 0)
        self.assertGreater(bbox.max_lat, 0)


class TestPolygonGeometry(unittest.TestCase):
    
    def test_contains(self):
        """Test polygon containment."""
        polygon = PolygonGeometry([
            (0, 0),
            (0, 10),
            (10, 10),
            (10, 0)
        ])
        
        self.assertTrue(polygon.contains(Point(5, 5)))
        self.assertFalse(polygon.contains(Point(15, 5)))
    
    def test_invalid_polygon(self):
        """Test invalid polygon."""
        with self.assertRaises(ValueError):
            PolygonGeometry([(0, 0), (10, 10)])


class TestHaversineDistance(unittest.TestCase):
    
    def test_same_point(self):
        """Test distance to same point."""
        p = Point(40.7128, -74.0060)
        dist = haversine_distance(p, p)
        self.assertAlmostEqual(dist, 0, places=1)
    
    def test_nyc_to_london(self):
        """Test known distance NYC to London."""
        nyc = Point(40.7128, -74.0060)
        london = Point(51.5074, -0.1278)
        
        dist = haversine_distance(nyc, london)
        # Should be approximately 5570 km
        self.assertAlmostEqual(dist / 1000, 5570, delta=50)


class TestGeohash(unittest.TestCase):
    
    def test_encode(self):
        """Test geohash encoding."""
        geohash = geohash_encode(40.7484, -73.9857, 12)
        self.assertEqual(len(geohash), 12)
        self.assertTrue(all(c in '0123456789bcdefghjkmnpqrstuvwxyz' for c in geohash))
    
    def test_decode(self):
        """Test geohash decoding."""
        lat, lon = 40.7484, -73.9857
        geohash = geohash_encode(lat, lon, 8)
        
        bbox = geohash_decode(geohash)
        
        # Center should be close to original
        center_lat = (bbox[0] + bbox[2]) / 2
        center_lon = (bbox[1] + bbox[3]) / 2
        
        self.assertAlmostEqual(center_lat, lat, places=1)
        self.assertAlmostEqual(center_lon, lon, places=1)
    
    def test_neighbors(self):
        """Test geohash neighbors."""
        geohash = geohash_encode(40.7484, -73.9857, 6)
        neighbors = geohash_neighbors(geohash)
        
        self.assertEqual(len(neighbors), 8)
        self.assertNotIn(geohash, neighbors)


class TestRTreeIndex(unittest.TestCase):
    
    def setUp(self):
        self.index = RTreeIndex()
    
    def test_insert_and_search(self):
        """Test insert and search."""
        self.index.insert("nyc", PointGeometry(40.7128, -74.0060), {"name": "NYC"})
        self.index.insert("la", PointGeometry(34.0522, -118.2437), {"name": "LA"})
        
        bbox = BoundingBox(35, -80, 45, -70)
        results = self.index.search(bbox)
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], "nyc")
    
    def test_near(self):
        """Test near query."""
        self.index.insert("nyc", PointGeometry(40.7128, -74.0060), {"name": "NYC"})
        self.index.insert("jersey", PointGeometry(40.7282, -74.0776), {"name": "Jersey City"})
        self.index.insert("la", PointGeometry(34.0522, -118.2437), {"name": "LA"})
        
        results = self.index.near(Point(40.7128, -74.0060), 50000)
        
        ids = [r[0] for r in results]
        self.assertIn("nyc", ids)
        self.assertIn("jersey", ids)
        self.assertNotIn("la", ids)
    
    def test_within_circle(self):
        """Test within circle query."""
        self.index.insert("nyc", PointGeometry(40.7128, -74.0060), {"name": "NYC"})
        self.index.insert("la", PointGeometry(34.0522, -118.2437), {"name": "LA"})
        
        circle = CircleGeometry(40.7128, -74.0060, 20000)
        results = self.index.within(circle)
        
        ids = [r[0] for r in results]
        self.assertIn("nyc", ids)
        self.assertNotIn("la", ids)
    
    def test_stats(self):
        """Test index statistics."""
        self.index.insert("nyc", PointGeometry(40.7128, -74.0060), {})
        self.index.insert("la", PointGeometry(34.0522, -118.2437), {})
        
        stats = self.index.get_stats()
        self.assertEqual(stats['total_objects'], 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
