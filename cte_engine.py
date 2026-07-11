"""
CTE Engine for KosDB v3.3.0

Provides Common Table Expression (CTE) support:
- Non-recursive CTEs
- Recursive CTEs (WITH RECURSIVE)
- Multiple CTEs in single query
- Proper scoping and reference resolution
"""

from typing import Dict, Any, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum


class CTENodeType(Enum):
    """Types of CTE nodes."""
    NON_RECURSIVE = "NON_RECURSIVE"
    RECURSIVE_ANCHOR = "RECURSIVE_ANCHOR"
    RECURSIVE_ITERATIVE = "RECURSIVE_ITERATIVE"


@dataclass
class CTE:
    """Represents a single Common Table Expression."""
    name: str
    columns: Optional[List[str]]  # Explicit column names (optional)
    query: Dict[str, Any]  # Parsed query
    node_type: CTENodeType
    is_recursive: bool = False
    
    # For recursive CTEs
    anchor_query: Optional[Dict[str, Any]] = None
    recursive_query: Optional[Dict[str, Any]] = None
    
    # Execution results (transient)
    result_data: List[Dict[str, Any]] = field(default_factory=list)
    is_executed: bool = False


@dataclass
class CTEDefinition:
    """Complete CTE definition from WITH clause."""
    ctes: List[CTE]
    is_recursive: bool = False
    main_query: Optional[Dict[str, Any]] = None


