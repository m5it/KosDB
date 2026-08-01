#!/usr/bin/env python3
files = {}

files['test_cdc_commands.py'] = '''#!/usr/bin/env python3
"""Unit tests for CDC command handlers."""

import unittest
from unittest.mock import MagicMock, patch
from cdc_commands import (
    CDCStartConsumerCommand,
    CDCStopConsumerCommand,
    CDCListConsumersCommand,
    CDCStatsCommand,
    CDCSetupKafkaCommand,
    CDCCreateSnapshotCommand,
)


class TestCDCStartConsumerCommand(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.auth = MagicMock()
        self.cmd = CDCStartConsumerCommand(self.db, self.auth)

    @patch('cdc_commands.get_cdc_manager')
    def test_execute_defaults(self, mock_get):
        manager = MagicMock()
        consumer = MagicMock()
        consumer.get_position.return_value = {'position': 0}
        manager.create_consumer.return_value = consumer
        mock_get.return_value = manager

        result = self.cmd.execute('c1')
        self.assertEqual(result['status'], 'success')
        self.assertIn('c1', result['message'])

    @patch('cdc_commands.get_cdc_manager')
    def test_execute_with_options(self, mock_get):
        manager = MagicMock()
        consumer = MagicMock()
        consumer.get_position.return_value = {'position': 5}
        manager.create_consumer.return_value = consumer
        mock_get.return_value = manager

        result = self.cmd.execute('c2', tables='t1,t2', operations='INSERT,UPDATE', format='protobuf', from_latest=True)
        self.assertEqual(result['status'], 'success')


class TestCDCStopConsumerCommand(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.auth = MagicMock()
        self.cmd = CDCStopConsumerCommand(self.db, self.auth)

    @patch('cdc_commands.get_cdc_manager')
    def test_stop_existing(self, mock_get):
        manager = MagicMock()
        manager.consumers = {'c1': MagicMock()}
        mock_get.return_value = manager

        result = self.cmd.execute('c1')
        self.assertEqual(result['status'], 'success')

    @patch('cdc_commands.get_cdc_manager')
    def test_stop_missing(self, mock_get):
        manager = MagicMock()
        manager.consumers = {}
        mock_get.return_value = manager

        result = self.cmd.execute('c1')
        self.assertEqual(result['status'], 'error')


class TestCDCListConsumersCommand(unittest.TestCase):
    @patch('cdc_commands.get_cdc_manager')
    def test_list(self, mock_get):
        manager = MagicMock()
        manager.consumers = {'c1': MagicMock()}
        mock_get.return_value = manager
        cmd = CDCListConsumersCommand(MagicMock(), MagicMock())
        result = cmd.execute()
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['count'], 1)


class TestCDCStatsCommand(unittest.TestCase):
    @patch('cdc_commands.get_cdc_manager')
    def test_stats(self, mock_get):
        manager = MagicMock()
        manager.get_stats.return_value = {'events': 1}
        mock_get.return_value = manager
        cmd = CDCStatsCommand(MagicMock(), MagicMock())
        result = cmd.execute()
        self.assertEqual(result['stats']['events'], 1)


class TestCDCSetupKafkaCommand(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.auth = MagicMock()
        self.cmd = CDCSetupKafkaCommand(self.db, self.auth)

    @patch('cdc_commands.get_cdc_manager')
    def test_setup_success(self, mock_get):
        manager = MagicMock()
        mock_get.return_value = manager
        result = self.cmd.execute('localhost:9092')
        self.assertEqual(result['status'], 'success')

    @patch('cdc_commands.get_cdc_manager')
    def test_setup_import_error(self, mock_get):
        manager = MagicMock()
        manager.setup_kafka.side_effect = ImportError('no kafka')
        mock_get.return_value = manager
        result = self.cmd.execute('localhost:9092')
        self.assertEqual(result['status'], 'error')


class TestCDCCreateSnapshotCommand(unittest.TestCase):
    @patch('cdc_commands.get_cdc_manager')
    def test_snapshot(self, mock_get):
        manager = MagicMock()
        event = MagicMock()
        event.to_dict.return_value = {'table': 't1'}
        manager.cdc_log.create_snapshot.return_value = [event]
        mock_get.return_value = manager
        cmd = CDCCreateSnapshotCommand(MagicMock(), MagicMock())
        result = cmd.execute('t1,t2')
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['snapshot_size'], 1)


if __name__ == '__main__':
    unittest.main()
'''

files['test_cdc_parser.py'] = '''#!/usr/bin/env python3
"""Unit tests for CDC parser."""

import unittest
from cdc_parser import CDCParser, get_cdc_parser


class TestCDCParser(unittest.TestCase):
    def setUp(self):
        self.parser = CDCParser()

    def test_start_consumer_minimal(self):
        result = self.parser.parse('CDC START CONSUMER c1')
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'CDC_START_CONSUMER')
        self.assertEqual(result['consumer_id'], 'c1')
        self.assertEqual(result['format'], 'json')
        self.assertFalse(result['from_latest'])

    def test_start_consumer_full(self):
        result = self.parser.parse('CDC START CONSUMER c2 TABLES t1,t2 OPS INSERT,UPDATE FORMAT protobuf FROM_LATEST')
        self.assertEqual(result['tables'], 't1,t2')
        self.assertEqual(result['operations'], 'INSERT,UPDATE')
        self.assertEqual(result['format'], 'protobuf')
        self.assertTrue(result['from_latest'])

    def test_stop_consumer(self):
        result = self.parser.parse('CDC STOP CONSUMER c1')
        self.assertEqual(result['type'], 'CDC_STOP_CONSUMER')

    def test_list_consumers(self):
        result = self.parser.parse('CDC LIST CONSUMERS')
        self.assertEqual(result['type'], 'CDC_LIST_CONSUMERS')

    def test_stats(self):
        result = self.parser.parse('CDC STATS')
        self.assertEqual(result['type'], 'CDC_STATS')

    def test_setup_kafka(self):
        result = self.parser.parse('CDC SETUP KAFKA localhost:9092 PREFIX kosdb')
        self.assertEqual(result['type'], 'CDC_SETUP_KAFKA')
        self.assertEqual(result['bootstrap_servers'], 'localhost:9092')
        self.assertEqual(result['topic_prefix'], 'kosdb')

    def test_snapshot(self):
        result = self.parser.parse('CDC SNAPSHOT t1,t2')
        self.assertEqual(result['type'], 'CDC_SNAPSHOT')

    def test_non_cdc_returns_none(self):
        self.assertIsNone(self.parser.parse('SELECT * FROM t'))

    def test_get_cdc_parser_singleton(self):
        self.assertIs(get_cdc_parser(), get_cdc_parser())


if __name__ == '__main__':
    unittest.main()
'''

files['test_compression_commands.py'] = '''#!/usr/bin/env python3
"""Unit tests for compression command handlers."""

import unittest
from unittest.mock import MagicMock, patch
from compression_commands import (
    CompressionEnableCommand,
    CompressionDisableCommand,
    CompressionStatsCommand,
    CompressionAlgorithmsCommand,
    CompressionBenchmarkCommand,
    CompressionTestCommand,
    CompressionCacheStatsCommand,
)


class TestCompressionCommands(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.auth = MagicMock()

    def test_enable_success(self):
        cmd = CompressionEnableCommand(self.db, self.auth)
        result = cmd.execute('users', algorithm='zlib', level=6, min_size=100)
        self.assertEqual(result['status'], 'success')

    def test_enable_invalid_algorithm(self):
        cmd = CompressionEnableCommand(self.db, self.auth)
        result = cmd.execute('users', algorithm='invalid')
        self.assertEqual(result['status'], 'error')

    def test_disable(self):
        cmd = CompressionDisableCommand(self.db, self.auth)
        result = cmd.execute('users')
        self.assertEqual(result['status'], 'success')

    @patch('compression_commands.CompressionManager')
    def test_stats(self, mock_mgr):
        mock_mgr.get_stats.return_value = {}
        cmd = CompressionStatsCommand(self.db, self.auth)
        result = cmd.execute('users')
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['table'], 'users')

    def test_algorithms(self):
        cmd = CompressionAlgorithmsCommand(self.db, self.auth)
        result = cmd.execute()
        self.assertEqual(result['status'], 'success')
        self.assertGreater(len(result['algorithms']), 0)

    def test_benchmark(self):
        cmd = CompressionBenchmarkCommand(self.db, self.auth)
        result = cmd.execute(data_size=1000)
        self.assertEqual(result['status'], 'success')

    def test_test_command(self):
        cmd = CompressionTestCommand(self.db, self.auth)
        result = cmd.execute('users', sample_size=50)
        self.assertEqual(result['status'], 'success')

    def test_cache_stats(self):
        cmd = CompressionCacheStatsCommand(self.db, self.auth)
        result = cmd.execute('users')
        self.assertEqual(result['status'], 'success')


if __name__ == '__main__':
    unittest.main()
'''

