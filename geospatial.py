"""
Geospatial Indexing for KosDB

Implements R-tree spatial indexing with support for POINT, POLYGON, and CIRCLE
geometry types. Includes spatial query operators and geohash encoding.
"""

import math
import json
import logging
from enum import Enum
from typing import List, Tuple, Optional, Dict, Any, Union, Iterator
from dataclasses import dataclass
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class GeometryType(Enum):
    """Supported geometry types."""
    POINT = "point"
    POLYGON = "polygon"
    CIRCLE = "circle"
    BBOX = "bbox"


@dataclass
class Point:
    """2D Point with latitude and longitude."""
    lat: float
    lon: float
    
    def __post_init__(self):
        if not (-90 <= self.lat <= 90):
            raise ValueError(f"Latitude must be between -90 and 90, got {self.lat}")
        if not (-180 <= self.lon <= 180):
            raise ValueError(f"Longitude must be between -180 and 180, got {self.lon}")
    
    def to_tuple(self) -> Tuple[float, float]:
        return (self.lat, self.lon)
    
    def __hash__(self):
        return hash((round(self.lat, 6), round(self.lon, 6)))


@dataclass
class BoundingBox:
    """Axis-aligned bounding box."""
    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float
    
    @property
    def center(self) -> Point:
        """Calculate center point."""
        return Point(
            (self.min_lat + self.max_lat) / 2,
            (self.min_lon + self.max_lon) / 2
        )
    
    @property
    def area(self) -> float:
        """Calculate area (approximate for small regions)."""
        return (self.max_lat - self.min_lat) * (self.max_lon - self.min_lon)
    
    def contains(self, point: Point) -> bool:
        """Check if point is inside bounding box."""
        return (self.min_lat <= point.lat <= self.max_lat and
                self.min_lon <= point.lon <= self.max_lon)
    
    def intersects(self, other: 'BoundingBox') -> bool:
        """Check if two bounding boxes intersect."""
        return not (self.max_lat < other.min_lat or
                   self.min_lat > other.max_lat or
                   self.max_lon < other.min_lon or
                   self.min_lon > other.max_lon)
    
    def expand(self, point: Point) -> 'BoundingBox':
        """Expand bounding box to include point."""
        return BoundingBox(
            min(self.min_lat, point.lat),
            min(self.min_lon, point.lon),
            max(self.max_lat, point.lat),
            max(self.max_lon, point.lon)
        )
    
    def expand_box(self, other: 'BoundingBox') -> 'BoundingBox':
        """Expand bounding box to include another box."""
        return BoundingBox(
            min(self.min_lat, other.min_lat),
            min(self.min_lon, other.min_lon),
            max(self.max_lat, other.max_lat),
            max(self.max_lon, other.max_lon)
        )


class Geometry(ABC):
    """Abstract base class for geometries."""
    
    @property
    @abstractmethod
    def bbox(self) -> BoundingBox:
        """Get bounding box."""
        pass
    
    @abstractmethod
    def contains(self, point: Point) -> bool:
        """Check if geometry contains point."""
        pass
    
    @abstractmethod
    def intersects(self, other: 'Geometry') -> bool:
        """Check if geometry intersects another."""
        pass


class PointGeometry(Geometry):
    """Point geometry."""
    
    def __init__(self, lat: float, lon: float):
        self.point = Point(lat, lon)
    
    @property
    def bbox(self) -> BoundingBox:
        # Point has zero-area bbox
        return BoundingBox(
            self.point.lat, self.point.lon,
            self.point.lat, self.point.lon
        )
    
    def contains(self, point: Point) -> bool:
        return self.point == point
    
    def intersects(self, other: Geometry) -> bool:
        return other.contains(self.point)
    
    def distance_to(self, other: Point) -> float:
        """Calculate haversine distance to another point in meters."""
        return haversine_distance(self.point, other)


