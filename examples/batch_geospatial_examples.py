
"""
Batch Geospatial Operations Examples

Demonstrates batch geospatial operations for various use cases:
- Store locator
- Delivery optimization
- Service area analysis
- Real-time tracking
"""

import time
import random
from typing import List, Tuple, Dict, Any

# Mock geospatial imports for standalone execution
class MockSpatialIndex:
    """Mock spatial index for standalone examples."""
    def __init__(self):
        self.points = {}
    
    def insert(self, pid, lat, lon, meta=None):
        self.points[pid] = {'lat': lat, 'lon': lon, 'meta': meta or {}}
        return True
    
    def radius_search(self, lat, lon, radius, limit=10):
        """Return points sorted by distance (simplified)."""
        results = []
        for k, v in self.points.items():
            dist = ((v['lat'] - lat)**2 + (v['lon'] - lon)**2)**0.5 * 111000
            results.append((k, dist))
        results.sort(key=lambda x: x[1])
        return results[:limit]
    
    def nearest_neighbors(self, lat, lon, k=5):
        """Return k nearest neighbors."""
        results = []
        for point_id, data in self.points.items():
            dist = ((data['lat'] - lat)**2 + (data['lon'] - lon)**2)**0.5 * 111000
            results.append((point_id, dist))
        results.sort(key=lambda x: x[1])
        return results[:k]
    
    def bbox_search(self, bbox):
        """Return points within bounding box."""
        results = []
        for point_id, data in self.points.items():
            if (bbox.min_lat <= data['lat'] <= bbox.max_lat and
                bbox.min_lon <= data['lon'] <= bbox.max_lon):
                results.append(point_id)
        return results


class MockBoundingBox:
    def __init__(self, min_lat, min_lon, max_lat, max_lon):
        self.min_lat = min_lat
        self.min_lon = min_lon
        self.max_lat = max_lat
        self.max_lon = max_lon


# Try to import real modules, fall back to mocks
try:
    from geospatial import SpatialIndex, BoundingBox
except ImportError:
    print("Warning: geospatial module not available, using mocks")
    SpatialIndex = MockSpatialIndex
    BoundingBox = MockBoundingBox

from batch_geospatial import BatchGeospatialManager


def example_store_locator():
    """
    Example: Find nearby stores for multiple users.
    """
    print("\n=== Store Locator Example ===\n")
    
    index = SpatialIndex()
    manager = BatchGeospatialManager(index)
    
    # Add store locations
    stores = [
        ('store_nyc_1', 40.7128, -74.0060, {'name': 'NYC Downtown', 'category': 'retail'}),
        ('store_nyc_2', 40.7589, -73.9851, {'name': 'NYC Midtown', 'category': 'retail'}),
        ('store_la_1', 34.0522, -118.2437, {'name': 'LA Downtown', 'category': 'retail'}),
        ('store_la_2', 34.0407, -118.2468, {'name': 'LA Arts District', 'category': 'retail'}),
        ('store_chi_1', 41.8781, -87.6298, {'name': 'Chicago Loop', 'category': 'retail'}),
        ('store_chi_2', 41.9484, -87.6553, {'name': 'Chicago Lincoln Park', 'category': 'retail'}),
    ]
    
    result = manager.batch_geo_add(stores)
    print(f"Added {result.added} stores in {result.elapsed_ms:.2f}ms")
    
    # Multiple users searching for stores
    user_searches = [
        ('user_nyc_1', 40.7128, -74.0060, 5000),
        ('user_nyc_2', 40.7589, -73.9851, 3000),
        ('user_la_1', 34.0522, -118.2437, 10000),
        ('user_chi_1', 41.8781, -87.6298, 8000),
    ]
    
    print("\nBatch radius search results:")
    results = manager.batch_radius_search(user_searches, k=3)
    
    for result in results:
        print(f"\n  User {result.center_id}:")
        print(f"    Location: ({result.center[0]:.4f}, {result.center[1]:.4f})")
        print(f"    Radius: {result.radius_meters}m")
        print(f"    Found {len(result.results)} stores:")
        for store_id, distance in result.results:
            print(f"      - {store_id}: {distance:.1f}m")


