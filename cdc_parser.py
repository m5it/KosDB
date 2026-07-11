"""
Parser extensions for CDC commands.
"""

import re
from typing import Dict, Any, Optional


class CDCParser:
    """
    Parser for CDC commands.
    
    Supports:
    - CDC START CONSUMER id [TABLES t1,t2] [OPS INSERT,UPDATE] [FORMAT json] [FROM_LATEST]
    - CDC STOP CONSUMER id
    - CDC LIST CONSUMERS
    - CDC STATS
    - CDC SETUP KAFKA servers [PREFIX prefix]
    - CDC SNAPSHOT tables
    """
    
    START_CONSUMER_PATTERN = re.compile(
        r'CDC\s+START\s+CONSUMER\s+(\w+)'
        r'(?:\s+TABLES\s+([\w,]+))?'
        r'(?:\s+OPS\s+([\w,]+))?'
        r'(?:\s+FORMAT\s+(\w+))?'
        r'(?:\s+(FROM_LATEST))?',
        re.IGNORECASE
    )
    
    STOP_CONSUMER_PATTERN = re.compile(
        r'CDC\s+STOP\s+CONSUMER\s+(\w+)',
        re.IGNORECASE
    )
    
    LIST_CONSUMERS_PATTERN = re.compile(
        r'CDC\s+LIST\s+CONSUMERS',
        re.IGNORECASE
    )
    
    CDC_STATS_PATTERN = re.compile(
        r'CDC\s+STATS',
        re.IGNORECASE
    )
    
    SETUP_KAFKA_PATTERN = re.compile(
        r'CDC\s+SETUP\s+KAFKA\s+(\S+)'
        r'(?:\s+PREFIX\s+(\S+))?',
        re.IGNORECASE
    )
    
    SNAPSHOT_PATTERN = re.compile(
        r'CDC\s+SNAPSHOT\s+([\w,]+)',
        re.IGNORECASE
    )
    
    def parse(self, query: str) -> Optional[Dict[str, Any]]:
        """Parse a CDC command."""
        query = query.strip()
        upper = query.upper()
        
        if not upper.startswith('CDC'):
            return None
        
        # CDC START CONSUMER
        match = self.START_CONSUMER_PATTERN.match(query)
        if match:
            return {
                'type': 'CDC_START_CONSUMER',
                'command': 'cdc_start_consumer',
                'consumer_id': match.group(1),
                'tables': match.group(2),
                'operations': match.group(3),
                'format': match.group(4) or 'json',
                'from_latest': bool(match.group(5))
            }
        
        # CDC STOP CONSUMER
        match = self.STOP_CONSUMER_PATTERN.match(query)
        if match:
            return {
                'type': 'CDC_STOP_CONSUMER',
                'command': 'cdc_stop_consumer',
                'consumer_id': match.group(1)
            }
        
        # CDC LIST CONSUMERS
        if self.LIST_CONSUMERS_PATTERN.match(query):
            return {
                'type': 'CDC_LIST_CONSUMERS',
                'command': 'cdc_list_consumers'
            }
        
        # CDC STATS
        if self.CDC_STATS_PATTERN.match(query):
            return {
                'type': 'CDC_STATS',
                'command': 'cdc_stats'
            }
        
        # CDC SETUP KAFKA
        match = self.SETUP_KAFKA_PATTERN.match(query)
        if match:
            return {
                'type': 'CDC_SETUP_KAFKA',
                'command': 'cdc_setup_kafka',
                'bootstrap_servers': match.group(1),
                'topic_prefix': match.group(2) or 'kosdb.cdc'
            }
        
        # CDC SNAPSHOT
        match = self.SNAPSHOT_PATTERN.match(query)
        if match:
            return {
                'type': 'CDC_SNAPSHOT',
                'command': 'cdc_create_snapshot',
                'tables': match.group(1)
            }
        
        return None


_cdc_parser = None


def get_cdc_parser():
    global _cdc_parser
    if _cdc_parser is None:
        _cdc_parser = CDCParser()
    return _cdc_parser