class CircleGeometry(Geometry):
    """Circle geometry with center and radius."""
    
    def __init__(self, center_lat: float, center_lon: float, radius_meters: float):
        self.center = Point(center_lat, center_lon)
        self.radius_meters = radius_meters
        
        # Calculate bbox (approximate)
        # 1 degree lat ≈ 111km
        lat_delta = radius_meters / 111000
        # 1 degree lon varies by latitude
        lon_delta = radius_meters / (111000 * math.cos(math.radians(center_lat)))
        
        self._bbox = BoundingBox(
            center_lat - lat_delta,
            center_lon - lon_delta,
            center_lat + lat_delta,
            center_lon + lon_delta
        )
    
    @property
    def bbox(self) -> BoundingBox:
        return self._bbox
    
    def contains(self, point: Point) -> bool:
        """Check if point is within circle."""
        distance = haversine_distance(self.center, point)
        return distance <= self.radius_meters
    
    def intersects(self, other: Geometry) -> bool:
        """Check if circle intersects another geometry."""
        # Simplified: check bbox intersection first
        if not self.bbox.intersects(other.bbox):
            return False
        
        # For point
        if isinstance(other, PointGeometry):
            return self.contains(other.point)
        
        # For other geometries, use bbox approximation
        return True


class PolygonGeometry(Geometry):
    """Polygon geometry (simple, non-self-intersecting)."""
    
    def __init__(self, points: List[Tuple[float, float]]):
        if len(points) < 3:
            raise ValueError("Polygon must have at least 3 points")
        
        self.points = [Point(lat, lon) for lat, lon in points]
        
        # Calculate bbox
        lats = [p.lat for p in self.points]
        lons = [p.lon for p in self.points]
        self._bbox = BoundingBox(min(lats), min(lons), max(lats), max(lons))
    
    @property
    def bbox(self) -> BoundingBox:
        return self._bbox
    
    def contains(self, point: Point) -> bool:
        """Ray casting algorithm for point-in-polygon."""
        n = len(self.points)
        inside = False
        
        j = n - 1
        for i in range(n):
            pi = self.points[i]
            pj = self.points[j]
            
            if ((pi.lon > point.lon) != (pj.lon > point.lon) and
                point.lat < (pj.lat - pi.lat) * (point.lon - pi.lon) / (pj.lon - pi.lon) + pi.lat):
                inside = not inside
            
            j = i
        
        return inside
    
    def intersects(self, other: Geometry) -> bool:
        """Check if polygon intersects another geometry."""
        if not self.bbox.intersects(other.bbox):
            return False
        
        # Check if any point of other is inside polygon
        if isinstance(other, PointGeometry):
            return self.contains(other.point)
        
        if isinstance(other, CircleGeometry):
            # Check if circle center is in polygon or circle intersects polygon edge
            return self.contains(other.center)
        
        # Default: bbox intersection
        return True


def haversine_distance(p1: Point, p2: Point) -> float:
    """
    Calculate haversine distance between two points in meters.
    
    Args:
        p1: First point
        p2: Second point
    
    Returns:
        Distance in meters
    """
    R = 6371000  # Earth radius in meters
    
    lat1 = math.radians(p1.lat)
    lat2 = math.radians(p2.lat)
    dlat = math.radians(p2.lat - p1.lat)
    dlon = math.radians(p2.lon - p1.lon)
    
    a = (math.sin(dlat/2) * math.sin(dlat/2) +
         math.cos(lat1) * math.cos(lat2) *
         math.sin(dlon/2) * math.sin(dlon/2))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c


def geohash_encode(lat: float, lon: float, precision: int = 12) -> str:
    """
    Encode latitude/longitude to geohash string.
    
    Args:
        lat: Latitude
        lon: Longitude
        precision: Length of geohash (1-12)
    
    Returns:
        Geohash string
    """
    base32 = '0123456789bcdefghjkmnpqrstuvwxyz'
    
    lat_range = [-90.0, 90.0]
    lon_range = [-180.0, 180.0]
    
    geohash = []
    bits = 0
    bits_total = 0
    even_bit = True
    
    while len(geohash) < precision:
        if even_bit:
            # Divide longitude range
            mid = (lon_range[0] + lon_range[1]) / 2
            if lon >= mid:
                bits = (bits << 1) | 1
                lon_range[0] = mid
            else:
                bits = bits << 1
                lon_range[1] = mid
        else:
            # Divide latitude range
            mid = (lat_range[0] + lat_range[1]) / 2
            if lat >= mid:
                bits = (bits << 1) | 1
                lat_range[0] = mid
            else:
                bits = bits << 1
                lat_range[1] = mid
        
        even_bit = not even_bit
        bits_total += 1
        
        if bits_total == 5:
            geohash.append(base32[bits])
            bits = 0
            bits_total = 0
    
    return ''.join(geohash)


