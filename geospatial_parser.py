"""
Parser extensions for geospatial commands.

Adds CREATE SPATIAL INDEX, NEAR, WITHIN, INTERSECTS, BOUNDING_BOX, 
GEOHASH, and DISTANCE commands.
"""

import re
from typing import Dict, Any, Optional


class GeospatialParser:
    """
    Parser for geospatial commands.
    
    Supports:
    - CREATE SPATIAL INDEX ON table_name (column)
    - DROP SPATIAL INDEX ON table_name
    - NEAR table_name LAT lon LON lon RADIUS r [UNIT unit]
    - WITHIN table_name CIRCLE lat lon radius
    - WITHIN table_name POLYGON (lat1,lon1),(lat2,lon2),...
    - INTERSECTS table_name BBOX min_lat min_lon max_lat max_lon
    - BOUNDING_BOX table_name min_lat min_lon max_lat max_lon
    - SPATIAL INSERT table_name id lat lon
    - SPATIAL DELETE table_name id
    - GEOHASH ENCODE lat lon [PRECISION n]
    - GEOHASH NEIGHBORS geohash
    - DISTANCE lat1 lon1 lat2 lon2
    - SPATIAL STATS [table_name]
    """
    
    # Command patterns
    CREATE_SPATIAL_INDEX_PATTERN = re.compile(
        r'CREATE\s+SPATIAL\s+INDEX\s+ON\s+(\w+)'
        r'(?:\s*\(\s*(\w+)\s*\))?',
        re.IGNORECASE
    )
    
    DROP_SPATIAL_INDEX_PATTERN = re.compile(
        r'DROP\s+SPATIAL\s+INDEX\s+(?:ON\s+)?(\w+)',
        re.IGNORECASE
    )
    
    NEAR_PATTERN = re.compile(
        r'NEAR\s+(\w+)\s+'
        r'LAT\s+(-?\d+\.?\d*)\s+'
        r'LON\s+(-?\d+\.?\d*)\s+'
        r'RADIUS\s+(\d+\.?\d*)'
        r'(?:\s+UNIT\s+(\w+))?',
        re.IGNORECASE
    )
    
    WITHIN_CIRCLE_PATTERN = re.compile(
        r'WITHIN\s+(\w+)\s+CIRCLE\s+'
        r'(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+(\d+\.?\d*)',
        re.IGNORECASE
    )
    
    WITHIN_POLYGON_PATTERN = re.compile(
        r'WITHIN\s+(\w+)\s+POLYGON\s+(.+)',
        re.IGNORECASE | re.DOTALL
    )
    
    INTERSECTS_BBOX_PATTERN = re.compile(
        r'INTERSECTS\s+(\w+)\s+BBOX\s+'
        r'(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+'
        r'(-?\d+\.?\d*)\s+(-?\d+\.?\d*)',
        re.IGNORECASE
    )
    
    BOUNDING_BOX_PATTERN = re.compile(
        r'BOUNDING[_-]?BOX\s+(\w+)\s+'
        r'(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+'
        r'(-?\d+\.?\d*)\s+(-?\d+\.?\d*)',
        re.IGNORECASE
    )
    
    SPATIAL_INSERT_PATTERN = re.compile(
        r'SPATIAL\s+INSERT\s+(\w+)\s+(\w+)\s+'
        r'(-?\d+\.?\d*)\s+(-?\d+\.?\d*)',
        re.IGNORECASE
    )
    
    SPATIAL_DELETE_PATTERN = re.compile(
        r'SPATIAL\s+DELETE\s+(\w+)\s+(\w+)',
        re.IGNORECASE
    )
    
    GEOHASH_ENCODE_PATTERN = re.compile(
        r'GEOHASH\s+ENCODE\s+'
        r'(-?\d+\.?\d*)\s+(-?\d+\.?\d*)'
        r'(?:\s+PRECISION\s+(\d+))?',
        re.IGNORECASE
    )
    
    GEOHASH_NEIGHBORS_PATTERN = re.compile(
        r'GEOHASH\s+NEIGHBORS\s+([a-z0-9]+)',
        re.IGNORECASE
    )
    
    DISTANCE_PATTERN = re.compile(
        r'DISTANCE\s+'
        r'(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+'
        r'(-?\d+\.?\d*)\s+(-?\d+\.?\d*)',
        re.IGNORECASE
    )
    
    SPATIAL_STATS_PATTERN = re.compile(
        r'SPATIAL\s+STATS(?:\s+(\w+))?',
        re.IGNORECASE
    )
    
    def parse(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Parse a geospatial command.
        
        Args:
            query: SQL command string
        
        Returns:
            Parsed command dict or None if not recognized
        """
        query = query.strip()
        upper = query.upper()
        
        # CREATE SPATIAL INDEX
        match = self.CREATE_SPATIAL_INDEX_PATTERN.match(query)
        if match:
            return {
                'type': 'CREATE_SPATIAL_INDEX',
                'command': 'create_spatial_index',
                'table_name': match.group(1),
                'column': match.group(2) or 'location'
            }
        
        # DROP SPATIAL INDEX
        match = self.DROP_SPATIAL_INDEX_PATTERN.match(query)
        if match:
            return {
                'type': 'DROP_SPATIAL_INDEX',
                'command': 'drop_spatial_index',
                'table_name': match.group(1)
            }
        
        # NEAR
        match = self.NEAR_PATTERN.match(query)
        if match:
            return {
                'type': 'NEAR',
                'command': 'spatial_near',
                'table_name': match.group(1),
                'lat': float(match.group(2)),
                'lon': float(match.group(3)),
                'radius': float(match.group(4)),
                'unit': match.group(5) or 'meters'
            }
        
        # WITHIN CIRCLE
        match = self.WITHIN_CIRCLE_PATTERN.match(query)
        if match:
            return {
                'type': 'WITHIN_CIRCLE',
                'command': 'spatial_within',
                'table_name': match.group(1),
                'geometry_type': 'circle',
                'lat': float(match.group(2)),
                'lon': float(match.group(3)),
                'radius': float(match.group(4))
            }
        
        # WITHIN POLYGON
        match = self.WITHIN_POLYGON_PATTERN.match(query)
        if match:
            points_str = match.group(2).strip()
            points = self._parse_polygon_points(points_str)
            
            return {
                'type': 'WITHIN_POLYGON',
                'command': 'spatial_within',
                'table_name': match.group(1),\n                'geometry_type': 'polygon',\n                'points': points\n            }\n        \n        # INTERSECTS BBOX\n        match = self.INTERSECTS_BBOX_PATTERN.match(query)\n        if match:\n            return {\n                'type': 'INTERSECTS_BBOX',\n                'command': 'spatial_intersects',\n                'table_name': match.group(1),\n                'geometry_type': 'bbox',\n                'min_lat': float(match.group(2)),\n                'min_lon': float(match.group(3)),\n                'max_lat': float(match.group(4)),\n                'max_lon': float(match.group(5))\n            }\n        \n        # BOUNDING_BOX\n        match = self.BOUNDING_BOX_PATTERN.match(query)\n        if match:\n            return {\n                'type': 'BOUNDING_BOX',\n                'command': 'spatial_bounding_box',\n                'table_name': match.group(1),\n                'min_lat': float(match.group(2)),\n                'min_lon': float(match.group(3)),\n                'max_lat': float(match.group(4)),\n                'max_lon': float(match.group(5))\n            }\n        \n        # SPATIAL INSERT\n        match = self.SPATIAL_INSERT_PATTERN.match(query)\n        if match:\n            return {\n                'type': 'SPATIAL_INSERT',\n                'command': 'spatial_insert',\n                'table_name': match.group(1),\n                'obj_id': match.group(2),\n                'lat': float(match.group(3)),\n                'lon': float(match.group(4))\n            }\n        \n        # SPATIAL DELETE\n        match = self.SPATIAL_DELETE_PATTERN.match(query)\n        if match:\n            return {\n                'type': 'SPATIAL_DELETE',\n                'command': 'spatial_delete',\n                'table_name': match.group(1),\n                'obj_id': match.group(2)\n            }\n        \n        # GEOHASH ENCODE\n        match = self.GEOHASH_ENCODE_PATTERN.match(query)\n        if match:\n            return {\n                'type': 'GEOHASH_ENCODE',\n                'command': 'geohash_encode',\n                'lat': float(match.group(1)),\n                'lon': float(match.group(2)),\n                'precision': int(match.group(3)) if match.group(3) else 12\n            }\n        \n        # GEOHASH NEIGHBORS\n        match = self.GEOHASH_NEIGHBORS_PATTERN.match(query)\n        if match:\n            return {\n                'type': 'GEOHASH_NEIGHBORS',\n                'command': 'geohash_neighbors',\n                'geohash': match.group(1)\n            }\n        \n        # DISTANCE\n        match = self.DISTANCE_PATTERN.match(query)\n        if match:\n            return {\n                'type': 'DISTANCE',\n                'command': 'spatial_distance',\n                'lat1': float(match.group(1)),\n                'lon1': float(match.group(2)),\n                'lat2': float(match.group(3)),\n                'lon2': float(match.group(4))\n            }\n        \n        # SPATIAL STATS\n        match = self.SPATIAL_STATS_PATTERN.match(query)\n        if match:\n            return {\n                'type': 'SPATIAL_STATS',\n                'command': 'spatial_stats',\n                'table_name': match.group(1)\n            }\n        \n        return None\n    \n    def _parse_polygon_points(self, points_str: str) -> list:\n        \"\"\"Parse polygon points from string.\"\"\"\n        points = []\n        # Remove parentheses and split\n        points_str = points_str.replace('(', '').replace(')', '')\n        pairs = points_str.split(',')\n        \n        for pair in pairs:\n            coords = pair.strip().split()\n            if len(coords) >= 2:\n                try:\n                    lat = float(coords[0])\n                    lon = float(coords[1])\n                    points.append((lat, lon))\n                except ValueError:\n                    continue\n        \n        return points\n\n\n# Singleton parser instance\n_geospatial_parser: Optional[GeospatialParser] = None\n\n\ndef get_geospatial_parser() -> GeospatialParser:\n    \"\"\"Get global geospatial parser.\"\"\"\n    global _geospatial_parser\n    if _geospatial_parser is None:\n        _geospatial_parser = GeospatialParser()\n    return _geospatial_parser
