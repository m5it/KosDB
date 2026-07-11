"""
Command Execution Framework for LevelDB Socket Server
"""

from typing import Dict, Any, Optional, List
from database import Database


class Command:
    def __init__(self, db: Database, replication_client=None):
        self.db = db
        self.replication_client = replication_client
    
    def execute(self, params: Dict[str, Any], client_state: Dict[str, Any]) -> str:
        raise NotImplementedError
    
    def validate_params(self, params: Dict[str, Any], required: List[str]) -> bool:
        for param in required:
            if param not in params or params[param] is None:
                return False
        return True


class CreateDatabaseCommand(Command):
    def execute(self, params, client_state):
        if not self.validate_params(params, ['database']):
            return "ERROR: Database name required"
        try:
            self.db.create_database(params['database'])
            return f"OK: Database '{params['database']}' created"
        except Exception as e:
            return f"ERROR: {e}"


class DropDatabaseCommand(Command):
    def execute(self, params, client_state):
        if not self.validate_params(params, ['database']):
            return "ERROR: Database name required"
        try:
            self.db.drop_database(params['database'])
            if client_state.get('current_db') == params['database']:
                client_state['current_db'] = None
            return f"OK: Database '{params['database']}' dropped"
        except Exception as e:
            return f"ERROR: {e}"


class UseDatabaseCommand(Command):
    def execute(self, params, client_state):
        if not self.validate_params(params, ['database']):
            return "ERROR: Database name required"
        try:
            result = self.db.use_database(params['database'])
            client_state['current_db'] = params['database']
            return result
        except Exception as e:
            return f"ERROR: {e}"


class CreateTableCommand(Command):
    def execute(self, params, client_state):
        if not self.validate_params(params, ['table']):
            return "ERROR: Table name required"
        if not client_state.get('current_db'):
            return "ERROR: No database selected"
        try:
            columns = params.get('columns', [])
            self.db.create_table(params['table'], columns)
            return f"OK: Table '{params['table']}' created"
        except Exception as e:
            return f"ERROR: {e}"


class DropTableCommand(Command):
    def execute(self, params, client_state):
        if not self.validate_params(params, ['table']):
            return "ERROR: Table name required"
        if not client_state.get('current_db'):
            return "ERROR: No database selected"
        try:
            self.db.drop_table(params['table'])
            return f"OK: Table '{params['table']}' dropped"
        except Exception as e:
            return f"ERROR: {e}"


class InsertCommand(Command):
    def execute(self, params, client_state):
        if not self.validate_params(params, ['table', 'values']):
            return "ERROR: Table and values required"
        if not client_state.get('current_db'):
            return "ERROR: No database selected"
        try:
            self.db.insert(params['table'], params['values'])
            return f"OK: Inserted into '{params['table']}'"
        except Exception as e:
            return f"ERROR: {e}"


class SelectCommand(Command):
    def execute(self, params, client_state):
        if not self.validate_params(params, ['table']):
            return "ERROR: Table name required"
        if not client_state.get('current_db'):
            return "ERROR: No database selected"
        try:
            columns = params.get('columns', ['*'])
            where = params.get('where')
            order_by = params.get('order_by')
            order_desc = params.get('order_desc', False)
            result = self.db.select(params['table'], columns, where, order_by, order_desc)
            return result
        except Exception as e:
            return f"ERROR: {e}"


class UpdateCommand(Command):
    def execute(self, params, client_state):
        if not self.validate_params(params, ['table', 'set']):
            return "ERROR: Table and SET required"
        if not client_state.get('current_db'):
            return "ERROR: No database selected"
        try:
            count = self.db.update(params['table'], params['set'], params.get('where'))
            return f"OK: Updated {count} row(s)"
        except Exception as e:
            return f"ERROR: {e}"


class DeleteCommand(Command):
    def execute(self, params, client_state):
        if not self.validate_params(params, ['table']):
            return "ERROR: Table name required"
        if not client_state.get('current_db'):
            return "ERROR: No database selected"
        try:
            count = self.db.delete(params['table'], params.get('where'))
            return f"OK: Deleted {count} row(s)"
        except Exception as e:
            return f"ERROR: {e}"


