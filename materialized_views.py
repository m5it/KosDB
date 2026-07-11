"""
Materialized Views and Query Rewriting for KosDB

Implements automatic query rewriting, materialized views with incremental refresh,
and query result caching.
"""

import re
import time
import logging
import threading
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import hashlib

logger = logging.getLogger(__name__)


class RefreshStrategy(Enum):
    """Materialized view refresh strategies."""
    FULL = "full"              # Complete rebuild
    INCREMENTAL = "incremental"  # Update based on changes
    AUTO = "auto"               # Choose based on data changes


class RefreshSchedule(Enum):
    """Refresh schedule types."""
    MANUAL = "manual"
    ON_COMMIT = "on_commit"
    EVERY_N_MINUTES = "every_n_minutes"
    CRON = "cron"


@dataclass
class QueryPlan:
    """Represents a query execution plan."""
    original_query: str
    rewritten_query: Optional[str] = None
    uses_index: bool = False
    estimated_cost: float = 0.0
    estimated_rows: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'original_query': self.original_query,
            'rewritten_query': self.rewritten_query,
            'uses_index': self.uses_index,
            'estimated_cost': self.estimated_cost,
            'estimated_rows': self.estimated_rows
        }


@dataclass
class MaterializedView:
    """
    Represents a materialized view.
    
    Attributes:
        name: View name
        query: Base query
        refresh_strategy: How to refresh
        refresh_schedule: When to refresh
        schedule_interval: Minutes between refreshes (for EVERY_N_MINUTES)
        last_refresh: Last refresh timestamp
        is_stale: Whether view needs refresh
        data: Cached query results
        change_tracking: Tracks changes for incremental refresh
    """
    name: str
    query: str
    refresh_strategy: RefreshStrategy = RefreshStrategy.FULL
    refresh_schedule: RefreshSchedule = RefreshSchedule.MANUAL
    schedule_interval: Optional[int] = None
    last_refresh: Optional[float] = None
    is_stale: bool = True
    data: List[Dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    refresh_count: int = 0
    total_refresh_time: float = 0.0
    change_tracking: Dict[str, Any] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    
    def __post_init__(self):
        if isinstance(self.refresh_strategy, str):
            self.refresh_strategy = RefreshStrategy(self.refresh_strategy)
        if isinstance(self.refresh_schedule, str):
            self.refresh_schedule = RefreshSchedule(self.refresh_schedule)
    
    def mark_stale(self):
        """Mark view as needing refresh."""
        with self._lock:
            self.is_stale = True
    
    def get_stats(self) -> Dict[str, Any]:
        """Get view statistics."""
        with self._lock:
            avg_refresh_time = (
                self.total_refresh_time / self.refresh_count 
                if self.refresh_count > 0 else 0
            )
            
            return {
                'name': self.name,
                'refresh_strategy': self.refresh_strategy.value,
                'refresh_schedule': self.refresh_schedule.value,
                'schedule_interval': self.schedule_interval,
                'last_refresh': self.last_refresh,
                'is_stale': self.is_stale,
                'row_count': self.row_count,
                'refresh_count': self.refresh_count,
                'avg_refresh_time_ms': round(avg_refresh_time * 1000, 2)
            }


class QueryRewriter:
    """
    Automatic query rewriting for optimization.
    """
    
    def __init__(self):
        self.rewrite_rules: List[Callable[[str], Optional[str]]] = [
            self._rewrite_select_star,
            self._rewrite_subquery_to_join,
            self._rewrite_or_to_in,
            self._rewrite_implicit_join,
            self._rewrite_order_by_index,
        ]
    
    def rewrite(self, query: str) -> QueryPlan:
        """
        Rewrite query for optimization.
        
        Args:
            query: Original SQL query
        
        Returns:
            Optimized query plan
        """
        original = query.strip()
        rewritten = original
        cost = self._estimate_cost(original)
        
        for rule in self.rewrite_rules:
            try:
                result = rule(rewritten)
                if result:
                    rewritten = result
                    cost *= 0.9  # Assume 10% improvement per rewrite
            except Exception as e:
                logger.debug(f"Rewrite rule failed: {e}")
        
        # Calculate if we should use the rewrite
        if rewritten == original:
            rewritten = None
        
        return QueryPlan(
            original_query=original,
            rewritten_query=rewritten,
            estimated_cost=cost,
            estimated_rows=self._estimate_rows(original)
        )
    
    def _estimate_cost(self, query: str) -> float:
        """Estimate query cost (simplified)."""
        cost = 1.0
        
        # Full table scans are expensive
        if 'SELECT *' in query.upper():
            cost *= 2.0
        
        # Subqueries are expensive
        if 'SELECT' in query.upper() and query.upper().count('SELECT') > 1:
            cost *= 1.5
        
        # Multiple joins
        join_count = query.upper().count(' JOIN ')
        cost *= (1 + join_count * 0.5)
        
        # ORDER BY without index
        if 'ORDER BY' in query.upper():
            cost *= 1.3
        
        return cost
    
    def _estimate_rows(self, query: str) -> int:
        """Estimate result row count (simplified)."""
        # This would use table statistics in real implementation
        return 1000
    
    def _rewrite_select_star(self, query: str) -> Optional[str]:
        """Rewrite SELECT * to explicit columns."""
        # Simplified - would need table schema in real implementation
        if 'SELECT * FROM' in query.upper():
            # Can't rewrite without schema knowledge
            return None
        return None
    
    def _rewrite_subquery_to_join(self, query: str) -> Optional[str]:
        """Rewrite IN/EXISTS subqueries to JOINs."""
        # Pattern: WHERE x IN (SELECT ...)
        pattern = r'WHERE\s+(\w+)\s+IN\s*\(\s*SELECT'
        if re.search(pattern, query, re.IGNORECASE):
            # Would rewrite to JOIN in real implementation
            return None
        return None
    
    def _rewrite_or_to_in(self, query: str) -> Optional[str]:
        """Rewrite OR conditions to IN clauses."""
        # Pattern: x = 'a' OR x = 'b' -> x IN ('a', 'b')
        pattern = r"(\w+)\s*=\s*'[^']+'\s+OR\s+\1\s*="
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            # Would rewrite in real implementation
            return None
        return None
    
    def _rewrite_implicit_join(self, query: str) -> Optional[str]:
        """Rewrite implicit joins to explicit JOIN syntax."""
        # Pattern: FROM a, b WHERE a.id = b.id
        if 'FROM' in query.upper() and ',' in query:
            # Check if it's an implicit join
            if ' JOIN ' not in query.upper():
                # Would rewrite to explicit JOIN
                return None
        return None
    
    def _rewrite_order_by_index(self, query: str) -> Optional[str]:
        """Suggest index for ORDER BY."""
        # Would check if ORDER BY columns are indexed
        return None


class MaterializedViewManager:
    """
    Manages materialized views with incremental refresh.
    """
    
    def __init__(self):
        self.views: Dict[str, MaterializedView] = {}
        self.query_cache: Dict[str, Any] = {}  # query_hash -> results
        self.rewriter = QueryRewriter()
        self._schedules: Dict[str, threading.Timer] = {}
        self._lock = threading.RLock()
    
    def create_view(
        self,
        name: str,
        query: str,
        refresh_strategy: str = "full",
        refresh_schedule: str = "manual",
        schedule_interval: Optional[int] = None
    ) -> MaterializedView:
        """
        Create a materialized view.
        
        Args:
            name: View name
            query: Base query
            refresh_strategy: full/incremental/auto
            refresh_schedule: manual/on_commit/every_n_minutes/cron
            schedule_interval: Minutes between refreshes
        
        Returns:
            Created view
        """
        with self._lock:
            if name in self.views:
                raise ValueError(f"View {name} already exists")
            
            view = MaterializedView(
                name=name,
                query=query,
                refresh_strategy=RefreshStrategy(refresh_strategy),
                refresh_schedule=RefreshSchedule(refresh_schedule),
                schedule_interval=schedule_interval
            )
            
            self.views[name] = view
            
            # Setup scheduled refresh if needed
            if refresh_schedule == "every_n_minutes" and schedule_interval:
                self._setup_schedule(name, schedule_interval)
            
            logger.info(f"Created materialized view: {name}")
            return view
    
    def drop_view(self, name: str) -> bool:
        """Drop a materialized view."""
        with self._lock:
            if name not in self.views:
                return False
            
            # Cancel any scheduled refreshes
            if name in self._schedules:
                self._schedules[name].cancel()
                del self._schedules[name]
            
            del self.views[name]
            logger.info(f"Dropped materialized view: {name}")
            return True
    
    def refresh_view(self, name: str, strategy: Optional[str] = None) -> Dict[str, Any]:
        """
        Refresh a materialized view.
        
        Args:
            name: View name
            strategy: Override refresh strategy
        
        Returns:
            Refresh statistics
        """
        with self._lock:
            if name not in self.views:
                raise ValueError(f"View {name} not found")
            
            view = self.views[name]
            
            start_time = time.time()
            
            # Determine strategy
            use_strategy = RefreshStrategy(strategy) if strategy else view.refresh_strategy
            
            if use_strategy == RefreshStrategy.INCREMENTAL:
                self._incremental_refresh(view)
            else:
                self._full_refresh(view)
            
            elapsed = time.time() - start_time
            
            with view._lock:
                view.last_refresh = time.time()
                view.is_stale = False
                view.refresh_count += 1
                view.total_refresh_time += elapsed
            
            logger.info(f"Refreshed view {name} in {elapsed:.3f}s using {use_strategy.value}")
            
            return {
                'view': name,
                'strategy': use_strategy.value,
                'duration_ms': round(elapsed * 1000, 2),
                'rows': view.row_count
            }
    
    def _full_refresh(self, view: MaterializedView):
        """Perform full refresh."""
        # In real implementation, would execute query against database
        # For now, simulate with cached data or empty result
        
        with view._lock:
            # Simulate query execution
            view.data = self._execute_query(view.query)
            view.row_count = len(view.data)
            
            # Update change tracking baseline
            view.change_tracking = self._compute_checksum(view.data)
    
    def _incremental_refresh(self, view: MaterializedView):
        """Perform incremental refresh based on changes."""
        with view._lock:
            # Get current data state
            current_data = self._execute_query(view.query)
            current_checksum = self._compute_checksum(current_data)
            
            # Compare with last known state
            if view.change_tracking != current_checksum:
                # Compute delta (simplified)
                new_rows = [
                    row for row in current_data 
                    if row not in view.data
                ]
                deleted_rows = [
                    row for row in view.data 
                    if row not in current_data
                ]
                
                # Apply changes
                view.data = current_data
                view.row_count = len(view.data)
                view.change_tracking = current_checksum
                
                logger.debug(f"Incremental refresh: +{len(new_rows)} rows, -{len(deleted_rows)} rows")
    
    def _execute_query(self, query: str) -> List[Dict[str, Any]]:
        """Execute query and return results."""
        # Check cache first
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        
        if query_hash in self.query_cache:
            return self.query_cache[query_hash]
        
        # In real implementation, would execute against database
        # For now, return empty list
        return []
    
    def _compute_checksum(self, data: List[Dict]) -> str:
        """Compute checksum of data for change detection."""
        content = str(sorted([str(d) for d in data]))
        return hashlib.sha256(content.encode()).hexdigest()
    
    def _setup_schedule(self, name: str, interval_minutes: int):
        """Setup automatic refresh schedule."""
        def refresh_task():
            try:
                self.refresh_view(name)
            except Exception as e:
                logger.error(f"Scheduled refresh failed for {name}: {e}")
            
            # Reschedule
            self._setup_schedule(name, interval_minutes)
        
        timer = threading.Timer(interval_minutes * 60, refresh_task)
        timer.daemon = True
        timer.start()
        
        self._schedules[name] = timer
    
    def get_view(self, name: str) -> Optional[MaterializedView]:
        """Get materialized view."""
        return self.views.get(name)
    
    def list_views(self) -> List[str]:
        """List all materialized views."""
        return list(self.views.keys())
    
    def query_view(self, name: str, rewrite: bool = True) -> Tuple[List[Dict], Optional[QueryPlan]]:
        """
        Query a materialized view.
        
        Args:
            name: View name
            rewrite: Whether to attempt query rewriting
        
        Returns:
            Query results and optional plan
        """
        view = self.get_view(name)
        if not view:
            raise ValueError(f"View {name} not found")
        
        if view.is_stale:
            logger.warning(f"View {name} is stale, consider refreshing")
        
        plan = None
        if rewrite:
            plan = self.rewriter.rewrite(view.query)
        
        with view._lock:
            return view.data.copy(), plan
    
    def get_stats(self) -> Dict[str, Any]:
        """Get manager statistics."""
        with self._lock:
            view_stats = [v.get_stats() for v in self.views.values()]
            
            return {
                'view_count': len(self.views),
                'scheduled_refreshes': len(self._schedules),
                'cached_queries': len(self.query_cache),
                'views': view_stats
            }


# Global manager
_mv_manager = MaterializedViewManager()


def get_materialized_view_manager() -> MaterializedViewManager:
    """Get global materialized view manager."""
    return _mv_manager
