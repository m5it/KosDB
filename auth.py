"""
Authentication module using database-backed user management
"""

import hashlib
import secrets
from typing import Dict, Set, List, Optional, Tuple
from database import Database


class Authenticator:
    """Database-backed authentication with privilege checking"""
    
    def __init__(self, db: Database):
        self.db = db
        self.active_sessions: Dict[str, Dict] = {}  # token -> user_info
    
    def authenticate(self, username: str, password: str) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Authenticate user against database.
        
        Returns:
            Tuple of (success, session_token, user_info)
        """
        success, is_admin, privileges = self.db.authenticate_user(username, password)
        
        if not success:
            return False, None, None
        
        # Create session
        token = secrets.token_hex(16)
        user_info = {
            "username": username,
            "is_admin": is_admin,
            "privileges": privileges
        }
        self.active_sessions[token] = user_info
        
        return True, token, user_info
    
    def validate_session(self, token: str) -> bool:
        """Check if session token is valid."""
        return token in self.active_sessions
    
    def get_user_info(self, token: str) -> Optional[Dict]:
        """Get user info from session token."""
        return self.active_sessions.get(token)
    
    def end_session(self, token: str):
        """End a session."""
        if token in self.active_sessions:
            del self.active_sessions[token]
    
    def check_privilege(self, token: str, db_name: str, table_name: str, 
                       required_priv: str) -> bool:
        """Check if user has required privilege."""
        user_info = self.get_user_info(token)
        if not user_info:
            return False
        
        username = user_info["username"]
        is_admin = user_info.get("is_admin", False)
        
        # Admins have all privileges
        if is_admin:
            return True
        
        # Check database privileges
        return self.db.check_privilege(username, db_name, table_name, required_priv)
    
    def has_db_access(self, token: str, db_name: str) -> bool:
        """Check if user has any access to database."""
        return self.check_privilege(token, db_name, "*", "CONNECT")
    
    def has_table_access(self, token: str, db_name: str, table_name: str, 
                         operation: str) -> bool:
        """Check if user can perform operation on table."""
        priv_map = {
            "SELECT": "SELECT",
            "INSERT": "INSERT",
            "UPDATE": "UPDATE",
            "DELETE": "DELETE",
            "CREATE": "CREATE",
            "DROP": "DROP"
        }
        required_priv = priv_map.get(operation, operation)
        return self.check_privilege(token, db_name, table_name, required_priv)
    
    def is_replication_user(self, token: str) -> bool:
        """Check if user has REPLICATION SLAVE privilege."""
        user_info = self.get_user_info(token)
        if not user_info:
            return False
        
        username = user_info["username"]
        is_admin = user_info.get("is_admin", False)
        
        if is_admin:
            return True
        
        # Check for REPLICATION_SLAVE privilege
        privileges = self.db._get_user_privileges(username)
        for priv in privileges:
            if "REPLICATION_SLAVE" in priv.get("privs", []):
                return True
        
        return False
    
    def create_replication_user(self, username: str, password: str) -> str:
        """Create a replication user with REPLICATION SLAVE privilege."""
        # Create the user first
        result = self.db.create_user(username, password, is_admin=False)
        if "already exists" in result:
            return result
        
        # Grant REPLICATION SLAVE privilege
        result2 = self.db.grant_privilege(username, "*", "*", ["REPLICATION_SLAVE"])
        
        return f"Replication user '{username}' created with REPLICATION SLAVE privilege"