class ShowTablesCommand(Command):
    def execute(self, params, client_state):
        if not client_state.get('current_db'):
            return "ERROR: No database selected"
        try:
            tables = self.db.list_tables()
            return "OK:\n" + "\n".join(tables) if tables else "OK: No tables"
        except Exception as e:
            return f"ERROR: {e}"


class ShowDatabasesCommand(Command):
    def execute(self, params, client_state):
        try:
            dbs = self.db.list_databases()
            return "OK:\n" + "\n".join(dbs) if dbs else "OK: No databases"
        except Exception as e:
            return f"ERROR: {e}"


class ShowUsersCommand(Command):
    def execute(self, params, client_state):
        if not client_state.get('is_admin'):
            return "ERROR: Admin only"
        try:
            users = self.db.list_users()
            return "OK:\n" + "\n".join(users) if users else "OK: No users"
        except Exception as e:
            return f"ERROR: {e}"


class ShowMasterStatusCommand(Command):
    def execute(self, params, client_state):
        if not client_state.get('is_admin'):
            return "ERROR: Admin only"
        try:
            if not self.db._binlog:
                return "ERROR: Binlog not initialized"
            
            position = self.db._binlog.get_latest_position()
            
            lines = []
            lines.append("-" * 50)
            lines.append("Master Status")
            lines.append("-" * 50)
            lines.append(f"Binlog Position: {position}")
            lines.append(f"Server ID: {self.db.server_id}")
            lines.append("Connected Slaves: 0")
            lines.append("-" * 50)
            return "\n".join(lines)
            
        except Exception as e:
            return f"ERROR: {e}"


class ShowSlaveStatusCommand(Command):
    def execute(self, params, client_state):
        if not client_state.get('is_admin'):
            return "ERROR: Admin only"
        
        try:
            lines = []
            lines.append("-" * 50)
            lines.append("Slave Status")
            lines.append("-" * 50)
            
            if self.replication_client:
                lines.append(f"Slave IO State: {'Connected' if self.replication_client.connected else 'Disconnected'}")
                lines.append(f"Master Host: {self.replication_client.master_host}")
                lines.append(f"Master Port: {self.replication_client.master_port}")
            else:
                lines.append("Slave IO State: Not configured")
            
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


class StartSlaveCommand(Command):
    def execute(self, params, client_state):
        if not client_state.get('is_admin'):
            return "ERROR: Admin only"
        
        if self.replication_client and self.replication_client.is_alive():
            return "OK: Slave is already running"
        
        return "OK: Slave started (if configured)"


class StopSlaveCommand(Command):
    def execute(self, params, client_state):
        if not client_state.get('is_admin'):
            return "ERROR: Admin only"
        
        if self.replication_client:
            self.replication_client.stop()
            return "OK: Slave stopped"
        
        return "ERROR: Slave not running"


class ResetSlaveCommand(Command):
    def execute(self, params, client_state):
        if not client_state.get('is_admin'):
            return "ERROR: Admin only"
        
        try:
            if self.db._system_db:
                self.db._system_db.delete(b"_replication:last_position")
                return "OK: Slave reset - will start from beginning"
        except Exception as e:
            return f"ERROR: {e}"


class CreateReplicationUserCommand(Command):
    def execute(self, params, client_state):
        if not client_state.get('is_admin'):
            return "ERROR: Admin only"
        if not self.validate_params(params, ['username', 'password']):
            return "ERROR: Username and password required"
        try:
            from auth import Authenticator
            auth = Authenticator(self.db)
            result = auth.create_replication_user(params['username'], params['password'])
            return f"OK: {result}"
        except Exception as e:
            return f"ERROR: {e}"


