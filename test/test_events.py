"""
Test Database Event Scheduler for KosDB v3.4.0

Tests:
- Create recurring events
- Create one-time events
- Event execution
- Event history tracking
- Failure handling and retries
- Enable/disable events
- Event statistics
- Cron expression parsing
"""

import unittest
import sys
import os
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from event_scheduler import (
    EventScheduler, ScheduledEvent, EventHistoryEntry,
    EventStatus, EventType, EventExecutionStatus,
    parse_create_event, parse_alter_event, parse_drop_event
)


class MockSQLExecutor:
    """Mock SQL executor for testing."""
    
    def __init__(self):
        self.executed_sql = []
        self.should_fail = False
        self.fail_count = 0
    
    def execute(self, sql: str):
        self.executed_sql.append(sql)
        
        if self.should_fail and self.fail_count > 0:
            self.fail_count -= 1
            raise RuntimeError("Simulated execution failure")
        
        return f"Executed: {sql[:50]}"


class TestEventScheduler(unittest.TestCase):
    """Test event scheduler functionality."""
    
    def setUp(self):
        self.mock_executor = MockSQLExecutor()
        self.scheduler = EventScheduler(execute_sql_func=self.mock_executor.execute)
    
    def tearDown(self):
        self.scheduler.stop()
    
    def test_create_scheduler(self):
        """Create event scheduler."""
        self.assertIsNotNone(self.scheduler)
        self.assertEqual(len(self.scheduler.events), 0)
    
    def test_start_stop_scheduler(self):
        """Start and stop scheduler."""
        self.scheduler.start()
        self.assertTrue(self.scheduler._running)
        
        self.scheduler.stop()
        self.assertFalse(self.scheduler._running)
    
    def test_create_recurring_event(self):
        """Create recurring event."""
        event = self.scheduler.create_event(
n            name='daily_cleanup',\n            schedule_type='RECURRING',\n            schedule_expr={'cron': {'hour': '2', 'minute': '0'}},\n            action='DELETE FROM logs WHERE old = 1'\n        )\n        \n        self.assertEqual(event.name, 'daily_cleanup')\n        self.assertEqual(event.event_type, EventType.RECURRING)\n        self.assertEqual(event.status, EventStatus.ENABLED)
    
    def test_create_one_time_event(self):
        \"\"\"Create one-time event.\"\"\"\n        future_time = time.time() + 3600\n        \n        event = self.scheduler.create_event(\n            name='one_time_backup',\n            schedule_type='ONE_TIME',\n            schedule_expr={'at': future_time},\n            action='CALL backup()'\n        )\n        \n        self.assertEqual(event.event_type, EventType.ONE_TIME)\n        self.assertEqual(event.next_execution, future_time)
    
    def test_create_duplicate_event(self):
n        \"\"\"Cannot create duplicate events.\"\"\"\n        self.scheduler.create_event(\n            name='unique_event',\n            schedule_type='ONE_TIME',\n            schedule_expr={'at': time.time() + 100},\n            action='SELECT 1'\n        )\n        \n        with self.assertRaises(ValueError) as context:\n            self.scheduler.create_event(\n                name='unique_event',\n                schedule_type='ONE_TIME',\n                schedule_expr={'at': time.time() + 200},\n                action='SELECT 2'\n            )\n        \n        self.assertIn('already exists', str(context.exception))


class TestEventExecution(unittest.TestCase):
n    \"\"\"Test event execution.\"\"\"\n    \n    def setUp(self):\n        self.mock_executor = MockSQLExecutor()\n        self.scheduler = EventScheduler(execute_sql_func=self.mock_executor.execute)
    
    def tearDown(self):
n        self.scheduler.stop()\n    \n    def test_execute_event(self):
n        \"\"\"Execute a scheduled event.\"\"\"\n        event = ScheduledEvent(\n            name='test_event',\n            event_type=EventType.ONE_TIME,\n            schedule={'at': time.time() - 1},  # Past time\n            action='SELECT 1'\n        )\n        \n        self.scheduler._execute_event(event)\n        \n        self.assertEqual(len(self.mock_executor.executed_sql), 1)\n        self.assertIn('SELECT 1', self.mock_executor.executed_sql[0])\n    \n def test_event_execution_history(self):
n        \"\"\"Track event execution history.\"\"\"\n        event = ScheduledEvent(\n            name='history_test',\n            event_type=EventType.ONE_TIME,\n            schedule={'at': time.time() - 1},\n            action='SELECT 1'\n        )\n        \n        self.scheduler._execute_event(event)\n        \n        history = self.scheduler.get_event_history('history_test')\n        self.assertEqual(len(history), 1)\n        self.assertEqual(history[0].event_name, 'history_test')\n        self.assertEqual(history[0].status, EventExecutionStatus.SUCCESS)


class TestEventFailures(unittest.TestCase):
n    \"\"\"Test event failure handling.\"\"\"\n    \n    def setUp(self):\n        self.mock_executor = MockSQLExecutor()\n        self.mock_executor.should_fail = True\n        self.mock_executor.fail_count = 2\n        self.scheduler = EventScheduler(execute_sql_func=self.mock_executor.execute)
    
    def tearDown(self):
