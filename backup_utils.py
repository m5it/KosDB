"""
Backup utilities with integrity checking for LevelDB Socket Server
"""

import json
import gzip
import hashlib
import os
from datetime import datetime
from typing import Dict, Any, Optional, Tuple


class BackupIntegrityError(Exception):
    """Raised when backup integrity check fails."""
    pass


def calculate_checksum(data: bytes) -> str:
    """Calculate SHA-256 checksum of data."""
    return hashlib.sha256(data).hexdigest()


def verify_backup_integrity(file_path: str) -> Tuple[bool, Optional[str]]:
    """
    Verify backup file integrity.
    Returns (success, error_message)
    """
    try:
        # Check file exists and is readable
        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}"
        
        if not os.access(file_path, os.R_OK):
            return False, f"File not readable: {file_path}"
        
        # Try to decompress and parse
        with gzip.open(file_path, 'rt', encoding='utf-8') as f:
            content = f.read()
            backup_data = json.loads(content)
        
        # Verify required fields
        if 'version' not in backup_data:
            return False, "Missing 'version' field"
        
        if 'tables' not in backup_data and 'table' not in backup_data:
            return False, "Missing 'tables' or 'table' field"
        
        # Verify checksum if present
        if 'checksum' in backup_data:
            stored_checksum = backup_data['checksum']
            # Recalculate checksum without the checksum field
            verification_data = {k: v for k, v in backup_data.items() if k != 'checksum'}
            expected = calculate_checksum(json.dumps(verification_data, sort_keys=True).encode())
            if stored_checksum != expected:
                return False, "Checksum mismatch - file may be corrupted"
        
        # Verify table data integrity
        if 'tables' in backup_data:
            for table_name, table_info in backup_data['tables'].items():
                if 'schema' not in table_info:
                    return False, f"Table '{table_name}' missing schema"
                if 'rows' not in table_info:
                    return False, f"Table '{table_name}' missing rows"
        elif 'table' in backup_data:
            # Single table backup
            if 'schema' not in backup_data:
                return False, "Single table backup missing schema"
            if 'rows' not in backup_data:
                return False, "Single table backup missing rows"
        
        return True, None
        
    except gzip.BadGzipFile:
        return False, "Invalid gzip file - may be corrupted"
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {e}"
    except Exception as e:
        return False, f"Integrity check failed: {e}"


def create_backup_metadata(db_name: str, tables: list, rows_count: int) -> Dict[str, Any]:
    """Create metadata for backup file."""
    return {
        'version': '1.0',
        'created_at': datetime.now().isoformat(),
        'database': db_name,
        'table_count': len(tables),
        'row_count': rows_count,
        'tables': tables
    }


def add_integrity_check(backup_data: Dict[str, Any]) -> Dict[str, Any]:
    """Add checksum to backup data for integrity verification."""
    # Create a copy without checksum for calculation
    data_for_hash = {k: v for k, v in backup_data.items() if k != 'checksum'}
    data_bytes = json.dumps(data_for_hash, sort_keys=True).encode()
    backup_data['checksum'] = calculate_checksum(data_bytes)
    return backup_data


def validate_before_restore(file_path: str, target_db: str) -> Tuple[bool, Optional[str]]:
    """
    Validate backup before restore.
    Returns (success, error_message)
    """
    valid, error = verify_backup_integrity(file_path)
    if not valid:
        return False, error
    
    try:
        with gzip.open(file_path, 'rt', encoding='utf-8') as f:
            backup_data = json.load(f)
        
        # Check if target database matches
        source_db = backup_data.get('database')
        if source_db and source_db != target_db:
            # This is a warning, not an error
            pass  # Allow restoring to different database name
        
        return True, None
        
    except Exception as e:
        return False, f"Validation failed: {e}"


def get_backup_info(file_path: str) -> Optional[Dict[str, Any]]:
    """Get information about a backup file."""
    try:
        stat = os.stat(file_path)
        
        with gzip.open(file_path, 'rt', encoding='utf-8') as f:
            backup_data = json.load(f)
        
        info = {
            'file': os.path.basename(file_path),
            'path': file_path,
            'size': stat.st_size,
            'size_human': format_size(stat.st_size),
            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'version': backup_data.get('version', 'unknown'),
            'database': backup_data.get('database', 'unknown'),
            'table_count': backup_data.get('table_count', len(backup_data.get('tables', {}))),
            'row_count': backup_data.get('row_count', 0),
            'has_checksum': 'checksum' in backup_data
        }
        
        # Calculate row count if not stored
        if info['row_count'] == 0 and 'tables' in backup_data:
            for table_data in backup_data['tables'].values():
                info['row_count'] += len(table_data.get('rows', []))
        
        return info
        
    except Exception:
        return None


def format_size(size_bytes: int) -> str:
    """Format byte size to human readable."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


class BackupManager:
    """Manage backup operations with integrity checking."""
    
    def __init__(self, backup_dir: str = './backups'):
        self.backup_dir = backup_dir
        os.makedirs(backup_dir, exist_ok=True)
    
    def list_backups(self) -> list:
        """List all backup files with info."""
        backups = []
        for filename in os.listdir(self.backup_dir):
            if filename.endswith('.json.gz'):
                file_path = os.path.join(self.backup_dir, filename)
                info = get_backup_info(file_path)
                if info:
                    backups.append(info)
        return sorted(backups, key=lambda x: x['modified'], reverse=True)
    
    def cleanup_old_backups(self, keep_count: int = 10):
        """Remove old backups keeping only the most recent."""
        backups = self.list_backups()
        if len(backups) > keep_count:
            for backup in backups[keep_count:]:
                try:
                    os.remove(backup['path'])
                except:
                    pass


def generate_backup_filename(db_name: str, suffix: str = '') -> str:
    """Generate standardized backup filename."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    if suffix:
        return f"{db_name}_{suffix}_{timestamp}.json.gz"
    return f"{db_name}_{timestamp}.json.gz"
