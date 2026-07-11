#!/usr/bin/env python3
"""
INSERT/SELECT value round-trip test against a running server on localhost:9999.

Connects as admin/admin, creates a temporary database and table, inserts rows
with INT, TEXT, FLOAT, NULL-like and quoted string values, then SELECTs them
back and asserts the returned values match the inserted ones exactly.
"""

import socket
import unittest


HOST = 'localhost'
PORT = 9999
ADMIN_USER = 'admin'
ADMIN_PASSWORD = 'admin'


def _send(sock: socket.socket, command: str) -> None:
    """Send a single command line to the server."""
    sock.sendall((command + '\n').encode())


class _BufferedSocket:
    """Buffered line reader for the server's line-oriented protocol."""

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self._buffer = b""

    def read_line(self) -> str:
        """Read one newline-terminated line from the server."""
        while b"\n" not in self._buffer:
            data = self.sock.recv(4096)
            if not data:
                if self._buffer:
                    break
                raise ConnectionError("Server closed connection")
            self._buffer += data

        line, sep, self._buffer = self._buffer.partition(b"\n")
        return line.decode().strip()

    def read_response(self) -> str:
        """Read a complete command response until a terminator line."""
        lines = []
        while True:
            line = self.read_line()
            lines.append(line)

            # Single-line responses (INSERT, CREATE, USE, etc.) do not start
            # with the ASCII-table markers used by SELECT.
            if not line.startswith(("+", "|")):
                break

            # Multi-line SELECT results end with the row count footer.
            if "row(s) in set" in line:
                break
        return "\n".join(lines)


def _parse_select_response(text: str):
    """
    Parse the server's ASCII-table SELECT response into a list of row dicts.

    Numeric strings are converted back to int/float; the literal "NULL"
    becomes Python None.
    """
    rows = []
    headers = []
    for raw_line in text.strip().splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue

        cells = [cell.strip() for cell in line.split("|")[1:-1]]

        if not headers:
            headers = cells
            continue

        if len(cells) != len(headers):
            continue

        row = {}
        for header, cell in zip(headers, cells):
            if cell == "NULL":
                row[header] = None
                continue

            try:
                row[header] = int(cell)
                continue
            except ValueError:
                pass

            try:
                row[header] = float(cell)
                continue
            except ValueError:
                pass

            row[header] = cell

        rows.append(row)

    return rows


