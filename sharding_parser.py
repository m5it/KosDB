"""
Parser extensions for sharding commands.
"""

import re
from typing import Dict, Any, Optional


class ShardingParser:
    """
    Parser for sharding commands.

    Supported commands:
    - CREATE SHARD id REGION region HOST host PORT port [ROLE role] [WEIGHT weight]
    - DROP SHARD id
    - SHOW SHARDS
    - REBALANCE SHARDS
    - ADD READ REPLICA replica_id FOR SHARD shard_id REGION region HOST host PORT port
    - ROUTE KEY key [OPERATION read|write]
    """

    CREATE_SHARD_PATTERN = re.compile(
        r"CREATE\s+SHARD\s+(\w+)\s+"
        r"REGION\s+(\w+)\s+"
        r"HOST\s+([^\s]+)\s+"
        r"PORT\s+(\d+)"
        r"(?:\s+ROLE\s+(\w+))?"
        r"(?:\s+WEIGHT\s+(\d+))?",
        re.IGNORECASE,
    )

    DROP_SHARD_PATTERN = re.compile(
        r"DROP\s+SHARD\s+(\w+)",
        re.IGNORECASE,
    )

    SHOW_SHARDS_PATTERN = re.compile(
        r"SHOW\s+SHARDS",
        re.IGNORECASE,
    )

    REBALANCE_PATTERN = re.compile(
        r"REBALANCE\s+SHARDS",
        re.IGNORECASE,
    )

    ADD_REPLICA_PATTERN = re.compile(
        r"ADD\s+READ\s+REPLICA\s+(\w+)\s+"
        r"FOR\s+SHARD\s+(\w+)\s+"
        r"REGION\s+(\w+)\s+"
        r"HOST\s+([^\s]+)\s+"
        r"PORT\s+(\d+)",
        re.IGNORECASE,
    )

    ROUTE_KEY_PATTERN = re.compile(
        r"ROUTE\s+KEY\s+([^\s]+)"
        r"(?:\s+OPERATION\s+(read|write))?",
        re.IGNORECASE,
    )

    def parse(self, query: str) -> Optional[Dict[str, Any]]:
        """Parse a sharding command."""
        query = query.strip()

        match = self.CREATE_SHARD_PATTERN.match(query)
        if match:
            return {
                "type": "CREATE_SHARD",
                "shard_id": match.group(1),
                "region": match.group(2),
                "host": match.group(3),
                "port": match.group(4),
                "role": match.group(5) or "primary",
                "weight": match.group(6) or "1",
            }

        match = self.DROP_SHARD_PATTERN.match(query)
        if match:
            return {
                "type": "DROP_SHARD",
                "shard_id": match.group(1),
            }

        match = self.SHOW_SHARDS_PATTERN.match(query)
        if match:
            return {"type": "SHOW_SHARDS"}

        match = self.REBALANCE_PATTERN.match(query)
        if match:
            return {"type": "REBALANCE_SHARDS"}

        match = self.ADD_REPLICA_PATTERN.match(query)
        if match:
            return {
                "type": "ADD_READ_REPLICA",
                "replica_id": match.group(1),
                "shard_id": match.group(2),
                "region": match.group(3),
                "host": match.group(4),
                "port": match.group(5),
            }

        match = self.ROUTE_KEY_PATTERN.match(query)
        if match:
            return {
                "type": "ROUTE_KEY",
                "key": match.group(1),
                "operation": match.group(2) or "read",
            }

        return None


_sharding_parser = None


def get_sharding_parser():
    global _sharding_parser
    if _sharding_parser is None:
        _sharding_parser = ShardingParser()
    return _sharding_parser