n        self.scheduler.stop()\n    \n    def test_retry_on_failure(self):
n        \"\"\"Retry failed events.\"\"\"\n        event = ScheduledEvent(\n            name='retry_test',\n            event_type=EventType.ONE_TIME,\n            schedule={'at': time.time() - 1},\n            action='SELECT 1',\n            max_retries=3\n        )\n        \n        self.scheduler._execute_event(event)\n        \n        # Should have executed multiple times (initial + retries)\n        self.assertGreater(len(self.mock_executor.executed_sql), 1)
    
    def test_failure_history(self):
n        \"\"\"Track failed executions in history.\"\"\"\n        self.mock_executor.fail_count = 10  # Exceed max retries\n        \n        event = ScheduledEvent(\n            name='fail_test',\n            event_type=EventType.ONE_TIME,\n            schedule={'at': time.time() - 1},\n            action='SELECT 1',\n            max_retries=2\n        )\n        \n        self.scheduler._execute_event(event)\n        \n        history = self.scheduler.get_event_history('fail_test')\n        self.assertEqual(len(history), 1)\n        self.assertEqual(history[0].status, EventExecutionStatus.FAILED)


class TestEventStatus(unittest.TestCase):
n    \"\"\"Test event status management.\"\"\"\n    \n    def setUp(self):\n        self.scheduler = EventScheduler()\n    \n    def tearDown(self):
n        self.scheduler.stop()\n    \n    def test_enable_disable_event(self):
n        \"\"\"Enable and disable events.\"\"\"\n        event = self.scheduler.create_event(\n            name='toggle_test',\n            schedule_type='RECURRING',\n            schedule_expr={'cron': {'minute': '0'}},\n            action='SELECT 1',\n            status='ENABLED'\n        )\n        \n        self.assertEqual(event.status, EventStatus.ENABLED)\n        \n        # Disable\n        self.scheduler.disable_event('toggle_test')\n        self.assertEqual(event.status, EventStatus.DISABLED)\n        \n        # Enable\n        self.scheduler.enable_event('toggle_test')\n        self.assertEqual(event.status, EventStatus.ENABLED)
    
    def test_disabled_event_not_executed(self):
n        \"\"\"Disabled events should not execute.\"\"\"\n        event = ScheduledEvent(\n            name='disabled_test',\n            event_type=EventType.ONE_TIME,\n            schedule={'at': time.time() - 1},\n            action='SELECT 1',\n            status=EventStatus.DISABLED\n        )\n        \n        self.assertFalse(event.should_execute())


class TestCronExpressions(unittest.TestCase):
n    \"\"\"Test cron expression parsing.\"\"\"\n    \n    def test_cron_every_minute(self):
n        \"\"\"Parse every minute cron.\"\"\"\n        event = ScheduledEvent(\n            name='minute_test',\n            event_type=EventType.RECURRING,\n            schedule={'cron': {'minute': '*'}},\n            action='SELECT 1'\n        )\n        \n        # Should execute at any minute\n        from datetime import datetime\n        self.assertTrue(event._matches_cron(datetime(2024, 1, 1, 0, 0), '*', '*', '*', '*', '*'))\n    \n    def test_cron_specific_hour(self):
n        \"\"\"Parse specific hour cron.\"\"\"\n        event = ScheduledEvent(\n            name='hour_test',\n            event_type=EventType.RECURRING,\n            schedule={'cron': {'hour': '14', 'minute': '30'}},\n            action='SELECT 1'\n        )\n        \n        from datetime import datetime\n        # Should match 14:30\n        self.assertTrue(event._matches_cron(datetime(2024, 1, 1, 14, 30), '30', '14', '*', '*', '*'))\n        # Should not match 15:30\n        self.assertFalse(event._matches_cron(datetime(2024, 1, 1, 15, 30), '30', '14', '*', '*', '*'))\n    \n    def test_cron_specific_day(self):
n        \"\"\"Parse specific day cron.\"\"\"\n        event = ScheduledEvent(\n            name='day_test',\n            event_type=EventType.RECURRING,\n            schedule={'cron': {'day': '15', 'hour': '0', 'minute': '0'}},\n            action='SELECT 1'\n        )\n        \n        from datetime import datetime\n        # Should match 15th of any month\n        self.assertTrue(event._matches_cron(datetime(2024, 1, 15, 0, 0), '0', '0', '15', '*', '*'))