class BackupDatabaseCommand(Command):
    def execute(self, params, client_state):
        if not self.validate_params(params, ['database', 'file']):
            return "ERROR: Database name and file path required"
        if not client_state.get('is_admin'):
            return "ERROR: Admin only"
        
        import json
        import gzip
        import os
        import hashlib
        from datetime import datetime
        
        db_name = params['database']
        file_path = params['file']
        
        if not file_path.endswith('.json.gz'):
            file_path += '.json.gz'
        
        try:
            result = self.db.use_database(db_name)
            if result.startswith("Database"):
                return f"ERROR: {result}"
            
            backup_data = {
                'version': '1.0',
                'database': db_name,
                'created_at': datetime.now().isoformat(),
                'tables': {}
            }
            
            tables = self.db.list_tables()
            total_rows = 0
            
            for table_name in tables:
                if table_name.startswith('_'):
                    continue
                
                table_data = []
                prefix = f"{table_name}:".encode()
                for key, value in self.db._db.iterator(prefix=prefix):
                    if key.startswith(f"_schema:{table_name}".encode()):
                        continue
                    row = json.loads(value.decode())
                    table_data.append(row)
                
                schema_key = f"_schema:{table_name}".encode()
                schema_data = self.db._db.get(schema_key)
                schema = json.loads(schema_data.decode()) if schema_data else {}
                
                backup_data['tables'][table_name] = {
                    'schema': schema,
                    'rows': table_data
                }
                total_rows += len(table_data)
            
            backup_data['table_count'] = len([t for t in tables if not t.startswith('_')])
            backup_data['row_count'] = total_rows
            
            data_for_hash = {k: v for k, v in backup_data.items() if k != 'checksum'}
            hash_bytes = json.dumps(data_for_hash, sort_keys=True).encode()
            backup_data['checksum'] = hashlib.sha256(hash_bytes).hexdigest()
            
            with gzip.open(file_path, 'wt', encoding='utf-8') as f:
                json.dump(backup_data, f, indent=2)
            
            if client_state.get('current_db') and client_state['current_db'] != db_name:
                self.db.use_database(client_state['current_db'])
            
            size_mb = os.path.getsize(file_path) / (1024 * 1024)
            return f"OK: Backup complete - {backup_data['table_count']} tables, {total_rows} rows, {size_mb:.2f} MB"
            
        except Exception as e:
            return f"ERROR: Backup failed - {e}"


class RestoreDatabaseCommand(Command):
    def execute(self, params, client_state):
        if not self.validate_params(params, ['database', 'file']):
            return "ERROR: Database name and file path required"
        if not client_state.get('is_admin'):
            return "ERROR: Admin only"
        
        import json
        import gzip
        import os
        import hashlib
        
        db_name = params['database']
        file_path = params['file']
        
        if not file_path.endswith('.json.gz'):
            file_path += '.json.gz'
        
        if not os.path.exists(file_path):
            return f"ERROR: Backup file not found: {file_path}"
        
        try:
            with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                backup_data = json.load(f)
            
            if 'checksum' in backup_data:
                stored_checksum = backup_data['checksum']
                data_for_hash = {k: v for k, v in backup_data.items() if k != 'checksum'}
                expected = hashlib.sha256(json.dumps(data_for_hash, sort_keys=True).encode()).hexdigest()
                if stored_checksum != expected:
                    return "ERROR: Integrity check failed - checksum mismatch"
        except Exception as e:
            return f"ERROR: Cannot read backup file: {e}"
        
        try:
            if 'version' not in backup_data or 'tables' not in backup_data:
                return "ERROR: Invalid backup file format"
            
            source_db = backup_data.get('database', 'unknown')
            source_time = backup_data.get('created_at', 'unknown')
            
            self.db.create_database(db_name)
            self.db.use_database(db_name)
            
            tables_restored = 0
            rows_restored = 0
            
            for table_name, table_info in backup_data['tables'].items():
                schema = table_info.get('schema', {})
                rows = table_info.get('rows', [])
                
                columns = schema.get('columns', [])
                if columns:
                    self.db.create_table(table_name, columns)
                
                for row in rows:
                    values = [row.get(col) for col in columns]
                    self.db.insert(table_name, values)
                    rows_restored += 1
                
                tables_restored += 1
            
            return f"OK: Restored {tables_restored} tables, {rows_restored} rows from {source_db}"
            
        except json.JSONDecodeError:
            return "ERROR: Invalid JSON in backup file"
        except Exception as e:
            return f"ERROR: Restore failed - {e}"


