"""
Database Event Scheduler for KosDB v3.4.0

Provides automated task scheduling with:
- Cron-like recurring schedules (minute, hour, day, month, weekday)
- One-time scheduled events
- Event history tracking and logging
- Failure handling with retry logic
- Event status management (ENABLED/DISABLED)
- Thread-safe execution

SQL Interface:
    -- Create recurring event (runs every day at 2 AM)
    CREATE EVENT daily_cleanup
        ON SCHEDULE EVERY 1 DAY
        STARTS CURRENT_TIMESTAMP + INTERVAL 1 HOUR
        DO
        DELETE FROM logs WHERE created_at < DATE_SUB(NOW(), INTERVAL 30 DAYS);
    
    -- Create one-time event
    CREATE EVENT one_time_backup
        ON SCHEDULE AT '2024-12-25 02:00:00'
        DO
        CALL backup_database();
    
    -- Alter event
    ALTER EVENT daily_cleanup
        ON SCHEDULE EVERY 2 DAY;
    
    -- Enable/disable event
    ALTER EVENT daily_cleanup DISABLE;
    ALTER EVENT daily_cleanup ENABLE;
    
    -- Drop event
    DROP EVENT daily_cleanup;
    
    -- Show events
    SHOW EVENTS;
    SHOW EVENT STATUS LIKE 'daily%';
"""

import re
import time
import threading
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum, auto
import heapq

# Setup logging
logger = logging.getLogger(__name__)


class EventStatus(Enum):
    """Status of a scheduled event."""
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"


class EventType(Enum):
    """Type of scheduled event."""
    RECURRING = "RECURRING"
    ONE_TIME = "ONE_TIME"


