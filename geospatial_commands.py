"""
Command handlers for geospatial operations.

Integrates geospatial indexing with the CLI.
"""

import logging
from typing import Dict, Any, List, Optional
from geospatial import (
    RTreeIndex,
    PointGeometry,
    CircleGeometry,
    PolygonGeometry,
    BoundingBox,
    Point,
    haversine_distance,
    geohash_encode,
    geohash_neighbors
)

logger = logging.getLogger(__name__)


class SpatialIndexManager:
    """Manages spatial indexes for tables."""
    
    def __init__(self):
        self._indexes: Dict[str, RTreeIndex] = {}
    
    def create_index(self, table_name: str) -> RTreeIndex:
        """Create spatial index for table."""
        index = RTreeIndex()
        self._indexes[table_name] = index
        logger.info(f"Created spatial index for table: {table_name}")
        return index
    
    def get_index(self, table_name: str) -> Optional[RTreeIndex]:
        """Get spatial index for table."""
        return self._indexes.get(table_name)
    
    def drop_index(self, table_name: str) -> bool:
        """Drop spatial index."""
        if table_name in self._indexes:
            del self._indexes[table_name]
            logger.info(f"Dropped spatial index for table: {table_name}")
            return True
        return False
    
    def list_indexes(self) -> List[str]:
        """List all spatial indexes."""
        return list(self._indexes.keys())


# Global spatial index manager
_spatial_manager = SpatialIndexManager()


def get_spatial_manager() -> SpatialIndexManager:
    """Get global spatial index manager."""
    return _spatial_manager


class CreateSpatialIndexCommand:
    """CREATE SPATIAL INDEX - Create spatial index for table."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, table_name: str, column: str = "location") -> Dict[str, Any]:
        """
        Create spatial index for a table.
        
        Args:
            table_name: Table to index
            column: Column containing spatial data
        
        Returns:
            Success/error response
        """
        try:
            manager = get_spatial_manager()
            index = manager.create_index(table_name)
            
            return {
                'status': 'success',
                'message': f'Created spatial index on {table_name}.{column}',
                'table': table_name,
                'column': column
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': str(e)
            }


class DropSpatialIndexCommand:
    """DROP SPATIAL INDEX - Remove spatial index."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, table_name: str) -> Dict[str, Any]:
        """Drop spatial index for table."""
        manager = get_spatial_manager()
        
        if manager.drop_index(table_name):
            return {
                'status': 'success',
                'message': f'Dropped spatial index for {table_name}'
            }
        else:
            return {
                'status': 'error',
                'message': f'No spatial index found for {table_name}'
            }


class SpatialNearCommand:
    """NEAR - Find objects near a point."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(
        self,
        table_name: str,
        lat: float,
        lon: float,
        radius: float,
        unit: str = "meters"
    ) -> Dict[str, Any]:
        """
        Find objects near a point.
        
        Args:
            table_name: Table to search
            lat: Latitude
            lon: Longitude
            radius: Search radius
            unit: Unit (meters, km, miles)
        
        Returns:
            Matching objects sorted by distance
        """
        manager = get_spatial_manager()
        index = manager.get_index(table_name)
        
        if not index:
            return {
                'status': 'error',
                'message': f'No spatial index for table {table_name}'
            }
        
        # Convert to meters
        radius_m = self._to_meters(radius, unit)
        
        point = Point(lat, lon)
        results = index.near(point, radius_m)
        
        return {
            'status': 'success',
            'count': len(results),
            'results': [
                {
                    'id': obj_id,
                    'distance_meters': round(dist, 2),
                    'data': data
                }
                for obj_id, dist, data in results[:100]  # Limit results
            ]
        }
    
    def _to_meters(self, value: float, unit: str) -> float:
        """Convert distance to meters."""
        unit = unit.lower()
        if unit in ['m', 'meter', 'meters']:
            return value
        elif unit in ['km', 'kilometer', 'kilometers']:
            return value * 1000
        elif unit in ['mi', 'mile', 'miles']:
            return value * 1609.34
        elif unit in ['ft', 'foot', 'feet']:
            return value * 0.3048
        return value


class SpatialWithinCommand:
    """WITHIN - Find objects within a geometry."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(
        self,
        table_name: str,
        geometry_type: str,
        **geometry_params
    ) -> Dict[str, Any]:
        """
        Find objects within a geometry.
        
        Args:
            table_name: Table to search
            geometry_type: circle, polygon, or bbox
            **geometry_params: Geometry-specific parameters
        
        Returns:
            Matching objects
        """
        manager = get_spatial_manager()
        index = manager.get_index(table_name)
        
        if not index:
            return {
                'status': 'error',
                'message': f'No spatial index for table {table_name}'
            }
        
        # Build geometry
        geometry = self._build_geometry(geometry_type, geometry_params)
        if not geometry:
            return {
                'status': 'error',
                'message': f'Invalid geometry type: {geometry_type}'
            }
        
        results = index.within(geometry)
        
        return {
            'status': 'success',
            'count': len(results),
            'geometry_type': geometry_type,
            'results': [
                {
                    'id': obj_id,
                    'data': data
                }
                for obj_id, geom, data in results[:100]
            ]
        }
    
    def _build_geometry(self, geom_type: str, params: dict):
        """Build geometry from parameters."""
        geom_type = geom_type.lower()
        
        if geom_type == 'circle':
            return CircleGeometry(
                params['lat'],
                params['lon'],
                params['radius']
            )
        elif geom_type == 'polygon':
            return PolygonGeometry(params['points'])
        elif geom_type == 'bbox':
            return BoundingBox(
                params['min_lat'],
                params['min_lon'],
                params['max_lat'],
                params['max_lon']
            )
        return None


