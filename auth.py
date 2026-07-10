"""
Enhanced Authentication module with granular permissions and role-based access control
"""

import hashlib
import secrets
import json
import threading
import time
from typing import Dict, Set, List, Optional, Tuple, Any
from functools import wraps
from database import Database


# All supported privileges
ALL_PRIVILEGES = {
    'SELECT', 'INSERT', 'UPDATE', 'DELETE',
    'CREATE', 'DROP', 'ALTER', 'INDEX',
    'ADMIN', 'REPLICATION_SLAVE', 'ALL'
}


class PermissionCache:
    """Thread-safe cache for permission lookups."""
    
    def __init__(self, ttl_seconds: int = 300):
        self._cache: Dict[str, Dict] = {}
        self._lock = threading.RLock()
        self._ttl = ttl_seconds
    
    def _make_key(self, username: str, db: str, table: str, column: Optional[str] = None) -> str:
        """Create cache key."""
        col_part = f".{column}" if column else ""
        return f"{username}:{db}:{table}{col_part}"
    
    def get(self, username: str, db: str, table: str, 
            privilege: str, column: Optional[str] = None) -> Optional[bool]:
        """Get cached permission result."""
        key = self._make_key(username, db, table, column)
        with self._lock:
            entry = self._cache.get(key)
            if entry and entry['expires'] > time.time():
                return entry['privileges'].get(privilege, False)
            return None
    
    def set(self, username: str, db: str, table: str,
            privileges: Dict[str, bool], column: Optional[str] = None):
        """Cache permission result."""
        key = self._make_key(username, db, table, column)
        with self._lock:
            self._cache[key] = {
                'privileges': privileges,
                'expires': time.time() + self._ttl
            }
    
    def invalidate_user(self, username: str):
        """Invalidate all cache entries for a user."""
        with self._lock:
            keys_to_remove = [k for k in self._cache if k.startswith(f"{username}:")]
            for key in keys_to_remove:
                del self._cache[key]
    
    def clear(self):
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()


