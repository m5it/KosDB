"""
Command handlers for SQL wire protocol configuration.
"""

import json
from typing import Dict, Any
from database import Database


class ShowProtocolStatusCommand:
    def __init__(self, db: Database):
        self.db = db

    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        status = self._get_status()
        lines = [
            "-" * 50,
            "SQL Protocol Status",
            "-" * 50,
            f"PostgreSQL: {'enabled' if status.get('postgres_enabled') else 'disabled'} port={status.get('postgres_port', 'N/A')}",
            f"MySQL:      {'enabled' if status.get('mysql_enabled') else 'disabled'} port={status.get('mysql_port', 'N/A')}",
            f"TLS:        {'enabled' if status.get('tls_enabled') else 'disabled'}",
            "-" * 50,
        ]
        return "\n".join(lines)

    def _get_status(self) -> Dict[str, Any]:
        return getattr(self.db, "_sql_protocol_status", {
            "postgres_enabled": False,
            "postgres_port": 5432,
            "mysql_enabled": False,
            "mysql_port": 3306,
            "tls_enabled": False,
        })


class SetProtocolPortCommand:
    def __init__(self, db: Database):
        self.db = db

    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        if not client_state.get("is_admin"):
            return "ERROR: Admin only"

        protocol = params.get("protocol", "").lower()
        port_str = params.get("port")
        if protocol not in ("postgres", "mysql"):
            return "ERROR: protocol must be 'postgres' or 'mysql'"
        try:
            port = int(port_str)
        except (ValueError, TypeError):
            return "ERROR: port must be an integer"

        status = self._get_status()
        if protocol == "postgres":
            status["postgres_port"] = port
        else:
            status["mysql_port"] = port
        self._set_status(status)
        return f"OK: {protocol} protocol port set to {port}"

    def _get_status(self) -> Dict[str, Any]:
        if not hasattr(self.db, "_sql_protocol_status"):
            self.db._sql_protocol_status = {
                "postgres_enabled": False,
                "postgres_port": 5432,
                "mysql_enabled": False,
                "mysql_port": 3306,
                "tls_enabled": False,
            }
        return self.db._sql_protocol_status

    def _set_status(self, status: Dict[str, Any]):
        self.db._sql_protocol_status = status


class EnableProtocolCommand:
    def __init__(self, db: Database):
        self.db = db

    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        if not client_state.get("is_admin"):
            return "ERROR: Admin only"

        protocol = params.get("protocol", "").lower()
        if protocol not in ("postgres", "mysql"):
            return "ERROR: protocol must be 'postgres' or 'mysql'"

        status = self._get_status()
        if protocol == "postgres":
            status["postgres_enabled"] = True
        else:
            status["mysql_enabled"] = True
        self._set_status(status)
        return f"OK: {protocol} protocol enabled"

    def _get_status(self) -> Dict[str, Any]:
        if not hasattr(self.db, "_sql_protocol_status"):
            self.db._sql_protocol_status = {
                "postgres_enabled": False,
                "postgres_port": 5432,
                "mysql_enabled": False,
                "mysql_port": 3306,
                "tls_enabled": False,
            }
        return self.db._sql_protocol_status

    def _set_status(self, status: Dict[str, Any]):
        self.db._sql_protocol_status = status


class DisableProtocolCommand:
    def __init__(self, db: Database):
        self.db = db

    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        if not client_state.get("is_admin"):
            return "ERROR: Admin only"

        protocol = params.get("protocol", "").lower()
        if protocol not in ("postgres", "mysql"):
            return "ERROR: protocol must be 'postgres' or 'mysql'"

        status = self._get_status()
        if protocol == "postgres":
            status["postgres_enabled"] = False
        else:
            status["mysql_enabled"] = False
        self._set_status(status)
        return f"OK: {protocol} protocol disabled"

    def _get_status(self) -> Dict[str, Any]:
        if not hasattr(self.db, "_sql_protocol_status"):
            self.db._sql_protocol_status = {
                "postgres_enabled": False,
                "postgres_port": 5432,
                "mysql_enabled": False,
                "mysql_port": 3306,
                "tls_enabled": False,
            }
        return self.db._sql_protocol_status

    def _set_status(self, status: Dict[str, Any]):
        self.db._sql_protocol_status = status