files['test_compression_parser.py'] = '''#!/usr/bin/env python3
"""Unit tests for compression parser."""

import unittest
from compression_parser import CompressionParser, get_compression_parser


class TestCompressionParser(unittest.TestCase):
    def setUp(self):
        self.parser = CompressionParser()

    def test_enable(self):
        result = self.parser.parse('COMPRESSION ENABLE users ALGORITHM zstd LEVEL 9 MIN_SIZE 200')
        self.assertEqual(result['type'], 'COMPRESSION_ENABLE')
        self.assertEqual(result['table_name'], 'users')
        self.assertEqual(result['algorithm'], 'zstd')
        self.assertEqual(result['level'], 9)
        self.assertEqual(result['min_size'], 200)

    def test_disable(self):
        result = self.parser.parse('COMPRESSION DISABLE users')
        self.assertEqual(result['type'], 'COMPRESSION_DISABLE')

    def test_stats(self):
        result = self.parser.parse('COMPRESSION STATS users')
        self.assertEqual(result['type'], 'COMPRESSION_STATS')

    def test_algorithms(self):
        result = self.parser.parse('COMPRESSION ALGORITHMS')
        self.assertEqual(result['type'], 'COMPRESSION_ALGORITHMS')

    def test_benchmark(self):
        result = self.parser.parse('COMPRESSION BENCHMARK DATA_SIZE 5000')
        self.assertEqual(result['data_size'], 5000)

    def test_test(self):
        result = self.parser.parse('COMPRESSION TEST users SAMPLE_SIZE 20')
        self.assertEqual(result['sample_size'], 20)

    def test_cache_stats(self):
        result = self.parser.parse('COMPRESSION CACHE STATS users')
        self.assertEqual(result['type'], 'COMPRESSION_CACHE_STATS')

    def test_unrelated_returns_none(self):
        self.assertIsNone(self.parser.parse('SELECT 1'))

    def test_singleton(self):
        self.assertIs(get_compression_parser(), get_compression_parser())


if __name__ == '__main__':
    unittest.main()
'''

files['test_geospatial_commands.py'] = '''#!/usr/bin/env python3
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
'''

files['test_geospatial_parser.py'] = '''#!/usr/bin/env python3
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
'''

files['test_mv_commands.py'] = '''#!/usr/bin/env python3
"""Unit tests for materialized view command handlers."""

import unittest
from unittest.mock import MagicMock, patch
from mv_commands import (
    CreateMaterializedViewCommand,
    DropMaterializedViewCommand,
    RefreshMaterializedViewCommand,
    RefreshAllCommand,
    ListMaterializedViewsCommand,
    QueryMaterializedViewCommand,
    SetRefreshScheduleCommand,
    MVStatsCommand,
)


class TestMVCommands(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.auth = MagicMock()

    @patch('mv_commands.get_materialized_view_manager')
    def test_create_view(self, mock_mgr):
        mock_mgr.return_value.create_view.return_value = MagicMock()
        cmd = CreateMaterializedViewCommand(self.db, self.auth)
        result = cmd.execute('mv1', 'SELECT * FROM users')
        self.assertEqual(result['status'], 'success')

    @patch('mv_commands.get_materialized_view_manager')
    def test_create_view_error(self, mock_mgr):
        mock_mgr.return_value.create_view.side_effect = ValueError('bad query')
        cmd = CreateMaterializedViewCommand(self.db, self.auth)
        result = cmd.execute('mv1', 'bad')
        self.assertEqual(result['status'], 'error')

    @patch('mv_commands.get_materialized_view_manager')
    def test_drop_view(self, mock_mgr):
        mock_mgr.return_value.drop_view.return_value = True
        cmd = DropMaterializedViewCommand(self.db, self.auth)
        result = cmd.execute('mv1')
        self.assertEqual(result['status'], 'success')

    @patch('mv_commands.get_materialized_view_manager')
    def test_drop_view_missing(self, mock_mgr):
        mock_mgr.return_value.drop_view.return_value = False
        cmd = DropMaterializedViewCommand(self.db, self.auth)
        result = cmd.execute('mv1')
        self.assertEqual(result['status'], 'error')

    @patch('mv_commands.get_materialized_view_manager')
    def test_refresh_view(self, mock_mgr):
        mock_mgr.return_value.refresh_view.return_value = {'rows': 1}
        cmd = RefreshMaterializedViewCommand(self.db, self.auth)
        result = cmd.execute('mv1')
        self.assertEqual(result['status'], 'success')

    @patch('mv_commands.get_materialized_view_manager')
    def test_refresh_all(self, mock_mgr):
        mock_mgr.return_value.list_views.return_value = ['mv1']
        mock_mgr.return_value.refresh_view.return_value = {}
        cmd = RefreshAllCommand(self.db, self.auth)
        result = cmd.execute()
        self.assertEqual(result['status'], 'success')

    @patch('mv_commands.get_materialized_view_manager')
    def test_list_views(self, mock_mgr):
        view = MagicMock()
        view.get_stats.return_value = {'name': 'mv1'}
        mock_mgr.return_value.list_views.return_value = ['mv1']
        mock_mgr.return_value.get_view.return_value = view
        cmd = ListMaterializedViewsCommand(self.db, self.auth)
        result = cmd.execute()
        self.assertEqual(result['count'], 1)

    @patch('mv_commands.get_materialized_view_manager')
    def test_query_view(self, mock_mgr):
        mock_mgr.return_value.query_view.return_value = ([], None)
        cmd = QueryMaterializedViewCommand(self.db, self.auth)
        result = cmd.execute('mv1')
        self.assertEqual(result['status'], 'success')

    @patch('mv_commands.get_materialized_view_manager')
    def test_set_schedule(self, mock_mgr):
        view = MagicMock()
        mock_mgr.return_value.get_view.return_value = view
        cmd = SetRefreshScheduleCommand(self.db, self.auth)
        result = cmd.execute('mv1', 'every_n_minutes', 5)
        self.assertEqual(result['status'], 'success')

    @patch('mv_commands.get_materialized_view_manager')
    def test_stats(self, mock_mgr):
        mock_mgr.return_value.get_stats.return_value = {'views': 1}
        cmd = MVStatsCommand(self.db, self.auth)
        result = cmd.execute()
        self.assertEqual(result['status'], 'success')


if __name__ == '__main__':
    unittest.main()
'''

