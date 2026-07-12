
"""
Batch Geospatial Operations for KosDB v2.3.0

Provides batch operations for geospatial data:
- Batch GEO ADD for bulk point insertion
- Batch radius searches with multiple centers
- Batch nearest neighbor queries
- Batch bounding box queries
- Optimized spatial index for batch operations
"""

import re
import time
import logging
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


# Try to import geospatial support
try:
    from geospatial import (
        SpatialIndex, Point, BoundingBox, PointGeometry,
        CircleGeometry, haversine_distance, geohash_encode
    )
    GEO_AVAILABLE = True
except ImportError:
    GEO_AVAILABLE = False
    # Define minimal BoundingBox for parsing
    class BoundingBox:
        def __init__(self, min_lat: float, min_lon: float, 
                     max_lat: float, max_lon: float):
            self.min_lat = min_lat
            self.min_lon = min_lon
            self.max_lat = max_lat
            self.max_lon = max_lon


@dataclass
class BatchGeoAddResult:
    """Result of batch geo add operation."""
    added: int
    failed: int
    elapsed_ms: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'added': self.added,
            'failed': self.failed,
            'elapsed_ms': self.elapsed_ms
        }


@dataclass
class BatchRadiusSearchResult:
    """Result of batch radius search."""
    center_id: str
    center: Tuple[float, float]
    radius_meters: float
    results: List[Tuple[str, float]]
    elapsed_ms: float


@dataclass
class BatchNearestNeighborResult:
    """Result of batch nearest neighbor query."""
    query_id: str
    query_point: Tuple[float, float]
    neighbors: List[Tuple[str, float]]
    elapsed_ms: float


@dataclass
class BatchBBoxQueryResult:
    """Result of batch bounding box query."""
    query_id: str
    bbox: BoundingBox
    results: List[str]
    elapsed_ms: float


