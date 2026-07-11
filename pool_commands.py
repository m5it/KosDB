"""
Command handlers for connection pool management.

Integrates connection pooling with the CLI.
"""

import logging
from typing import Dict, Any, Optional
from connection_pool import (
    ConnectionPool,
    create_pool,
    get_pool,
    shutdown_pool,
    list_pools,
    get_all_stats
)

logger = logging.getLogger(__name__)


class PoolCreateCommand:
    """POOL CREATE - Create a new connection pool."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
        self.admin_required = True
    
    def execute(
        self,
        pool_name: str,
        min_connections: int = 5,
        max_connections: int = 20,
        connection_timeout: float = 30.0,
        idle_timeout: float = 300.0
    ) -> Dict[str, Any]:
        """
        Create a new connection pool.
        
        Args:
            pool_name: Unique name for the pool
            min_connections: Minimum connections to maintain
            max_connections: Maximum connections allowed
            connection_timeout: Seconds to wait for connection
            idle_timeout: Seconds before idle connection cleanup
        
        Returns:
            Success/error response
        """
        try:
            def connection_factory():
                # Create actual database connection
                # This would integrate with existing database
                return {'type': 'database_connection', 'created': True}
            
            pool = create_pool(
                pool_name=pool_name,
                min_connections=min_connections,
                max_connections=max_connections,
                connection_timeout=connection_timeout,
                idle_timeout=idle_timeout,
                connection_factory=connection_factory
            )
            
            return {
                'status': 'success',
                'message': f'Created connection pool: {pool_name}',
                'pool': {
                    'name': pool_name,
                    'min_connections': min_connections,
                    'max_connections': max_connections,
                    'connection_timeout': connection_timeout,
                    'idle_timeout': idle_timeout
                }
            }
            
        except ValueError as e:
            return {
                'status': 'error',
                'message': str(e)
            }


class PoolStatusCommand:
    """POOL STATUS - Show pool statistics."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, pool_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get connection pool statistics.
        
        Args:
            pool_name: Specific pool name, or None for all
        
        Returns:
            Pool statistics
        """
        if pool_name:
            pool = get_pool(pool_name)
            if not pool:
                return {
                    'status': 'error',
                    'message': f'Pool not found: {pool_name}'
                }
            
            stats = pool.get_stats()
            return {
                'status': 'success',
                'pool': stats
            }
        else:
            stats = get_all_stats()
            return {
                'status': 'success',
                'pools': stats,
                'count': len(stats)
            }


class PoolListCommand:
    """POOL LIST - List all connection pools."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self) -> Dict[str, Any]:
        """
        List all connection pools.
        
        Returns:
            List of pool names
        """
        pools = list_pools()
        
        return {
            'status': 'success',
            'pools': pools,
            'count': len(pools)
        }


class PoolShutdownCommand:
    """POOL SHUTDOWN - Shutdown a connection pool."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
        self.admin_required = True
    
    def execute(self, pool_name: str, wait: bool = True) -> Dict[str, Any]:
        """
        Shutdown a connection pool.
        
        Args:
            pool_name: Pool to shutdown
            wait: Wait for connections to be returned
        
        Returns:
            Success/error response
        """
        if pool_name not in list_pools():
            return {
                'status': 'error',
                'message': f'Pool not found: {pool_name}'
            }
        
        shutdown_pool(pool_name, wait=wait)
        
        return {
            'status': 'success',
            'message': f'Pool {pool_name} shutdown complete'
        }


class PoolAcquireCommand:
    """POOL ACQUIRE - Test connection acquisition."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, pool_name: str, timeout: Optional[float] = None) -> Dict[str, Any]:
        """
        Test acquiring a connection from the pool.
        
        Args:
            pool_name: Pool name
            timeout: Override default timeout
        
        Returns:
            Success/error response with connection info
        """
        pool = get_pool(pool_name)
        if not pool:
            return {
                'status': 'error',
                'message': f'Pool not found: {pool_name}'
            }
        
        try:
            conn_id = pool.get_connection(timeout)
            
            # Return immediately for testing
            pool.return_connection(conn_id)
            
            return {
                'status': 'success',
                'message': 'Successfully acquired and released connection',
                'connection_id': conn_id
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Failed to acquire connection: {str(e)}'
            }


class ConnectionMonitor:
    """
    Real-time connection pool monitor.
    
    Tracks connection usage patterns and alerts on issues.
    """
    
    def __init__(self, check_interval: float = 5.0):
        self.check_interval = check_interval
        self.alerts: list = []
        self.thresholds = {
            'pool_utilization': 0.8,  # Alert if >80% utilized
            'connection_wait_time': 1.0,  # Alert if waiting >1s
            'health_check_failure_rate': 0.1  # Alert if >10% fail
        }
    
    def check_pool_health(self, pool_name: str) -> Dict[str, Any]:
        """
        Check health of a specific pool.
        
        Args:
            pool_name: Pool to check
        
        Returns:
            Health status with alerts
        """
        pool = get_pool(pool_name)
        if not pool:
            return {
                'status': 'error',
                'message': f'Pool not found: {pool_name}'
            }
        
        stats = pool.get_stats()
        alerts = []
        
        # Check utilization
        utilization = stats['active_connections'] / stats['max_connections']
        if utilization > self.thresholds['pool_utilization']:
            alerts.append({
                'level': 'warning',
                'message': f'High pool utilization: {utilization:.1%}',
                'metric': 'utilization',
                'value': utilization
            })
        
        # Check timeout rate
        total_requests = stats['total_borrowed'] + stats['total_timeout']
        if total_requests > 0:
            timeout_rate = stats['total_timeout'] / total_requests
            if timeout_rate > 0.05:  # 5% timeout rate
                alerts.append({
                    'level': 'error',
                    'message': f'High timeout rate: {timeout_rate:.1%}',
                    'metric': 'timeout_rate',
                    'value': timeout_rate
                })
        
        # Check health check failures
        if stats['health_check_failures'] > 10:
            alerts.append({
                'level': 'warning',
                'message': f'Health check failures: {stats["health_check_failures"]}',
                'metric': 'health_failures',
                'value': stats['health_check_failures']
            })
        
        return {
            'status': 'healthy' if not alerts else 'degraded',
            'pool_name': pool_name,
            'alerts': alerts,
            'stats': stats
        }
    
    def get_all_health(self) -> Dict[str, Any]:
        """Get health status for all pools."""
        results = {}
        for pool_name in list_pools():
            results[pool_name] = self.check_pool_health(pool_name)
        
        return {
            'status': 'success',
            'pools': results,
            'overall_health': 'healthy' if all(
                r['status'] == 'healthy' for r in results.values()
            ) else 'degraded'
        }


class PoolHealthCommand:
    """POOL HEALTH - Check pool health status."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
        self.monitor = ConnectionMonitor()
    
    def execute(self, pool_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Check pool health.
        
        Args:
            pool_name: Specific pool or all
        
        Returns:
            Health status
        """
        if pool_name:
            return self.monitor.check_pool_health(pool_name)
        else:
            return self.monitor.get_all_health()