files['test_mv_parser.py'] = '''#!/usr/bin/env python3
"""Unit tests for materialized view parser."""

import unittest
from mv_parser import MVParser, get_mv_parser


class TestMVParser(unittest.TestCase):
    def setUp(self):
        self.parser = MVParser()

    def test_create_view(self):
        result = self.parser.parse('CREATE MATERIALIZED VIEW mv1 AS SELECT * FROM users STRATEGY incremental SCHEDULE every_n_minutes INTERVAL 5')
        self.assertEqual(result['type'], 'CREATE_MATERIALIZED_VIEW')
        self.assertEqual(result['name'], 'mv1')
        self.assertEqual(result['refresh_strategy'], 'incremental')

    def test_drop_view(self):
        result = self.parser.parse('DROP MATERIALIZED VIEW mv1')
        self.assertEqual(result['type'], 'DROP_MATERIALIZED_VIEW')

    def test_refresh_view(self):
        result = self.parser.parse('REFRESH MATERIALIZED VIEW mv1 STRATEGY full')
        self.assertEqual(result['type'], 'REFRESH_MATERIALIZED_VIEW')

    def test_refresh_all(self):
        result = self.parser.parse('REFRESH ALL MATERIALIZED VIEWS')
        self.assertEqual(result['type'], 'REFRESH_ALL')

    def test_list_views(self):
        result = self.parser.parse('LIST MATERIALIZED VIEWS')
        self.assertEqual(result['type'], 'LIST_MATERIALIZED_VIEWS')

    def test_query_view(self):
        result = self.parser.parse('SELECT * FROM MV mv1')
        self.assertEqual(result['type'], 'QUERY_MATERIALIZED_VIEW')

    def test_set_schedule(self):
        result = self.parser.parse('SET REFRESH SCHEDULE mv1 SCHEDULE on_commit INTERVAL 10')
        self.assertEqual(result['type'], 'SET_REFRESH_SCHEDULE')

    def test_stats(self):
        result = self.parser.parse('MATERIALIZED VIEW STATS mv1')
        self.assertEqual(result['type'], 'MV_STATS')

    def test_unrelated(self):
        self.assertIsNone(self.parser.parse('SELECT 1'))

    def test_singleton(self):
        self.assertIs(get_mv_parser(), get_mv_parser())


if __name__ == '__main__':
    unittest.main()
'''

files['test_multitenant_commands.py'] = '''#!/usr/bin/env python3
"""Unit tests for multitenant command handlers."""

import unittest
from unittest.mock import MagicMock, patch
from multitenant_commands import (
    CreateTenantCommand,
    DropTenantCommand,
    UseTenantCommand,
    ListTenantsCommand,
    TenantStatsCommand,
    SetTenantQuotaCommand,
    AddRowPolicyCommand,
    RemoveRowPolicyCommand,
    CheckQuotaCommand,
    TenantBackupCommand,
    TenantRestoreCommand,
)


class TestMultitenantCommands(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.auth = MagicMock()

    @patch('multitenant_commands.get_tenant_manager')
    def test_create_tenant(self, mock_mgr):
        tenant = MagicMock()
        tenant.quota.to_dict.return_value = {}
        mock_mgr.return_value.create_tenant.return_value = tenant
        cmd = CreateTenantCommand(self.db, self.auth)
        result = cmd.execute('t1', 'Tenant One', storage_gb=5)
        self.assertEqual(result['status'], 'success')

    @patch('multitenant_commands.get_tenant_manager')
    def test_create_tenant_error(self, mock_mgr):
        from multitenant import TenantError
        mock_mgr.return_value.create_tenant.side_effect = TenantError('exists')
        cmd = CreateTenantCommand(self.db, self.auth)
        result = cmd.execute('t1', 'Tenant One')
        self.assertEqual(result['status'], 'error')

    @patch('multitenant_commands.get_tenant_manager')
    def test_drop_tenant(self, mock_mgr):
        mock_mgr.return_value.drop_tenant.return_value = True
        cmd = DropTenantCommand(self.db, self.auth)
        result = cmd.execute('t1')
        self.assertEqual(result['status'], 'success')

    @patch('multitenant_commands.get_tenant_manager')
    def test_use_tenant(self, mock_mgr):
        tenant = MagicMock()
        tenant.is_active = True
        tenant.to_dict.return_value = {}
        mock_mgr.return_value.get_tenant.return_value = tenant
        cmd = UseTenantCommand(self.db, self.auth)
        result = cmd.execute('t1')
        self.assertEqual(result['status'], 'success')

    @patch('multitenant_commands.get_tenant_manager')
    def test_use_tenant_inactive(self, mock_mgr):
        tenant = MagicMock()
        tenant.is_active = False
        mock_mgr.return_value.get_tenant.return_value = tenant
        cmd = UseTenantCommand(self.db, self.auth)
        result = cmd.execute('t1')
        self.assertEqual(result['status'], 'error')

    @patch('multitenant_commands.get_tenant_manager')
    def test_list_tenants(self, mock_mgr):
        tenant = MagicMock()
        tenant.to_dict.return_value = {}
        mock_mgr.return_value.list_tenants.return_value = [tenant]
        cmd = ListTenantsCommand(self.db, self.auth)
        result = cmd.execute()
        self.assertEqual(result['count'], 1)

    @patch('multitenant_commands.get_tenant_manager')
    def test_tenant_stats(self, mock_mgr):
        tenant = MagicMock()
        tenant.get_stats.return_value = {}
        mock_mgr.return_value.get_tenant.return_value = tenant
        cmd = TenantStatsCommand(self.db, self.auth)
        result = cmd.execute('t1')
        self.assertEqual(result['status'], 'success')

    @patch('multitenant_commands.get_tenant_manager')
    def test_set_quota(self, mock_mgr):
        tenant = MagicMock()
        tenant.quota.to_dict.return_value = {}
        mock_mgr.return_value.get_tenant.return_value = tenant
        cmd = SetTenantQuotaCommand(self.db, self.auth)
        result = cmd.execute('t1', storage_gb=20)
        self.assertEqual(result['status'], 'success')

    @patch('multitenant_commands.get_tenant_manager')
    def test_add_row_policy(self, mock_mgr):
        tenant = MagicMock()
        mock_mgr.return_value.get_tenant.return_value = tenant
        cmd = AddRowPolicyCommand(self.db, self.auth)
        result = cmd.execute('t1', 'p1', 'users', 'tenant_id = current_tenant')
        self.assertEqual(result['status'], 'success')

    @patch('multitenant_commands.get_tenant_manager')
    def test_remove_row_policy(self, mock_mgr):
        tenant = MagicMock()
        tenant.remove_row_policy.return_value = True
        mock_mgr.return_value.get_tenant.return_value = tenant
        cmd = RemoveRowPolicyCommand(self.db, self.auth)
        result = cmd.execute('t1', 'p1')
        self.assertEqual(result['status'], 'success')

    @patch('multitenant_commands.get_tenant_manager')
    def test_check_quota(self, mock_mgr):
        tenant = MagicMock()
        tenant.quota.storage_bytes = 100
        tenant.usage.storage_bytes = 50
        tenant.usage.active_connections = 2
        tenant.quota.max_connections = 10
        mock_mgr.return_value.get_tenant.return_value = tenant
        cmd = CheckQuotaCommand(self.db, self.auth)
        result = cmd.execute('t1')
        self.assertEqual(result['status'], 'success')

    @patch('multitenant_commands.get_tenant_manager')
    def test_tenant_backup(self, mock_mgr):
        tenant = MagicMock()
        mock_mgr.return_value.get_tenant.return_value = tenant
        cmd = TenantBackupCommand(self.db, self.auth)
        result = cmd.execute('t1', '/tmp/backup')
        self.assertEqual(result['status'], 'success')

    def test_tenant_restore(self):
        cmd = TenantRestoreCommand(self.db, self.auth)
        result = cmd.execute('t1', '/tmp/backup')
        self.assertEqual(result['status'], 'success')


if __name__ == '__main__':
    unittest.main()
'''

