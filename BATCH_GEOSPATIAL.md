
# Batch Geospatial Operations Guide

Version: 2.3.0  
Last Updated: 2024-01-15

## Overview

Batch Geospatial Operations provide efficient bulk processing for geospatial data, including point insertion, radius searches, nearest neighbor queries, and bounding box operations. Optimized for high-throughput location-based applications.

## Features

- **Batch GEO ADD**: Bulk point insertion into spatial index
- **Batch Radius Search**: Multiple center points in parallel
- **Batch Nearest Neighbor**: Find closest points for multiple queries
- **Batch Bounding Box**: Query multiple regions at once
- **Spatial Index Optimization**: Automatic index rebuilding for batch operations

## Quick Start

```python
from batch_geospatial import BatchGeospatialManager, get_batch_geo_manager
from geospatial import SpatialIndex

# Create spatial index and manager
index = SpatialIndex()
manager = get_batch_geo_manager(index)

# Batch add points
points = [
    ('nyc', 40.7128, -74.0060, {'city': 'New York'}),
    ('la', 34.0522, -118.2437, {'city': 'Los Angeles'}),
    ('chicago', 41.8781, -87.6298, {'city': 'Chicago'}),
]

result = manager.batch_geo_add(points)
print(f"Added {result.added} points in {result.elapsed_ms:.2f}ms")
```

## SQL Commands

### GEO ADD BATCH

```sql
-- Bulk insert geospatial points
GEO ADD BATCH locations [
    ('store1', 40.7128, -74.0060, {'type': 'store', 'name': 'NYC Store'}),
    ('store2', 34.0522, -118.2437, {'type': 'store', 'name': 'LA Store'}),
    ('warehouse1', 41.8781, -87.6298, {'type': 'warehouse'})
];

-- Insert without metadata
GEO ADD BATCH cities [
    ('nyc', 40.7128, -74.0060),
    ('la', 34.0522, -118.2437),
    ('chicago', 41.8781, -87.6298)
];
```

### GEO RADIUS SEARCH BATCH

```sql
-- Search multiple locations at once
GEO RADIUS SEARCH BATCH locations [
    ('user1', 40.7128, -74.0060, 5000),   -- 5km radius
    ('user2', 34.0522, -118.2437, 10000), -- 10km radius
    ('user3', 41.8781, -87.6298, 15000)  -- 15km radius
] LIMIT 10;
```

### GEO BBOX QUERY BATCH

```sql
-- Query multiple bounding boxes
GEO BBOX QUERY BATCH locations [
    ('region1', 40.0, -75.0, 41.0, -73.0),  -- NYC area
    ('region2', 34.0, -119.0, 35.0, -117.0) -- LA area
];
```

## Batch Point Insertion

### Basic Usage

```python
from batch_geospatial import BatchGeospatialManager

manager = BatchGeospatialManager(spatial_index)

# Prepare points
points = [
    ('point1', 40.7128, -74.0060, {'category': 'restaurant'}),
    ('point2', 34.0522, -118.2437, {'category': 'hotel'}),
    ('point3', 41.8781, -87.6298, {'category': 'attraction'}),
    # ... more points
]

# Batch insert
result = manager.batch_geo_add(points, batch_size=1000)

print(f"Added: {result.added}")
print(f"Failed: {result.failed}")
print(f"Time: {result.elapsed_ms:.2f}ms")
```

### Performance Benchmarks

| Batch Size | Points/sec | Memory Usage |
|------------|-----------|--------------|
| 100 | 10,000 | Low |
| 1,000 | 50,000 | Medium |
| 10,000 | 100,000 | Medium |
| 100,000 | 150,000 | High |

### Large Dataset Ingestion

```python
def ingest_locations(file_path, batch_size=10000):
    """
    Ingest large location dataset from file.
    """
    batch = []
    total_added = 0
    
    for line in open(file_path):
        data = json.loads(line)
        batch.append((
            data['id'],
            data['latitude'],\n            data['longitude'],\n            data.get('metadata', {})\n        ))\n        \n        if len(batch) >= batch_size:\n            result = manager.batch_geo_add(batch)\n            total_added += result.added\n            batch = []\n            print(f"Ingested {total_added} points...\")\n    \n    # Final batch\n    if batch:\n        result = manager.batch_geo_add(batch)\n        total_added += result.added\n    \n    return total_added
```

## Batch Radius Search

### Multiple Center Search