class BatchGeospatialManager:
    """Manager for batch geospatial operations."""
    
    def __init__(self, spatial_index: Optional[Any] = None):
        self.spatial_index = spatial_index
        self._metrics = {
            'batch_adds': 0,
            'batch_radius_searches': 0,
            'batch_nn_queries': 0,
            'batch_bbox_queries': 0,
            'total_points_added': 0
        }
    
    def batch_geo_add(
        self,
        points: List[Tuple[str, float, float, Optional[Dict[str, Any]]]],
        batch_size: int = 1000
    ) -> BatchGeoAddResult:
        """
        Batch add points to spatial index.
        
        Args:
            points: List of (point_id, lat, lon, metadata) tuples
            batch_size: Processing batch size
        
        Returns:
            Batch add result
        """
        if not GEO_AVAILABLE or not self.spatial_index:
            return BatchGeoAddResult(
                added=0, failed=len(points), elapsed_ms=0
            )
        
        start_time = time.time()
        added = 0
        failed = 0
        
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            
            for point_data in batch:
                try:
                    if len(point_data) >= 3:
                        point_id = point_data[0]
                        lat = float(point_data[1])
                        lon = float(point_data[2])
                        metadata = point_data[3] if len(point_data) > 3 else {}
                        
                        self.spatial_index.insert(point_id, lat, lon, metadata)
                        added += 1
                    else:
                        failed += 1
                except Exception as e:
                    logger.warning(f"Failed to add point {point_data[0] if point_data else 'unknown'}: {e}")
                    failed += 1
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        self._metrics['batch_adds'] += 1
        self._metrics['total_points_added'] += added
        
        return BatchGeoAddResult(
            added=added,
            failed=failed,
            elapsed_ms=elapsed_ms
        )
    
    def batch_radius_search(
        self,
        centers: List[Tuple[str, float, float, float]],
        k: int = 10,
        parallel: bool = False
    ) -> List[BatchRadiusSearchResult]:
        """
        Batch radius search with multiple centers.
        
        Args:
            centers: List of (center_id, lat, lon, radius_meters) tuples
            k: Max results per query
            parallel: Use parallel execution
        
        Returns:
            List of radius search results
        """
        if not GEO_AVAILABLE or not self.spatial_index:
            return []
        
        results = []
        
        if parallel and len(centers) > 1:
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {
                    executor.submit(
                        self._radius_search_single, center_id, lat, lon, radius, k
                    ): center_id
                    for center_id, lat, lon, radius in centers
                }
                
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        results.append(result)
        else:
            for center_id, lat, lon, radius in centers:
                result = self._radius_search_single(center_id, lat, lon, radius, k)
                if result:
                    results.append(result)
        
        self._metrics['batch_radius_searches'] += 1
        
        return results
    
    def _radius_search_single(
        self,
        center_id: str,
        lat: float,
        lon: float,
        radius_meters: float,
        k: int
    ) -> Optional[BatchRadiusSearchResult]:
        """Single radius search."""
        start_time = time.time()
        
        try:
            # Use spatial index radius search
            results = self.spatial_index.radius_search(
                lat, lon, radius_meters, limit=k
            )
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            return BatchRadiusSearchResult(
                center_id=center_id,
                center=(lat, lon),
                radius_meters=radius_meters,
                results=results,
                elapsed_ms=elapsed_ms
            )
        except Exception as e:
            logger.warning(f"Radius search failed for {center_id}: {e}")
            return None
    
    def batch_nearest_neighbor(
        self,
        queries: List[Tuple[str, float, float]],
        k: int = 5,
        parallel: bool = False
    ) -> List[BatchNearestNeighborResult]:
        """
        Batch nearest neighbor queries.
        
        Args:
            queries: List of (query_id, lat, lon) tuples
            k: Number of nearest neighbors
            parallel: Use parallel execution
        
        Returns:
            List of nearest neighbor results
        """
        if not GEO_AVAILABLE or not self.spatial_index:
            return []
        
        results = []
        
        if parallel and len(queries) > 1:
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {
                    executor.submit(
                        self._nn_search_single, query_id, lat, lon, k
                    ): query_id
                    for query_id, lat, lon in queries
                }
                
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        results.append(result)
        else:
            for query_id, lat, lon in queries:
                result = self._nn_search_single(query_id, lat, lon, k)
                if result:
                    results.append(result)
        
        self._metrics['batch_nn_queries'] += 1
        
        return results
    
    def _nn_search_single(
        self,
        query_id: str,
        lat: float,
        lon: float,
        k: int
    ) -> Optional[BatchNearestNeighborResult]:
        """Single nearest neighbor search."""
        start_time = time.time()
        
        try:
            # Use spatial index nearest neighbor search
            neighbors = self.spatial_index.nearest_neighbors(lat, lon, k=k)
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            return BatchNearestNeighborResult(
                query_id=query_id,
                query_point=(lat, lon),
                neighbors=neighbors,
                elapsed_ms=elapsed_ms
            )
        except Exception as e:
            logger.warning(f"NN search failed for {query_id}: {e}")
            return None
    
    def batch_bbox_query(
        self,
        bboxes: List[Tuple[str, BoundingBox]],
        parallel: bool = False
    ) -> List[BatchBBoxQueryResult]:
        """
        Batch bounding box queries.
        
        Args:
            bboxes: List of (query_id, bbox) tuples
            parallel: Use parallel execution
        
        Returns:
            List of bbox query results
        """
        if not GEO_AVAILABLE or not self.spatial_index:
            return []
        
        results = []
        
        if parallel and len(bboxes) > 1:
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {
                    executor.submit(
                        self._bbox_query_single, query_id, bbox
                    ): query_id
                    for query_id, bbox in bboxes
                }
                
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        results.append(result)
        else:
            for query_id, bbox in bboxes:
                result = self._bbox_query_single(query_id, bbox)
                if result:
                    results.append(result)
        
        self._metrics['batch_bbox_queries'] += 1
        
        return results
    
    def _bbox_query_single(
        self,
        query_id: str,
        bbox: BoundingBox
    ) -> Optional[BatchBBoxQueryResult]:
        """Single bbox query."""
        start_time = time.time()
        
        try:
            # Use spatial index bbox search
            results = self.spatial_index.bbox_search(bbox)
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            return BatchBBoxQueryResult(
                query_id=query_id,
                bbox=bbox,
                results=results,
                elapsed_ms=elapsed_ms
            )
        except Exception as e:
            logger.warning(f"Bbox query failed for {query_id}: {e}")
            return None
    
    def optimize_spatial_index(self) -> Dict[str, Any]:
        """Optimize spatial index for batch operations."""
        if not GEO_AVAILABLE or not self.spatial_index:
            return {'error': 'Spatial index not available'}
        
        start_time = time.time()
        
        # Force index rebuild
        if hasattr(self.spatial_index, 'rebuild'):
            self.spatial_index.rebuild()
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        return {
            'optimized': True,
            'elapsed_ms': elapsed_ms
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get batch geospatial metrics."""
        return dict(self._metrics)


def parse_geo_add_batch(command: str) -> Tuple[Optional[str], List[Tuple]]:
    """Parse GEO ADD BATCH command."""
    # GEO ADD BATCH index_name [(id, lat, lon), ...]
    match = re.match(r'GEO\s+ADD\s+BATCH\s+(\w+)', command, re.IGNORECASE)
    if not match:
        return None, []
    
    index_name = match.group(1)
    
    # Extract values list
    values_match = re.search(r'\[(.*?)\]', command, re.DOTALL)
    if not values_match:
        return index_name, []
    
    values_str = values_match.group(1)
    points = []
    
    # Parse tuples: ('id', lat, lon)
    tuple_pattern = r"\(\s*'([^']+)'\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)"
    
    for m in re.finditer(tuple_pattern, values_str):
        point_id = m.group(1)
        lat = float(m.group(2))
        lon = float(m.group(3))
        points.append((point_id, lat, lon))
    
    return index_name, points


def parse_radius_search_batch(command: str) -> Dict[str, Any]:
    """Parse batch radius search command."""
    # GEO RADIUS SEARCH BATCH index_name [(id, lat, lon, radius), ...] LIMIT k
    match = re.search(r'GEO\s+RADIUS\s+SEARCH\s+BATCH\s+(\w+)', command, re.IGNORECASE)
    if not match:
        return {}
    
    index_name = match.group(1)
    
    # Extract centers list
    values_match = re.search(r'\[(.*?)\]', command, re.DOTALL)
    if not values_match:
        return {'index_name': index_name, 'centers': [], 'k': 10}
    
    values_str = values_match.group(1)
    centers = []
    
    # Parse tuples: ('id', lat, lon, radius)
    tuple_pattern = r"\(\s*'([^']+)'\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)"
    
    for m in re.finditer(tuple_pattern, values_str):
        center_id = m.group(1)
        lat = float(m.group(2))
        lon = float(m.group(3))
        radius = float(m.group(4))
        centers.append((center_id, lat, lon, radius))
    
    # Parse limit
    limit_match = re.search(r'LIMIT\s+(\d+)', command, re.IGNORECASE)
    k = int(limit_match.group(1)) if limit_match else 10
    
    return {
        'index_name': index_name,
        'centers': centers,
        'k': k
    }


def parse_bbox_query_batch(command: str) -> Dict[str, Any]:
    """Parse batch bbox query command."""
    # GEO BBOX QUERY BATCH index_name [(id, min_lat, min_lon, max_lat, max_lon), ...]
    match = re.search(r'GEO\s+BBOX\s+QUERY\s+BATCH\s+(\w+)', command, re.IGNORECASE)
    if not match:
        return {}
    
    index_name = match.group(1)
    
    # Extract bbox list
    values_match = re.search(r'\[(.*?)\]', command, re.DOTALL)
    if not values_match:
        return {'index_name': index_name, 'bboxes': []}
    
    values_str = values_match.group(1)
    bboxes = []
    
    # Parse tuples: ('id', min_lat, min_lon, max_lat, max_lon)
    tuple_pattern = r"\(\s*'([^']+)'\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)"
    
    for m in re.finditer(tuple_pattern, values_str):
        query_id = m.group(1)
        min_lat = float(m.group(2))
        min_lon = float(m.group(3))
        max_lat = float(m.group(4))
        max_lon = float(m.group(5))
        
        bbox = BoundingBox(min_lat, min_lon, max_lat, max_lon)
        bboxes.append((query_id, bbox))
    
    return {
        'index_name': index_name,
        'bboxes': bboxes
    }


# Global manager
_batch_geo_manager: Optional[BatchGeospatialManager] = None


def get_batch_geo_manager(spatial_index: Optional[Any] = None) -> BatchGeospatialManager:
    """Get global batch geospatial manager."""
    global _batch_geo_manager
    if _batch_geo_manager is None:
        _batch_geo_manager = BatchGeospatialManager(spatial_index)
    return _batch_geo_manager
