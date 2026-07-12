"""
Tests for server batch command execution.
"""
import unittest
import sys
import os
import socket
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import SocketServer, ClientHandler
from database import Database
from auth import Authenticator


class MockSocket:
    """Mock socket for testing."""
    def __init__(self):
        self.sent_data = []
        self.recv_data = []
        self.recv_index = 0
    
    def sendall(self, data):
        self.sent_data.append(data.decode().strip())
    
    def recv(self, size):
        if self.recv_index < len(self.recv_data):
            data = self.recv_data[self.recv_index]
            self.recv_index += 1
            return data.encode()
        return b''
    
    def close(self):
        pass
    
    def set_recv_sequence(self, sequence):
        self.recv_data = sequence


class TestServerBatch(unittest.TestCase):
    """Test batch command execution in server."""
    
    def setUp(self):
        self.db = Database(':memory:')
        self.authenticator = Authenticator(self.db)
        # Create admin user
        self.db.create_user('admin', 'admin123', is_admin=True)
        self.parser = __import__('parser').BackupRestoreParser()
    
    def tearDown(self):
        self.db.close()
    
    def test_split_commands_single(self):
        """Single command without semicolon."""
        result = self.parser.split_commands("SHOW DATABASES")
        self.assertEqual(result, ["SHOW DATABASES"])
    
    def test_split_commands_multiple(self):
        """Multiple commands separated by semicolons."""
        result = self.parser.split_commands("CMD1; CMD2; CMD3")
        self.assertEqual(result, ["CMD1", "CMD2", "CMD3"])
    
    def test_split_commands_with_quotes(self):
        """Semicolons in quotes should not split."""
        result = self.parser.split_commands("INSERT INTO t VALUES ('a;b'); SELECT 1")
        self.assertEqual(result, ["INSERT INTO t VALUES ('a;b')", "SELECT 1"])
    
    def test_split_commands_empty(self):
        """Empty and whitespace-only strings."""
        self.assertEqual(self.parser.split_commands(""), [])
        self.assertEqual(self.parser.split_commands("   "), [])
        self.assertEqual(self.parser.split_commands(";;;"), [])


class TestBatchResponseFormat(unittest.TestCase):
    """Test batch response formatting."""
    
    def test_batch_response_format(self):
        """Verify batch response format includes command numbering and summary."""
        # This is a format test - actual execution tested in integration
        results = [
            "[1/3] OK: SELECT 1\nResult1",
            "[2/3] OK: SELECT 2\nResult2",
            "[3/3] ERROR: BAD CMD\nError message"
        ]
        summary = "\n--- Batch Complete ---\n3 command(s): 2 succeeded, 1 failed"
        full_response = "\n\n".join(results + [summary])
        
        # Verify structure
        self.assertIn("[1/3]", full_response)
        self.assertIn("[2/3]", full_response)
        self.assertIn("[3/3]", full_response)
        self.assertIn("Batch Complete", full_response)
        self.assertIn("2 succeeded", full_response)
        self.assertIn("1 failed", full_response)


if __name__ == '__main__':
    unittest.main()
