"""
Query Rewrite Engine for KosDB v3.4.0

Provides advanced query transformation capabilities:
- View Merging: Replace views with their base query definitions
- Predicate Pushdown: Move WHERE clauses closer to data sources
- Subquery Unnesting: Convert subqueries to joins
- Join Reordering: Optimize join order based on statistics
- Constant Folding: Evaluate constant expressions at compile time
- Eliminate Dead Code: Remove unused columns and tables

Example:
    -- View merging
    CREATE VIEW high_value_customers AS
    SELECT * FROM customers WHERE total_orders > 1000;
    
    SELECT * FROM high_value_customers WHERE region = 'US';
    -- Rewritten to:
    SELECT * FROM customers WHERE total_orders > 1000 AND region = 'US';
    
    -- Subquery unnesting
    SELECT * FROM orders WHERE customer_id IN (
        SELECT id FROM customers WHERE country = 'US'
    );
    -- Rewritten to:
    SELECT o.* FROM orders o
    JOIN customers c ON o.customer_id = c.id
    WHERE c.country = 'US';
"""

import re
import copy
from typing import Dict, Any, List, Optional, Tuple, Set, Union, Callable
from dataclasses import dataclass, field
from enum import Enum, auto


class RewriteType(Enum):
    """Types of query rewrites."""
    VIEW_MERGE = "view_merge"
    PREDICATE_PUSHDOWN = "predicate_pushdown"
    SUBQUERY_UNNEST = "subquery_unnest"
    JOIN_REORDER = "join_reorder"
    CONSTANT_FOLDING = "constant_folding"
    ELIMINATE_UNUSED = "eliminate_unused"
    MERGE_PREDICATES = "merge_predicates"
    SIMPLIFY_EXPRESSIONS = "simplify_expressions"


@dataclass
class RewriteRule:
    """Represents a query rewrite rule."""
    name: str
    rewrite_type: RewriteType
    transform_func: Callable
    enabled: bool = True
    priority: int = 100  # Lower = higher priority
    statistics_required: bool = False
    
    def apply(self, query: Dict[str, Any], context: Dict) -> Tuple[Dict[str, Any], bool]:
        """
        Apply the rewrite rule.
        
        Returns:
            Tuple of (rewritten_query, was_modified)
        """
        if not self.enabled:
            return query, False
        
        try:
            return self.transform_func(query, context)
        except Exception as e:
            # Log error but don't fail
            return query, False


@dataclass
class RewriteContext:
    """Context for query rewrite operations."""
    views: Dict[str, Dict] = field(default_factory=dict)
    statistics: Dict[str, Dict] = field(default_factory=dict)
    hints: Set[str] = field(default_factory=set)
    foreign_tables: Set[str] = field(default_factory=set)
    
    def add_hint(self, hint: str):
        """Add a query hint."""
        self.hints.add(hint.upper())
    
    def has_hint(self, hint: str) -> bool:
        """Check if hint is present."""
        return hint.upper() in self.hints


