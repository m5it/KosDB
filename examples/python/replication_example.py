#!/usr/bin/env python3
"""
LevelDB Python Client - Replication Example

This example demonstrates working with replication features.
"""

import time
from leveldb_client import LevelDBClient, connect


def main():
    print("=" * 60)
    print("LevelDB Python Client - Replication Example")
    print("=" * 60)
    
    try:
        # Connect to master
        print("\n--- Connecting to MASTER ---\n")
        master = LevelDBClient('localhost', 9999)
        master.connect()
        master.auth('admin', 'admin')
        print("Connected to master!")
        
        # Create replication user on master
        print("\nCreating replication user on master...")
        try:
            result = master.create_replication_user('repl', 'replpass')
            print(result)
        except Exception as e:
            print(f"Note: {e}")  # User might already exist
        
        # Show master status
        print("\n" + "=" * 60)
        print("Master Status:")
        print("=" * 60)
        print(master.show_master_status())
        
        # Create test database on master
        print("\n" + "=" * 60)
        print("Creating test database on master...")
        print("=" * 60)
        print(master.create_database('replication_test'))
        print(master.use('replication_test'))
        print(master.create_table('sync_data', [
            'id INT PRIMARY KEY',
            'message TEXT',
            'timestamp TEXT',
            'server_id INT'
        ]))
        
        # Connect to slave
        print("\n--- Connecting to SLAVE ---\n")
        slave = LevelDBClient('localhost', 9998)  # Different port
        slave.connect()
        slave.auth('admin', 'admin')
        print("Connected to slave!")
        
        # Show slave status
        print("\n" + "=" * 60)
        print("Slave Status:")
        print("=" * 60)
        print(slave.show_slave_status())
        
        # Insert data on master
        print("\n" + "=" * 60)
        print("Inserting data on MASTER...")
        print("=" * 60)
        import datetime
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        print(master.insert('sync_data', [
            1, 'Hello from master!', timestamp, 1
        ]))
        print(master.insert('sync_data', [
            2, 'This will replicate to slave', timestamp, 1
        ]))
        
        # Wait for replication
        print("\nWaiting 3 seconds for replication...")
        time.sleep(3)
        
        # Check data on slave
        print("\n" + "=" * 60)
        print("Checking data on SLAVE:")
        print("=" * 60)
        slave.use('replication_test')
        data = slave.select('sync_data')
        
        if data:
            for row in data:
                print(f"  ID: {row['id']}, Message: {row['message']}, "
                      f"Time: {row['timestamp']}")
        else:
            print("  No data yet (replication might still be in progress)")
        
        # Insert more data
        print("\n" + "=" * 60)
        print("Inserting more data on master...")
        print("=" * 60)
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(master.insert('sync_data', [
            3, 'Replication is working!', timestamp, 1
        ]))
        
        # Wait again
        print("\nWaiting 3 seconds for replication...")
        time.sleep(3)
        
        # Check all data on slave
        print("\n" + "=" * 60)
        print("All data on SLAVE:")
        print("=" * 60)
        data = slave.select('sync_data', order_by='id')
        for row in data:
            print(f"  [{row['id']}] {row['message']}")
        
        # Demonstrate conflict handling (master-master scenario)
        print("\n" + "=" * 60)
        print("Demonstrating bi-directional sync...")
        print("=" * 60)
        
        # In master-master, both can write
        # (Note: This requires --peer-host setup on both servers)
        print("In master-master replication, both servers can accept writes.")
        print("Each server filters out its own entries to prevent loops.")
        
        # Clean up
        print("\n" + "=" * 60)
        print("Cleaning up...")
        print("=" * 60)
        print(master.drop_table('sync_data'))
        print(master.drop_database('replication_test'))
        
        # Close connections
        master.close()
        slave.close()
        
        print("\n" + "=" * 60)
        print("Replication test completed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())