"""
Command handlers for prepared statements.

Integrates prepared statement functionality with the command system.
"""

import logging
from typing import Dict, Any, Optional
from prepared_statements import (
    PreparedStatementManager,
    get_session_manager,
    ParameterError
)
from query_plan_cache import get_query_plan_cache

logger = logging.getLogger(__name__)


class PrepareCommand:
    """PREPARE - Create a prepared statement."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, statement_name: str, sql: str, session_id: str) -> Dict[str, Any]:
        """
        Prepare a SQL statement.
        
        Args:
            statement_name: Name for the prepared statement
            sql: SQL statement with parameters
            session_id: Current session ID
        
        Returns:
            Success response with statement details
        """
        try:
            manager = get_session_manager(session_id)
            stmt_id = manager.prepare(sql)
            
            stmt = manager.get_statement(stmt_id)
            
            return {
                'status': 'success',
                'message': f'Prepared statement "{statement_name}" created',
                'statement_id': stmt_id,
                'parameters': stmt.parameter_names if stmt.parameter_names else stmt.parameter_positions,
                'parameter_count': len(stmt.parameter_names) or len(stmt.parameter_positions)
            }
            
        except ValueError as e:
            return {
                'status': 'error',
                'message': str(e)
            }


class ExecuteCommand:
    """EXECUTE - Execute a prepared statement."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, statement_name: str, parameters: Optional[Dict[str, Any]] = None, 
                session_id: str = None, use_cache: bool = True) -> Dict[str, Any]:
        """
        Execute a prepared statement with bound parameters.
        
        Args:
            statement_name: Name of prepared statement
            parameters: Parameter values
            session_id: Current session ID
            use_cache: Whether to use query plan cache
        
        Returns:
            Query results
        """
        try:
            manager = get_session_manager(session_id)
            
            # Find statement by name (we store mapping separately)
            stmt = self._find_statement(manager, statement_name)
            if not stmt:
                return {
                    'status': 'error',
                    'message': f'Prepared statement "{statement_name}" not found'
                }
            
            # Bind parameters
            final_sql, bound_params = manager.execute(stmt.statement_id, parameters)
            
            # Check query plan cache
            if use_cache:
                cache = get_query_plan_cache()
                cached = cache.get(final_sql)
                if cached:
                    # Use cached plan
                    logger.debug(f"Using cached plan for: {final_sql[:50]}...")
                    # Execute with cached plan
                    return self._execute_with_plan(cached.parsed_plan, bound_params)
            
            # Parse and execute
            # This would integrate with existing parser/command system
            from parser import SQLParser
            parser = SQLParser()
            parsed = parser.parse(final_sql)
            
            # Cache the plan
            if use_cache:
                tables = self._extract_table_dependencies(parsed)
                cache.put(final_sql, parsed, tables)
            
            # Execute
            return self._execute_with_plan(parsed, bound_params)
            
        except ParameterError as e:
            return {
                'status': 'error',
                'message': f'Parameter error: {str(e)}'
            }
        except Exception as e:
            logger.exception("Execute failed")
            return {
                'status': 'error',
                'message': f'Execution failed: {str(e)}'
            }
    
    def _find_statement(self, manager: PreparedStatementManager, name: str) -> Optional[Any]:
        """Find prepared statement by name."""
        # In a real implementation, we'd maintain a name->id mapping
        # For now, iterate through statements
        for stmt in manager.list_statements():
            # Simple matching - in production, use proper mapping
            if name in stmt['sql'][:50]:
                return manager.get_statement(stmt['id'])
        return None
    
    def _extract_table_dependencies(self, parsed: Any) -> list:
        """Extract table names from parsed query."""
        tables = []
        if hasattr(parsed, 'get'):
            if 'table' in parsed:
                tables.append(parsed['table'])
            elif 'tables' in parsed:
                tables.extend(parsed['tables'])
        return tables
    
    def _execute_with_plan(self, plan: Any, params: list) -> Dict[str, Any]:
        """Execute using parsed plan."""
        # This would integrate with existing command execution
        # For now, return a placeholder
        return {
            'status': 'success',
            'message': 'Executed prepared statement',
            'rows_affected': 0,
            'plan_type': type(plan).__name__,
            'parameters': params
        }


class DeallocateCommand:
    """DEALLOCATE - Remove a prepared statement."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, statement_name: str, session_id: str) -> Dict[str, Any]:
        """
        Deallocate a prepared statement.
        
        Args:
            statement_name: Name of prepared statement to remove
            session_id: Current session ID
        
        Returns:
            Success/error response
        """
        manager = get_session_manager(session_id)
        
        # Find and deallocate
        for stmt_info in manager.list_statements():
            if statement_name in stmt_info['sql'][:50]:
                success = manager.deallocate(stmt_info['id'])
                if success:
                    return {
                        'status': 'success',
                        'message': f'Prepared statement "{statement_name}" deallocated'
                    }
        
        return {
            'status': 'error',
            'message': f'Prepared statement "{statement_name}" not found'
        }


class DeallocateAllCommand:
    """DEALLOCATE ALL - Remove all prepared statements."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, session_id: str) -> Dict[str, Any]:
        """
        Deallocate all prepared statements for session.
        
        Args:
            session_id: Current session ID
        
        Returns:
            Success response
        """
        manager = get_session_manager(session_id)
        count = len(manager.list_statements())
        manager.deallocate_all()
        
        return {
            'status': 'success',
            'message': f'Deallocated {count} prepared statement(s)'
        }


class ListPreparedCommand:
    """SHOW PREPARED - List all prepared statements."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, session_id: str) -> Dict[str, Any]:
        """
        List all prepared statements for session.
        
        Args:
            session_id: Current session ID
        
        Returns:
            List of prepared statements
        """
        manager = get_session_manager(session_id)
        statements = manager.list_statements()
        
        return {
            'status': 'success',
            'statements': statements,
            'count': len(statements)
        }


class CacheStatsCommand:
    """SHOW CACHE STATS - Display query plan cache statistics."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self) -> Dict[str, Any]:
        """
        Get query plan cache statistics.
        
        Returns:
            Cache statistics
        """
        cache = get_query_plan_cache()
        stats = cache.get_stats()
        
        return {
            'status': 'success',
            'cache_stats': stats
        }


class CacheInvalidateCommand:
    """CACHE INVALIDATE - Manually invalidate cache entries."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
        self.admin_required = True
    
    def execute(self, table_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Invalidate cache entries.
        
        Args:
            table_name: Specific table to invalidate, or None for all
        
        Returns:
            Success response
        """
        cache = get_query_plan_cache()
        
        if table_name:
            cache.invalidate_table(table_name)
            return {
                'status': 'success',
                'message': f'Cache invalidated for table: {table_name}'
            }
        else:
            cache.invalidate_all()
            return {
                'status': 'success',
                'message': 'All cache entries invalidated'
            }