class EventExecutionStatus(Enum):
    """Execution status of an event instance."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


@dataclass
class EventHistoryEntry:
    """History entry for event execution."""
    event_name: str
    execution_time: float
    status: EventExecutionStatus
    duration_ms: float = 0.0
    error_message: Optional[str] = None
    retry_count: int = 0


@dataclass
class ScheduledEvent:
    """Represents a scheduled database event."""
    name: str
    event_type: EventType
    schedule: Dict[str, Any]  # Cron expression or one-time timestamp
    action: str               # SQL to execute
    status: EventStatus = EventStatus.ENABLED
    created_at: float = field(default_factory=time.time)
    last_executed: Optional[float] = None
    next_execution: Optional[float] = None
    execution_count: int = 0
    failure_count: int = 0
    max_retries: int = 3
    retry_interval: int = 60  # seconds
    enabled_until: Optional[float] = None  # Optional expiration
    comment: Optional[str] = None
    
    def __post_init__(self):
        if self.next_execution is None and self.status == EventStatus.ENABLED:
            self.next_execution = self._calculate_next_execution()
    
    def _calculate_next_execution(self) -> Optional[float]:
        """Calculate next execution time based on schedule."""
        if self.event_type == EventType.ONE_TIME:
            return self.schedule.get('at')
        
        elif self.event_type == EventType.RECURRING:
            # Calculate based on cron-like expression
            cron = self.schedule.get('cron', {})
            if not cron:
                return None
            
            now = datetime.now()
            next_time = self._next_cron_execution(cron, now)
            return next_time.timestamp() if next_time else None
        
        return None
    
    def _next_cron_execution(self, cron: Dict, after: datetime) -> Optional[datetime]:
        """
        Calculate next execution time from cron expression.
        
        Supports: minute, hour, day, month, weekday
        """
        minute = cron.get('minute', '*')
        hour = cron.get('hour', '*')
        day = cron.get('day', '*')
        month = cron.get('month', '*')
        weekday = cron.get('weekday', '*')
        
        # Start from next minute
        current = after + timedelta(minutes=1)
        current = current.replace(second=0, microsecond=0)
        
        # Search for next valid time (max 4 years to prevent infinite loop)
        max_iterations = 366 * 4 * 24 * 60  # 4 years in minutes
        for _ in range(max_iterations):
            if self._matches_cron(current, minute, hour, day, month, weekday):
                return current
            current += timedelta(minutes=1)
        
        return None
    
    def _matches_cron(self, dt: datetime, minute, hour, day, month, weekday) -> bool:
        """Check if datetime matches cron expression."""
        if minute != '*' and dt.minute != int(minute):
            return False
        if hour != '*' and dt.hour != int(hour):
            return False
        if day != '*' and dt.day != int(day):
            return False
        if month != '*' and dt.month != int(month):
            return False
        if weekday != '*' and dt.weekday() != int(weekday):
            return False
        return True
    
    def should_execute(self) -> bool:
        """Check if event should execute now."""
        if self.status != EventStatus.ENABLED:
            return False
        
        if self.enabled_until and time.time() > self.enabled_until:
            return False
        
        if self.next_execution is None:
            return False
        
        return time.time() >= self.next_execution
    
    def mark_executed(self):
        """Mark event as executed and calculate next execution."""
        self.last_executed = time.time()
        self.execution_count += 1
        
        if self.event_type == EventType.ONE_TIME:
            self.status = EventStatus.DISABLED
            self.next_execution = None
        else:
            self.next_execution = self._calculate_next_execution()
    
    def mark_failed(self):
        """Mark event execution as failed."""
        self.failure_count += 1


class EventScheduler:
    """
    Main event scheduler for KosDB.
    Manages scheduled events and their execution.
    """
    
    def __init__(self, execute_sql_func: Optional[Callable] = None):
        self.events: Dict[str, ScheduledEvent] = {}
        self.history: List[EventHistoryEntry] = []
        self._execute_sql = execute_sql_func or self._default_execute_sql
        self._lock = threading.RLock()
        self._scheduler_thread: Optional[threading.Thread] = None
        self._running = False
        self._check_interval = 1.0  # seconds
        
        # Statistics
        self.stats = {
            'events_created': 0,
            'events_dropped': 0,
            'events_executed': 0,
            'events_failed': 0,
            'total_executions': 0
        }
    
    def start(self):
        """Start the scheduler thread."""
        with self._lock:
            if self._running:
                return
            
            self._running = True
            self._scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
            self._scheduler_thread.start()
            logger.info("Event scheduler started")
    
    def stop(self):
        """Stop the scheduler thread."""
        with self._lock:
            self._running = False
        
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5.0)
            logger.info("Event scheduler stopped")
    
    def _scheduler_loop(self):
        """Main scheduler loop."""
        while self._running:
            try:
                self._check_and_execute_events()
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
            
            time.sleep(self._check_interval)
    
    def _check_and_execute_events(self):
        """Check for due events and execute them."""
        with self._lock:
            events_to_execute = [
                event for event in self.events.values()
                if event.should_execute()
            ]
        
        for event in events_to_execute:
            self._execute_event(event)
    
    def _execute_event(self, event: ScheduledEvent):
        """Execute a scheduled event."""
        history_entry = EventHistoryEntry(
            event_name=event.name,
            execution_time=time.time(),
            status=EventExecutionStatus.RUNNING
        )
        
        start_time = time.time()
        retry_count = 0
        success = False
        
        while retry_count <= event.max_retries and not success:
            try:
                # Execute the event action
                self._execute_sql(event.action)
                
                success = True
                history_entry.status = EventExecutionStatus.SUCCESS
                
            except Exception as e:
                retry_count += 1
                error_msg = str(e)
                
                if retry_count <= event.max_retries:
                    logger.warning(f"Event {event.name} failed (attempt {retry_count}), retrying...")
                    history_entry.status = EventExecutionStatus.RETRYING
                    time.sleep(event.retry_interval)
                else:
                    logger.error(f"Event {event.name} failed after {retry_count} retries: {error_msg}")
                    event.mark_failed()
                    self.stats['events_failed'] += 1
                    history_entry.status = EventExecutionStatus.FAILED
                    history_entry.error_message = error_msg
        
        history_entry.duration_ms = (time.time() - start_time) * 1000
        history_entry.retry_count = retry_count - 1
        
        # Update event
        if success:
            event.mark_executed()
            self.stats['events_executed'] += 1
        
        self.stats['total_executions'] += 1
        
        # Add to history
        with self._lock:
            self.history.append(history_entry)
            # Keep only last 10000 entries
            if len(self.history) > 10000:
                self.history = self.history[-10000:]
    
    def _default_execute_sql(self, sql: str) -> Any:
        """Default SQL execution function."""
        logger.info(f"Executing: {sql[:100]}...")
        return None
    
    def create_event(self,
                     name: str,
                     schedule_type: str,
                     schedule_expr: Dict[str, Any],
                     action: str,
                     status: str = "ENABLED",
                     comment: Optional[str] = None) -> ScheduledEvent:
        """
        Create a new scheduled event.
        
        Args:
            name: Event name
            schedule_type: 'RECURRING' or 'ONE_TIME'
            schedule_expr: Schedule expression (cron dict or timestamp)
            action: SQL to execute
            status: 'ENABLED' or 'DISABLED'
            comment: Optional comment
        
        Returns:
            Created ScheduledEvent
        """
        with self._lock:
            if name in self.events:
                raise ValueError(f"Event '{name}' already exists")
            
            event_type = EventType(schedule_type.upper())
            event_status = EventStatus(status.upper())
            
            event = ScheduledEvent(
                name=name,
                event_type=event_type,
                schedule=schedule_expr,
                action=action,
                status=event_status,
                comment=comment
            )
            
            self.events[name] = event
            self.stats['events_created'] += 1
            
            logger.info(f"Created {schedule_type} event '{name}'")
            
            return event
    
    def alter_event(self,
                    name: str,
                    new_schedule: Optional[Dict[str, Any]] = None,
                    new_action: Optional[str] = None,
                    new_status: Optional[str] = None,
                    new_comment: Optional[str] = None) -> ScheduledEvent:
        """Alter an existing event."""
        with self._lock:
            if name not in self.events:
                raise ValueError(f"Event '{name}' does not exist")
            
            event = self.events[name]
            
            if new_schedule:
                event.schedule = new_schedule
                event.next_execution = event._calculate_next_execution()
            
            if new_action:
                event.action = new_action
            
            if new_status:
                event.status = EventStatus(new_status.upper())
                if event.status == EventStatus.ENABLED and event.next_execution is None:
                    event.next_execution = event._calculate_next_execution()
            
            if new_comment is not None:
                event.comment = new_comment
            
            logger.info(f"Altered event '{name}'")
            
            return event
    
    def drop_event(self, name: str) -> bool:
        """Drop an event."""
        with self._lock:
            if name not in self.events:
                return False
            
            del self.events[name]
            self.stats['events_dropped'] += 1
            
            logger.info(f"Dropped event '{name}'")
            
            return True
    
    def enable_event(self, name: str) -> ScheduledEvent:
        """Enable an event."""
        return self.alter_event(name, new_status="ENABLED")
    
    def disable_event(self, name: str) -> ScheduledEvent:
        """Disable an event."""
        return self.alter_event(name, new_status="DISABLED")
    
    def get_event(self, name: str) -> Optional[ScheduledEvent]:
        """Get event by name."""
        return self.events.get(name)
    
    def list_events(self, pattern: Optional[str] = None, 
                    status: Optional[str] = None) -> List[ScheduledEvent]:
        """
        List events, optionally filtered by pattern or status.
        
        Args:
            pattern: Optional name pattern (SQL LIKE)
            status: Optional status filter
        """
        with self._lock:
            events = list(self.events.values())
            
            if pattern:
                import fnmatch
                events = [e for e in events if fnmatch.fnmatch(e.name, pattern)]
            
            if status:
                events = [e for e in events if e.status.value == status.upper()]
            
            return events
    
    def get_event_history(self, 
                          event_name: Optional[str] = None,
                          limit: int = 100) -> List[EventHistoryEntry]:
        """
        Get event execution history.
        
        Args:
            event_name: Filter by event name
            limit: Maximum number of entries
        
        Returns:
            List of history entries
        """
        with self._lock:
            history = self.history
            
            if event_name:
                history = [h for h in history if h.event_name == event_name]
            
            return history[-limit:]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics."""
        with self._lock:
            return {
                **self.stats,
                'active_events': len([e for e in self.events.values() 
                                     if e.status == EventStatus.ENABLED]),
                'total_events': len(self.events),
                'history_entries': len(self.history)
            }


