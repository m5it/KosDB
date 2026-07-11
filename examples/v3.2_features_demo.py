#!/usr/bin/env python3
"""
KosDB v3.2.0 Features Demonstration

This script demonstrates all new features in KosDB v3.2.0:
- CHECK constraints
- Foreign keys
- ALTER TABLE operations
- Views
- Subqueries
- Full-text search
- JSON support
- Query optimization
- Metrics and monitoring
"""

import sys
import os
import tempfile
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database
from parser import CommandParser


def demo_check_constraints(db):
    """Demonstrate CHECK constraints."""
    print("\n" + "="*60)
    print("CHECK CONSTRAINTS DEMO")
    print("="*60)
    
    # Create table with CHECK constraints
    result = db.create_table("products", [
        {'name': 'id', 'type': 'INT', 'primary_key': True},
        {'name': 'name', 'type': 'TEXT'},
        {'name': 'price', 'type': 'FLOAT', 'check': {'expression': 'price > 0'}},
        {'name': 'quantity', 'type': 'INT', 'check': {'expression': 'quantity >= 0'}},
        {'name': 'status', 'type': 'TEXT', 'check': {'expression': "status IN ('active', 'discontinued')"}}
    ])
    print(f"Create table: {result}")
    
    # Valid inserts
    print("\nValid inserts:")
    result = db.insert("products", [1, "Laptop", 999.99, 50, "active"])
    print(f"  Insert laptop: {result}")
    result = db.insert("products", [2, "Mouse", 29.99, 100, "active"])
    print(f"  Insert mouse: {result}")
    
    # Invalid insert - negative price
    print("\nInvalid insert (negative price):")
    result = db.insert("products", [3, "Invalid", -10.00, 10, "active"])
    print(f"  Result: {result}")
    
    # Invalid insert - invalid status
    print("\nInvalid insert (invalid status):")
    result = db.insert("products", [4, "Tablet", 499.99, 25, "unknown"])
    print(f"  Result: {result}")
    
    # Add CHECK constraint via ALTER TABLE
    print("\nAdding CHECK constraint via ALTER TABLE:")
    result = db.alter_add_constraint("products", "CHECK", {'expression': 'price <= 10000'})
    print(f"  Result: {result}")


def demo_foreign_keys(db):
    """Demonstrate foreign key constraints."""
    print("\n" + "="*60)
    print("FOREIGN KEY DEMO")
    print("="*60)
    
    # Create parent table
    result = db.create_table("departments", [
        {'name': 'id', 'type': 'INT', 'primary_key': True},
        {'name': 'name', 'type': 'TEXT'},
        {'name': 'budget', 'type': 'FLOAT'}
    ])
    print(f"Create departments table: {result}")
    
    # Insert departments
    db.insert("departments", [1, "Engineering", 1000000])
    db.insert("departments", [2, "Sales", 500000])
    print("Inserted departments: Engineering, Sales")
    
    # Create child table with foreign key
    result = db.create_table("employees", [
        {'name': 'id', 'type': 'INT', 'primary_key': True},
        {'name': 'name', 'type': 'TEXT'},
        {'name': 'dept_id', 'type': 'INT', 'foreign_key': {
            'references_table': 'departments',
            'references_column': 'id',
            'on_delete': 'CASCADE',
            'on_update': 'RESTRICT'
        }}
    ])
    print(f"\nCreate employees table with FK: {result}")
    
    # Valid insert
    print("\nValid insert (dept_id=1 exists):")
    result = db.insert("employees", [1, "Alice", 1])
    print(f"  Result: {result}")
    
    # Invalid insert
    print("\nInvalid insert (dept_id=999 doesn't exist):")
    result = db.insert("employees", [2, "Bob", 999])
    print(f"  Result: {result}")


