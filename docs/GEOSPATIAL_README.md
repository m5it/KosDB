# Geospatial Indexing for KosDB

R-tree based spatial indexing with support for POINT, POLYGON, and CIRCLE geometry types.

## Features

- **R-Tree Index**: Efficient spatial indexing
- **Geometry Types**: Point, Circle, Polygon
- **Spatial Queries**: NEAR, WITHIN, INTERSECTS, BOUNDING_BOX
- **Geohash Support**: Efficient encoding for range queries
- **Haversine Distance**: Accurate Earth-surface distance calculation

## Geometry Types

| Type | Description | Example |
|------|-------------|---------|
| **POINT** | Latitude/Longitude coordinate | `40.7128, -74.0060` |
| **CIRCLE** | Center point + radius | `40.7128, -74.0060, 1000m` |
| **POLYGON** | Multi-point boundary | Triangle, rectangle, complex shapes |

## SQL Commands

### Create Spatial Index
```sql
CREATE SPATIAL INDEX ON locations (coordinates)
```

### Drop Spatial Index
```sql
DROP SPATIAL INDEX ON locations
```

### Find Nearby Locations
```sql
NEAR locations LAT 40.7128 LON -74.0060 RADIUS 5000 UNIT meters
```

### Find Within Geometry
```sql
-- Within circle
WITHIN locations CIRCLE 40.7128 -74.0060 5000

-- Within polygon
WITHIN locations POLYGON (40.7,-74.0),(40.8,-74.0),(40.8,-73.9),(40.7,-73.9)
```

### Find Intersecting
```sql
INTERSECTS locations BBOX 40.7 -74.1 40.8 -73.9
```

### Bounding Box Search
```sql
BOUNDING_BOX locations 40.7 -74.1 40.8 -73.9
```

### Insert Spatial Data
```sql
SPATIAL INSERT locations store_001 40.7128 -74.0060
```

### Calculate Distance
```sql
DISTANCE 40.7128 -74.0060 51.5074 -0.1278
```

### Geohash Operations
```sql
-- Encode coordinates
GEOHASH ENCODE 40.7128 -74.0060 PRECISION 8

-- Get neighbors
GEOHASH NEIGHBORS dr5r9x8
```

## Location-Based Services Example

```python
from geospatial import RTreeIndex, PointGeometry, CircleGeometry
from geospatial_commands import get_spatial_manager

# Initialize spatial manager
manager = get_spatial_manager()

# Create index for stores
index = manager.create_index(\"stores\")

# Add store locations
index.insert(\"store_001\", PointGeometry(40.7128, -74.0060), 
             {\"name\": \"NYC Flagship\", \"category\": \"electronics\"})
index.insert(\"store_002\", PointGeometry(40.7282, -74.0776), 
             {\"name\": \"Jersey City\", \"category\": \"home\"})
index.insert(\"store_003\", PointGeometry(40.6782, -73.9442), 
             {\"name\": \"Brooklyn\", \"category\": \"clothing\"})
index.insert(\"store_004\", PointGeometry(34.0522, -118.2437), 
             {\"name\": \"LA\", \"category\": \"electronics\"})

# Find stores within 10km of NYC
nearby = index.near(Point(40.7128, -74.0060), 10000)
for store_id, distance, data in nearby:
    print(f\"{data['name']}: {distance/1000:.1f}km away\")

# Find stores in delivery zone (circle)
delivery_zone = CircleGeometry(40.7128, -74.0060, 15000)  # 15km radius
stores_in_zone = index.within(delivery_zone)
for store_id, geom, data in stores_in_zone:
    print(f\"{data['name']} is in delivery zone\")

# Get statistics
stats = index.get_stats()
print(f\"Total stores indexed: {stats['total_objects']}\")
```

## API Reference

### RTreeIndex

```python
from geospatial import RTreeIndex, PointGeometry

index = RTreeIndex()

# Insert
index.insert(\"id\", PointGeometry(lat, lon), data)

# Search by bounding box
results = index.search(bbox)

# Find nearby
results = index.near(Point(lat, lon), radius_meters)

# Find within geometry
results = index.within(geometry)

# Find intersecting
results = index.intersects(geometry)
```

### Geohash

```python
from geospatial import geohash_encode, geohash_decode, geohash_neighbors

# Encode
geohash = geohash_encode(40.7128, -74.0060, precision=8)

# Decode to bbox
min_lat, min_lon, max_lat, max_lon = geohash_decode(geohash)

# Get neighbors
neighbors = geohash_neighbors(geohash)
```

### Distance

```python
from geospatial import haversine_distance, Point

# Calculate distance in meters
dist = haversine_distance(Point(lat1, lon1), Point(lat2, lon2))
```

## Configuration

```json
{
    \"geospatial\": {
        \"default_index_type\": \"rtree\",
        \"max_entries_per_node\": 8,
n        \"enable_geohash_index\": true\n    }\n}\n```\n\n## Testing\n\n```bash\npython test_geospatial.py\n```\n\nAll 21 tests passing ✓\n