def example_delivery_optimization():
    """
    Example: Assign nearest delivery riders to orders.
    """
    print("\n=== Delivery Optimization Example ===\n")
    
    index = SpatialIndex()
    manager = BatchGeospatialManager(index)
    
    # Index available riders
    riders = [
        (f'rider_{i}', 
         40.7 + random.uniform(-0.1, 0.1), 
         -74.0 + random.uniform(-0.1, 0.1),
         {'status': 'available', 'rating': 4.5 + random.random()})
        for i in range(20)
    ]
    
    result = manager.batch_geo_add(riders)
    print(f"Indexed {result.added} riders")
    
    # Multiple pickup locations
    orders = [
        (f'order_{i}',
         40.7 + random.uniform(-0.05, 0.05),
         -74.0 + random.uniform(-0.05, 0.05))
        for i in range(10)
    ]
    
    print(f"\nFinding nearest riders for {len(orders)} orders...")
    
    results = manager.batch_nearest_neighbor(orders, k=3)
    
    for result in results:
        print(f"\n  Order {result.query_id}:")
        print(f"    Pickup: ({result.query_point[0]:.4f}, {result.query_point[1]:.4f})")
        print(f"    Top 3 nearest riders:")
        for i, (rider_id, distance) in enumerate(result.neighbors[:3], 1):
            print(f"      {i}. {rider_id}: {distance:.1f}m")


def example_service_area_analysis():
    """
    Example: Analyze service coverage across multiple regions.
    """
    print("\n=== Service Area Analysis Example ===\n")
    
    index = SpatialIndex()
    manager = BatchGeospatialManager(index)
    
    # Add customer locations
    customers = [
        (f'customer_{i}',
         34.0 + random.uniform(0, 2),
         -119.0 + random.uniform(0, 2),
         {'plan': random.choice(['basic', 'premium'])})
        for i in range(100)
    ]
    
    result = manager.batch_geo_add(customers)
    print(f"Indexed {result.added} customers")
    
    # Define service areas
    service_areas = [
        ('downtown_la', BoundingBox(34.0, -118.5, 34.1, -118.2)),
        ('hollywood', BoundingBox(34.0, -118.4, 34.15, -118.2)),
        ('santa_monica', BoundingBox(34.0, -118.6, 34.05, -118.4)),
        ('pasadena', BoundingBox(34.1, -118.2, 34.2, -118.0)),
    ]
    
    print("\nAnalyzing service coverage...")
    
    results = manager.batch_bbox_query(service_areas)
    
    total_customers = 0
    for result in results:
        coverage = len(result.results)
        total_customers += coverage
        print(f"\n  {result.query_id}:")
        print(f"    Bounding Box: "
              f"({result.bbox.min_lat:.2f}, {result.bbox.min_lon:.2f}) to "
              f"({result.bbox.max_lat:.2f}, {result.bbox.max_lon:.2f})")
        print(f"    Customers covered: {coverage}")
        print(f"    Query time: {result.elapsed_ms:.2f}ms")
    
    print(f"\nTotal customers analyzed: {total_customers}")


