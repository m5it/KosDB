#!/usr/bin/env python3
"""Fix bugs in sort engine integration"""

# Fix 1: sort_engine.py - remove property decorator for backend_name
with open('sort_engine.py', 'r') as f:
    content = f.read()

# Remove the property decorator and setter for backend_name
# Just make it a regular attribute that gets updated
content = content.replace(
    '''    @property
    def backend_name(self) -> str:
        """Get actual backend name being used."""
        return self._backend.name if self._backend else 'unknown'
    
    @backend_name.setter
    def backend_name(self, value: str) -> None:
        """Set backend name (for initialization only)."""
        self._backend_name_input = value''',
    '''    @property
    def backend_name(self) -> str:
        """Get actual backend name being used."""
        return self._backend.name if self._backend else 'unknown'''
)

# Also fix the __init__ to not set backend_name directly
content = content.replace(
    '''        self.strict = strict
        self.backend_name = backend
        self._backend = None
        self._fallback_count = 0''',
    '''        self.strict = strict
        self._requested_backend = backend
        self._backend = None
        self._fallback_count = 0'''
)

with open('sort_engine.py', 'w') as f:
    f.write(content)

print("Fixed sort_engine.py")

# Fix 2: query_optimizer.py - add sort_strategy attribute to ExecutionPlan
with open('query_optimizer.py', 'r') as f:
    content = f.read()

# Find ExecutionPlan class and add sort_strategy attribute
old_plan = '''class ExecutionPlan:
    """Represents an optimized execution plan.'''
new_plan = '''class ExecutionPlan:
    """Represents an optimized execution plan.
    
    Attributes:
        query_type: Type of query (SELECT, INSERT, etc.)
        parsed: Parsed query dict
        index_usage: Index usage plan
        column_pruning: Column pruning info
        sort_strategy: Sort optimization strategy
        sort_cost: Estimated sort cost
    '''

content = content.replace(old_plan, new_plan)

# Add initialization of sort_strategy in ExecutionPlan.__init__
old_init = '''        self.query_type = query_type
        self.parsed = parsed
        self.index_usage = None
        self.column_pruning = None
        self.estimated_cost = 100.0
        self.estimated_rows = 1000'''

new_init = '''        self.query_type = query_type
        self.parsed = parsed
        self.index_usage = None
        self.column_pruning = None
        self.sort_strategy = {}
        self.sort_cost = 0.0
        self.estimated_cost = 100.0
        self.estimated_rows = 1000'''

content = content.replace(old_init, new_init)

with open('query_optimizer.py', 'w') as f:
    f.write(content)

print("Fixed query_optimizer.py")

# Fix 3: Update sort_examples.py to use correct import
with open('sort_examples.py', 'r') as f:
    content = f.read()

content = content.replace(
    'from database import KosDB',
    'from database import Database as KosDB'
)

with open('sort_examples.py', 'w') as f:
    f.write(content)

print("Fixed sort_examples.py")

print("\nAll bugs fixed!")
