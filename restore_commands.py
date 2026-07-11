"""
Restore command handlers for KosDB.

This module provides a standalone RestoreCommands class that wraps the
restore logic used by the command registry.
"""

import json
import gzip
import os
from typing import Optional, Dict, Any, List


class RestoreCommands:
    """High-level restore command handlers."""

    def __init__(self, db=None):
        self.db = db

    def restore_database(self, db_name: str, file_path: str, db=None) -> str:
        """Restore an entire database from a backup file."""
        database = db or self.db
        if database is None:
            return "ERROR: Database not available"

        if not os.path.exists(file_path):
            return f"ERROR: Backup file not found: {file_path}"

        try:
            with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                backup_data = json.load(f)
        except Exception as e:
            return f"ERROR: Cannot read backup file: {e}"

        if 'version' not in backup_data or 'tables' not in backup_data:
            return "ERROR: Invalid backup file format"

        source_db = backup_data.get('database', 'unknown')
        if source_db != db_name:
            return f"ERROR: Backup database '{source_db}' does not match target '{db_name}'"

        try:
            database.create_database(db_name)
            database.use_database(db_name)

            tables_restored = 0
            rows_restored = 0

            for table_name, table_info in backup_data['tables'].items():
                schema = table_info.get('schema', {})
                rows = table_info.get('rows', [])
                columns = schema.get('columns', [])

                if columns:
                    database.create_table(table_name, columns)

                for row in rows:
                    values = [row.get(col) for col in columns]
                    database.insert(table_name, values)
                    rows_restored += 1

                tables_restored += 1

            return f"OK: Restored {tables_restored} tables, {rows_restored} rows from {source_db}"
        except Exception as e:
            return f"ERROR: Restore failed - {e}"

    def restore_table(self, db_name: str, table_name: str, file_path: str, db=None) -> str:
        """Restore a single table from a backup file."""
        database = db or self.db
        if database is None:
            return "ERROR: Database not available"

        if not os.path.exists(file_path):
            return f"ERROR: Backup file not found: {file_path}"

        try:
            with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                backup_data = json.load(f)
        except Exception as e:
            return f"ERROR: Cannot read backup file: {e}"

        if table_name not in backup_data.get('tables', {}):
            return f"ERROR: Table '{table_name}' not found in backup"

        database.create_database(db_name)
        database.use_database(db_name)

        table_info = backup_data['tables'][table_name]
        schema = table_info.get('schema', {})
        rows = table_info.get('rows', [])
        columns = schema.get('columns', [])

        if columns:
            database.create_table(table_name, columns)

        rows_restored = 0
        for row in rows:
            values = [row.get(col) for col in columns]
            database.insert(table_name, values)
            rows_restored += 1

        return f"OK: Restored table '{table_name}' with {rows_restored} rows"

    def list_backups(self, path: str = '.') -> str:
        """List available backup files in a directory."""
        import glob
        if not os.path.isdir(path):
            return f"ERROR: Directory not found: {path}"

        files = sorted(glob.glob(os.path.join(path, '*.json.gz')), reverse=True)
        if not files:
            return "OK: No backup files found"

        lines = ["Backup files:", "-" * 50]
        for f in files:
            lines.append(os.path.basename(f))
        return "\n".join(lines)

    def verify_backup(self, file_path: str) -> str:
        """Verify a backup file's integrity."""
        from backup_utils import verify_backup_integrity
        valid, error = verify_backup_integrity(file_path)
        if valid:
            return f"OK: Backup '{file_path}' is valid"
        return f"ERROR: Backup '{file_path}' is invalid: {error}"


# Keep the original git-restore helper available for scripts.
def restore_commands_from_git():
    """Restore commands.py from git HEAD (legacy helper)."""
    import subprocess
    result = subprocess.run(
        ['git', 'show', 'HEAD:commands.py'],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print("ERROR:", result.stderr)
        return False
    with open('commands.py', 'w') as f:
        f.write(result.stdout)
    print(f"Restored commands.py: {len(result.stdout)} chars, {result.stdout.count(chr(10))} lines")
    return True


if __name__ == '__main__':
    restore_commands_from_git()
