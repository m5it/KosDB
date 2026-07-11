"""
Command handlers for materialized view operations.
"""

import logging
from typing import Dict, Any, Optional
from materialized_views import (
    MaterializedViewManager,
    RefreshStrategy,
    RefreshSchedule,
    get_materialized_view_manager
)

logger = logging.getLogger(__name__)


class CreateMaterializedViewCommand:
    """CREATE MATERIALIZED VIEW - Create a materialized view."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(
        self,
        name: str,
        query: str,
        refresh_strategy: str = "full",
        refresh_schedule: str = "manual",
        schedule_interval: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create a materialized view."""
        try:
            manager = get_materialized_view_manager()
            
            view = manager.create_view(
                name=name,
                query=query,
                refresh_strategy=refresh_strategy,
                refresh_schedule=refresh_schedule,
                schedule_interval=schedule_interval
            )
            
            return {
                'status': 'success',
                'message': f'Created materialized view: {name}',
                'view': {
                    'name': name,
                    'refresh_strategy': refresh_strategy,
                    'refresh_schedule': refresh_schedule
                }
            }
            
        except ValueError as e:
            return {
                'status': 'error',
                'message': str(e)
            }


class DropMaterializedViewCommand:
    """DROP MATERIALIZED VIEW - Remove a materialized view."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, name: str) -> Dict[str, Any]:
        """Drop a materialized view."""
        manager = get_materialized_view_manager()
        
        if not manager.drop_view(name):
            return {
                'status': 'error',
                'message': f'View not found: {name}'
            }
        
        return {
            'status': 'success',
            'message': f'Dropped materialized view: {name}'
        }


class RefreshMaterializedViewCommand:
    """REFRESH MATERIALIZED VIEW - Refresh view data."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, name: str, strategy: Optional[str] = None) -> Dict[str, Any]:
        """Refresh a materialized view."""
        try:
            manager = get_materialized_view_manager()
            result = manager.refresh_view(name, strategy)
            
            return {
                'status': 'success',
                'message': f'Refreshed view: {name}',
                'result': result
            }
            
        except ValueError as e:
            return {
                'status': 'error',
                'message': str(e)
            }


class RefreshAllCommand:
    """REFRESH ALL MATERIALIZED VIEWS - Refresh all views."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self) -> Dict[str, Any]:
        """Refresh all materialized views."""
        manager = get_materialized_view_manager()
        views = manager.list_views()
        
        results = []
        for name in views:
            try:
                result = manager.refresh_view(name)
                results.append({'view': name, 'status': 'success', 'result': result})
            except Exception as e:
                results.append({'view': name, 'status': 'error', 'error': str(e)})
        
        return {
            'status': 'success',
            'message': f'Refreshed {len(views)} views',
            'results': results
        }


class ListMaterializedViewsCommand:
    """LIST MATERIALIZED VIEWS - Show all views."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self) -> Dict[str, Any]:
        """List all materialized views."""
        manager = get_materialized_view_manager()
        views = manager.list_views()
        
        view_details = []
        for name in views:
            view = manager.get_view(name)
            if view:
                view_details.append(view.get_stats())
        
        return {
            'status': 'success',
            'views': view_details,
            'count': len(views)
        }


class QueryMaterializedViewCommand:
    """SELECT FROM MV - Query a materialized view."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, name: str, rewrite: bool = True) -> Dict[str, Any]:
        """Query a materialized view."""
        try:
            manager = get_materialized_view_manager()
            data, plan = manager.query_view(name, rewrite)
            
            result = {
                'status': 'success',
                'view': name,
                'row_count': len(data),
                'data': data[:100]
            }
            
            if plan:
                result['query_plan'] = plan.to_dict()
            
            return result
            
        except ValueError as e:
            return {
                'status': 'error',
                'message': str(e)
            }


class SetRefreshScheduleCommand:
    """SET REFRESH SCHEDULE - Configure automatic refresh."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(
        self,
        name: str,
        schedule: str,
        interval: Optional[int] = None
    ) -> Dict[str, Any]:
        """Set refresh schedule for a view."""
        manager = get_materialized_view_manager()
        view = manager.get_view(name)
        
        if not view:
            return {
                'status': 'error',
                'message': f'View not found: {name}'
            }
        
        try:
            view.refresh_schedule = RefreshSchedule(schedule)
            if interval:
                view.schedule_interval = interval
            
            if schedule == 'every_n_minutes' and interval:
                manager._setup_schedule(name, interval)
            
            return {
                'status': 'success',
                'message': f'Set refresh schedule for {name}',
                'schedule': schedule,
                'interval': interval
            }
            
        except ValueError as e:
            return {
                'status': 'error',
                'message': f'Invalid schedule: {e}'
            }


class MVStatsCommand:
    """MATERIALIZED VIEW STATS - Show statistics."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, name: Optional[str] = None) -> Dict[str, Any]:
        """Get materialized view statistics."""
        manager = get_materialized_view_manager()
        
        if name:
            view = manager.get_view(name)
            if not view:
                return {
                    'status': 'error',
                    'message': f'View not found: {name}'
                }
            
            return {
                'status': 'success',
                'view': view.get_stats()
            }
        else:
            stats = manager.get_stats()
            return {
                'status': 'success',
                'stats': stats
            }