files['test_multitenant_parser.py'] = '''#!/usr/bin/env python3
"""Unit tests for multitenant parser."""

import unittest
from multitenant_parser import MultitenantParser, get_multitenant_parser


class TestMultitenantParser(unittest.TestCase):
    def setUp(self):
        self.parser = MultitenantParser()

    def test_create_tenant(self):
        result = self.parser.parse('CREATE TENANT t1 NAME TenantOne STORAGE 5 QPM 500 CONNECTIONS 50 TABLES 10')
        self.assertEqual(result['type'], 'CREATE_TENANT')
        self.assertEqual(result['tenant_id'], 't1')

    def test_drop_tenant(self):
        result = self.parser.parse('DROP TENANT t1 FORCE')
        self.assertTrue(result['force'])

    def test_use_tenant(self):
        result = self.parser.parse('USE TENANT t1')
        self.assertEqual(result['type'], 'USE_TENANT')

    def test_list_tenants(self):
        result = self.parser.parse('LIST TENANTS')
        self.assertEqual(result['type'], 'LIST_TENANTS')

    def test_tenant_stats(self):
        result = self.parser.parse('TENANT STATS t1')
        self.assertEqual(result['type'], 'TENANT_STATS')

    def test_set_quota(self):
        result = self.parser.parse('SET TENANT QUOTA t1 STORAGE 20 QPM 2000')
        self.assertEqual(result['type'], 'SET_QUOTA')

    def test_add_row_policy(self):
        result = self.parser.parse('ADD ROW POLICY t1 p1 ON users CONDITION tenant_id = current_tenant')
        self.assertEqual(result['type'], 'ADD_ROW_POLICY')

    def test_remove_row_policy(self):
        result = self.parser.parse('REMOVE ROW POLICY t1 p1')
        self.assertEqual(result['type'], 'REMOVE_ROW_POLICY')

    def test_check_quota(self):
        result = self.parser.parse('CHECK QUOTA t1')
        self.assertEqual(result['type'], 'CHECK_QUOTA')

    def test_tenant_backup(self):
        result = self.parser.parse('TENANT BACKUP t1 TO /tmp/backup')
        self.assertEqual(result['type'], 'TENANT_BACKUP')

    def test_tenant_restore(self):
        result = self.parser.parse('TENANT RESTORE t1 FROM /tmp/backup')
        self.assertEqual(result['type'], 'TENANT_RESTORE')

    def test_unrelated(self):
        self.assertIsNone(self.parser.parse('SELECT 1'))

    def test_singleton(self):
        self.assertIs(get_multitenant_parser(), get_multitenant_parser())


if __name__ == '__main__':
    unittest.main()
'''

files['test_pool_commands.py'] = '''#!/usr/bin/env python3
"""Unit tests for pool command handlers."""

import unittest
from unittest.mock import MagicMock, patch
from pool_commands import (
    PoolCreateCommand,
    PoolStatusCommand,
    PoolListCommand,
    PoolShutdownCommand,
    PoolAcquireCommand,
    PoolHealthCommand,
)


class TestPoolCommands(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.auth = MagicMock()

    @patch('pool_commands.create_pool')
    def test_create(self, mock_create):
        mock_create.return_value = MagicMock()
        cmd = PoolCreateCommand(self.db, self.auth)
        result = cmd.execute('pool1', min_connections=2, max_connections=5)
        self.assertEqual(result['status'], 'success')

    @patch('pool_commands.get_pool')
    @patch('pool_commands.get_all_stats')
    def test_status_all(self, mock_stats, mock_get):
        mock_stats.return_value = {'pool1': {}}
        cmd = PoolStatusCommand(self.db, self.auth)
        result = cmd.execute()
        self.assertEqual(result['status'], 'success')

    @patch('pool_commands.get_pool')
    def test_status_single(self, mock_get):
        mock_get.return_value = MagicMock()
        mock_get.return_value.get_stats.return_value = {}
        cmd = PoolStatusCommand(self.db, self.auth)
        result = cmd.execute('pool1')
        self.assertEqual(result['status'], 'success')

    @patch('pool_commands.list_pools')
    def test_list(self, mock_list):
        mock_list.return_value = ['pool1']
        cmd = PoolListCommand(self.db, self.auth)
        result = cmd.execute()
        self.assertEqual(result['count'], 1)

    @patch('pool_commands.list_pools')
    @patch('pool_commands.shutdown_pool')
    def test_shutdown(self, mock_shutdown, mock_list):
        mock_list.return_value = ['pool1']
        cmd = PoolShutdownCommand(self.db, self.auth)
        result = cmd.execute('pool1', wait=True)
        self.assertEqual(result['status'], 'success')

    @patch('pool_commands.list_pools')
    def test_shutdown_missing(self, mock_list):
        mock_list.return_value = []
        cmd = PoolShutdownCommand(self.db, self.auth)
        result = cmd.execute('pool1')
        self.assertEqual(result['status'], 'error')

    @patch('pool_commands.get_pool')
    def test_acquire(self, mock_get):
        pool = MagicMock()
        pool.get_connection.return_value = 'conn1'
        mock_get.return_value = pool
        cmd = PoolAcquireCommand(self.db, self.auth)
        result = cmd.execute('pool1')
        self.assertEqual(result['status'], 'success')

    @patch('pool_commands.get_pool')
    def test_acquire_missing(self, mock_get):
        mock_get.return_value = None
        cmd = PoolAcquireCommand(self.db, self.auth)
        result = cmd.execute('pool1')
        self.assertEqual(result['status'], 'error')

    @patch('pool_commands.list_pools')
    @patch('pool_commands.get_pool')
    def test_health(self, mock_get, mock_list):
        pool = MagicMock()
        pool.get_stats.return_value = {
            'active_connections': 1,
            'max_connections': 10,
            'total_borrowed': 100,
            'total_timeout': 1,
            'health_check_failures': 0
        }
        mock_get.return_value = pool
        mock_list.return_value = ['pool1']
        cmd = PoolHealthCommand(self.db, self.auth)
        result = cmd.execute('pool1')
        self.assertEqual(result['status'], 'healthy')


if __name__ == '__main__':
    unittest.main()
'''

files['test_pool_parser.py'] = '''#!/usr/bin/env python3
"""Unit tests for pool parser."""

import unittest
from pool_parser import PoolCommandParser, get_pool_parser


class TestPoolParser(unittest.TestCase):
    def setUp(self):
        self.parser = PoolCommandParser()

    def test_create(self):
        result = self.parser.parse('POOL CREATE pool1 MIN 2 MAX 10 TIMEOUT 5.0 IDLE 60.0')
        self.assertEqual(result['type'], 'POOL_CREATE')
        self.assertEqual(result['min_connections'], 2)

    def test_status(self):
        result = self.parser.parse('POOL STATUS pool1')
        self.assertEqual(result['type'], 'POOL_STATUS')

    def test_list(self):
        result = self.parser.parse('POOL LIST')
        self.assertEqual(result['type'], 'POOL_LIST')

    def test_shutdown_nowait(self):
        result = self.parser.parse('POOL SHUTDOWN pool1 NOWAIT')
        self.assertFalse(result['wait'])

    def test_health(self):
        result = self.parser.parse('POOL HEALTH pool1')
        self.assertEqual(result['type'], 'POOL_HEALTH')

    def test_acquire(self):
        result = self.parser.parse('POOL ACQUIRE pool1 TIMEOUT 2.5')
        self.assertEqual(result['timeout'], 2.5)

    def test_unrelated(self):
        self.assertIsNone(self.parser.parse('SELECT 1'))

    def test_singleton(self):
        self.assertIs(get_pool_parser(), get_pool_parser())


if __name__ == '__main__':
    unittest.main()
'''

