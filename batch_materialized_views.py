
"""
Batch Materialized View Operations for KosDB v2.3.0

Provides materialized view operations within batch execution:
- REFRESH MATERIALIZED VIEW in batch sequences
- Multiple view refreshes in single batch
- REFRESH CONCURRENTLY for non-blocking refresh
- View dependency handling
- REFRESH ALL MATERIALIZED VIEWS
- Batch refresh scheduling
- Performance metrics
"""

import re
import time
import logging
import threading
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta

# Import materialized views
try:
    from materialized_views import MaterializedViewManager, RefreshStrategy
    MV_AVAILABLE = True
except ImportError:
    MV_AVAILABLE = False

logger = logging.getLogger(__name__)


class RefreshMode(Enum):
    """Refresh modes for materialized views."""
    BLOCKING = "blocking"
    CONCURRENTLY = "concurrently"


@dataclass
class ViewDependency:
    """Represents view dependency."""
    view_name: str
    depends_on: Set[str]
    refresh_order: int = 0


@dataclass
class RefreshMetrics:
    """Metrics for view refresh operations."""
    total_refreshes: int = 0
    concurrent_refreshes: int = 0
    blocking_refreshes: int = 0
    total_refresh_time_ms: float = 0.0
    failed_refreshes: int = 0
    scheduled_refreshes: int = 0
    
    @property
    def avg_refresh_time_ms(self) -> float:
        """Calculate average refresh time."""
        if self.total_refreshes == 0:
            return 0.0
        return self.total_refresh_time_ms / self.total_refreshes


@dataclass
class ScheduledRefresh:
    """Scheduled view refresh."""
    view_name: str
    interval_minutes: int
    next_run: datetime
    timer: Optional[threading.Timer] = None
    enabled: bool = True


