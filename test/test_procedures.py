"""
Test Stored Procedures for KosDB v3.4.0

Tests:
- CREATE PROCEDURE with parameters
- CALL statement execution
- Control flow: IF/ELSE, WHILE, FOR loops
- Variables: DECLARE, SET
- Exception handling: TRY/CATCH, RAISERROR
- Cursors
- DROP PROCEDURE
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from procedure_engine import (
    ProcedureEngine, ProcedureCompiler, Procedure, ProcedureParameter,
    ProcedureParameterMode, ExecutionContext, ProcedureExecutionError,
    parse_procedure_definition
)
from parser import CommandParser


class TestProcedureEngine(unittest.TestCase):
    """Test procedure engine functionality."""
    
    def setUp(self):
        self.engine = ProcedureEngine()
    
    def test_create_procedure_simple(self):
        """Create a simple procedure."""
        proc = self.engine.create_procedure(
            name='sp_test',
            parameters=[],
            body='RETURN 42;'
        )
        
        self.assertEqual(proc.name, 'sp_test')
        self.assertEqual(len(proc.parameters), 0)
        self.assertIn('_compiled', dir(proc))
    
    def test_create_procedure_with_params(self):
        """Create procedure with parameters."""
        params = [
            ProcedureParameter('id', ProcedureParameterMode.IN, 'INT'),
            ProcedureParameter('name', ProcedureParameterMode.IN, 'VARCHAR(100)')
        ]
        
        proc = self.engine.create_procedure(
            name='sp_with_params',
            parameters=params,
            body='RETURN @id;'
        )
        
        self.assertEqual(len(proc.parameters), 2)
        self.assertEqual(proc.parameters[0].name, 'id')
    
    def test_create_duplicate_procedure(self):
        """Cannot create duplicate procedures."""
        self.engine.create_procedure(
            name='sp_unique',
            parameters=[],
            body='RETURN 1;'
        )
        
        with self.assertRaises(ValueError) as context:
            self.engine.create_procedure(
                name='sp_unique',
                parameters=[],
                body='RETURN 2;'
            )
        
        self.assertIn('already exists', str(context.exception))
    
    def test_drop_procedure(self):
        """Drop a procedure."""
        self.engine.create_procedure(
            name='sp_temp',
            parameters=[],
            body='RETURN 1;'
        )
        
        success = self.engine.drop_procedure('sp_temp')
        self.assertTrue(success)
        self.assertNotIn('SP_TEMP', self.engine.procedures)
    
    def test_execute_procedure(self):
        """Execute a procedure."""
        self.engine.create_procedure(
            name='sp_execute',
            parameters=[],
            body='DECLARE @x INT; SET @x = 10; RETURN @x;'
        )
        
        result = self.engine.execute('sp_execute')
        self.assertEqual(result['return_value'], 10)
    
    def test_procedure_with_in_param(self):
        """Procedure with IN parameter."""
        params = [ProcedureParameter('value', ProcedureParameterMode.IN, 'INT')]
        
        self.engine.create_procedure(
            name='sp_in_param',
            parameters=params,
            body='RETURN @value * 2;'
        )
        
        result = self.engine.execute('sp_in_param', {'value': 5})
        self.assertEqual(result['return_value'], 10)


class TestProcedureControlFlow(unittest.TestCase):
    """Test control flow statements."""
    
    def setUp(self):
        self.engine = ProcedureEngine()
    
    def test_if_statement_true(self):
        """IF statement when condition is true."""
        self.engine.create_procedure(
            name='sp_if_true',
            parameters=[],
            body='''
                DECLARE @result INT;
                SET @result = 0;
                IF 1 = 1 THEN
                    SET @result = 100;
                END IF;
                RETURN @result;
            '''
        )
        
        result = self.engine.execute('sp_if_true')
        self.assertEqual(result['return_value'], 100)
    
    def test_if_statement_false(self):
        """IF statement when condition is false."""
        self.engine.create_procedure(
            name='sp_if_false',
            parameters=[],
            body='''
                DECLARE @result INT;
                SET @result = 0;
                IF 1 = 2 THEN
                    SET @result = 100;
                END IF;
                RETURN @result;
            '''
        )
        
        result = self.engine.execute('sp_if_false')
        self.assertEqual(result['return_value'], 0)
    
    def test_if_else_statement(self):
        """IF/ELSE statement."""
        self.engine.create_procedure(
            name='sp_if_else',
            parameters=[ProcedureParameter('x', ProcedureParameterMode.IN, 'INT')],
            body='''
                DECLARE @result INT;
                IF @x > 0 THEN
                    SET @result = 1;
                ELSE
                    SET @result = -1;
                END IF;
                RETURN @result;
            '''
        )
        
        result = self.engine.execute('sp_if_else', {'x': 5})
        self.assertEqual(result['return_value'], 1)
        
        result = self.engine.execute('sp_if_else', {'x': -5})
        self.assertEqual(result['return_value'], -1)
    
    def test_while_loop(self):
        """WHILE loop."""
        self.engine.create_procedure(
            name='sp_while',
            parameters=[],
            body='''
                DECLARE @i INT;
                DECLARE @sum INT;
                SET @i = 1;
                SET @sum = 0;
                WHILE @i <= 5
                BEGIN
                    SET @sum = @sum + @i;
                    SET @i = @i + 1;
                END;
                RETURN @sum;
            '''
        )
        
        result = self.engine.execute('sp_while')
        self.assertEqual(result['return_value'], 15)  # 1+2+3+4+5
    
    def test_while_break(self):
        """WHILE with BREAK."""
        self.engine.create_procedure(
            name='sp_while_break',
            parameters=[],
            body='''
                DECLARE @i INT;
                SET @i = 1;
                WHILE @i <= 10
                BEGIN
                    IF @i = 5 THEN
                        BREAK;
                    END IF;
                    SET @i = @i + 1;
                END;
                RETURN @i;
            '''
        )
        
        result = self.engine.execute('sp_while_break')
        self.assertEqual(result['return_value'], 5)


class TestProcedureVariables(unittest.TestCase):
    """Test variable handling."""
    
    def setUp(self):
        self.engine = ProcedureEngine()
    
    def test_declare_variable(self):
        """Declare and use variable."""
        self.engine.create_procedure(
            name='sp_declare',
            parameters=[],
            body='''
                DECLARE @x INT;
                SET @x = 42;
                RETURN @x;
            '''
        )
        
        result = self.engine.execute('sp_declare')
        self.assertEqual(result['return_value'], 42)
    
    def test_multiple_variables(self):
        """Multiple variables."""
        self.engine.create_procedure(
            name='sp_multi_var',
            parameters=[],
            body='''
                DECLARE @a INT;
                DECLARE @b INT;
                DECLARE @c INT;
                SET @a = 10;
                SET @b = 20;
                SET @c = @a + @b;
                RETURN @c;
            '''
        )
        
        result = self.engine.execute('sp_multi_var')
        self.assertEqual(result['return_value'], 30)
    
    def test_variable_types(self):
        """Different variable types."""
        self.engine.create_procedure(
            name='sp_types',
            parameters=[],
            body='''
                DECLARE @i INT;
                DECLARE @f FLOAT;
                DECLARE @s VARCHAR(100);
                DECLARE @b BIT;
                SET @i = 10;
                SET @f = 3.14;
                SET @s = 'hello';
                SET @b = 1;
                RETURN @i;
            '''
        )
        
        result = self.engine.execute('sp_types')
        self.assertEqual(result['return_value'], 10)


class TestProcedureExceptionHandling(unittest.TestCase):
    """Test exception handling."""
    
    def setUp(self):
        self.engine = ProcedureEngine()
    
    def test_raiserror(self):
        """RAISERROR statement."""
        self.engine.create_procedure(
            name='sp_raise',
            parameters=[],
            body="RAISERROR 'Test error', 16, 1;"
        )
        
        with self.assertRaises(ProcedureExecutionError) as context:
            self.engine.execute('sp_raise')
        
        self.assertIn('Test error', str(context.exception))
    
    def test_try_catch(self):
        """TRY...CATCH block."""
        self.engine.create_procedure(
            name='sp_try_catch',
            parameters=[],
            body='''
                DECLARE @result INT;
                SET @result = 0;
                TRY
                    SET @result = 1;
                    RAISERROR 'Error in try', 16, 1;
                    SET @result = 2;
                CATCH
                    SET @result = 100;
                END;
                RETURN @result;
            '''
        )
        
        result = self.engine.execute('sp_try_catch')
        self.assertEqual(result['return_value'], 100)
    
    def test_try_no_error(self):
        """TRY block without error."""
        self.engine.create_procedure(
            name='sp_try_ok',
            parameters=[],
            body='''
                DECLARE @result INT;
                TRY
                    SET @result = 42;
                CATCH
                    SET @result = 999;
                END;
                RETURN @result;
            '''
        )
        
        result = self.engine.execute('sp_try_ok')
        self.assertEqual(result['return_value'], 42)


class TestProcedureParser(unittest.TestCase):
    """Test procedure SQL parsing."""
    
    def setUp(self):
        self.parser = CommandParser()
    
    def test_parse_create_procedure(self):
        """Parse CREATE PROCEDURE."""
        sql = """
            CREATE PROCEDURE sp_test(IN @id INT, OUT @result INT)
            BEGIN
                SET @result = @id * 2;
                RETURN @result;
            END
        """
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'CREATE_PROCEDURE')
        self.assertEqual(params['name'], 'sp_test')
        self.assertIn('id', params['params'])
        self.assertIn('result', params['params'])
    
    def test_parse_call_procedure(self):
        """Parse CALL statement."""
        sql = "CALL sp_transfer(1, 2, 100.00)"
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'CALL')
        self.assertEqual(params['name'], 'sp_transfer')
        self.assertIn('1', params['args'])
    
    def test_parse_call_with_named_args(self):
        """Parse CALL with named arguments."""
        sql = "CALL sp_config(debug='true', timeout=30)"
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'CALL')
        self.assertIn('debug', params['args'])
    
    def test_parse_drop_procedure(self):
        """Parse DROP PROCEDURE."""
        sql = "DROP PROCEDURE sp_old"
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'DROP_PROCEDURE')
        self.assertEqual(params['name'], 'sp_old')
    
    def test_parse_show_procedures(self):
        """Parse SHOW PROCEDURES."""
        sql = "SHOW PROCEDURES"
        
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'SHOW_PROCEDURES')


class TestProcedureCompilation(unittest.TestCase):
    """Test procedure compilation."""
    
    def setUp(self):
        self.compiler = ProcedureCompiler()
    
    def test_compile_declare(self):
        """Compile DECLARE statement."""
        body = "DECLARE @x INT;"
        compiled = self.compiler.compile(body)
        
        self.assertEqual(len(compiled), 1)
        self.assertEqual(compiled[0]['type'], 'DECLARE')
        self.assertEqual(compiled[0]['name'], 'x')
    
    def test_compile_if(self):
        """Compile IF statement."""
        body = "IF 1 = 1 THEN SET @x = 1; END IF;"
        compiled = self.compiler.compile(body)
        
        self.assertEqual(compiled[0]['type'], 'IF')
        self.assertEqual(compiled[0]['condition'], '1 = 1')
    
    def test_compile_while(self):
        """Compile WHILE loop."""
        body = "WHILE @i < 10 BEGIN SET @i = @i + 1; END;"
        compiled = self.compiler.compile(body)
        
        self.assertEqual(compiled[0]['type'], 'WHILE')
    
    def test_compile_complex_procedure(self):
        """Compile complex procedure."""
        body = '''
            DECLARE @x INT;
            DECLARE @y INT;
            SET @x = 10;
            SET @y = 20;
            IF @x < @y THEN
                RETURN @y;
            ELSE
                RETURN @x;
            END IF;
        '''
        
        compiled = self.compiler.compile(body)
        self.assertGreater(len(compiled), 5)  # Multiple statements


class TestProcedureDefinitionParser(unittest.TestCase):
    """Test parse_procedure_definition function."""
    
    def test_parse_simple_procedure(self):
        """Parse simple procedure definition."""
        sql = """
            CREATE PROCEDURE sp_simple()
            BEGIN
                RETURN 1;
            END
        """
        
        result = parse_procedure_definition(sql)
        
        self.assertEqual(result['name'], 'sp_simple')
        self.assertEqual(len(result['parameters']), 0)
    
    def test_parse_procedure_with_params(self):
        """Parse procedure with parameters."""
        sql = """
            CREATE PROCEDURE sp_params(IN @id INT, OUT @name VARCHAR(100))
            BEGIN
                SELECT name INTO @name FROM users WHERE id = @id;
            END
        """
        
        result = parse_procedure_definition(sql)
        
        self.assertEqual(result['name'], 'sp_params')
        self.assertEqual(len(result['parameters']), 2)
        
        # Check first parameter
        self.assertEqual(result['parameters'][0].name, 'id')
        self.assertEqual(result['parameters'][0].mode, ProcedureParameterMode.IN)
        
        # Check second parameter
        self.assertEqual(result['parameters'][1].name, 'name')
        self.assertEqual(result['parameters'][1].mode, ProcedureParameterMode.OUT)


if __name__ == '__main__':
    unittest.main(verbosity=2)