files['test_prepared_statement_commands.py'] = '''#!/usr/bin/env python3
"""Unit tests for prepared statement command handlers."""

import unittest
from unittest.mock import MagicMock, patch
from prepared_statement_commands import (
    PrepareCommand,
    ExecuteCommand,
    DeallocateCommand,
    DeallocateAllCommand,
    ListPreparedCommand,
    CacheStatsCommand,
    CacheInvalidateCommand,
)


class TestPreparedStatementCommands(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.auth = MagicMock()

    @patch('prepared_statement_commands.get_session_manager')
    def test_prepare(self, mock_get):
        manager = MagicMock()
        stmt = MagicMock()
        stmt.parameter_names = ['id']
        stmt.parameter_positions = []
        manager.prepare.return_value = 'stmt-1'
        manager.get_statement.return_value = stmt
        mock_get.return_value = manager

        cmd = PrepareCommand(self.db, self.auth)
        result = cmd.execute('s1', 'SELECT * FROM users WHERE id = :id', 'session-1')
        self.assertEqual(result['status'], 'success')

    @patch('prepared_statement_commands.get_session_manager')
    @patch('prepared_statement_commands.get_query_plan_cache')
    def test_execute_found(self, mock_cache, mock_get):
        manager = MagicMock()
        stmt = MagicMock()
        stmt.statement_id = 'stmt-1'
        stmt.sql = 'SELECT * FROM users WHERE id = :id'
        manager.list_statements.return_value = [{'id': 'stmt-1', 'sql': stmt.sql}]
        manager.get_statement.return_value = stmt
        manager.execute.return_value = ('SELECT * FROM users WHERE id = 1', [])
        mock_get.return_value = manager
        cache = MagicMock()
        cache.get.return_value = None
        mock_cache.return_value = cache

        cmd = ExecuteCommand(self.db, self.auth)
        result = cmd.execute('s1', {'id': 1}, session_id='session-1')
        self.assertEqual(result['status'], 'success')

    @patch('prepared_statement_commands.get_session_manager')
    def test_execute_not_found(self, mock_get):
        manager = MagicMock()
        manager.list_statements.return_value = []
        mock_get.return_value = manager
        cmd = ExecuteCommand(self.db, self.auth)
        result = cmd.execute('missing', session_id='session-1')
        self.assertEqual(result['status'], 'error')

    @patch('prepared_statement_commands.get_session_manager')
    def test_deallocate(self, mock_get):
        manager = MagicMock()
        manager.list_statements.return_value = [{'id': 's1', 'sql': 'SELECT 1'}]
        manager.deallocate.return_value = True
        mock_get.return_value = manager
        cmd = DeallocateCommand(self.db, self.auth)
        result = cmd.execute('s1', 'session-1')
        self.assertEqual(result['status'], 'success')

    @patch('prepared_statement_commands.get_session_manager')
    def test_deallocate_all(self, mock_get):
        manager = MagicMock()
        manager.list_statements.return_value = [{'id': 's1'}]
        mock_get.return_value = manager
        cmd = DeallocateAllCommand(self.db, self.auth)
        result = cmd.execute('session-1')
        self.assertEqual(result['status'], 'success')

    @patch('prepared_statement_commands.get_session_manager')
    def test_list(self, mock_get):
        manager = MagicMock()
        manager.list_statements.return_value = []
        mock_get.return_value = manager
        cmd = ListPreparedCommand(self.db, self.auth)
        result = cmd.execute('session-1')
        self.assertEqual(result['status'], 'success')

    @patch('prepared_statement_commands.get_query_plan_cache')
    def test_cache_stats(self, mock_cache):
        mock_cache.return_value.get_stats.return_value = {}
        cmd = CacheStatsCommand(self.db, self.auth)
        result = cmd.execute()
        self.assertEqual(result['status'], 'success')

    @patch('prepared_statement_commands.get_query_plan_cache')
    def test_cache_invalidate_table(self, mock_cache):
        cmd = CacheInvalidateCommand(self.db, self.auth)
        result = cmd.execute('users')
        self.assertEqual(result['status'], 'success')

    @patch('prepared_statement_commands.get_query_plan_cache')
    def test_cache_invalidate_all(self, mock_cache):
        cmd = CacheInvalidateCommand(self.db, self.auth)
        result = cmd.execute()
        self.assertEqual(result['status'], 'success')


if __name__ == '__main__':
    unittest.main()
'''

files['test_prepared_statement_parser.py'] = '''#!/usr/bin/env python3
"""Unit tests for prepared statement parser."""

import unittest
from prepared_statement_parser import PreparedStatementParser, get_prepared_parser


class TestPreparedStatementParser(unittest.TestCase):
    def setUp(self):
        self.parser = PreparedStatementParser()

    def test_prepare(self):
        result = self.parser.parse("PREPARE s1 AS 'SELECT * FROM users WHERE id = :id'")
        self.assertEqual(result['type'], 'PREPARE')
        self.assertEqual(result['statement_name'], 's1')

    def test_execute_named(self):
        result = self.parser.parse('EXECUTE s1(id => 123)')
        self.assertEqual(result['type'], 'EXECUTE')
        self.assertEqual(result['parameters']['id'], 123)

    def test_execute_using(self):
        result = self.parser.parse('EXECUTE s1 USING 123, "abc"')
        self.assertEqual(result['parameter_style'], 'positional')
        self.assertEqual(result['parameters'], [123, 'abc'])

    def test_execute_simple(self):
        result = self.parser.parse('EXECUTE s1')
        self.assertEqual(result['parameter_style'], 'none')

    def test_deallocate(self):
        result = self.parser.parse('DEALLOCATE s1')
        self.assertEqual(result['type'], 'DEALLOCATE')

    def test_deallocate_all(self):
        result = self.parser.parse('DEALLOCATE ALL')
        self.assertEqual(result['type'], 'DEALLOCATE_ALL')

    def test_show_prepared(self):
        result = self.parser.parse('SHOW PREPARED STATEMENTS')
        self.assertEqual(result['type'], 'SHOW_PREPARED')

    def test_cache_stats(self):
        result = self.parser.parse('SHOW CACHE STATS')
        self.assertEqual(result['type'], 'SHOW_CACHE_STATS')

    def test_cache_invalidate(self):
        result = self.parser.parse('CACHE INVALIDATE TABLE users')
        self.assertEqual(result['type'], 'CACHE_INVALIDATE')

    def test_unrelated(self):
        self.assertIsNone(self.parser.parse('SELECT 1'))

    def test_singleton(self):
        self.assertIs(get_prepared_parser(), get_prepared_parser())


if __name__ == '__main__':
    unittest.main()
'''