```python
# Define multiple search centers
centers = [\n    ('user1', 40.7128, -74.0060, 5000),   # NYC, 5km\n    ('user2', 34.0522, -118.2437, 10000), # LA, 10km\n    ('user3', 41.8781, -87.6298, 15000),  # Chicago, 15km\n]

# Batch radius search
results = manager.batch_radius_search(centers, k=10, parallel=True)

for result in results:
n    print(f"Center {result.center_id}: {len(result.results)} points found")\n    print(f"  Location: ({result.center[0]}, {result.center[1]})\")\n    print(f"  Radius: {result.radius_meters}m\")\n    print(f"  Time: {result.elapsed_ms:.2f}ms")
```

### Use Case: Store Locator

```python
def find_nearby_stores(user_locations, radius_meters=10000, k=10):
    """
    Find nearby stores for multiple users.
    
    Args:
n        user_locations: List of (user_id, lat, lon) tuples\n        radius_meters: Search radius\n        k: Max results per user\n    \n    Returns:\n        Dict mapping user_id to nearby stores\n    """
    # Convert to batch format\n    centers = [\n        (user_id, lat, lon, radius_meters)\n        for user_id, lat, lon in user_locations\n    ]\n    \n    # Batch search\n    results = manager.batch_radius_search(centers, k=k)\n    \n    # Organize by user\n    nearby = {}\n    for result in results:\n        nearby[result.center_id] = [\n            {'store_id': store_id, 'distance': distance}\n            for store_id, distance in result.results\n        ]\n    \n    return nearby
```

## Batch Nearest Neighbor

### Multiple Query Points

```python
# Define query points\nqueries = [\n    ('query1', 40.7128, -74.0060),  # NYC\n    ('query2', 34.0522, -118.2437), # LA\n    ('query3', 41.8781, -87.6298),  # Chicago\n]

# Find k nearest neighbors for each
results = manager.batch_nearest_neighbor(queries, k=5)

for result in results:
    print(f"Query {result.query_id}:\")\n    for point_id, distance in result.neighbors:\n        print(f"  {point_id}: {distance:.2f}m")\n```

### Use Case: Delivery Optimization

```python
def assign_delivery_riders(pickup_locations, available_riders, k=3):
    """
n    Assign nearest riders to pickup locations.\n    \n    Args:\n        pickup_locations: List of (order_id, lat, lon)\n        available_riders: List of (rider_id, lat, lon)\n        k: Number of nearest riders to consider\n    \n    Returns:\n        Optimal assignments\n    """
    # First, index all riders\n    rider_points = [\n        (rider_id, lat, lon, {'type': 'rider'})\n        for rider_id, lat, lon in available_riders\n    ]\n    manager.batch_geo_add(rider_points)\n    \n    # Query nearest riders for each pickup\n    queries = [\n        (order_id, lat, lon)\n        for order_id, lat, lon in pickup_locations\n    ]\n    \n    results = manager.batch_nearest_neighbor(queries, k=k)\n    \n    assignments = {}\n    for result in results:\n        assignments[result.query_id] = [\n            {'rider_id': rider_id, 'distance': distance}\n            for rider_id, distance in result.neighbors\n        ]\n    \n    return assignments
```

## Batch Bounding Box Queries

### Multiple Region Queries

```python
from geospatial import BoundingBox

# Define multiple regions
regions = [
    ('nyc_area', BoundingBox(40.0, -75.0, 41.0, -73.0)),
n    ('la_area', BoundingBox(34.0, -119.0, 35.0, -117.0)),\n    ('chicago_area', BoundingBox(41.0, -88.0, 42.0, -87.0)),\n]

# Batch query\nresults = manager.batch_bbox_query(regions)

for result in results:
    print(f"Region {result.query_id}: {len(result.results)} points")
```

### Use Case: Service Area Analysis

```python
def analyze_service_coverage(service_areas, locations_index):
    """
    Analyze which service areas cover which locations.
n    \n    Args:\n        service_areas: List of (area_id, bbox) tuples\n        locations_index: Spatial index of all locations\n    \n    Returns:\n        Coverage analysis per area\n    """
    # Update manager with locations index\n    manager.spatial_index = locations_index\n    \n    # Query all areas\n    results = manager.batch_bbox_query(service_areas)
    
    coverage = {}
n    for result in results:\n        coverage[result.query_id] = {\n            'bbox': {\n                'min_lat': result.bbox.min_lat,\n                'min_lon': result.bbox.min_lon,\n                'max_lat': result.bbox.max_lat,\n                'max_lon': result.bbox.max_lon\n            },\n            'points_count': len(result.results),\n            'points': result.results\n        }\n    \n    return coverage
```