class BackupTableCommand(Command):
    def execute(self, params, client_state):
        if not self.validate_params(params, ['table', 'file']):
            return "ERROR: Table name and file path required"
        if not client_state.get('current_db'):
            return "ERROR: No database selected"
        
        import json
        import gzip
        import hashlib
        from datetime import datetime
        
        table_name = params['table']
        file_path = params['file']
        
        if not file_path.endswith('.json.gz'):
            file_path += '.json.gz'
        
        try:
            schema_key = f"_schema:{table_name}".encode()
            schema_data = self.db._db.get(schema_key)
            if not schema_data:
                return f"ERROR: Table '{table_name}' does not exist"
            
            schema = json.loads(schema_data.decode())
            
            rows = []
            prefix = f"{table_name}:".encode()
            for key, value in self.db._db.iterator(prefix=prefix):
                if key.startswith(f"_schema:{table_name}".encode()):
                    continue
                row = json.loads(value.decode())
                rows.append(row)
            
            backup_data = {
                'version': '1.0',
                'database': client_state.get('current_db'),
                'table': table_name,
                'created_at': datetime.now().isoformat(),
                'schema': schema,
                'rows': rows,
                'row_count': len(rows)
            }
            
            data_for_hash = {k: v for k, v in backup_data.items() if k != 'checksum'}
            backup_data['checksum'] = hashlib.sha256(json.dumps(data_for_hash, sort_keys=True).encode()).hexdigest()
            
            with gzip.open(file_path, 'wt', encoding='utf-8') as f:
                json.dump(backup_data, f, indent=2)
            
            return f"OK: Table '{table_name}' backed up - {len(rows)} rows"
            
        except Exception as e:
            return f"ERROR: Backup failed - {e}"