class SpatialIntersectsCommand:
    """INTERSECTS - Find objects intersecting a geometry."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(
        self,
        table_name: str,
        geometry_type: str,
        **geometry_params
    ) -> Dict[str, Any]:
        """Find objects intersecting a geometry."""
        manager = get_spatial_manager()
        index = manager.get_index(table_name)
        
        if not index:
            return {
                'status': 'error',
                'message': f'No spatial index for table {table_name}'
            }
        
        geometry = self._build_geometry(geometry_type, geometry_params)
        if not geometry:
            return {
                'status': 'error',
                'message': f'Invalid geometry type: {geometry_type}'
            }
        
        results = index.intersects(geometry)
        
        return {
            'status': 'success',
            'count': len(results),
            'results': [
                {
                    'id': obj_id,
                    'data': data
                }
                for obj_id, geom, data in results[:100]
            ]
        }
    
    def _build_geometry(self, geom_type: str, params: dict):
        """Build geometry from parameters."""
        geom_type = geom_type.lower()
        
        if geom_type == 'circle':
            return CircleGeometry(
                params['lat'],
                params['lon'],
                params['radius']
            )
        elif geom_type == 'polygon':
            return PolygonGeometry(params['points'])
        elif geom_type == 'bbox':
            return BoundingBox(
                params['min_lat'],
                params['min_lon'],
                params['max_lat'],
                params['max_lon']
            )
        return None


class SpatialBoundingBoxCommand:
    """BOUNDING_BOX - Search within bounding box."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(
        self,
        table_name: str,
        min_lat: float,
        min_lon: float,
        max_lat: float,
        max_lon: float
    ) -> Dict[str, Any]:
        """Search within bounding box."""
        manager = get_spatial_manager()
        index = manager.get_index(table_name)
        
        if not index:
            return {
                'status': 'error',
                'message': f'No spatial index for table {table_name}'
            }
        
        bbox = BoundingBox(min_lat, min_lon, max_lat, max_lon)
        results = index.search(bbox)
        
        return {
            'status': 'success',
            'count': len(results),
            'bounding_box': {
                'min_lat': min_lat,
                'min_lon': min_lon,
                'max_lat': max_lat,
                'max_lon': max_lon
            },
            'results': [
                {
                    'id': obj_id,
                    'data': data
                }
                for obj_id, geom, data in results[:100]
            ]
        }


class SpatialInsertCommand:
    """SPATIAL INSERT - Insert spatial data."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(
        self,
        table_name: str,
        obj_id: str,
        lat: float,
        lon: float,
        data: Any = None
    ) -> Dict[str, Any]:
        """Insert point data into spatial index."""
        manager = get_spatial_manager()
        index = manager.get_index(table_name)
        
        if not index:
            return {
                'status': 'error',
                'message': f'No spatial index for table {table_name}'
            }
        
        point = PointGeometry(lat, lon)
        index.insert(obj_id, point, data)
        
        return {
            'status': 'success',
            'message': f'Inserted {obj_id} at ({lat}, {lon})'
        }


class SpatialDeleteCommand:
    """SPATIAL DELETE - Remove spatial data."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, table_name: str, obj_id: str) -> Dict[str, Any]:
        """Delete object from spatial index."""
        manager = get_spatial_manager()
        index = manager.get_index(table_name)
        
        if not index:
            return {
                'status': 'error',
                'message': f'No spatial index for table {table_name}'
            }
        
        if index.delete(obj_id):
            return {
                'status': 'success',
                'message': f'Deleted {obj_id} from {table_name}'
            }
        else:
            return {
                'status': 'error',
                'message': f'Object {obj_id} not found'
            }


class GeohashEncodeCommand:
    """GEOHASH ENCODE - Encode coordinates to geohash."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, lat: float, lon: float, precision: int = 12) -> Dict[str, Any]:
        """Encode coordinates to geohash."""
        geohash = geohash_encode(lat, lon, precision)
        
        return {
            'status': 'success',
            'latitude': lat,
            'longitude': lon,
            'geohash': geohash,
            'precision': precision
        }


class GeohashNeighborsCommand:
    """GEOHASH NEIGHBORS - Get neighboring geohashes."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, geohash: str) -> Dict[str, Any]:
        """Get all 8 neighboring geohashes."""
        neighbors = geohash_neighbors(geohash)
        
        return {
            'status': 'success',
            'geohash': geohash,
            'neighbors': neighbors,
            'count': len(neighbors)
        }


class SpatialDistanceCommand:
    """DISTANCE - Calculate distance between two points."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float
    ) -> Dict[str, Any]:
        """Calculate haversine distance between two points."""
        p1 = Point(lat1, lon1)
        p2 = Point(lat2, lon2)
        
        distance_m = haversine_distance(p1, p2)
        distance_km = distance_m / 1000
        distance_mi = distance_m / 1609.34
        
        return {
            'status': 'success',
            'point1': {'lat': lat1, 'lon': lon1},
            'point2': {'lat': lat2, 'lon': lon2},
            'distance_meters': round(distance_m, 2),
            'distance_kilometers': round(distance_km, 4),
            'distance_miles': round(distance_mi, 4)
        }


class SpatialStatsCommand:
    """SPATIAL STATS - Show spatial index statistics."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, table_name: Optional[str] = None) -> Dict[str, Any]:
        """Get spatial index statistics."""
        manager = get_spatial_manager()
        
        if table_name:
            index = manager.get_index(table_name)
            if not index:
                return {
                    'status': 'error',
                    'message': f'No spatial index for {table_name}'
                }
            
            stats = index.get_stats()
            return {
                'status': 'success',
                'table': table_name,
                'stats': stats
            }
        else:
            indexes = manager.list_indexes()
            return {
                'status': 'success',
                'spatial_indexes': indexes,
                'count': len(indexes)
            }