class CTEEngine:
    """
    Engine for executing Common Table Expressions.
    
    Handles:
    - CTE registration and scoping
    - Non-recursive CTE execution
    - Recursive CTE execution (fixed-point iteration)
    - Reference resolution
    """
    
    def __init__(self, execute_query_func=None):
        self.ctes: Dict[str, CTE] = {}
        self.execute_query = execute_query_func or self._default_execute
        self.max_recursive_iterations = 100  # Prevent infinite recursion
    
    def register_ctes(self, cte_def: CTEDefinition):
        """Register CTEs from definition."""
        self.ctes.clear()
        for cte in cte_def.ctes:
            self.ctes[cte.name.upper()] = cte
    
    def execute_cte(self, cte_name: str) -> List[Dict[str, Any]]:
        """
        Execute a CTE and return results.
        
        Args:
            cte_name: Name of the CTE to execute
        
        Returns:
            List of result rows
        """
        cte_name = cte_name.upper()
        cte = self.ctes.get(cte_name)
        
        if not cte:
            raise ValueError(f"CTE not found: {cte_name}")
        
        if cte.is_executed:
            return cte.result_data
        
        if cte.is_recursive:
            result = self._execute_recursive_cte(cte)
        else:
            result = self._execute_non_recursive_cte(cte)
        
        cte.result_data = result
        cte.is_executed = True
        
        return result
    
    def _execute_non_recursive_cte(self, cte: CTE) -> List[Dict[str, Any]]:
        """Execute a non-recursive CTE."""
        # Execute the CTE query
        return self.execute_query(cte.query)
    
    def _execute_recursive_cte(self, cte: CTE) -> List[Dict[str, Any]]:
        """
        Execute a recursive CTE using fixed-point iteration.
        
        Algorithm:
        1. Execute anchor query (base case)
        2. Execute recursive query with current results
        3. Union results
        4. Repeat until no new rows or max iterations reached
        """
        if not cte.anchor_query or not cte.recursive_query:
            raise ValueError(f"Recursive CTE {cte.name} missing anchor or recursive query")
        
        # Execute anchor query
        result = self.execute_query(cte.anchor_query)
        all_results = result.copy()
        
        # Iterative execution
        for iteration in range(self.max_recursive_iterations):
            # Execute recursive query with current results as input
            new_rows = self._execute_recursive_step(
                cte.recursive_query, 
                cte.name,
                result
            )
            
            if not new_rows:
                break  # Fixed point reached
            
            # Add new rows (UNION semantics - remove duplicates)
            existing_keys = {self._row_key(r) for r in all_results}
            for row in new_rows:
                key = self._row_key(row)
                if key not in existing_keys:
                    all_results.append(row)
                    existing_keys.add(key)
            
            result = new_rows  # Continue with new rows only
        
        return all_results
    
    def _execute_recursive_step(self, query: Dict[str, Any], 
                                cte_name: str, 
                                current_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute one step of recursive CTE."""
        # Temporarily register current data as CTE result
        if cte_name.upper() in self.ctes:
            self.ctes[cte_name.upper()].result_data = current_data
        
        return self.execute_query(query)
    
    def _row_key(self, row: Dict[str, Any]) -> Tuple:
        """Generate hashable key for row (for duplicate detection)."""
        return tuple(sorted(row.items()))
    
    def _default_execute(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Default query execution (placeholder)."""
        # This should be replaced with actual database execution
        return []
    
    def resolve_cte_reference(self, table_name: str) -> Optional[CTE]:
        """
        Check if table name refers to a CTE.
        
        Args:
            table_name: Table name to check
        
        Returns:
            CTE if found, None otherwise
        """
        return self.ctes.get(table_name.upper())
    
    def get_cte_columns(self, cte_name: str) -> List[str]:
        """
        Get column names for a CTE.
        
        Args:
            cte_name: Name of the CTE
        
        Returns:
            List of column names
        """
        cte_name = cte_name.upper()
        cte = self.ctes.get(cte_name)
        
        if not cte:
            return []
        
        if cte.columns:
            return cte.columns
        
        # Infer from result data
        if cte.result_data:
            return list(cte.result_data[0].keys())
        
        return []
    
    def clear(self):
        """Clear all CTEs."""
        self.ctes.clear()
    
    def get_execution_order(self) -> List[str]:
        """
        Get topological order for CTE execution.
        
        Handles dependencies between CTEs.
        """
        # Build dependency graph
        dependencies: Dict[str, Set[str]] = {}
        
        for name, cte in self.ctes.items():
            deps = self._extract_dependencies(cte.query)
            dependencies[name] = deps
        
        # Topological sort
        visited: Set[str] = set()
        order: List[str] = []
        
        def visit(n: str):
            if n in visited:
                return
            visited.add(n)
            for dep in dependencies.get(n, []):
                if dep in self.ctes:  # Only visit CTE dependencies
                    visit(dep)
            order.append(n)
        
        for name in self.ctes:
            visit(name)
        
        return order
    
    def _extract_dependencies(self, query: Dict[str, Any]) -> Set[str]:
        """Extract CTE dependencies from query."""
        deps = set()
        
        # Check FROM clause
        table = query.get('table')
        if table and isinstance(table, str):
            deps.add(table.upper())
        
        # Check subqueries
        # This is simplified - full implementation would parse all subqueries
        
        return deps


def parse_cte_definition(sql: str) -> Optional[CTEDefinition]:
    """
    Parse WITH clause from SQL.
    
    Args:
        sql: SQL query with CTE
    
    Returns:
        CTEDefinition or None if no CTE
    """
    import re
    
    # Match WITH [RECURSIVE] clause
    pattern = r'^\s*WITH\s+(RECURSIVE\s+)?(.+?)\s+SELECT\s+'
    match = re.match(pattern, sql, re.IGNORECASE | re.DOTALL)
    
    if not match:
        return None
    
    is_recursive = bool(match.group(1))
    cte_part = match.group(2)
    
    # Split CTEs (handle parentheses carefully)
    ctes = []
    current_cte = ""
    paren_depth = 0
    
    for char in cte_part:
        if char == '(':
            paren_depth += 1
            current_cte += char
        elif char == ')':
            paren_depth -= 1
            current_cte += char
        elif char == ',' and paren_depth == 0:
            # End of CTE
            cte = _parse_single_cte(current_cte.strip(), is_recursive)
            if cte:
                ctes.append(cte)
            current_cte = ""
        else:
            current_cte += char
    
    # Last CTE
    if current_cte.strip():
        cte = _parse_single_cte(current_cte.strip(), is_recursive)
        if cte:
            ctes.append(cte)
    
    return CTEDefinition(
        ctes=ctes,
        is_recursive=is_recursive
    )


def _parse_single_cte(cte_str: str, is_recursive: bool) -> Optional[CTE]:
    """Parse a single CTE definition."""
    import re
    
    # Pattern: name [(cols)] AS (query)
    pattern = r'(\w+)\s*(?:\(([^)]+)\))?\s+AS\s*\((.+)\)'
    match = re.match(pattern, cte_str.strip(), re.IGNORECASE | re.DOTALL)
    
    if not match:
        return None
    
    name = match.group(1)
    columns = None
    if match.group(2):
        columns = [c.strip() for c in match.group(2).split(',')]
    
    query_str = match.group(3).strip()
    
    # Check for recursive UNION/UNION ALL
    union_pattern = r'(.+?)\s+UNION\s+(?:ALL\s+)?(.+)'
    union_match = re.match(union_pattern, query_str, re.IGNORECASE | re.DOTALL)
    
    if is_recursive and union_match:
        # Recursive CTE with anchor and recursive parts
        return CTE(
            name=name,
            columns=columns,
            query={'raw': query_str},
            node_type=CTENodeType.RECURSIVE_ANCHOR,
            is_recursive=True,
            anchor_query={'raw': union_match.group(1).strip()},
            recursive_query={'raw': union_match.group(2).strip()}
        )
    
    # Non-recursive CTE
    return CTE(
        name=name,
        columns=columns,
        query={'raw': query_str},
        node_type=CTENodeType.NON_RECURSIVE,
        is_recursive=False
    )


# Example usage
if __name__ == '__main__':
    # Example 1: Simple non-recursive CTE
    sql1 = """
        WITH sales_summary AS (
            SELECT dept, SUM(sales) as total_sales
            FROM sales
            GROUP BY dept
        )
        SELECT * FROM sales_summary WHERE total_sales > 10000
    """
    
    cte_def = parse_cte_definition(sql1)
    if cte_def:
        print(f"Found {len(cte_def.ctes)} CTE(s)")
        for cte in cte_def.ctes:
            print(f"  CTE: {cte.name}, Recursive: {cte.is_recursive}")
    
    # Example 2: Recursive CTE for hierarchical data
    sql2 = """
        WITH RECURSIVE employee_hierarchy AS (
            -- Anchor: top-level employees
            SELECT id, name, manager_id, 0 as level
            FROM employees
            WHERE manager_id IS NULL
            
            UNION ALL
            
            -- Recursive: employees with managers
            SELECT e.id, e.name, e.manager_id, eh.level + 1
            FROM employees e
            JOIN employee_hierarchy eh ON e.manager_id = eh.id
        )
        SELECT * FROM employee_hierarchy
    """
    
    cte_def2 = parse_cte_definition(sql2)
    if cte_def2:
        print(f"\nFound {len(cte_def2.ctes)} CTE(s), Recursive: {cte_def2.is_recursive}")
        for cte in cte_def2.ctes:
            print(f"  CTE: {cte.name}")
            if cte.anchor_query:
                print(f"    Anchor: {cte.anchor_query['raw'][:50]}...")
            if cte.recursive_query:
                print(f"    Recursive: {cte.recursive_query['raw'][:50]}...")
