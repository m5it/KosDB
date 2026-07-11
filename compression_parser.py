"""
Parser extensions for compression commands.

Adds COMPRESSION ENABLE/DISABLE/STATS/ALGORITHMS/BENCHMARK/TEST/CACHE commands.
"""

import re
from typing import Dict, Any, Optional


class CompressionParser:
    """
    Parser for compression management commands.
    
    Supports:
    - COMPRESSION ENABLE table_name [ALGORITHM name] [LEVEL n] [MIN_SIZE n]
    - COMPRESSION DISABLE table_name
    - COMPRESSION STATS [table_name]
    - COMPRESSION ALGORITHMS
    - COMPRESSION BENCHMARK [DATA_SIZE n]
    - COMPRESSION TEST table_name [SAMPLE_SIZE n]
    - COMPRESSION CACHE STATS [table_name]
    """
    
    # Command patterns
    COMPRESSION_ENABLE_PATTERN = re.compile(
        r'COMPRESSION\s+ENABLE\s+(\w+)'
        r'(?:\s+ALGORITHM\s+(\w+))?'
        r'(?:\s+LEVEL\s+(\d+))?'
        r'(?:\s+MIN[_-]?SIZE\s+(\d+))?',
        re.IGNORECASE
    )
    
    COMPRESSION_DISABLE_PATTERN = re.compile(
        r'COMPRESSION\s+DISABLE\s+(\w+)',
        re.IGNORECASE
    )
    
    COMPRESSION_STATS_PATTERN = re.compile(
        r'COMPRESSION\s+STATS(?:\s+(\w+))?',
        re.IGNORECASE
    )
    
    COMPRESSION_ALGORITHMS_PATTERN = re.compile(
        r'COMPRESSION\s+ALGORITHMS',
        re.IGNORECASE
    )
    
    COMPRESSION_BENCHMARK_PATTERN = re.compile(
        r'COMPRESSION\s+BENCHMARK'
        r'(?:\s+DATA[_-]?SIZE\s+(\d+))?',
        re.IGNORECASE
    )
    
    COMPRESSION_TEST_PATTERN = re.compile(
        r'COMPRESSION\s+TEST\s+(\w+)'
        r'(?:\s+SAMPLE[_-]?SIZE\s+(\d+))?',
        re.IGNORECASE
    )
    
    COMPRESSION_CACHE_STATS_PATTERN = re.compile(
        r'COMPRESSION\s+CACHE\s+STATS(?:\s+(\w+))?',
        re.IGNORECASE
    )
    
    def parse(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Parse a compression command.
        
        Args:
            query: SQL command string
        
        Returns:
            Parsed command dict or None if not recognized
        """
        query = query.strip()
        upper = query.upper()
        
        if not upper.startswith('COMPRESSION'):
            return None
        
        # COMPRESSION ENABLE
        match = self.COMPRESSION_ENABLE_PATTERN.match(query)
        if match:
            return {
                'type': 'COMPRESSION_ENABLE',
                'command': 'compression_enable',
                'table_name': match.group(1),
                'algorithm': match.group(2) or 'zlib',
                'level': int(match.group(3)) if match.group(3) else 6,
                'min_size': int(match.group(4)) if match.group(4) else 100
            }
        
        # COMPRESSION DISABLE
        match = self.COMPRESSION_DISABLE_PATTERN.match(query)
        if match:
            return {
                'type': 'COMPRESSION_DISABLE',
                'command': 'compression_disable',
                'table_name': match.group(1)
            }
        
        # COMPRESSION STATS
        match = self.COMPRESSION_STATS_PATTERN.match(query)
        if match:
            return {
                'type': 'COMPRESSION_STATS',
                'command': 'compression_stats',
                'table_name': match.group(1)
            }
        
        # COMPRESSION ALGORITHMS
        if self.COMPRESSION_ALGORITHMS_PATTERN.match(query):
            return {
                'type': 'COMPRESSION_ALGORITHMS',
                'command': 'compression_algorithms'
            }
        
        # COMPRESSION BENCHMARK
        match = self.COMPRESSION_BENCHMARK_PATTERN.match(query)
        if match:
            return {
                'type': 'COMPRESSION_BENCHMARK',
                'command': 'compression_benchmark',
                'data_size': int(match.group(1)) if match.group(1) else 10000
            }
        
        # COMPRESSION TEST
        match = self.COMPRESSION_TEST_PATTERN.match(query)
        if match:
            return {
                'type': 'COMPRESSION_TEST',
                'command': 'compression_test',
                'table_name': match.group(1),
                'sample_size': int(match.group(2)) if match.group(2) else 100
            }
        
        # COMPRESSION CACHE STATS
        match = self.COMPRESSION_CACHE_STATS_PATTERN.match(query)
        if match:
            return {
                'type': 'COMPRESSION_CACHE_STATS',
                'command': 'compression_cache_stats',
                'table_name': match.group(1)
            }
        
        return None


# Singleton parser instance
_compression_parser: Optional[CompressionParser] = None


def get_compression_parser() -> CompressionParser:
    """Get global compression parser."""
    global _compression_parser
    if _compression_parser is None:
        _compression_parser = CompressionParser()
    return _compression_parser
