"""
Materialized View Manager for KosDB v3.4.0

Provides materialized view support with:
- Fast refresh: Incremental updates using change tracking
- Complete refresh: Full rebuild from base tables
- Manual refresh: On-demand refresh via command
- Automatic refresh: Scheduled background refresh
- Query rewrite: Route queries to materialized views
- Staleness tracking: Track data freshness

Example:
    CREATE MATERIALIZED VIEW mv_sales_summary
    BUILD IMMEDIATE
    REFRESH FAST ON COMMIT
    ENABLE QUERY REWRITE
    AS
    SELECT 
        date_trunc('month', sale_date) as month,
        region,
        SUM(amount) as total_sales,
        COUNT(*) as transaction_count
    FROM sales
    GROUP BY date_trunc('month', sale_date), region;
    
    -- Refresh the view
    REFRESH MATERIALIZED VIEW mv_sales_summary;
    
    -- Fast refresh (incremental)
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_sales_summary;
"""

import re
import time
import hashlib
import threading
from typing import Dict, Any, List, Optional, Tuple, Set, Callable, Union
from dataclasses import dataclass, field
from enum import Enum, auto
from datetime import datetime, timedelta


class RefreshType(Enum):
    """Materialized view refresh strategies."""
    COMPLETE = "COMPLETE"      # Full rebuild
    FAST = "FAST"              # Incremental refresh
    FORCE = "FORCE"          # Fast if possible, else complete
    NEVER = "NEVER"            # No automatic refresh


class RefreshTiming(Enum):
    """When to refresh materialized views."""
    ON_DEMAND = "ON DEMAND"    # Manual refresh only
    ON_COMMIT = "ON COMMIT"    # Refresh on base table commit
    START_WITH = "START WITH"  # Refresh on schedule


class BuildType(Enum):
    """Build options for materialized views."""
    IMMEDIATE = "IMMEDIATE"    # Build immediately on creation
    DEFERRED = "DEFERRED"      # Build on first refresh


@dataclass
class MaterializedView:
    """Represents a materialized view."""
    name: str
    query: str                      # Source query
    base_tables: List[str]          # Tables the view depends on
    columns: List[str]            # Output columns
    
    # Refresh configuration
    refresh_type: RefreshType = RefreshType.COMPLETE
    refresh_timing: RefreshTiming = RefreshTiming.ON_DEMAND
    build_type: BuildType = BuildType.IMMEDIATE
    
    # Query rewrite
    enable_query_rewrite: bool = False
    rewrite_integrity: str = "ENFORCED"  # ENFORCED or TRUSTED
    
    # State
    data: List[Dict[str, Any]] = field(default_factory=list)
    is_stale: bool = False
    last_refresh: Optional[float] = None
    last_refresh_type: Optional[str] = None
    refresh_count: int = 0
    error_count: int = 0
    last_error: Optional[str] = None
    
    # Change tracking for fast refresh
    change_log: List[Dict] = field(default_factory=list)
    has_aggregate: bool = False     # Contains GROUP BY, SUM, etc.
    has_join: bool = False          # Contains JOIN
    
    # Statistics
    row_count: int = 0
    size_bytes: int = 0
    
    def touch(self):
        """Update access time."""
        self.last_accessed = time.time()
    
    last_accessed: Optional[float] = field(default=None)


