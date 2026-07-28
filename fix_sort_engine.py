#!/usr/bin/env python3
"""Fix sort_engine.py property issue"""

with open('sort_engine.py', 'r') as f:
    content = f.read()

# Fix the property issue - change self.backend_name to self._backend_name_input
content = content.replace(
    'self.backend_name = backend',
    'self._backend_name_input = backend'
)

# Also need to update the property getter
content = content.replace(
    '''    @property
    def backend_name(self) -> str:
        """Get actual backend name being used."""
        return self._backend.name if self._backend else 'unknown' ''',
    '''    @property
    def backend_name(self) -> str:
        """Get actual backend name being used."""
        return self._backend.name if self._backend else 'unknown'
    
    @backend_name.setter
    def backend_name(self, value: str) -> None:
        """Set backend name (for initialization only)."""
        self._backend_name_input = value'''
)

with open('sort_engine.py', 'w') as f:
    f.write(content)

print("Fixed sort_engine.py")
