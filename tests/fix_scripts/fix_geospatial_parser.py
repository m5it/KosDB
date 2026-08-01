content = '''\"\"\"
Parser extensions for geospatial commands.

Adds CREATE SPATIAL INDEX, NEAR, WITHIN, INTERSECTS, BOUNDING_BOX, 
GEOHASH, and DISTANCE commands.
\"\"\"

import re
from typing import Dict, Any, Optional


class GeospatialParser:
    \"\"\"
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
    \"\"\"
    
    # Command patterns
    CREATE_SPATIAL_INDEX_PATTERN = re.compile(
        r'CREATE\\s+SPATIAL\\s+INDEX\\s+ON\\s+(\\w+)'
        r'(?:\\s*\\(\\s*(\\w+)\\s*\\))?',
        re.IGNORECASE
    )
    
    DROP_SPATIAL_INDEX_PATTERN = re.compile(
        r'DROP\\s+SPATIAL\\s+INDEX\\s+(?:ON\\s+)?(\\w+)',
        re.IGNORECASE
    )
    
    NEAR_PATTERN = re.compile(
        r'NEAR\\s+(\\w+)\\s+'
        r'LAT\\s+(-?\\d+\\.?\\d*)\\s+'
        r'LON\\s+(-?\\d+\\.?\\d*)\\s+'
        r'RADIUS\\s+(\\d+\\.?\\d*)'
        r'(?:\\s+UNIT\\s+(\\w+))?',
        re.IGNORECASE
    )
    
    WITHIN_CIRCLE_PATTERN = re.compile(
        r'WITHIN\\s+(\\w+)\\s+CIRCLE\\s+'
        r'(-?\\d+\\.?\\d*)\\s+(-?\\d+\\.?\\d*)\\s+(\\d+\\.?\\d*)',
        re.IGNORECASE
    )
    
    WITHIN_POLYGON_PATTERN = re.compile(
        r'WITHIN\\s+(\\w+)\\s+POLYGON\\s+(.+)',
        re.IGNORECASE | re.DOTALL
    )
    
    INTERSECTS_BBOX_PATTERN = re.compile(
        r'INTERSECTS\\s+(\\w+)\\s+BBOX\\s+'
        r'(-?\\d+\\.?\\d*)\\s+(-?\\d+\\.?\\d*)\\s+'
        r'(-?\\d+\\.?\\d*)\\s+(-?\\d+\\.?\\d*)',
        re.IGNORECASE
    )
    
    BOUNDING_BOX_PATTERN = re.compile(
        r'BOUNDING[_-]?BOX\\s+(\\w+)\\s+'
        r'(-?\\d+\\.?\\d*)\\s+(-?\\d+\\.?\\d*)\\s+'
        r'(-?\\d+\\.?\\d*)\\s+(-?\\d+\\.?\\d*)',
        re.IGNORECASE
    )
    
    SPATIAL_INSERT_PATTERN = re.compile(
        r'SPATIAL\\s+INSERT\\s+(\\w+)\\s+(\\w+)\\s+'
        r'(-?\\d+\\.?\\d*)\\s+(-?\\d+\\.?\\d*)',
        re.IGNORECASE
    )
    
    SPATIAL_DELETE_PATTERN = re.compile(
        r'SPATIAL\\s+DELETE\\s+(\\w+)\\s+(\\w+)',
        re.IGNORECASE
    )
    
    GEOHASH_ENCODE_PATTERN = re.compile(
        r'GEOHASH\\s+ENCODE\\s+'
        r'(-?\\d+\\.?\\d*)\\s+(-?\\d+\\.?\\d*)'
        r'(?:\\s+PRECISION\\s+(\\d+))?',
        re.IGNORECASE
    )
    
    GEOHASH_NEIGHBORS_PATTERN = re.compile(
        r'GEOHASH\\s+NEIGHBORS\\s+([a-z0-9]+)',
        re.IGNORECASE
    )
    
    DISTANCE_PATTERN = re.compile(
        r'DISTANCE\\s+'
        r'(-?\\d+\\.?\\d*)\\s+(-?\\d+\\.?\\d*)\\s+'
        r'(-?\\d+\\.?\\d*)\\s+(-?\\d+\\.?\\d*)',
        re.IGNORECASE
    )
    
    SPATIAL_STATS_PATTERN = re.compile(
        r'SPATIAL\\s+STATS(?:\\s+(\\w+))?',
        re.IGNORECASE
    )
    
    def parse(self, query: str) -> Optional[Dict[str, Any]]:
        \"\"\"
        Parse a geospatial command.
        
        Args:
            query: SQL command string
        
        Returns:
            Parsed command dict or None if not recognized
        \"\"\"
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
                'table_name': match.group(1),
                'geometry_type': 'polygon',
                'points': points
            }
        
        # INTERSECTS BBOX
        match = self.INTERSECTS_BBOX_PATTERN.match(query)
        if match:
            return {
                'type': 'INTERSECTS_BBOX',
                'command': 'spatial_intersects',
                'table_name': match.group(1),
                'geometry_type': 'bbox',
                'min_lat': float(match.group(2)),
                'min_lon': float(match.group(3)),
                'max_lat': float(match.group(4)),
                'max_lon': float(match.group(5))
            }
        
        # BOUNDING_BOX
        match = self.BOUNDING_BOX_PATTERN.match(query)
        if match:
            return {
                'type': 'BOUNDING_BOX',
                'command': 'spatial_bounding_box',
                'table_name': match.group(1),
                'min_lat': float(match.group(2)),
                'min_lon': float(match.group(3)),
                'max_lat': float(match.group(4)),
                'max_lon': float(match.group(5))
            }
        
        # SPATIAL INSERT
        match = self.SPATIAL_INSERT_PATTERN.match(query)
        if match:
            return {
                'type': 'SPATIAL_INSERT',
                'command': 'spatial_insert',
                'table_name': match.group(1),
                'obj_id': match.group(2),
                'lat': float(match.group(3)),
                'lon': float(match.group(4))
            }
        
        # SPATIAL DELETE
        match = self.SPATIAL_DELETE_PATTERN.match(query)
        if match:
            return {
                'type': 'SPATIAL_DELETE',
                'command': 'spatial_delete',
                'table_name': match.group(1),
                'obj_id': match.group(2)
            }
        
        # GEOHASH ENCODE
        match = self.GEOHASH_ENCODE_PATTERN.match(query)
        if match:
            return {
                'type': 'GEOHASH_ENCODE',
                'command': 'geohash_encode',
                'lat': float(match.group(1)),
                'lon': float(match.group(2)),
                'precision': int(match.group(3)) if match.group(3) else 12
            }
        
        # GEOHASH NEIGHBORS
        match = self.GEOHASH_NEIGHBORS_PATTERN.match(query)
        if match:
            return {
                'type': 'GEOHASH_NEIGHBORS',
                'command': 'geohash_neighbors',
                'geohash': match.group(1)
            }
        
        # DISTANCE
        match = self.DISTANCE_PATTERN.match(query)
        if match:
            return {
                'type': 'DISTANCE',
                'command': 'spatial_distance',
                'lat1': float(match.group(1)),
                'lon1': float(match.group(2)),
                'lat2': float(match.group(3)),
                'lon2': float(match.group(4))
            }
        
        # SPATIAL STATS
        match = self.SPATIAL_STATS_PATTERN.match(query)
        if match:
            return {
                'type': 'SPATIAL_STATS',
                'command': 'spatial_stats',
                'table_name': match.group(1)
            }
        
        return None
    
    def _parse_polygon_points(self, points_str: str) -> list:
        \"\"\"Parse polygon points from string.\"\"\"
        points = []
        # Remove parentheses and split
        points_str = points_str.replace('(', '').replace(')', '')
        pairs = points_str.split(',')
        
        for pair in pairs:
            coords = pair.strip().split()
            if len(coords) >= 2:
                try:
                    lat = float(coords[0])
                    lon = float(coords[1])
                    points.append((lat, lon))
                except ValueError:
                    continue
        
        return points


# Singleton parser instance
_geospatial_parser: Optional[GeospatialParser] = None


def get_geospatial_parser() -> GeospatialParser:
    \"\"\"Get global geospatial parser.\"\"\"
    global _geospatial_parser
    if _geospatial_parser is None:
        _geospatial_parser = GeospatialParser()
    return _geospatial_parser
'''
with open('geospatial_parser.py', 'w') as f:
    f.write(content)
print('Fixed geospatial_parser.py')