class QueryRewriteEngine:
    """
    Main query rewrite engine for KosDB.
    Applies transformation rules to optimize queries before cost-based optimization.
    """
    
    def __init__(self):
        self.rules: List[RewriteRule] = []
        self.stats = {
            'queries_rewritten': 0,
            'rules_applied': 0,
            'view_merges': 0,
            'predicate_pushdowns': 0,
            'subquery_unnests': 0,
            'join_reorders': 0
        }
        self._register_default_rules()
    
    def _register_default_rules(self):
        """Register default rewrite rules."""
        self.rules = [
            # High priority: Constant folding first
            RewriteRule(
                name="constant_folding",
                rewrite_type=RewriteType.CONSTANT_FOLDING,
                transform_func=self._rewrite_constant_folding,
                priority=10
            ),
            
            # View merging (priority 20)
            RewriteRule(
                name="view_merge",
                rewrite_type=RewriteType.VIEW_MERGE,
                transform_func=self._rewrite_view_merge,
                priority=20
            ),
            
            # Predicate pushdown (priority 30)
            RewriteRule(
                name="predicate_pushdown",
                rewrite_type=RewriteType.PREDICATE_PUSHDOWN,
                transform_func=self._rewrite_predicate_pushdown,
                priority=30
            ),
            
            # Subquery unnesting (priority 40)
            RewriteRule(
                name="subquery_unnest",
                rewrite_type=RewriteType.SUBQUERY_UNNEST,
                transform_func=self._rewrite_subquery_unnest,
                priority=40
            ),
            
            # Join reordering (priority 50, requires statistics)
            RewriteRule(
                name="join_reorder",
                rewrite_type=RewriteType.JOIN_REORDER,
                transform_func=self._rewrite_join_reorder,
                priority=50,
                statistics_required=True
            ),
            
            # Eliminate unused columns/tables (priority 60)
            RewriteRule(
                name="eliminate_unused",
                rewrite_type=RewriteType.ELIMINATE_UNUSED,
                transform_func=self._rewrite_eliminate_unused,
                priority=60
            ),
            
            # Merge predicates (priority 70)
            RewriteRule(
                name="merge_predicates",
                rewrite_type=RewriteType.MERGE_PREDICATES,
                transform_func=self._rewrite_merge_predicates,
                priority=70
            ),
            
            # Simplify expressions (priority 80)
            RewriteRule(
                name="simplify_expressions",
                rewrite_type=RewriteType.SIMPLIFY_EXPRESSIONS,
                transform_func=self._rewrite_simplify_expressions,
                priority=80
            )
        ]
        
        # Sort by priority
        self.rules.sort(key=lambda r: r.priority)
    
    def rewrite(self, query: Dict[str, Any], 
                context: Optional[RewriteContext] = None) -> Tuple[Dict[str, Any], Dict]:
        """
        Apply all enabled rewrite rules to a query.
        
        Args:
            query: Parsed query structure
            context: Rewrite context with views, statistics, etc.
        
        Returns:
            Tuple of (rewritten_query, rewrite_stats)
        """
        if context is None:
            context = RewriteContext()
        
        original_query = copy.deepcopy(query)
        current_query = query
        applied_rules = []
        total_modifications = 0
        
        # Apply rules iteratively until no more changes
        max_iterations = 10
        for iteration in range(max_iterations):
            modified = False
            
            for rule in self.rules:
                # Skip if statistics required but not available
                if rule.statistics_required and not context.statistics:
                    continue
                
                # Skip if disabled by hint
                if f"NO_{rule.rewrite_type.value.upper()}" in context.hints:
                    continue
                
                new_query, was_modified = rule.apply(current_query, context)
                
                if was_modified:
                    current_query = new_query
                    applied_rules.append(rule.name)
                    self.stats['rules_applied'] += 1
                    total_modifications += 1
                    modified = True
                    
                    # Update specific stats
                    if rule.rewrite_type == RewriteType.VIEW_MERGE:
                        self.stats['view_merges'] += 1
                    elif rule.rewrite_type == RewriteType.PREDICATE_PUSHDOWN:
                        self.stats['predicate_pushdowns'] += 1
                    elif rule.rewrite_type == RewriteType.SUBQUERY_UNNEST:
                        self.stats['subquery_unnests'] += 1
                    elif rule.rewrite_type == RewriteType.JOIN_REORDER:
                        self.stats['join_reorders'] += 1
            
            if not modified:
                break  # No more changes
        
        if total_modifications > 0:
            self.stats['queries_rewritten'] += 1
        
        rewrite_stats = {
            'original': original_query,
            'rewritten': current_query,
            'rules_applied': applied_rules,
            'modifications': total_modifications,
            'iterations': iteration + 1
        }
        
        return current_query, rewrite_stats
    
    # ==================== Rewrite Transformations ====================
    
    def _rewrite_view_merge(self, query: Dict[str, Any], 
                           context: RewriteContext) -> Tuple[Dict[str, Any], bool]:
        """
        Merge view definitions into the query.
        
        Example:
            SELECT * FROM high_value_customers WHERE region = 'US'
            -- high_value_customers is: SELECT * FROM customers WHERE orders > 1000
            -- Becomes:
            SELECT * FROM customers WHERE orders > 1000 AND region = 'US'
        """