class QueryRewriteRule:
    """
    Rule for rewriting queries to use materialized views.
    """
    
    def __init__(self, mv: MaterializedView):
        self.mv = mv
        self.query_pattern = self._compile_pattern(mv.query)
    
    def _compile_pattern(self, query: str) -> Dict:
        """Compile query into matchable pattern."""
        # Extract key components
        pattern = {
            'tables': mv.base_tables,
            'columns': mv.columns,
            'has_aggregate': mv.has_aggregate,
            'has_group_by': 'GROUP BY' in query.upper()
        }
        return pattern
    
    def can_rewrite(self, query: str, query_tables: List[str]) -> bool:
        """
        Check if query can be rewritten to use materialized view.
        
        Args:
            query: User query
            query_tables: Tables referenced in query
        
        Returns:
            True if rewrite is possible
        """
        # Check if MV is stale
        if self.mv.is_stale and self.mv.rewrite_integrity == "ENFORCED":
            return False
        
        # Check if query tables are subset of MV tables
        if not set(query_tables).issubset(set(self.mv.base_tables)):
            return False
        
        # Check if query columns are subset of MV columns
        # (Simplified - would need proper parsing in production)
        
        return True
    
    def rewrite_query(self, query: str) -> str:
        """Rewrite query to use materialized view."""
        # Replace FROM clause with MV name
        # This is simplified - production would use proper AST transformation
        
        pattern = r'FROM\s+(\w+(?:\s*,\s*\w+)*)'
        replacement = f'FROM {self.mv.name}'
        
        rewritten = re.sub(pattern, replacement, query, flags=re.IGNORECASE)
        return rewritten


class MaterializedViewManager:
    """
    Main materialized view manager for KosDB.
    """
    
    def __init__(self, 
                 execute_query_func: Optional[Callable] = None,
                 get_table_data_func: Optional[Callable] = None):
        self.views: Dict[str, MaterializedView] = {}
        self.rewrite_rules: Dict[str, QueryRewriteRule] = {}
        self._execute_query = execute_query_func or self._default_execute
        self._get_table_data = get_table_data_func or self._default_get_data
        self._lock = threading.RLock()
        self._refresh_schedulers: Dict[str, threading.Timer] = {}
        
        # Statistics
        self.stats = {
            'views_created': 0,
            'views_dropped': 0,
            'refreshes_complete': 0,
            'refreshes_fast': 0,
            'query_rewrites': 0,
            'rewrite_failures': 0
        }
    
    def create_materialized_view(self,
                                  name: str,
                                  query: str,
                                  base_tables: List[str],
                                  columns: List[str],
                                  refresh_type: str = "COMPLETE",
                                  refresh_timing: str = "ON DEMAND",
                                  build_type: str = "IMMEDIATE",
                                  enable_query_rewrite: bool = False) -> MaterializedView:
        """
        Create a materialized view.
        
        Args:
            name: View name
            query: Source query
            base_tables: Base tables the view depends on
            columns: Output column names
            refresh_type: COMPLETE, FAST, FORCE, or NEVER
            refresh_timing: ON DEMAND, ON COMMIT, or START WITH
            build_type: IMMEDIATE or DEFERRED
            enable_query_rewrite: Enable automatic query rewrite
        
        Returns:
            Created MaterializedView
        """
        with self._lock:
            if name.upper() in self.views:
                raise ValueError(f"Materialized view '{name}' already exists")
            
            # Parse refresh configuration
            try:
                rt = RefreshType(refresh_type.upper())
                rtiming = RefreshTiming(refresh_timing.upper().replace('_', ' '))
                bt = BuildType(build_type.upper())
            except ValueError as e:
                raise ValueError(f"Invalid refresh configuration: {e}")
            
            # Analyze query for fast refresh capability
            has_aggregate = self._detect_aggregates(query)
            has_join = 'JOIN' in query.upper()
            
            # Fast refresh requires specific conditions
            if rt == RefreshType.FAST:
                if not self._can_fast_refresh(query):
                    raise ValueError(
                        "Query does not support fast refresh. "
                        "Requires materialized view log on base tables."
                    )
            
            mv = MaterializedView(
                name=name,
                query=query,
                base_tables=base_tables,
                columns=columns,
                refresh_type=rt,
                refresh_timing=rtiming,
                build_type=bt,
                enable_query_rewrite=enable_query_rewrite,
                has_aggregate=has_aggregate,
                has_join=has_join
            )
            
            self.views[name.upper()] = mv
            self.stats['views_created'] += 1
            
            # Build immediately if requested
            if bt == BuildType.IMMEDIATE:
                self._refresh_complete(mv)
            
            # Create rewrite rule if enabled
            if enable_query_rewrite:
                self.rewrite_rules[name.upper()] = QueryRewriteRule(mv)
            
            return mv
    
    def _detect_aggregates(self, query: str) -> bool:
        """Detect if query contains aggregate functions."""
        aggregates = ['SUM(', 'COUNT(', 'AVG(', 'MIN(', 'MAX(', 'GROUP BY']
