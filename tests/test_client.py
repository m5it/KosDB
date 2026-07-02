#!/usr/bin/env python3
"""
Test client for threaded socket server with LevelDB backend.
Tests authentication and SQL-like commands.
"""

import socket
import sys
import time

HOST = 'localhost'
PORT = 9999


def send_command(sock, command):
    """Send a command and receive response."""
    sock.sendall((command + '\n').encode())
    response = sock.recv(4096).decode().strip()
    return response


def test_authentication():
    """Test authentication flow."""
    print("=" * 50)
    print("TEST: Authentication")
    print("=" * 50)
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((HOST, PORT))
        
        # Receive welcome message
        welcome = sock.recv(1024).decode().strip()
        print(f"Server: {welcome}")
        
        # Test wrong password
        print("\n--- Testing wrong password ---")
        send_command(sock, "admin")
        response = send_command(sock, "wrongpass")
        print(f"User: admin, Pass: wrongpass")
        print(f"Response: {response}")
        assert "Authentication failed" in response, "Should reject wrong password"
        
    # Reconnect for correct auth
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((HOST, PORT))
        welcome = sock.recv(1024).decode().strip()
        
        print("\n--- Testing correct credentials ---")
        send_command(sock, "admin")
        response = send_command(sock, "skrlat")
        print(f"User: admin, Pass: skrlat")
        print(f"Response: {response}")
        assert "Authentication successful" in response, "Should accept correct password"
        
    print("✓ Authentication tests passed\n")


def test_database_commands():
    """Test database operations."""
    print("=" * 50)
    print("TEST: Database Commands")
    print("=" * 50)
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((HOST, PORT))
        
        # Authenticate
        sock.recv(1024)  # welcome
        send_command(sock, "admin")
        send_command(sock, "skrlat")
        
        # Test CREATE DATABASE
        print("\n--- CREATE DATABASE ---")
        response = send_command(sock, "CREATE DATABASE testdb")
        print(f"Command: CREATE DATABASE testdb")
        print(f"Response: {response}")
        
        # Test USE
        print("\n--- USE DATABASE ---")
        response = send_command(sock, "USE testdb")
        print(f"Command: USE testdb")
        print(f"Response: {response}")
        
        # Test CREATE TABLE
        print("\n--- CREATE TABLE ---")
        response = send_command(sock, "CREATE TABLE users (id INT, name TEXT)")
        print(f"Command: CREATE TABLE users (id INT, name TEXT)")
        print(f"Response: {response}")
        
        # Test INSERT
        print("\n--- INSERT ---")
        response = send_command(sock, "INSERT INTO users VALUES (1, 'Alice')")
        print(f"Command: INSERT INTO users VALUES (1, 'Alice')")
        print(f"Response: {response}")
        
        response = send_command(sock, "INSERT INTO users VALUES (2, 'Bob')")
        print(f"Command: INSERT INTO users VALUES (2, 'Bob')")
        print(f"Response: {response}")
        
        # Test SELECT
        print("\n--- SELECT ---")
        response = send_command(sock, "SELECT * FROM users")
        print(f"Command: SELECT * FROM users")
        print(f"Response: {response}")
        
        response = send_command(sock, "SELECT name FROM users WHERE id=1")
        print(f"Command: SELECT name FROM users WHERE id=1")
        print(f"Response: {response}")
        
        # Test UPDATE
        print("\n--- UPDATE ---")
        response = send_command(sock, "UPDATE users SET name='Charlie' WHERE id=1")
        print(f"Command: UPDATE users SET name='Charlie' WHERE id=1")
        print(f"Response: {response}")
        
        # Verify update
        response = send_command(sock, "SELECT * FROM users WHERE id=1")
        print(f"Verify: SELECT * FROM users WHERE id=1")
        print(f"Response: {response}")
        
        # Test DELETE
        print("\n--- DELETE ---")
        response = send_command(sock, "DELETE FROM users WHERE id=2")
        print(f"Command: DELETE FROM users WHERE id=2")
        print(f"Response: {response}")
        
        # Verify delete
        response = send_command(sock, "SELECT * FROM users")
        print(f"Verify: SELECT * FROM users")
        print(f"Response: {response}")
        
        # Test DROP TABLE
        print("\n--- DROP TABLE ---")
        response = send_command(sock, "DROP TABLE users")
        print(f"Command: DROP TABLE users")
        print(f"Response: {response}")
        
        # Test DROP DATABASE
        print("\n--- DROP DATABASE ---")
        response = send_command(sock, "DROP DATABASE testdb")
        print(f"Command: DROP DATABASE testdb")
        print(f"Response: {response}")
        
    print("\n✓ Database command tests completed\n")


def test_error_handling():
    """Test error responses."""
    print("=" * 50)
    print("TEST: Error Handling")
    print("=" * 50)
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((HOST, PORT))
        
        # Authenticate
        sock.recv(1024)
        send_command(sock, "admin")
        send_command(sock, "skrlat")
        
        print("\n--- Invalid command ---")
        response = send_command(sock, "FOOBAR")
        print(f"Command: FOOBAR")
        print(f"Response: {response}")
        
        print("\n--- Syntax error ---")
        response = send_command(sock, "SELECT FROM")  # Missing table
        print(f"Command: SELECT FROM")
        print(f"Response: {response}")
        
        print("\n--- Database not selected ---")
        response = send_command(sock, "SELECT * FROM users")
        print(f"Command: SELECT * FROM users (no DB selected)")
        print(f"Response: {response}")
        
    print("\n✓ Error handling tests completed\n")


def run_all_tests():
    """Run all test suites."""
    print("\n" + "=" * 50)
    print("SOCKET SERVER TEST SUITE")
    print("=" * 50 + "\n")
    
    try:
        test_authentication()
        time.sleep(0.5)
        
        test_database_commands()
        time.sleep(0.5)
        
        test_error_handling()
        
        print("=" * 50)
        print("ALL TESTS COMPLETED SUCCESSFULLY!")
        print("=" * 50)
        
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    except ConnectionRefusedError:
        print(f"\n✗ CONNECTION FAILED: Is the server running on {HOST}:{PORT}?")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()