class Role:
    """Represents a database role with assigned privileges."""
    
    def __init__(self, name: str, description: str = "", is_default: bool = False):
        self.name = name
        self.description = description
        self.is_default = is_default
        self.privileges: Dict[str, Dict[str, Set[str]]] = {}  # db -> table -> set of privs
    
    def grant_privilege(self, db: str, table: str, privileges: List[str]):
        """Grant privileges on database/table to role."""
        if db not in self.privileges:
            self.privileges[db] = {}
        if table not in self.privileges[db]:
            self.privileges[db][table] = set()
        self.privileges[db][table].update(privileges)
    
    def revoke_privilege(self, db: str, table: str, privileges: List[str]):
        """Revoke privileges from role."""
        if db in self.privileges and table in self.privileges[db]:
            self.privileges[db][table].difference_update(privileges)
            # Clean up empty entries
            if not self.privileges[db][table]:
                del self.privileges[db][table]
            if not self.privileges[db]:
                del self.privileges[db]
    
    def has_privilege(self, db: str, table: str, privilege: str) -> bool:
        """Check if role has specific privilege."""
        # Check specific table
        if db in self.privileges:
            if table in self.privileges[db]:
                if privilege in self.privileges[db][table] or 'ALL' in self.privileges[db][table]:
                    return True
            # Check wildcard table
            if '*' in self.privileges[db]:
                if privilege in self.privileges[db]['*'] or 'ALL' in self.privileges[db]['*']:
                    return True
        # Check wildcard database
        if '*' in self.privileges:
            if table in self.privileges['*']:
                if privilege in self.privileges['*'][table] or 'ALL' in self.privileges['*'][table]:
                    return True
            if '*' in self.privileges['*']:
                if privilege in self.privileges['*']['*'] or 'ALL' in self.privileges['*']['*']:
                    return True
        return False
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for storage."""
        return {
            'name': self.name,
            'description': self.description,
            'is_default': self.is_default,
            'privileges': {
                db: {
                    table: list(privs) 
                    for table, privs in tables.items()
                }
                for db, tables in self.privileges.items()
            }
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Role':
        """Create from dictionary."""
        role = cls(data['name'], data.get('description', ''), data.get('is_default', False))
        role.privileges = {
            db: {
                table: set(privs)
                for table, privs in tables.items()
            }
            for db, tables in data.get('privileges', {}).items()
        }
        return role


class Authenticator:
    """Enhanced database-backed authentication with RBAC."""
    
    def __init__(self, db: Database):
        self.db = db
        self.active_sessions: Dict[str, Dict] = {}
        self._sessions_lock = threading.RLock()
        self.permission_cache = PermissionCache(ttl_seconds=300)
        self._ensure_system_tables()
    
    def _ensure_system_tables(self):
        """Ensure system tables exist for RBAC."""
        # Create roles table
        self.db._ensure_system_tables()
        
        # Ensure roles column exists in users table
        try:
            users = self.db._get_table_data('system', 'users')
            if users and 'roles' not in users[0]:
                # Migrate existing users
                for user in users:
                    user['roles'] = []
                    user['column_privileges'] = {}
                self.db._save_table_data('system', 'users', users)
        except:
            pass
    
    def authenticate(self, username: str, password: str) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Authenticate user against database.
        
        Returns:
            Tuple of (success, session_token, user_info)
        """
        success, is_admin, privileges = self.db.authenticate_user(username, password)
        
        if not success:
            return False, None, None
        
        # Get user roles
        roles = self._get_user_roles(username)
        
        # Create session
        token = secrets.token_hex(16)
        user_info = {
            "username": username,
            "is_admin": is_admin,
            "privileges": privileges,
            "roles": roles
        }
        
        with self._sessions_lock:
            self.active_sessions[token] = user_info
        
        return True, token, user_info
    
    def validate_session(self, token: str) -> bool:
        """Check if session token is valid."""
        with self._sessions_lock:
            return token in self.active_sessions
    
    def get_user_info(self, token: str) -> Optional[Dict]:
        """Get user info from session token."""
        with self._sessions_lock:
            return self.active_sessions.get(token)
    
    def end_session(self, token: str):
        """End a session."""
        with self._sessions_lock:
            if token in self.active_sessions:
                del self.active_sessions[token]
    
    def _get_user_roles(self, username: str) -> List[str]:
        """Get roles assigned to user."""
        try:
            user = self.db._get_user(username)
            return user.get('roles', []) if user else []
        except:
            return []
    
    def _get_role(self, role_name: str) -> Optional[Role]:
        """Get role by name."""
        try:
            roles_data = self.db._get_table_data('system', 'roles')
            for role_data in roles_data:
                if role_data['name'] == role_name:
                    return Role.from_dict(role_data)
        except:
            pass
        return None
    
    def _get_user_effective_privileges(self, username: str, db: str, table: str) -> Set[str]:
        """Get all effective privileges for user (direct + from roles)."""
        privileges = set()
        
        # Get direct privileges
        try:
            user = self.db._get_user(username)
            if user:
                user_privs = user.get('privileges', {})
                if db in user_privs:
                    if table in user_privs[db]:
                        privileges.update(user_privs[db][table])
                    if '*' in user_privs[db]:
                        privileges.update(user_privs[db]['*'])
                if '*' in user_privs:
                    if table in user_privs['*']:
                        privileges.update(user_privs['*'][table])
                    if '*' in user_privs['*']:
                        privileges.update(user_privs['*']['*'])
        except:
            pass
        
        # Get role privileges
        roles = self._get_user_roles(username)
        for role_name in roles:
            role = self._get_role(role_name)
            if role:
                # Check role privileges
                if role.has_privilege(db, table, 'ALL'):
                    privileges.update(ALL_PRIVILEGES)
                else:
                    for priv in ALL_PRIVILEGES:
                        if role.has_privilege(db, table, priv):
                            privileges.add(priv)
        
        return privileges
    
    def check_privilege(self, token: str, db_name: str, table_name: str, 
                       required_priv: str, column: Optional[str] = None) -> bool:
        """
        Check if user has required privilege with caching.
        
        Supports column-level privileges if column is specified.
        """
        user_info = self.get_user_info(token)
        if not user_info:
            return False
        
        username = user_info["username"]
        is_admin = user_info.get("is_admin", False)
        
        # Admins have all privileges
        if is_admin:
            return True
        
        # Check cache first
        cached = self.permission_cache.get(username, db_name, table_name, required_priv, column)
        if cached is not None:
            return cached
        
        # Get effective privileges
        privileges = self._get_user_effective_privileges(username, db_name, table_name)
        
        # Check if has required privilege or ALL
        has_priv = required_priv in privileges or 'ALL' in privileges
        
        # Check column-level privileges if specified
        if has_priv and column:
            # Get column-specific privileges
            try:
                user = self.db._get_user(username)
                col_privs = user.get('column_privileges', {})
                if db_name in col_privs and table_name in col_privs[db_name]:
                    if column in col_privs[db_name][table_name]:
                        allowed = col_privs[db_name][table_name][column]
                        has_priv = required_priv in allowed or 'ALL' in allowed
            except:
                pass
        
        # Cache result
        self.permission_cache.set(username, db_name, table_name, {required_priv: has_priv}, column)
        
        return has_priv
    
    def check_any_privilege(self, token: str, db_name: str, table_name: str,
                           privileges: List[str]) -> bool:
        """Check if user has any of the required privileges."""
        for priv in privileges:
            if self.check_privilege(token, db_name, table_name, priv):
                return True
        return False
    
    def has_db_access(self, token: str, db_name: str) -> bool:
        """Check if user has any access to database."""
        return self.check_privilege(token, db_name, "*", "CONNECT") or \
               self.check_privilege(token, db_name, "*", "ALL")
    
    def has_table_access(self, token: str, db_name: str, table_name: str, 
                         operation: str) -> bool:
        """Check if user can perform operation on table."""
        priv_map = {
            "SELECT": "SELECT",
            "INSERT": "INSERT", 
            "UPDATE": "UPDATE",
            "DELETE": "DELETE",
            "CREATE": "CREATE",
            "DROP": "DROP",
            "ALTER": "ALTER",
            "INDEX": "INDEX"
        }
        required_priv = priv_map.get(operation, operation)
        return self.check_privilege(token, db_name, table_name, required_priv)
    
    def is_replication_user(self, token: str) -> bool:
        """Check if user has REPLICATION SLAVE privilege."""
        return self.check_privilege(token, "*", "*", "REPLICATION_SLAVE")
    
    # Role Management
    
    def create_role(self, role_name: str, description: str = "", 
                    is_default: bool = False) -> str:
        """Create a new role."""
        try:
            roles = self.db._get_table_data('system', 'roles')
            
            # Check if exists
            for role in roles:
                if role['name'] == role_name:
                    return f"ERROR: Role '{role_name}' already exists"
            
            # Create role
            role = Role(role_name, description, is_default)
            roles.append(role.to_dict())
            self.db._save_table_data('system', 'roles', roles)
            
            return f"OK: Role '{role_name}' created"
        except Exception as e:
            return f"ERROR: Failed to create role: {e}"
    
    def drop_role(self, role_name: str) -> str:
        """Drop a role."""
        try:
            roles = self.db._get_table_data('system', 'roles')
            roles = [r for r in roles if r['name'] != role_name]
            self.db._save_table_data('system', 'roles', roles)
            
            # Remove role from all users
            users = self.db._get_table_data('system', 'users')
            for user in users:
                if 'roles' in user and role_name in user['roles']:
                    user['roles'].remove(role_name)
            self.db._save_table_data('system', 'users', users)
            
            # Invalidate cache
            self.permission_cache.clear()
            
            return f"OK: Role '{role_name}' dropped"
        except Exception as e:
            return f"ERROR: Failed to drop role: {e}"
    
    def grant_role_to_user(self, username: str, role_name: str) -> str:
        """Assign role to user."""
        try:
            # Check role exists
            role = self._get_role(role_name)
            if not role:
                return f"ERROR: Role '{role_name}' does not exist"
            
            # Update user
            users = self.db._get_table_data('system', 'users')
            for user in users:
                if user['username'] == username:
                    if 'roles' not in user:
                        user['roles'] = []
                    if role_name not in user['roles']:
                        user['roles'].append(role_name)
                    break
            else:
                return f"ERROR: User '{username}' not found"
            
            self.db._save_table_data('system', 'users', users)
            
            # Invalidate cache
            self.permission_cache.invalidate_user(username)
            
            return f"OK: Role '{role_name}' granted to '{username}'"
        except Exception as e:
            return f"ERROR: Failed to grant role: {e}"
    
    def revoke_role_from_user(self, username: str, role_name: str) -> str:
        """Remove role from user."""
        try:
            users = self.db._get_table_data('system', 'users')
            for user in users:
                if user['username'] == username:
                    if 'roles' in user and role_name in user['roles']:
                        user['roles'].remove(role_name)
                    break
            else:
                return f"ERROR: User '{username}' not found"
            
            self.db._save_table_data('system', 'users', users)
            
            # Invalidate cache
            self.permission_cache.invalidate_user(username)
            
            return f"OK: Role '{role_name}' revoked from '{username}'"
        except Exception as e:
            return f"ERROR: Failed to revoke role: {e}"
    
    def grant_privilege_to_role(self, role_name: str, db: str, table: str,
                                 privileges: List[str]) -> str:
        """Grant privileges to a role."""
        try:
            role = self._get_role(role_name)
            if not role:
                return f"ERROR: Role '{role_name}' does not exist"
            
            # Validate privileges
            invalid_privs = [p for p in privileges if p not in ALL_PRIVILEGES]
            if invalid_privs:
                return f"ERROR: Invalid privileges: {', '.join(invalid_privs)}"
            
            role.grant_privilege(db, table, privileges)
            
            # Save role
            roles = self.db._get_table_data('system', 'roles')
            for i, r in enumerate(roles):
                if r['name'] == role_name:
                    roles[i] = role.to_dict()
                    break
            self.db._save_table_data('system', 'roles', roles)
            
            # Invalidate cache for all users with this role
            self.permission_cache.clear()
            
            return f"OK: Privileges granted to role '{role_name}'"
        except Exception as e:
            return f"ERROR: Failed to grant privileges to role: {e}"
    
    def show_grants(self, username: Optional[str] = None) -> str:
        """Show grants for user or all users."""
        try:
            if username:
                user = self.db._get_user(username)
                if not user:
                    return f"ERROR: User '{username}' not found"
                
                lines = [f"Grants for {username}:"]
                
                # Direct privileges
                privileges = user.get('privileges', {})
                for db, tables in privileges.items():
                    for table, privs in tables.items():
                        lines.append(f"  ON {db}.{table}: {', '.join(privs)}")
                
                # Column privileges
                col_privs = user.get('column_privileges', {})
                for db, tables in col_privs.items():
                    for table, columns in tables.items():
                        for col, privs in columns.items():
                            lines.append(f"  ON {db}.{table}.{col}: {', '.join(privs)}")
                
                # Roles
                roles = user.get('roles', [])
                if roles:
                    lines.append(f"  ROLES: {', '.join(roles)}")
                
                return '\n'.join(lines) if len(lines) > 1 else f"No grants for {username}"
            
            else:
                # Show all users
                users = self.db._get_table_data('system', 'users')
                lines = ["Grants for all users:"]
                for user in users:
                    user_lines = self.show_grants(user['username']).split('\n')[1:]
                    lines.extend(user_lines)
                    lines.append("")
                
                return '\n'.join(lines)
                
        except Exception as e:
            return f"ERROR: Failed to show grants: {e}"
    
    def show_roles(self) -> str:
        """Show all roles."""
        try:
            roles = self.db._get_table_data('system', 'roles')
            if not roles:
                return "No roles defined"
            
            lines = ["Roles:"]
            for role_data in roles:
                role = Role.from_dict(role_data)
                lines.append(f"  {role.name}: {role.description}")
                if role.is_default:
                    lines[-1] += " (default)"
                
                for db, tables in role.privileges.items():
                    for table, privs in tables.items():
                        lines.append(f"    ON {db}.{table}: {', '.join(privs)}")
            
            return '\n'.join(lines)
        except Exception as e:
            return f"ERROR: Failed to show roles: {e}"
    
    def create_replication_user(self, username: str, password: str) -> str:
        """Create a replication user with REPLICATION SLAVE privilege."""
        result = self.db.create_user(username, password, is_admin=False)
        if "already exists" in result:
            return result
        
        # Grant REPLICATION SLAVE privilege
        result2 = self.db.grant_privilege(username, "*", "*", ["REPLICATION_SLAVE"])
        
        # Invalidate cache
        self.permission_cache.invalidate_user(username)
        
        return f"Replication user '{username}' created with REPLICATION SLAVE privilege"
    
    def grant_column_privilege(self, username: str, db: str, table: str,
                              column: str, privileges: List[str]) -> str:
        """Grant column-level privileges."""
        try:
            users = self.db._get_table_data('system', 'users')
            for user in users:
                if user['username'] == username:
                    if 'column_privileges' not in user:
                        user['column_privileges'] = {}
                    if db not in user['column_privileges']:
                        user['column_privileges'][db] = {}
                    if table not in user['column_privileges'][db]:
                        user['column_privileges'][db][table] = {}
                    if column not in user['column_privileges'][db][table]:
                        user['column_privileges'][db][table][column] = []
                    
                    user['column_privileges'][db][table][column].extend(privileges)
                    user['column_privileges'][db][table][column] = list(
                        set(user['column_privileges'][db][table][column])
                    )
                    break
            else:
                return f"ERROR: User '{username}' not found"
            
            self.db._save_table_data('system', 'users', users)
            
            # Invalidate cache
            self.permission_cache.invalidate_user(username)
            
            return f"OK: Column privileges granted to '{username}'"
        except Exception as e:
            return f"ERROR: Failed to grant column privileges: {e}"