files['test_security_commands.py'] = '''#!/usr/bin/env python3
"""Unit tests for security command handlers."""

import unittest
from unittest.mock import MagicMock, patch
from security_commands import (
    AuditLogCommand,
    ExportAuditLogCommand,
    GrantRoleCommand,
    RevokeRoleCommand,
    CheckPermissionCommand,
    EncryptColumnCommand,
    DecryptColumnCommand,
    ValidatePasswordCommand,
    SQLInjectionCheckCommand,
    ComplianceReportCommand,
    SecurityStatsCommand,
    HighRiskEventsCommand,
)


class TestSecurityCommands(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.auth = MagicMock()

    @patch('security_commands.get_security_manager')
    def test_audit_log(self, mock_get):
        manager = MagicMock()
        event = MagicMock()
        event.to_dict.return_value = {}
        manager.audit_logger.query.return_value = [event]
        mock_get.return_value = manager
        cmd = AuditLogCommand(self.db, self.auth)
        result = cmd.execute()
        self.assertEqual(result['status'], 'success')

    @patch('security_commands.get_security_manager')
    def test_audit_log_invalid_type(self, mock_get):
        manager = MagicMock()
        mock_get.return_value = manager
        cmd = AuditLogCommand(self.db, self.auth)
        result = cmd.execute(event_type='invalid')
        self.assertEqual(result['status'], 'error')

    @patch('security_commands.get_security_manager')
    def test_export_audit(self, mock_get):
        manager = MagicMock()
        manager.audit_logger.export.return_value = 'data'
        mock_get.return_value = manager
        cmd = ExportAuditLogCommand(self.db, self.auth)
        result = cmd.execute('json')
        self.assertEqual(result['status'], 'success')

    def test_export_audit_bad_format(self):
        cmd = ExportAuditLogCommand(self.db, self.auth)
        result = cmd.execute('xml')
        self.assertEqual(result['status'], 'error')

    @patch('security_commands.get_security_manager')
    def test_grant_role(self, mock_get):
        manager = MagicMock()
        mock_get.return_value = manager
        cmd = GrantRoleCommand(self.db, self.auth)
        result = cmd.execute('alice', 'admin')
        self.assertEqual(result['status'], 'success')

    @patch('security_commands.get_security_manager')
    def test_grant_role_error(self, mock_get):
        manager = MagicMock()
        manager.rbac.grant_role.side_effect = ValueError('bad role')
        mock_get.return_value = manager
        cmd = GrantRoleCommand(self.db, self.auth)
        result = cmd.execute('alice', 'bad')
        self.assertEqual(result['status'], 'error')

    @patch('security_commands.get_security_manager')
    def test_revoke_role(self, mock_get):
        manager = MagicMock()
        mock_get.return_value = manager
        cmd = RevokeRoleCommand(self.db, self.auth)
        result = cmd.execute('alice', 'admin')
        self.assertEqual(result['status'], 'success')

    @patch('security_commands.get_security_manager')
    def test_check_permission(self, mock_get):
        manager = MagicMock()
        manager.check_permission.return_value = True
        manager.rbac.get_user_permissions.return_value = {'SELECT'}
        mock_get.return_value = manager
        cmd = CheckPermissionCommand(self.db, self.auth)
        result = cmd.execute('alice', 'SELECT')
        self.assertTrue(result['has_permission'])

    @patch('security_commands.get_security_manager')
    def test_encrypt_column(self, mock_get):
        manager = MagicMock()
        manager.encrypt_sensitive_data.return_value = 'cipher'
        mock_get.return_value = manager
        cmd = EncryptColumnCommand(self.db, self.auth)
        result = cmd.execute('users', 'ssn', '123-45-6789')
        self.assertEqual(result['encrypted'], 'cipher')

    @patch('security_commands.get_security_manager')
    def test_decrypt_column(self, mock_get):
        manager = MagicMock()
        manager.decrypt_sensitive_data.return_value = 'plain'
        mock_get.return_value = manager
        cmd = DecryptColumnCommand(self.db, self.auth)
        result = cmd.execute('users', 'ssn', 'cipher')
        self.assertEqual(result['decrypted'], 'plain')

    @patch('security_commands.get_security_manager')
    def test_decrypt_error(self, mock_get):
        manager = MagicMock()
        manager.decrypt_sensitive_data.side_effect = Exception('fail')
        mock_get.return_value = manager
        cmd = DecryptColumnCommand(self.db, self.auth)
        result = cmd.execute('users', 'ssn', 'cipher')
        self.assertEqual(result['status'], 'error')

    @patch('security_commands.get_security_manager')
    def test_validate_password(self, mock_get):
        manager = MagicMock()
        manager.policy.validate_password.return_value = (True, [])
        mock_get.return_value = manager
        cmd = ValidatePasswordCommand(self.db, self.auth)
        result = cmd.execute('StrongP@ss1')
        self.assertTrue(result['is_valid'])

    @patch('security_commands.get_security_manager')
    def test_sql_injection_check(self, mock_get):
        manager = MagicMock()
        manager.injection_detector.analyze.return_value = (True, 0.9, [])
        mock_get.return_value = manager
        cmd = SQLInjectionCheckCommand(self.db, self.auth)
        result = cmd.execute('SELECT 1')
        self.assertTrue(result['is_safe'])

    @patch('security_commands.get_security_manager')
    def test_compliance_report(self, mock_get):
        manager = MagicMock()
        manager.compliance.generate_report.return_value = {}
        mock_get.return_value = manager
        cmd = ComplianceReportCommand(self.db, self.auth)
        result = cmd.execute('SOC2', days=7)
        self.assertEqual(result['status'], 'success')

    @patch('security_commands.get_security_manager')
    def test_security_stats(self, mock_get):
        manager = MagicMock()
        manager.get_security_report.return_value = {}
        mock_get.return_value = manager
        cmd = SecurityStatsCommand(self.db, self.auth)
        result = cmd.execute()
        self.assertEqual(result['status'], 'success')

    @patch('security_commands.get_security_manager')
    def test_high_risk_events(self, mock_get):
        manager = MagicMock()
        event = MagicMock()
        event.to_dict.return_value = {}
        manager.audit_logger.get_high_risk_events.return_value = [event]
        mock_get.return_value = manager
        cmd = HighRiskEventsCommand(self.db, self.auth)
        result = cmd.execute(threshold=75)
        self.assertEqual(result['status'], 'success')


if __name__ == '__main__':
    unittest.main()
'''

files['test_security_parser.py'] = '''#!/usr/bin/env python3
"""Unit tests for security parser."""

import unittest
from security_parser import SecurityParser, get_security_parser


class TestSecurityParser(unittest.TestCase):
    def setUp(self):
        self.parser = SecurityParser()

    def test_audit_log(self):
        result = self.parser.parse('AUDIT LOG USER alice TYPE login RISK 50')
        self.assertEqual(result['type'], 'AUDIT_LOG')
        self.assertEqual(result['min_risk'], 50)

    def test_export_audit(self):
        result = self.parser.parse('EXPORT AUDIT LOG FORMAT csv')
        self.assertEqual(result['format'], 'csv')

    def test_grant_role(self):
        result = self.parser.parse('GRANT ROLE alice admin')
        self.assertEqual(result['type'], 'GRANT_ROLE')

    def test_revoke_role(self):
        result = self.parser.parse('REVOKE ROLE alice admin')
        self.assertEqual(result['type'], 'REVOKE_ROLE')

    def test_check_permission(self):
        result = self.parser.parse('CHECK PERMISSION alice SELECT')
        self.assertEqual(result['type'], 'CHECK_PERMISSION')

    def test_encrypt_column(self):
        result = self.parser.parse('ENCRYPT COLUMN users ssn 123-45-6789')
        self.assertEqual(result['type'], 'ENCRYPT_COLUMN')

    def test_decrypt_column(self):
        result = self.parser.parse('DECRYPT COLUMN users ssn cipher')
        self.assertEqual(result['type'], 'DECRYPT_COLUMN')

    def test_validate_password(self):
        result = self.parser.parse('VALIDATE PASSWORD Secret123!')
        self.assertEqual(result['type'], 'VALIDATE_PASSWORD')

    def test_sql_injection(self):
        result = self.parser.parse('CHECK SQL INJECTION SELECT * FROM users')
        self.assertEqual(result['type'], 'CHECK_SQL_INJECTION')

    def test_compliance_report(self):
        result = self.parser.parse('COMPLIANCE REPORT SOC2 DAYS 30')
        self.assertEqual(result['days'], 30)

    def test_security_stats(self):
        result = self.parser.parse('SECURITY STATS')
        self.assertEqual(result['type'], 'SECURITY_STATS')

    def test_high_risk_events(self):
        result = self.parser.parse('HIGH RISK EVENTS THRESHOLD 75')
        self.assertEqual(result['threshold'], 75)

    def test_unrelated(self):
        self.assertIsNone(self.parser.parse('SELECT 1'))

    def test_singleton(self):
        self.assertIs(get_security_parser(), get_security_parser())


if __name__ == '__main__':
    unittest.main()
'''

files['test_sharding_commands.py'] = '''#!/usr/bin/env python3
"""Unit tests for sharding command handlers."""

import unittest
from unittest.mock import MagicMock
from sharding_commands import (
    CreateShardCommand,
    DropShardCommand,
    ShowShardsCommand,
    RebalanceShardsCommand,
    AddReadReplicaCommand,
    RouteKeyCommand,
)


class TestShardingCommands(unittest.TestCase):
    def _db_with_coordinator(self):
        db = MagicMock()
        coordinator = MagicMock()
        db._sharding_coordinator = coordinator
        return db, coordinator

    def test_create_shard(self):
        db, coord = self._db_with_coordinator()
        coord.create_shard.return_value = 'OK: created'
        cmd = CreateShardCommand(db)
        result = cmd.execute({'shard_id': 's1', 'region': 'us', 'host': '127.0.0.1', 'port': '8001'}, {'is_admin': True})
        self.assertIn('OK', result)

    def test_create_shard_not_admin(self):
        db, _ = self._db_with_coordinator()
        cmd = CreateShardCommand(db)
        result = cmd.execute({}, {'is_admin': False})
        self.assertIn('Admin only', result)

    def test_create_shard_no_coordinator(self):
        db = MagicMock()
        cmd = CreateShardCommand(db)
        result = cmd.execute({'shard_id': 's1'}, {'is_admin': True})
        self.assertIn('not available', result)

    def test_create_shard_missing_params(self):
        db, coord = self._db_with_coordinator()
        cmd = CreateShardCommand(db)
        result = cmd.execute({'shard_id': 's1'}, {'is_admin': True})
        self.assertIn('required', result)

    def test_drop_shard(self):
        db, coord = self._db_with_coordinator()
        coord.drop_shard.return_value = 'OK: dropped'
        cmd = DropShardCommand(db)
        result = cmd.execute({'shard_id': 's1'}, {'is_admin': True})
        self.assertIn('OK', result)

    def test_show_shards(self):
        db, coord = self._db_with_coordinator()
        coord.list_shards.return_value = [{'shard_id': 's1', 'region': 'us', 'host': '127.0.0.1', 'port': 8001, 'role': 'primary', 'status': 'active'}]
        cmd = ShowShardsCommand(db)
        result = cmd.execute({}, {})
        self.assertIn('s1', result)

    def test_rebalance(self):
        db, coord = self._db_with_coordinator()
        coord.rebalance.return_value = 'OK: rebalanced'
        coord.manager.get_rebalance_plan.return_value = [{'shard_id': 's1', 'region': 'us', 'weight': 1, 'key_range_count': 2, 'estimated_load_pct': 50.0}]
        cmd = RebalanceShardsCommand(db)
        result = cmd.execute({}, {'is_admin': True})
        self.assertIn('OK', result)

    def test_add_read_replica(self):
        db, coord = self._db_with_coordinator()
        coord.add_read_replica.return_value = 'OK: replica added'
        cmd = AddReadReplicaCommand(db)
        result = cmd.execute({'shard_id': 's1', 'replica_id': 'r1', 'region': 'us', 'host': '127.0.0.1', 'port': '8002'}, {'is_admin': True})
        self.assertIn('OK', result)

    def test_route_key(self):
        db, coord = self._db_with_coordinator()
        coord.route_key.return_value = {'shard_id': 's1', 'region': 'us'}
        cmd = RouteKeyCommand(db)
        result = cmd.execute({'key': 'user-1'}, {})
        self.assertIn('s1', result)


if __name__ == '__main__':
    unittest.main()
'''