def geohash_decode(geohash: str) -> Tuple[float, float, float, float]:
    """
    Decode geohash to bounding box.
    
    Args:
        geohash: Geohash string
    
    Returns:
        (min_lat, min_lon, max_lat, max_lon)
    """
    base32 = '0123456789bcdefghjkmnpqrstuvwxyz'
    
    lat_range = [-90.0, 90.0]
    lon_range = [-180.0, 180.0]
    even_bit = True
    
    for char in geohash:
        cd = base32.index(char)
        for mask in [16, 8, 4, 2, 1]:
            if even_bit:
                # Longitude
                mid = (lon_range[0] + lon_range[1]) / 2
                if cd & mask:
                    lon_range[0] = mid
                else:
                    lon_range[1] = mid
            else:
                # Latitude
                mid = (lat_range[0] + lat_range[1]) / 2
                if cd & mask:
                    lat_range[0] = mid
                else:
                    lat_range[1] = mid
            
            even_bit = not even_bit
    
    return (lat_range[0], lon_range[0], lat_range[1], lon_range[1])


def geohash_neighbors(geohash: str) -> List[str]:
    """Get all 8 neighboring geohashes."""
    if not geohash:
        return []
    
    # Direction deltas
    lat_delta = {'n': 1, 's': -1, 'e': 0, 'w': 0}
    lon_delta = {'n': 0, 's': 0, 'e': 1, 'w': -1}
    
    neighbors = []
    bbox = geohash_decode(geohash)
    center_lat = (bbox[0] + bbox[2]) / 2
    center_lon = (bbox[1] + bbox[3]) / 2
    
    # Calculate neighbor centers
    lat_step = (bbox[2] - bbox[0])
    lon_step = (bbox[3] - bbox[1])
    
    for direction in ['n', 'ne', 'e', 'se', 's', 'sw', 'w', 'nw']:
        dlat = {'n': 1, 'ne': 1, 'e': 0, 'se': -1, 's': -1, 'sw': -1, 'w': 0, 'nw': 1}[direction]
        dlon = {'n': 0, 'ne': 1, 'e': 1, 'se': 1, 's': 0, 'sw': -1, 'w': -1, 'nw': -1}[direction]
        
        nlat = center_lat + dlat * lat_step
        nlon = center_lon + dlon * lon_step
        
        if -90 <= nlat <= 90 and -180 <= nlon <= 180:
            neighbors.append(geohash_encode(nlat, nlon, len(geohash)))
    
    return neighbors


class RTreeNode:
    """Node in R-tree."""
    
    def __init__(self, is_leaf: bool = True):
        self.is_leaf = is_leaf
        self.entries: List[Union[Tuple[BoundingBox, str], 'RTreeNode']] = []
        self.bbox: Optional[BoundingBox] = None
    
    def add_entry(self, bbox: BoundingBox, obj_id: str):
        """Add entry to leaf node."""
        self.entries.append((bbox, obj_id))
        self._update_bbox(bbox)
    
    def add_child(self, node: 'RTreeNode'):
        """Add child node (for internal nodes)."""
        self.entries.append(node)
        if node.bbox:
            self._update_bbox(node.bbox)
    
    def _update_bbox(self, bbox: BoundingBox):
        """Update node's bounding box."""
        if self.bbox is None:
            self.bbox = bbox
        else:
            self.bbox = self.bbox.expand_box(bbox)
    
    def search(self, query_bbox: BoundingBox) -> List[str]:
        """Search for objects intersecting query bbox."""
        results = []
        
        if not self.bbox or not self.bbox.intersects(query_bbox):
            return results
        
        for entry in self.entries:
            if self.is_leaf:
                entry_bbox, obj_id = entry
                if entry_bbox.intersects(query_bbox):
                    results.append(obj_id)
            else:
                child_node = entry
                results.extend(child_node.search(query_bbox))
        
        return results