def migrate_to_rbac(db: Database) -> str:
    """
    Migrate existing users to new RBAC system.
    
    Creates default roles and assigns users appropriately.
    """
    auth = Authenticator(db)
    
    # Create default roles
    auth.create_role("admin", "Full database access", is_default=False)
    auth.create_role("read_only", "Read-only access", is_default=False)
    auth.create_role("read_write", "Read and write access", is_default=True)
    
    # Grant privileges to roles
    auth.grant_privilege_to_role("admin", "*", "*", ["ALL"])
    auth.grant_privilege_to_role("read_only", "*", "*", ["SELECT"])
    auth.grant_privilege_to_role("read_write", "*", "*", ["SELECT", "INSERT", "UPDATE", "DELETE"])
    
    # Migrate existing users
    try:
        users = db._get_table_data('system', 'users')
        for user in users:
            if 'roles' not in user:
                user['roles'] = []
            if 'column_privileges' not in user:
                user['column_privileges'] = {}
            
            # Assign role based on is_admin
            if user.get('is_admin'):
                if 'admin' not in user['roles']:
                    user['roles'].append('admin')
        
        db._save_table_data('system', 'users', users)
        
        return "OK: Migration to RBAC completed successfully"
    except Exception as e:
        return f"ERROR: Migration failed: {e}"