def example_real_time_tracking():
    """
    Example: Real-time asset tracking with batch updates.
    """
    print("\n=== Real-Time Tracking Example ===\n")
    
    index = SpatialIndex()
    manager = BatchGeospatialManager(index)
    
    # Simulate fleet of vehicles
    num_vehicles = 50
    vehicles = [
        (f'vehicle_{i}',
         37.7749 + random.uniform(-0.5, 0.5),
         -122.4194 + random.uniform(-0.5, 0.5),
         {'type': 'delivery_van', 'status': 'active'})
        for i in range(num_vehicles)
    ]
    
    result = manager.batch_geo_add(vehicles)
    print(f"Indexed {result.added} vehicles")
    
    # Simulate position updates
    print("\nSimulating real-time position updates...")
    
    num_updates = 5
    for update_round in range(num_updates):
        updates = [
            (f'vehicle_{i}',
             37.7749 + random.uniform(-0.5, 0.5),
             -122.4194 + random.uniform(-0.5, 0.5),
             {'type': 'delivery_van', 'status': 'active', 'update_round': update_round})
            for i in range(num_vehicles)
        ]
        
        start = time.time()
        result = manager.batch_geo_add(updates)
        elapsed = (time.time() - start) * 1000
        
        print(f"  Update {update_round + 1}: {result.added} positions in {elapsed:.2f}ms "
              f"({result.added/elapsed*1000:.0f} updates/sec)")
    
    # Batch query for dispatch center
    dispatch_centers = [
        ('dispatch_north', 37.8, -122.4, 10000),
        ('dispatch_south', 37.7, -122.5, 10000),
        ('dispatch_east', 37.75, -122.3, 10000),
    ]
    
    print("\nDispatch center vehicle queries:")
    results = manager.batch_radius_search(dispatch_centers, k=10)
    
    for result in results:
        print(f"  {result.center_id}: {len(result.results)} vehicles nearby")


def example_performance_comparison():
    """
    Compare batch vs individual operations.
    """
    print("\n=== Performance Comparison ===\n")
    
    num_points = 1000
    
    print(f"Inserting {num_points} points...")
    
    index1 = SpatialIndex()
    manager1 = BatchGeospatialManager(index1)
    
    points = [
        (f'point_{i}',
         random.uniform(30, 50),
         random.uniform(-120, -70),
         {'index': i})
        for i in range(num_points)
    ]
    
    # Individual inserts
    start = time.time()
    for point in points:
        manager1.batch_geo_add([point])
    individual_time = (time.time() - start) * 1000
    
    print(f"  Individual inserts: {individual_time:.2f}ms")
    
    # Batch insert
    index2 = SpatialIndex()
    manager2 = BatchGeospatialManager(index2)
    
    start = time.time()
    result = manager2.batch_geo_add(points)
    batch_time = (time.time() - start) * 1000
    
    print(f"  Batch insert: {batch_time:.2f}ms")
    print(f"  Speedup: {individual_time/batch_time:.1f}x")
    
    # Test 2: Individual vs batch queries
    print(f"\nQuerying {num_points} queries...")
    
    num_queries = 100
    queries = [
        (f'q_{i}',
         random.uniform(30, 50),
         random.uniform(-120, -70))
        for i in range(num_queries)
    ]
    
    # Individual queries
    start = time.time()
    for qid, lat, lon in queries:
        manager2.batch_nearest_neighbor([(qid, lat, lon)], k=5)
    individual_query_time = (time.time() - start) * 1000
    
    # Batch queries
    start = time.time()
    manager2.batch_nearest_neighbor(queries, k=5)
    batch_query_time = (time.time() - start) * 1000
    
    print(f"  Individual queries: {individual_query_time:.2f}ms")
    print(f"  Batch queries: {batch_query_time:.2f}ms")
    if batch_query_time > 0:
        print(f"  Speedup: {individual_query_time/batch_query_time:.1f}x")
    else:
        print(f"  Batch queries completed in <1ms")


def run_all_examples():
    """Run all batch geospatial examples."""
    examples = [
        example_store_locator,
        example_delivery_optimization,
        example_service_area_analysis,
        example_real_time_tracking,
        example_performance_comparison,
    ]
    
    for example in examples:
        try:
            example()
        except Exception as e:
            print(f"\nError in {example.__name__}: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*50)
    print("All examples completed!")
    print("="*50)


if __name__ == '__main__':
    run_all_examples()