n        return any(agg in query.upper() for agg in aggregates)\n    \n    def _can_fast_refresh(self, query: str) -> bool:\n        \"\"\"Check if query supports fast refresh.\"\"\"\n        # Fast refresh requires:\n        # - Materialized view logs on base tables\n        # - No certain complex operations\n        \n        unsupported = ['DISTINCT', 'UNION', 'INTERSECT', 'EXCEPT']\n        if any(op in query.upper() for op in unsupported):\n            return False\n        \n        return True  # Simplified - would check actual log tables\n    \n    def drop_materialized_view(self, name: str) -> bool:\n        \"\"\"Drop a materialized view.\"\"\"\n        with self._lock:\n            name_upper = name.upper()\n            if name_upper not in self.views:\n                return False\n            \n            # Cancel any scheduled refresh\n            if name_upper in self._refresh_schedulers:\n                self._refresh_schedulers[name_upper].cancel()\n                del self._refresh_schedulers[name_upper]\n            \n            del self.views[name_upper]\n            if name_upper in self.rewrite_rules:\n                del self.rewrite_rules[name_upper]\n            \n            self.stats['views_dropped'] += 1\n            return True\n    \n    def refresh(self, \n                name: str, \n                refresh_type: Optional[str] = None,\n                concurrently: bool = False) -> Dict[str, Any]:\n        \"\"\"\n        Refresh a materialized view.\n        \n        Args:\n            name: View name\n            refresh_type: COMPLETE or FAST (None = use view's default)\n            concurrently: Allow queries during refresh\n        \n        Returns:\n            Refresh statistics\n        \"\"\"\n        with self._lock:\n            mv = self.views.get(name.upper())\n            if not mv:\n                raise ValueError(f\"Materialized view '{name}' not found\")\n            \n            start_time = time.time()\n            \n            try:\n                # Determine refresh type\n                rt = refresh_type or mv.refresh_type.value\n                \n                if rt == \"FAST\" and mv.refresh_type == RefreshType.FAST:\n                    rows_affected = self._refresh_fast(mv)\n                    mv.last_refresh_type = \"FAST\"\n                    self.stats['refreshes_fast'] += 1\n                else:\n                    rows_affected = self._refresh_complete(mv)\n                    mv.last_refresh_type = \"COMPLETE\"\n                    self.stats['refreshes_complete'] += 1\n                \n                mv.last_refresh = time.time()\n                mv.is_stale = False\n                mv.refresh_count += 1\n                mv.error_count = 0\n                mv.last_error = None\n                \n                duration = time.time() - start_time\n                \n                return {\n                    'view': mv.name,\n                    'refresh_type': mv.last_refresh_type,\n                    'rows_affected': rows_affected,\n                    'duration_ms': int(duration * 1000),\n                    'success': True\n                }\n                \n            except Exception as e:\n                mv.error_count += 1\n                mv.last_error = str(e)\n                raise RefreshError(f\"Refresh failed: {e}\") from e\n    \n    def _refresh_complete(self, mv: MaterializedView) -> int:\n        \"\"\"Complete refresh - rebuild from scratch.\"\"\"\n        # Execute source query\n        result = self._execute_query(mv.query)\n        \n        # Replace data\n        mv.data = result if result else []\n        mv.row_count = len(mv.data)\n        mv.size_bytes = self._estimate_size(mv.data)\n        \n        return mv.row_count\n    \n    def _refresh_fast(self, mv: MaterializedView) -> int:\n        \"\"\"Fast refresh - incremental update.\"\"\"\n        # Apply changes from change log\n        changes = mv.change_log\n        mv.change_log = []  # Clear log\n        \n        rows_affected = 0\n        \n        for change in changes:\n            operation = change.get('operation')\n            \n            if operation == 'INSERT':\n                # Add new row if it matches view criteria\n                if self._row_matches_view(change['data'], mv):\n                    mv.data.append(change['data'])\n                    rows_affected += 1\n            \n            elif operation == 'DELETE':\n                # Remove matching rows\n                old_len = len(mv.data)\n                mv.data = [r for r in mv.data \n                          if not self._rows_match(r, change['data'], mv.columns)]\n                rows_affected += old_len - len(mv.data)\n            \n            elif operation == 'UPDATE':\n                # Update matching rows\n                for i, row in enumerate(mv.data):\n                    if self._rows_match(row, change['old_data'], mv.columns):\n                        mv.data[i] = change['new_data']\n                        rows_affected += 1\n        \n        # Re-aggregate if needed\n        if mv.has_aggregate:\n            mv.data = self._reaggregate(mv.data, mv.query)\n        \n        mv.row_count = len(mv.data)\n        return rows_affected\n    \n    def _row_matches_view(self, row: Dict, mv: MaterializedView) -> bool:\n        \"\"\"Check if a row matches the view's filter criteria.\"\"\"\n        # Simplified - would evaluate WHERE clause\n        return True\n    \n    def _rows_match(self, \n                    row1: Dict, \n                    row2: Dict, \n                    columns: List[str]) -> bool:\n        \"\"\"Check if two rows match on key columns.\"\"\"\n        for col in columns:\n            if row1.get(col) != row2.get(col):\n                return False\n        return True\n    \n    def _reaggregate(self, \n                     data: List[Dict], \n                     query: str) -> List[Dict]:\n        \"\"\"Re-aggregate data after changes.\"\"\"\n        # Simplified - would parse and re-execute GROUP BY\n        return data\n    \n    def _estimate_size(self, data: List[Dict]) -> int:\n        \"\"\"Estimate size of data in bytes.\"\"\"\n        if not data:\n            return 0\n        \n        # Rough estimate\n        sample = str(data[0])\n        return len(sample) * len(data)\n    \n    def record_change(self,\n                      table: str,\n                      operation: str,\n                      old_data: Optional[Dict] = None,\n                      new_data: Optional[Dict] = None):\n        \"\"\"\n        Record a change to base table for fast refresh.\n        \n        Args:\n            table: Table that changed\n            operation: INSERT, UPDATE, or DELETE\n            old_data: Row data before change\n            new_data: Row data after change\n        \"\"\"\n        with self._lock:\n            for mv in self.views.values():\n                if table.upper() in [t.upper() for t in mv.base_tables]:\n                    mv.change_log.append({\n                        'table': table,\n                        'operation': operation,\n                        'old_data': old_data,\n                        'new_data': new_data,\n                        'timestamp': time.time()\n                    })\n                    mv.is_stale = True\n    \n    def try_rewrite_query(self, \n                         query: str, \n                         query_tables: List[str]) -> Tuple[str, bool]:\n        \"\"\"\n        Try to rewrite query to use materialized views.\n        \n        Args:\n            query: Original query\n            query_tables: Tables referenced in query\n        \n        Returns:\n            Tuple of (rewritten_query, was_rewritten)\n        \"\"\"\n        for rule in self.rewrite_rules.values():\n            if rule.can_rewrite(query, query_tables):\n                try:\n                    rewritten = rule.rewrite_query(query)\n                    self.stats['query_rewrites'] += 1\n                    return rewritten, True\n                except Exception:\n                    self.stats['rewrite_failures'] += 1\n        \n        return query, False\n    \n    def get_view_info(self, name: str) -> Optional[Dict]:\n        \"\"\"Get materialized view information.\"\"\"\n        mv = self.views.get(name.upper())\n        if not mv:\n            return None\n        \n        return {\n            'name': mv.name,\n            'query': mv.query[:100] + '...' if len(mv.query) > 100 else mv.query,\n            'base_tables': mv.base_tables,\n            'columns': mv.columns,\n            'refresh_type': mv.refresh_type.value,\n            'refresh_timing': mv.refresh_timing.value,\n            'enable_query_rewrite': mv.enable_query_rewrite,\n            'is_stale': mv.is_stale,\n            'last_refresh': mv.last_refresh,\n            'last_refresh_type': mv.last_refresh_type,\n            'refresh_count': mv.refresh_count,\n            'row_count': mv.row_count,\n            'size_bytes': mv.size_bytes,\n            'error_count': mv.error_count\n        }\n    \n    def list_materialized_views(self, \n                                 stale_only: bool = False) -> List[Dict]:\n        \"\"\"List materialized views.\"\"\"\n        result = []\n        for mv in self.views.values():\n            if stale_only and not mv.is_stale:\n                continue\n            result.append(self.get_view_info(mv.name))\n        return result\n    \n    def get_stats(self) -> Dict[str, Any]:\n        \"\"\"Get manager statistics.\"\"\"\n        return {\n            **self.stats,\n            'total_views': len(self.views),\n            'stale_views': sum(1 for mv in self.views.values() if mv.is_stale),\n            'views_with_rewrite': len(self.rewrite_rules)\n        }\n    \n    def _default_execute(self, query: str) -> List[Dict]:\n        \"\"\"Default query execution.\"\"\"\n        return []\n    \n    def _default_get_data(self, table: str) -> List[Dict]:\n        \"\"\"Default data retrieval.\"\"\"\n        return []\n\n\nclass RefreshError(Exception):\n    \"\"\"Error during materialized view refresh.\"\"\"\n    pass\n\n\ndef parse_create_materialized_view(sql: str) -> Dict[str, Any]:\n    \"\"\"\n    Parse CREATE MATERIALIZED VIEW statement.\n    \n    Returns:\n        Dictionary with view components\n    \"\"\"\n    pattern = re.compile(\n        r'CREATE\\s+MATERIALIZED\\s+VIEW\\s+(?P<name>\\w+)\\s*'\n        r'(?:\\s*BUILD\\s+(?P<build>IMMEDIATE|DEFERRED))?'\n        r'(?:\\s*REFRESH\\s+(?P<refresh>FAST|COMPLETE|FORCE|ON\\s+DEMAND|ON\\s+COMMIT))?'\n        r'(?:\\s*(?P<rewrite>ENABLE|DISABLE)\\s+QUERY\\s+REWRITE)?'\n        r'\\s*AS\\s*(?P<query>.+)',\n        re.IGNORECASE | re.DOTALL\n    )\n    \n    match = pattern.match(sql.strip())\n    if not match:\n        raise ValueError(\"Invalid CREATE MATERIALIZED VIEW syntax\")\n    \n    result = match.groupdict()\n    \n    # Normalize values\n    if result.get('build'):\n        result['build'] = result['build'].upper()\n    \n    if result.get('refresh'):\n        refresh = result['refresh'].upper()\n        if refresh in ('FAST', 'COMPLETE', 'FORCE'):\n            result['refresh_type'] = refresh\n            result['refresh_timing'] = 'ON DEMAND'\n        elif 'ON' in refresh:\n            result['refresh_type'] = 'COMPLETE'\n            result['refresh_timing'] = refresh\n    \n    result['enable_query_rewrite'] = result.get('rewrite', '').upper() == 'ENABLE'\n    \n    return result\n\n\n# Example usage\nif __name__ == '__main__':\n    manager = MaterializedViewManager()\n    \n    # Create materialized view\n    mv = manager.create_materialized_view(\n        name='mv_sales_summary',\n        query='SELECT region, SUM(amount) as total FROM sales GROUP BY region',\n        base_tables=['sales'],\n        columns=['region', 'total'],\n        refresh_type='COMPLETE',\n        refresh_timing='ON DEMAND',\n        enable_query_rewrite=True\n    )\n    \n    print(f\"Created materialized view: {mv.name}\")\n    print(f\"Refresh type: {mv.refresh_type.value}\")\n    print(f\"Query rewrite enabled: {mv.enable_query_rewrite}\")\n    \n    # Test query rewrite\n    query = \"SELECT region, SUM(amount) FROM sales GROUP BY region\"\n    rewritten, was_rewritten = manager.try_rewrite_query(query, ['sales'])\n    \n    if was_rewritten:\n        print(f\"Query rewritten to use: {rewritten}\")\n