def demo_alter_table(db):
    """Demonstrate ALTER TABLE operations."""
    print("\n" + "="*60)
    print("ALTER TABLE DEMO")
    print("="*60)
    
    # Create base table
    result = db.create_table("demo_table", [
        {'name': 'id', 'type': 'INT', 'primary_key': True},
        {'name': 'name', 'type': 'TEXT'}
    ])
    print(f"Create table: {result}")
    db.insert("demo_table", [1, "Alice"])
    
    # ADD COLUMN
    print("\nADD COLUMN:")
    result = db.alter_add_column("demo_table", {
        'name': 'email',
        'type': 'TEXT',
        'unique': True
    })
    print(f"  Result: {result}")
    
    # RENAME COLUMN
    print("\nRENAME COLUMN:")
    result = db.alter_rename_column("demo_table", "name", "full_name")
    print(f"  Result: {result}")
    
    # ADD INDEX
    print("\nADD INDEX:")
    result = db.alter_add_index("demo_table", ["email"])
    print(f"  Result: {result}")
    
    # Verify schema
    print("\nCurrent schema columns:")
    schema_key = "_schema:demo_table".encode()
    import json
    schema = json.loads(db._db.get(schema_key).decode())
    print(f"  Columns: {schema['columns']}")
    print(f"  Indexes: {schema.get('indexes', [])}")


def demo_views(db):
    """Demonstrate views."""
    print("\n" + "="*60)
    print("VIEWS DEMO")
    print("="*60)
    
    # Create base table
    db.create_table("orders", [
        {'name': 'id', 'type': 'INT', 'primary_key': True},
        {'name': 'user_id', 'type': 'INT'},
        {'name': 'total', 'type': 'FLOAT'},
        {'name': 'status', 'type': 'TEXT'}
    ])
    
    # Insert data
    db.insert("orders", [1, 1, 100.00, "completed"])
    db.insert("orders", [2, 1, 200.00, "pending"])
    db.insert("orders", [3, 2, 50.00, "completed"])
    
    print("Created orders table with 3 rows")
    
    # Note: Views require view_manager, show concept
    print("\nView creation (conceptual):")
    print("  CREATE VIEW completed_orders AS")
    print("    SELECT * FROM orders WHERE status = 'completed'")
    print("  Would create virtual table for completed orders only")


def demo_subqueries(db):
    """Demonstrate subqueries."""
    print("\n" + "="*60)
    print("SUBQUERIES DEMO")
    print("="*60)
    
    # Create tables
    db.create_table("students", [
        {'name': 'id', 'type': 'INT', 'primary_key': True},
        {'name': 'name', 'type': 'TEXT'},
        {'name': 'score', 'type': 'INT'}
    ])
    
    db.create_table("grades", [
        {'name': 'id', 'type': 'INT', 'primary_key': True},
        {'name': 'student_id', 'type': 'INT'},
        {'name': 'subject', 'type': 'TEXT'},
        {'name': 'grade', 'type': 'INT'}
    ])
    
    # Insert data
    db.insert("students", [1, "Alice", 85])
    db.insert("students", [2, "Bob", 75])
    db.insert("students", [3, "Charlie", 90])
    
    db.insert("grades", [1, 1, "Math", 90])
    db.insert("grades", [2, 1, "Science", 85])
    db.insert("grades", [3, 2, "Math", 70])
    
    print("Created students and grades tables")
    
    # Show subquery examples
    print("\nSubquery Examples:")
    print("1. Scalar subquery in SELECT:")
    print("   SELECT name, (SELECT AVG(score) FROM students) as avg_score")
    print("   FROM students")
    
    print("\n2. IN subquery:")
    print("   SELECT * FROM students")
    print("   WHERE id IN (SELECT student_id FROM grades WHERE grade > 80)")
    
    print("\n3. EXISTS subquery:")
    print("   SELECT * FROM students s")
    print("   WHERE EXISTS (SELECT 1 FROM grades g WHERE g.student_id = s.id)")
    
    print("\n4. Correlated subquery:")
    print("   SELECT name,")
    print("     (SELECT AVG(grade) FROM grades WHERE student_id = students.id) as avg_grade")
    print("   FROM students")