def parse_create_event(sql: str) -> Dict[str, Any]:
    """
    Parse CREATE EVENT statement.
    
    Returns:
        Dictionary with event components
    """
    # Match CREATE EVENT name ON SCHEDULE ...
    pattern = re.compile(
        r'CREATE\s+EVENT\s+(?P<name>\w+)\s+'
        r'ON\s+SCHEDULE\s+'
        r'(?:(?P<recurring>EVERY\s+(?P<interval>\d+)\s+(?P<unit>\w+))'
        r'|(?P<at>AT\s+\'?([^\'\']+)\'?))'
        r'(?:\s+STARTS\s+\'?([^\'\']+)\'?)?'
        r'(?:\s+ENDS\s+\'?([^\'\']+)\'?)?'
        r'(?:\s+ON\s+COMPLETION\s+(?P<completion>PRESERVE|DELETE))?'
        r'(?:\s+(?P<status>ENABLED|DISABLED))?'
        r'\s+DO\s+(?P<action>.+)',
        re.IGNORECASE | re.DOTALL
    )
    
    match = pattern.match(sql.strip())
    if not match:
        raise ValueError("Invalid CREATE EVENT syntax")
    
    result = match.groupdict()
    
    # Determine schedule type
    if result.get('recurring'):
        schedule_type = 'RECURRING'
        
        # Parse interval
        interval = int(result['interval'])
        unit = result['unit'].upper()
        
        # Convert to cron-like expression
        if unit in ('MINUTE', 'MINUTES'):
            schedule_expr = {'cron': {'minute': f'*/{interval}'}}
        elif unit in ('HOUR', 'HOURS'):
            schedule_expr = {'cron': {'hour': f'*/{interval}'}}
        elif unit in ('DAY', 'DAYS'):
            schedule_expr = {'cron': {'hour': '0', 'minute': '0'}}
        else:
            schedule_expr = {'cron': {}}
        
    elif result.get('at'):
        schedule_type = 'ONE_TIME'
        
        # Parse timestamp
        at_str = result['at'].strip().strip("'\"")
        try:
            at_time = datetime.fromisoformat(at_str)
            schedule_expr = {'at': at_time.timestamp()}
        except ValueError:
            # Try relative time
            schedule_expr = {'at': time.time() + 3600}  # Default to 1 hour
    else:
        raise ValueError("Schedule must specify EVERY or AT")
    
    result['schedule_type'] = schedule_type
    result['schedule_expr'] = schedule_expr
    
    return result


