# Materialized Views and Query Rewriting for KosDB

Automatic query optimization and materialized views with incremental refresh.

## Features

- **Query Rewriting**: Automatic query optimization
- **Materialized Views**: Pre-computed query results
- **Incremental Refresh**: Update based on changes only
- **Scheduled Refresh**: Automatic periodic updates
- **Query Caching**: Cached results for performance

## Refresh Strategies

| Strategy | Description |
|----------|-------------|
| full | Complete rebuild of view |
| incremental | Update based on detected changes |
| auto | Automatically choose best strategy |

## Refresh Schedules

| Schedule | Description |
|----------|-------------|
| manual | Refresh on demand |
| on_commit | Refresh after each transaction |
| every_n_minutes | Periodic refresh |
| cron | Cron-based schedule |

## SQL Commands

### Create Materialized View
```sql
CREATE MATERIALIZED VIEW monthly_sales AS 
SELECT month, SUM(amount) FROM orders GROUP BY month

CREATE MATERIALIZED VIEW user_stats AS 
SELECT user_id, COUNT(*) FROM orders GROUP BY user_id
STRATEGY incremental SCHEDULE every_n_minutes INTERVAL 60
```

### Drop Materialized View
```sql
DROP MATERIALIZED VIEW monthly_sales
```

### Refresh Materialized View
```sql
REFRESH MATERIALIZED VIEW monthly_sales
REFRESH MATERIALIZED VIEW user_stats STRATEGY full
REFRESH ALL MATERIALIZED VIEWS
```

### List Materialized Views
```sql
LIST MATERIALIZED VIEWS
```

### Query Materialized View
```sql
SELECT * FROM MV monthly_sales
```

### Set Refresh Schedule
```sql
SET REFRESH SCHEDULE monthly_sales SCHEDULE every_n_minutes INTERVAL 30
SET REFRESH SCHEDULE user_stats SCHEDULE manual
```

### Statistics
```sql
MATERIALIZED VIEW STATS
MATERIALIZED VIEW STATS monthly_sales
```

## API Reference

### QueryRewriter

```python
from materialized_views import QueryRewriter

rewriter = QueryRewriter()

# Rewrite query
plan = rewriter.rewrite("SELECT * FROM users WHERE id = 1")

print(f"Original: {plan.original_query}")
print(f"Rewritten: {plan.rewritten_query}")
print(f"Estimated cost: {plan.estimated_cost}")
```

### MaterializedView

```python
from materialized_views import MaterializedView, RefreshStrategy, RefreshSchedule

view = MaterializedView(
    name="sales_summary",
    query="SELECT SUM(amount) FROM orders",
    refresh_strategy=RefreshStrategy.INCREMENTAL,
    refresh_schedule=RefreshSchedule.EVERY_N_MINUTES,
    schedule_interval=60
)

# Mark as stale when base data changes
view.mark_stale()

# Get statistics
stats = view.get_stats()
```

### MaterializedViewManager

```python
from materialized_views import get_materialized_view_manager

manager = get_materialized_view_manager()

# Create view
view = manager.create_view(
    name="monthly_sales",
    query="SELECT month, SUM(amount) FROM orders GROUP BY month",
    refresh_strategy="incremental",
    refresh_schedule="every_n_minutes",
    schedule_interval=60
)

# Refresh view
result = manager.refresh_view("monthly_sales")
print(f"Refreshed in {result['duration_ms']}ms")

# Query view
data, plan = manager.query_view("monthly_sales")

# Drop view
manager.drop_view("monthly_sales")

# Get statistics
stats = manager.get_stats()
```

## Example: Sales Dashboard

```python
from materialized_views import get_materialized_view_manager

manager = get_materialized_view_manager()

# Create daily sales summary
manager.create_view(
    name="daily_sales",
    query="""
        SELECT 
            DATE(order_date) as day,
            COUNT(*) as order_count,
            SUM(amount) as total_revenue,
            AVG(amount) as avg_order_value
        FROM orders
        GROUP BY DATE(order_date)
    """,
    refresh_strategy="incremental",
    refresh_schedule="every_n_minutes",
    schedule_interval=5  # Refresh every 5 minutes
)

# Create top products view
manager.create_view(
    name="top_products",
    query="""
        SELECT 
            product_id,
            product_name,
            SUM(quantity) as total_sold
        FROM order_items
        GROUP BY product_id, product_name
        ORDER BY total_sold DESC
        LIMIT 100
    """,
    refresh_strategy="full",
    refresh_schedule="every_n_minutes",
    schedule_interval=15  # Refresh every 15 minutes
)

# Query the views
sales_data, _ = manager.query_view("daily_sales")
products_data, _ = manager.query_view("top_products")

print(f"Daily sales: {len(sales_data)} days")
print(f"Top products: {len(products_data)} products")
```

## Example: Query Rewriting

```python
from materialized_views import QueryRewriter

rewriter = QueryRewriter()

# Original query with potential issues
original = """
    SELECT * FROM users u, orders o, items i
    WHERE u.id = o.user_id AND o.id = i.order_id
    AND u.status = 'active'
    ORDER BY u.created_at
"""

plan = rewriter.rewrite(original)

print(f"Original cost: {plan.estimated_cost}")
print(f"Suggested rewrite: {plan.rewritten_query}")
```

## Configuration

```json
{
    "materialized_views": {
        "default_refresh_strategy": "full",
        "default_schedule": "manual",
        "enable_query_rewriting": true,
        "cache_size_mb": 100
    }
}
```

## Testing

```bash
python test_materialized_views.py
```

All 16 tests passing ✓