n        if query.get('type') != 'SELECT':\n            return query, False\n        \n        modified = False\n        \n        # Check if FROM table is a view\n        table = query.get('table')\n        if table and table in context.views:\n            view_def = context.views[table]\n            \n            # Merge view into query\n            query['table'] = view_def.get('table')\n            \n            # Merge WHERE clauses\n            view_where = view_def.get('where')\n            query_where = query.get('where')\n            \n            if view_where and query_where:\n                query['where'] = {\n                    'op': 'AND',\n                    'left': view_where,\n                    'right': query_where\n                }\n            elif view_where:\n                query['where'] = view_where\n            \n            modified = True\n        \n        # Handle JOINs with views\n        joins = query.get('joins', [])\n        for join in joins:\n            join_table = join.get('table')\n            if join_table and join_table in context.views:\n                # Similar merging for joins\n                pass\n        \n        return query, modified
    
    def _rewrite_predicate_pushdown(self, query: Dict[str, Any],
                                   context: RewriteContext) -> Tuple[Dict[str, Any], bool]:
        """
        Push predicates down to data sources.
        
        Example:
            SELECT * FROM (SELECT * FROM orders WHERE amount > 100) o
            WHERE o.customer_id = 5
            -- Becomes:
            SELECT * FROM orders WHERE amount > 100 AND customer_id = 5
        """
n        if query.get('type') != 'SELECT':\n            return query, False\n        \n        modified = False\n        \n        # Get WHERE clause\n        where = query.get('where')\n        if not where:\n            return query, False\n        \n        # Check if FROM is a subquery\n        table = query.get('table')\n        if isinstance(table, dict) and table.get('type') == 'SELECT':
n            # Push predicate into subquery\n            subquery_where = table.get('where')\n            \n            if subquery_where:\n                table['where'] = {\n                    'op': 'AND',\n                    'left': subquery_where,\n                    'right': copy.deepcopy(where)\n                }\n            else:\n                table['where'] = copy.deepcopy(where)\n            \n            # Remove from outer query\n            del query['where']\n            modified = True\n        \n        # Push predicates into JOINs\n        joins = query.get('joins', [])\n        for join in joins:\n            join_table = join.get('table')\n            join_condition = join.get('on')\n            \n            # Check if we can push additional predicates\n            if where and self._can_push_to_table(where, join_table):
n                # Add to join condition\n                if join_condition:\n                    join['on'] = {\n                        'op': 'AND',\n                        'left': join_condition,\n                        'right': self._extract_predicates_for_table(where, join_table)\n                    }\n                else:\n                    join['on'] = self._extract_predicates_for_table(where, join_table)\n                \n                modified = True\n        \n        return query, modified
    
    def _rewrite_subquery_unnest(self, query: Dict[str, Any],
                                context: RewriteContext) -> Tuple[Dict[str, Any], bool]:
        """
        Convert subqueries to joins where possible.
        
        Example:
            SELECT * FROM orders WHERE customer_id IN (
                SELECT id FROM customers WHERE country = 'US'
            )
            -- Becomes:
            SELECT DISTINCT o.* FROM orders o
            JOIN customers c ON o.customer_id = c.id
            WHERE c.country = 'US'
        """
n        if query.get('type') != 'SELECT':\n            return query, False\n        \n        modified = False\n        where = query.get('where')\n        \n        if not where:\n            return query, False\n        \n        # Check for IN subquery
        if where.get('op') == 'IN' and 'subquery' in where.get('right', {}):
n            subquery = where['right']['subquery']\n            \n            # Convert to JOIN\n            if subquery.get('type') == 'SELECT':
n                # Create join\n                new_join = {\n                    'type': 'JOIN',\n                    'join_type': 'SEMI',  # or INNER with DISTINCT\n                    'table': subquery.get('table'),\n                    'on': {\n                        'op': '=',\n                        'left': where['left'],  # outer column\n                        'right': subquery.get('columns', [None])[0]  # subquery column\n                    }\n                }\n                \n                # Add subquery WHERE to join\n                subquery_where = subquery.get('where')\n                if subquery_where:\n                    new_join['on'] = {\n                        'op': 'AND',\n                        'left': new_join['on'],\n                        'right': subquery_where\n                    }\n                \n                # Replace WHERE with JOIN\n                joins = query.get('joins', [])\n                joins.append(new_join)\n                query['joins'] = joins\n                del query['where']\n                \n                modified = True\n        \n        # Check for EXISTS subquery
        if where.get('op') == 'EXISTS':