files['test_sharding_parser.py'] = '''#!/usr/bin/env python3
"""Unit tests for sharding parser."""

import unittest
from sharding_parser import ShardingParser, get_sharding_parser


class TestShardingParser(unittest.TestCase):
    def setUp(self):
        self.parser = ShardingParser()

    def test_create_shard(self):
        result = self.parser.parse('CREATE SHARD s1 REGION us HOST 127.0.0.1 PORT 8001 ROLE primary WEIGHT 2')
        self.assertEqual(result['type'], 'CREATE_SHARD')
        self.assertEqual(result['weight'], '2')

    def test_drop_shard(self):
        result = self.parser.parse('DROP SHARD s1')
        self.assertEqual(result['type'], 'DROP_SHARD')

    def test_show_shards(self):
        result = self.parser.parse('SHOW SHARDS')
        self.assertEqual(result['type'], 'SHOW_SHARDS')

    def test_rebalance(self):
        result = self.parser.parse('REBALANCE SHARDS')
        self.assertEqual(result['type'], 'REBALANCE_SHARDS')

    def test_add_replica(self):
        result = self.parser.parse('ADD READ REPLICA r1 FOR SHARD s1 REGION eu HOST 127.0.0.1 PORT 8002')
        self.assertEqual(result['type'], 'ADD_READ_REPLICA')

    def test_route_key(self):
        result = self.parser.parse('ROUTE KEY user-1 OPERATION write')
        self.assertEqual(result['operation'], 'write')

    def test_unrelated(self):
        self.assertIsNone(self.parser.parse('SELECT 1'))

    def test_singleton(self):
        self.assertIs(get_sharding_parser(), get_sharding_parser())


if __name__ == '__main__':
    unittest.main()
'''

files['test_sql_protocol_commands.py'] = '''#!/usr/bin/env python3
"""Unit tests for SQL protocol command handlers."""

import unittest
from unittest.mock import MagicMock
from sql_protocol_commands import (
    ShowProtocolStatusCommand,
    SetProtocolPortCommand,
    EnableProtocolCommand,
    DisableProtocolCommand,
)


class TestSQLProtocolCommands(unittest.TestCase):
    def _make_db(self):
        db = MagicMock()
        db._sql_protocol_status = {
            'postgres_enabled': False,
            'postgres_port': 5432,
            'mysql_enabled': False,
            'mysql_port': 3306,
            'tls_enabled': False,
        }
        return db

    def test_show_status(self):
        db = self._make_db()
        cmd = ShowProtocolStatusCommand(db)
        result = cmd.execute({}, {})
        self.assertIn('PostgreSQL', result)

    def test_set_port_postgres(self):
        db = self._make_db()
        cmd = SetProtocolPortCommand(db)
        result = cmd.execute({'protocol': 'postgres', 'port': '5433'}, {'is_admin': True})
        self.assertIn('OK', result)
        self.assertEqual(db._sql_protocol_status['postgres_port'], 5433)

    def test_set_port_not_admin(self):
        db = self._make_db()
        cmd = SetProtocolPortCommand(db)
        result = cmd.execute({'protocol': 'postgres', 'port': '5433'}, {'is_admin': False})
        self.assertIn('Admin only', result)

    def test_set_port_invalid_protocol(self):
        db = self._make_db()
        cmd = SetProtocolPortCommand(db)
        result = cmd.execute({'protocol': 'redis', 'port': '5433'}, {'is_admin': True})
        self.assertIn('ERROR', result)

    def test_set_port_invalid_port(self):
        db = self._make_db()
        cmd = SetProtocolPortCommand(db)
        result = cmd.execute({'protocol': 'postgres', 'port': 'abc'}, {'is_admin': True})
        self.assertIn('ERROR', result)

    def test_enable_protocol(self):
        db = self._make_db()
        cmd = EnableProtocolCommand(db)
        result = cmd.execute({'protocol': 'postgres'}, {'is_admin': True})
        self.assertIn('OK', result)
        self.assertTrue(db._sql_protocol_status['postgres_enabled'])

    def test_disable_protocol(self):
        db = self._make_db()
        cmd = DisableProtocolCommand(db)
        result = cmd.execute({'protocol': 'mysql'}, {'is_admin': True})
        self.assertIn('OK', result)
        self.assertFalse(db._sql_protocol_status['mysql_enabled'])


if __name__ == '__main__':
    unittest.main()
'''

files['test_sql_protocol_parser.py'] = '''#!/usr/bin/env python3
"""Unit tests for SQL protocol parser."""

import unittest
from sql_protocol_parser import SQLProtocolParser, get_sql_protocol_parser


class TestSQLProtocolParser(unittest.TestCase):
    def setUp(self):
        self.parser = SQLProtocolParser()

    def test_show_status(self):
        result = self.parser.parse('SHOW PROTOCOL STATUS')
        self.assertEqual(result['type'], 'SHOW_PROTOCOL_STATUS')

    def test_set_port(self):
        result = self.parser.parse('SET PROTOCOL postgres PORT 5433')
        self.assertEqual(result['type'], 'SET_PROTOCOL_PORT')
        self.assertEqual(result['port'], '5433')

    def test_enable(self):
        result = self.parser.parse('ENABLE PROTOCOL mysql')
        self.assertEqual(result['type'], 'ENABLE_PROTOCOL')

    def test_disable(self):
        result = self.parser.parse('DISABLE PROTOCOL postgres')
        self.assertEqual(result['type'], 'DISABLE_PROTOCOL')

    def test_unrelated(self):
        self.assertIsNone(self.parser.parse('SELECT 1'))

    def test_singleton(self):
        self.assertIs(get_sql_protocol_parser(), get_sql_protocol_parser())


if __name__ == '__main__':
    unittest.main()
'''

