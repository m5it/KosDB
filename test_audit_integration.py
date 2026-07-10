"""
Audit Logging Integration Tests for KosDB v3.1.0

Tests that audit logging captures all operations correctly.
"""

import unittest
import subprocess
import time
import os
import tempfile
import shutil
import json
import socket
import glob
from pathlib import Path


class TestAuditIntegration(unittest.TestCase):
    """Integration tests for audit logging functionality."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment with audit logging enabled."""
        cls.temp_dir = tempfile.mkdtemp()
        cls.data_dir = os.path.join(cls.temp_dir, 'data')
        cls.audit_dir = os.path.join(cls.temp_dir, 'audit_logs')
        os.makedirs(cls.data_dir, exist_ok=True)
        os.makedirs(cls.audit_dir, exist_ok=True)
        
        # Create server config with audit logging enabled
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
        """Create server configuration with audit logging enabled."""
        config = {
            "version": "3.1.0",
            "server": {
                "host": "127.0.0.1",
                "port": 19995,
                "data_dir": cls.data_dir,
                "server_id": 1
            },
            "audit_logging": {
                "enabled": True,
                "log_dir": cls.audit_dir,
                "max_size_mb": 10,
                "max_age_days": 30,
                "compress": False,
                "targets": ["file"],
                "exclude_commands": ["PING"],
                "mask_commands": ["PASS", "PASSWORD"]
            }
        }
        
        with open(cls.config_path, 'w') as f:
            json.dump(config, f, indent=2)
    
    def setUp(self):
        """Start server before each test."""
        # Clear old audit logs
        for f in glob.glob(os.path.join(self.audit_dir, '*.jsonl')):
            os.remove(f)
        
        self.server_process = subprocess.Popen(
            ['python', 'server.py', '-c', self.config_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        
        # Wait for server to start
        time.sleep(2)
        
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
        with socket.create_connection(('127.0.0.1', 19995)) as sock:
            sock.send(f"{command}\n".encode())
            return sock.recv(4096).decode().strip()
    
    def _get_audit_logs(self):
        """Read all audit log entries."""
        logs = []
        for log_file in glob.glob(os.path.join(self.audit_dir, '*.jsonl')):
            with open(log_file, 'r') as f:
                for line in f:
                    if line.strip():
                        logs.append(json.loads(line))
        return logs
    
    def test_connection_audit_logged(self):
        """Test that connections are logged."""
        # Connect to server
        with socket.create_connection(('127.0.0.1', 19995)) as sock:
            sock.recv(1024)  # Read banner
        
        # Give time for async logging
        time.sleep(1)
        
        # Check audit logs
        logs = self._get_audit_logs()
        connect_logs = [log for log in logs if log.get('command_type') == 'CONNECT']
        
        self.assertGreaterEqual(len(connect_logs), 1)
        self.assertEqual(connect_logs[0]['user'], 'anonymous')
        self.assertEqual(connect_logs[0]['action'], 'AUTHENTICATION')
    
    def test_authentication_audit_logged(self):
        """Test that authentication attempts are logged."""
        # Attempt authentication
        self._send_command("USER testuser")
        self._send_command("PASS wrongpassword")
        
        time.sleep(1)
        
        # Check audit logs
        logs = self._get_audit_logs()
        auth_logs = [log for log in logs if log.get('command_type') in ['USER', 'PASS']]
        
        self.assertGreaterEqual(len(auth_logs), 2)
        
        # Check PASS is masked
        pass_logs = [log for log in auth_logs if log.get('command_type') == 'PASS']
        for log in pass_logs:
            self.assertEqual(log.get('command'), '[MASKED]')
    
    def test_database_operations_logged(self):
        """Test that database operations are logged."""
        # Authenticate first
        self._send_command("USER admin")
        self._send_command("PASS admin123")
        
        # Perform operations
        self._send_command("CREATE DATABASE audit_test")
        self._send_command("USE audit_test")
        self._send_command("CREATE TABLE test_table (id INT, name TEXT)")
        self._send_command("INSERT INTO test_table VALUES (1, 'test')")
        self._send_command("SELECT * FROM test_table")
        
        time.sleep(1)
        
        # Check audit logs
        logs = self._get_audit_logs()
        
        # Find specific operations
        commands = [log.get('command_type') for log in logs]
        
        self.assertIn('CREATE_DB', commands)
        self.assertIn('USE', commands)
        self.assertIn('CREATE', commands)
        self.assertIn('INSERT', commands)
        self.assertIn('SELECT', commands)
        
        # Check execution time is recorded
        for log in logs:
            if log.get('command_type') == 'SELECT':
                self.assertIn('execution_time_ms', log)
                self.assertGreaterEqual(log['execution_time_ms'], 0)
    
    def test_failed_operations_logged(self):
        """Test that failed operations are logged with error details."""
        # Authenticate
        self._send_command("USER admin")
        self._send_command("PASS admin123")
        
        # Try invalid operation
        self._send_command("SELECT * FROM nonexistent_table")
        
        time.sleep(1)
        
        # Check audit logs
        logs = self._get_audit_logs()
        error_logs = [log for log in logs if log.get('success') == False]
        
        self.assertGreaterEqual(len(error_logs), 1)
        for log in error_logs:
            self.assertIn('error_message', log)
    
    def test_excluded_commands_not_logged(self):
        """Test that excluded commands are not logged."""
        # Send PING (should be excluded)
        self._send_command("PING")
        
        time.sleep(1)
        
        # Check audit logs - PING should not appear
        logs = self._get_audit_logs()
        ping_logs = [log for log in logs if log.get('command_type') == 'PING']
        
        self.assertEqual(len(ping_logs), 0)
    
    def test_sensitive_data_masked(self):
        """Test that sensitive commands are masked."""
        # Authenticate
        self._send_command("USER admin")
        
        # Send PASS command
        self._send_command("PASS verysecretpassword123")
        
        time.sleep(1)
        
        # Check audit logs
        logs = self._get_audit_logs()
        pass_logs = [log for log in logs if log.get('command_type') == 'PASS']
        
        self.assertEqual(len(pass_logs), 1)
        self.assertEqual(pass_logs[0]['command'], '[MASKED]')
        self.assertNotIn('verysecretpassword', json.dumps(pass_logs[0]))
    
    def test_session_tracking(self):
        """Test that session IDs track user sessions."""
        # Connect and authenticate
        self._send_command("USER admin")
        self._send_command("PASS admin123")
        
        # Perform multiple operations
        self._send_command("CREATE DATABASE session_test")
        self._send_command("USE session_test")
        
        time.sleep(1)
        
        # Check audit logs
        logs = self._get_audit_logs()
        
        # All logs from same session should have same session_id
        session_logs = [log for log in logs if log.get('user') == 'admin']
        if len(session_logs) > 1:
            session_ids = set(log.get('session_id') for log in session_logs)
            self.assertEqual(len(session_ids), 1)
    
    def test_audit_log_format(self):
        """Test that audit logs have correct format."""
        # Perform operation
        self._send_command("USER admin")
        
        time.sleep(1)
        
        # Check audit log format
        logs = self._get_audit_logs()
        self.assertGreater(len(logs), 0)
        
        log = logs[0]
        required_fields = [
            'timestamp', 'event_id', 'user', 'client_ip',
            'action', 'command', 'command_type', 'success',
            'execution_time_ms', 'session_id'
        ]
        
        for field in required_fields:
            self.assertIn(field, log, f"Missing field: {field}")
        
        # Validate timestamp format
        self.assertRegex(log['timestamp'], r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}')
        
        # Validate event_id format
        self.assertEqual(len(log['event_id']), 16)
    
    def test_disconnection_logged(self):
        """Test that disconnections are logged."""
        # Connect
        sock = socket.create_connection(('127.0.0.1', 19995))
        sock.recv(1024)  # Banner
        
        # Disconnect
        sock.close()
        
        time.sleep(1)
        
        # Check audit logs
        logs = self._get_audit_logs()
        disconnect_logs = [log for log in logs if log.get('command_type') == 'DISCONNECT']
        
        self.assertGreaterEqual(len(disconnect_logs), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
