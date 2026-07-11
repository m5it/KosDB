"""
Parser extensions for connection pool commands.

Adds POOL CREATE, POOL STATUS, POOL LIST, POOL SHUTDOWN, POOL HEALTH commands.
"""

import re
from typing import Dict, Any, Optional


class PoolCommandParser:
    """
    Parser for connection pool management commands.
    
    Supports:
    - POOL CREATE name MIN 5 MAX 20 TIMEOUT 30
    - POOL STATUS [name]
    - POOL LIST
    - POOL SHUTDOWN name
    - POOL HEALTH [name]
    - POOL ACQUIRE name [TIMEOUT seconds]
    """
    
    # Command patterns
    POOL_CREATE_PATTERN = re.compile(
        r'POOL\s+CREATE\s+(\w+)'
        r'(?:\s+MIN\s+(\d+))?'
        r'(?:\s+MAX\s+(\d+))?'
        r'(?:\s+TIMEOUT\s+([\d.]+))?'
        r'(?:\s+IDLE\s+([\d.]+))?',
        re.IGNORECASE
    )
    
    POOL_STATUS_PATTERN = re.compile(
        r'POOL\s+STATUS(?:\s+(\w+))?',
        re.IGNORECASE
    )
    
    POOL_LIST_PATTERN = re.compile(
        r'POOL\s+LIST',
        re.IGNORECASE
    )
    
    POOL_SHUTDOWN_PATTERN = re.compile(
        r'POOL\s+SHUTDOWN\s+(\w+)'
        r'(?:\s+(NOWAIT))?',
        re.IGNORECASE
    )
    
    POOL_HEALTH_PATTERN = re.compile(
        r'POOL\s+HEALTH(?:\s+(\w+))?',
        re.IGNORECASE
    )
    
    POOL_ACQUIRE_PATTERN = re.compile(
        r'POOL\s+ACQUIRE\s+(\w+)'
        r'(?:\s+TIMEOUT\s+([\d.]+))?',
        re.IGNORECASE
    )
    
    def parse(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Parse a pool command.
        
        Args:
            query: SQL command string
        
        Returns:
            Parsed command dict or None if not recognized
        """
        query = query.strip()
        upper = query.upper()
        
        if not upper.startswith('POOL'):
            return None
        
        # POOL CREATE
        match = self.POOL_CREATE_PATTERN.match(query)
        if match:
            return {
                'type': 'POOL_CREATE',
                'command': 'pool_create',
                'pool_name': match.group(1),
                'min_connections': int(match.group(2)) if match.group(2) else 5,
                'max_connections': int(match.group(3)) if match.group(3) else 20,
                'connection_timeout': float(match.group(4)) if match.group(4) else 30.0,
                'idle_timeout': float(match.group(5)) if match.group(5) else 300.0
            }
        
        # POOL STATUS
        match = self.POOL_STATUS_PATTERN.match(query)
        if match:
            return {
                'type': 'POOL_STATUS',
                'command': 'pool_status',
                'pool_name': match.group(1)
            }
        
        # POOL LIST
        if self.POOL_LIST_PATTERN.match(query):
            return {
                'type': 'POOL_LIST',
                'command': 'pool_list'
            }
        
        # POOL SHUTDOWN
        match = self.POOL_SHUTDOWN_PATTERN.match(query)
        if match:
            return {
                'type': 'POOL_SHUTDOWN',
                'command': 'pool_shutdown',
                'pool_name': match.group(1),
                'wait': not bool(match.group(2))  # NOWAIT means don't wait
            }
        
        # POOL HEALTH
        match = self.POOL_HEALTH_PATTERN.match(query)
        if match:
            return {
                'type': 'POOL_HEALTH',
                'command': 'pool_health',
                'pool_name': match.group(1)
            }
        
        # POOL ACQUIRE
        match = self.POOL_ACQUIRE_PATTERN.match(query)
        if match:
            return {
                'type': 'POOL_ACQUIRE',
                'command': 'pool_acquire',
                'pool_name': match.group(1),
                'timeout': float(match.group(2)) if match.group(2) else None
            }
        
        return None


# Singleton parser instance
_pool_parser: Optional[PoolCommandParser] = None


def get_pool_parser() -> PoolCommandParser:
    """Get global pool command parser."""
    global _pool_parser
    if _pool_parser is None:
        _pool_parser = PoolCommandParser()
    return _pool_parser
