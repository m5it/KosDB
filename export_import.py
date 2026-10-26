"""
Offline export/import utilities for KosDB.

These operate directly on the LevelDB data files and do not require a running
server. The server must be stopped while using them to avoid lock conflicts.
"""

import os
import re
import json
from typing import Optional, List

from database import Database
from parser import BackupRestoreParser
from commands import CommandRegistry


class KosDBExporter:
    """Export a KosDB database or table to a SQL dump file."""

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = data_dir
        self.db = Database(data_dir)

    def export(self, target: str, output_file: Optional[str] = None) -> str:
        """Export database or database.table to SQL dump.

        Args:
            target: 'database' or 'database.table'
            output_file: Destination file. If None, derived from target.

        Returns:
            Status message.
        """
        if "." in target:
            db_name, table_name = target.split(".", 1)
            return self._export_table(db_name, table_name, output_file)
        return self._export_database(target, output_file)

    def _export_database(self, db_name: str, output_file: Optional[str]) -> str:
        if db_name not in self.db.list_databases():
            return f"ERROR: Database '{db_name}' does not exist"

        if output_file is None:
            output_file = f"{db_name}.sql"

        result = self.db.use_database(db_name)
        if result.startswith("ERROR"):
            return f"ERROR: {result}"

        tables = self.db.list_tables()
        if not tables:
            # Still export empty databases so users get a valid dump.
            with open(output_file, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            return f"OK: Exported empty database '{db_name}' to {output_file}"

        lines = [
            f"-- KosDB dump of database '{db_name}'",
            f"CREATE DATABASE {db_name};",
            f"USE {db_name};",
            "",
        ]

        for table_name in tables:
            lines.extend(self._dump_table(table_name))
            lines.append("")

        with open(output_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return f"OK: Exported database '{db_name}' to {output_file} ({len(tables)} table(s))"

    def _export_table(self, db_name: str, table_name: str, output_file: Optional[str]) -> str:
        if db_name not in self.db.list_databases():
            return f"ERROR: Database '{db_name}' does not exist"

        if output_file is None:
            output_file = f"{db_name}_{table_name}.sql"

        result = self.db.use_database(db_name)
        if result.startswith("ERROR"):
            return f"ERROR: {result}"

        if table_name not in self.db.list_tables():
            return f"ERROR: Table '{table_name}' does not exist in database '{db_name}'"

        lines = [
            f"-- KosDB dump of {db_name}.{table_name}",
            f"CREATE DATABASE {db_name};",
            f"USE {db_name};",
            "",
        ]
        lines.extend(self._dump_table(table_name))

        with open(output_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return f"OK: Exported table '{db_name}.{table_name}' to {output_file}"

    def _dump_table(self, table_name: str) -> List[str]:
        schema = self.db.get_schema(table_name)
        if not schema:
            return [f"-- Table '{table_name}' schema not found"]

        columns = schema.get("columns", [])
        column_types = schema.get('column_types', {})
        primary_key = schema.get("primary_key")
        indexes = schema.get("indexes", [])

        col_specs = []
        for col in columns:
            col_type = column_types.get(col, 'TEXT').upper()
            if col == primary_key:
                spec = f"{col} {col_type} PRIMARY KEY"
            else:
                spec = f"{col} {col_type}"
            if col in indexes:
                spec += " INDEX"
            col_specs.append(spec)

        lines = [f"DROP TABLE IF EXISTS {table_name};"]
        lines.append(f"CREATE TABLE {table_name} ({', '.join(col_specs)});")

        rows = self.db.select(table_name, raw=True)
        if not rows:
            return lines

        # Preserve next_id for tables with auto-increment primary key.
        if primary_key:
            next_id = schema.get('next_id', 1)
            if next_id > 1:
                lines.append(f"SET TABLE {table_name} next_id {next_id};")

        def _quote_value(val):
            if val is None:
                return "NULL"
            if isinstance(val, (int, float)):
                return str(val)
            if isinstance(val, (list, dict)):
                return "'" + json.dumps(val).replace("'", "''").replace("\\", "\\\\") + "'"
            return "'" + str(val).replace("\\", "\\\\").replace("'", "''").replace("\n", "\\n").replace("\r", "\\r") + "'"

        for row in rows:
            row_columns = [col for col in columns if col in row]
            values = [_quote_value(row[col]) for col in row_columns]
            col_list = ", ".join(row_columns)
            val_list = ", ".join(values)
            lines.append(f"INSERT INTO {table_name} ({col_list}) VALUES ({val_list});")

        return lines

    def close(self):
        self.db.close()


class KosDBImporter:
    """Import a KosDB SQL dump file."""

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = data_dir
        self.db = Database(data_dir)
        self.parser = BackupRestoreParser()
        self.registry = CommandRegistry(self.db, None)

    def import_sql(self, input_file: str) -> str:
        """Execute a SQL dump file against the local database.

        Args:
            input_file: Path to .sql dump file.

        Returns:
            Status message.
        """
        if not os.path.exists(input_file):
            return f"ERROR: File '{input_file}' not found"

        with open(input_file, "r", encoding="utf-8") as f:
            content = f.read()

        statements = self._split_statements(content)

        client_state = {
            'current_db': None,
            'username': 'import',
            'is_admin': True,
            'json_format': False,
        }

        executed = 0
        errors = []
        failed = False

        for stmt in statements:
            if failed:
                errors.append(f"Skipped after earlier error: {stmt[:60]}")
                continue
            try:
                cmd_type, params = self.parser.parse(stmt)
                if cmd_type == 'UNKNOWN':
                    errors.append(f"Unknown command: {stmt[:60]}")
                    failed = True
                    continue
                response = self.registry.execute(cmd_type, params or {}, client_state)
                if response.startswith("ERROR"):
                    errors.append(f"{stmt[:60]}: {response}")
                    failed = True
                else:
                    executed += 1
            except Exception as e:
                errors.append(f"{stmt[:60]}: {e}")
                failed = True

        if errors:
            return f"OK: Imported {executed} statement(s), {len(errors)} error(s):\n" + "\n".join(errors)
        return f"OK: Imported {executed} statement(s) from {input_file}"

    @staticmethod
    def _split_statements(sql: str) -> List[str]:
        """Split SQL dump into executable statements, ignoring comments.

        Statement boundaries are only recognised at top-level semicolons so that
        semicolons inside quoted string literals are not treated as terminators.
        """
        # Strip block comments first.
        sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
        statements = []
        current = []
        quote_char = None
        escape = False
        for ch in sql:
            if escape:
                current.append(ch)
                escape = False
                continue
            if ch == "\\" and quote_char in ("'", '"'):
                current.append(ch)
                escape = True
                continue
            if quote_char is None:
                if ch in ("'", '"'):
                    quote_char = ch
                    current.append(ch)
                elif ch == ";":
                    stmt = "".join(current).strip()
                    # Drop standalone line comments inside the accumulated text.
                    stmt = KosDBImporter._strip_line_comments(stmt)
                    if stmt:
                        statements.append(stmt)
                    current = []
                else:
                    current.append(ch)
            else:
                current.append(ch)
                if ch == quote_char:
                    quote_char = None
        # Trailing statement without semicolon
        stmt = "".join(current).strip()
        stmt = KosDBImporter._strip_line_comments(stmt)
        if stmt:
            statements.append(stmt)
        return statements

    @staticmethod
    def _strip_line_comments(stmt: str) -> str:
        """Remove line-style comments from a statement without touching quoted strings."""
        result = []
        quote_char = None
        escape = False
        i = 0
        while i < len(stmt):
            ch = stmt[i]
            if escape:
                result.append(ch)
                escape = False
                i += 1
                continue
            if ch == "\\" and quote_char in ("'", '"'):
                result.append(ch)
                escape = True
                i += 1
                continue
            if quote_char is None:
                if ch in ("'", '"'):
                    quote_char = ch
                    result.append(ch)
                elif ch == "-" and i + 1 < len(stmt) and stmt[i + 1] == "-":
                    # Skip until newline or end of string.
                    while i < len(stmt) and stmt[i] != "\n":
                        i += 1
                    continue
                elif ch == "#":
                    while i < len(stmt) and stmt[i] != "\n":
                        i += 1
                    continue
                else:
                    result.append(ch)
            else:
                result.append(ch)
                if ch == quote_char:
                    quote_char = None
            i += 1
        return "".join(result).strip()

    def close(self):
        self.db.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="KosDB export/import utilities")
    parser.add_argument("--data-dir", default="./data", help="Data directory")
    parser.add_argument("--export", help="Export database or database.table")
    parser.add_argument("--export-to", help="Output file for export")
    parser.add_argument("--import", dest="import_file", help="Import SQL dump file")
    args = parser.parse_args()

    if args.export:
        exporter = KosDBExporter(args.data_dir)
        print(exporter.export(args.export, args.export_to))
        exporter.close()
    elif args.import_file:
        importer = KosDBImporter(args.data_dir)
        print(importer.import_sql(args.import_file))
        importer.close()
    else:
        parser.print_help()
