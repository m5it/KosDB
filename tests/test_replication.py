#!/usr/bin/env python3
"""
Replication Test Suite for LevelDB Socket Server

Tests master-slave and master-master replication scenarios.
"""

import subprocess
import time
import socket
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database


class ReplicationTest:
    def __init__(self):
        self.master_proc = None
        self.slave_proc = None
        self.test_results = []
    
    def log(self, message):
        print(f"[TEST] {message}")
    
    def start_master(self, port=9999, data_dir="./test_data_master"):
        """Start master server."""
        self.log(f"Starting master on port {port}...")
        
        cmd = [
            "python3", "server.py",
            "--port", str(port),
            "--data_dir", data_dir,
            "--server-id", "1",
            "--role", "master",
            "--replication-port", str(port + 1000)
        ]
        
        self.master_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        
        # Wait for server to start
        time.sleep(2)
        
        # Check if process is running
        if self.master_proc.poll() is not None:
            self.log("ERROR: Master failed to start")
            return False
        
        self.log("Master started successfully")
        return True
    
    def start_slave(self, master_host="localhost:9999", port=9998, data_dir="./test_data_slave"):
        """Start slave server."""
        self.log(f"Starting slave on port {port}, connecting to {master_host}...")
        
        cmd = [
            "python3", "server.py",
            "--port", str(port),
            "--data_dir", data_dir,
            "--server-id", "2",
            "--role", "slave",
            "--master-host", master_host
        ]
        
        self.slave_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        
        # Wait for server to start
        time.sleep(2)
        
        # Check if process is running
        if self.slave_proc.poll() is not None:
            self.log("ERROR: Slave failed to start")
            return False
        
        self.log("Slave started successfully")
        return True
    
    def stop_servers(self):
        """Stop all test servers."""
        self.log("Stopping servers...")
        
        if self.slave_proc:
            self.slave_proc.terminate()
            self.slave_proc.wait()
            self.slave_proc = None
        
        if self.master_proc:
            self.master_proc.terminate()
            self.master_proc.wait()
            self.master_proc = None
        
        self.log("Servers stopped")
    
    def send_command(self, host, port, commands):
        """Send commands to server and return responses."""
        responses = []
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((host, port))
            
            for cmd in commands:
                sock.sendall((cmd + '\n').encode())
                time.sleep(0.5)
                data = sock.recv(4096).decode()
                responses.append(data)
            
            sock.close()
        except Exception as e:
            self.log(f"Connection error: {e}")
            return None
        
        return responses
    
    def test_basic_replication(self):
        """Test basic master-slave replication."""
        self.log("=" * 50)
        self.log("TEST: Basic Replication")
        self.log("=" * 50)
        
        try:
            # Setup: Create replication user on master
            self.log("Creating replication user...")
            
            # Test 1: Connect to master and create database
            self.log("Creating test database on master...")
            responses = self.send_command("localhost", 9999, [
                "USER admin",
                "PASS admin",
                "CREATE DATABASE test_repl",
                "USE test_repl",
                "CREATE TABLE users (id INT PRIMARY KEY, name TEXT)",
                "INSERT INTO users VALUES (1, 'Alice')",
                "INSERT INTO users VALUES (2, 'Bob')"
            ])
            
            if not responses:
                self.log("FAIL: Could not connect to master")
                return False
            
            self.log("Data inserted on master")
            
            # Wait for replication
            time.sleep(3)
            
            # Test 2: Check data on slave
            self.log("Checking data on slave...")
            responses = self.send_command("localhost", 9998, [
                "USER admin",
                "PASS admin",
                "USE test_repl",
                "SELECT * FROM users"
            ])
            
            if not responses:
                self.log("FAIL: Could not connect to slave")
                return False
            
            last_response = responses[-1] if responses else ""
            if "Alice" in last_response and "Bob" in last_response:
                self.log("PASS: Data replicated to slave")
                return True
            else:
                self.log(f"FAIL: Data not found on slave. Response: {last_response}")
                return False
                
        except Exception as e:
            self.log(f"FAIL: Test error: {e}")
            return False
    
    def test_slave_recovery(self):
        """Test slave reconnection and catch-up."""
        self.log("=" * 50)
        self.log("TEST: Slave Recovery")
        self.log("=" * 50)
        
        try:
            # Stop slave
            self.log("Stopping slave...")
            if self.slave_proc:
                self.slave_proc.terminate()
                self.slave_proc.wait()
                self.slave_proc = None
            
            # Insert more data on master while slave is down
            self.log("Inserting data while slave is down...")
            self.send_command("localhost", 9999, [
                "USER admin",
                "PASS admin",
                "USE test_repl",
                "INSERT INTO users VALUES (3, 'Charlie')",
                "INSERT INTO users VALUES (4, 'David')"
            ])
            
            # Restart slave
            self.log("Restarting slave...")
            if not self.start_slave():
                self.log("FAIL: Could not restart slave")
                return False
            
            # Wait for catch-up
            time.sleep(3)
            
            # Check all data is present
            self.log("Verifying slave caught up...")
            responses = self.send_command("localhost", 9998, [
                "USER admin",
                "PASS admin",
                "USE test_repl",
                "SELECT * FROM users"
            ])
            
            if not responses:
                self.log("FAIL: Could not connect to slave after restart")
                return False
            
            last_response = responses[-1] if responses else ""
            if "Charlie" in last_response and "David" in last_response:
                self.log("PASS: Slave recovered and caught up")
                return True
            else:
                self.log(f"FAIL: Slave did not catch up. Response: {last_response}")
                return False
                
        except Exception as e:
            self.log(f"FAIL: Test error: {e}")
            return False
    
    def run_all_tests(self):
        """Run all replication tests."""
        self.log("Starting Replication Test Suite")
        self.log("=" * 50)
        
        results = []
        
        try:
            # Start master
            if not self.start_master():
                self.log("FAILED: Could not start master")
                return False
            
            # Create admin user on master first
            time.sleep(1)
            
            # Start slave
            if not self.start_slave():
                self.log("FAILED: Could not start slave")
                self.stop_servers()
                return False
            
            # Run tests
            results.append(("Basic Replication", self.test_basic_replication()))
            results.append(("Slave Recovery", self.test_slave_recovery()))
            
        finally:
            # Cleanup
            self.stop_servers()
            self.cleanup_test_data()
        
        # Print summary
        self.log("=" * 50)
        self.log("TEST SUMMARY")
        self.log("=" * 50)
        
        passed = 0
        failed = 0
        
        for name, result in results:
            status = "PASS" if result else "FAIL"
            self.log(f"{name}: {status}")
            if result:
                passed += 1
            else:
                failed += 1
        
        self.log(f"\nTotal: {passed} passed, {failed} failed")
        
        return failed == 0
    
    def cleanup_test_data(self):
        """Remove test data directories."""
        import shutil
        for data_dir in ["./test_data_master", "./test_data_slave"]:
            if os.path.exists(data_dir):
                try:
                    shutil.rmtree(data_dir)
                    self.log(f"Cleaned up {data_dir}")
                except Exception as e:
                    self.log(f"Warning: Could not remove {data_dir}: {e}")


if __name__ == '__main__':
    test = ReplicationTest()
    success = test.run_all_tests()
    sys.exit(0 if success else 1)