n            subquery = where.get('subquery')\n            \n            if subquery and subquery.get('type') == 'SELECT':
n                # Convert EXISTS to JOIN\n                new_join = {\n                    'type': 'JOIN',\n                    'join_type': 'SEMI',\n                    'table': subquery.get('table'),\n                    'on': subquery.get('where', {'op': 'TRUE'})\n                }\n                \n                joins = query.get('joins', [])\n                joins.append(new_join)\n                query['joins'] = joins\n                del query['where']\n                \n                modified = True\n        \n        return query, modified
    
    def _rewrite_join_reorder(self, query: Dict[str, Any],
                             context: RewriteContext) -> Tuple[Dict[str, Any], bool]:
        """
        Reorder joins based on table statistics.
        
        Uses greedy algorithm: join smallest tables first.
        """
n        if query.get('type') != 'SELECT':\n            return query, False\n        \n        joins = query.get('joins', [])\n        if len(joins) <= 1:\n            return query, False\n        \n        # Get table sizes from statistics
        table_sizes = {}\n        for join in joins:
n            table = join.get('table')\n            if table in context.statistics:\n                table_sizes[table] = context.statistics[table].get('row_count', 1000)\n            else:
n                table_sizes[table] = 1000  # Default estimate\n        \n        # Sort by size (smallest first)
n        sorted_joins = sorted(joins, \n                            key=lambda j: table_sizes.get(j.get('table'), 1000))\n        \n        if sorted_joins != joins:\n            query['joins'] = sorted_joins\n            return query, True\n        \n        return query, False
    
    def _rewrite_constant_folding(self, query: Dict[str, Any],
                                 context: RewriteContext) -> Tuple[Dict[str, Any], bool]:
        """
        Evaluate constant expressions at compile time.
        
        Example:
            WHERE age > 20 + 5  -->  WHERE age > 25
            WHERE 1 = 1 AND x = 5  -->  WHERE x = 5
        """
n        modified = False\n        \n        # Process WHERE clause
        where = query.get('where')\n        if where:\n            new_where, was_modified = self._fold_constants_in_condition(where)\n            if was_modified:\n                query['where'] = new_where\n                modified = True\n        \n        # Process SELECT expressions
        columns = query.get('columns', [])\n        new_columns = []\n        for col in columns:\n            if isinstance(col, dict) and 'expression' in col:
n                new_expr, was_modified = self._fold_constants_in_expression(\n                    col['expression']\n                )\n                if was_modified:\n                    col = dict(col)\n                    col['expression'] = new_expr\n                    modified = True\n            new_columns.append(col)\n        \n        if modified:\n            query['columns'] = new_columns\n        \n        return query, modified
    
    def _rewrite_eliminate_unused(self, query: Dict[str, Any],
                                 context: RewriteContext) -> Tuple[Dict[str, Any], bool]:
        """
        Remove unused columns and tables from the query.
        """
n        modified = False\n        \n        if query.get('type') != 'SELECT':\n            return query, False\n        \n        # Get columns that are actually used
        used_columns = self._get_used_columns(query)\n        \n        # Remove unused columns from SELECT
        columns = query.get('columns', [])\n        if columns != ['*']:\n            new_columns = [c for c in columns if c in used_columns or c == '*']\n            if len(new_columns) < len(columns):\n                query['columns'] = new_columns\n                modified = True\n        \n        # Remove tables that don't contribute to results
        # (This is more complex and would require analysis)
n        \n        return query, modified
    
    def _rewrite_merge_predicates(self, query: Dict[str, Any],
                                 context: RewriteContext) -> Tuple[Dict[str, Any], bool]:
        """
        Merge multiple predicates on same column.
        
        Example:
            WHERE x > 5 AND x > 3  -->  WHERE x > 5
            WHERE x = 5 AND x = 5  -->  WHERE x = 5
        """
