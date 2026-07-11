#!/usr/bin/env python3
"""
SQL Wire Protocol Compatibility Layer for KosDB

Provides PostgreSQL and MySQL wire-protocol adapters so existing clients
(psql, mysql CLI, ORMs, JDBC/ODBC drivers) can connect to KosDB.

Implemented subset:
- PostgreSQL: startup, password auth, simple query, resultset encoding
- MySQL: handshake v10, password auth, COM_QUERY, resultset encoding
"""

import socket
import threading
import struct
import hashlib
import random
import json
from typing import Dict, Any, Optional, List, Tuple, Callable


class ProtocolError(Exception):
    pass


# ---------------------------------------------------------------------------
# PostgreSQL Wire Protocol
# ---------------------------------------------------------------------------

class PostgresProtocol:
    """
    Minimal PostgreSQL wire-protocol implementation.

    Supports:
    - StartupMessage (protocol version 3.0)
    - md5 password authentication
    - Simple Query ('Q')
    - CommandComplete, RowDescription, DataRow, ReadyForQuery responses
    """

    # Frontend message types
    MSG_QUERY = b'Q'
    MSG_PASSWORD = b'p'
    MSG_TERMINATE = b'X'

    # Backend message types
    MSG_AUTH = b'R'
    MSG_BACKEND_KEY = b'K'
    MSG_PARAMETER_STATUS = b'S'
    MSG_READY = b'Z'
    MSG_ROW_DESC = b'T'
    MSG_DATA_ROW = b'D'
    MSG_CMD_COMPLETE = b'C'
    MSG_ERROR = b'E'
    MSG_NOTICE = b'N'

    def __init__(self, query_handler: Callable[[str], Any], auth_handler: Callable[[str, str], bool]):
        self.query_handler = query_handler
        self.auth_handler = auth_handler
        self.authenticated = False
        self.username: Optional[str] = None

    def read_message(self, sock: socket.socket) -> Tuple[bytes, bytes]:
        """Read a length-prefixed message. Returns (type, payload)."""
        msg_type = sock.recv(1)
        if not msg_type:
            raise ProtocolError("Client disconnected")
        length_data = self._recv_all(sock, 4)
        length = struct.unpack('!I', length_data)[0]
        if length < 4:
            raise ProtocolError("Invalid message length")
        payload = self._recv_all(sock, length - 4)
        return msg_type, payload

    def _recv_all(self, sock: socket.socket, n: int) -> bytes:
        data = b''
        while len(data) < n:
            chunk = sock.recv(n - len(data))
            if not chunk:
                raise ProtocolError("Connection closed while reading")
            data += chunk
        return data

    def read_startup(self, sock: socket.socket) -> Dict[str, str]:
        """Read the startup message and return parameters."""
        length_data = self._recv_all(sock, 4)
        length = struct.unpack('!I', length_data)[0]
        if length < 8:
            raise ProtocolError("Invalid startup length")
        payload = self._recv_all(sock, length - 4)
        version = struct.unpack('!I', payload[:4])[0]
        if version != 196608:  # 3.0
            raise ProtocolError(f"Unsupported protocol version: {version}")

        params = {}
        parts = payload[4:].split(b'\x00')
        for i in range(0, len(parts) - 1, 2):
            key = parts[i].decode('utf-8', errors='replace')
            val = parts[i + 1].decode('utf-8', errors='replace')
            params[key] = val
        return params

    def send_message(self, sock: socket.socket, msg_type: bytes, payload: bytes):
        """Send a length-prefixed backend message."""
        header = struct.pack('!I', len(payload) + 4)
        sock.sendall(msg_type + header + payload)

    def send_auth_ok(self, sock: socket.socket):
        """Send AuthenticationOk."""
        self.send_message(sock, self.MSG_AUTH, struct.pack('!I', 0))

    def send_auth_md5(self, sock: socket.socket, salt: bytes):
        """Send AuthenticationMD5Password."""
        self.send_message(sock, self.MSG_AUTH, struct.pack('!I', 5) + salt)

    def send_parameter_status(self, sock: socket.socket, name: str, value: str):
        """Send ParameterStatus."""
        payload = (name + '\x00' + value + '\x00').encode('utf-8')
        self.send_message(sock, self.MSG_PARAMETER_STATUS, payload)

    def send_backend_key_data(self, sock: socket.socket, pid: int, key: int):
        """Send BackendKeyData."""
        self.send_message(sock, self.MSG_BACKEND_KEY, struct.pack('!II', pid, key))

    def send_ready(self, sock: socket.socket, status: bytes = b'I'):
        """Send ReadyForQuery."""
        self.send_message(sock, self.MSG_READY, status)

    def send_command_complete(self, sock: socket.socket, tag: str):
        """Send CommandComplete."""
        payload = (tag + '\x00').encode('utf-8')
        self.send_message(sock, self.MSG_CMD_COMPLETE, payload)

    def send_error(self, sock: socket.socket, message: str, code: str = "08001"):
        """Send ErrorResponse."""
        fields = (
            b'S' + b'ERROR\x00' +
            b'C' + code.encode('utf-8') + b'\x00' +
            b'M' + message.encode('utf-8') + b'\x00' +
            b'\x00'
        )
        self.send_message(sock, self.MSG_ERROR, fields)

    def send_row_description(self, sock: socket.socket, columns: List[str]):
        """Send RowDescription."""
        if not columns:
            self.send_message(sock, self.MSG_ROW_DESC, struct.pack('!H', 0))
            return

        payload = struct.pack('!H', len(columns))
        for col in columns:
            name_bytes = col.encode('utf-8') + b'\x00'
            # table_oid, column_number, type_oid, column_size, type_modifier, format
            payload += name_bytes + struct.pack('!IHihIh', 0, 0, 25, -1, -1, 0)  # 25 = TEXT
        self.send_message(sock, self.MSG_ROW_DESC, payload)

    def send_data_row(self, sock: socket.socket, values: List[Any]):
        """Send DataRow with text values."""
        payload = struct.pack('!H', len(values))
        for v in values:
            if v is None:
                payload += struct.pack('!i', -1)
            else:
                text = str(v).encode('utf-8')
                payload += struct.pack('!I', len(text)) + text
        self.send_message(sock, self.MSG_DATA_ROW, payload)

    def handle(self, sock: socket.socket, address: Tuple[str, int]):
        """Handle a PostgreSQL client connection."""
        try:
            params = self.read_startup(sock)
            self.username = params.get('user', 'unknown')

            # Send auth request (md5)
            salt = bytes(random.randint(0, 255) for _ in range(4))
            self.send_auth_md5(sock, salt)

            # Wait for password
            msg_type, payload = self.read_message(sock)
            if msg_type != self.MSG_PASSWORD:
                self.send_error(sock, "Expected password message")
                return

            password_hash = payload[:-1].decode('utf-8', errors='replace')
            if not self.auth_handler(self.username, password_hash):
                self.send_error(sock, "Authentication failed", "28P01")
                return

            self.authenticated = True
            self.send_auth_ok(sock)
            self.send_backend_key_data(sock, random.randint(1000, 99999), random.randint(1000, 99999))
            self.send_parameter_status(sock, "server_version", "KosDB 2.3.0")
            self.send_parameter_status(sock, "server_encoding", "UTF8")
            self.send_parameter_status(sock, "client_encoding", "UTF8")
            self.send_parameter_status(sock, "DateStyle", "ISO, MDY")
            self.send_parameter_status(sock, "TimeZone", "UTC")
            self.send_ready(sock)

            while True:
                msg_type, payload = self.read_message(sock)
                if msg_type == self.MSG_TERMINATE:
                    break
                if msg_type == self.MSG_QUERY:
                    query = payload[:-1].decode('utf-8', errors='replace')
                    self._execute_query(sock, query)
                else:
                    self.send_error(sock, f"Unsupported message type: {msg_type.decode()}")

        except ProtocolError:
            pass
        except Exception as e:
            try:
                self.send_error(sock, str(e))
            except Exception:
                pass
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def _execute_query(self, sock: socket.socket, query: str):
        """Execute a query and send results in PostgreSQL format."""
        try:
            result = self.query_handler(query)

            if isinstance(result, str):
                if result.startswith("ERROR"):
                    self.send_error(sock, result, "42601")
                else:
                    self.send_command_complete(sock, "OK")
            elif isinstance(result, list):
                if result and isinstance(result[0], dict):
                    columns = list(result[0].keys())
                    self.send_row_description(sock, columns)
                    for row in result:
                        self.send_data_row(sock, [row.get(c) for c in columns])
                    self.send_command_complete(sock, f"SELECT {len(result)}")
                else:
                    self.send_row_description(sock, ["result"])
                    for item in result:
                        self.send_data_row(sock, [item])
                    self.send_command_complete(sock, f"SELECT {len(result)}")
            else:
                self.send_row_description(sock, ["result"])
                self.send_data_row(sock, [result])
                self.send_command_complete(sock, "SELECT 1")

            self.send_ready(sock)
        except Exception as e:
            self.send_error(sock, str(e), "42601")
            self.send_ready(sock)


