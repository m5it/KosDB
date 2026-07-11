#!/usr/bin/env python3
"""Unit tests for geospatial parser."""

import unittest
from geospatial_parser import GeospatialParser, get_geospatial_parser


class TestGeospatialParser(unittest.TestCase):
    def setUp(self):
        self.parser = GeospatialParser()

    def test_create_spatial_index(self):
        result = self.parser.parse('CREATE SPATIAL INDEX ON users (location)')
        self.assertEqual(result['type'], 'CREATE_SPATIAL_INDEX')
        self.assertEqual(result['column'], 'location')

    def test_drop_spatial_index(self):
        result = self.parser.parse('DROP SPATIAL INDEX ON users')
        self.assertEqual(result['type'], 'DROP_SPATIAL_INDEX')

    def test_near(self):
        result = self.parser.parse('NEAR users LAT 0.0 LON 0.0 RADIUS 100 UNIT meters')
        self.assertEqual(result['type'], 'NEAR')
        self.assertEqual(result['radius'], 100.0)

    def test_within_circle(self):
        result = self.parser.parse('WITHIN users CIRCLE 0.0 0.0 100.0')
        self.assertEqual(result['type'], 'WITHIN_CIRCLE')

    def test_within_polygon(self):
        result = self.parser.parse('WITHIN users POLYGON (0 0),(1 0),(1 1),(0 1)')
        self.assertEqual(result['type'], 'WITHIN_POLYGON')
        self.assertEqual(len(result['points']), 4)

    def test_intersects_bbox(self):
        result = self.parser.parse('INTERSECTS users BBOX -1 -1 1 1')
        self.assertEqual(result['type'], 'INTERSECTS_BBOX')

    def test_bounding_box(self):
        result = self.parser.parse('BOUNDING_BOX users -1 -1 1 1')
        self.assertEqual(result['type'], 'BOUNDING_BOX')

    def test_spatial_insert(self):
        result = self.parser.parse('SPATIAL INSERT users id1 0.0 0.0')
        self.assertEqual(result['type'], 'SPATIAL_INSERT')

    def test_spatial_delete(self):
        result = self.parser.parse('SPATIAL DELETE users id1')
        self.assertEqual(result['type'], 'SPATIAL_DELETE')

    def test_geohash_encode(self):
        result = self.parser.parse('GEOHASH ENCODE 0.0 0.0 PRECISION 8')
        self.assertEqual(result['precision'], 8)

    def test_geohash_neighbors(self):
        result = self.parser.parse('GEOHASH NEIGHBORS s0000000')
        self.assertEqual(result['type'], 'GEOHASH_NEIGHBORS')

    def test_distance(self):
        result = self.parser.parse('DISTANCE 0.0 0.0 0.0 1.0')
        self.assertEqual(result['type'], 'DISTANCE')

    def test_spatial_stats(self):
        result = self.parser.parse('SPATIAL STATS users')
        self.assertEqual(result['type'], 'SPATIAL_STATS')

    def test_unrelated(self):
        self.assertIsNone(self.parser.parse('SELECT 1'))

    def test_singleton(self):
        self.assertIs(get_geospatial_parser(), get_geospatial_parser())


if __name__ == '__main__':
    unittest.main()
