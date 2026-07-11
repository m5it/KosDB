"""
Command handlers for sharding operations.
"""

import json
from typing import Dict, Any, List
from database import Database


class CreateShardCommand:
    def __init__(self, db: Database):
        self.db = db

    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        if not client_state.get("is_admin"):
            return "ERROR: Admin only"

        coordinator = self._get_coordinator()
        if not coordinator:
            return "ERROR: Sharding coordinator not available"

        required = ["shard_id", "region", "host", "port"]
        for r in required:
            if r not in params or params[r] is None:
                return f"ERROR: {r} required"

        try:
            port = int(params["port"])
            weight = int(params.get("weight", 1))
        except ValueError:
            return "ERROR: port and weight must be integers"

        return coordinator.create_shard(
            shard_id=params["shard_id"],
            region=params["region"],
            host=params["host"],
            port=port,
            role=params.get("role", "primary"),
            weight=weight,
        )

    def _get_coordinator(self):
        return getattr(self.db, "_sharding_coordinator", None)


class DropShardCommand:
    def __init__(self, db: Database):
        self.db = db

    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        if not client_state.get("is_admin"):
            return "ERROR: Admin only"

        coordinator = self._get_coordinator()
        if not coordinator:
            return "ERROR: Sharding coordinator not available"

        if "shard_id" not in params or params["shard_id"] is None:
            return "ERROR: shard_id required"

        return coordinator.drop_shard(params["shard_id"])

    def _get_coordinator(self):
        return getattr(self.db, "_sharding_coordinator", None)


class ShowShardsCommand:
    def __init__(self, db: Database):
        self.db = db

    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        coordinator = self._get_coordinator()
        if not coordinator:
            return "ERROR: Sharding coordinator not available"

        shards = coordinator.list_shards()
        if not shards:
            return "OK: No shards configured"

        lines = ["-" * 70, f"{'Shard ID':<16} {'Region':<12} {'Host':<16} {'Port':<6} {'Role':<14} {'Status':<8}", "-" * 70]
        for s in shards:
            lines.append(
                f"{s['shard_id']:<16} {s['region']:<12} {s['host']:<16} "
                f"{s['port']:<6} {s['role']:<14} {s['status']:<8}"
            )
        lines.append("-" * 70)
        return "\n".join(lines)

    def _get_coordinator(self):
        return getattr(self.db, "_sharding_coordinator", None)


class RebalanceShardsCommand:
    def __init__(self, db: Database):
        self.db = db

    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        if not client_state.get("is_admin"):
            return "ERROR: Admin only"

        coordinator = self._get_coordinator()
        if not coordinator:
            return "ERROR: Sharding coordinator not available"

        result = coordinator.rebalance()
        if not result.startswith("OK"):
            return result

        plan = coordinator.manager.get_rebalance_plan()
        lines = [result, "-" * 60, f"{'Shard ID':<16} {'Region':<12} {'Weight':<8} {'Ranges':<8} {'Load %':<8}", "-" * 60]
        for p in plan:
            lines.append(
                f"{p['shard_id']:<16} {p['region']:<12} {p['weight']:<8} "
                f"{p['key_range_count']:<8} {p['estimated_load_pct']:<8.2f}"
            )
        lines.append("-" * 60)
        return "\n".join(lines)

    def _get_coordinator(self):
        return getattr(self.db, "_sharding_coordinator", None)


class AddReadReplicaCommand:
    def __init__(self, db: Database):
        self.db = db

    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        if not client_state.get("is_admin"):
            return "ERROR: Admin only"

        coordinator = self._get_coordinator()
        if not coordinator:
            return "ERROR: Sharding coordinator not available"

        required = ["shard_id", "replica_id", "region", "host", "port"]
        for r in required:
            if r not in params or params[r] is None:
                return f"ERROR: {r} required"

        try:
            port = int(params["port"])
        except ValueError:
            return "ERROR: port must be integer"

        return coordinator.add_read_replica(
            shard_id=params["shard_id"],
            replica_id=params["replica_id"],
            region=params["region"],
            host=params["host"],
            port=port,
        )

    def _get_coordinator(self):
        return getattr(self.db, "_sharding_coordinator", None)


class RouteKeyCommand:
    def __init__(self, db: Database):
        self.db = db

    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        coordinator = self._get_coordinator()
        if not coordinator:
            return "ERROR: Sharding coordinator not available"

        if "key" not in params or params["key"] is None:
            return "ERROR: key required"

        shard = coordinator.route_key(params["key"], operation=params.get("operation", "read"))
        if not shard:
            return "ERROR: No shard found for key"

        return f"OK: Key '{params['key']}' routes to {shard['shard_id']} ({shard['region']})"

    def _get_coordinator(self):
        return getattr(self.db, "_sharding_coordinator", None)