class RTreeIndex:
    """
    R-tree spatial index.
    
    Simple implementation with quadratic split.
    """
    
    MAX_ENTRIES = 8
    MIN_ENTRIES = 2
    
    def __init__(self):
        self.root = RTreeNode(is_leaf=True)
        self.objects: Dict[str, Tuple[Geometry, Any]] = {}
    
    def insert(self, obj_id: str, geometry: Geometry, data: Any = None):
        """
        Insert object into index.
        
        Args:
            obj_id: Unique object identifier
            geometry: Geometry object
            data: Associated data
        """
        self.objects[obj_id] = (geometry, data)
        
        bbox = geometry.bbox
        
        # Simple insert - in production would use proper R-tree insertion
        if len(self.root.entries) < self.MAX_ENTRIES:
            self.root.add_entry(bbox, obj_id)
        else:
            # Split node
            self._split_and_insert(bbox, obj_id)
    
    def _split_and_insert(self, bbox: BoundingBox, obj_id: str):
        """Split node and insert."""
        # Simplified: create new root
        old_root = self.root
        self.root = RTreeNode(is_leaf=False)
        self.root.add_child(old_root)
        
        # Create new leaf for overflow
        new_leaf = RTreeNode(is_leaf=True)
        new_leaf.add_entry(bbox, obj_id)
        
        self.root.add_child(new_leaf)
    
    def search(self, bbox: BoundingBox) -> List[Tuple[str, Geometry, Any]]:
        """
        Search for objects intersecting bounding box.
        
        Args:
            bbox: Query bounding box
        
        Returns:
            List of (obj_id, geometry, data) tuples
        """
        obj_ids = self.root.search(bbox)
        results = []
        
        for obj_id in obj_ids:
            if obj_id in self.objects:
                geom, data = self.objects[obj_id]
                results.append((obj_id, geom, data))
        
        return results
    
    def near(self, point: Point, radius_meters: float) -> List[Tuple[str, float, Any]]:
        """
        Find objects near a point.
        
        Args:
            point: Center point
            radius_meters: Search radius
        
        Returns:
            List of (obj_id, distance, data) tuples sorted by distance
        """
        # Create circle for search
        circle = CircleGeometry(point.lat, point.lon, radius_meters)
        
        # Search bbox first
        candidates = self.search(circle.bbox)
        
        # Filter by actual distance
        results = []
        for obj_id, geom, data in candidates:
            if isinstance(geom, PointGeometry):
                dist = haversine_distance(point, geom.point)
                if dist <= radius_meters:
                    results.append((obj_id, dist, data))
            elif isinstance(geom, CircleGeometry):
                dist = haversine_distance(point, geom.center)
                if dist <= radius_meters + geom.radius_meters:
                    results.append((obj_id, dist, data))
            elif geom.contains(point):
                results.append((obj_id, 0, data))
        
        # Sort by distance
        results.sort(key=lambda x: x[1])
        return results
    
    def within(self, geometry: Geometry) -> List[Tuple[str, Geometry, Any]]:
        """
        Find objects within a geometry.
        
        Args:
            geometry: Containing geometry
        
        Returns:
            List of (obj_id, geometry, data) tuples
        """
        candidates = self.search(geometry.bbox)
        results = []
        
        for obj_id, geom, data in candidates:
            if isinstance(geometry, CircleGeometry):
                # Check if object is within circle
                if isinstance(geom, PointGeometry):
                    if geometry.contains(geom.point):
                        results.append((obj_id, geom, data))
                elif isinstance(geom, CircleGeometry):
                    # Circle within circle: center distance + radius <= container radius
                    dist = haversine_distance(geometry.center, geom.center)
                    if dist + geom.radius_meters <= geometry.radius_meters:
                        results.append((obj_id, geom, data))
            elif isinstance(geometry, PolygonGeometry):
                if isinstance(geom, PointGeometry):
                    if geometry.contains(geom.point):
                        results.append((obj_id, geom, data))
        
        return results
    
    def intersects(self, geometry: Geometry) -> List[Tuple[str, Geometry, Any]]:
        """
        Find objects intersecting a geometry.
        
        Args:
            geometry: Query geometry
        
        Returns:
            List of (obj_id, geometry, data) tuples
        """
        candidates = self.search(geometry.bbox)
        results = []
        
        for obj_id, geom, data in candidates:
            if geom.intersects(geometry):
                results.append((obj_id, geom, data))
        
        return results
    
    def delete(self, obj_id: str) -> bool:
        """Delete object from index."""
        if obj_id in self.objects:
            del self.objects[obj_id]
            # Note: In production, would need to remove from tree structure
            return True
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        return {
            'total_objects': len(self.objects),
            'index_type': 'R-tree',
            'max_entries_per_node': self.MAX_ENTRIES
        }
