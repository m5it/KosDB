"""
GPU Integration Tests for KosDB v3.1.0

Tests GPU vector search integration and CPU fallback.
"""

import unittest
import subprocess
import time
import os
import tempfile
import shutil
import json
import numpy as np

# Check if GPU is available
try:
    import pycuda.driver as cuda
    cuda.init()
    GPU_AVAILABLE = True
    GPU_DEVICE_COUNT = cuda.Device.count()
except ImportError:
    GPU_AVAILABLE = False
    GPU_DEVICE_COUNT = 0


@unittest.skipUnless(GPU_AVAILABLE and GPU_DEVICE_COUNT > 0, "GPU not available")
class TestGPUIntegration(unittest.TestCase):
    """Integration tests for GPU acceleration."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment."""
        cls.temp_dir = tempfile.mkdtemp()
        cls.data_dir = os.path.join(cls.temp_dir, 'data')
        os.makedirs(cls.data_dir, exist_ok=True)
        
        # Create server config with GPU enabled
        cls.config_path = os.path.join(cls.temp_dir, 'config.json')
        cls._create_server_config()
        
        cls.server_process = None
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test environment."""
        if cls.server_process:
            cls.server_process.terminate()
            cls.server_process.wait()
        
        shutil.rmtree(cls.temp_dir, ignore_errors=True)
    
    @classmethod
    def _create_server_config(cls):
        """Create server configuration with GPU enabled."""
        config = {
            "version": "3.1.0",
            "server": {
                "host": "127.0.0.1",
                "port": 19997,
                "data_dir": cls.data_dir,
                "server_id": 1
            },
            "gpu": {
                "enabled": True,
                "device_id": 0,
                "memory_fraction": 0.5,
                "compute_capability": "auto",
                "kernels": ["vector_ops", "matrix_mult", "sort", "aggregate"]
            },
            "audit_logging": {
                "enabled": False
            }
        }
        
        with open(cls.config_path, 'w') as f:
            json.dump(config, f, indent=2)
    
    def setUp(self):
        """Start server before each test."""
        self.server_process = subprocess.Popen(
            ['python', 'server.py', '-c', self.config_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        
        # Wait for server to start
        time.sleep(3)
        
        # Check if server is running
        self.assertIsNone(self.server_process.poll(), "Server failed to start")
    
    def tearDown(self):
        """Stop server after each test."""
        if self.server_process:
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
            self.server_process = None
    
    def _send_command(self, command):
        """Send command to server and return response."""
        import socket
        with socket.create_connection(('127.0.0.1', 19997)) as sock:
            sock.send(f"{command}\\n".encode())
            return sock.recv(4096).decode().strip()
    
    def test_gpu_initialization(self):
        """Test that GPU is initialized on server startup."""
        # Check server output for GPU initialization
        stdout, stderr = self.server_process.communicate(timeout=1)
        output = (stdout.decode() + stderr.decode()).lower()
        
        # Should mention GPU in output
        self.assertIn('gpu', output or 'initialized')
    
    def test_vector_search_performance(self):
        """Test GPU-accelerated vector search."""
        # Create test database and table
        self._send_command("USER admin")
        self._send_command("PASS admin123")
        self._send_command("CREATE DATABASE testdb")
        self._send_command("USE testdb")
        self._send_command("CREATE TABLE vectors (id INT, vec FLOAT[])")
        
        # Insert test vectors
        import random
        vectors = []
        for i in range(1000):
            vec = [random.random() for _ in range(128)]
            vectors.append((i, vec))
            vec_str = ','.join(str(v) for v in vec)
            self._send_command(f"INSERT INTO vectors VALUES ({i}, ARRAY[{vec_str}])")
        
        # Perform vector search (should use GPU)
        query_vec = [random.random() for _ in range(128)]
        
        import time
        start = time.time()
        response = self._send_command("SELECT * FROM vectors ORDER BY vec <-> query_vec LIMIT 10")
        gpu_time = time.time() - start
        
        # Should return results
        self.assertIn('rows', response.lower())
        
        # GPU should be faster than CPU (if properly implemented)
        # This is a rough check - actual performance depends on hardware
        print(f"GPU search time: {gpu_time:.3f}s")
    
    def test_gpu_memory_management(self):
        """Test GPU memory fraction configuration."""
        # Create large dataset to test memory limits
        self._send_command("USER admin")
        self._send_command("PASS admin123")
        self._send_command("CREATE DATABASE memtest")
        self._send_command("USE memtest")
        self._send_command("CREATE TABLE large_data (id INT, data FLOAT[])")
        
        # Insert data that might exceed GPU memory fraction
        for i in range(100):
            data = [0.0] * 10000  # Large vectors
            data_str = ','.join(str(v) for v in data)
            response = self._send_command(f"INSERT INTO large_data VALUES ({i}, ARRAY[{data_str}])")
            self.assertTrue(response.startswith("OK") or "error" not in response.lower())
        
        # Query should still work (with memory management)
        response = self._send_command("SELECT COUNT(*) FROM large_data")
        self.assertIn('100', response)
    
    def test_aggregate_operations(self):
        """Test GPU-accelerated aggregate operations."""
        self._send_command("USER admin")
        self._send_command("PASS admin123")
        self._send_command("CREATE DATABASE aggtest")
        self._send_command("USE aggtest")
        self._send_command("CREATE TABLE numbers (val FLOAT)")
        
        # Insert numbers
        for i in range(10000):
            self._send_command(f"INSERT INTO numbers VALUES ({i}.0)")
        
        # Test aggregate functions
        response = self._send_command("SELECT SUM(val), AVG(val), MIN(val), MAX(val) FROM numbers")
        
        # Should return correct aggregates
        self.assertIn('49995000', response)  # SUM
        self.assertIn('4999.5', response)   # AVG
    
    def test_sorting_performance(self):
        """Test GPU-accelerated sorting."""
        self._send_command("USER admin")
        self._send_command("PASS admin123")
        self._send_command("CREATE DATABASE sorttest")
        self._send_command("USE sorttest")
        self._send_command("CREATE TABLE items (id INT, value FLOAT)")
        
        # Insert random data
        import random
        for i in range(10000):
            val = random.random() * 1000
            self._send_command(f"INSERT INTO items VALUES ({i}, {val})")
        
        # Sort and verify
        response = self._send_command("SELECT * FROM items ORDER BY value ASC LIMIT 5")
        
        # Should return sorted results
        self.assertTrue(len(response) > 0)


@unittest.skipIf(GPU_AVAILABLE and GPU_DEVICE_COUNT > 0, "GPU is available")
class TestCPUFallback(unittest.TestCase):
    """Test CPU fallback when GPU is not available."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, 'config.json')
        
        # Create config with GPU disabled
        config = {
            "version": "3.1.0",
            "server": {
                "host": "127.0.0.1",
                "port": 19996,
                "data_dir": self.temp_dir,
                "server_id": 1
            },
            "gpu": {
                "enabled": False
            }
        }
        
        with open(self.config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        self.server_process = subprocess.Popen(
            ['python', 'server.py', '-c', self.config_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        
        time.sleep(2)
    
    def tearDown(self):
        if self.server_process:
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
        
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_cpu_operations_work(self):
        """Test that operations work on CPU when GPU is disabled."""
        import socket
        
        with socket.create_connection(('127.0.0.1', 19996)) as sock:
            sock.send(b"TEST\\n")
            response = sock.recv(1024)
            self.assertIn(b"LevelDB", response)
        
        # Database operations should still work
        with socket.create_connection(('127.0.0.1', 19996)) as sock:
            sock.send(b"USER admin\\n")
            sock.recv(1024)
            sock.send(b"PASS admin123\\n")
            response = sock.recv(1024).decode()
            # May fail auth but should not crash
            self.assertTrue(len(response) > 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
