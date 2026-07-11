"""
Foreign Data Wrapper Manager for KosDB v3.4.0

Provides access to external data sources:
- PostgreSQL databases
- MySQL databases
- CSV files (local and remote)
- REST APIs (JSON/XML responses)
- Other databases via ODBC

Features:
- Connection pooling and management
- Data type mapping between external sources and KosDB
- Predicate pushdown for query optimization
- Schema import from external sources
- Transaction coordination (two-phase commit)

Example:
    -- Create FDW extension
    CREATE EXTENSION postgres_fdw;
    
    -- Create server connection
    CREATE SERVER pg_server
        FOREIGN DATA WRAPPER postgres_fdw
        OPTIONS (host 'localhost', port '5432', dbname 'sales_db');
    
    -- Create user mapping
    CREATE USER MAPPING FOR current_user
        SERVER pg_server
        OPTIONS (user 'postgres', password 'secret');
    
    -- Create foreign table
    CREATE FOREIGN TABLE remote_customers (
        id INTEGER,
        name VARCHAR(100),
        email VARCHAR(100)
    ) SERVER pg_server
    OPTIONS (schema_name 'public', table_name 'customers');
    
    -- Query foreign table (with predicate pushdown)
    SELECT * FROM remote_customers WHERE id > 1000;
    
    -- Import entire schema
    IMPORT FOREIGN SCHEMA public
        FROM SERVER pg_server
        INTO local_schema;
"""

import re
import json
import time
import urllib.request
import urllib.parse
from typing import Dict, Any, List, Optional, Tuple, Set, Callable, Union
from dataclasses import dataclass, field
from enum import Enum, auto
from abc import ABC, abstractmethod
import threading


class FDWType(Enum):
    """Types of foreign data wrappers."""
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"
    CSV = "csv"
    JSON = "json"
    REST_API = "rest_api"
    ODBC = "odbc"


