"""
Procedure Engine for KosDB v3.4.0

Provides stored procedure execution with:
- Control flow: IF/ELSE, WHILE, FOR loops, CASE
- Variables: Declaration, assignment, scoping
- Exception handling: TRY/CATCH, RAISERROR
- Cursors: Declaration, OPEN, FETCH, CLOSE
- Dynamic SQL: EXECUTE with string interpolation

Example:
    CREATE PROCEDURE sp_transfer_money(
        IN sender_id INT,
        IN receiver_id INT,
        IN amount DECIMAL(10,2)
    )
    BEGIN
        DECLARE balance DECIMAL(10,2);
        
        -- Check sender balance
        SELECT balance INTO balance FROM accounts WHERE id = sender_id;
        
        IF balance < amount THEN
            RAISERROR('Insufficient funds', 16, 1);
        ELSE
            BEGIN TRANSACTION;
            
            UPDATE accounts SET balance = balance - amount WHERE id = sender_id;
            UPDATE accounts SET balance = balance + amount WHERE id = receiver_id;
            
            COMMIT;
        END IF;
    END;
"""

import re
import ast
import time
import threading
from typing import Dict, Any, List, Optional, Callable, Union, Tuple
from dataclasses import dataclass, field
from enum import Enum, auto
from collections import defaultdict


class ProcedureParameterMode(Enum):
    """Parameter passing modes."""
    IN = "IN"
    OUT = "OUT"
    INOUT = "INOUT"


@dataclass
class ProcedureParameter:
    """Procedure parameter definition."""
    name: str
    mode: ProcedureParameterMode
    data_type: str
    default_value: Optional[Any] = None


@dataclass
class ProcedureVariable:
    """Procedure variable."""
    name: str
    data_type: str
    value: Any = None
    is_cursor: bool = False


@dataclass
class Procedure:
    """Stored procedure definition."""
    name: str
    parameters: List[ProcedureParameter]
    body: str
    variables: Dict[str, ProcedureVariable] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    execution_count: int = 0
    last_executed: Optional[float] = None
    
    def get_parameter(self, name: str) -> Optional[ProcedureParameter]:
        """Get parameter by name."""
        for param in self.parameters:
            if param.name.upper() == name.upper():
                return param
        return None


class ExecutionContext:
    """
    Runtime context for procedure execution.
    Manages variables, parameters, and execution state.
    """
    
    def __init__(self, procedure: Procedure, args: Dict[str, Any]):
        self.procedure = procedure
        self.variables: Dict[str, ProcedureVariable] = {}
        self.parameters: Dict[str, Any] = {}
        self.return_value: Any = None
        self.error_occurred: bool = False
        self.error_message: Optional[str] = None
        self.error_severity: int = 0
        self.error_state: int = 0
        self.cursors: Dict[str, Any] = {}
        self.loop_stack: List[str] = []  # Track nested loops for BREAK/CONTINUE
        
        # Initialize parameters
        for param in procedure.parameters:
            value = args.get(param.name, param.default_value)
            self.parameters[param.name.upper()] = value
            
            # INOUT and OUT parameters also become variables
            if param.mode in (ProcedureParameterMode.INOUT, ProcedureParameterMode.OUT):
                self.variables[param.name.upper()] = ProcedureVariable(
                    name=param.name,
                    data_type=param.data_type,
                    value=value
                )
    
    def declare_variable(self, name: str, data_type: str, value: Any = None):
        """Declare a new variable."""
        name_upper = name.upper()
        if name_upper in self.variables:
            raise ProcedureExecutionError(f"Variable '{name}' already declared")
        
        self.variables[name_upper] = ProcedureVariable(
            name=name,
            data_type=data_type,
            value=value
        )
    
    def set_variable(self, name: str, value: Any):
        """Set variable value."""
        name_upper = name.upper()
        if name_upper not in self.variables:
            raise ProcedureExecutionError(f"Variable '{name}' not declared")
        
        self.variables[name_upper].value = value
    
    def get_variable(self, name: str) -> Any:
        """Get variable value."""
        name_upper = name.upper()
        
        # Check variables first
        if name_upper in self.variables:
            return self.variables[name_upper].value
        
        # Check parameters
        if name_upper in self.parameters:
            return self.parameters[name_upper]
        
        raise ProcedureExecutionError(f"Variable or parameter '{name}' not found")
    
    def set_return_value(self, value: Any):
        """Set procedure return value."""
        self.return_value = value
    
    def raise_error(self, message: str, severity: int = 16, state: int = 1):
        """Raise an error within the procedure."""
        self.error_occurred = True
        self.error_message = message
        self.error_severity = severity
        self.error_state = state
        raise ProcedureExecutionError(message, severity, state)