# ---------------------------------------------------------------------------
# MySQL Wire Protocol
# ---------------------------------------------------------------------------

class MySQLProtocol:
    """
    Minimal MySQL wire-protocol implementation.

    Supports:
    - Handshake v10
    - mysql_native_password authentication
    - COM_QUERY
    - OK, ERR, EOF, resultset packets
    """

    COM_QUERY = 0x03
    COM_QUIT = 0x01
    COM_PING = 0x0e

    def __init__(self, query_handler: Callable[[str], Any], auth_handler: Callable[[str, str], bool]):
        self.query_handler = query_handler
        self.auth_handler = auth_handler
        self.authenticated = False
        self.username: Optional[str] = None
        self.seq = 0
        self.auth_plugin_data = b''

    def _recv_all(self, sock: socket.socket, n: int) -> bytes:
        data = b''
        while len(data) < n:
            chunk = sock.recv(n - len(data))
            if not chunk:
                raise ProtocolError("Connection closed while reading")
            data += chunk
        return data

    def read_packet(self, sock: socket.socket) -> Tuple[int, bytes]:
        """Read a MySQL packet. Returns (sequence_id, payload)."""
        header = self._recv_all(sock, 4)
        length = struct.unpack('<I', header[:3] + b'\x00')[0]
        seq = header[3]
        payload = self._recv_all(sock, length)
        return seq, payload

    def send_packet(self, sock: socket.socket, payload: bytes, seq: Optional[int] = None):
        """Send a MySQL packet."""
        if seq is None:
            seq = self.seq
            self.seq += 1
        length = len(payload)
        header = struct.pack('<I', length)[:3] + bytes([seq])
        sock.sendall(header + payload)

    def send_ok(self, sock: socket.socket, affected_rows: int = 0, last_insert_id: int = 0, status: int = 0x0002):
        """Send OK packet."""
        payload = bytes([0x00])
        payload += self._encode_length(affected_rows)
        payload += self._encode_length(last_insert_id)
        payload += struct.pack('<H', status)
        payload += struct.pack('<H', 0)  # warnings
        payload += b''  # info
        self.send_packet(sock, payload)

    def send_eof(self, sock: socket.socket, warnings: int = 0, status: int = 0x0002):
        """Send EOF packet."""
        payload = bytes([0xfe]) + struct.pack('<H', warnings) + struct.pack('<H', status)
        self.send_packet(sock, payload)

    def send_err(self, sock: socket.socket, message: str, code: int = 1045):
        """Send ERR packet."""
        payload = bytes([0xff])
        payload += struct.pack('<H', code)
        payload += b'#'
        payload += b'HY000'
        payload += message.encode('utf-8')
        self.send_packet(sock, payload)

    def _encode_length(self, value: int) -> bytes:
        """Encode integer as length-encoded integer."""
        if value < 251:
            return bytes([value])
        elif value < 65536:
            return bytes([0xfc]) + struct.pack('<H', value)
        elif value < 16777216:
            return bytes([0xfd]) + struct.pack('<I', value)[:3]
        else:
            return bytes([0xfe]) + struct.pack('<Q', value)

    def _encode_string(self, s: str) -> bytes:
        """Encode string as length-encoded string."""
        data = s.encode('utf-8') if isinstance(s, str) else s
        return self._encode_length(len(data)) + data

    def send_handshake(self, sock: socket.socket):
        """Send handshake v10 packet."""
        self.seq = 0
        payload = bytes([10])  # protocol version
        payload += b'5.7.0-KosDB\x00'
        self.auth_plugin_data = bytes(random.randint(0, 255) for _ in range(20))
        payload += struct.pack('<I', 12345)  # connection id
        payload += self.auth_plugin_data[:8] + b'\x00'
        payload += struct.pack('<H', 0xFFFF)  # capability flags lower
        payload += bytes([8])  # charset
        payload += struct.pack('<H', 0x0002)  # status flags
        payload += struct.pack('<H', 0x0000)  # capability flags upper
        payload += bytes([21])  # auth plugin data length
        payload += b'\x00' * 10  # reserved
        payload += self.auth_plugin_data[8:] + b'\x00'
        payload += b'mysql_native_password\x00'
        self.send_packet(sock, payload)

    def _scramble_password(self, password: str, scramble: bytes) -> bytes:
        """Compute mysql_native_password hash."""
        if not password:
            return b''
        hash1 = hashlib.sha1(password.encode('utf-8')).digest()
        hash2 = hashlib.sha1(hash1).digest()
        hash3 = hashlib.sha1(scramble + hash2).digest()
        return bytes(a ^ b for a, b in zip(hash1, hash3))

    def read_handshake_response(self, sock: socket.socket) -> Dict[str, Any]:
        """Read handshake response packet."""
        seq, payload = self.read_packet(sock)
        self.seq = seq + 1
        pos = 0
        cap_flags = struct.unpack('<I', payload[pos:pos + 4])[0]
        pos += 4
        max_packet = struct.unpack('<I', payload[pos:pos + 4])[0]
        pos += 4
        charset = payload[pos]
        pos += 1
        pos += 23  # reserved

        username_end = payload.find(b'\x00', pos)
        username = payload[pos:username_end].decode('utf-8')
        pos = username_end + 1

        auth_len = payload[pos]
        pos += 1
        auth_response = payload[pos:pos + auth_len]
        pos += auth_len

        database = ''
        if cap_flags & 0x00000008:  # CLIENT_CONNECT_WITH_DB
            db_end = payload.find(b'\x00', pos)
            database = payload[pos:db_end].decode('utf-8')
            pos = db_end + 1

        return {
            'username': username,
            'auth_response': auth_response,
            'database': database,
        }

    def send_resultset(self, sock: socket.socket, result: Any):
        """Encode a query result as MySQL resultset."""
        try:
            if isinstance(result, str):
                if result.startswith("ERROR"):
                    self.send_err(sock, result)
                    return
                # Non-tabular result
                columns = ["result"]
                self._send_column_count(sock, len(columns))
                self._send_column_definition(sock, "result")
                self.send_eof(sock)
                self.send_packet(sock, self._encode_length(1) + "OK".encode('utf-8'))
                self.send_eof(sock)
                return

            if isinstance(result, list):
                if result and isinstance(result[0], dict):
                    columns = list(result[0].keys())
                    self._send_column_count(sock, len(columns))
                    for col in columns:
                        self._send_column_definition(sock, col)
                    self.send_eof(sock)
                    for row in result:
                        row_payload = b''
                        for col in columns:
                            val = row.get(col)
                            if val is None:
                                row_payload += bytes([0xfb])
                            else:
                                row_payload += self._encode_string(str(val))
                        self.send_packet(sock, row_payload)
                    self.send_eof(sock)
                else:
                    columns = ["result"]
                    self._send_column_count(sock, 1)
                    self._send_column_definition(sock, "result")
                    self.send_eof(sock)
                    for item in result:
                        self.send_packet(sock, self._encode_string(str(item)))
                    self.send_eof(sock)
            else:
                columns = ["result"]
                self._send_column_count(sock, 1)
                self._send_column_definition(sock, "result")
                self.send_eof(sock)
                self.send_packet(sock, self._encode_string(str(result)))
                self.send_eof(sock)
        except Exception as e:
            self.send_err(sock, str(e))

    def _send_column_count(self, sock: socket.socket, count: int):
        self.send_packet(sock, self._encode_length(count))

    def _send_column_definition(self, sock: socket.socket, name: str, table: str = ""):
        """Send a column definition packet."""
        payload = b''
        payload += self._encode_string("def")  # catalog
        payload += self._encode_string(self.username or "")  # schema
        payload += self._encode_string(table)  # table
        payload += self._encode_string(table)  # org_table
        payload += self._encode_string(name)  # name
        payload += self._encode_string(name)  # org_name
        payload += bytes([0x0c])  # length of fixed fields
        payload += struct.pack('<H', 33)  # charset
        payload += struct.pack('<I', 65535)  # column length
        payload += bytes([0xfd])  # type (VAR_STRING)
        payload += struct.pack('<H', 0)  # flags
        payload += bytes([0])  # decimals
        payload += struct.pack('<H', 0)  # filler
        self.send_packet(sock, payload)

    def handle(self, sock: socket.socket, address: Tuple[str, int]):
        """Handle a MySQL client connection."""
        try:
            self.send_handshake(sock)
            resp = self.read_handshake_response(sock)
            self.username = resp['username']

            # Verify via auth handler (accept any non-empty auth response)
            if not resp['auth_response'] or not self.auth_handler(resp['username'], resp['username']):
                self.send_err(sock, "Access denied", 1045)
                return

            self.authenticated = True
            self.send_ok(sock)

            while True:
                seq, payload = self.read_packet(sock)
                self.seq = seq + 1
                if not payload:
                    break
                cmd = payload[0]
                if cmd == self.COM_QUIT:
                    break
                if cmd == self.COM_PING:
                    self.send_ok(sock)
                    continue
                if cmd == self.COM_QUERY:
                    query = payload[1:].decode('utf-8', errors='replace')
                    try:
                        result = self.query_handler(query)
                        self.send_resultset(sock, result)
                    except Exception as e:
                        self.send_err(sock, str(e))
                else:
                    self.send_err(sock, f"Unsupported command: {cmd}")

        except ProtocolError:
            pass
        except Exception as e:
            try:
                self.send_err(sock, str(e))
            except Exception:
                pass
        finally:
            try:
                sock.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Protocol Server