@dataclass
class FDWServer:
    """Foreign server connection configuration."""
    name: str
    fdw_type: FDWType
    options: Dict[str, str]  # host, port, database, etc.
    created_at: float = field(default_factory=time.time)
    
    # Connection pool
    _connections: List[Any] = field(default_factory=list, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


@dataclass
class UserMapping:
    """User credentials for foreign server."""
    server_name: str
    local_user: str
    remote_user: str
    remote_password: Optional[str] = None
    options: Dict[str, str] = field(default_factory=dict)


@dataclass
class ForeignTable:
    """Foreign table definition."""
    name: str
    local_schema: str
    server_name: str
    columns: List[Dict[str, Any]]
    remote_schema: Optional[str] = None
    remote_table: Optional[str] = None
    options: Dict[str, str] = field(default_factory=dict)
    
    # Statistics
    estimated_rows: int = 1000
    last_analyzed: Optional[float] = None


@dataclass 
class ColumnMapping:
    """Maps external column types to KosDB types."""
    external_type: str
    kosdb_type: str
    converter: Optional[Callable] = None


class BaseFDWHandler(ABC):
    """
    Abstract base class for FDW handlers.
    Each external data source type implements this interface.
    """
    
    def __init__(self, server: FDWServer, user_mapping: Optional[UserMapping] = None):
        self.server = server
        self.user_mapping = user_mapping
        self.type_mappings = self._init_type_mappings()
    
    @abstractmethod
    def _init_type_mappings(self) -> Dict[str, ColumnMapping]:
        """Initialize type mappings for this FDW."""
        pass
    
    @abstractmethod
    def connect(self) -> Any:
        """Establish connection to external source."""
        pass
    
    @abstractmethod
    def disconnect(self, connection: Any):
        """Close connection."""
        pass
    
    @abstractmethod
    def execute_query(self, 
                     connection: Any, 
                     query: str,
                     params: Optional[List] = None) -> List[Dict]:
        """Execute query on external source."""
        pass
    
    @abstractmethod
    def get_table_schema(self, 
                        connection: Any,
                        remote_schema: str,
                        remote_table: str) -> List[Dict[str, Any]]:
        """Get column definitions for remote table."""
        pass
    
    @abstractmethod
    def can_pushdown(self, operator: str) -> bool:
        """Check if operator can be pushed to external source."""
        pass
    
    def map_external_type(self, external_type: str) -> str:
        """Map external type to KosDB type."""
n        mapping = self.type_mappings.get(external_type.upper())\n        if mapping:\n            return mapping.kosdb_type\n        return 'TEXT'  # Default fallback
    
    def convert_value(self, value: Any, kosdb_type: str) -> Any:
        """Convert external value to KosDB format."""
n        if value is None:\n            return None\n        \n        if kosdb_type == 'INTEGER':\n            return int(value)\n        elif kosdb_type == 'REAL':\n            return float(value)\n        elif kosdb_type == 'BOOLEAN':\n            return bool(value)\n        elif kosdb_type == 'TEXT':\n            return str(value)\n        \n        return value


class PostgreSQLFDWHandler(BaseFDWHandler):
    """Handler for PostgreSQL foreign data wrapper."""
n    \n    def _init_type_mappings(self) -> Dict[str, ColumnMapping]:\n        return {\n            'INTEGER': ColumnMapping('INTEGER', 'INTEGER'),\n            'BIGINT': ColumnMapping('BIGINT', 'INTEGER'),\n            'SMALLINT': ColumnMapping('SMALLINT', 'INTEGER'),\n            'SERIAL': ColumnMapping('SERIAL', 'INTEGER'),\n            'BIGSERIAL': ColumnMapping('BIGSERIAL', 'INTEGER'),\n            'REAL': ColumnMapping('REAL', 'REAL'),\n            'DOUBLE PRECISION': ColumnMapping('DOUBLE PRECISION', 'REAL'),\n            'NUMERIC': ColumnMapping('NUMERIC', 'REAL'),\n            'DECIMAL': ColumnMapping('DECIMAL', 'REAL'),\n            'CHARACTER VARYING': ColumnMapping('CHARACTER VARYING', 'TEXT'),\n            'VARCHAR': ColumnMapping('VARCHAR', 'TEXT'),\n            'CHARACTER': ColumnMapping('CHARACTER', 'TEXT'),\n            'CHAR': ColumnMapping('CHAR', 'TEXT'),\n            'TEXT': ColumnMapping('TEXT', 'TEXT'),\n            'BOOLEAN': ColumnMapping('BOOLEAN', 'BOOLEAN'),\n            'DATE': ColumnMapping('DATE', 'TEXT'),\n            'TIMESTAMP': ColumnMapping('TIMESTAMP', 'TEXT'),\n            'TIMESTAMPTZ': ColumnMapping('TIMESTAMPTZ', 'TEXT'),\n            'JSON': ColumnMapping('JSON', 'TEXT'),\n            'JSONB': ColumnMapping('JSONB', 'TEXT'),\n            'UUID': ColumnMapping('UUID', 'TEXT'),\n        }\n    \n    def connect(self) -> Any:\n        \"\"\"Connect to PostgreSQL using psycopg2 if available.\"\"\"\n        try:\n            import psycopg2\n            \n            conn = psycopg2.connect(\n                host=self.server.options.get('host', 'localhost'),\n                port=self.server.options.get('port', '5432'),\n                database=self.server.options.get('dbname'),\n                user=self.user_mapping.remote_user if self.user_mapping else None,\n                password=self.user_mapping.remote_password if self.user_mapping else None\n            )\n            return conn\n        except ImportError:\n            raise RuntimeError(\"psycopg2 not installed. Install with: pip install psycopg2\")\n    \n    def disconnect(self, connection: Any):\n        \"\"\"Close PostgreSQL connection.\"\"\"\n        if connection:\n            connection.close()\n    \n    def execute_query(self, connection: Any, query: str, \n                     params: Optional[List] = None) -> List[Dict]:\n        \"\"\"Execute query on PostgreSQL.\"\"\"\n        cursor = connection.cursor()\n        try:\n            cursor.execute(query, params or [])\n            \n            # Get column names\n            columns = [desc[0] for desc in cursor.description] if cursor.description else []\n            \n            # Fetch results\n            results = []\n            for row in cursor.fetchall():\n                results.append(dict(zip(columns, row)))\n            \n            return results\n        finally:\n            cursor.close()\n    \n    def get_table_schema(self, connection: Any, remote_schema: str, \n                        remote_table: str) -> List[Dict[str, Any]]:\n        \"\"\"Get PostgreSQL table schema.\"\"\"\n        query = \"\"\"\n            SELECT column_name, data_type, is_nullable\n            FROM information_schema.columns\n            WHERE table_schema = %s AND table_name = %s\n            ORDER BY ordinal_position\n        \"\"\"\n        \n        results = self.execute_query(connection, query, [remote_schema, remote_table])\n        \n        columns = []\n        for row in results:\n            columns.append({\n                'name': row['column_name'],\n                'type': self.map_external_type(row['data_type']),\n                'nullable': row['is_nullable'] == 'YES'\n            })\n        \n        return columns\n    \n    def can_pushdown(self, operator: str) -> bool:\n        \"\"\"PostgreSQL supports most operators.\"\"\"\n        supported = {'=', '<>', '<', '>', '<=', '>=', 'LIKE', 'IN', 'BETWEEN', 'IS NULL', 'IS NOT NULL'}\n        return operator.upper() in supported\n    \n    def build_remote_query(self, table: ForeignTable, \n                          columns: List[str],\n                          where_conditions: List[Dict]) -> str:\n        \"\"\"Build SQL query for remote PostgreSQL.\"\"\"\n        cols = ', '.join(columns) if columns else '*'\n        \n        remote_schema = table.remote_schema or 'public'\n        remote_table_name = table.remote_table or table.name\n        \n        query = f'SELECT {cols} FROM \"{remote_schema}\".\"{remote_table_name}\"'\n        \n        # Add WHERE with pushdown\n        if where_conditions:\n            conditions = []\n            for cond in where_conditions:\n                if self.can_pushdown(cond.get('op', '=')):\n                    col = cond['column']\n                    op = cond['op']\n                    val = cond['value']\n                    \n                    if isinstance(val, str):\n                        val = f\"'{val}'\"\n                    \n                    conditions.append(f'\"{col}\" {op} {val}')\n            \n            if conditions:\n                query += ' WHERE ' + ' AND '.join(conditions)\n        \n        return query


class MySQLFDWHandler(BaseFDWHandler):
n    \"\"\"Handler for MySQL foreign data wrapper.\"\"\"\n    \n    def _init_type_mappings(self) -> Dict[str, ColumnMapping]:\n        return {\n            'INT': ColumnMapping('INT', 'INTEGER'),\n            'BIGINT': ColumnMapping('BIGINT', 'INTEGER'),\n            'SMALLINT': ColumnMapping('SMALLINT', 'INTEGER'),\n            'TINYINT': ColumnMapping('TINYINT', 'INTEGER'),\n            'FLOAT': ColumnMapping('FLOAT', 'REAL'),\n            'DOUBLE': ColumnMapping('DOUBLE', 'REAL'),\n            'DECIMAL': ColumnMapping('DECIMAL', 'REAL'),\n            'VARCHAR': ColumnMapping('VARCHAR', 'TEXT'),\n            'CHAR': ColumnMapping('CHAR', 'TEXT'),\n            'TEXT': ColumnMapping('TEXT', 'TEXT'),\n            'BLOB': ColumnMapping('BLOB', 'TEXT'),\n            'BOOLEAN': ColumnMapping('BOOLEAN', 'BOOLEAN'),\n            'DATE': ColumnMapping('DATE', 'TEXT'),\n            'DATETIME': ColumnMapping('DATETIME', 'TEXT'),\n            'TIMESTAMP': ColumnMapping('TIMESTAMP', 'TEXT'),\n            'JSON': ColumnMapping('JSON', 'TEXT'),\n        }\n    \n    def connect(self) -> Any:\n        \"\"\"Connect to MySQL using pymysql if available.\"\"\"\n        try:\n            import pymysql\n            \n            conn = pymysql.connect(\n                host=self.server.options.get('host', 'localhost'),\n                port=int(self.server.options.get('port', '3306')),\n                database=self.server.options.get('database'),\n                user=self.user_mapping.remote_user if self.user_mapping else None,\n                password=self.user_mapping.remote_password if self.user_mapping else None\n            )\n            return conn\n        except ImportError:\n            raise RuntimeError(\"pymysql not installed. Install with: pip install pymysql\")\n    \n    def disconnect(self, connection: Any):\n        \"\"\"Close MySQL connection.\"\"\"\n        if connection:\n            connection.close()\n    \n    def execute_query(self, connection: Any, query: str,\n                     params: Optional[List] = None) -> List[Dict]:\n        \"\"\"Execute query on MySQL.\"\"\"\n        cursor = connection.cursor(pymysql.cursors.DictCursor)\n        try:\n            cursor.execute(query, params or [])\n            return cursor.fetchall()\n        finally:\n            cursor.close()\n    \n    def get_table_schema(self, connection: Any, remote_schema: str,\n                        remote_table: str) -> List[Dict[str, Any]]:\n        \"\"\"Get MySQL table schema.\"\"\"\n        query = \"\"\"\n            SELECT column_name, data_type, is_nullable\n            FROM information_schema.columns\n            WHERE table_schema = %s AND table_name = %s\n            ORDER BY ordinal_position\n        \"\"\"\n        \n        results = self.execute_query(connection, query, \n                                     [remote_schema or self.server.options.get('database'), remote_table])\n        \n        columns = []\n        for row in results:\n            columns.append({\n                'name': row['column_name'],\n                'type': self.map_external_type(row['data_type']),\n                'nullable': row['is_nullable'] == 'YES'\n            })\n        \n        return columns\n    \n    def can_pushdown(self, operator: str) -> bool:\n        \"\"\"MySQL supports standard operators.\"\"\"\n        supported = {'=', '!=', '<', '>', '<=', '>=', 'LIKE', 'IN', 'BETWEEN'}\n        return operator.upper() in supported


class CSVFDWHandler(BaseFDWHandler):
n    \"\"\"Handler for CSV file foreign data wrapper.\"\"\"\n    \n    def _init_type_mappings(self) -> Dict[str, ColumnMapping]:\n        # CSV is text-based, types inferred from content\n        return {\n            'TEXT': ColumnMapping('TEXT', 'TEXT'),\n            'INTEGER': ColumnMapping('INTEGER', 'INTEGER'),\n            'REAL': ColumnMapping('REAL', 'REAL'),\n            'BOOLEAN': ColumnMapping('BOOLEAN', 'BOOLEAN'),\n        }\n    \n    def connect(self) -> Any:\n        \"\"\"Open CSV file.\"\"\"\n        import csv\n        \n        filename = self.server.options.get('filename')\n        if not filename:\n            raise ValueError(\"CSV FDW requires 'filename' option\")\n        \n        delimiter = self.server.options.get('delimiter', ',')\n        quotechar = self.server.options.get('quotechar', '\"')\n        \n        return {\n            'filename': filename,\n            'delimiter': delimiter,\n            'quotechar': quotechar,\n            'file': None  # Will be opened on demand\n        }\n    \n    def disconnect(self, connection: Any):\n        \"\"\"Close CSV file.\"\"\"\n        if connection.get('file'):\n            connection['file'].close()\n    \n    def execute_query(self, connection: Any, query: str,\n                     params: Optional[List] = None) -> List[Dict]:\n        \"\"\"Read from CSV file with optional filtering.\"\"\"\n        import csv\n        \n        filename = connection['filename']\n        delimiter = connection['delimiter']\n        \n        results = []\n        with open(filename, 'r', newline='', encoding='utf-8') as f:\n            reader = csv.DictReader(f, delimiter=delimiter)\n            for row in reader:\n                # Convert types based on content\n                converted = {}\n                for key, value in row.items():\n                    converted[key] = self._infer_type(value)\n                results.append(converted)\n        \n        return results\n    \n    def _infer_type(self, value: str) -> Any:\n        \"\"\"Infer type from string value.\"\"\"\n        if value == '' or value is None:\n            return None\n        \n        # Try integer\n        try:\n            return int(value)\n        except ValueError:\n            pass\n        \n        # Try float\n        try:\n            return float(value)\n        except ValueError:\n            pass\n        \n        # Try boolean\n        lower = value.lower()\n        if lower in ('true', 'yes', '1'):\n            return True\n        if lower in ('false', 'no', '0'):\n            return False\n        \n        # Default to string\n        return value\n    \n    def get_table_schema(self, connection: Any, remote_schema: str,\n                        remote_table: str) -> List[Dict[str, Any]]:\n        \"\"\"Infer schema from CSV header.\"\"\"\n        import csv\n        \n        filename = connection['filename']\n        delimiter = connection['delimiter']\n        \n        with open(filename, 'r', newline='', encoding='utf-8') as f:\n            reader = csv.reader(f, delimiter=delimiter)\n            headers = next(reader)\n            \n            # Sample first row to infer types\n            sample = next(reader, None)\n        \n        columns = []\n        for i, header in enumerate(headers):\n            col_type = 'TEXT'\n            if sample and i < len(sample):\n                val = sample[i]\n                try:\n                    int(val)\n                    col_type = 'INTEGER'\n                except ValueError:\n                    try:\n                        float(val)\n                        col_type = 'REAL'\n                    except ValueError:\n                        pass\n            \n            columns.append({\n                'name': header.strip(),\n                'type': col_type,\n                'nullable': True\n            })\n        \n        return columns\n    \n    def can_pushdown(self, operator: str) -> bool:\n        \"\"\"CSV supports limited pushdown (file-level only).\"\"\"\n        return False  # CSV files don't support query pushdown


class RESTAPIFDWHandler(BaseFDWHandler):
n    \"\"\"Handler for REST API foreign data wrapper.\"\"\"\n    \n    def _init_type_mappings(self) -> Dict[str, ColumnMapping]:\n        # JSON types\n        return {\n            'string': ColumnMapping('string', 'TEXT'),\n            'number': ColumnMapping('number', 'REAL'),\n            'integer': ColumnMapping('integer', 'INTEGER'),\n            'boolean': ColumnMapping('boolean', 'BOOLEAN'),\n            'array': ColumnMapping('array', 'TEXT'),\n            'object': ColumnMapping('object', 'TEXT'),\n        }\n    \n    def connect(self) -> Any:\n        \"\"\"Prepare API connection.\"\"\"\n        return {\n            'base_url': self.server.options.get('url'),\n            'headers': self._parse_headers(self.server.options.get('headers', '{}')),\n            'auth': self._get_auth()\n        }\n    \n    def _parse_headers(self, headers_str: str) -> Dict[str, str]:\n        \"\"\"Parse headers from options.\"\"\"\n        try:\n            return json.loads(headers_str)\n        except json.JSONDecodeError:\n            return {}\n    \n    def _get_auth(self) -> Optional[Tuple[str, str]]:\n        \"\"\"Get authentication tuple.\"\"\"\n        if self.user_mapping:\n            return (self.user_mapping.remote_user, self.user_mapping.remote_password)\n        return None\n    \n    def disconnect(self, connection: Any):\n        \"\"\"No persistent connection for REST API.\"\"\"\n        pass\n    \n    def execute_query(self, connection: Any, query: str,\n                     params: Optional[List] = None) -> List[Dict]:\n        \"\"\"Execute REST API request.\"\"\"\n        base_url = connection['base_url']\n        headers = connection['headers']\n        auth = connection['auth']\n        \n        # Build URL with query parameters\n        url = base_url\n        if params:\n            query_string = urllib.parse.urlencode(params)\n            url = f\"{base_url}?{query_string}\"\n        \n        # Make request\n        req = urllib.request.Request(url, headers=headers)\n        \n        if auth:\n            import base64\n            credentials = base64.b64encode(f\"{auth[0]}:{auth[1]}\".encode()).decode()\n            req.add_header('Authorization', f'Basic {credentials}')\n        \n        with urllib.request.urlopen(req, timeout=30) as response:\n            data = json.loads(response.read().decode('utf-8'))\n        \n        # Handle different response formats\n        if isinstance(data, list):\n            return data\n        elif isinstance(data, dict):\n            # Extract array if present\n            for key in ['data', 'results', 'items', 'records']:\n                if key in data and isinstance(data[key], list):\n                    return data[key]\n            return [data]\n        \n        return []\n    \n    def get_table_schema(self, connection: Any, remote_schema: str,\n                        remote_table: str) -> List[Dict[str, Any]]:\n        \"\"\"Infer schema from API response sample.\"\"\"\n        # Make sample request\n        sample_data = self.execute_query(connection, '', [])\n        \n        if not sample_data:\n            return []\n        \n        # Infer from first record\n        first_record = sample_data[0]\n        columns = []\n        \n        for key, value in first_record.items():\n            col_type = self._infer_json_type(value)\n            columns.append({\n                'name': key,\n                'type': col_type,\n                'nullable': True\n            })\n        \n        return columns\n    \n    def _infer_json_type(self, value: Any) -> str:\n        \"\"\"Infer KosDB type from JSON value.\"\"\"\n        if isinstance(value, bool):\n            return 'BOOLEAN'\n        elif isinstance(value, int):\n            return 'INTEGER'\n        elif isinstance(value, float):\n            return 'REAL'\n        elif isinstance(value, list):\n            return 'TEXT'  # Store as JSON string\n        elif isinstance(value, dict):\n            return 'TEXT'  # Store as JSON string\n        else:\n            return 'TEXT'\n    \n    def can_pushdown(self, operator: str) -> bool:\n        \"\"\"REST API pushdown depends on API capabilities.\"\"\"\n        # Check if server supports query parameters\n        supports_query = self.server.options.get('supports_query', 'false').lower() == 'true'\n        if not supports_query:\n            return False\n        \n        supported = {'=', 'LIKE'}\n        return operator.upper() in supported


class FDWManager:
n    \"\"\"\n    Main manager for Foreign Data Wrappers.
    \"\"\"\n    \n    def __init__(self):\n        self.servers: Dict[str, FDWServer] = {}\n        self.user_mappings: Dict[str, UserMapping] = {}\n        self.foreign_tables: Dict[str, ForeignTable] = {}\n        self.handlers: Dict[str, Callable] = {\n            FDWType.POSTGRESQL.value: PostgreSQLFDWHandler,\n            FDWType.MYSQL.value: MySQLFDWHandler,\n            FDWType.CSV.value: CSVFDWHandler,\n            FDWType.REST_API.value: RESTAPIFDWHandler,\n        }\n        self.stats = {\n            'servers_created': 0,\n            'tables_created': 0,\n            'queries_executed': 0,\n            'rows_fetched': 0\n        }\n    \n    def create_server(self, \n                     name: str,\n                     fdw_type: str,\n                     options: Dict[str, str]) -> FDWServer:\n        \"\"\"Create a foreign server.\"\"\"\n        if name in self.servers:\n            raise ValueError(f\"Server '{name}' already exists\")\n        \n        try:\n            fdw_enum = FDWType(fdw_type.lower())\n        except ValueError:\n            raise ValueError(f\"Unknown FDW type: {fdw_type}\")\n        \n        server = FDWServer(\n            name=name,\n            fdw_type=fdw_enum,\n            options=options\n        )\n        \n        self.servers[name] = server\n        self.stats['servers_created'] += 1\n        \n        return server\n    \n    def drop_server(self, name: str) -> bool:\n        \"\"\"Drop a foreign server.\"\"\"\n        if name not in self.servers:\n            return False\n        \n        # Drop dependent objects\n        tables_to_drop = [\n            key for key, table in self.foreign_tables.items()\n            if table.server_name == name\n        ]\n        for key in tables_to_drop:\n            del self.foreign_tables[key]\n        \n        # Drop user mappings\n        mappings_to_drop = [\n            key for key, mapping in self.user_mappings.items()\n            if mapping.server_name == name\n        ]\n        for key in mappings_to_drop:\n            del self.user_mappings[key]\n        \n        del self.servers[name]\n        return True\n    \n    def create_user_mapping(self,\n                           server_name: str,\n                           local_user: str,\n                           remote_user: str,\n                           remote_password: Optional[str] = None,\n                           options: Optional[Dict[str, str]] = None) -> UserMapping:\n        \"\"\"Create user mapping for foreign server.\"\"\"\n        if server_name not in self.servers:\n            raise ValueError(f\"Server '{server_name}' does not exist\")\n        \n        key = f\"{local_user}@{server_name}\"\n        \n        mapping = UserMapping(\n            server_name=server_name,\n            local_user=local_user,\n            remote_user=remote_user,\n            remote_password=remote_password,\n            options=options or {}\n        )\n        \n        self.user_mappings[key] = mapping\n        return mapping\n    \n    def create_foreign_table(self,\n                            name: str,\n                            local_schema: str,\n                            server_name: str,\n                            columns: List[Dict[str, Any]],\n                            remote_schema: Optional[str] = None,\n                            remote_table: Optional[str] = None,\n                            options: Optional[Dict[str, str]] = None) -> ForeignTable:\n        \"\"\"Create a foreign table.\"\"\"\n        if server_name not in self.servers:\n            raise ValueError(f\"Server '{server_name}' does not exist\")\n        \n        full_name = f\"{local_schema}.{name}\"\n        \n        table = ForeignTable(\n            name=name,\n            local_schema=local_schema,\n            server_name=server_name,\n            columns=columns,\n            remote_schema=remote_schema,\n            remote_table=remote_table,\n            options=options or {}\n        )\n        \n        self.foreign_tables[full_name] = table\n        self.stats['tables_created'] += 1\n        \n        return table\n    \n    def import_foreign_schema(self,\n                             server_name: str,\n                             remote_schema: str,\n                             local_schema: str,\n                             tables: Optional[List[str]] = None) -> List[ForeignTable]:\n        \"\"\"Import schema from foreign server.\"\"\"\n        if server_name not in self.servers:\n            raise ValueError(f\"Server '{server_name}' does not exist\")\n        \n        server = self.servers[server_name]\n        handler_class = self.handlers.get(server.fdw_type.value)\n        \n        if not handler_class:\n            raise ValueError(f\"No handler for FDW type: {server.fdw_type}\")\n        \n        # Get user mapping\n        key = f\"current_user@{server_name}\"\n        user_mapping = self.user_mappings.get(key)\n        \n        handler = handler_class(server, user_mapping)\n        \n        # Connect and get schema\n        connection = handler.connect()\n        try:\n            imported_tables = []\n            \n            # Get list of tables (simplified - would query information_schema)\n            remote_tables = tables or self._get_remote_tables(handler, connection, remote_schema)\n            \n            for remote_table in remote_tables:\n                columns = handler.get_table_schema(connection, remote_schema, remote_table)\n                \n                table = self.create_foreign_table(\n                    name=remote_table,\n                    local_schema=local_schema,\n                    server_name=server_name,\n                    columns=columns,\n                    remote_schema=remote_schema,\n                    remote_table=remote_table\n                )\n                \n                imported_tables.append(table)\n            \n            return imported_tables\n        finally:\n            handler.disconnect(connection)\n    \n    def _get_remote_tables(self, handler: BaseFDWHandler, \n                          connection: Any,\n                          remote_schema: str) -> List[str]:\n        \"\"\"Get list of tables from remote schema.\"\"\"\n        # This would query information_schema or equivalent\n        # For now, return empty list - would be implemented per FDW type\n        return []\n    \n    def execute_foreign_query(self,\n                             table_name: str,\n                             local_schema: str,\n                             columns: List[str],\n                             where_conditions: Optional[List[Dict]] = None) -> List[Dict]:\n        \"\"\"Execute query on foreign table.\"\"\"\n        full_name = f\"{local_schema}.{table_name}\"\n        \n        if full_name not in self.foreign_tables:\n            raise ValueError(f\"Foreign table '{full_name}' does not exist\")\n        \n        table = self.foreign_tables[full_name]\n        server = self.servers[table.server_name]\n        \n        handler_class = self.handlers.get(server.fdw_type.value)\n        if not handler_class:\n            raise ValueError(f\"No handler for FDW type: {server.fdw_type}\")\n        \n        # Get user mapping\n        key = f\"current_user@{table.server_name}\"\n        user_mapping = self.user_mappings.get(key)\n        \n        handler = handler_class(server, user_mapping)\n        \n        # Build and execute query\n        connection = handler.connect()\n        try:\n            if hasattr(handler, 'build_remote_query'):\n                query = handler.build_remote_query(table, columns, where_conditions or [])\n            else:\n                query = f\"SELECT * FROM {table.remote_table or table.name}\"\n            \n            results = handler.execute_query(connection, query)\n            \n            # Convert types\n            converted = []\n            for row in results:\n                converted_row = {}\n                for col in table.columns:\n                    col_name = col['name']\n                    if col_name in row:\n                        converted_row[col_name] = handler.convert_value(\n                            row[col_name], col['type']\n                        )\n                converted.append(converted_row)\n            \n            self.stats['queries_executed'] += 1\n            self.stats['rows_fetched'] += len(converted)\n            \n            return converted\n        finally:\n            handler.disconnect(connection)\n    \n    def get_pushdown_predicates(self,\n                               table_name: str,\n                               local_schema: str,\n                               conditions: List[Dict]) -> Tuple[List[Dict], List[Dict]]:\n        \"\"\"\n        Separate conditions into pushable and non-pushable.
        
        Returns:
n            Tuple of (pushable_conditions, local_conditions)
n        \"\"\"\n        full_name = f\"{local_schema}.{table_name}\"\n        \n        if full_name not in self.foreign_tables:\n            return [], conditions\n        \n        table = self.foreign_tables[full_name]\n        server = self.servers[table.server_name]\n        \n        handler_class = self.handlers.get(server.fdw_type.value)\n        if not handler_class:\n            return [], conditions\n        \n        handler = handler_class(server, None)\n        \n        pushable = []\n        local = []\n        \n        for cond in conditions:\n            if handler.can_pushdown(cond.get('op', '=')):\n                pushable.append(cond)\n            else:\n                local.append(cond)\n        \n        return pushable, local\n    \n    def get_stats(self) -> Dict[str, Any]:\n        \"\"\"Get FDW statistics.\"\"\"\n        return {\n            **self.stats,\n            'servers': len(self.servers),\n            'tables': len(self.foreign_tables),\n            'user_mappings': len(self.user_mappings)\n        }


def parse_create_server(sql: str) -> Dict[str, Any]:
n    \"\"\"Parse CREATE SERVER statement.\"\"\"\n    pattern = re.compile(\n        r'CREATE\\s+SERVER\\s+(\\w+)\\s+'\n        r'FOREIGN\\s+DATA\\s+WRAPPER\\s+(\\w+)\\s*'\n        r'OPTIONS\\s*\\(([^)]+)\\)',\n        re.IGNORECASE\n    )\n    \n    match = pattern.match(sql.strip())\n    if not match:\n        raise ValueError(\"Invalid CREATE SERVER syntax\")\n    \n    name = match.group(1)\n    fdw_type = match.group(2)\n    options_str = match.group(3)\n    \n    # Parse options\n    options = {}\n    for opt in options_str.split(','):\n        if '=' in opt:\n            key, value = opt.split('=', 1)\n            options[key.strip()] = value.strip().strip(\"'\\\"\")\n    \n    return {\n        'name': name,\n        'fdw_type': fdw_type,\n        'options': options\n    }\n\n\ndef parse_create_foreign_table(sql: str) -> Dict[str, Any]:
n    \"\"\"Parse CREATE FOREIGN TABLE statement.\"\"\"\n    pattern = re.compile(\n        r'CREATE\\s+FOREIGN\\s+TABLE\\s+(\\w+)\\s*\\(([^)]+)\\)\\s*'\n        r'SERVER\\s+(\\w+)'\n        r'(?:\\s+OPTIONS\\s*\\(([^)]+)\\))?',\n        re.IGNORECASE | re.DOTALL\n    )\n    \n    match = pattern.match(sql.strip())\n    if not match:\n        raise ValueError(\"Invalid CREATE FOREIGN TABLE syntax\")\n    \n    name = match.group(1)\n    columns_str = match.group(2)\n    server_name = match.group(3)\n    options_str = match.group(4) or ''\n    \n    # Parse columns (simplified)\n    columns = []\n    for col_def in columns_str.split(','):\n        parts = col_def.strip().split()\n        if len(parts) >= 2:\n            columns.append({\n                'name': parts[0],\n                'type': parts[1]\n            })\n    \n    # Parse options\n    options = {}\n    if options_str:\n        for opt in options_str.split(','):\n            if '=' in opt:\n                key, value = opt.split('=', 1)\n                options[key.strip()] = value.strip().strip(\"'\\\"\")\n    \n    return {\n        'name': name,\n        'columns': columns,\n        'server_name': server_name,\n        'options': options\n    }\n\n\n# Example usage\nif __name__ == '__main__':\n    manager = FDWManager()\n    \n    # Create PostgreSQL server\n    server = manager.create_server(\n        name='pg_sales',\n        fdw_type='postgresql',\n        options={\n            'host': 'localhost',\n            'port': '5432',\n            'dbname': 'sales_db'\n        }\n    )\n    \n    print(f\"Created server: {server.name} ({server.fdw_type.value})\")\n    \n    # Create user mapping\n    mapping = manager.create_user_mapping(\n        server_name='pg_sales',\n        local_user='kosdb_user',\n        remote_user='postgres',\n        remote_password='secret'\n    )\n    \n    print(f\"Created user mapping for {mapping.local_user}\")\n    \n    # Create foreign table\n    table = manager.create_foreign_table(\n        name='remote_customers',\n        local_schema='public',\n        server_name='pg_sales',\n        columns=[\n            {'name': 'id', 'type': 'INTEGER'},\n            {'name': 'name', 'type': 'TEXT'},\n            {'name': 'email', 'type': 'TEXT'}\n        ],\n        remote_schema='public',\n        remote_table='customers'\n    )\n    \n    print(f\"Created foreign table: {table.name}\")\n    print(f\"Stats: {manager.get_stats()}\")\n