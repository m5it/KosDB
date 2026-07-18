
#!/usr/bin/env python3
"""
Test concurrent USE commands and UPDATE operations to verify KosDB fixes.
"""

import socket
import threading
import time
import sys

def send_command(sock, cmd):
    """Send command and receive response."""
    sock.send((cmd + "\n").encode())
    return sock.recv(4096).decode().strip()

def test_concurrent_use(host, port, db_name, num_threads=5):
    """Test concurrent USE commands from multiple threads."""
    results = []
    errors = []
    
    def worker(thread_id):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((host, port))
            
            # Welcome
            welcome = sock.recv(1024).decode()
            
            # Login
            login_resp = send_command(sock, "LOGIN admin skrlat")
            if "Welcome" not in login_resp:
                errors.append(f"Thread {thread_id}: Login failed")
                sock.close()
                return
            
            # Concurrent USE commands
            for i in range(3):
                use_resp = send_command(sock, f"USE {db_name}")
                results.append(f"Thread {thread_id}, Iter {i}: {use_resp}")
                time.sleep(0.01)  # Small delay
            
            sock.close()
        except Exception as e:
            errors.append(f"Thread {thread_id}: {str(e)}")
    
    threads = []
    for i in range(num_threads):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
    
    start_time = time.time()
    for t in threads:
        t.start()
    
    for t in threads:
        t.join()
    
    elapsed = time.time() - start_time
    
    print(f"\n=== Concurrent USE Test ({num_threads} threads) ===")
    print(f"Completed in {elapsed:.2f}s")
    print(f"Results: {len(results)}")
    print(f"Errors: {len(errors)}")
    
    # Check for idempotent behavior
    already_count = sum(1 for r in results if "Already using" in r)
    switched_count = sum(1 for r in results if "Switched to" in r)
    
    print(f"Idempotent responses (Already using): {already_count}")
    print(f"Switch responses (Switched to): {switched_count}")
    
    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  {e}")
    
    return len(errors) == 0

def test_update_response(host, port):
    """Test that UPDATE returns proper row count."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((host, port))
        
        # Welcome & Login
        sock.recv(1024)
        send_command(sock, "LOGIN admin skrlat")
        
        # Use test db
        send_command(sock, "USE webcms")
        
        # Create table
        send_command(sock, "CREATE TABLE settings (key, value)")
        
        # Insert test data
        send_command(sock, "INSERT INTO settings VALUES ('test_key', 'test_value')")
        
        # Update and check response
        update_resp = send_command(sock, "UPDATE settings SET value='new_value' WHERE key='test_key'")
        
        print("\n=== UPDATE Response Test ===")
        print(f"Response: {update_resp}")
        
        # Verify format is correct (should be "OK: Updated X row(s)")
        if update_resp.startswith("OK: Updated") and "row(s)" in update_resp:
            # Extract number
            import re
            match = re.search(r'Updated (\d+) row', update_resp)
            if match:
                num = int(match.group(1))
                print(f"✓ Row count extracted: {num}")
                return True
            else:
                print("✗ Could not extract row count")
                return False
        else:
            print("✗ Response format incorrect")
            return False
        
        sock.close()
    except Exception as e:
        print(f"✗ Test failed: {e}")
        return False

def main():
    host = "localhost"
    port = 5555
    
    print("Testing KosDB fixes...")
    print("Make sure server is running on port 5555")
    
    # Test 1: Concurrent USE
    use_ok = test_concurrent_use(host, port, "webcms", num_threads=5)
    
    # Test 2: UPDATE response format
    update_ok = test_update_response(host, port)
    
    print("\n" + "=" * 50)
    if use_ok and update_ok:
        print("✓ All tests PASSED")
        return 0
    else:
        print("✗ Some tests FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
