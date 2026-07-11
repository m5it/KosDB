"""
Parser extensions for materialized view commands.
"""

import re
from typing import Dict, Any, Optional


class MVParser:
    """
    Parser for materialized view commands.
    
    Supports:
    - CREATE MATERIALIZED VIEW name AS query [STRATEGY full|incremental|auto] [SCHEDULE manual|on_commit|every_n_minutes] [INTERVAL n]
    - DROP MATERIALIZED VIEW name
    - REFRESH MATERIALIZED VIEW name [STRATEGY full|incremental]
    - REFRESH ALL MATERIALIZED VIEWS
    - LIST MATERIALIZED VIEWS
    - SELECT FROM MV name
    - SET REFRESH SCHEDULE name SCHEDULE schedule [INTERVAL n]
    - MATERIALIZED VIEW STATS [name]
    """
    
    CREATE_MV_PATTERN = re.compile(
        r'CREATE\s+MATERIALIZED\s+VIEW\s+(\w+)'
        r'\s+AS\s+(.+?)'
        r'(?:\s+STRATEGY\s+(\w+))?'
        r'(?:\s+SCHEDULE\s+(\w+))?'
        r'(?:\s+INTERVAL\s+(\d+))?',
        re.IGNORECASE | re.DOTALL
    )
    
    DROP_MV_PATTERN = re.compile(
        r'DROP\s+MATERIALIZED\s+VIEW\s+(\w+)',
        re.IGNORECASE
    )
    
    REFRESH_MV_PATTERN = re.compile(
        r'REFRESH\s+MATERIALIZED\s+VIEW\s+(\w+)'
        r'(?:\s+STRATEGY\s+(\w+))?',
        re.IGNORECASE
    )
    
    REFRESH_ALL_PATTERN = re.compile(
        r'REFRESH\s+ALL\s+MATERIALIZED\s+VIEWS',
        re.IGNORECASE
    )
    
    LIST_MV_PATTERN = re.compile(
        r'LIST\s+MATERIALIZED\s+VIEWS',
        re.IGNORECASE
    )
    
    SELECT_MV_PATTERN = re.compile(
        r'SELECT\s+\*\s+FROM\s+MV\s+(\w+)',
        re.IGNORECASE
    )
    
    SET_SCHEDULE_PATTERN = re.compile(
        r'SET\s+REFRESH\s+SCHEDULE\s+(\w+)'
        r'\s+SCHEDULE\s+(\w+)'
        r'(?:\s+INTERVAL\s+(\d+))?',
        re.IGNORECASE
    )
    
    MV_STATS_PATTERN = re.compile(
        r'MATERIALIZED\s+VIEW\s+STATS(?:\s+(\w+))?',
        re.IGNORECASE
    )
    
    def parse(self, query: str) -> Optional[Dict[str, Any]]:
        """Parse a materialized view command."""
        query = query.strip()
        upper = query.upper()
        
        if not any(x in upper for x in ['MATERIALIZED', 'MV']):
            return None
        
        # CREATE MATERIALIZED VIEW
        match = self.CREATE_MV_PATTERN.match(query)
        if match:
            return {
                'type': 'CREATE_MATERIALIZED_VIEW',
                'command': 'create_materialized_view',
                'name': match.group(1),
                'query': match.group(2).strip(),
                'refresh_strategy': match.group(3) or 'full',
                'refresh_schedule': match.group(4) or 'manual',
                'schedule_interval': int(match.group(5)) if match.group(5) else None
            }
        
        # DROP MATERIALIZED VIEW
        match = self.DROP_MV_PATTERN.match(query)
        if match:
            return {
                'type': 'DROP_MATERIALIZED_VIEW',
                'command': 'drop_materialized_view',
                'name': match.group(1)
            }
        
        # REFRESH MATERIALIZED VIEW
        match = self.REFRESH_MV_PATTERN.match(query)
        if match:
            return {
                'type': 'REFRESH_MATERIALIZED_VIEW',
                'command': 'refresh_materialized_view',
                'name': match.group(1),
                'strategy': match.group(2)
            }
        
        # REFRESH ALL MATERIALIZED VIEWS
        if self.REFRESH_ALL_PATTERN.match(query):
            return {
                'type': 'REFRESH_ALL',
                'command': 'refresh_all'
            }
        
        # LIST MATERIALIZED VIEWS
        if self.LIST_MV_PATTERN.match(query):
            return {
                'type': 'LIST_MATERIALIZED_VIEWS',
                'command': 'list_materialized_views'
            }
        
        # SELECT FROM MV
        match = self.SELECT_MV_PATTERN.match(query)
        if match:
            return {
                'type': 'QUERY_MATERIALIZED_VIEW',
                'command': 'query_materialized_view',
                'name': match.group(1)
            }
        
        # SET REFRESH SCHEDULE
        match = self.SET_SCHEDULE_PATTERN.match(query)
        if match:
            return {
                'type': 'SET_REFRESH_SCHEDULE',
                'command': 'set_refresh_schedule',
                'name': match.group(1),
                'schedule': match.group(2),
                'interval': int(match.group(3)) if match.group(3) else None
            }
        
        # MATERIALIZED VIEW STATS
        match = self.MV_STATS_PATTERN.match(query)
        if match:
            return {
                'type': 'MV_STATS',
                'command': 'mv_stats',
                'name': match.group(1)
            }
        
        return None


_mv_parser = None


def get_mv_parser():
    global _mv_parser
    if _mv_parser is None:
        _mv_parser = MVParser()
    return _mv_parser
