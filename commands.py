"""
Command Execution Framework for LevelDB Socket Server
"""

import os
import json
import time
import threading
import logging
from typing import Dict, Any, Optional, List

# Import audit logger for AUDIT LOG command
try:
    from audit_logger import AuditLogger
    AUDIT_AVAILABLE = True
except ImportError:
    AUDIT_AVAILABLE = False

# Import backup utilities
try:
    from backup_utils import (
        BackupManager, CompressionType,
        create_backup, restore_backup,
        verify_backup_integrity
    )
    BACKUP_UTILS_AVAILABLE = True
except ImportError:
    BACKUP_UTILS_AVAILABLE = False

logger = logging.getLogger(__name__)
    
    def __init__(self, db, authenticator=None, replication_client=None):
        self.db = db
        self.authenticator = authenticator
        self.replication_client = replication_client
        self.commands = {
            'CREATE_DB': self._create_db,
            'DROP_DB': self._drop_db,
            'USE': self._use_db,
            'CREATE': self._create_table,
            'DROP': self._drop_table,
            'ALTER': self._alter_table,
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
            'AUDIT_LOG': self._audit_log,
        }
    
    def execute(self, cmd_type: str, params: Dict[str, Any], 
                client_state: Dict[str, Any]) -> str:
        """Execute a command with permission checking."""
        if cmd_type not in self.commands:
            return f"ERROR: Unknown command: {cmd_type}"
        
        # Check permissions if authenticator available
        if self.authenticator and 'session_token' in client_state:
            token = client_state['session_token']
            if not self._check_permission(cmd_type, params, client_state, token):
                return "ERROR: Permission denied"
        
        return self.commands[cmd_type](params, client_state)
    
    def _check_permission(self, cmd_type: str, params: Dict[str, Any],
                         client_state: Dict[str, Any], token: str) -> bool:
        """Check if user has required permission for command."""
        # Get required privileges
        required_privs = self.COMMAND_PRIVILEGES.get(cmd_type, [])
        
        # No privilege required
        if not required_privs:
            return True
        
        # Get database and table context
        db_name = client_state.get('current_db', '')
        table_name = params.get('table', '*')
        
        # Check if user has any of the required privileges
        for priv in required_privs:
            if self.authenticator.check_privilege(token, db_name, table_name, priv):
                return True
        
        # Check column-level for UPDATE/SELECT if column specified
        if cmd_type in ('UPDATE', 'SELECT') and 'column' in params:
            column = params.get('column')
            for priv in required_privs:
                if self.authenticator.check_privilege(token, db_name, table_name, priv, column):
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
        if result.startswith("OK"):
            state['current_db'] = db_name
        return result
    
    def _create_table(self, params, state):
        if not state['current_db']:
            return "ERROR: No database selected. Use USE <database> first."
        
        table_name = params.get('table')
        columns = params.get('columns', [])
        
        if not table_name:
            return "ERROR: Table name required"
        if not columns:
            return "ERROR: Column definitions required"
        
        return self.db.create_table(state['current_db'], table_name, columns)
    
    def _drop_table(self, params, state):
        if not state['current_db']:
            return "ERROR: No database selected"
        
        table_name = params.get('table')
        if not table_name:
            return "ERROR: Table name required"
        
        return self.db.drop_table(state['current_db'], table_name)
    
    def _alter_table(self, params, state):
        if not state['current_db']:
            return "ERROR: No database selected"
        
        table_name = params.get('table')
        alter_spec = params.get('alter_spec')
        
        if not table_name or not alter_spec:
            return "ERROR: ALTER TABLE requires table and specification"
        
        return self.db.alter_table(state['current_db'], table_name, alter_spec)
    
    def _insert(self, params, state):
        if not state['current_db']:
            return "ERROR: No database selected"
        
        table_name = params.get('table')
        values = params.get('values', [])
        
        if not table_name:
            return "ERROR: Table name required"
        if not values:
            return "ERROR: Values required"
        
        result = self.db.insert(state['current_db'], table_name, values)
        
        # Replicate if configured
        if self.replication_client and result.startswith("OK"):
            try:
                self.replication_client.replicate_command(
                    f"INSERT INTO {table_name} VALUES {values}"
                )
            except Exception as e:
                logger.error(f"Replication failed: {e}")
        
        return result
    
    def _select(self, params, state):
        if not state['current_db']:
            return "ERROR: No database selected"
        
        table_name = params.get('table')
        columns = params.get('columns', ['*'])
        where = params.get('where')
        
        if not table_name:
            return "ERROR: Table name required"
        
        return self.db.select(state['current_db'], table_name, columns, where)
    
    def _update(self, params, state):
        if not state['current_db']:
            return "ERROR: No database selected"
        
        table_name = params.get('table')
        set_clause = params.get('set')
        where = params.get('where')
        
        if not table_name or not set_clause:
            return "ERROR: UPDATE requires table and SET clause"
        
        result = self.db.update(state['current_db'], table_name, set_clause, where)
        
        if self.replication_client and result.startswith("OK"):
            try:
                where_clause = f" WHERE {where}" if where else ""
                self.replication_client.replicate_command(
                    f"UPDATE {table_name} SET {set_clause}{where_clause}"
                )
            except Exception as e:
                logger.error(f"Replication failed: {e}")
        
        return result
    
    def _delete(self, params, state):
        if not state['current_db']:
            return "ERROR: No database selected"
        
    def _backup(self, params, state):
        db_name = params.get('db_name') or state.get('current_db')
        backup_path = params.get('backup_path')
        
        # Parse encryption and compression options
        passphrase = params.get('encryption')
        compression = params.get('compression', 'gzip')
        compression_level = params.get('compression_level', 6)
        
        if not db_name:
            return "ERROR: No database specified"
        
        if not BACKUP_UTILS_AVAILABLE:
            # Fallback to basic backup
            return self.db.backup_database(db_name, backup_path)
        
        try:
            # Get all tables data
            tables_data = {}
            tables = self.db._list_tables(db_name)
            
            for table_name in tables:
                table_info = self.db._get_table(db_name, table_name)
                if table_info:
                    tables_data[table_name] = {
                        'schema': table_info.get('schema', []),
                        'rows': table_info.get('rows', [])
                    }
            
            # Create backup with encryption and compression
            comp_type = CompressionType(compression) if compression else CompressionType.GZIP
            
            backup_data = create_backup(
                db_name=db_name,
                tables_data=tables_data,
                compression=comp_type,
                compression_level=compression_level,
                passphrase=passphrase
            )
            
            # Determine backup path
            if not backup_path:
                timestamp = time.strftime('%Y%m%d_%H%M%S')
                ext = '.enc' if passphrase else '.json.gz'
                backup_path = f"./backups/{db_name}_{timestamp}{ext}"
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(backup_path) or '.', exist_ok=True)
            
            # Write backup file
            with open(backup_path, 'wb') as f:
                f.write(backup_data)
            
            # Verify integrity
            valid, error = verify_backup_integrity(backup_path, passphrase)
            if not valid:
                return f"ERROR: Backup integrity check failed: {error}"
            
            return f"OK: Backup created at {backup_path} ({len(backup_data)} bytes)"
            
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            return f"ERROR: Backup failed: {e}"
    
    def _restore(self, params, state):
        db_name = params.get('db_name')
        backup_path = params.get('backup_path')
        passphrase = params.get('encryption')
        
        if not db_name:
            return "ERROR: RESTORE requires database name"
        
        if not backup_path:
            return "ERROR: RESTORE requires backup path"
        
        if not BACKUP_UTILS_AVAILABLE:
            # Fallback to basic restore
            return self.db.restore_database(db_name, backup_path)
        
        try:
            # Verify integrity first
            valid, error = verify_backup_integrity(backup_path, passphrase)
            if not valid:
                return f"ERROR: Backup integrity check failed: {error}"
            
            # Restore backup
            backup_data = restore_backup(backup_path, passphrase)
            
            # Restore tables
            tables = backup_data.get('tables', {})
            restored_count = 0
            
            for table_name, table_info in tables.items():
                # Create table if not exists
                self.db.create_table(db_name, table_name, table_info.get('schema', []))
                
                # Insert rows
                for row in table_info.get('rows', []):
                    self.db.insert(db_name, table_name, row)
                
                restored_count += 1
            
            return f"OK: Restored {restored_count} tables from {backup_path}"
            
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            return f"ERROR: Restore failed: {e}"
            return "ERROR: Table name required"
        
        return self.db.describe_table(state['current_db'], table_name)
    
    def _backup(self, params, state):
        db_name = params.get('db_name') or state.get('current_db')
        backup_path = params.get('backup_path')
        
        if not db_name:
            return "ERROR: No database specified"
        
        return self.db.backup_database(db_name, backup_path)
    
    def _restore(self, params, state):
        db_name = params.get('db_name')
        backup_path = params.get('backup_path')
        
        if not db_name or not backup_path:
            return "ERROR: RESTORE requires database name and backup path"
        
        return self.db.restore_database(db_name, backup_path)
    
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
        
        return self.db.drop_user(username)
    
    def _grant(self, params, state):
        username = params.get('username')
        db_name = params.get('db')
        table = params.get('table')
        privileges = params.get('privileges', [])
        
        if not all([username, db_name, table, privileges]):
            return "ERROR: GRANT syntax: GRANT privilege ON db.table TO username"
        
        return self.db.grant_privilege(username, db_name, table, privileges)
    
    def _revoke(self, params, state):
        username = params.get('username')
        db_name = params.get('db')
        table = params.get('table')
        privileges = params.get('privileges', [])
        
        if not all([username, db_name, table, privileges]):
            return "ERROR: REVOKE syntax: REVOKE privilege ON db.table FROM username"
        
        return self.db.revoke_privilege(username, db_name, table, privileges)
    
    def _create_role(self, params, state):
        if not self.authenticator:
            return "ERROR: Role management not available"
        
        role_name = params.get('role_name')
        description = params.get('description', '')
        
        if not role_name:
            return "ERROR: CREATE ROLE requires role name"
        
        return self.authenticator.create_role(role_name, description)
    
    def _drop_role(self, params, state):
        if not self.authenticator:
            return "ERROR: Role management not available"
        
        role_name = params.get('role_name')
        if not role_name:
            return "ERROR: DROP ROLE requires role name"
        
        return self.authenticator.drop_role(role_name)
    
    def _grant_role(self, params, state):
        if not self.authenticator:
            return "ERROR: Role management not available"
        
        username = params.get('username')
        role_name = params.get('role_name')
        
        if not username or not role_name:
            return "ERROR: GRANT ROLE syntax: GRANT ROLE rolename TO username"
        
        return self.authenticator.grant_role_to_user(username, role_name)
    
    def _revoke_role(self, params, state):
        if not self.authenticator:
            return "ERROR: Role management not available"
        
        username = params.get('username')
        role_name = params.get('role_name')
        
        if not username or not role_name:
            return "ERROR: REVOKE ROLE syntax: REVOKE ROLE rolename FROM username"
        
        return self.authenticator.revoke_role_from_user(username, role_name)
    
    def _show_grants(self, params, state):
        if not self.authenticator:
            return "ERROR: Grant information not available"
        
        username = params.get('username')
        return self.authenticator.show_grants(username)
    
    def _show_roles(self, params, state):
        if not self.authenticator:
            return "ERROR: Role information not available"
        
        return self.authenticator.show_roles()
    
    def _audit_log(self, params, state):
        """Query audit log entries (admin only)."""
        if not state.get('is_admin'):
            return "ERROR: AUDIT LOG requires admin privileges"
        
        if not AUDIT_AVAILABLE:
            return "ERROR: Audit logging not available"
        
        limit = params.get('limit', 50)
        user = params.get('user')
        action = params.get('action')
        
        try:
            return f"OK: Audit log query - limit={limit}, user={user}, action={action}"
        except Exception as e:
            return f"ERROR: Failed to query audit log: {e}"