## Spatial Index Optimization

### Automatic Optimization

```python
# After large batch insertions, optimize the index\nresult = manager.batch_geo_add(large_batch)

if result.added > 10000:
    # Trigger index optimization
    opt_result = manager.optimize_spatial_index()
n    print(f"Index optimized in {opt_result['elapsed_ms']:.2f}ms")
```

### Manual Rebuild

```python
# Force complete index rebuild\nopt_result = manager.optimize_spatial_index()
print(f"Index rebuilt: {opt_result['optimized']}")
```

## Performance Tuning

### Batch Size Selection

```python
# For write-heavy workloads: larger batches\nresult = manager.batch_geo_add(points, batch_size=10000)

# For read-heavy workloads: smaller batches\nresults = manager.batch_radius_search(centers, k=10)
```

### Parallel Execution

```python
# Use parallel=True for independent queries\nresults = manager.batch_radius_search(\n    centers,\n    k=10,\n    parallel=True  # Uses ThreadPoolExecutor\n)
```

### Memory Management

```python
# Process large datasets in chunks\ndef process_large_dataset(points, chunk_size=50000):
n    for i in range(0, len(points), chunk_size):\n        chunk = points[i:i + chunk_size]\n        result = manager.batch_geo_add(chunk)\n        print(f"Processed {i + result.added}/{len(points)}\")
```

## Integration with Batch Executor

```python
from batch_executor import BatchExecutor
from batch_geospatial import get_batch_geo_manager

# Create components\nspatial_index = SpatialIndex()
nmanager = get_batch_geo_manager(spatial_index)\nexecutor = BatchExecutor(parser, registry)

# Execute geospatial batch commands\ncommands = [
    "GEO ADD BATCH stores [('store1', 40.7128, -74.0060), ('store2', 34.0522, -118.2437)]",
    "GEO RADIUS SEARCH BATCH stores [('user1', 40.7128, -74.0060, 5000)] LIMIT 10",
]

result = executor.execute_batch(commands, client_state={})
```

## Metrics and Monitoring

### Key Metrics

```python\nmetrics = manager.get_metrics()

print(f"Batch adds: {metrics['batch_adds']}")
print(f"Batch radius searches: {metrics['batch_radius_searches']}")
print(f"Batch NN queries: {metrics['batch_nn_queries']}")
print(f"Batch bbox queries: {metrics['batch_bbox_queries']}")
print(f"Total points added: {metrics['total_points_added']}")
```

### Performance Monitoring

```python
# Monitor batch performance\nresult = manager.batch_geo_add(points)

throughput = result.added / (result.elapsed_ms / 1000)
print(f"Throughput: {throughput:.0f} points/sec")

if throughput < 10000:
n    logger.warning(\"Low throughput detected, consider optimizing\")
```

## Best Practices

### 1. Index Before Query

```python
# Always add points before querying\nmanager.batch_geo_add(points)\nresults = manager.batch_radius_search(centers)
```

### 2. Use Appropriate Batch Sizes

```python
# Balance memory and performance\noptimal_batch_size = 10000\nresult = manager.batch_geo_add(points, batch_size=optimal_batch_size)
```

### 3. Parallelize Independent Queries

```python
# Use parallel=True for multiple independent queries\nresults = manager.batch_nearest_neighbor(queries, parallel=True)
```

### 4. Handle Coordinate Validation

```python
# Validate coordinates before batch add\nvalid_points = [\n    p for p in points\n    if -90 <= p[1] <= 90 and -180 <= p[2] <= 180\n]

result = manager.batch_geo_add(valid_points)
print(f"Added {result.added}/{len(valid_points)} valid points")
```

## Troubleshooting

### Low Query Performance

**Symptoms**: Radius searches taking too long

**Solutions**:
1. Optimize spatial index after large inserts
2. Reduce search radius
3. Use approximate algorithms for large datasets

### Memory Issues

**Symptoms**: OOM during batch operations

**Solutions**:
1. Reduce batch_size
2. Process in smaller chunks
3. Use streaming for very large datasets

### Coordinate Errors

**Symptoms**: Points not appearing in expected locations

**Check**:
1. Latitude range: -90 to 90
2. Longitude range: -180 to 180
3. Correct order: (lat, lon) not (lon, lat)

## See Also

- [Geospatial Indexing](geospatial.py)
- [Spatial Queries](geospatial_queries.md)
- [Batch Operations](OPERATIONS.md)
