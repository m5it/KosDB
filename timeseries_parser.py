"""
Parser extensions for time-series commands.

Adds CREATE HYPERTABLE, INSERT, SELECT, TIME_BUCKET, DOWNSAMPLE, 
RETENTION POLICY, and FIRST/LAST commands.
"""

import re
from typing import Dict, Any, Optional
from datetime import datetime


class TimeSeriesParser:
    """
    Parser for time-series commands.
    
    Supports:
    - CREATE HYPERTABLE name [CHUNK_INTERVAL interval] [RETENTION period]
    - DROP HYPERTABLE name
    - INSERT INTO hypertable VALUES (timestamp, value, tags)
    - SELECT * FROM hypertable WHERE time > start AND time < end
    - TIME_BUCKET(bucket_size, hypertable, [aggregation])
    - DOWNSAMPLE hypertable FROM source TO target
    - RETENTION POLICY APPLY hypertable
    - FIRST/LAST hypertable [WHERE time > start]
    - HYPERTABLE STATS [name]
    - LIST HYPERTABLES
    """
    
    # Command patterns
    CREATE_HYPERTABLE_PATTERN = re.compile(
        r'CREATE\s+HYPERTABLE\s+(\w+)'
        r'(?:\s+CHUNK[_-]?INTERVAL\s+(\w+))?'
        r'(?:\s+RETENTION\s+(\w+))?',
        re.IGNORECASE
    )
    
    DROP_HYPERTABLE_PATTERN = re.compile(
        r'DROP\s+HYPERTABLE\s+(\w+)',
        re.IGNORECASE
    )
    
    INSERT_PATTERN = re.compile(
        r'INSERT\s+INTO\s+(\w+)\s+VALUES\s*\('
        r'([^,]+),\s*([^,]+)'
        r'(?:,\s*(\{[^}]*\}))?\s*\)',
        re.IGNORECASE
    )
    
    SELECT_PATTERN = re.compile(
        r'SELECT\s+(?:\*\s+)?FROM\s+(\w+)'
        r'(?:\s+WHERE\s+time\s*>\s*(\d+|\w+))?'
        r'(?:\s+AND\s+time\s*<\s*(\d+|\w+))?'
        r'(?:\s+LIMIT\s+(\d+))?',
        re.IGNORECASE
    )
    
    TIME_BUCKET_PATTERN = re.compile(
        r'TIME[_-]?BUCKET\s*\(\s*(\'[^\']+\'|\w+)\s*,\s*(\w+)\s*'
        r'(?:,\s*(\w+))?\s*\)',
        re.IGNORECASE
    )
    
    DOWNSAMPLE_PATTERN = re.compile(
        r'DOWNSAMPLE\s+(\w+)'
        r'\s+FROM\s+(\w+)'
        r'\s+TO\s+(\w+)'
        r'(?:\s+WHERE\s+time\s*>\s*(\d+))?'
        r'(?:\s+AND\s+time\s*<\s*(\d+))?',
        re.IGNORECASE
    )
    
    RETENTION_APPLY_PATTERN = re.compile(
        r'RETENTION\s+POLICY\s+APPLY\s+(\w+)',
        re.IGNORECASE
    )
    
    RETENTION_SHOW_PATTERN = re.compile(
        r'RETENTION\s+POLICY\s+SHOW\s+(\w+)',
        re.IGNORECASE
    )
    
    FIRST_PATTERN = re.compile(
        r'FIRST\s+(\w+)'
        r'(?:\s+WHERE\s+time\s*>\s*(\d+))?',
        re.IGNORECASE
    )
    
    LAST_PATTERN = re.compile(
        r'LAST\s+(\w+)'
        r'(?:\s+WHERE\s+time\s*<\s*(\d+))?',
        re.IGNORECASE
    )
    
    HYPERTABLE_STATS_PATTERN = re.compile(
        r'HYPERTABLE\s+STATS(?:\s+(\w+))?',
        re.IGNORECASE
    )
    
    LIST_HYPERTABLES_PATTERN = re.compile(
        r'LIST\s+HYPERTABLES',
        re.IGNORECASE
    )
    
    def parse(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Parse a time-series command.
        
        Args:
            query: SQL command string
        
        Returns:
            Parsed command dict or None if not recognized
        """
        query = query.strip()
        upper = query.upper()
        
        # CREATE HYPERTABLE
        match = self.CREATE_HYPERTABLE_PATTERN.match(query)
        if match:
            return {
                'type': 'CREATE_HYPERTABLE',
                'command': 'create_hypertable',
                'name': match.group(1),
                'chunk_interval': match.group(2) or '1d',
                'retention': match.group(3)
            }
        
        # DROP HYPERTABLE
        match = self.DROP_HYPERTABLE_PATTERN.match(query)
        if match:
            return {
                'type': 'DROP_HYPERTABLE',
                'command': 'drop_hypertable',
                'name': match.group(1)
            }
        
        # INSERT
        match = self.INSERT_PATTERN.match(query)
        if match:
            timestamp_str = match.group(2).strip()
            value_str = match.group(3).strip()
            tags_str = match.group(4)
            
            # Parse timestamp
            if timestamp_str.upper() == 'NOW':
                timestamp = None
            else:
                try:
                    timestamp = float(timestamp_str)
                except ValueError:
                    # Try to parse as ISO format
                    try:
                        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        timestamp = dt.timestamp()
                    except:
                        timestamp = None
            
            # Parse value
            try:
                value = float(value_str)
            except ValueError:
                value = value_str.strip("'\"")
            
            # Parse tags
            tags = {}
            if tags_str:
                try:
                    import json
                    tags = json.loads(tags_str)
                except:
                    pass
            
            return {
                'type': 'INSERT',
                'command': 'insert_timeseries',
                'table_name': match.group(1),
                'timestamp': timestamp,
                'value': value,
                'tags': tags
            }
        
        # SELECT
        match = self.SELECT_PATTERN.match(query)
        if match:
            start = self._parse_timestamp(match.group(2))
            end = self._parse_timestamp(match.group(3))
            
            return {
                'type': 'SELECT',
                'command': 'select_timeseries',
                'table_name': match.group(1),
                'start': start,
                'end': end,
                'limit': int(match.group(4)) if match.group(4) else 1000
            }
        
        # TIME_BUCKET
        match = self.TIME_BUCKET_PATTERN.match(query)
        if match:
            bucket_size = match.group(1).strip("'\"")
            aggregation = match.group(3) or 'avg'
            
            return {
                'type': 'TIME_BUCKET',
                'command': 'time_bucket',
                'bucket_size': bucket_size,
                'table_name': match.group(2),
                'aggregation': aggregation
            }
        
        # DOWNSAMPLE
        match = self.DOWNSAMPLE_PATTERN.match(query)
        if match:
            return {
                'type': 'DOWNSAMPLE',
                'command': 'downsample',
                'table_name': match.group(1),
                'source_bucket': match.group(2),
                'target_bucket': match.group(3),
                'start': float(match.group(4)) if match.group(4) else None,
                'end': float(match.group(5)) if match.group(5) else None
            }
        
        # RETENTION APPLY
        match = self.RETENTION_APPLY_PATTERN.match(query)
        if match:
            return {
                'type': 'RETENTION_APPLY',
                'command': 'retention_policy',
                'action': 'apply',
                'table_name': match.group(1)
            }
        
        # RETENTION SHOW
        match = self.RETENTION_SHOW_PATTERN.match(query)
        if match:
            return {
                'type': 'RETENTION_SHOW',
                'command': 'retention_policy',
                'action': 'show',
                'table_name': match.group(1)
            }
        
        # FIRST
        match = self.FIRST_PATTERN.match(query)
        if match:
            return {
                'type': 'FIRST',
                'command': 'first_last',
                'function': 'first',
                'table_name': match.group(1),
                'start': float(match.group(2)) if match.group(2) else None
            }
        
        # LAST
        match = self.LAST_PATTERN.match(query)
        if match:
            return {
                'type': 'LAST',
                'command': 'first_last',
                'function': 'last',
                'table_name': match.group(1),
                'end': float(match.group(2)) if match.group(2) else None
            }
        
        # HYPERTABLE STATS
        match = self.HYPERTABLE_STATS_PATTERN.match(query)
        if match:
            return {
                'type': 'HYPERTABLE_STATS',
                'command': 'hypertable_stats',
                'table_name': match.group(1)
            }
        
        # LIST HYPERTABLES
        if self.LIST_HYPERTABLES_PATTERN.match(query):
            return {
                'type': 'LIST_HYPERTABLES',
                'command': 'list_hypertables'
            }
        
        return None
    
    def _parse_timestamp(self, ts_str: Optional[str]) -> Optional[float]:
        """Parse timestamp string."""
        if not ts_str:
            return None
        
        ts_str = ts_str.strip()
        
        if ts_str.upper() == 'NOW':
            return None
        
        try:
            return float(ts_str)
        except ValueError:
            # Try ISO format
            try:
                dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                return dt.timestamp()
            except:
                return None


# Singleton parser instance
_timeseries_parser: Optional[TimeSeriesParser] = None


def get_timeseries_parser() -> TimeSeriesParser:
    """Get global time-series parser."""
    global _timeseries_parser
    if _timeseries_parser is None:
        _timeseries_parser = TimeSeriesParser()
    return _timeseries_parser
