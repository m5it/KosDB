"""
Command Execution Framework for LevelDB Socket Server
"""

import os
import json
import time
import logging
from typing import Dict, Any, Optional, List

# Import full-text index manager
try:
    from fulltext_index import FulltextIndexManager
    FULLTEXT_AVAILABLE = True
except ImportError:
    FULLTEXT_AVAILABLE = False

# Import view manager
try:
    from view_manager import ViewManager
    VIEWS_AVAILABLE = True
except ImportError:
    VIEWS_AVAILABLE = False

logger = logging.getLogger(__name__)


class CommandRegistry:
    """Registry for database commands."""
    
    # Command to required privilege mapping
    COMMAND_PRIVILEGES = {
        'CREATE_DB': ['CREATE'],
        'DROP_DB': ['DROP'],
        'USE': [],
        'CREATE': ['CREATE'],
        'DROP': ['DROP'],
        'ALTER': ['ALTER'],
        'INSERT': ['INSERT'],
        'SELECT': ['SELECT'],
        'UPDATE': ['UPDATE'],
        'DELETE': ['DELETE'],
        'BACKUP': ['ADMIN'],
        'RESTORE': ['ADMIN'],
        # Import prepared statement cache
        try:
            from prepared_statement_cache import PreparedStatementCache
            PREPARED_AVAILABLE = True
        except ImportError:
            PREPARED_AVAILABLE = False
        
        # Initialize prepared statement cache
        self.prepared_cache = None
        if PREPARED_AVAILABLE:
            self.prepared_cache = PreparedStatementCache(max_size=100)
        
        # Command handlers
        self.handlers = {
            'CREATE_DB': self._create_db,
            'DROP_DB': self._drop_db,
            'USE': self._use_db,
            'CREATE': self._create_table,
            'DROP': self._drop_table,
            'INSERT': self._insert,
            'SELECT': self._select,
            'UPDATE': self._update,
            'DELETE': self._delete,
            'SHOW': self._show,
            'DESCRIBE': self._describe,
            'BACKUP': self._backup,
            'RESTORE': self._restore,
            'CREATE_USER': self._create_user,
            'DROP_USER': self._drop_user,
            'GRANT': self._grant,
            'REVOKE': self._revoke,
            'CREATE_ROLE': self._create_role,
            'DROP_ROLE': self._drop_role,
            'GRANT_ROLE': self._grant_role,
            'REVOKE_ROLE': self._revoke_role,
            'SHOW_GRANTS': self._show_grants,
            'SHOW_ROLES': self._show_roles,
            'CREATE_FULLTEXT_INDEX': self._create_fulltext_index,
            'DROP_FULLTEXT_INDEX': self._drop_fulltext_index,
            'MATCH_AGAINST': self._match_against,
            'CREATE_VIEW': self._create_view,
            'DROP_VIEW': self._drop_view,
            'SHOW_VIEWS': self._show_views,
            'EXPLAIN': self._explain,
            # Prepared statements (v3.3.0)
            'PREPARE': self._prepare,
            'EXECUTE': self._execute,
            'DEALLOCATE': self._deallocate,
            'DEALLOCATE_ALL': self._deallocate_all,
            # ALTER TABLE operations
            'ALTER_ADD_COLUMN': self._alter_add_column,
            'ALTER_DROP_COLUMN': self._alter_drop_column,
            'ALTER_MODIFY_COLUMN': self._alter_modify_column,
            'ALTER_RENAME_COLUMN': self._alter_rename_column,
            'ALTER_ADD_INDEX': self._alter_add_index,
            'ALTER_DROP_INDEX': self._alter_drop_index,
            'ALTER_ADD_FK': self._alter_add_constraint,
            'ALTER_ADD_UNIQUE': self._alter_add_constraint,
            'ALTER_ADD_CHECK': self._alter_add_constraint,
            'ALTER_DROP_CONSTRAINT': self._alter_drop_constraint,
        }
            'DESCRIBE': self._describe,
            'BACKUP': self._backup,
            'RESTORE': self._restore,
            'CREATE_USER': self._create_user,
            'DROP_USER': self._drop_user,
            'GRANT': self._grant,
            'REVOKE': self._revoke,
            'CREATE_ROLE': self._create_role,
            'DROP_ROLE': self._drop_role,
            'GRANT_ROLE': self._grant_role,
            'REVOKE_ROLE': self._revoke_role,
            'SHOW_GRANTS': self._show_grants,
            'SHOW_ROLES': self._show_roles,
            'CREATE_FULLTEXT_INDEX': self._create_fulltext_index,
            'DROP_FULLTEXT_INDEX': self._drop_fulltext_index,
            'CREATE_VIEW': self._create_view,
            'DROP_VIEW': self._drop_view,
            'SHOW_VIEWS': self._show_views,
            'EXPLAIN': self._explain,
            # ALTER TABLE operations
            'ALTER_ADD_COLUMN': self._alter_add_column,
            'ALTER_DROP_COLUMN': self._alter_drop_column,
            'ALTER_MODIFY_COLUMN': self._alter_modify_column,
            'ALTER_RENAME_COLUMN': self._alter_rename_column,
            'ALTER_ADD_INDEX': self._alter_add_index,
            'ALTER_DROP_INDEX': self._alter_drop_index,
            'ALTER_ADD_FK': self._alter_add_constraint,
            'ALTER_ADD_UNIQUE': self._alter_add_constraint,
            'ALTER_ADD_CHECK': self._alter_add_constraint,
            'ALTER_DROP_CONSTRAINT': self._alter_drop_constraint,
        }
    
    def execute(self, cmd_type: str, params: Dict[str, Any], state: Dict[str, Any]) -> str:
        """
        Execute a command with privilege checking.
        
        Args:
            cmd_type: Type of command
            params: Command parameters
            state: Current session state
        
        Returns:
            Command result as string
        """
        # Check privileges
        if not self._check_privileges(cmd_type, params, state):
            return "ERROR: Insufficient privileges"
        
        # Execute command
        handler = self.handlers.get(cmd_type)
        if handler:
            return handler(params, state)
        
        return f"ERROR: Unknown command type: {cmd_type}"
    
    def _check_privileges(self, cmd_type: str, params: Dict[str, Any], state: Dict[str, Any]) -> bool:
        """Check if user has required privileges."""
        if not self.authenticator:
            return True
        
        required_privs = self.COMMAND_PRIVILEGES.get(cmd_type, [])
        if not required_privs:
            return True
        
        token = state.get('auth_token')
        if not token:
            return False
        
        db_name = state.get('current_db', '*')
        table_name = params.get('table', '*')
        
        for priv in required_privs:
            if self.authenticator.check_privilege(token, db_name, table_name, priv):
                return True
        
        return False
    
    def _create_db(self, params, state):
        db_name = params.get('db_name')
        if not db_name:
            return "ERROR: Database name required"
        return self.db.create_database(db_name)
    
    def _drop_db(self, params, state):
        db_name = params.get('db_name')
        if not db_name:
            return "ERROR: Database name required"
        return self.db.drop_database(db_name)
    
    def _use_db(self, params, state):
        db_name = params.get('db_name')
        if not db_name:
            return "ERROR: Database name required"
        
        result = self.db.use_database(db_name)
        if not result.startswith("ERROR"):
            state['current_db'] = db_name
        return result
    
    def _create_table(self, params, state):
        if not state.get('current_db'):
            return "ERROR: No database selected. Use USE <database> first."
        
        table_name = params.get('table')
        columns = params.get('columns', [])
        
        if not table_name:
            return "ERROR: Table name required"
        if not columns:
            return "ERROR: Column definitions required"
        
        return self.db.create_table(table_name, columns)
    
    def _drop_table(self, params, state):
        if not state.get('current_db'):
            return "ERROR: No database selected"
        
        table_name = params.get('table')
        if not table_name:
            return "ERROR: Table name required"
        
        return self.db.drop_table(table_name)
    
    def _insert(self, params, state):
        if not state.get('current_db'):
            return "ERROR: No database selected"
        
        table_name = params.get('table')
        values = params.get('values', [])
        
        if not table_name:
            return "ERROR: Table name required"
        
        result = self.db.insert(table_name, values)
        return result
    
    def _select(self, params, state):
        if not state.get('current_db'):
            return "ERROR: No database selected"
        
        table_name = params.get('table')
        columns = params.get('columns', ['*'])
        where = params.get('where')
        
        if not table_name:
            return "ERROR: Table name required"
        
        # Check if table_name is actually a view
        if self.view_manager and self.view_manager.view_exists(state['current_db'], table_name):
            # Expand view and execute
            expanded_query = self.view_manager.expand_view(state['current_db'], table_name)
            if expanded_query:
                return f"View expanded: {expanded_query}"
        
        return self.db.select(table_name, columns, where)
    
    def _update(self, params, state):
        if not state.get('current_db'):
            return "ERROR: No database selected"
        
        table_name = params.get('table')
        set_clause = params.get('set')
        where = params.get('where')
        
        if not table_name or not set_clause:
            return "ERROR: UPDATE requires table and SET clause"
        
        # Parse set clause
        set_dict = {}
        for pair in set_clause.split(','):
            if '=' in pair:
                col, val = pair.split('=', 1)
                set_dict[col.strip()] = val.strip()
        
        return self.db.update(table_name, set_dict, where)
    
    def _delete(self, params, state):
        if not state.get('current_db'):
            return "ERROR: No database selected"
        
        table_name = params.get('table')
        where = params.get('where')
        
        if not table_name:
            return "ERROR: Table name required"
        
        # Parse where clause
        where_dict = None
        if where and '=' in where:
            col, val = where.split('=', 1)
            where_dict = {col.strip(): val.strip()}
        
        return self.db.delete(table_name, where_dict)
    
    def _show(self, params, state):
        target = params.get('target', '').upper()
        
        if target == 'DATABASES':
            dbs = self.db.list_databases()
            return "\n".join(dbs) if dbs else "No databases"
        elif target == 'TABLES':
            if not state.get('current_db'):
                return "ERROR: No database selected"
            tables = self.db.list_tables()
            return "\n".join(tables) if tables else "No tables"
        elif target == 'USERS':
            users = self.db.list_users()
            return "\n".join(users) if users else "No users"
        
        return f"ERROR: Unknown SHOW target: {target}"
    
    def _describe(self, params, state):
        if not state.get('current_db'):
            return "ERROR: No database selected"
        
        table_name = params.get('table')
        if not table_name:
            return "ERROR: Table name required"
        
        # Check if it's a view
        if self.view_manager and self.view_manager.view_exists(state['current_db'], table_name):
            desc = self.view_manager.describe_view(state['current_db'], table_name)
            return desc if desc else f"ERROR: View '{table_name}' does not exist"
        
        # Get table schema
        schema_key = f"_schema:{table_name}".encode()
        schema_data = self.db._db.get(schema_key)
        if not schema_data:
            return f"ERROR: Table '{table_name}' does not exist"
        
        schema = json.loads(schema_data.decode())
        columns = schema.get('columns', [])
        
        lines = [f"Table: {table_name}", "-" * 40]
        for col in columns:
            lines.append(f"  {col}")
        
        return "\n".join(lines)
    
    def _backup(self, params, state):
        return "ERROR: Backup not implemented"
    
    def _restore(self, params, state):
        return "ERROR: Restore not implemented"
    
    def _create_user(self, params, state):
        username = params.get('username')
        password = params.get('password')
        
        if not username or not password:
            return "ERROR: CREATE USER requires username and password"
        
        return self.db.create_user(username, password)
    
    def _drop_user(self, params, state):
        username = params.get('username')
        if not username:
            return "ERROR: DROP USER requires username"
        
        return self.db.delete_user(username)
    
    def _grant(self, params, state):
        username = params.get('username')
        db_name = params.get('db')
        table = params.get('table')
        privileges = params.get('privileges', [])
        
        if not all([username, db_name, table, privileges]):
            return "ERROR: GRANT syntax: GRANT privilege ON db.table TO username"
        
        return self.db.grant_privilege(username, db_name, table, privileges)
    
    def _revoke(self, params, state):
        return "ERROR: REVOKE not fully implemented"
    
    def _create_role(self, params, state):
        return "ERROR: CREATE ROLE not implemented"
    
    def _drop_role(self, params, state):
        return "ERROR: DROP ROLE not implemented"
    
    def _grant_role(self, params, state):
        return "ERROR: GRANT ROLE not implemented"
    
    def _revoke_role(self, params, state):
        return "ERROR: REVOKE ROLE not implemented"
    
    def _show_grants(self, params, state):
        return "ERROR: SHOW GRANTS not implemented"
    
    def _show_roles(self, params, state):
        return "ERROR: SHOW ROLES not implemented"
    
    def _create_fulltext_index(self, params, state):
        """Create full-text index on table column(s)."""
        if not self.ft_manager:
            return "ERROR: Full-text search not available"
        
        if not state.get('current_db'):
            return "ERROR: No database selected"
        
        table_name = params.get('table')
        columns = params.get('columns', [])
        
        if not table_name:
            return "ERROR: Table name required"
        if not columns:
            return "ERROR: Column(s) required for full-text index"
        
        column_name = columns[0]
        return self.ft_manager.create_index(table_name, column_name)
    
    def _drop_fulltext_index(self, params, state):
        """Drop full-text index from table."""
        if not self.ft_manager:
            return "ERROR: Full-text search not available"
        
        if not state.get('current_db'):
            return "ERROR: No database selected"
        
        table_name = params.get('table')
        
        if not table_name:
            return "ERROR: Table name required"
        
        return "ERROR: DROP FULLTEXT INDEX not fully implemented"
    
    def _match_against(self, params, state):
        """Execute MATCH ... AGAINST ... full-text search."""
        if not self.ft_manager:
            return "ERROR: Full-text search not available"
        
        if not state.get('current_db'):
            return "ERROR: No database selected"
        
        table_name = params.get('table')
        columns = params.get('columns', [])
        query = params.get('query')
        mode = params.get('mode', 'NATURAL')
        
        if not table_name:
            return "ERROR: Full-text search requires table context"
        
        results = self.ft_manager.search(table_name, columns, query, mode)
        
        if not results:
            return "Empty set"
        
        lines = []
        lines.append("| doc_id | relevance |")
        lines.append("+--------+-----------+")
        
        for doc_id, score in results[:50]:
            lines.append(f"| {str(doc_id)[:6].ljust(6)} | {score:.4f}    |")
        
        lines.append(f"{len(results)} row(s) in set")
        
        return "\n".join(lines)
    
    def _create_view(self, params, state):
        """Create a database view."""
        if not self.view_manager:
            return "ERROR: View support not available"
        
        if not state.get('current_db'):
            return "ERROR: No database selected"
        
        view_name = params.get('view_name')
        query = params.get('query')
        
        if not view_name:
            return "ERROR: View name required"
        if not query:
            return "ERROR: View definition (SELECT query) required"
        
        return self.view_manager.create_view(state['current_db'], view_name, query)
    
    def _drop_view(self, params, state):
        """Drop a database view."""
        if not self.view_manager:
            return "ERROR: View support not available"
        
        if not state.get('current_db'):
            return "ERROR: No database selected"
        
        view_name = params.get('view_name')
        
        if not view_name:
            return "ERROR: View name required"
        
        return self.view_manager.drop_view(state['current_db'], view_name)
    
    def _show_views(self, params, state):
        """Show all views in current database."""
        if not self.view_manager:
            return "ERROR: View support not available"
        
        if not state.get('current_db'):
            return "ERROR: No database selected"
        
        views = self.view_manager.list_views(state['current_db'])
        
        if not views:
            return "No views in database"
        
        lines = ["Views:", "-" * 20]
        for view in views:
            lines.append(f"  {view}")
        
        return "\n".join(lines)
    
    def _explain(self, params, state):
        """Explain query execution plan or cache status."""
        target = params.get('target', '').strip().upper()
        
        if target == 'CACHE':
            # Import here to avoid circular import
            try:
                from query_optimizer import QueryOptimizer
                optimizer = QueryOptimizer()
                return optimizer.explain_cache()
            except ImportError:
                return "ERROR: Query optimizer not available"
        else:
            # Explain query execution plan
            query = params.get('target', '')
            if not query:
                return "ERROR: EXPLAIN requires a query or CACHE keyword"
            
            try:
                from query_optimizer import QueryOptimizer, Statistics
                optimizer = QueryOptimizer()
                
                # Add basic statistics if available
                if state.get('current_db'):
                    # Could load real statistics here
                    pass
                
                plan = optimizer.optimize(query)
                return plan.explain()
            except Exception as e:
                return f"ERROR: Failed to explain query: {e}"
    
    # ALTER TABLE command handlers
    def _alter_add_column(self, params, state):
        """Handle ALTER TABLE ADD COLUMN."""
        if not self.db:
            return "ERROR: Database not initialized"
        
        if not state.get('current_db'):
            return "ERROR: No database selected"
        
        table = params.get('table')
        column = params.get('column')
        
        if not table or not column:
            return "ERROR: Table and column definition required"
        
        return self.db.alter_add_column(table, column)
    
    def _alter_drop_column(self, params, state):
        """Handle ALTER TABLE DROP COLUMN."""
        if not self.db:
            return "ERROR: Database not initialized"
        
        if not state.get('current_db'):
            return "ERROR: No database selected"
        
        table = params.get('table')
        column = params.get('column')
        cascade = params.get('cascade', False)
        
        if not table or not column:
            return "ERROR: Table and column name required"
        return self.db.alter_drop_constraint(table, constraint_name)
    
    # Prepared Statement Handlers (v3.3.0)
    def _prepare(self, params, state):
        """Prepare a statement for later execution."""
        if not self.prepared_cache:
            return "ERROR: Prepared statement support not available"
        
        name = params.get('name')
        sql = params.get('sql')
        
        if not name or not sql:
            return "ERROR: PREPARE requires statement name and SQL"
        
        try:
            self.prepared_cache.prepare(name, sql)
            return f"Statement '{name}' prepared successfully"
        except ValueError as e:
            return f"ERROR: {e}"
        except Exception as e:
            return f"ERROR: Failed to prepare statement: {e}"
    
    def _execute(self, params, state):
        """Execute a prepared statement with parameters."""
        if not self.prepared_cache:
            return "ERROR: Prepared statement support not available"
        
        name = params.get('name')
        parameters = params.get('parameters')
        
        if not name:
            return "ERROR: EXECUTE requires statement name"
        
        try:
            # Get bound SQL
            sql = self.prepared_cache.execute(name, parameters)
            
            # Now execute the SQL
            # This requires parsing and executing the resulting SQL
            from parser import CommandParser
            parser = CommandParser()
            cmd_type, exec_params = parser.parse(sql)
            
            # Execute the parsed command
            return self.execute(cmd_type, exec_params, state)
            
        except ValueError as e:
            return f"ERROR: {e}"
        except Exception as e:
            return f"ERROR: Failed to execute statement: {e}"
    
    def _deallocate(self, params, state):
        """Deallocate a prepared statement."""
        if not self.prepared_cache:
            return "ERROR: Prepared statement support not available"
        
        name = params.get('name')
        
        if not name:
            return "ERROR: DEALLOCATE requires statement name"
        
        success = self.prepared_cache.deallocate(name)
        if success:
            return f"Statement '{name}' deallocated"
        else:
            return f"ERROR: Statement '{name}' not found"
    
    def _deallocate_all(self, params, state):
        """Deallocate all prepared statements."""
        if not self.prepared_cache:
            return "ERROR: Prepared statement support not available"
        
        self.prepared_cache.deallocate_all()
        return "All prepared statements deallocated"
        return self.db.alter_drop_column(table, column, cascade)
    
    def _alter_modify_column(self, params, state):
        """Handle ALTER TABLE MODIFY COLUMN."""
        # Determine constraint type from params
        if 'column' in params and 'references_table' in params:
            constraint_type = 'FOREIGN_KEY'
            constraint_def = {
                'column': params.get('column'),
                'references_table': params.get('references_table'),
                'references_column': params.get('references_column')
            }
        elif 'columns' in params:
            constraint_type = 'UNIQUE'
            constraint_def = {'columns': params.get('columns', [])}
        elif 'expression' in params:
            constraint_type = 'CHECK'
            constraint_def = {'expression': params.get('expression', '')}
        else:
            return "ERROR: Unknown constraint type"
        return self.db.alter_rename_column(table, old_name, new_name)
    
    def _alter_add_index(self, params, state):
        """Handle ALTER TABLE ADD INDEX."""
        if not self.db:
            return "ERROR: Database not initialized"
        
        if not state.get('current_db'):
            return "ERROR: No database selected"
        
        table = params.get('table')
        columns = params.get('columns', [])
        
        if not table or not columns:
            return "ERROR: Table and columns required"
        
        return self.db.alter_add_index(table, columns)
    
    def _alter_drop_index(self, params, state):
        """Handle ALTER TABLE DROP INDEX."""
        if not self.db:
            return "ERROR: Database not initialized"
        
        if not state.get('current_db'):
            return "ERROR: No database selected"
        
        table = params.get('table')
        index_name = params.get('index_name')
        
        if not table or not index_name:
            return "ERROR: Table and index name required"
        
        return self.db.alter_drop_index(table, index_name)
    
    def _alter_add_constraint(self, params, state):
        """Handle ALTER TABLE ADD CONSTRAINT."""
        if not self.db:
            return "ERROR: Database not initialized"
        
        if not state.get('current_db'):
            return "ERROR: No database selected"
        
        # Determine constraint type from params
        if 'column' in params and 'references_table' in params:
            constraint_type = 'FOREIGN_KEY'
            constraint_def = {
                'column': params.get('column'),\n                'references_table': params.get('references_table'),\n                'references_column': params.get('references_column')\n            }\n        elif 'columns' in params:\n            constraint_type = 'UNIQUE'\n            constraint_def = {'columns': params.get('columns', [])}\n        elif 'expression' in params:\n            constraint_type = 'CHECK'\n            constraint_def = {'expression': params.get('expression', '')}\n        else:\n            return "ERROR: Unknown constraint type"
        
        table = params.get('table')
        if not table:
            return "ERROR: Table name required"
        
        return self.db.alter_add_constraint(table, constraint_type, constraint_def)
    
    def _alter_drop_constraint(self, params, state):
        """Handle ALTER TABLE DROP CONSTRAINT."""
        if not self.db:
            return "ERROR: Database not initialized"
        
        if not state.get('current_db'):
            return "ERROR: No database selected"
        
        table = params.get('table')
        constraint_name = params.get('constraint_name')
        
        if not table or not constraint_name:
            return "ERROR: Table and constraint name required"
        
        return self.db.alter_drop_constraint(table, constraint_name)