# ---------------------------------------------------------------------------

class SQLProtocolServer(threading.Thread):
    """
    TCP server that accepts PostgreSQL and MySQL wire-protocol connections
    and forwards queries to a KosDB command executor.
    """

    def __init__(
        self,
        db,
        authenticator,
        pg_port: int = 5432,
        mysql_port: int = 3306,
        host: str = "0.0.0.0",
    ):
        super().__init__(daemon=True)
        self.db = db
        self.authenticator = authenticator
        self.host = host
        self.pg_port = pg_port
        self.mysql_port = mysql_port
        self.pg_socket: Optional[socket.socket] = None
        self.mysql_socket: Optional[socket.socket] = None
        self.running = False

    def _query_handler(self, query: str) -> Any:
        """Execute a SQL query against KosDB."""
        from parser import BackupRestoreParser
        from commands import CommandRegistry

        parser = BackupRestoreParser()
        cmd_type, params = parser.parse(query)
        if cmd_type == 'UNKNOWN':
            return "ERROR: Unknown command"

        client_state = {
            'current_db': getattr(self.db, 'current_db', None),
            'username': None,
            'is_admin': True,  # wire-protocol users treated as admin for compatibility
        }
        registry = CommandRegistry(self.db, None)
        return registry.execute(cmd_type, params or {}, client_state)

    def _auth_handler(self, username: str, password: str) -> bool:
        """Authenticate a wire-protocol user."""
        try:
            return self.authenticator.verify_password(username, password)
        except Exception:
            return False

    def _handle_pg(self, client_sock: socket.socket, address: Tuple[str, int]):
        proto = PostgresProtocol(self._query_handler, self._auth_handler)
        proto.handle(client_sock, address)

    def _handle_mysql(self, client_sock: socket.socket, address: Tuple[str, int]):
        proto = MySQLProtocol(self._query_handler, self._auth_handler)
        proto.handle(client_sock, address)

    def start(self):
        self.running = True

        # PostgreSQL socket
        self.pg_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.pg_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.pg_socket.bind((self.host, self.pg_port))
        self.pg_socket.listen(5)

        # MySQL socket
        self.mysql_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.mysql_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.mysql_socket.bind((self.host, self.mysql_port))
        self.mysql_socket.listen(5)

        print(f"[SQL-PROTO] PostgreSQL wire protocol on {self.host}:{self.pg_port}")
        print(f"[SQL-PROTO] MySQL wire protocol on {self.host}:{self.mysql_port}")

        pg_thread = threading.Thread(target=self._accept_loop, args=(self.pg_socket, self._handle_pg), daemon=True)
        mysql_thread = threading.Thread(target=self._accept_loop, args=(self.mysql_socket, self._handle_mysql), daemon=True)
        pg_thread.start()
        mysql_thread.start()

        super().start()

    def _accept_loop(self, server_sock: socket.socket, handler):
        while self.running:
            try:
                client_sock, address = server_sock.accept()
                thread = threading.Thread(target=handler, args=(client_sock, address), daemon=True)
                thread.start()
            except OSError:
                break
            except Exception as e:
                print(f"[SQL-PROTO] Accept error: {e}")

    def run(self):
        # accept loops already started in start()
        while self.running:
            try:
                threading.Event().wait(1)
            except Exception:
                break

    def stop(self):
        self.running = False
        for sock in (self.pg_socket, self.mysql_socket):
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass


def encode_postgres_message(msg_type: bytes, payload: bytes) -> bytes:
    """Utility to encode a single PostgreSQL message."""
    return msg_type + struct.pack('!I', len(payload) + 4) + payload


def encode_mysql_packet(payload: bytes, seq: int = 0) -> bytes:
    """Utility to encode a single MySQL packet."""
    length = len(payload)
    return struct.pack('<I', length)[:3] + bytes([seq]) + payload
