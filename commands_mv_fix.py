
    # Materialized View Handlers (v3.4.0)
    def _create_materialized_view(self, params, state):
        """Create a materialized view."""
        if not self.mv_manager:
            return "ERROR: Materialized view support not available"
        
        if not state.get('current_db'):
            return "ERROR: No database selected"
        
        name = params.get('name')
        query = params.get('query')
        build = params.get('build', 'IMMEDIATE')
        refresh = params.get('refresh', 'COMPLETE')
        rewrite = params.get('rewrite', '').upper() == 'ENABLE'
        
        if not name or not query:
            return "ERROR: CREATE MATERIALIZED VIEW requires name and query"
        
        try:
            # Extract base tables from query (simplified)
            import re
            from_tables = re.findall(r'FROM\s+(\w+)', query, re.IGNORECASE)
            join_tables = re.findall(r'JOIN\s+(\w+)', query, re.IGNORECASE)
            base_tables = list(set(from_tables + join_tables))
            
            # Extract columns (simplified)
            columns = []
            select_match = re.match(r'SELECT\s+(.+?)\s+FROM', query, re.IGNORECASE)
            if select_match:
                cols_str = select_match.group(1)
                # Simple extraction - would need proper parsing
                for col in cols_str.split(','):
                    col = col.strip()
                    # Remove aliases
                    if ' AS ' in col.upper():
                        col = col.split()[-1]
                    # Remove functions
                    if '(' in col:
                        col = col.split(')')[-1].strip()
                    columns.append(col)
            
            mv = self.mv_manager.create_materialized_view(
                name=name,
                query=query,
                base_tables=base_tables,
                columns=columns,
                refresh_type=refresh,
                build_type=build,
                enable_query_rewrite=rewrite
            )
            
            rewrite_str = " with query rewrite" if rewrite else ""
            return f"Materialized view '{name}' created{rewrite_str} ({len(mv.data)} rows)"
            
        except Exception as e:
            return f"ERROR: Failed to create materialized view: {e}"
    
    def _refresh_materialized_view(self, params, state):
        """Refresh a materialized view."""
        if not self.mv_manager:
            return "ERROR: Materialized view support not available"
        
        name = params.get('name')
        concurrently = params.get('concurrently') is not None
        
        if not name:
            return "ERROR: REFRESH MATERIALIZED VIEW requires view name"
        
        try:
            result = self.mv_manager.refresh(name, concurrently=concurrently)
            
            return (
                f"Materialized view '{name}' refreshed\n"
                f"Type: {result['refresh_type']}\n"
                f"Rows: {result['rows_affected']}\n"
                f"Duration: {result['duration_ms']}ms"
            )
            
        except Exception as e:
            return f"ERROR: Failed to refresh materialized view: {e}"
    
    def _drop_materialized_view(self, params, state):
        """Drop a materialized view."""
        if not self.mv_manager:
            return "ERROR: Materialized view support not available"
        
        name = params.get('name')
        if not name:
            return "ERROR: DROP MATERIALIZED VIEW requires view name"
        
        success = self.mv_manager.drop_materialized_view(name)
        if success:
            return f"Materialized view '{name}' dropped"
        else:
            return f"ERROR: Materialized view '{name}' not found"
    
    def _show_materialized_views(self, params, state):
        """Show all materialized views."""
        if not self.mv_manager:
            return "ERROR: Materialized view support not available"
        
        views = self.mv_manager.list_materialized_views()
        
        if not views:
            return "No materialized views found"
        
        lines = ["Materialized Views:", "-" * 80]
        lines.append(f"{'Name':<25} {'Type':<12} {'Rows':<10} {'Last Refresh':<20} {'Stale'}")
        lines.append("-" * 80)
        
        for mv in views:
            last_refresh = "Never"
            if mv['last_refresh']:
                last_refresh = time.strftime('%Y-%m-%d %H:%M', 
                                             time.localtime(mv['last_refresh']))
            
            stale_mark = "YES" if mv['is_stale'] else "NO"
            
            lines.append(
                f"{mv['name']:<25} {mv['refresh_type']:<12} "
                f"{mv['row_count']:<10} {last_refresh:<20} {stale_mark}"
            )
        
        return "\n".join(lines)
    
    def _get_table_data(self, table: str) -> List[Dict]:
        """Get data from table for materialized view."""
        # Would integrate with actual database
        return []