def parse_alter_event(sql: str) -> Dict[str, Any]:
    """Parse ALTER EVENT statement."""
    pattern = re.compile(
        r'ALTER\s+EVENT\s+(?P<name>\w+)'
        r'(?:\s+RENAME\s+TO\s+(?P<new_name>\w+))?'
        r'(?:\s+ON\s+SCHEDULE\s+(.+))?'
        r'(?:\s+(?P<status>ENABLED|DISABLED))?'
        r'(?:\s+COMMENT\s+\'([^\']+)\')?',
        re.IGNORECASE | re.DOTALL
    )
    
    match = pattern.match(sql.strip())
    if not match:
        raise ValueError("Invalid ALTER EVENT syntax")
    
    return match.groupdict()


def parse_drop_event(sql: str) -> Dict[str, Any]:
    """Parse DROP EVENT statement."""
    pattern = re.compile(
        r'DROP\s+EVENT\s+(?P<name>\w+)'
        r'(?:\s+(?P<if_exists>IF\s+EXISTS))?',
        re.IGNORECASE
    )
    
    match = pattern.match(sql.strip())
    if not match:
        raise ValueError("Invalid DROP EVENT syntax")
    
    return match.groupdict()


# Example usage
if __name__ == '__main__':
    scheduler = EventScheduler()
    
    # Create a recurring event
    event = scheduler.create_event(
        name='daily_cleanup',
        schedule_type='RECURRING',
        schedule_expr={'cron': {'hour': '2', 'minute': '0'}},
        action='DELETE FROM logs WHERE created_at < NOW() - INTERVAL 30 DAY',
        status='ENABLED',
        comment='Clean up old logs daily at 2 AM'
    )
    
    print(f"Created event: {event.name}")
    print(f"Next execution: {datetime.fromtimestamp(event.next_execution) if event.next_execution else 'N/A'}")
    
    # Create a one-time event
    one_time = scheduler.create_event(
        name='one_time_backup',
        schedule_type='ONE_TIME',
        schedule_expr={'at': time.time() + 3600},  # 1 hour from now
        action='CALL backup_database()',
        status='ENABLED'
    )
    
    print(f"Created one-time event: {one_time.name}")
    
    # Show stats
    print(f"Scheduler stats: {scheduler.get_stats()}")
