"""Authentication module for the socket server."""

import hashlib
import secrets


class Authenticator:
    """Simple authenticator with session management."""
    
    VALID_CREDENTIALS = {
        'admin': 'skrlat'
    }
    
    def __init__(self):
        self.active_sessions = set()
    
    def authenticate(self, username: str, password: str) -> bool:
        """
        Validate credentials.
        
        Args:
            username: Username to validate
            password: Password to validate
            
        Returns:
            True if authentication successful, False otherwise
        """
        if username in self.VALID_CREDENTIALS:
            return self.VALID_CREDENTIALS[username] == password
        return False
    
    def generate_token(self) -> str:
        """Generate a secure session token."""
        return secrets.token_hex(16)
    
    def create_session(self, token: str) -> None:
        """Mark a token as an active session."""
        self.active_sessions.add(token)
    
    def validate_session(self, token: str) -> bool:
        """Check if a session token is valid."""
        return token in self.active_sessions
    
    def remove_session(self, token: str) -> None:
        """Remove a session token."""
        self.active_sessions.discard(token)