class ProcedureCompiler:
    """
    Compiles procedure body into executable AST-like structure.
    """
    
    def __init__(self):
        self.keywords = {
            'DECLARE', 'SET', 'IF', 'ELSE', 'ELSEIF', 'WHILE', 'FOR',
            'BEGIN', 'END', 'TRY', 'CATCH', 'RAISERROR', 'RETURN',
            'BREAK', 'CONTINUE', 'OPEN', 'FETCH', 'CLOSE', 'DEALLOCATE',
            'CASE', 'WHEN', 'THEN', 'SELECT', 'INSERT', 'UPDATE', 'DELETE'
        }
    
    def compile(self, body: str) -> List[Dict[str, Any]]:
        """
        Compile procedure body into statement list.
        
        Returns list of statement dictionaries with type and parameters.
        """
        statements = []
        lines = self._tokenize(body)
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            if not line or line.startswith('--'):
                i += 1
                continue
            
            # Try to match each statement type
            stmt, consumed = self._parse_statement(lines, i)
            if stmt:
                statements.append(stmt)
                i += consumed
            else:
                i += 1
        
        return statements
    
    def _tokenize(self, body: str) -> List[str]:
        """Split body into lines preserving structure."""
        # Normalize line endings
        body = body.replace('\r\n', '\n')
        
        # Split but keep delimiters for block statements
        lines = []
        current = ""
        depth = 0
        
        for char in body:
            if char == ';' and depth == 0:
                lines.append(current.strip())
                current = ""
            elif char == '(':
                depth += 1
                current += char
            elif char == ')':
                depth -= 1
                current += char
            else:
                current += char
        
        if current.strip():
            lines.append(current.strip())
        
        return lines
    
    def _parse_statement(self, lines: List[str], start: int) -> Tuple[Optional[Dict], int]:
        """Parse a single statement starting at given position."""
        line = lines[start].strip().upper()
        original = lines[start].strip()
        
        # DECLARE @var type [= value]
        if line.startswith('DECLARE '):
            return self._parse_declare(original), 1
        
        # SET @var = value
        if line.startswith('SET '):
            return self._parse_set(original), 1
        
        # IF condition
        if line.startswith('IF '):
            return self._parse_if(lines, start)
        
        # WHILE condition
        if line.startswith('WHILE '):
            return self._parse_while(lines, start)
        
        # FOR loop
        if line.startswith('FOR '):
            return self._parse_for(lines, start)
        
        # BEGIN...END block
        if line == 'BEGIN' or line.startswith('BEGIN '):
            return self._parse_block(lines, start)
        
        # TRY...CATCH
        if line == 'TRY':
            return self._parse_try_catch(lines, start)
        
        # RAISERROR
        if line.startswith('RAISERROR'):
            return self._parse_raiserror(original), 1
        
        # RETURN
        if line.startswith('RETURN'):
            return self._parse_return(original), 1
        
        # BREAK
        if line == 'BREAK':
            return {'type': 'BREAK'}, 1
        
        # CONTINUE
        if line == 'CONTINUE':
            return {'type': 'CONTINUE'}, 1
        
        # SQL statements (SELECT, INSERT, UPDATE, DELETE)
        if any(line.startswith(kw) for kw in ['SELECT', 'INSERT', 'UPDATE', 'DELETE']):
            return {'type': 'SQL', 'sql': original}, 1
        
        # CASE statement
        if line.startswith('CASE'):
            return self._parse_case(lines, start)
        
        return None, 1
    
    def _parse_declare(self, line: str) -> Dict:
        """Parse DECLARE statement."""
        # DECLARE @name TYPE [= default]
        match = re.match(
            r'DECLARE\s+@(\w+)\s+(\w+(?:\([^)]*\))?)'
            r'(?:\s*=\s*(.+))?',
            line,
            re.IGNORECASE
        )
        
        if not match:
            raise ProcedureCompilationError(f"Invalid DECLARE syntax: {line}")
        
        return {
            'type': 'DECLARE',
            'name': match.group(1),
            'data_type': match.group(2),
            'default': match.group(3).strip() if match.group(3) else None
        }
    
    def _parse_set(self, line: str) -> Dict:
        """Parse SET statement."""
        # SET @var = expression
        match = re.match(
            r'SET\s+@(\w+)\s*=\s*(.+)',
            line,
            re.IGNORECASE
        )
        
        if not match:
            raise ProcedureCompilationError(f"Invalid SET syntax: {line}")
        
        return {
            'type': 'SET',
            'name': match.group(1),
            'value': match.group(2).strip()
        }
    
    def _parse_if(self, lines: List[str], start: int) -> Tuple[Dict, int]:
        """Parse IF...ELSE block."""
        condition_line = lines[start]
        match = re.match(r'IF\s+(.+)', condition_line, re.IGNORECASE)
        
        if not match:
            raise ProcedureCompilationError(f"Invalid IF syntax: {condition_line}")
        
        condition = match.group(1).strip()
        
        # Find matching ELSE/ELSEIF/END IF
        then_block = []
        else_block = []
        i = start + 1
        depth = 1
        
        while i < len(lines) and depth > 0:
            line_upper = lines[i].strip().upper()
            
            if line_upper == 'BEGIN':
                depth += 1
            elif line_upper == 'END':
                depth -= 1
                if depth == 0:
                    break
            elif line_upper.startswith('ELSE') and depth == 1:
                if line_upper.startswith('ELSEIF'):
                    # Handle ELSEIF
                    pass
                else:
                    # ELSE block
                    i += 1
                    else_start = i
                    while i < len(lines):
                        if lines[i].strip().upper() == 'END':
                            break
                        i += 1
                    else_block = lines[else_start:i]
                    break
            
            if depth > 0:
                then_block.append(lines[i])
            
            i += 1
        
        # Compile blocks
        then_stmts = self.compile('\n'.join(then_block)) if then_block else []
        else_stmts = self.compile('\n'.join(else_block)) if else_block else []
        
        return {
            'type': 'IF',
            'condition': condition,
            'then_block': then_stmts,
            'else_block': else_stmts
        }, i - start + 1
    
    def _parse_while(self, lines: List[str], start: int) -> Tuple[Dict, int]:
        """Parse WHILE loop."""
        condition_line = lines[start]
        match = re.match(r'WHILE\s+(.+)', condition_line, re.IGNORECASE)
        
        if not match:
            raise ProcedureCompilationError(f"Invalid WHILE syntax: {condition_line}")
        
        condition = match.group(1).strip()
        
        # Find loop body
        body = []
        i = start + 1
        
        while i < len(lines):
            line = lines[i].strip().upper()
            if line == 'END':
                break
            body.append(lines[i])
            i += 1
        
        body_stmts = self.compile('\n'.join(body)) if body else []
        
        return {
            'type': 'WHILE',
            'condition': condition,
            'body': body_stmts
        }, i - start + 1
    
    def _parse_for(self, lines: List[str], start: int) -> Tuple[Dict, int]:
        """Parse FOR loop (cursor-based)."""
        # FOR @var AS cursor_name CURSOR FOR select_statement
        match = re.match(
            r'FOR\s+@(\w+)\s+AS\s+(\w+)\s+CURSOR\s+FOR\s+(.+)',
            lines[start],
            re.IGNORECASE
        )
        
        if not match:
            raise ProcedureCompilationError(f"Invalid FOR syntax: {lines[start]}")
        
        var_name = match.group(1)
        cursor_name = match.group(2)
        select_stmt = match.group(3)
        
        # Find loop body
        body = []
        i = start + 1
        
        while i < len(lines):
            line = lines[i].strip().upper()
            if line == 'END':
                break
            body.append(lines[i])
            i += 1
        
        body_stmts = self.compile('\n'.join(body)) if body else []
        
        return {
            'type': 'FOR',
            'variable': var_name,
            'cursor': cursor_name,
            'select': select_stmt,
            'body': body_stmts
        }, i - start + 1
    
    def _parse_block(self, lines: List[str], start: int) -> Tuple[Dict, int]:
        """Parse BEGIN...END block."""
        body = []
        i = start + 1
        
        while i < len(lines):
            line = lines[i].strip().upper()
            if line == 'END':
                break
            body.append(lines[i])
            i += 1
        
        body_stmts = self.compile('\n'.join(body)) if body else []
        
        return {
            'type': 'BLOCK',
            'body': body_stmts
        }, i - start + 1
    
    def _parse_try_catch(self, lines: List[str], start: int) -> Tuple[Dict, int]:
        """Parse TRY...CATCH block."""
        # TRY block
        try_body = []
        i = start + 1
        
        while i < len(lines):
            line = lines[i].strip().upper()
            if line == 'CATCH':
                break
            try_body.append(lines[i])
            i += 1
        
        if i >= len(lines):
            raise ProcedureCompilationError("TRY without CATCH")
        
        # CATCH block
        catch_body = []
        i += 1
        
        while i < len(lines):
            line = lines[i].strip().upper()
            if line == 'END':
                break
            catch_body.append(lines[i])
            i += 1
        
        try_stmts = self.compile('\n'.join(try_body)) if try_body else []
        catch_stmts = self.compile('\n'.join(catch_body)) if catch_body else []
        
        return {
            'type': 'TRY_CATCH',
            'try_block': try_stmts,
            'catch_block': catch_stmts
        }, i - start + 1
    
    def _parse_raiserror(self, line: str) -> Dict:
        """Parse RAISERROR statement."""
        # RAISERROR 'message', severity, state
        match = re.match(
            r"RAISERROR\s+['\"](.+?)['\"]\s*,\s*(\d+)\s*,\s*(\d+)",
            line,
            re.IGNORECASE
        )
        
        if not match:
            # Simple form: RAISERROR 'message'
            match = re.match(r"RAISERROR\s+['\"](.+?)['\"]", line, re.IGNORECASE)
            if match:
                return {
                    'type': 'RAISERROR',
                    'message': match.group(1),
                    'severity': 16,
                    'state': 1
                }
            raise ProcedureCompilationError(f"Invalid RAISERROR syntax: {line}")
        
        return {
            'type': 'RAISERROR',
            'message': match.group(1),
            'severity': int(match.group(2)),
            'state': int(match.group(3))
        }
    
    def _parse_return(self, line: str) -> Dict:
        """Parse RETURN statement."""
        match = re.match(r'RETURN(?:\s+(.+))?', line, re.IGNORECASE)
        
        return {
            'type': 'RETURN',
            'value': match.group(1).strip() if match.group(1) else None
        }
    
    def _parse_case(self, lines: List[str], start: int) -> Tuple[Dict, int]:
        """Parse CASE statement."""
        cases = []
        i = start
        
        while i < len(lines):
            line = lines[i].strip().upper()
            
            if line.startswith('CASE '):
                # Simple CASE: CASE expression WHEN...
                pass
            elif line == 'CASE':
                # Searched CASE: CASE WHEN...THEN...
                pass
            elif line.startswith('WHEN '):
                match = re.match(r'WHEN\s+(.+)\s+THEN\s+(.+)', lines[i], re.IGNORECASE)
                if match:
                    cases.append({
                        'when': match.group(1).strip(),
                        'then': match.group(2).strip()
                    })
            elif line.startswith('ELSE '):
                else_clause = re.match(r'ELSE\s+(.+)', lines[i], re.IGNORECASE)
                if else_clause:
                    cases.append({'else': else_clause.group(1).strip()})
            elif line == 'END':
                i += 1
                break
            
            i += 1
        
        return {
            'type': 'CASE',
            'cases': cases
        }, i - start


