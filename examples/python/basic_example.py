#!/usr/bin/env python3
"""
LevelDB Python Client - Basic Usage Example

This example demonstrates basic CRUD operations using the LevelDBClient.
"""

from leveldb_client import LevelDBClient, connect


def main():
    print("=" * 60)
    print("LevelDB Python Client - Basic Example")
    print("=" * 60)
    
    # Method 1: Using context manager (recommended)
    print("\n--- Method 1: Context Manager ---\n")
    
    try:
        with connect('localhost', 9999, 'admin', 'admin') as db:
            print("Connected and authenticated!\n")
            
            # Create database
            print("Creating database 'demo_app'...")
            print(db.create_database('demo_app'))
            
            # Use database
            print("\nSelecting database...")
            print(db.use('demo_app'))
            
            # Create table
            print("\nCreating table 'products'...")
            print(db.create_table('products', [
                'id INT PRIMARY KEY',
                'name TEXT',
                'category TEXT',
                'price FLOAT',
                'stock INT'
            ]))
            
            # Insert data
            print("\nInserting products...")
            print(db.insert('products', [1, 'Laptop', 'Electronics', 999.99, 50]))
            print(db.insert('products', [2, 'Mouse', 'Electronics', 29.99, 200]))
            print(db.insert('products', [3, 'Keyboard', 'Electronics', 79.99, 150]))
            print(db.insert('products', [4, 'Monitor', 'Electronics', 299.99, 30]))
            print(db.insert('products', [5, 'Desk Chair', 'Furniture', 199.99, 20]))
            
            # Select all
            print("\n" + "=" * 60)
            print("All Products:")
            print("=" * 60)
            products = db.select('products')
            for product in products:
                print(f"  ID: {product['id']}, Name: {product['name']}, "
                      f"Price: ${product['price']}, Stock: {product['stock']}")
            
            # Select with WHERE
            print("\n" + "=" * 60)
            print("Products under $100:")
            print("=" * 60)
            cheap_products = db.select('products', where='price<100')
            for product in cheap_products:
                print(f"  {product['name']}: ${product['price']}")
            
            # Select with ORDER BY
            print("\n" + "=" * 60)
            print("Products by price (highest first):")
            print("=" * 60)
            sorted_products = db.select('products', order_by='price', desc=True)
            for product in sorted_products:
                print(f"  {product['name']}: ${product['price']}")
            
            # Update
            print("\n" + "=" * 60)
            print("Updating product 1 (Laptop) price...")
            print("=" * 60)
            print(db.update('products', "price=899.99", "id=1"))
            
            # Verify update
            print("\nUpdated product:")
            updated = db.select('products', where='id=1')
            if updated:
                print(f"  {updated[0]['name']}: ${updated[0]['price']}")
            
            # Delete
            print("\n" + "=" * 60)
            print("Deleting product 5...")
            print("=" * 60)
            print(db.delete('products', 'id=5'))
            
            # Remaining products
            print("\nRemaining products:")
            remaining = db.select('products')
            for product in remaining:
                print(f"  {product['name']}")
            
            # List databases and tables
            print("\n" + "=" * 60)
            print("Databases:", db.list_databases())
            print("Tables:", db.list_tables())
            
            # Clean up
            print("\n" + "=" * 60)
            print("Cleaning up...")
            print("=" * 60)
            print(db.drop_table('products'))
            print(db.drop_database('demo_app'))
            
    except Exception as e:
        print(f"\nError: {e}")
        return 1
    
    # Method 2: Direct usage
    print("\n--- Method 2: Direct Usage ---\n")
    
    try:
        client = LevelDBClient('localhost', 9999)
        client.connect()
        client.auth('admin', 'admin')
        print("Connected successfully!")
        
        # Simple query
        result = client.execute("SHOW DATABASES")
        print(f"\nDatabases:\n{result}")
        
        client.close()
        print("\nConnection closed.")
        
    except Exception as e:
        print(f"\nError: {e}")
        return 1
    
    print("\n" + "=" * 60)
    print("Example completed successfully!")
    print("=" * 60)
    return 0


if __name__ == '__main__':
    exit(main())