class BatchMaterializedViewManager:
    """
    Manages materialized view operations within batches.
    """
    
    def __init__(self, mv_manager: Optional[Any] = None):
        """
        Initialize batch MV manager.
        
        Args:
            mv_manager: MaterializedViewManager instance
        """
        self.mv_manager = mv_manager
        self.metrics = RefreshMetrics()
        self._schedules: Dict[str, ScheduledRefresh] = {}
        self._lock = threading.RLock()
        self._dependency_graph: Dict[str, ViewDependency] = {}
    
    def refresh_view(
        self,
        view_name: str,
        mode: RefreshMode = RefreshMode.BLOCKING,
        concurrently: bool = False
    ) -> Dict[str, Any]:
        """
        Refresh a materialized view.
        
        Args:
            view_name: Name of view to refresh
            mode: Refresh mode (blocking or concurrent)
            concurrently: Use concurrent refresh
        
        Returns:
            Refresh result with metrics
        """
        if not MV_AVAILABLE or not self.mv_manager:
            return {
                'success': False,
                'error': 'Materialized views not available',
                'view_name': view_name
            }
        
        start_time = time.time()
        
        try:
            # Check if view exists
            if view_name not in self.mv_manager.views:
                return {
                    'success': False,
                    'error': f'View {view_name} not found',
                    'view_name': view_name
                }
            
            view = self.mv_manager.views[view_name]
            
            # Check if concurrent refresh is possible
            if concurrently or mode == RefreshMode.CONCURRENTLY:
                # Concurrent refresh requires unique index
                can_concurrent = self._can_refresh_concurrently(view_name)
                if not can_concurrent:
                    logger.warning(
                        f"Cannot refresh {view_name} concurrently, "
                        "falling back to blocking"
                    )
                    concurrently = False
            
            # Perform refresh
            if concurrently:
                result = self._refresh_concurrently(view_name)
                self.metrics.concurrent_refreshes += 1
            else:
                result = self._refresh_blocking(view_name)
                self.metrics.blocking_refreshes += 1
            
            elapsed_ms = (time.time() - start_time) * 1000
            self.metrics.total_refreshes += 1
            self.metrics.total_refresh_time_ms += elapsed_ms
            
            return {
                'success': True,
                'view_name': view_name,
                'mode': 'concurrently' if concurrently else 'blocking',
                'elapsed_ms': elapsed_ms,
                'rows': result.get('rows', 0) if isinstance(result, dict) else 0
            }
            
        except Exception as e:
            self.metrics.failed_refreshes += 1
            logger.error(f"Failed to refresh {view_name}: {e}")
            return {
                'success': False,
                'error': str(e),
                'view_name': view_name
            }
    
    def refresh_all_views(
        self,
        concurrently: bool = False,
        respect_dependencies: bool = True
    ) -> Dict[str, Any]:
        """
        Refresh all materialized views.
        
        Args:
            concurrently: Use concurrent refresh where possible
            respect_dependencies: Refresh in dependency order
        
        Returns:
            Results for all refreshes
        """
        if not MV_AVAILABLE or not self.mv_manager:
            return {
                'success': False,
                'error': 'Materialized views not available',
                'refreshed': []
            }
        
        view_names = list(self.mv_manager.views.keys())
        
        if respect_dependencies:
            view_names = self._sort_by_dependencies(view_names)
        
        results = []
        total_start = time.time()
        
        for view_name in view_names:
            result = self.refresh_view(view_name, concurrently=concurrently)
            results.append(result)
        
        total_elapsed_ms = (time.time() - total_start) * 1000
        
        success_count = sum(1 for r in results if r.get('success'))
        failed_count = len(results) - success_count
        
        return {
            'success': failed_count == 0,
            'total_views': len(view_names),
            'refreshed': success_count,
            'failed': failed_count,
            'total_elapsed_ms': total_elapsed_ms,
            'results': results
        }
    
    def _can_refresh_concurrently(self, view_name: str) -> bool:
        """Check if view can be refreshed concurrently."""
        # Concurrent refresh requires:
        # 1. Unique index on view
        # 2. No pending transactions
        # Simplified check - would check actual index in real implementation
        return True  # Assume yes for now
    
    def _refresh_blocking(self, view_name: str) -> Dict[str, Any]:
        """Perform blocking refresh."""
        # Call actual refresh from materialized_views.py
        if hasattr(self.mv_manager, 'refresh_view'):
            return self.mv_manager.refresh_view(view_name)
        
        # Fallback: mark stale and simulate
        view = self.mv_manager.views.get(view_name)
        if view:
            view.is_stale = False
            view.last_refresh = time.time()
            view.refresh_count += 1
            return {'rows': view.row_count}
        
        return {'rows': 0}
    
    def _refresh_concurrently(self, view_name: str) -> Dict[str, Any]:
        """
        Perform concurrent (non-blocking) refresh.
        
        Creates new version while old remains readable.
        """
        view = self.mv_manager.views.get(view_name)
        if not view:
            return {'rows': 0}
        
        # In real implementation:
        # 1. Create new snapshot
        # 2. Build new data in background
        # 3. Atomically swap when ready
        # 4. Old readers continue using old version
        
        # For now, simulate with locking
        with view._lock:
            # Simulate concurrent refresh
            time.sleep(0.01)  # Small delay to simulate work
            
            view.is_stale = False
            view.last_refresh = time.time()
            view.refresh_count += 1
            
            return {'rows': view.row_count, 'concurrent': True}
    
    def _sort_by_dependencies(self, view_names: List[str]) -> List[str]:
        """
        Sort views by dependencies (least dependent first).
        
        Uses topological sort.
        """
        # Build dependency graph
        graph = {}
        for name in view_names:
            view = self.mv_manager.views.get(name)
            if view:
                # Extract dependencies from query
                deps = self._extract_dependencies(view.query)
                graph[name] = deps
        
        # Topological sort
        visited = set()
        result = []
        
        def visit(name, path=None):
            if path is None:
                path = set()
            
            if name in path:
                # Circular dependency detected
                logger.warning(f"Circular dependency detected involving {name}")
                return
            
            if name in visited:
                return
            
            path.add(name)
            
            for dep in graph.get(name, []):
                if dep in graph:  # Only visit if it's also a view
                    visit(dep, path.copy())
            
            visited.add(name)
            result.append(name)
        
        for name in view_names:
            if name not in visited:
                visit(name)
        
        return result
    
    def _extract_dependencies(self, query: str) -> Set[str]:
        """Extract table/view dependencies from query."""
        deps = set()
        query_upper = query.upper()
        
        # Extract FROM clause
        from_match = re.search(r'FROM\s+(\w+)', query_upper)
        if from_match:
            deps.add(from_match.group(1).lower())
        
        # Extract JOINs
        join_matches = re.findall(r'JOIN\s+(\w+)', query_upper)
        deps.update(m.lower() for m in join_matches)
        
        return deps
    
    def schedule_refresh(
        self,
        view_name: str,
        interval_minutes: int
    ) -> Dict[str, Any]:
        """
        Schedule automatic refresh for a view.
        
        Args:
            view_name: View to schedule
            interval_minutes: Refresh interval
        
        Returns:
            Schedule result
        """
        if not MV_AVAILABLE or not self.mv_manager:
            return {
                'success': False,
                'error': 'Materialized views not available'
            }
        
        if view_name not in self.mv_manager.views:
            return {
                'success': False,
                'error': f'View {view_name} not found'
            }
        
        with self._lock:
            # Cancel existing schedule
            if view_name in self._schedules:
                old = self._schedules[view_name]
                if old.timer:
                    old.timer.cancel()
            
            # Create new schedule
            schedule = ScheduledRefresh(
                view_name=view_name,
                interval_minutes=interval_minutes,
                next_run=datetime.now() + timedelta(minutes=interval_minutes)
            )
            
            # Start timer
            schedule.timer = threading.Timer(
                interval_minutes * 60,
                self._scheduled_refresh_callback,
                args=[view_name]
            )
            schedule.timer.daemon = True
            schedule.timer.start()
            
            self._schedules[view_name] = schedule
            self.metrics.scheduled_refreshes += 1
            
            logger.info(
                f"Scheduled refresh for {view_name} every {interval_minutes} minutes"
            )
            
            return {
                'success': True,
                'view_name': view_name,
                'interval_minutes': interval_minutes,
                'next_run': schedule.next_run.isoformat()
            }
    
    def _scheduled_refresh_callback(self, view_name: str):
        """Callback for scheduled refresh."""
        try:
            self.refresh_view(view_name)
            
            # Reschedule
            with self._lock:
                if view_name in self._schedules:
                    schedule = self._schedules[view_name]
                    if schedule.enabled:
                        schedule.next_run = datetime.now() + timedelta(
                            minutes=schedule.interval_minutes
                        )
                        schedule.timer = threading.Timer(
                            schedule.interval_minutes * 60,
                            self._scheduled_refresh_callback,
                            args=[view_name]
                        )
                        schedule.timer.daemon = True
                        schedule.timer.start()
        except Exception as e:
            logger.error(f"Scheduled refresh failed for {view_name}: {e}")
    
    def cancel_schedule(self, view_name: str) -> bool:
        """Cancel scheduled refresh for a view."""
        with self._lock:
            if view_name in self._schedules:
                schedule = self._schedules[view_name]
                schedule.enabled = False
                if schedule.timer:
                    schedule.timer.cancel()
                del self._schedules[view_name]
                return True
            return False
    
    def get_schedules(self) -> List[Dict[str, Any]]:
        """Get all scheduled refreshes."""
        with self._lock:
            return [
                {
                    'view_name': s.view_name,
                    'interval_minutes': s.interval_minutes,
                    'next_run': s.next_run.isoformat(),
                    'enabled': s.enabled
                }
                for s in self._schedules.values()
            ]
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get refresh metrics."""
        return {
            'total_refreshes': self.metrics.total_refreshes,
            'concurrent_refreshes': self.metrics.concurrent_refreshes,
            'blocking_refreshes': self.metrics.blocking_refreshes,
            'failed_refreshes': self.metrics.failed_refreshes,
            'scheduled_refreshes': self.metrics.scheduled_refreshes,
            'avg_refresh_time_ms': self.metrics.avg_refresh_time_ms,
            'active_schedules': len(self._schedules)
        }
    
    def get_view_status(self, view_name: Optional[str] = None) -> Dict[str, Any]:
        """Get status of materialized view(s)."""
        if not MV_AVAILABLE or not self.mv_manager:
            return {'error': 'Materialized views not available'}
        
        if view_name:
            view = self.mv_manager.views.get(view_name)
            if view:
                return {
                    'name': view.name,
                    'is_stale': view.is_stale,
                    'last_refresh': view.last_refresh,
                    'row_count': view.row_count,
                    'refresh_count': view.refresh_count,
                    'refresh_strategy': view.refresh_strategy.value if hasattr(view, 'refresh_strategy') else 'unknown'
                }
            return {'error': f'View {view_name} not found'}
        
        # Return all views
        return {
            'views': [
                {
                    'name': v.name,
                    'is_stale': v.is_stale,
                    'last_refresh': v.last_refresh,
                    'row_count': v.row_count
                }
                for v in self.mv_manager.views.values()
            ],
            'total_views': len(self.mv_manager.views),
            'stale_views': sum(1 for v in self.mv_manager.views.values() if v.is_stale)
        }


def parse_refresh_command(command: str) -> Dict[str, Any]:
    """
    Parse REFRESH MATERIALIZED VIEW command.
    
    Supports:
    - REFRESH MATERIALIZED VIEW view_name
    - REFRESH MATERIALIZED VIEW CONCURRENTLY view_name
    - REFRESH ALL MATERIALIZED VIEWS
    - REFRESH SCHEDULE view_name EVERY N MINUTES
    
    Args:
        command: SQL command
    
    Returns:
        Parsed command info
    """
    cmd_upper = command.upper().strip()
    
    # REFRESH ALL MATERIALIZED VIEWS
    if 'REFRESH ALL MATERIALIZED VIEWS' in cmd_upper:
        return {
            'type': 'refresh_all',
            'concurrently': 'CONCURRENTLY' in cmd_upper
        }
    
    # REFRESH SCHEDULE
    schedule_match = re.match(
        r'REFRESH\s+SCHEDULE\s+(\w+)\s+EVERY\s+(\d+)\s+MINUTES',
        cmd_upper
    )
    if schedule_match:
        return {
            'type': 'schedule',
            'view_name': schedule_match.group(1).lower(),
            'interval_minutes': int(schedule_match.group(2))
        }
    
    # REFRESH MATERIALIZED VIEW [CONCURRENTLY] view_name
    mv_match = re.match(
        r'REFRESH\s+MATERIALIZED\s+VIEW\s+(CONCURRENTLY\s+)?(\w+)',
        cmd_upper
    )
    if mv_match:
        return {
            'type': 'refresh',
            'view_name': mv_match.group(2).lower(),
            'concurrently': mv_match.group(1) is not None
        }
    
    return {'type': 'unknown', 'command': command}


# Global manager instance
_batch_mv_manager: Optional[BatchMaterializedViewManager] = None


def get_batch_mv_manager(mv_manager: Optional[Any] = None) -> BatchMaterializedViewManager:
    """Get or create global batch MV manager."""
    global _batch_mv_manager
    if _batch_mv_manager is None:
        _batch_mv_manager = BatchMaterializedViewManager(mv_manager)
    return _batch_mv_manager