class ProcedureEngine:
    """
    Main stored procedure execution engine.
    """
    
    def __init__(self, execute_sql_func: Optional[Callable] = None):
        self.procedures: Dict[str, Procedure] = {}
        self.compiler = ProcedureCompiler()
        self._execute_sql = execute_sql_func or self._default_execute
        self._lock = threading.RLock()
    
    def create_procedure(self,
                         name: str,
                         parameters: List[ProcedureParameter],
                         body: str) -> Procedure:
        """
        Create and register a stored procedure.
        
        Args:
            name: Procedure name
            parameters: List of parameters
            body: Procedure body (SQL/control flow)
        
        Returns:
            Compiled Procedure object
        """
        with self._lock:
            if name.upper() in self.procedures:
                raise ValueError(f"Procedure '{name}' already exists")
            
            # Compile body
            compiled_body = self.compiler.compile(body)
            
            procedure = Procedure(
                name=name,
                parameters=parameters,
                body=body,
                variables={}
            )
            
            # Store compiled representation
            procedure._compiled = compiled_body
            
            self.procedures[name.upper()] = procedure
            return procedure
    
    def drop_procedure(self, name: str) -> bool:
        """Drop a procedure."""
        with self._lock:
            name_upper = name.upper()
            if name_upper in self.procedures:
                del self.procedures[name_upper]
                return True
            return False
    
    def execute(self, name: str, args: Dict[str, Any] = None) -> Any:
        """
        Execute a stored procedure.
        
        Args:
            name: Procedure name
            args: Arguments dictionary
        
        Returns:
            Procedure return value or result
        """
        args = args or {}
        
        with self._lock:
            procedure = self.procedures.get(name.upper())
            if not procedure:
                raise ProcedureExecutionError(f"Procedure '{name}' not found")
            
            # Create execution context
            context = ExecutionContext(procedure, args)
            
            try:
                # Execute compiled statements
                result = self._execute_statements(procedure._compiled, context)
                
                procedure.execution_count += 1
                procedure.last_executed = time.time()
                
                # Collect OUT parameters
                output_params = {}
                for param in procedure.parameters:
                    if param.mode in (ProcedureParameterMode.OUT, ProcedureParameterMode.INOUT):
                        if param.name.upper() in context.variables:
                            output_params[param.name] = context.variables[param.name.upper()].value
                
                return {
                    'return_value': context.return_value,
                    'output_params': output_params,
                    'result': result
                }
                
            except ProcedureExecutionError:
                raise
            except Exception as e:
                raise ProcedureExecutionError(f"Procedure execution failed: {e}") from e
    
    def _execute_statements(self, 
                            statements: List[Dict], 
                            context: ExecutionContext) -> Any:
        """Execute a list of compiled statements."""
        result = None
        
        for stmt in statements:
            result = self._execute_statement(stmt, context)
            
            # Check for BREAK/CONTINUE in loops
            if result == 'BREAK':
                return 'BREAK'
            elif result == 'CONTINUE':
                return 'CONTINUE'
        
        return result
    
    def _execute_statement(self, 
                            stmt: Dict, 
                            context: ExecutionContext) -> Any:
        """Execute a single statement."""
        stmt_type = stmt['type']
        
        if stmt_type == 'DECLARE':
            self._execute_declare(stmt, context)
        
        elif stmt_type == 'SET':
            self._execute_set(stmt, context)
        
        elif stmt_type == 'IF':
            return self._execute_if(stmt, context)
        
        elif stmt_type == 'WHILE':
            return self._execute_while(stmt, context)
        
        elif stmt_type == 'FOR':
            return self._execute_for(stmt, context)
        
        elif stmt_type == 'BLOCK':
            return self._execute_statements(stmt['body'], context)
        
        elif stmt_type == 'TRY_CATCH':
            return self._execute_try_catch(stmt, context)
        
        elif stmt_type == 'RAISERROR':
            context.raise_error(
                stmt['message'],
                stmt.get('severity', 16),
                stmt.get('state', 1)
            )
        
        elif stmt_type == 'RETURN':
            value = self._evaluate_expression(stmt.get('value'), context)
            context.set_return_value(value)
            return value
        
        elif stmt_type == 'BREAK':
            return 'BREAK'
        
        elif stmt_type == 'CONTINUE':
            return 'CONTINUE'
        
        elif stmt_type == 'SQL':
            return self._execute_sql(stmt['sql'], context)
        
        elif stmt_type == 'CASE':
            return self._execute_case(stmt, context)
        
        return None
    
    def _execute_declare(self, stmt: Dict, context: ExecutionContext):
        """Execute DECLARE statement."""
        name = stmt['name']
        data_type = stmt['data_type']
        default = stmt.get('default')
        
        # Evaluate default value
        if default:
            value = self._evaluate_expression(default, context)
        else:
            value = self._default_for_type(data_type)
        
        context.declare_variable(name, data_type, value)
    
    def _execute_set(self, stmt: Dict, context: ExecutionContext):
        """Execute SET statement."""
        name = stmt['name']
        value = self._evaluate_expression(stmt['value'], context)
        context.set_variable(name, value)
    
    def _execute_if(self, stmt: Dict, context: ExecutionContext) -> Any:
        """Execute IF statement."""
        condition = self._evaluate_condition(stmt['condition'], context)
        
        if condition:
            return self._execute_statements(stmt['then_block'], context)
        elif stmt.get('else_block'):
            return self._execute_statements(stmt['else_block'], context)
        
        return None
    
    def _execute_while(self, stmt: Dict, context: ExecutionContext) -> Any:
        """Execute WHILE loop."""
        max_iterations = 10000  # Prevent infinite loops
        iterations = 0
        
        while self._evaluate_condition(stmt['condition'], context):
            iterations += 1
            if iterations > max_iterations:
                raise ProcedureExecutionError("WHILE loop exceeded maximum iterations")
            
            result = self._execute_statements(stmt['body'], context)
            
            if result == 'BREAK':
                break
            elif result == 'CONTINUE':
                continue
        
        return None
    
    def _execute_for(self, stmt: Dict, context: ExecutionContext) -> Any:
        """Execute FOR loop (cursor)."""
        # Would implement cursor-based iteration
        # For now, placeholder
        raise NotImplementedError("FOR cursor loops not yet implemented")
    
    def _execute_try_catch(self, stmt: Dict, context: ExecutionContext) -> Any:
        """Execute TRY...CATCH block."""
        try:
            return self._execute_statements(stmt['try_block'], context)
        except ProcedureExecutionError:
            return self._execute_statements(stmt['catch_block'], context)
    
    def _execute_case(self, stmt: Dict, context: ExecutionContext) -> Any:
        """Execute CASE statement."""
        for case in stmt['cases']:
            if 'when' in case:
                if self._evaluate_condition(case['when'], context):
                    return self._evaluate_expression(case['then'], context)
            elif 'else' in case:
                return self._evaluate_expression(case['else'], context)
        
        return None
    
    def _evaluate_condition(self, condition: str, context: ExecutionContext) -> bool:
        """Evaluate a boolean condition."""
        # Substitute variables
        condition = self._substitute_variables(condition, context)
        
        # Simple evaluation - in production would use proper SQL expression evaluator
        # For now, handle common cases
        
        # Comparison operators
        match = re.match(r'(.+?)\s*(=|!=|<>|<|>|<=|>=)\s*(.+)', condition)
        if match:
            left = self._evaluate_expression(match.group(1).strip(), context)
            op = match.group(2)
            right = self._evaluate_expression(match.group(3).strip(), context)
            
            if op == '=': return left == right
            if op in ('!=', '<>'): return left != right
            if op == '<': return left < right
            if op == '>': return left > right
            if op == '<=': return left <= right
            if op == '>=': return left >= right
        
        # IS NULL / IS NOT NULL
        if 'IS NULL' in condition.upper():
            var = condition.upper().replace('IS NULL', '').strip()
            val = context.get_variable(var)
            return val is None
        
        if 'IS NOT NULL' in condition.upper():
            var = condition.upper().replace('IS NOT NULL', '').strip()
            val = context.get_variable(var)
            return val is not None
        
        # Boolean variable
        try:
            val = context.get_variable(condition)
            return bool(val)
        except:
            pass
        
        # Default to True for unparseable conditions
        return True
    
    def _evaluate_expression(self, expr: Optional[str], context: ExecutionContext) -> Any:
        """Evaluate an expression."""
        if expr is None:
            return None
        
        expr = expr.strip()
        
        # Variable reference
        if expr.startswith('@'):
            return context.get_variable(expr[1:])
        
        # String literal
        if (expr.startswith("'") and expr.endswith("'")) or \
           (expr.startswith('"') and expr.endswith('"')):
            return expr[1:-1]
        
        # Number
        try:
            if '.' in expr:
                return float(expr)
            return int(expr)
        except ValueError:
            pass
        
        # NULL
        if expr.upper() == 'NULL':
            return None
        
        # TRUE/FALSE
        if expr.upper() == 'TRUE':
            return True
        if expr.upper() == 'FALSE':
            return False
        
        # Arithmetic expression (simplified)
        match = re.match(r'(.+?)\s*([+\-*/])\s*(.+)', expr)
        if match:
            left = self._evaluate_expression(match.group(1), context)
            op = match.group(2)
            right = self._evaluate_expression(match.group(3), context)
            
            if op == '+': return left + right
            if op == '-': return left - right
            if op == '*': return left * right
            if op == '/': 
                if right == 0:
                    raise ProcedureExecutionError("Division by zero")
                return left / right
        
        # Return as-is if can't evaluate
        return expr
    
    def _substitute_variables(self, text: str, context: ExecutionContext) -> str:
        """Substitute @variables in text."""
        def replace_var(match):
            var_name = match.group(1)
            try:
                value = context.get_variable(var_name)
                if value is None:
                    return 'NULL'
                if isinstance(value, str):
                    return f"'{value}'"
                return str(value)
            except:
                return match.group(0)
        
        return re.sub(r'@(\w+)', replace_var, text)
    
    def _default_for_type(self, data_type: str) -> Any:
        """Get default value for data type."""
        upper = data_type.upper()
        
        if 'INT' in upper:
            return 0
        if any(t in upper for t in ['FLOAT', 'REAL', 'DOUBLE', 'DECIMAL', 'NUMERIC']):
            return 0.0
        if 'BIT' in upper or 'BOOL' in upper:
            return False
        if any(t in upper for t in ['CHAR', 'TEXT', 'VARCHAR', 'STRING']):
            return ''
        if 'DATE' in upper or 'TIME' in upper:
            return None
        
        return None
    
    def _default_execute(self, sql: str) -> Any:
        """Default SQL execution."""
        return None
    
    def list_procedures(self) -> List[Dict[str, Any]]:
        """List all procedures."""
        return [
            {
                'name': proc.name,
                'parameters': len(proc.parameters),
                'created_at': proc.created_at,
                'execution_count': proc.execution_count
            }
            for proc in self.procedures.values()
        ]


