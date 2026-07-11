"""
Test Database Triggers for KosDB v3.4.0

Tests:
- CREATE TRIGGER parsing and execution
- BEFORE/AFTER triggers for INSERT, UPDATE, DELETE
- Row-level and statement-level triggers
- Trigger chaining and execution order
- Recursive trigger prevention
- WHEN clause conditions
- ENABLE/DISABLE trigger
- DROP TRIGGER
"""

import unittest
import sys
import os
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trigger_engine import (
    TriggerEngine, Trigger, TriggerTiming, TriggerEvent, 
    TriggerLevel, TriggerAction, TriggerExecutionContext,
    TriggerExecutionError, parse_trigger_definition
)
from parser import CommandParser


class TestTriggerEngine(unittest.TestCase):
    """Test trigger engine functionality."""
    
    def setUp(self):
        self.engine = TriggerEngine()
        self.test_table = 'test_users'
    
    def test_create_trigger_basic(self):
        """Create a basic trigger."""
        trigger = self.engine.create_trigger(
            name='trg_test',
            table=self.test_table,
            timing='BEFORE',
            event='INSERT',
            level='FOR EACH ROW',
            action_body='SELECT 1',
            action_type='SQL'
        )
        
        self.assertEqual(trigger.name, 'trg_test')
        self.assertEqual(trigger.table, self.test_table)
        self.assertEqual(trigger.timing, TriggerTiming.BEFORE)
        self.assertEqual(trigger.event, TriggerEvent.INSERT)
        self.assertEqual(trigger.level, TriggerLevel.ROW)
        self.assertTrue(trigger.enabled)
    
    def test_create_trigger_after(self):
        """Create an AFTER trigger."""
        trigger = self.engine.create_trigger(
            name='trg_audit',
            table=self.test_table,
            timing='AFTER',
            event='UPDATE',
            level='FOR EACH STATEMENT',
            action_body='INSERT INTO audit_log VALUES (1)',
            action_type='SQL'
        )
        
        self.assertEqual(trigger.timing, TriggerTiming.AFTER)
        self.assertEqual(trigger.level, TriggerLevel.STATEMENT)
    
    def test_create_duplicate_trigger(self):
        """Cannot create duplicate trigger names."""
        self.engine.create_trigger(
            name='trg_unique',
            table=self.test_table,
            timing='BEFORE',
            event='INSERT',
            level='FOR EACH ROW',
            action_body='SELECT 1',
            action_type='SQL'
        )
        
        with self.assertRaises(ValueError) as context:
            self.engine.create_trigger(
                name='trg_unique',
                table=self.test_table,
                timing='AFTER',
                event='DELETE',
                level='FOR EACH ROW',
                action_body='SELECT 2',
                action_type='SQL'
            )
        
        self.assertIn('already exists', str(context.exception))
    
    def test_drop_trigger(self):
        """Drop a trigger."""
        self.engine.create_trigger(
            name='trg_temp',
            table=self.test_table,
            timing='BEFORE',
            event='INSERT',
            level='FOR EACH ROW',
            action_body='SELECT 1',
            action_type='SQL'
        )
        
        success = self.engine.drop_trigger('trg_temp')
        self.assertTrue(success)
        
        # Should not exist anymore
        self.assertIsNone(self.engine.triggers.get('trg_temp'))
    
    def test_drop_nonexistent_trigger(self):
        """Drop non-existent trigger returns False."""
        success = self.engine.drop_trigger('nonexistent')
        self.assertFalse(success)
    
    def test_enable_disable_trigger(self):
        """Enable and disable triggers."""
        self.engine.create_trigger(
            name='trg_toggle',
            table=self.test_table,
            timing='BEFORE',
            event='INSERT',
            level='FOR EACH ROW',
            action_body='SELECT 1',
            action_type='SQL'
        )
        
        # Disable
        self.engine.disable_trigger('trg_toggle')
        self.assertFalse(self.engine.triggers['trg_toggle'].enabled)
        
        # Enable
        self.engine.enable_trigger('trg_toggle')
        self.assertTrue(self.engine.triggers['trg_toggle'].enabled)
    
    def test_get_triggers_for_table(self):
        """Get triggers matching table and event."""
        self.engine.create_trigger(
            name='trg_before_insert',
            table=self.test_table,
            timing='BEFORE',
            event='INSERT',
            level='FOR EACH ROW',
            action_body='SELECT 1',
            action_type='SQL'
        )
        
        self.engine.create_trigger(
            name='trg_after_insert',
            table=self.test_table,
            timing='AFTER',
            event='INSERT',
            level='FOR EACH ROW',
            action_body='SELECT 2',
            action_type='SQL'
        )
        
        self.engine.create_trigger(
            name='trg_before_update',
            table=self.test_table,
            timing='BEFORE',
            event='UPDATE',
            level='FOR EACH ROW',
            action_body='SELECT 3',
            action_type='SQL'
        )
        
        # Get BEFORE INSERT triggers
        triggers = self.engine.get_triggers_for_table(
            self.test_table, TriggerEvent.INSERT, TriggerTiming.BEFORE
        )
        
        self.assertEqual(len(triggers), 1)
        self.assertEqual(triggers[0].name, 'trg_before_insert')
    
    def test_trigger_execution_order(self):
        """Triggers execute in creation order."""
        execution_order = []
        
        def mock_execute(sql):
            execution_order.append(sql)
            return None
        
        engine = TriggerEngine(execute_sql_func=mock_execute)
        
        engine.create_trigger(
            name='trg_first',
            table='test',
            timing='AFTER',
            event='INSERT',
            level='FOR EACH ROW',
            action_body='SELECT 1',
            action_type='SQL'
        )
        
        engine.create_trigger(
            name='trg_second',
            table='test',
            timing='AFTER',
            event='INSERT',
            level='FOR EACH ROW',
            action_body='SELECT 2',
            action_type='SQL'
        )
        
        # Fire triggers
        from trigger_engine import TriggerEvent, TriggerTiming
        engine.fire_triggers(
            'test', TriggerEvent.INSERT, TriggerTiming.AFTER,
            new_rows=[{'id': 1}]
        )
        
        self.assertEqual(len(execution_order), 2)
        self.assertIn('SELECT 1', execution_order[0])
        self.assertIn('SELECT 2', execution_order[1])


