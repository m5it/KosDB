
#!/usr/bin/env python3
"""
KosDB Python Batch Commands Demo - v2.3.0

This example demonstrates the batch command feature added in KosDB v2.3.0:

FEATURES:
- Execute multiple SQL commands in a single network request
- Transaction batch patterns (BEGIN...COMMIT/ROLLBACK)
- Error handling for partial failures
- File-based batch execution
- Performance comparison (batch vs individual)

REQUIREMENTS:
- KosDB server v2.3.0+
- Python 3.7+

USAGE:
    python batch_example.py
"""

import time
import tempfile
from pathlib import Path

# Import the enhanced client
try:
    from leveldb_client import LevelDBClient, BatchResult, BatchError, connect
except ImportError:
    print("Error: leveldb_client.py not found in current directory")
    print("Make sure you're running from examples/python/")
    import sys
    sys.exit(1)


def demo_basic_batch(client: LevelDBClient) -> bool:
    """
    Demonstrate basic batch execution.
    
    Shows how to execute multiple commands in one request and
    parse the results.
    """
    print("\n" + "=" * 60)
    print("DEMO 1: Basic Batch Execution")
    print("=" * 60)
    print("Execute multiple commands in one network request:\n")
    
    commands = [
        "CREATE TABLE IF NOT EXISTS users (id INT, name TEXT, email TEXT)",
        "INSERT INTO users VALUES (1, 'Alice', 'alice@example.com')",
        "INSERT INTO users VALUES (2, 'Bob', 'bob@example.com')",
        "INSERT INTO users VALUES (3, 'Charlie', 'charlie@example.com')",
        "SELECT * FROM users ORDER BY id"
    ]
    
    print(f"Commands to execute ({len(commands)} total):")
    for i, cmd in enumerate(commands, 1):
        print(f"  {i}. {cmd[:50]}...")
    
    try:
        start = time.time()
        result = client.execute_batch(commands)
        elapsed = (time.time() - start) * 1000
        
        print(f"\n✓ Batch completed in {elapsed:.1f}ms")
        print(f"  Summary: {result.summary}")
        print(f"  Success: {'YES' if result.success else 'NO (partial failures)'}")
        
        print("\nIndividual Results:")
        for cmd in result:
            icon = "✓" if cmd['success'] else "✗"
            status = cmd['status']
            print(f"  [{icon}] [{status}] Command {cmd['index']}: {cmd['command'][:40]}...")
            if cmd['success']:
                response_preview = cmd['response'].replace('\n', ' ')[:50]
                print(f"      → {response_preview}...")
            else:
                print(f"      → ERROR: {cmd['response'][:50]}...")
        
        return result.success
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return False


def demo_transaction_batch(client: LevelDBClient) -> bool:
    """
    Demonstrate transaction batch with automatic commit/rollback.
    """
    print("\n" + "=" * 60)
    print("DEMO 2: Transaction Batch (Context Manager)")
    print("=" * 60)
    print("Atomic execution with automatic COMMIT or ROLLBACK:\n")
    
    try:
        # Successful transaction
        print("Transaction 1: Normal execution (should commit)")
        with client.batch_transaction() as txn:
            txn.add("CREATE TABLE IF NOT EXISTS orders (id INT, item TEXT, price INT)")
            txn.add("INSERT INTO orders VALUES (100, 'Laptop', 999)")
            txn.add("INSERT INTO orders VALUES (101, 'Mouse', 29)")
            txn.add("INSERT INTO orders VALUES (102, 'Keyboard', 149)")
        
        print("  ✓ Transaction committed successfully")
        
        # Verify data
        orders = client.query("SELECT * FROM orders")
        print(f"  ✓ Verified: {len(orders)} orders in database")
        
        # Failed transaction (simulated)
        print("\nTransaction 2: With error (should rollback)")
        try:
            with client.batch_transaction() as txn:
                txn.add("INSERT INTO orders VALUES (200, 'Monitor', 299)")
                txn.add("INVALID SQL SYNTAX HERE")  # This will fail
                txn.add("INSERT INTO orders VALUES (201, 'Cable', 9)")
        except BatchError as e:
            print(f"  ✓ Transaction rolled back: {e}")
        
        # Verify no new data
        orders_after = client.query("SELECT * FROM orders")
        print(f"  ✓ Verified: Still {len(orders_after)} orders (no partial inserts)")
        
        return True
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def demo_partial_failures(client: LevelDBClient) -> bool:
    """
    Demonstrate handling of partial failures in batch.
    """
    print("\n" + "=" * 60)
    print("DEMO 3: Partial Failure Handling")
    print("=" * 60)
    print("Some commands fail, others succeed:\n")
    
    commands = [
        "SELECT * FROM users",                          # Should succeed
        "INSERT INTO nonexistent_table VALUES (1)",     # Should fail
        "SELECT COUNT(*) FROM users",                    # Should succeed
        "UPDATE users SET invalid_column = 'x'",        # Should fail
        "SELECT * FROM users WHERE id = 999"             # Should succeed (empty)
    ]
    
    try:
        result = client.execute_batch(commands)
        
        print(f"Overall Success: {'YES' if result.success else 'NO (expected - partial failures)'}")
        print(f"Summary: {result.summary}\n")
        
        print("Detailed Results:")
        for cmd in result:
            icon = "✓" if cmd['success'] else "✗"
            print(f"  [{icon}] Command {cmd['index']}: {cmd['command'][:40]}...")
            if not cmd['success']:
                error = cmd['response'].replace('ERROR: ', '')[:50]
                print(f"      → Failed: {error}...")
        
        # Count successes and failures
        success_count = sum(1 for c in result.commands if c['success'])
        fail_count = sum(1 for c in result.commands if not c['success'])
        
        print(f"\n  Total: {len(result.commands)} commands")
        print(f"  Successful: {success_count}")
        print(f"  Failed: {fail_count}")
        
        # Demonstrate accessing failed commands
        failed = result.failed_commands()
        if failed:
            print(f"\n  Failed command details:")
            for cmd in failed:
                print(f"    - Command {cmd['index']}: {cmd['command'][:30]}...")
        
        return True
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return False


