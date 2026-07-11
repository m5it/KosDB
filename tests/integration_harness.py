#!/usr/bin/env python3
"""
Integration test harness for the LevelDB socket server.

Provides helpers to start a server on a random free port, create an admin
user, authenticate a client connection, run a sequence of commands, and
cleanly stop the server.
"""

import os
import shutil
import socket
import tempfile
import threading
import time

import sys

# Ensure the project root is on the path when running from the tests directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import SocketServer
from database import Database


def _find_free_port(host="127.0.0.1"):
    """Return a random free TCP port on the given host."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


class ServerHarness:
    """Manages a SocketServer instance for integration tests."""

    def __init__(self, admin_user="admin", admin_password="adminpass"):
        self.host = "127.0.0.1"
        self.port = _find_free_port(self.host)
        self.data_dir = tempfile.mkdtemp(prefix="leveldb_test_")
        self.admin_user = admin_user
        self.admin_password = admin_password

        self._server = None
        self._server_thread = None

    def start(self):
        """Create admin user, start the server, and wait until it accepts connections."""
        # Prepare the admin user directly in the data directory.
        db = Database(self.data_dir)
        db.create_user(self.admin_user, self.admin_password, is_admin=True)
        db.close()

        self._server = SocketServer(
            host=self.host,
            port=self.port,
            data_dir=self.data_dir,
            server_id=1,
            role="master",
        )

        self._server_thread = threading.Thread(target=self._run_server, daemon=True)
        self._server_thread.start()

        # Wait until the server socket is accepting connections.
        self._wait_for_server(timeout=10)

    def _run_server(self):
        """Run the server."""
        self._server.start()

    def _wait_for_server(self, timeout=10):
        """Poll the server port until it accepts connections."""
        deadline = time.time() + timeout
        last_error = None
        while time.time() < deadline:
            try:
                with socket.create_connection((self.host, self.port), timeout=0.5):
                    return
            except (ConnectionRefusedError, OSError) as exc:
                last_error = exc
                time.sleep(0.05)
        raise RuntimeError(f"Server did not start on {self.host}:{self.port}: {last_error}")

    def stop(self):
        """Stop the server and remove the temporary data directory."""
        if self._server:
            self._server.stop()
        if self._server_thread:
            self._server_thread.join(timeout=5)

        # Best-effort cleanup of the data directory.
        try:
            shutil.rmtree(self.data_dir)
        except FileNotFoundError:
            pass

    def connect(self):
        """Return a raw, connected socket to the server."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((self.host, self.port))
        return sock

    @staticmethod
    def _read_line(sock):
        """Read a single line from the server."""
        chunks = []
        while True:
            chunk = sock.recv(1)
            if not chunk:
                break
            if chunk == b"\n":
                break
            chunks.append(chunk)
        return b"".join(chunks).decode().strip()

    @staticmethod
    def _read_response(sock, timeout=0.5):
        """Read a complete multi-line response up to a short quiet period."""
        sock.settimeout(timeout)
        chunks = []
        try:
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                chunks.append(data)
        except socket.timeout:
            pass
        return b"".join(chunks).decode().strip()

    def authenticate(self, sock, username=None, password=None):
        """
        Perform the USER/PASS handshake on an open socket.

        Consumes the server's initial banner messages. Returns the final
        authentication response string.
        """
        username = username or self.admin_user
        password = password or self.admin_password

        # Consume the initial banner lines sent by the server on connect.
        for _ in range(6):
            self._read_line(sock)

        sock.sendall(f"USER {username}\n".encode())
        self._read_line(sock)

        sock.sendall(f"PASS {password}\n".encode())
        return self._read_line(sock)

    def run_commands(self, commands, username=None, password=None):
        """
        Connect, authenticate, and run a sequence of commands.

        Args:
            commands: Iterable of command strings.
            username/password: Optional credentials (defaults to admin).

        Returns:
            List of response strings, one per command.
        """
        with self.connect() as sock:
            auth_response = self.authenticate(sock, username, password)
            if not auth_response.startswith("OK"):
                raise RuntimeError(f"Authentication failed: {auth_response}")

            results = []
            for command in commands:
                sock.sendall((command + "\n").encode())
                response = self._read_response(sock)
                results.append(response)
            return results