class TestTriggerRecursionPrevention(unittest.TestCase):
    """Test recursive trigger prevention."""
    
    def test_recursion_prevention(self):
        """Prevent recursive trigger execution."""
        engine = TriggerEngine()
        
        # Create a trigger that would recursively fire itself
        # (In real scenario, this would be prevented by stack depth)
        engine.create_trigger(
            name='trg_recursive',
            table='test',
            timing='AFTER',
            event='INSERT',
            level='FOR EACH ROW',
            action_body='INSERT INTO test VALUES (1)',
            action_type='SQL'
        )
        
        # Simulate stack limit
        for i in range(20):
            if not engine._stack.push('trg_recursive'):
                break
        
        # Should have stopped before 20
        self.assertLess(i, 19)
    
    def test_max_recursion_depth(self):
        """Test max recursion depth."""
        engine = TriggerEngine()
        
        # Fill stack to max depth
        max_depth = engine._stack.max_depth
        for i in range(max_depth + 5):
            result = engine._stack.push(f'trg_{i}')
            if not result:
                break
        
        # Should have stopped at max_depth
        self.assertEqual(engine._stack.current_depth(), max_depth)


class TestTriggerParser(unittest.TestCase):
    """Test trigger SQL parsing."""
    
    def setUp(self):
        self.parser = CommandParser()
    
    def test_parse_create_trigger_basic(self):
        """Parse basic CREATE TRIGGER."""
        sql = """
            CREATE TRIGGER trg_audit
            AFTER INSERT ON users
            FOR EACH ROW
            EXECUTE FUNCTION audit_log()
        """
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'CREATE_TRIGGER')
        self.assertEqual(params['name'], 'trg_audit')
        self.assertEqual(params['timing'], 'AFTER')
        self.assertEqual(params['event'], 'INSERT')
        self.assertEqual(params['table'], 'users')
        self.assertEqual(params['level'], 'FOR_EACH_ROW')
    
    def test_parse_create_trigger_before_update(self):
        """Parse BEFORE UPDATE trigger."""
        sql = """
            CREATE TRIGGER trg_validate
            BEFORE UPDATE ON orders
            FOR EACH ROW
            WHEN (NEW.status = 'shipped')
            EXECUTE PROCEDURE validate_shipping()
        """
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'CREATE_TRIGGER')
        self.assertEqual(params['timing'], 'BEFORE')
        self.assertEqual(params['event'], 'UPDATE')
        self.assertEqual(params['table'], 'orders')
        self.assertEqual(params['when'], "NEW.status = 'shipped'")
    
    def test_parse_create_trigger_statement_level(self):
        """Parse statement-level trigger."""
        sql = """
            CREATE TRIGGER trg_log
            AFTER DELETE ON logs
            FOR EACH STATEMENT
            EXECUTE FUNCTION archive_logs()
        """
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'CREATE_TRIGGER')
        self.assertEqual(params['level'], 'FOR_EACH_STATEMENT')
    
    def test_parse_drop_trigger(self):
        """Parse DROP TRIGGER."""
        sql = "DROP TRIGGER trg_audit"
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'DROP_TRIGGER')
        self.assertEqual(params['name'], 'trg_audit')
    
    def test_parse_enable_trigger(self):
        """Parse ALTER TRIGGER ENABLE."""
        sql = "ALTER TRIGGER trg_audit ENABLE"
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'ENABLE_TRIGGER')
        self.assertEqual(params['name'], 'trg_audit')
    
    def test_parse_disable_trigger(self):
        """Parse ALTER TRIGGER DISABLE."""
        sql = "ALTER TRIGGER trg_audit DISABLE"
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'DISABLE_TRIGGER')
        self.assertEqual(params['name'], 'trg_audit')
    
    def test_parse_show_triggers(self):
        """Parse SHOW TRIGGERS."""
        sql = "SHOW TRIGGERS ON users"
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'SHOW_TRIGGERS')
        self.assertEqual(params['table'], 'users')


