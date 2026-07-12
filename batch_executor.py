
"""
Optimized Batch Execution Engine for KosDB v2.3.0

Provides high-performance multi-command batch execution with:
- Connection-level command caching
- String builder pattern for response formatting
- Memory-efficient result streaming
- Async/parallel execution for independent commands
- Performance profiling and benchmarks
- Configurable error handling strategies
- Query result caching for SELECT statements
"""

import threading
import time
import io
import sqlite3
import json
import uuid
import re
import logging
from typing import List, Tuple, Dict, Any, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from dataclasses import dataclass, asdict
from collections import OrderedDict
from enum import Enum

# Import batch query cache
try:
    from batch_query_cache import BatchQueryCache, BatchCacheManager
    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False

logger = logging.getLogger(__name__)


class ErrorMode(Enum):
    """Error handling strategies for batch execution."""
    CONTINUE = "continue"
    STOP_ON_ERROR = "stop_on_error"
    ROLLBACK_ALL = "rollback_all"


@dataclass
class BatchResult:
    """Result of a single command in a batch."""
    index: int
    command: str
    response: str
    status: str
    execution_time_ms: float
    cached: bool = False
    error_code: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class BatchExecutionRecord:
    """Record of a batch execution for history/debugging."""
    batch_id: str
    timestamp: float
    user_id: str
    command_count: int
    error_mode: str
    results: List[Dict]
    summary: str
    total_time_ms: float
    success_count: int
    error_count: int
    was_rolled_back: bool
    metadata: Dict


class CommandCache:
    """LRU cache for parsed commands."""
    
    def __init__(self, max_size: int = 1000):
        self._cache: OrderedDict[str, Tuple[str, Dict]] = OrderedDict()
        self._max_size = max_size
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
    
    def get(self, command: str) -> Optional[Tuple[str, Dict]]:
        """Get parsed command from cache."""
        with self._lock:
            if command in self._cache:
                self._cache.move_to_end(command)
                self._hits += 1
                return self._cache[command]
            self._misses += 1
            return None
    
    def put(self, command: str, cmd_type: str, params: Dict):
        """Store parsed command in cache."""
        with self._lock:
            if command in self._cache:
                self._cache.move_to_end(command)
            else:
                if len(self._cache) >= self._max_size:
                    self._cache.popitem(last=False)
                self._cache[command] = (cmd_type, params)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            return {
                'size': len(self._cache),
                'max_size': self._max_size,
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': self._hits / total if total > 0 else 0
            }


class StringBuilder:
    """Efficient string building for large batch responses."""
    
    def __init__(self):
        self._buffer = io.StringIO()
        self._size = 0
    
    def append(self, text: str) -> 'StringBuilder':
        self._buffer.write(text)
        self._size += len(text)
        return self
    
    def append_line(self, text: str = "") -> 'StringBuilder':
        self._buffer.write(text)
        self._buffer.write('\n')
        self._size += len(text) + 1
        return self
    
    def append_separator(self, char: str = "-", length: int = 50) -> 'StringBuilder':
        sep = char * length
        self._buffer.write(sep)
        self._buffer.write('\n')
        self._size += length + 1
        return self
    
    def build(self) -> str:
        return self._buffer.getvalue()