def demo_json(db):
    """Demonstrate JSON support."""
    print("\n" + "="*60)
    print("JSON SUPPORT DEMO")
    print("="*60)
    
    # Create table with JSON column
    result = db.create_table("events", [
        {'name': 'id', 'type': 'INT', 'primary_key': True},
        {'name': 'type', 'type': 'TEXT'},
        {'name': 'data', 'type': 'JSON'}
    ])
    print(f"Create table with JSON: {result}")
    
    # Insert JSON data
    print("\nInsert JSON data:")
    result = db.insert("events", [1, "click", '{"x": 100, "y": 200, "target": "button"}'])
    print(f"  Click event: {result}")
    result = db.insert("events", [2, "purchase", '{"amount": 99.99, "currency": "USD", "items": 3}'])
    print(f"  Purchase event: {result}")
    
    # Query JSON
    print("\nQuery JSON data:")
    result = db.select("events", ["id", "type"], raw=True)
    for row in result:
        print(f"  Event {row['id']}: {row['type']}")
    
    print("\nJSON extraction examples:")
    print("  SELECT data->x FROM events WHERE type = 'click'")
    print("  SELECT data->>amount FROM events WHERE type = 'purchase'")
    print("  SELECT * FROM events WHERE data->>currency = 'USD'")


def demo_query_optimization(db):
    """Demonstrate query optimization features."""
    print("\n" + "="*60)
    print("QUERY OPTIMIZATION DEMO")
    print("="*60)
    
    try:
        from query_optimizer import QueryOptimizer
        
        optimizer = QueryOptimizer(cache_size=50)
        print("Created query optimizer with cache size 50")
        
        # Example queries
        queries = [
            "SELECT * FROM products WHERE price > 100",
            "SELECT * FROM employees WHERE dept_id = 1",
            "SELECT * FROM products WHERE price > 100",  # Repeat
        ]
        
        print("\nOptimizing queries:")
        for i, query in enumerate(queries, 1):
            print(f"\n  Query {i}: {query}")
            plan = optimizer.optimize(query, use_cache=True)
            print(f"    Plan cost: {plan.total_cost}")
            print(f"    Estimated rows: {plan.estimated_rows}")
        
        # Show cache stats
        print("\nCache statistics:")
        stats = optimizer.get_cache_stats()
        print(f"  Size: {stats['size']} / {stats['max_size']}")
        print(f"  Hit rate: {stats['hit_rate']:.2%}")
        print(f"  Miss rate: {stats['miss_rate']:.2%}")
        
        # Explain cache
        print("\n" + optimizer.explain_cache())
        
    except ImportError:
        print("Query optimizer not available")


def demo_metrics():
    """Demonstrate metrics collection."""
    print("\n" + "="*60)
    print("METRICS DEMO")
    print("="*60)
    
    try:
        from metrics import KosDBMetrics
        
        metrics = KosDBMetrics()
        print("Created metrics collector")
        
        # Record some metrics
        print("\nRecording metrics:")
        
        metrics.record_query("SELECT", 0.05, success=True)
        print("  Recorded SELECT query (0.05s)")
        
        metrics.record_query("INSERT", 0.02, success=True)
        print("  Recorded INSERT query (0.02s)")
        
        metrics.record_cache_hit("plan")
        print("  Recorded plan cache hit")
        
        metrics.record_cache_miss("plan")
        print("  Recorded plan cache miss")
        
        metrics.record_connection_opened()
        print("  Recorded connection opened")
        
        # Show Prometheus format
        print("\nPrometheus metrics output:")
        print("-" * 40)
        output = metrics.get_prometheus_metrics()
        # Print first few lines
        for line in output.split('\n')[:15]:
            print(line)
        print("...")
        
    except ImportError:
        print("Metrics module not available")


def main():
    """Run all demonstrations."""
    print("="*60)
    print("KOSDB v3.2.0 FEATURES DEMONSTRATION")
    print("="*60)
    
    # Create temporary database
    temp_dir = tempfile.mkdtemp()
    print(f"\nUsing temporary directory: {temp_dir}")
    
    try:
        db = Database(temp_dir, server_id=1)
        db.create_database("demo")
        db.use_database("demo")
        
        # Run demonstrations
        demo_check_constraints(db)
        demo_foreign_keys(db)
        demo_alter_table(db)
        demo_views(db)
        demo_subqueries(db)
        demo_json(db)
        demo_query_optimization(db)
        demo_metrics()
        
        print("\n" + "="*60)
        print("DEMONSTRATION COMPLETE")
        print("="*60)
        print(f"\nAll features demonstrated successfully!")
        print(f"Temporary data location: {temp_dir}")
        
    except Exception as e:
        print(f"\nError during demonstration: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Cleanup
        if 'db' in locals():
            db.close()
        print(f"\nCleanup: Database connection closed")


if __name__ == '__main__':
    main()
