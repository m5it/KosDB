#!/usr/bin/env python3
"""Unit tests for geospatial command handlers."""

import unittest
from unittest.mock import MagicMock, patch
from geospatial_commands import (
    CreateSpatialIndexCommand,
    DropSpatialIndexCommand,
    SpatialNearCommand,
    SpatialWithinCommand,
    SpatialIntersectsCommand,
    SpatialBoundingBoxCommand,
    SpatialInsertCommand,
    SpatialDeleteCommand,
    GeohashEncodeCommand,
    GeohashNeighborsCommand,
    SpatialDistanceCommand,
    SpatialStatsCommand,
)


class TestGeospatialCommands(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.auth = MagicMock()

    @patch('geospatial_commands.get_spatial_manager')
    def test_create_index(self, mock_mgr):
        mock_mgr.return_value.create_index.return_value = MagicMock()
        cmd = CreateSpatialIndexCommand(self.db, self.auth)
        result = cmd.execute('users')
        self.assertEqual(result['status'], 'success')

    @patch('geospatial_commands.get_spatial_manager')
    def test_drop_index(self, mock_mgr):
        mock_mgr.return_value.drop_index.return_value = True
        cmd = DropSpatialIndexCommand(self.db, self.auth)
        result = cmd.execute('users')
        self.assertEqual(result['status'], 'success')

    @patch('geospatial_commands.get_spatial_manager')
    def test_near(self, mock_mgr):
        index = MagicMock()
        index.near.return_value = [('id1', 10.0, {})]
        mock_mgr.return_value.get_index.return_value = index
        cmd = SpatialNearCommand(self.db, self.auth)
        result = cmd.execute('users', 0.0, 0.0, 100.0)
        self.assertEqual(result['count'], 1)

    @patch('geospatial_commands.get_spatial_manager')
    def test_near_no_index(self, mock_mgr):
        mock_mgr.return_value.get_index.return_value = None
        cmd = SpatialNearCommand(self.db, self.auth)
        result = cmd.execute('users', 0.0, 0.0, 100.0)
        self.assertEqual(result['status'], 'error')

    @patch('geospatial_commands.get_spatial_manager')
    def test_within_circle(self, mock_mgr):
        index = MagicMock()
        index.within.return_value = [('id1', None, {})]
        mock_mgr.return_value.get_index.return_value = index
        cmd = SpatialWithinCommand(self.db, self.auth)
        result = cmd.execute('users', 'circle', lat=0.0, lon=0.0, radius=100.0)
        self.assertEqual(result['status'], 'success')

    @patch('geospatial_commands.get_spatial_manager')
    def test_intersects_invalid(self, mock_mgr):
        mock_mgr.return_value.get_index.return_value = MagicMock()
        cmd = SpatialIntersectsCommand(self.db, self.auth)
        result = cmd.execute('users', 'invalid')
        self.assertEqual(result['status'], 'error')

    @patch('geospatial_commands.get_spatial_manager')
    def test_bounding_box(self, mock_mgr):
        index = MagicMock()
        index.search.return_value = [('id1', None, {})]
        mock_mgr.return_value.get_index.return_value = index
        cmd = SpatialBoundingBoxCommand(self.db, self.auth)
        result = cmd.execute('users', -1.0, -1.0, 1.0, 1.0)
        self.assertEqual(result['status'], 'success')

    @patch('geospatial_commands.get_spatial_manager')
    def test_insert(self, mock_mgr):
        index = MagicMock()
        mock_mgr.return_value.get_index.return_value = index
        cmd = SpatialInsertCommand(self.db, self.auth)
        result = cmd.execute('users', 'id1', 0.0, 0.0)
        self.assertEqual(result['status'], 'success')

    @patch('geospatial_commands.get_spatial_manager')
    def test_delete(self, mock_mgr):
        index = MagicMock()
        index.delete.return_value = True
        mock_mgr.return_value.get_index.return_value = index
        cmd = SpatialDeleteCommand(self.db, self.auth)
        result = cmd.execute('users', 'id1')
        self.assertEqual(result['status'], 'success')

    def test_geohash_encode(self):
        cmd = GeohashEncodeCommand(self.db, self.auth)
        result = cmd.execute(0.0, 0.0, precision=8)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(len(result['geohash']), 8)

    def test_geohash_neighbors(self):
        cmd = GeohashNeighborsCommand(self.db, self.auth)
        result = cmd.execute('s0000000')
        self.assertEqual(result['count'], 8)

    def test_distance(self):
        cmd = SpatialDistanceCommand(self.db, self.auth)
        result = cmd.execute(0.0, 0.0, 0.0, 1.0)
        self.assertEqual(result['status'], 'success')
        self.assertGreater(result['distance_meters'], 0)

    @patch('geospatial_commands.get_spatial_manager')
    def test_stats(self, mock_mgr):
        mock_mgr.return_value.list_indexes.return_value = ['users']
        cmd = SpatialStatsCommand(self.db, self.auth)
        result = cmd.execute()
        self.assertEqual(result['count'], 1)


if __name__ == '__main__':
    unittest.main()