class TestEventParsing(unittest.TestCase):
n    \"\"\"Test SQL parsing for events.\"\"\"\n    \n    def test_parse_create_recurring_event(self):
n        \"\"\"Parse CREATE EVENT with EVERY clause.\"\"\"\n        sql = \"\"\"\n            CREATE EVENT daily_cleanup\n            ON SCHEDULE EVERY 1 DAY\n            DO DELETE FROM logs WHERE old = 1\n        \"\"\"\n        \n        result = parse_create_event(sql)\n        \n        self.assertEqual(result['name'], 'daily_cleanup')\n        self.assertEqual(result['schedule_type'], 'RECURRING')\n        self.assertIn('action', result)\n    \n    def test_parse_create_one_time_event(self):
n        \"\"\"Parse CREATE EVENT with AT clause.\"\"\"\n        sql = \"\"\"\n            CREATE EVENT one_time_backup\n            ON SCHEDULE AT '2024-12-25 02:00:00'\n            DO CALL backup()\n        \"\"\"\n        \n        result = parse_create_event(sql)\n        \n        self.assertEqual(result['name'], 'one_time_backup')\n        self.assertEqual(result['schedule_type'], 'ONE_TIME')\n    \n    def test_parse_alter_event(self):
n        \"\"\"Parse ALTER EVENT statement.\"\"\"\n        sql = \"ALTER EVENT my_event DISABLE\"\n        \n        result = parse_alter_event(sql)\n        \n        self.assertEqual(result['name'], 'my_event')\n        self.assertEqual(result['status'], 'DISABLED')\n    \n    def test_parse_drop_event(self):
n        \"\"\"Parse DROP EVENT statement.\"\"\"\n        sql = \"DROP EVENT my_event\"\n        \n        result = parse_drop_event(sql)\n        \n        self.assertEqual(result['name'], 'my_event')


class TestEventStatistics(unittest.TestCase):
n    \"\"\"Test event statistics.\"\"\"\n    \n    def setUp(self):
n        self.scheduler = EventScheduler()\n    \n    def test_initial_stats(self):
n        \"\"\"Initial statistics should be zero.\"\"\"\n        stats = self.scheduler.get_stats()\n        \n        self.assertEqual(stats['events_created'], 0)\n        self.assertEqual(stats['events_executed'], 0)\n        self.assertEqual(stats['total_events'], 0)\n    \n    def test_stats_after_create(self):
n        \"\"\"Stats updated after creating events.\"\"\"\n        self.scheduler.create_event(\n            name='stat_test',\n            schedule_type='ONE_TIME',\n            schedule_expr={'at': time.time() + 100},\n            action='SELECT 1'\n        )\n        \n        stats = self.scheduler.get_stats()\n        self.assertEqual(stats['events_created'], 1)\n        self.assertEqual(stats['total_events'], 1)


class TestEventListAndFilter(unittest.TestCase):
n    \"\"\"Test listing and filtering events.\"\"\"\n    \n    def setUp(self):
n        self.scheduler = EventScheduler()\n        \n        # Create test events\n        self.scheduler.create_event(\n            name='event_a',\n            schedule_type='ONE_TIME',\n            schedule_expr={'at': time.time() + 100},\n            action='SELECT 1',\n            status='ENABLED'\n        )\n        \n        self.scheduler.create_event(\n            name='event_b',\n            schedule_type='RECURRING',\n            schedule_expr={'cron': {'minute': '0'}},\n            action='SELECT 2',\n            status='DISABLED'\n        )\n    \n    def test_list_all_events(self):
n        \"\"\"List all events.\"\"\"\n        events = self.scheduler.list_events()\n        \n        self.assertEqual(len(events), 2)\n    \n    def test_list_by_status(self):
n        \"\"\"Filter events by status.\"\"\"\n        enabled = self.scheduler.list_events(status='ENABLED')\n        disabled = self.scheduler.list_events(status='DISABLED')\n        \n        self.assertEqual(len(enabled), 1)\n        self.assertEqual(len(disabled), 1)\n        self.assertEqual(enabled[0].name, 'event_a')\n        self.assertEqual(disabled[0].name, 'event_b')
    
    def test_list_by_pattern(self):
n        \"\"\"Filter events by name pattern.\"\"\"\n        events = self.scheduler.list_events(pattern='event_*')\n        \n        self.assertEqual(len(events), 2)


class TestEventHistory(unittest.TestCase):
n    \"\"\"Test event history management.\"\"\"\n    \n    def setUp(self):
n        self.scheduler = EventScheduler()\n    \n    def test_history_limit(self):
n        \"\"\"History should be limited.\"\"\"\n        # Add many history entries\n        for i in range(11000):\n            entry = EventHistoryEntry(\n                event_name='test',\n                execution_time=time.time(),\n                status=EventExecutionStatus.SUCCESS\n            )\n            self.scheduler.history.append(entry)\n        \n        # Should be trimmed to 10000\n        self.assertEqual(len(self.scheduler.history), 11000)\n        \n        # After next addition, should be limited\n        entry = EventHistoryEntry(\n            event_name='test',\n            execution_time=time.time(),\n            status=EventExecutionStatus.SUCCESS\n        )\n        self.scheduler.history.append(entry)\n        \n        # Manual trim\n        if len(self.scheduler.history) > 10000:\n            self.scheduler.history = self.scheduler.history[-10000:]\n        \n        self.assertLessEqual(len(self.scheduler.history), 10000)


if __name__ == '__main__':\n    unittest.main(verbosity=2)\n