class TestInsertSelectValues(unittest.TestCase):
    """Value-roundtrip test against localhost:9999."""

    def _connect_and_auth(self):
        """Open a connection, consume the banner, and authenticate as admin."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((HOST, PORT))

        reader = _BufferedSocket(sock)

        # Consume the 6-line welcome banner
        for _ in range(6):
            reader.read_line()

        _send(sock, f"USER {ADMIN_USER}")
        response = reader.read_line()
        self.assertTrue(response.startswith("OK"), f"USER failed: {response}")

        _send(sock, f"PASS {ADMIN_PASSWORD}")
        response = reader.read_line()
        self.assertTrue(response.startswith("OK"), f"PASS failed: {response}")

        return reader

    def _run(self, commands):
        """Run a sequence of commands on a fresh authenticated connection."""
        reader = self._connect_and_auth()
        try:
            results = []
            for command in commands:
                _send(reader.sock, command)
                results.append(reader.read_response())
            return results
        finally:
            try:
                _send(reader.sock, "QUIT")
                reader.read_response()
            except Exception:
                pass
            reader.sock.close()

    def test_basic_types_roundtrip(self):
        """Integers, floats, text, booleans-as-text and NULL round-trip."""
        db_name = "test_values_roundtrip"
        table_name = "samples"

        results = self._run([
            f"CREATE DATABASE {db_name}",
            f"USE {db_name}",
            f"CREATE TABLE {table_name} ("
            f"id INT PRIMARY KEY, int_col INT, float_col FLOAT, text_col TEXT, "
            f"bool_col TEXT, null_col TEXT)",
            f"INSERT INTO {table_name} VALUES (1, 42, 3.14159, 'hello', 'TRUE', 'NULL')",
            f"INSERT INTO {table_name} VALUES (2, -7, -2.5, 'world', 'FALSE', NULL)",
            f"SELECT * FROM {table_name} ORDER BY id ASC",
            f"SELECT text_col FROM {table_name} WHERE id=1",
            f"DROP TABLE {table_name}",
            f"DROP DATABASE {db_name}",
        ])

        self.assertTrue(results[0].startswith("OK") or "already exists" in results[0], results[0])
        self.assertTrue(results[1].startswith("Switched") or results[1].startswith("OK"), results[1])
        self.assertTrue(results[2].startswith("OK"), results[2])
        self.assertTrue(results[3].startswith("OK"), results[3])
        self.assertTrue(results[4].startswith("OK"), results[4])

        rows = _parse_select_response(results[5])
        self.assertEqual(len(rows), 2, results[5])

        self.assertEqual(rows[0]["id"], 1)
        self.assertEqual(rows[0]["int_col"], 42)
        self.assertEqual(rows[0]["float_col"], 3.14159)
        self.assertEqual(rows[0]["text_col"], "hello")
        self.assertEqual(rows[0]["bool_col"], "TRUE")
        self.assertIsNone(rows[0]["null_col"])

        self.assertEqual(rows[1]["id"], 2)
        self.assertEqual(rows[1]["int_col"], -7)
        self.assertEqual(rows[1]["float_col"], -2.5)
        self.assertEqual(rows[1]["text_col"], "world")
        self.assertEqual(rows[1]["bool_col"], "FALSE")
        self.assertIsNone(rows[1]["null_col"])

        filtered = _parse_select_response(results[6])
        self.assertEqual(len(filtered), 1, results[6])
        self.assertEqual(filtered[0]["text_col"], "hello")

    def test_quoted_and_special_strings(self):
        """Quoted strings and special characters survive the round-trip."""
        db_name = "test_special_strings"
        table_name = "strings"

        # Avoid ) and | because the current parser/format uses them as delimiters.
        special = r'He said "Hello" and \\backslash\\ plus !@#$%^&*_+-=[]{};:,.<>?'

        results = self._run([
            f"CREATE DATABASE {db_name}",
            f"USE {db_name}",
            f"CREATE TABLE {table_name} (id INT PRIMARY KEY, value TEXT)",
            f"INSERT INTO {table_name} VALUES (1, 'single-quoted')",
            f'INSERT INTO {table_name} VALUES (2, "double-quoted")',
            f"INSERT INTO {table_name} VALUES (3, '{special}')",
            f"SELECT * FROM {table_name} ORDER BY id ASC",
            f"SELECT value FROM {table_name} WHERE id=3",
            f"DROP TABLE {table_name}",
            f"DROP DATABASE {db_name}",
        ])

        self.assertTrue(results[3].startswith("OK"), results[3])
        self.assertTrue(results[4].startswith("OK"), results[4])
        self.assertTrue(results[5].startswith("OK"), results[5])

        rows = _parse_select_response(results[6])
        self.assertEqual(len(rows), 3, results[6])
        self.assertEqual(rows[0]["value"], "single-quoted")
        self.assertEqual(rows[1]["value"], "double-quoted")
        self.assertEqual(rows[2]["value"], special)

        targeted = _parse_select_response(results[7])
        self.assertEqual(len(targeted), 1, results[7])
        self.assertEqual(targeted[0]["value"], special)

    def test_multiple_rows_and_negative_numbers(self):
        """Multiple rows and negative numeric values are preserved."""
        db_name = "test_multiple_rows"
        table_name = "numbers"

        results = self._run([
            f"CREATE DATABASE {db_name}",
            f"USE {db_name}",
            f"CREATE TABLE {table_name} (id INT PRIMARY KEY, n INT, f FLOAT)",
            f"INSERT INTO {table_name} VALUES (1, -100, -0.001)",
            f"INSERT INTO {table_name} VALUES (2, 0, 0.0)",
            f"INSERT INTO {table_name} VALUES (3, 999999, 1.797693e+308)",
            f"SELECT * FROM {table_name} ORDER BY id ASC",
            f"SELECT n, f FROM {table_name} WHERE id=2",
            f"DROP TABLE {table_name}",
            f"DROP DATABASE {db_name}",
        ])

        rows = _parse_select_response(results[6])
        self.assertEqual(len(rows), 3, results[6])

        self.assertEqual(rows[0]["id"], 1)
        self.assertEqual(rows[0]["n"], -100)
        self.assertEqual(rows[0]["f"], -0.001)

        self.assertEqual(rows[1]["id"], 2)
        self.assertEqual(rows[1]["n"], 0)
        self.assertEqual(rows[1]["f"], 0.0)

        self.assertEqual(rows[2]["id"], 3)
        self.assertEqual(rows[2]["n"], 999999)
        self.assertEqual(rows[2]["f"], 1.797693e308)

        targeted = _parse_select_response(results[7])
        self.assertEqual(len(targeted), 1, results[7])
        self.assertEqual(targeted[0]["n"], 0)
        self.assertEqual(targeted[0]["f"], 0.0)


if __name__ == "__main__":
    unittest.main()