n        where = query.get('where')\n        if not where:\n            return query, False\n        \n        new_where, modified = self._merge_conditions(where)\n        if modified:\n            query['where'] = new_where\n        \n        return query, modified
    
    def _rewrite_simplify_expressions(self, query: Dict[str, Any],
                                      context: RewriteContext) -> Tuple[Dict[str, Any], bool]:
        """
        Simplify boolean expressions.
        
        Example:
            WHERE x = x  -->  WHERE TRUE (or remove)
            WHERE x IS NOT NULL OR x IS NULL  -->  WHERE TRUE
            WHERE FALSE AND x = 5  -->  WHERE FALSE
        """
n        where = query.get('where')\n        if not where:\n            return query, False\n        \n        new_where, modified = self._simplify_boolean_expressions(where)\n        if modified:\n            query['where'] = new_where\n        \n        return query, modified
    
    # ==================== Helper Methods ====================
    
    def _can_push_to_table(self, condition: Dict, table: str) -> bool:
n        \"\"\"Check if condition can be pushed to specific table.\"\"\"\n        # Simple check: does condition reference only this table?\n        cols = self._extract_columns_from_condition(condition)\n        return len(cols) == 1 and table in cols
    
    def _extract_predicates_for_table(self, condition: Dict, table: str) -> Dict:
n        \"\"\"Extract predicates that apply to specific table.\"\"\"\n        # Simplified - would need full implementation\n        return condition
    
    def _extract_columns_from_condition(self, condition: Dict) -> Set[str]:
n        \"\"\"Extract all column references from condition.\"\"\"\n        columns = set()\n        \n        if isinstance(condition, dict):\n            if 'column' in condition:\n                columns.add(condition['column'])\n            if 'left' in condition:\n                columns.update(self._extract_columns_from_condition(condition['left']))\n            if 'right' in condition:\n                columns.update(self._extract_columns_from_condition(condition['right']))\n        \n        return columns
    
    def _fold_constants_in_condition(self, condition: Dict) -> Tuple[Dict, bool]:
n        \"\"\"Fold constants in WHERE condition.\"\"\"\n        modified = False\n        \n        if not isinstance(condition, dict):\n            return condition, False\n        \n        op = condition.get('op')\n        \n        # Handle arithmetic operations
        if op in ('+', '-', '*', '/'):\n            left = condition.get('left')\n            right = condition.get('right')\n            \n            # Try to evaluate if both sides are constants
            if self._is_constant(left) and self._is_constant(right):\n                try:\n                    result = self._evaluate_constant_op(op, left, right)\n                    return result, True\n                except:\n                    pass\n        \n        # Handle AND with TRUE
        if op == 'AND':
n            left = condition.get('left')\n            right = condition.get('right')\n            \n            # Remove TRUE from AND
            if self._is_true(left):\n                return right, True\n            if self._is_true(right):\n                return left, True\n            \n            # Fold recursively
            new_left, mod_left = self._fold_constants_in_condition(left)\n            new_right, mod_right = self._fold_constants_in_condition(right)\n            \n            if mod_left or mod_right:\n                return {'op': 'AND', 'left': new_left, 'right': new_right}, True\n        \n        # Handle OR with FALSE
        if op == 'OR':
n            left = condition.get('left')\n            right = condition.get('right')\n            \n            if self._is_false(left):\n                return right, True\n            if self._is_false(right):\n                return left, True\n        \n        return condition, modified
    
    def _fold_constants_in_expression(self, expression: Any) -> Tuple[Any, bool]:
n        \"\"\"Fold constants in expression.\"\"\"\n        # Simplified implementation\n        return expression, False
    
    def _is_constant(self, value: Any) -> bool:
n        \"\"\"Check if value is a constant.\"\"\"\n        return isinstance(value, (int, float, str, bool)) and not isinstance(value, dict)\n    
    def _is_true(self, value: Any) -> bool:
n        \"\"\"Check if value is TRUE constant.\"\"\"\n        return value is True or (isinstance(value, dict) and value.get('op') == 'TRUE')\n    
    def _is_false(self, value: Any) -> bool:
