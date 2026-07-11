#!/usr/bin/env python3
"""
Core integration tests for the LevelDB socket server.

Covers authentication, databases, tables, CRUD, transactions, and basic
replication commands using the integration harness.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.integration_harness import ServerHarness


class TestIntegrationCore(unittest.TestCase):
    """Integration tests using a real server instance."""

    @classmethod
    def setUpClass(cls):
        cls.harness = ServerHarness(admin_user="admin", admin_password="adminpass")
        cls.harness.start()

    @classmethod
    def tearDownClass(cls):
        cls.harness.stop()

    def test_authentication_success(self):
        """Admin credentials are accepted."""
        with self.harness.connect() as sock:
            response = self.harness.authenticate(sock)
            self.assertTrue(response.startswith("OK"), response)

    def test_authentication_failure(self):
        """Invalid password is rejected."""
        with self.harness.connect() as sock:
            for _ in range(6):
                self.harness._read_line(sock)

            sock.sendall(b"USER admin\n")
            self.harness._read_line(sock)

            sock.sendall(b"PASS wrongpass\n")
            response = self.harness._read_line(sock)
            self.assertTrue(response.startswith("ERROR"), response)

    def test_database_lifecycle(self):
        """CREATE DATABASE, USE, SHOW DATABASES, DROP DATABASE work."""
        db_name = "test_db_lifecycle"
        results = self.harness.run_commands([
            f"CREATE DATABASE {db_name}",
            f"USE {db_name}",
            "SHOW DATABASES",
            f"DROP DATABASE {db_name}",
            "SHOW DATABASES",
        ])

        self.assertTrue(results[0].startswith("OK") or "already exists" in results[0], results[0])
        self.assertTrue(results[1].startswith("Switched") or results[1].startswith("OK"), results[1])
        self.assertIn(db_name, results[2], results[2])
        self.assertTrue(results[3].startswith("OK"), results[3])
        self.assertNotIn(db_name, results[4], results[4])

    def test_table_lifecycle(self):
        """CREATE TABLE, SHOW TABLES, DROP TABLE work inside a database."""
        db_name = "test_table_lifecycle"
        table_name = "items"
        results = self.harness.run_commands([
            f"CREATE DATABASE {db_name}",
            f"USE {db_name}",
            f"CREATE TABLE {table_name} (id INT PRIMARY KEY, name TEXT)",
            "SHOW TABLES",
            f"DROP TABLE {table_name}",
            "SHOW TABLES",
            f"DROP DATABASE {db_name}",
        ])

        self.assertTrue(results[0].startswith("OK") or "already exists" in results[0], results[0])
        self.assertTrue(results[1].startswith("Switched") or results[1].startswith("OK"), results[1])
        self.assertTrue(results[2].startswith("OK"), results[2])
        self.assertIn(table_name, results[3], results[3])
        self.assertTrue(results[4].startswith("OK"), results[4])
        self.assertNotIn(table_name, results[5], results[5])
        self.assertTrue(results[6].startswith("OK"), results[6])

    def test_crud_operations(self):
        """INSERT, SELECT, UPDATE, DELETE work as expected."""
        db_name = "test_crud"
        table_name = "users"
        results = self.harness.run_commands([
            f"CREATE DATABASE {db_name}",
            f"USE {db_name}",
            f"CREATE TABLE {table_name} (id INT PRIMARY KEY, name TEXT)",
            f"INSERT INTO {table_name} VALUES (1, 'Alice')",
            f"INSERT INTO {table_name} VALUES (2, 'Bob')",
            f"SELECT * FROM {table_name}",
            f"UPDATE {table_name} SET name='Charlie' WHERE id=1",
            f"SELECT name FROM {table_name} WHERE id=1",
            f"DELETE FROM {table_name} WHERE id=2",
            f"SELECT * FROM {table_name}",
            f"DROP TABLE {table_name}",
            f"DROP DATABASE {db_name}",
        ])

        self.assertTrue(results[2].startswith("OK"), results[2])
        self.assertTrue(results[3].startswith("OK"), results[3])
        self.assertTrue(results[4].startswith("OK"), results[4])
        self.assertIn("Alice", results[5], results[5])
        self.assertIn("Bob", results[5], results[5])
        self.assertTrue(results[6].startswith("OK"), results[6])
        self.assertIn("Charlie", results[7], results[7])
        self.assertTrue(results[8].startswith("OK"), results[8])
        self.assertNotIn("Bob", results[9], results[9])
        self.assertIn("Charlie", results[9], results[9])

    def test_transaction_commit(self):
        """BEGIN/COMMIT persist queued changes."""
        db_name = "test_tx_commit"
        table_name = "tx_test"
        results = self.harness.run_commands([
            f"CREATE DATABASE {db_name}",
            f"USE {db_name}",
            f"CREATE TABLE {table_name} (id INT PRIMARY KEY, value TEXT)",
            "BEGIN",
            f"INSERT INTO {table_name} VALUES (1, 'committed')",
            "COMMIT",
            f"SELECT * FROM {table_name}",
            f"DROP TABLE {table_name}",
            f"DROP DATABASE {db_name}",
        ])

        self.assertTrue(results[3].startswith("OK"), results[3])
        self.assertTrue(results[5].startswith("OK"), results[5])
        self.assertIn("committed", results[6], results[6])

    def test_transaction_rollback(self):
        """BEGIN/ROLLBACK discards queued changes."""
        db_name = "test_tx_rollback"
        table_name = "tx_test"
        results = self.harness.run_commands([
            f"CREATE DATABASE {db_name}",
            f"USE {db_name}",
            f"CREATE TABLE {table_name} (id INT PRIMARY KEY, value TEXT)",
            "BEGIN",
            f"INSERT INTO {table_name} VALUES (1, 'rolledback')",
            "ROLLBACK",
            f"SELECT * FROM {table_name}",
            f"DROP TABLE {table_name}",
            f"DROP DATABASE {db_name}",
        ])

        self.assertTrue(results[3].startswith("OK"), results[3])
        self.assertTrue(results[5].startswith("OK"), results[5])
        self.assertEqual(results[6].strip(), "Empty set", results[6])

    def test_basic_replication_status(self):
        """SHOW MASTER STATUS returns binlog information for admin users."""
        with self.harness.connect() as sock:
            self.harness.authenticate(sock)
            sock.sendall(b"SHOW MASTER STATUS\n")
            response = self.harness._read_response(sock)
            self.assertIn("Master Status", response, response)
            self.assertIn("Binlog Position", response, response)

if __name__ == "__main__":
    unittest.main()