class ProcedureCompilationError(Exception):
    """Error during procedure compilation."""
    pass


class ProcedureExecutionError(Exception):
    """Error during procedure execution."""
    
    def __init__(self, message: str, severity: int = 16, state: int = 1):
        super().__init__(message)
        self.severity = severity
        self.state = state


def parse_procedure_definition(sql: str) -> Dict[str, Any]:
    """
    Parse CREATE PROCEDURE statement.
    
    Returns:
        Dictionary with procedure components
    """
    pattern = re.compile(
        r'CREATE\s+(?:OR\s+REPLACE\s+)?PROCEDURE\s+(?P<name>\w+)'
        r'\s*\((?P<params>[^)]*)\)?'
        r'\s*(?:LANGUAGE\s+(?P<lang>\w+))?'
        r'\s*(?:AS\s+)?'
        r'(?P<body>.*)',
        re.IGNORECASE | re.DOTALL
    )
    
    match = pattern.match(sql.strip())
    if not match:
        raise ValueError("Invalid CREATE PROCEDURE syntax")
    
    result = match.groupdict()
    
    # Parse parameters
    params = []
    if result.get('params'):
        for param_str in result['params'].split(','):
            param_str = param_str.strip()
            if not param_str:
                continue
            
            # Parse: [IN|OUT|INOUT] @name TYPE [= default]
            param_match = re.match(
                r'(?:(IN|OUT|INOUT)\s+)?@?(\w+)\s+(\w+(?:\([^)]*\))?)'
                r'(?:\s*=\s*(.+))?',
                param_str,
                re.IGNORECASE
            )
            
            if param_match:
                mode = param_match.group(1) or 'IN'
                params.append(ProcedureParameter(
                    name=param_match.group(2),
                    mode=ProcedureParameterMode(mode.upper()),
                    data_type=param_match.group(3),
                    default_value=param_match.group(4)
                ))
    
    result['parameters'] = params
    return result


# Example usage
if __name__ == '__main__':
    engine = ProcedureEngine()
    
    # Create simple procedure
    proc_sql = """
    CREATE PROCEDURE sp_greet(IN @name VARCHAR(100))
    BEGIN
        DECLARE @message VARCHAR(200);
        SET @message = 'Hello, ' + @name;
        RETURN @message;
    END
    """
    
    parsed = parse_procedure_definition(proc_sql)
    print(f"Procedure: {parsed['name']}")
    print(f"Parameters: {len(parsed['parameters'])}")
    
    # Create procedure
    proc = engine.create_procedure(
        name='sp_test',
        parameters=[ProcedureParameter('name', ProcedureParameterMode.IN, 'VARCHAR(100)')],
        body="DECLARE @x INT; SET @x = 1; RETURN @x;"
    )
    
    print(f"Created: {proc.name}")
    print(f"Compiled statements: {len(proc._compiled)}")