class ListBackupsCommand(Command):
    def execute(self, params, client_state):
        import os
        import glob
        import gzip
        import json
        
        path = params.get('path', '.')
        if not os.path.isdir(path):
            return f"ERROR: Directory not found: {path}"
        
        try:
            backup_files = glob.glob(os.path.join(path, '*.json.gz'))
            if not backup_files:
                return "OK: No backup files found"
            
            lines = []
            lines.append("-" * 80)
            lines.append(f"{'Backup File':<35} {'Size':>10} {'Tables':>8} {'Rows':>10} {'Status':>8}")
            lines.append("-" * 80)
            
            for backup_file in sorted(backup_files, reverse=True):
                try:
                    with gzip.open(backup_file, 'rt', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    filename = os.path.basename(backup_file)
                    size = os.path.getsize(backup_file)
                    
                    if size < 1024:
                        size_str = f"{size} B"
                    elif size < 1024 * 1024:
                        size_str = f"{size/1024:.1f} KB"
                    else:
                        size_str = f"{size/(1024*1024):.1f} MB"
                    
                    table_count = len(data.get('tables', {}))
                    if table_count == 0 and 'table' in data:
                        table_count = 1
                    
                    row_count = data.get('row_count', 0)
                    if row_count == 0 and 'tables' in data:
                        for t in data['tables'].values():
                            row_count += len(t.get('rows', []))
                    
                    status = "OK" if 'checksum' in data else "?"
                    lines.append(f"{filename[:34]:<35} {size_str:>10} {table_count:>8} {row_count:>10} {status:>8}")
                except:
                    filename = os.path.basename(backup_file)
                    lines.append(f"{filename[:34]:<35} {'?':>10} {'?':>8} {'?':>10} {'ERR':>8}")
            
            lines.append("-" * 80)
            lines.append(f"{len(backup_files)} backup(s) found")
            
            return "\n".join(lines)
            
        except Exception as e:
            return f"ERROR: {e}"


class VerifyBackupCommand(Command):
    def execute(self, params, client_state):
        if not self.validate_params(params, ['file']):
            return "ERROR: Backup file path required"
        if not client_state.get('is_admin'):
            return "ERROR: Admin only"
        
        import os
        import gzip
        import json
        import hashlib
        
        file_path = params['file']
        if not file_path.endswith('.json.gz'):
            file_path += '.json.gz'
        
        if not os.path.exists(file_path):
            return f"ERROR: Backup file not found: {file_path}"
        
        try:
            with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                backup_data = json.load(f)
            
            if 'version' not in backup_data:
                return "ERROR: Missing 'version' field - invalid backup format"
            
            has_checksum = 'checksum' in backup_data
            
            lines = []
            lines.append("-" * 50)
            
            if has_checksum:
                stored_checksum = backup_data['checksum']
                data_for_hash = {k: v for k, v in backup_data.items() if k != 'checksum'}
                expected = hashlib.sha256(json.dumps(data_for_hash, sort_keys=True).encode()).hexdigest()
                
                if stored_checksum == expected:
                    lines.append("Backup Verification: PASSED")
                else:
                    lines.append("Backup Verification: FAILED")
                    lines.append(f"Expected: {expected[:32]}...")
                    lines.append(f"Found:    {stored_checksum[:32]}...")
                    return "\n".join(lines)
            else:
                lines.append("Backup Verification: WARNING")
                lines.append("No checksum present - cannot verify integrity")
            
            lines.append("-" * 50)
            lines.append(f"File: {os.path.basename(file_path)}")
            lines.append(f"Version: {backup_data.get('version', 'unknown')}")
            lines.append(f"Database: {backup_data.get('database', 'unknown')}")
            lines.append(f"Created: {backup_data.get('created_at', 'unknown')}")
            
            if 'tables' in backup_data:
                lines.append(f"Tables: {len(backup_data['tables'])}")
                total_rows = sum(len(t.get('rows', [])) for t in backup_data['tables'].values())
                lines.append(f"Rows: {total_rows}")
            elif 'table' in backup_data:
                lines.append(f"Table: {backup_data['table']}")
                lines.append(f"Rows: {len(backup_data.get('rows', []))}")
            
            lines.append("-" * 50)
            return "\n".join(lines)
                
        except gzip.BadGzipFile:
            return "ERROR: Invalid gzip file - may be corrupted"
        except json.JSONDecodeError as e:
            return f"ERROR: Invalid JSON: {e}"
        except Exception as e:
            return f"ERROR: Verification failed: {e}"


class BeginTransactionCommand(Command):
    def execute(self, params, client_state):
        if not client_state.get('current_db'):
            return "ERROR: No database selected"
        return self.db.begin_transaction()


class CommitCommand(Command):
    def execute(self, params, client_state):
        return self.db.commit_transaction()


class RollbackCommand(Command):
    def execute(self, params, client_state):
        return self.db.rollback_transaction()


class DistributedTxBeginCommand(Command):
    def execute(self, params, client_state):
        if not client_state.get('is_admin'):
            return "ERROR: Admin only"
        if not self.validate_params(params, ['operations']):
            return "ERROR: Operations JSON required"
        
        try:
            from distributed_tx import DistributedTxCommands
            dist_tx = DistributedTxCommands()
            if hasattr(self.db, '_dist_tx_coordinator'):
                dist_tx.coordinator = self.db._dist_tx_coordinator
            return dist_tx.dist_tx_begin(params['operations'])
        except Exception as e:
            return f"ERROR: {e}"


class DistributedTxStatusCommand(Command):
    def execute(self, params, client_state):
        if not client_state.get('is_admin'):
            return "ERROR: Admin only"
        if not self.validate_params(params, ['tx_id']):
            return "ERROR: Transaction ID required"
        
        try:
            from distributed_tx import DistributedTxCommands
            dist_tx = DistributedTxCommands()
            if hasattr(self.db, '_dist_tx_coordinator'):
                dist_tx.coordinator = self.db._dist_tx_coordinator
            return dist_tx.dist_tx_status(params['tx_id'])
        except Exception as e:
            return f"ERROR: {e}"


class DistributedTxListCommand(Command):
    def execute(self, params, client_state):
        if not client_state.get('is_admin'):
            return "ERROR: Admin only"
        
        try:
            from distributed_tx import DistributedTxCommands
            dist_tx = DistributedTxCommands()
            if hasattr(self.db, '_dist_tx_coordinator'):
                dist_tx.coordinator = self.db._dist_tx_coordinator
            return dist_tx.dist_tx_list()
        except Exception as e:
            return f"ERROR: {e}"


class FailoverStatusCommand(Command):
    def execute(self, params, client_state):
        if not client_state.get('is_admin'):
            return "ERROR: Admin only"
        
        try:
            from failover import FailoverCommands
            fm = FailoverCommands()
            if hasattr(self.db, '_failover_manager'):
                fm.manager = self.db._failover_manager
            return fm.failover_status()
        except Exception as e:
            return f"ERROR: {e}"


class FailoverProposeCommand(Command):
    def execute(self, params, client_state):
        if not client_state.get('is_admin'):
            return "ERROR: Admin only"
        if not self.validate_params(params, ['command']):
            return "ERROR: Command JSON required"
        
        try:
            from failover import FailoverCommands
            fm = FailoverCommands()
            if hasattr(self.db, '_failover_manager'):
                fm.manager = self.db._failover_manager
            return fm.propose_command(params['command'])
        except Exception as e:
            return f"ERROR: {e}"


class MetricsCommand(Command):
    def execute(self, params, client_state):
        if not client_state.get('is_admin'):
            return "ERROR: Admin only"
        
        try:
            from monitoring import MonitoringCommands
            mc = MonitoringCommands()
            if hasattr(self.db, '_metrics_registry'):
                mc.registry = self.db._metrics_registry
            return mc.metrics_show()
        except Exception as e:
            return f"ERROR: {e}"


class HealthCommand(Command):
    def execute(self, params, client_state):
        if not client_state.get('is_admin'):
            return "ERROR: Admin only"
        
        try:
            from monitoring import MonitoringCommands
            mc = MonitoringCommands()
            if hasattr(self.db, '_health_checker'):
                mc.health_checker = self.db._health_checker
            return mc.health_check()
        except Exception as e:
            return f"ERROR: {e}"


class PrometheusCommand(Command):
    def execute(self, params, client_state):
        if not client_state.get('is_admin'):
            return "ERROR: Admin only"
        
        try:
            from monitoring import MonitoringCommands
            mc = MonitoringCommands()
            if hasattr(self.db, '_metrics_registry'):
                mc.registry = self.db._metrics_registry
            return mc.metrics_prometheus()
        except Exception as e:
            return f"ERROR: {e}"


class HelpCommand(Command):
    def execute(self, params, client_state):
        is_admin = client_state.get('is_admin', False)
        has_dist_tx = hasattr(self.db, '_dist_tx_coordinator')
        has_failover = hasattr(self.db, '_failover_manager')
        has_metrics = hasattr(self.db, '_metrics_registry')
        help_text = """Available commands:
  SHOW DATABASES           - List databases
  CREATE DATABASE <name>   - Create database
  DROP DATABASE <name>     - Delete database
  USE <database>           - Select database
  SHOW TABLES              - List tables
  
  CREATE TABLE <name> (col [PRIMARY KEY], col [INDEX], ...)
                           - Create table with indexes
  DROP TABLE <name>        - Delete table
  
  INSERT INTO <t> VALUES (v...)  - Insert row
  SELECT * FROM <t>              - Select all
  SELECT * FROM <t> ORDER BY c [ASC|DESC]
                           - Select sorted
  SELECT c FROM <t> WHERE cond ORDER BY c
                           - Select filtered
  UPDATE <t> SET c=v WHERE...    - Update
  DELETE FROM <t> WHERE cond     - Delete
  
  BEGIN                    - Start transaction
  COMMIT                   - Commit transaction
  ROLLBACK                 - Rollback transaction
  
  BACKUP DATABASE <db> TO <file>   - Backup database
  RESTORE DATABASE <db> FROM <file> - Restore database
  BACKUP TABLE <t> TO <file>      - Backup single table
  SHOW BACKUPS [path]             - List backup files
  VERIFY BACKUP <file>            - Check backup integrity
  
  HELP                     - This help
  QUIT                     - Disconnect
"""
        if has_dist_tx:
            help_text += """
Distributed Transactions:
  DIST_TX_BEGIN <ops_json>  - Begin distributed transaction
  DIST_TX_STATUS <tx_id>    - Check transaction status
  DIST_TX_LIST              - List all transactions
"""
        if has_failover:
            help_text += """
Failover & Clustering:
  FAILOVER STATUS           - Show cluster status
  FAILOVER PROPOSE <cmd>    - Propose command through Raft
"""
        if has_metrics:
            help_text += """
Monitoring:
  METRICS                   - Show system metrics
  HEALTH                    - Run health checks
  PROMETHEUS                - Export Prometheus metrics
"""
        if is_admin:
            help_text += """
Admin:
  SHOW USERS               - List users
  SHOW MASTER STATUS       - Show binlog position
  SHOW SLAVE STATUS        - Show replication status
  START SLAVE              - Start replication
  STOP SLAVE               - Stop replication
  RESET SLAVE              - Reset replication position
  CREATE REPLICATION USER <name> IDENTIFIED BY <pass>
                           - Create replication user
"""
        return help_text


class QuitCommand(Command):
    def execute(self, params, client_state):
        return "BYE"


class CommandRegistry:
    def __init__(self, db: Database, replication_client=None):
        self.db = db
        self.replication_client = replication_client
        self.commands = {
            'CREATE_DB': CreateDatabaseCommand(db),
            'DROP_DB': DropDatabaseCommand(db),
            'USE': UseDatabaseCommand(db),
            'CREATE': CreateTableCommand(db),
            'DROP': DropTableCommand(db),
            'INSERT': InsertCommand(db),
            'SELECT': SelectCommand(db),
            'UPDATE': UpdateCommand(db),
            'DELETE': DeleteCommand(db),
            'SHOW_TABLES': ShowTablesCommand(db),
            'SHOW_DATABASES': ShowDatabasesCommand(db),
            'SHOW_USERS': ShowUsersCommand(db),
            'SHOW_MASTER_STATUS': ShowMasterStatusCommand(db),
            'SHOW_SLAVE_STATUS': ShowSlaveStatusCommand(db, replication_client),
            'START_SLAVE': StartSlaveCommand(db, replication_client),
            'STOP_SLAVE': StopSlaveCommand(db, replication_client),
            'RESET_SLAVE': ResetSlaveCommand(db),
            'CREATE_REPL_USER': CreateReplicationUserCommand(db),
            'BACKUP_DB': BackupDatabaseCommand(db),
            'RESTORE_DB': RestoreDatabaseCommand(db),
            'BACKUP_TABLE': BackupTableCommand(db),
            'SHOW_BACKUPS': ListBackupsCommand(db),
            'VERIFY_BACKUP': VerifyBackupCommand(db),
            'BEGIN': BeginTransactionCommand(db),
            'COMMIT': CommitCommand(db),
            'ROLLBACK': RollbackCommand(db),
            'DIST_TX_BEGIN': DistributedTxBeginCommand(db),
            'DIST_TX_STATUS': DistributedTxStatusCommand(db),
            'DIST_TX_LIST': DistributedTxListCommand(db),
            'FAILOVER_STATUS': FailoverStatusCommand(db),
            'FAILOVER_PROPOSE': FailoverProposeCommand(db),
            'METRICS': MetricsCommand(db),
            'HEALTH': HealthCommand(db),
            'PROMETHEUS': PrometheusCommand(db),
            'HELP': HelpCommand(db),
            'QUIT': QuitCommand(db),
        }
    
    def execute(self, cmd_type: str, params: Dict, client_state: Dict) -> str:
        if cmd_type == 'UNKNOWN':
            return "ERROR: Unknown command"
        if cmd_type not in self.commands:
            return f"ERROR: {cmd_type} not implemented"
        return self.commands[cmd_type].execute(params, client_state)
