"""
Sharding integration layer for KosDB.

Combines ShardRouter and ShardManager into a single ShardingCoordinator
that the server and command handlers can use.
"""

import json
import socket
import threading
from typing import Dict, Any, List, Optional
from shard_manager import ShardManager
from shard_router import ShardRouter, RoutingStrategy


class ShardingError(Exception):
    pass


class ShardingCoordinator:
    """
    High-level coordinator for sharded operations.

    Routes queries and mutations to the appropriate shard,
    manages topology, and provides cross-region read replica awareness.
    """

    def __init__(self, db, server_id: int = 1, default_region: str = "local"):
        self.db = db
        self.server_id = server_id
        self.manager = ShardManager(db, server_id, default_region)
        self.router = ShardRouter(self.manager)
        self._local_cache: Dict[str, Any] = {}
        self._lock = threading.RLock()

    def create_shard(
        self,
        shard_id: str,
        region: str,
        host: str,
        port: int,
        role: str = "primary",
        weight: int = 1,
    ) -> str:
        """Create a new shard and rebalance the cluster."""
        result = self.manager.create_shard(
            shard_id=shard_id,
            region=region,
            host=host,
            port=port,
            role=role,
            weight=weight,
        )
        if result.startswith("OK"):
            self.router.invalidate_cache()
        return result

    def drop_shard(self, shard_id: str) -> str:
        """Remove a shard and rebalance."""
        result = self.manager.drop_shard(shard_id)
        if result.startswith("OK"):
            self.router.invalidate_cache()
        return result

    def rebalance(self) -> str:
        """Rebalance shards and invalidate routing cache."""
        result = self.manager.rebalance_shards()
        self.router.invalidate_cache()
        return result

    def list_shards(self) -> List[Dict[str, Any]]:
        return self.manager.list_shards()

    def add_read_replica(
        self,
        shard_id: str,
        replica_id: str,
        region: str,
        host: str,
        port: int,
    ) -> str:
        result = self.manager.add_read_replica(
            shard_id, replica_id, region, host, port
        )
        if result.startswith("OK"):
            self.router.invalidate_cache()
        return result

    def route_key(self, key: str, operation: str = "read", region: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Route a key to the best shard."""
        return self.router.route_key(key, operation, region)

    def route_query(
        self,
        table: str,
        operation: str = "read",
        region: Optional[str] = None,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Route a query to all shards that may contain matching data."""
        return self.router.route_query(table, operation, region, where)

    def is_local_shard(self, shard_id: str) -> bool:
        """Check if a shard refers to the local server."""
        shard = self.manager.get_shard(shard_id)
        if not shard:
            return False
        return shard.host in ("localhost", "127.0.0.1", "0.0.0.0") and shard.port == self.server_id

    def execute_on_shard(
        self,
        shard_id: str,
        command: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> str:
        """Execute a raw command on a remote shard."""
        shard = self.manager.get_shard(shard_id)
        if not shard:
            return f"ERROR: Shard '{shard_id}' not found"

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(10)
                s.connect((shard.host, shard.port))

                if username and password:
                    s.sendall(f"USER {username}\n".encode())
                    s.recv(4096)
                    s.sendall(f"PASS {password}\n".encode())
                    auth_resp = s.recv(4096).decode().strip()
                    if not auth_resp.startswith("OK"):
                        return f"ERROR: Auth failed on shard {shard_id}: {auth_resp}"

                s.sendall((command + "\n").encode())
                return s.recv(65536).decode().strip()
        except Exception as e:
            return f"ERROR: Failed to execute on shard {shard_id}: {e}"

    def execute_distributed_insert(
        self,
        table: str,
        key: str,
        values: List[Any],
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> str:
        """Route an insert to the correct primary shard."""
        shard = self.route_key(key, operation="write")
        if not shard:
            return "ERROR: No shard available for write"

        # If local, execute directly via database
        if self.is_local_shard(shard["shard_id"]):
            return self.db.insert(table, values)

        cmd = f"INSERT INTO {table} VALUES ({', '.join(self._format_values(values))})"
        return self.execute_on_shard(shard["shard_id"], cmd, username, password)

    def execute_distributed_select(
        self,
        table: str,
        key: Optional[str] = None,
        where: Optional[Dict[str, Any]] = None,
        region: Optional[str] = None,
    ) -> str:
        """Route a select query to appropriate shard(s) and merge results."""
        if key:
            shards = [self.route_key(key, operation="read", region=region)]
        else:
            shards = self.route_query(table, operation="read", region=region, where=where)

        if not shards or all(s is None for s in shards):
            return "ERROR: No shard available for read"

        results = []
        for shard in shards:
            if shard is None:
                continue
            if self.is_local_shard(shard["shard_id"]):
                local_result = self.db.select(table, ["*"], where, raw=True)
                if isinstance(local_result, list):
                    results.extend(local_result)
            else:
                # Build a SELECT command
                cmd = f"SELECT * FROM {table}"
                if where:
                    conditions = " AND ".join(f"{k} = {self._format_value(v)}" for k, v in where.items())
                    cmd += f" WHERE {conditions}"
                resp = self.execute_on_shard(shard["shard_id"], cmd)
                results.append(f"[{shard['shard_id']}] {resp}")

        if any(not self.is_local_shard(s["shard_id"]) for s in shards if s):
            return "\n".join(results)

        if not results:
            return "Empty set"
        return json.dumps(results, indent=2, default=str)

    @staticmethod
    def _format_value(value: Any) -> str:
        if isinstance(value, str):
            return f"'{value}'"
        return str(value)

    @staticmethod
    def _format_values(values: List[Any]) -> List[str]:
        return [ShardingCoordinator._format_value(v) for v in values]

    def get_stats(self) -> Dict[str, Any]:
        return {
            "manager": self.manager.get_stats(),
            "router": self.router.get_stats(),
        }