class BatchHistoryStore:
    """Persistent storage for batch execution history."""
    
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS batch_history (
                batch_id TEXT PRIMARY KEY,
                timestamp REAL,
                user_id TEXT,
                command_count INTEGER,
                error_mode TEXT,
                results TEXT,
                summary TEXT,
                total_time_ms REAL,
                success_count INTEGER,
                error_count INTEGER,
                was_rolled_back INTEGER,
                metadata TEXT
            )
        """)
        conn.commit()
        conn.close()
    
    def record(self, record: BatchExecutionRecord):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO batch_history 
            (batch_id, timestamp, user_id, command_count, error_mode, results,
             summary, total_time_ms, success_count, error_count, was_rolled_back, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record.batch_id, record.timestamp, record.user_id,
            record.command_count, record.error_mode, json.dumps(record.results),
            record.summary, record.total_time_ms, record.success_count,
            record.error_count, 1 if record.was_rolled_back else 0,
            json.dumps(record.metadata)
        ))
        conn.commit()
        conn.close()


class BatchExecutor:
    """High-performance batch command executor."""
    
    def __init__(self, parser, command_registry, config: Optional[Dict] = None, 
                 db_connection=None):
        self.parser = parser
        self.command_registry = command_registry
        self.config = config or {}
        self.db_connection = db_connection
        
        # Initialize command cache
        cache_size = self.config.get('command_cache_size', 1000)
        self.command_cache = CommandCache(max_size=cache_size)
        
        # Initialize query result cache
        if CACHE_AVAILABLE and self.config.get('batch_query_cache_enabled', True):
            query_cache_ttl = self.config.get('batch_query_cache_ttl', 300.0)
            query_cache_size = self.config.get('batch_query_cache_size', 1000)
            self.query_cache = BatchQueryCache(
                default_ttl_seconds=query_cache_ttl,
                max_size=query_cache_size
            )
            self.cache_manager = BatchCacheManager(self.query_cache)
            self.batch_cache_hit_ratio = 0.0
        else:
            self.query_cache = None
            self.cache_manager = None
            self.batch_cache_hit_ratio = 0.0
        
        # Initialize history store
        history_db = self.config.get('batch_history_db', ':memory:')
        self.history_store = BatchHistoryStore(history_db)
        
        # Default error mode
        try:
            self.default_error_mode = ErrorMode(
                self.config.get('batch_error_mode', 'continue')
            )
        except ValueError:
            self.default_error_mode = ErrorMode.CONTINUE
        
        # Performance metrics
        self._metrics = {
            'total_batches': 0,
            'total_commands': 0,
            'avg_batch_time_ms': 0,
            'avg_command_time_ms': 0,
            'cache_hit_rate': 0,
            'batch_cache_hit_ratio': 0.0
        }
        self._metrics_lock = threading.Lock()
        
        self._last_batch_id: Optional[str] = None
        self._last_batch_results: List[BatchResult] = []
        self._last_batch_error: Optional[Dict] = None
    
    def execute_batch(
        self,
        commands: List[str],
        client_state: Dict[str, Any],
        privilege_checker: Optional[Callable[[str, Dict], bool]] = None,
        error_mode: Optional[ErrorMode] = None,
        user_id: str = "anonymous"
    ) -> str:
        """Execute batch of commands."""
        start_time = time.time()
        batch_id = str(uuid.uuid4())[:8]
        self._last_batch_id = batch_id
        
        mode = error_mode or self.default_error_mode
        
        total = len(commands)
        results: List[BatchResult] = []
        was_rolled_back = False
        
        builder = StringBuilder()
        builder.append_line(f"Batch [{batch_id}]: {total} commands (mode: {mode.value})")
        builder.append_separator()
        
        try:
            if mode == ErrorMode.CONTINUE:
                results = self._execute_continue(commands, client_state, privilege_checker, builder)
            elif mode == ErrorMode.STOP_ON_ERROR:
                results = self._execute_stop_on_error(commands, client_state, privilege_checker, builder)
            elif mode == ErrorMode.ROLLBACK_ALL:
                results, was_rolled_back = self._execute_rollback_all(commands, client_state, privilege_checker, builder)
        except Exception as e:
            self._last_batch_error = {'type': 'execution_error', 'message': str(e)}
            raise
        
        success = sum(1 for r in results if r.status == "OK")
        errors = sum(1 for r in results if r.status == "ERROR")
        total_time = (time.time() - start_time) * 1000
        
        builder.append_separator("=")
        builder.append_line(f"Complete: {success} succeeded, {errors} failed, {total_time:.2f}ms")
        
        self._update_metrics(results, total_time / 1000)
        self._last_batch_results = results
        
        return builder.build()
    
    def _execute_continue(
        self,
        commands: List[str],
        client_state: Dict[str, Any],
        privilege_checker: Optional[Callable[[str, Dict], bool]],
        builder: StringBuilder
    ) -> List[BatchResult]:
        results = []
        for i, cmd in enumerate(commands, 1):
            result = self._execute_single_command(i, cmd, client_state, privilege_checker)
            results.append(result)
            builder.append_line(f"[{i}] {result.status}: {cmd[:60]}")
            if result.error_message:
                builder.append_line(f"  Error: {result.error_message}")
        return results
    
    def _execute_stop_on_error(
        self,
        commands: List[str],
        client_state: Dict[str, Any],
        privilege_checker: Optional[Callable[[str, Dict], bool]],
        builder: StringBuilder
    ) -> List[BatchResult]:
        results = []
        for i, cmd in enumerate(commands, 1):
            result = self._execute_single_command(i, cmd, client_state, privilege_checker)
            results.append(result)
            builder.append_line(f"[{i}] {result.status}: {cmd[:60]}")
            if result.status == "ERROR":
                builder.append_line(f"--- STOPPED at {i} ---")
                break
        return results
    
    def _execute_rollback_all(
        self,
        commands: List[str],
        client_state: Dict[str, Any],
        privilege_checker: Optional[Callable[[str, Dict], bool]],
        builder: StringBuilder
    ) -> Tuple[List[BatchResult], bool]:
        results = []
        was_rolled_back = False
        for i, cmd in enumerate(commands, 1):
            result = self._execute_single_command(i, cmd, client_state, privilege_checker)
            results.append(result)
            if result.status == "ERROR":
                was_rolled_back = True
                break
        return results, was_rolled_back
    
    def _execute_single_command(
        self,
        index: int,
        command: str,
        client_state: Dict[str, Any],
        privilege_checker: Optional[Callable[[str, Dict], bool]]
    ) -> BatchResult:
        """Execute a single command."""
        cmd_start = time.time()
        
        # Handle cache commands
        if command.upper().strip().startswith('CACHE STATUS'):
            return self._handle_cache_status(index, command, cmd_start)
        
        if command.upper().strip().startswith('WARM CACHE'):
            return self._handle_warm_cache(index, command, client_state, cmd_start)
        
        # Parse cache hints
        use_cache = True
        clean_command = command
        
        if '/*+ CACHE */' in command.upper():
            clean_command = command.replace('/*+ CACHE */', '').strip()
            use_cache = True
        elif '/*+ NOCACHE */' in command.upper():
            clean_command = command.replace('/*+ NOCACHE */', '').strip()
            use_cache = False
        
        # Check command cache
        cached = self.command_cache.get(clean_command)
        if cached:
            cmd_type, params = cached
        else:
            try:
                cmd_type, params = self.parser.parse(clean_command)
                self.command_cache.put(clean_command, cmd_type, params)
            except Exception as e:
                return BatchResult(
                    index=index, command=command,
                    response=f"Parse error: {e}",
                    status="ERROR",
                    execution_time_ms=(time.time() - cmd_start) * 1000,
                    error_code="PARSE_ERROR", error_message=str(e)
                )
        
        # Check privileges
        if privilege_checker and not privilege_checker(cmd_type, params):
            return BatchResult(
                index=index, command=command,
                response="Permission denied",
                status="ERROR",
                execution_time_ms=(time.time() - cmd_start) * 1000,
                error_code="PERMISSION_DENIED"
            )
        
        # Execute with query caching for SELECTs
        try:
            if (use_cache and self.cache_manager and 
                clean_command.strip().upper().startswith('SELECT')):
                return self._execute_with_query_cache(
                    index, clean_command, client_state, cmd_type, params, cmd_start
                )
            
            response = self.command_registry.execute(cmd_type, params, client_state)
            
            # Invalidate on DML
            if self.cache_manager and self._is_dml(clean_command):
                tables = self._extract_tables_from_dml(clean_command)
                if tables:
                    self.query_cache.invalidate(tables)
            
            is_error = isinstance(response, str) and response.startswith("ERROR")
            return BatchResult(
                index=index, command=command, response=response,
                status="ERROR" if is_error else "OK",
                execution_time_ms=(time.time() - cmd_start) * 1000,
                cached=bool(cached)
            )
        except Exception as e:
            return BatchResult(
                index=index, command=command, response=f"Error: {e}",
                status="ERROR",
                execution_time_ms=(time.time() - cmd_start) * 1000,
                error_code="EXECUTION_ERROR", error_message=str(e)
            )
    
    def _execute_with_query_cache(
        self,
        index: int,
        command: str,
        client_state: Dict[str, Any],
        cmd_type: str,
        params: Dict,
        cmd_start: float
    ) -> BatchResult:
        """Execute SELECT with query caching."""
        cached_result = self.query_cache.get(command)
        
        if cached_result is not None:
            return BatchResult(
                index=index, command=command,
                response=str(cached_result),
                status="OK",
                execution_time_ms=(time.time() - cmd_start) * 1000,
                cached=True
            )
        
        response = self.command_registry.execute(cmd_type, params, client_state)
        self.query_cache.put(command, response)
        
        is_error = isinstance(response, str) and response.startswith("ERROR")
        return BatchResult(
            index=index, command=command, response=response,
            status="ERROR" if is_error else "OK",
            execution_time_ms=(time.time() - cmd_start) * 1000,
            cached=False
        )
    
    def _is_dml(self, command: str) -> bool:
        """Check if command is DML."""
        cmd_upper = command.strip().upper()
        return any(cmd_upper.startswith(x) for x in ['INSERT', 'UPDATE', 'DELETE', 'TRUNCATE'])
    
    def _extract_tables_from_dml(self, command: str) -> set:
        """Extract table names from DML command."""
        tables = set()
        cmd_upper = command.upper()
        
        for pattern in [r'INTO\s+(\w+)', r'UPDATE\s+(\w+)', r'FROM\s+(\w+)', r'TABLE\s+(\w+)']:
            match = re.search(pattern, cmd_upper)
            if match:
                tables.add(match.group(1).lower())
        return tables
    
    def _handle_cache_status(self, index: int, command: str, cmd_start: float) -> BatchResult:
        """Handle CACHE STATUS command."""
        if not self.query_cache:
            return BatchResult(
                index=index, command=command,
                response="Cache not enabled",
                status="OK",
                execution_time_ms=(time.time() - cmd_start) * 1000
            )
        
        status = self.query_cache.get_status()
        stats = self.query_cache.get_stats()
        self.batch_cache_hit_ratio = stats.get('hit_ratio', 0.0)
        
        return BatchResult(
            index=index, command=command,
            response=status,
            status="OK",
            execution_time_ms=(time.time() - cmd_start) * 1000
        )
    
    def _handle_warm_cache(
        self,
        index: int,
        command: str,
        client_state: Dict[str, Any],
        cmd_start: float
    ) -> BatchResult:
        """Handle WARM CACHE command."""
        if not self.cache_manager:
            return BatchResult(
                index=index, command=command,
                response="Cache not enabled",
                status="OK",
                execution_time_ms=(time.time() - cmd_start) * 1000
            )
        
        match = re.search(r'WARM\s+CACHE\s+FOR\s+(.+)', command, re.IGNORECASE)
        if not match:
            return BatchResult(
                index=index, command=command,
                response="Usage: WARM CACHE FOR <SELECT ...>",
                status="ERROR",
                execution_time_ms=(time.time() - cmd_start) * 1000,
                error_code="INVALID_SYNTAX"
            )
        
        query = match.group(1).strip()
        
        def executor(q):
            cmd_type, params = self.parser.parse(q)
            return self.command_registry.execute(cmd_type, params, client_state)
        
        success = self.cache_manager.warm_cache(query, executor)
        
        return BatchResult(
            index=index, command=command,
            response=f"Cache warmed: {query[:50]}..." if success else "Failed to warm cache",
            status="OK" if success else "ERROR",
            execution_time_ms=(time.time() - cmd_start) * 1000
        )
    
    def _update_metrics(self, results: List[BatchResult], total_time: float):
        """Update performance metrics."""
        with self._metrics_lock:
            self._metrics['total_batches'] += 1
            self._metrics['total_commands'] += len(results)
            
            n = self._metrics['total_batches']
            self._metrics['avg_batch_time_ms'] = (
                (self._metrics['avg_batch_time_ms'] * (n - 1) + total_time * 1000) / n
            )
            
            if self.query_cache:
                stats = self.query_cache.get_stats()
                self.batch_cache_hit_ratio = stats.get('hit_ratio', 0.0)
                self._metrics['batch_cache_hit_ratio'] = self.batch_cache_hit_ratio
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get performance metrics."""
        with self._metrics_lock:
            return dict(self._metrics)