files['test_timeseries_commands.py'] = '''#!/usr/bin/env python3
"""Unit tests for timeseries command handlers."""

import unittest
from unittest.mock import MagicMock, patch
from timeseries_commands import (
    CreateHypertableCommand,
    DropHypertableCommand,
    InsertTimeSeriesCommand,
    SelectTimeSeriesCommand,
    TimeBucketCommand,
    DownsampleCommand,
    RetentionPolicyCommand,
    HypertableStatsCommand,
    ListHypertablesCommand,
    FirstLastCommand,
)


class TestTimeseriesCommands(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.auth = MagicMock()

    @patch('timeseries_commands.get_timeseries_engine')
    def test_create_hypertable(self, mock_get):
        engine = MagicMock()
        engine.create_hypertable.return_value = MagicMock()
        mock_get.return_value = engine
        cmd = CreateHypertableCommand(self.db, self.auth)
        result = cmd.execute('metrics', chunk_interval='1h', retention='7d')
        self.assertEqual(result['status'], 'success')

    @patch('timeseries_commands.get_timeseries_engine')
    def test_create_hypertable_error(self, mock_get):
        engine = MagicMock()
        engine.create_hypertable.side_effect = Exception('fail')
        mock_get.return_value = engine
        cmd = CreateHypertableCommand(self.db, self.auth)
        result = cmd.execute('metrics')
        self.assertEqual(result['status'], 'error')

    @patch('timeseries_commands.get_timeseries_engine')
    def test_drop_hypertable(self, mock_get):
        engine = MagicMock()
        engine.drop_hypertable.return_value = True
        mock_get.return_value = engine
        cmd = DropHypertableCommand(self.db, self.auth)
        result = cmd.execute('metrics')
        self.assertEqual(result['status'], 'success')

    @patch('timeseries_commands.get_timeseries_engine')
    def test_insert(self, mock_get):
        table = MagicMock()
        table.insert.return_value = True
        engine = MagicMock()
        engine.get_hypertable.return_value = table
        mock_get.return_value = engine
        cmd = InsertTimeSeriesCommand(self.db, self.auth)
        result = cmd.execute('metrics', 1234567890.0, 42.0, {'host': 'a'})
        self.assertEqual(result['status'], 'success')

    @patch('timeseries_commands.get_timeseries_engine')
    def test_insert_no_table(self, mock_get):
        engine = MagicMock()
        engine.get_hypertable.return_value = None
        mock_get.return_value = engine
        cmd = InsertTimeSeriesCommand(self.db, self.auth)
        result = cmd.execute('metrics', 1234567890.0, 42.0)
        self.assertEqual(result['status'], 'error')

    @patch('timeseries_commands.get_timeseries_engine')
    def test_select(self, mock_get):
        table = MagicMock()
        table.query.return_value = []
        engine = MagicMock()
        engine.get_hypertable.return_value = table
        mock_get.return_value = engine
        cmd = SelectTimeSeriesCommand(self.db, self.auth)
        result = cmd.execute('metrics', start=0.0, end=1.0)
        self.assertEqual(result['status'], 'success')

    @patch('timeseries_commands.get_timeseries_engine')
    def test_time_bucket(self, mock_get):
        table = MagicMock()
        table.time_bucket.return_value = []
        engine = MagicMock()
        engine.get_hypertable.return_value = table
        mock_get.return_value = engine
        cmd = TimeBucketCommand(self.db, self.auth)
        result = cmd.execute('metrics', '1h')
        self.assertEqual(result['status'], 'success')

    @patch('timeseries_commands.get_timeseries_engine')
    def test_downsample(self, mock_get):
        table = MagicMock()
        table.downsample.return_value = []
        engine = MagicMock()
        engine.get_hypertable.return_value = table
        mock_get.return_value = engine
        cmd = DownsampleCommand(self.db, self.auth)
        result = cmd.execute('metrics', '1h', '1d')
        self.assertEqual(result['status'], 'success')

    @patch('timeseries_commands.get_timeseries_engine')
    def test_retention_apply(self, mock_get):
        table = MagicMock()
        table.apply_retention_policy.return_value = 5
        engine = MagicMock()
        engine.get_hypertable.return_value = table
        mock_get.return_value = engine
        cmd = RetentionPolicyCommand(self.db, self.auth)
        result = cmd.execute('apply', 'metrics')
        self.assertEqual(result['deleted_points'], 5)

    @patch('timeseries_commands.get_timeseries_engine')
    def test_retention_unknown_action(self, mock_get):
        table = MagicMock()
        engine = MagicMock()
        engine.get_hypertable.return_value = table
        mock_get.return_value = engine
        cmd = RetentionPolicyCommand(self.db, self.auth)
        result = cmd.execute('unknown', 'metrics')
        self.assertEqual(result['status'], 'error')

    @patch('timeseries_commands.get_timeseries_engine')
    def test_hypertable_stats(self, mock_get):
        table = MagicMock()
        table.get_stats.return_value = {}
        engine = MagicMock()
        engine.get_hypertable.return_value = table
        mock_get.return_value = engine
        cmd = HypertableStatsCommand(self.db, self.auth)
        result = cmd.execute('metrics')
        self.assertEqual(result['status'], 'success')

    @patch('timeseries_commands.get_timeseries_engine')
    def test_list_hypertables(self, mock_get):
        engine = MagicMock()
        engine.list_hypertables.return_value = ['metrics']
        mock_get.return_value = engine
        cmd = ListHypertablesCommand(self.db, self.auth)
        result = cmd.execute()
        self.assertEqual(result['count'], 1)

    @patch('timeseries_commands.get_timeseries_engine')
    def test_first(self, mock_get):
        point = MagicMock()
        point.timestamp = 1.0
        point.value = 42.0
        table = MagicMock()
        table.query.return_value = [point]
        engine = MagicMock()
        engine.get_hypertable.return_value = table
        mock_get.return_value = engine
        cmd = FirstLastCommand(self.db, self.auth)
        result = cmd.execute('metrics', 'first')
        self.assertEqual(result['value'], 42.0)


if __name__ == '__main__':
    unittest.main()
'''

files['test_timeseries_parser.py'] = '''#!/usr/bin/env python3
"""Unit tests for timeseries parser."""

import unittest
from timeseries_parser import TimeSeriesParser, get_timeseries_parser


class TestTimeseriesParser(unittest.TestCase):
    def setUp(self):
        self.parser = TimeSeriesParser()

    def test_create_hypertable(self):
        result = self.parser.parse('CREATE HYPERTABLE metrics CHUNK_INTERVAL 1h RETENTION 7d')
        self.assertEqual(result['type'], 'CREATE_HYPERTABLE')
        self.assertEqual(result['chunk_interval'], '1h')

    def test_drop_hypertable(self):
        result = self.parser.parse('DROP HYPERTABLE metrics')
        self.assertEqual(result['type'], 'DROP_HYPERTABLE')

    def test_insert(self):
        result = self.parser.parse("INSERT INTO metrics VALUES (1234567890, 42.0, {'host':'a'})")
        self.assertEqual(result['type'], 'INSERT')
        self.assertEqual(result['value'], 42.0)

    def test_insert_now(self):
        result = self.parser.parse("INSERT INTO metrics VALUES (NOW, 1.0)")
        self.assertIsNone(result['timestamp'])

    def test_select(self):
        result = self.parser.parse('SELECT * FROM metrics WHERE time > 0 AND time < 100 LIMIT 10')
        self.assertEqual(result['type'], 'SELECT')
        self.assertEqual(result['limit'], 10)

    def test_time_bucket(self):
        result = self.parser.parse("TIME_BUCKET('1h', metrics, avg)")
        self.assertEqual(result['type'], 'TIME_BUCKET')

    def test_downsample(self):
        result = self.parser.parse('DOWNSAMPLE metrics FROM 1h TO 1d WHERE time > 0 AND time < 100')
        self.assertEqual(result['type'], 'DOWNSAMPLE')

    def test_retention_apply(self):
        result = self.parser.parse('RETENTION POLICY APPLY metrics')
        self.assertEqual(result['type'], 'RETENTION_APPLY')

    def test_retention_show(self):
        result = self.parser.parse('RETENTION POLICY SHOW metrics')
        self.assertEqual(result['type'], 'RETENTION_SHOW')

    def test_first(self):
        result = self.parser.parse('FIRST metrics WHERE time > 0')
        self.assertEqual(result['type'], 'FIRST')

    def test_last(self):
        result = self.parser.parse('LAST metrics WHERE time < 100')
        self.assertEqual(result['type'], 'LAST')

    def test_hypertable_stats(self):
        result = self.parser.parse('HYPERTABLE STATS metrics')
        self.assertEqual(result['type'], 'HYPERTABLE_STATS')

    def test_list_hypertables(self):
        result = self.parser.parse('LIST HYPERTABLES')
        self.assertEqual(result['type'], 'LIST_HYPERTABLES')

    def test_unrelated(self):
        self.assertIsNone(self.parser.parse('SELECT 1'))

    def test_singleton(self):
        self.assertIs(get_timeseries_parser(), get_timeseries_parser())


if __name__ == '__main__':
    unittest.main()
'''

for name, content in files.items():
    with open(name, 'w') as f:
        f.write(content)
    print('Wrote', name)
