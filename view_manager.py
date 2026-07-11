"""
View Manager Module for KosDB v3.2.0

Provides virtual table (view) support with:
- View creation and storage
- View query execution via inline expansion
- Circular reference detection
- View dependency tracking
"""

import json
import re
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass


@dataclass
class ViewDefinition:
    """Represents a view definition."""
    name: str
    query: str
    created_at: float
    dependencies: List[str]  # Tables/views this view depends on


class ViewManager:
    """
    Manager for database views.
    
    Views are stored in the _system database with key pattern:
    _view:<database_name>:<view_name>
    """
    
    def __init__(self, db):
        self.db = db
        self._view_cache = {}  # Cache for view definitions
        self._expansion_stack = []  # Track view expansion for circular detection
    
    def _get_view_key(self, db_name: str, view_name: str) -> bytes:
        """Get the storage key for a view."""
        return f"_view:{db_name}:{view_name}".encode()
    
    def _get_view_metadata_key(self, db_name: str) -> bytes:
        """Get key for view metadata (list of views)."""
        return f"_view_meta:{db_name}".encode()
    
    def create_view(self, db_name: str, view_name: str, query: str) -> str:
        """
        Create a new view.
        
        Args:
            db_name: Database name
            view_name: View name
            query: SELECT query defining the view
        
        Returns:
            Success message or error
        """
        if not self.db._system_db:
            return "ERROR: System database not available"
        
        # Check if view already exists
        view_key = self._get_view_key(db_name, view_name)
        if self.db._system_db.get(view_key):
            return f"ERROR: View '{view_name}' already exists"
        
        # Parse query to extract dependencies
        dependencies = self._extract_dependencies(query)
        
        # Check for circular references
        circular_ref = self._check_circular_reference(db_name, view_name, dependencies)
        if circular_ref:
            return f"ERROR: Circular reference detected: {circular_ref}"
        
        # Validate query (basic check)
        if not self._is_valid_select_query(query):
            return "ERROR: View definition must be a SELECT query"
        
        # Store view definition
        view_def = {
            'name': view_name,
            'query': query,
            'created_at': time.time(),
            'dependencies': dependencies
        }
        
        self.db._system_db.put(view_key, json.dumps(view_def).encode())
        
        # Update metadata
        self._add_view_to_metadata(db_name, view_name)
        
        # Clear cache
        self._view_cache.pop(f"{db_name}:{view_name}", None)
        
        return f"View '{view_name}' created successfully"
    
    def drop_view(self, db_name: str, view_name: str) -> str:
        """
        Drop a view.
        
        Args:
            db_name: Database name
            view_name: View name
        
        Returns:
            Success message or error
        """
        if not self.db._system_db:
            return "ERROR: System database not available"
        
        view_key = self._get_view_key(db_name, view_name)
        if not self.db._system_db.get(view_key):
            return f"ERROR: View '{view_name}' does not exist"
        
        # Check if other views depend on this view
        dependent_views = self._get_dependent_views(db_name, view_name)
        if dependent_views:
            return f"ERROR: Cannot drop view '{view_name}' - depended on by: {', '.join(dependent_views)}"
        
        # Delete view
        self.db._system_db.delete(view_key)
        
        # Update metadata
        self._remove_view_from_metadata(db_name, view_name)
        
        # Clear cache
        self._view_cache.pop(f"{db_name}:{view_name}", None)
        
        return f"View '{view_name}' dropped successfully"
    
    def get_view(self, db_name: str, view_name: str) -> Optional[ViewDefinition]:
        """
        Get view definition.
        
        Args:
            db_name: Database name
            view_name: View name
        
        Returns:
            ViewDefinition or None
        """
        cache_key = f"{db_name}:{view_name}"
        
        # Check cache
        if cache_key in self._view_cache:
            return self._view_cache[cache_key]
        
        if not self.db._system_db:
            return None
        
        view_key = self._get_view_key(db_name, view_name)
        view_data = self.db._system_db.get(view_key)
        
        if not view_data:
            return None
        
        view_dict = json.loads(view_data.decode())
        view_def = ViewDefinition(
            name=view_dict['name'],
            query=view_dict['query'],
            created_at=view_dict['created_at'],
            dependencies=view_dict.get('dependencies', [])
        )
        
        # Cache it
        self._view_cache[cache_key] = view_def
        
        return view_def
    
    def view_exists(self, db_name: str, view_name: str) -> bool:
        """Check if a view exists."""
        return self.get_view(db_name, view_name) is not None
    
    def expand_view(self, db_name: str, view_name: str, 
                   visited: Optional[Set[str]] = None) -> Optional[str]:
        """
        Expand view to its underlying query.
        
        Args:
            db_name: Database name
            view_name: View name
            visited: Set of already visited views (for circular detection)
        
        Returns:
            Expanded query or None
        """
        if visited is None:
            visited = set()
        
        # Circular reference detection
        if view_name in visited:
            return None
        
        visited.add(view_name)
        
        view_def = self.get_view(db_name, view_name)
        if not view_def:
            return None
        
        query = view_def.query
        
        # Recursively expand any views referenced in this view
        for dep_view in view_def.dependencies:
            if self.view_exists(db_name, dep_view):
                expanded = self.expand_view(db_name, dep_view, visited)
                if expanded:
                    # Replace view reference with subquery
                    # This is a simplified expansion - real implementation
                    # would need proper SQL parsing
                    query = self._inline_view(query, dep_view, expanded)
        
        return query
    
    def _inline_view(self, query: str, view_name: str, expanded_query: str) -> str:
        """
        Inline a view reference with its expanded query.
        
        Args:
            query: Original query
            view_name: Name of view to inline
            expanded_query: Expanded view query
        
        Returns:
            Modified query with view inlined
        """
        # Simple replacement - wrap in subquery
        # In production, would need proper SQL parsing
        pattern = rf'\b{re.escape(view_name)}\b'
        replacement = f"({expanded_query}) AS {view_name}"
        return re.sub(pattern, replacement, query)
    
    def list_views(self, db_name: str) -> List[str]:
        """
        List all views in database.
        
        Args:
            db_name: Database name
        
        Returns:
            List of view names
        """
        if not self.db._system_db:
            return []
        
        meta_key = self._get_view_metadata_key(db_name)
        meta_data = self.db._system_db.get(meta_key)
        
        if not meta_data:
            return []
        
        return json.loads(meta_data.decode())
    
    def _extract_dependencies(self, query: str) -> List[str]:
        """
        Extract table/view dependencies from query.
        
        Args:
            query: SELECT query
        
        Returns:
            List of table/view names
        """
        dependencies = []
        
        # Simple regex extraction - FROM and JOIN clauses
        # FROM table_name
        from_matches = re.findall(r'\bFROM\s+(\w+)', query, re.IGNORECASE)
        dependencies.extend(from_matches)
        
        # JOIN table_name
        join_matches = re.findall(r'\bJOIN\s+(\w+)', query, re.IGNORECASE)
        dependencies.extend(join_matches)
        
        return list(set(dependencies))  # Remove duplicates
    
    def _check_circular_reference(self, db_name: str, view_name: str, 
                                   dependencies: List[str]) -> Optional[str]:
        """
        Check if creating this view would create a circular reference.
        
        Args:
            db_name: Database name
            view_name: Name of view being created
            dependencies: Dependencies of the new view
        
        Returns:
            Error message if circular, None otherwise
        """
        # Check if any dependency is the view itself
        if view_name in dependencies:
            return f"View '{view_name}' cannot reference itself"
        
        # Check if any dependency depends on this view (would create cycle)
        for dep in dependencies:
            if not self.view_exists(db_name, dep):
                continue
            
            # Check if dep view depends on view_name
            dep_def = self.get_view(db_name, dep)
            if dep_def and view_name in dep_def.dependencies:
                return f"View '{dep}' already depends on '{view_name}'"
            
            # Recursive check
            cycle = self._find_cycle(db_name, view_name, dep, set())
            if cycle:
                return cycle
        
        return None
    
    def _find_cycle(self, db_name: str, target: str, current: str, 
                    visited: Set[str]) -> Optional[str]:
        """Find cycle in view dependencies."""
        if current in visited:
            return None
        
        visited.add(current)
        
        if not self.view_exists(db_name, current):
            return None
        
        view_def = self.get_view(db_name, current)
        if not view_def:
            return None
        
        for dep in view_def.dependencies:
            if dep == target:
                return f"Cycle detected: {current} -> {target}"
            
            cycle = self._find_cycle(db_name, target, dep, visited)
            if cycle:
                return f"{current} -> {cycle}"
        
        return None
    
    def _is_valid_select_query(self, query: str) -> bool:
        """Basic validation that query is a SELECT statement."""
        query_upper = query.strip().upper()
        return query_upper.startswith('SELECT')
    
    def _add_view_to_metadata(self, db_name: str, view_name: str):
        """Add view to metadata list."""
        meta_key = self._get_view_metadata_key(db_name)
        meta_data = self.db._system_db.get(meta_key)
        
        views = []
        if meta_data:
            views = json.loads(meta_data.decode())
        
        if view_name not in views:
            views.append(view_name)
            self.db._system_db.put(meta_key, json.dumps(views).encode())
    
    def _remove_view_from_metadata(self, db_name: str, view_name: str):
        """Remove view from metadata list."""
        meta_key = self._get_view_metadata_key(db_name)
        meta_data = self.db._system_db.get(meta_key)
        
        if not meta_data:
            return
        
        views = json.loads(meta_data.decode())
        if view_name in views:
            views.remove(view_name)
            self.db._system_db.put(meta_key, json.dumps(views).encode())
    
    def _get_dependent_views(self, db_name: str, view_name: str) -> List[str]:
        """
        Get list of views that depend on the given view.
        
        Args:
            db_name: Database name
            view_name: View name
        
        Returns:
            List of dependent view names
        """
        dependents = []
        all_views = self.list_views(db_name)
        
        for vname in all_views:
            if vname == view_name:
                continue
            
            view_def = self.get_view(db_name, vname)
            if view_def and view_name in view_def.dependencies:
                dependents.append(vname)
        
        return dependents
    
    def describe_view(self, db_name: str, view_name: str) -> Optional[str]:
        """
        Get description of view.
        
        Args:
            db_name: Database name
            view_name: View name
        
        Returns:
            Description string or None
        """
        view_def = self.get_view(db_name, view_name)
        if not view_def:
            return None
        
        lines = [
            f"View: {view_name}",
            f"Query: {view_def.query}",
            f"Created: {time.ctime(view_def.created_at)}",
            f"Dependencies: {', '.join(view_def.dependencies)}"
        ]
        
        return "\n".join(lines)


# Import time here to avoid circular import
import time