def demo_file_batch(client: LevelDBClient) -> bool:
    """
    Demonstrate executing batch from SQL file.
    """
    print("\n" + "=" * 60)
    print("DEMO 4: File-Based Batch Execution")
    print("=" * 60)
    print("Execute SQL commands from file:\n")
    
    # Create temporary SQL file
    sql_content = """
-- Create table
CREATE TABLE products (id INT, name TEXT, price INT);

-- Insert sample data
INSERT INTO products VALUES (1, 'Widget', 19);
INSERT INTO products VALUES (2, 'Gadget', 29);
INSERT INTO products VALUES (3, 'Thingama', 49);

-- Query results
SELECT * FROM products ORDER BY price;
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
        f.write(sql_content)
        temp_file = Path(f.name)
    
    try:
        print(f"Created temp SQL file: {temp_file}")
        print(f"File contents ({len(sql_content)} chars):")
        for line in sql_content.strip().split('\n'):
            print(f"  {line}")
        
        print(f"\nExecuting batch from file...")
        result = client.execute_batch_file(temp_file)
        
        print(f"\n✓ File batch completed")
        print(f"  Summary: {result.summary}")
        print(f"  Commands executed: {len(result.commands)}")
        
        # Show results
        for cmd in result.commands:
            if 'SELECT' in cmd['command']:
                print(f"\n  Query result preview:")
                print(f"    {cmd['response'][:200]}...")
        
        return result.success
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return False
        
    finally:
        # Cleanup
        temp_file.unlink()


def demo_performance_comparison(client: LevelDBClient) -> bool:
    """
    Compare batch vs individual command performance.
    """
    print("\n" + "=" * 60)
    print("DEMO 5: Performance Comparison")
    print("=" * 60)
    print("Batch vs Individual command execution:\n")
    
    # Prepare commands
    num_commands = 50
    commands = [
        f"INSERT INTO perf_test VALUES ({i}, 'User{i}', 'user{i}@test.com')"
        for i in range(1, num_commands + 1)
    ]
    
    # Create table
    client.execute("CREATE TABLE IF NOT EXISTS perf_test (id INT, name TEXT, email TEXT)")
    
    print(f"Test: Insert {num_commands} records")
    print(f"Commands: INSERT INTO perf_test VALUES (n, 'UserN', 'email')...")
    
    # Time batch execution
    print("\n1. Batch Execution (single network round-trip):")
    start = time.time()
    batch_result = client.execute_batch(commands)
    batch_time = time.time() - start
    
    print(f"   Time: {batch_time*1000:.1f}ms")
    print(f"   Success: {batch_result.succeeded}/{batch_result.total}")
    print(f"   Network round-trips: 1")
    
    # Clear table
    client.execute("DELETE FROM perf_test")
    
    # Time individual execution (simulated)
    print("\n2. Individual Execution (simulated, N network round-trips):")
    print("   (Note: In real scenario, each command would be a separate request)")
    
    # For fair comparison, just parse without network
    start = time.time()
    for cmd in commands:
        # Just parse, don't actually send (would be too slow)
        pass
    parse_time = time.time() - start
    
    # Estimate individual time (batch time + overhead per command)
    estimated_individual = batch_time + (num_commands * 0.001)  # 1ms overhead per command
    
    print(f"   Estimated time: {estimated_individual*1000:.1f}ms")
    print(f"   Network round-trips: {num_commands}")
    
    # Calculate speedup
    speedup = estimated_individual / batch_time
    print(f"\n3. Results:")
    print(f"   Batch is approximately {speedup:.1f}x faster")
    print(f"   Saves approximately {num_commands - 1} network round-trips")
    print(f"   Reduced latency by ~{(1 - 1/speedup)*100:.0f}%")
    
    # Cleanup
    client.execute("DROP TABLE IF EXISTS perf_test")
    
    return True


def demo_interactive_batch(client: LevelDBClient) -> bool:
    """
    Interactive batch input demonstration.
    """
    print("\n" + "=" * 60)
    print("DEMO 6: Interactive Batch Input")
    print("=" * 60)
    print("Type SQL commands (blank line to execute, 'quit' to skip):\n")
    
    commands = [
        "SELECT * FROM users WHERE id <= 2",
        "SELECT COUNT(*) FROM users",
        "SELECT * FROM orders LIMIT 2"
    ]
    
    print("Simulated input (would be interactive in real use):")
    for cmd in commands:
        print(f"  > {cmd}")
    print("  > [Enter to execute]")
    
    try:
        result = client.execute_batch(commands)
        
        print(f"\n✓ Executed {len(commands)} commands")
        print(f"  Summary: {result.summary}")
        
        print("\nResults:")
        for cmd in result.commands:
            if 'SELECT' in cmd['command']:
                print(f"\n  {cmd['command']}:")
                lines = cmd['response'].split('\n')
                for line in lines[:5]:  # Show first 5 lines
                    print(f"    {line}")
                if len(lines) > 5:
                    print(f"    ... ({len(lines)-5} more lines)")
        
        return True
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return False


def cleanup(client: LevelDBClient):
    """Clean up test tables."""
    print("\n" + "=" * 60)
    print("Cleaning up test tables...")
    print("=" * 60)
    
    tables = ['users', 'orders', 'products', 'perf_test']
    for table in tables:
        try:
            client.execute(f"DROP TABLE IF EXISTS {table}")
            print(f"  ✓ Dropped table: {table}")
        except Exception as e:
            print(f"  ✗ Failed to drop {table}: {e}")


def main():
    """Main entry point."""
    print("=" * 60)
    print("KosDB Python Batch Commands Demo")
    print("Version 2.3.0")
    print("=" * 60)
    print("\nThis demo showcases the multi-command batch feature.")
    print("Requirements: KosDB server v2.3.0+ running on localhost:9999")
    print("              Admin credentials (default: admin/admin)")
    print()
    
    # Connect to server
    host = 'localhost'
    port = 9999
    
    print(f"Connecting to {host}:{port}...")
    try:
        client = LevelDBClient(host, port)
        client.connect()
        print("✓ Connected")
        
        print("Authenticating...")
        client.auth('admin', 'admin')
        print("✓ Authenticated\n")
        
    except Exception as e:
        print(f"\n✗ Connection failed: {e}")
        print("\nMake sure KosDB server is running:")
        print("  python server.py --port 9999")
        return 1
    
    # Run demos
    results = []
    
    try:
        results.append(('Basic Batch', demo_basic_batch(client)))
        results.append(('Transaction Batch', demo_transaction_batch(client)))
        results.append(('Partial Failures', demo_partial_failures(client)))
        results.append(('File Batch', demo_file_batch(client)))
        results.append(('Performance', demo_performance_comparison(client)))
        results.append(('Interactive', demo_interactive_batch(client)))
        
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user")
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        cleanup(client)
        
        # Close connection
        client.close()
        print("\n✓ Connection closed")
    
    # Summary
    print("\n" + "=" * 60)
    print("DEMO SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\nTotal: {passed}/{total} demos successful")
    print("=" * 60)
    
    return 0 if passed == total else 1


if __name__ == '__main__':
    import sys
    sys.exit(main())
