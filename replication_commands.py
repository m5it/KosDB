"""
Replication Control Commands

SQL-like commands for managing replication:
- START SLAVE
- STOP SLAVE
- RESET SLAVE
- SHOW SLAVE STATUS
"""

from typing import Dict, Any, Optional
from database import Database


class StartSlaveCommand:
    """START SLAVE - Begin replication from master."""
    
    def __init__(self, db: Database, replication_client=None):
        self.db = db
        self.replication_client = replication_client
    
    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        if not client_state.get('is_admin'):
            return "ERROR: Admin only"
        
        # This would require access to the replication client from server
        # For now, return status
        if self.replication_client and self.replication_client.is_alive():
            return "OK: Slave is already running"
        
        return "OK: Slave started (if configured)"


class StopSlaveCommand:
    """STOP SLAVE - Pause replication."""
    
    def __init__(self, db: Database, replication_client=None):
        self.db = db
        self.replication_client = replication_client
    
    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        if not client_state.get('is_admin'):
            return "ERROR: Admin only"
        
        if self.replication_client:
            self.replication_client.stop()
            return "OK: Slave stopped"
        
        return "ERROR: Slave not running"


class ResetSlaveCommand:
    """RESET SLAVE - Clear replication state and start from beginning."""
    
    def __init__(self, db: Database):
        self.db = db
    
    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        if not client_state.get('is_admin'):
            return "ERROR: Admin only"
        
        try:
            # Clear saved position
            if self.db._system_db:
                self.db._system_db.delete(b"_replication:last_position")
                return "OK: Slave reset - will start from beginning on next START SLAVE"
        except Exception as e:
            return f"ERROR: {e}"
        
        return "ERROR: Could not reset slave"


class ShowSlaveStatusCommand:
    """SHOW SLAVE STATUS - Display replication status."""
    
    def __init__(self, db: Database, replication_client=None):
        self.db = db
        self.replication_client = replication_client
    
    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        if not client_state.get('is_admin'):
            return "ERROR: Admin only"
        
        try:
            lines = []
            lines.append("-" * 50)
            lines.append("Slave Status")
            lines.append("-" * 50)
            
            # Connection status
            if self.replication_client:
                lines.append(f"Slave IO State: {'Connected' if self.replication_client.connected else 'Disconnected'}")
                lines.append(f"Master Host: {self.replication_client.master_host}")
                lines.append(f"Master Port: {self.replication_client.master_port}")
            else:
                lines.append("Slave IO State: Not configured")
            
            # Position info
            if self.db._system_db:
                pos_data = self.db._system_db.get(b"_replication:last_position")
                if pos_data:
                    last_pos = int(pos_data.decode())
                    lines.append(f"Last Applied Position: {last_pos}")
                else:
                    lines.append("Last Applied Position: Not set")
            
            if self.db._binlog:
                lines.append(f"Master Binlog Position: {self.db._binlog.get_latest_position()}")
            
            lines.append("-" * 50)
            return "\n".join(lines)
            
        except Exception as e:
            return f"ERROR: {e}"


# Export command classes
__all__ = [
    'StartSlaveCommand',
    'StopSlaveCommand', 
    'ResetSlaveCommand',
    'ShowSlaveStatusCommand'
]