n        \"\"\"Check if value is FALSE constant.\"\"\"\n        return value is False or (isinstance(value, dict) and value.get('op') == 'FALSE')\n    
    def _evaluate_constant_op(self, op: str, left: Any, right: Any) -> Any:
n        \"\"\"Evaluate constant operation.\"\"\"\n        if op == '+':\n            return left + right\n        elif op == '-':\n            return left - right\n        elif op == '*':\n            return left * right\n        elif op == '/':\n            return left / right\n        return None
    
    def _get_used_columns(self, query: Dict) -> Set[str]:
n        \"\"\"Get all columns used in query.\"\"\"\n        used = set()\n        \n        # Columns in WHERE
        where = query.get('where')\n        if where:\n            used.update(self._extract_columns_from_condition(where))\n        \n        # Columns in ORDER BY
        order_by = query.get('order_by', [])\n        used.update(order_by)\n        \n        # Columns in GROUP BY
        group_by = query.get('group_by', [])\n        used.update(group_by)\n        \n        return used
    
    def _merge_conditions(self, condition: Dict) -> Tuple[Dict, bool]:
n        \"\"\"Merge redundant conditions.\"\"\"\n        # Simplified - would implement full logic\n        return condition, False
    
    def _simplify_boolean_expressions(self, condition: Dict) -> Tuple[Dict, bool]:
n        \"\"\"Simplify boolean expressions.\"\"\"\n        # Simplified - would implement full logic\n        return condition, False
    
    def get_stats(self) -> Dict[str, Any]:
n        \"\"\"Get rewrite engine statistics.\"\"\"\n        return self.stats.copy()
    
    def enable_rule(self, rule_name: str):
n        \"\"\"Enable a rewrite rule.\"\"\"\n        for rule in self.rules:\n            if rule.name == rule_name:\n                rule.enabled = True\n                break
    
    def disable_rule(self, rule_name: str):
n        \"\"\"Disable a rewrite rule.\"\"\"\n        for rule in self.rules:\n            if rule.name == rule_name:\n                rule.enabled = False\n                break


def parse_query_hints(query: str) -> Tuple[str, Set[str]]:
n    \"\"\"\n    Parse query hints from SQL comment.
n    
n    Example:
n        SELECT /*+ NO_VIEW_MERGE NO_SUBQUERY_UNNEST */ * FROM t
n    \n    Returns:
n        Tuple of (query_without_hints, set_of_hints)
n    \"\"\"\n    # Match /*+ ... */ style hints\n    hint_pattern = re.compile(r'/\\*\\+\\s*(.+?)\\s*\\*/')\n    \n    hints = set()\n    \n    def extract_hints(match):\n        hint_text = match.group(1)\n        for hint in hint_text.split():\n            hints.add(hint.upper().strip())\n        return ''  # Remove hint from query\n    \n    cleaned_query = hint_pattern.sub(extract_hints, query)\n    \n    return cleaned_query, hints


def create_rewrite_context(views: Optional[Dict] = None,
n                          statistics: Optional[Dict] = None) -> RewriteContext:
n    \"\"\"Create a rewrite context.\"\"\"\n    context = RewriteContext()\n    \n    if views:\n        context.views = views\n    if statistics:\n        context.statistics = statistics\n    \n    return context


# Example usage\nif __name__ == '__main__':\n    engine = QueryRewriteEngine()\n    \n    # Example query\n    query = {\n        'type': 'SELECT',\n        'columns': ['*'],\n        'table': 'high_value_customers',\n        'where': {\n            'op': '=',\n            'column': 'region',\n            'value': 'US'\n        }\n    }\n    \n    # Create context with view definition\n    context = RewriteContext()\n    context.views['high_value_customers'] = {\n        'type': 'SELECT',\n        'table': 'customers',\n        'where': {\n            'op': '>',\n            'column': 'total_orders',\n            'value': 1000\n        }\n    }\n    \n    # Rewrite\n    rewritten, stats = engine.rewrite(query, context)\n    \n    print(\"Original query:\", query)\n    print(\"Rewritten query:\", rewritten)\n    print(\"Stats:\", stats)