class TestTriggerDefinitionParser(unittest.TestCase):
    """Test parse_trigger_definition function."""
    
    def test_parse_trigger_definition(self):
        """Parse trigger definition with all components."""
        sql = """
            CREATE TRIGGER trg_complex
            BEFORE UPDATE OF name, email ON users
            FOR EACH ROW
            WHEN (OLD.name IS NULL)
            EXECUTE FUNCTION notify_change()
        """
        
        result = parse_trigger_definition(sql)
        
        self.assertEqual(result['name'], 'trg_complex')
        self.assertEqual(result['timing'], 'BEFORE')
        self.assertEqual(result['event'], 'UPDATE')
        self.assertEqual(result['table'], 'users')
        self.assertEqual(result['columns'], 'name, email')
        self.assertEqual(result['level'], 'FOR EACH ROW')
        self.assertEqual(result['when'], 'OLD.name IS NULL')
        self.assertIn('notify_change', result['action_body'])


class TestTriggerExecutionContext(unittest.TestCase):
    """Test TriggerExecutionContext."""
    
    def test_context_creation(self):
        """Create execution context."""
        trigger = Trigger(
            name='test',
            table='users',
            timing=TriggerTiming.BEFORE,
            event=TriggerEvent.UPDATE,
            level=TriggerLevel.ROW,
            action=TriggerAction('SQL', 'SELECT 1')
        )
        
        old_row = {'id': 1, 'name': 'Alice'}
        new_row = {'id': 1, 'name': 'Bob'}
        
        context = TriggerExecutionContext(
            trigger=trigger,
            table_name='users',
            operation='UPDATE',
            old_row=old_row,
            new_row=new_row
        )
        
        self.assertEqual(context.get_old('name'), 'Alice')
        self.assertEqual(context.get_new('name'), 'Bob')
    
    def test_modify_new_in_before_trigger(self):
        """Can modify NEW in BEFORE trigger."""
        trigger = Trigger(
            name='test',
            table='users',
            timing=TriggerTiming.BEFORE,
            event=TriggerEvent.INSERT,
            level=TriggerLevel.ROW,
            action=TriggerAction('SQL', 'SELECT 1')
        )
        
        context = TriggerExecutionContext(
            trigger=trigger,
            table_name='users',
            operation='INSERT',
            new_row={'id': 1, 'name': 'Alice'}
        )
        
        context.set_new('name', 'Modified')
        self.assertEqual(context.get_new('name'), 'Modified')
    
    def test_cannot_modify_in_after_trigger(self):
        """Cannot modify NEW in AFTER trigger."""
        trigger = Trigger(
            name='test',
            table='users',
            timing=TriggerTiming.AFTER,
            event=TriggerEvent.INSERT,
            level=TriggerLevel.ROW,
            action=TriggerAction('SQL', 'SELECT 1')
        )
        
        context = TriggerExecutionContext(
            trigger=trigger,
            table_name='users',
            operation='INSERT',
            new_row={'id': 1, 'name': 'Alice'}
        )
        
        with self.assertRaises(ValueError):
            context.set_new('name', 'Modified')


class TestTriggerStatistics(unittest.TestCase):
    """Test trigger statistics."""
    
    def test_stats_tracking(self):
        """Track trigger execution statistics."""
        engine = TriggerEngine()
        
        # Create trigger
        engine.create_trigger(
            name='trg_stats',
            table='test',
            timing='AFTER',
            event='INSERT',
            level='FOR EACH ROW',
            action_body='SELECT 1',
            action_type='SQL'
        )
        
        # Check initial stats
        stats = engine.get_stats()
        self.assertEqual(stats['total_triggers'], 1)
        self.assertEqual(stats['triggers_fired'], 0)
        
        # Fire trigger
        from trigger_engine import TriggerEvent, TriggerTiming
        engine.fire_triggers(
            'test', TriggerEvent.INSERT, TriggerTiming.AFTER,
            new_rows=[{'id': 1}]
        )
        
        # Check updated stats
        stats = engine.get_stats()
        self.assertEqual(stats['triggers_fired'], 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
