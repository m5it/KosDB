"""
Tests for query optimizer.
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from query_optimizer import (
    OperatorType, JoinType, Operator, ExecutionPlan,
    Statistics, CostModel, QueryParser, QueryOptimizer,
    IndexAdvisor, explain_query, analyze_query
)


class TestStatistics(unittest.TestCase):
    def test_statistics_creation(self):
        stats = Statistics(
            table_name="users",
            row_count=1000,
            column_stats={"id": {"distinct_count": 1000}},
            index_stats={"id": {}}
        )
        
        self.assertEqual(stats.table_name, "users")
        self.assertEqual(stats.row_count, 1000)
    
    def test_column_cardinality(self):
        stats = Statistics(
            table_name="test",
            row_count=100,
            column_stats={"status": {"distinct_count": 5}}
        )
        
        self.assertEqual(stats.get_column_cardinality("status"), 5)
    
    def test_column_selectivity(self):
        stats = Statistics(
            table_name="test",
            row_count=100,
            column_stats={"active": {"distinct_count": 2}}
        )
        
        self.assertEqual(stats.get_column_selectivity("active"), 0.5)
    
    def test_has_index(self):
        stats = Statistics(
            table_name="test",
            row_count=100,
            index_stats={"id": {}}
        )
        
        self.assertTrue(stats.has_index("id"))
        self.assertFalse(stats.has_index("name"))


class TestCostModel(unittest.TestCase):
    def setUp(self):
        self.cost_model = CostModel()
        
        self.cost_model.add_statistics("users", Statistics(
            table_name="users",
            row_count=10000,
            column_stats={"id": {"distinct_count": 10000}},
            index_stats={"id": {}}
        ))
    
    def test_estimate_scan_cost(self):
        cost, rows = self.cost_model.estimate_scan_cost("users")
        self.assertGreater(cost, 0)
        self.assertEqual(rows, 10000)
    
    def test_estimate_scan_with_index(self):
        cost, rows = self.cost_model.estimate_scan_cost(
            "users", use_index=True, index_column="id"
        )
        self.assertGreater(cost, 0)
        self.assertEqual(rows, 1)  # Very selective
    
    def test_estimate_filter_cost(self):
        cost, rows = self.cost_model.estimate_filter_cost(
            1000, {"column": "status", "op": "=", "value": "active"}
        )
        self.assertGreater(cost, 0)
        self.assertLess(rows, 1000)  # Some filtering


class TestQueryParser(unittest.TestCase):
    def setUp(self):
        self.parser = QueryParser()
    
    def test_parse_select_simple(self):
        query = "SELECT * FROM users"
        result = self.parser.parse(query)
        
        self.assertEqual(result['type'], 'SELECT')
        self.assertEqual(result['table'], 'users')
        self.assertEqual(result['columns'], ['*'])
    
    def test_parse_select_columns(self):
        query = "SELECT id, name, email FROM users"
        result = self.parser.parse(query)
        
        self.assertEqual(result['columns'], ['id', 'name', 'email'])
    
    def test_parse_select_where(self):
        query = "SELECT * FROM users WHERE id = 123"
        result = self.parser.parse(query)
        
        self.assertIsNotNone(result['where'])
        self.assertEqual(result['where']['column'], 'id')
        self.assertEqual(result['where']['op'], '=')
    
    def test_parse_select_order_by(self):
        query = "SELECT * FROM users ORDER BY name DESC"
        result = self.parser.parse(query)
        
        self.assertEqual(result['order_by'], 'name')
        self.assertTrue(result['order_desc'])
    
    def test_parse_select_limit(self):
        query = "SELECT * FROM users LIMIT 10"
        result = self.parser.parse(query)
        
        self.assertEqual(result['limit'], 10)
    
    def test_parse_insert(self):
        query = "INSERT INTO users VALUES (1, 'Alice', 'alice@example.com')"
        result = self.parser.parse(query)
        
        self.assertEqual(result['type'], 'INSERT')
        self.assertEqual(result['table'], 'users')
    
    def test_parse_update(self):
        query = "UPDATE users SET name = 'Bob' WHERE id = 1"
        result = self.parser.parse(query)
        
        self.assertEqual(result['type'], 'UPDATE')
        self.assertEqual(result['table'], 'users')
        self.assertEqual(result['set'], {'name': 'Bob'})
    
    def test_parse_delete(self):
        query = "DELETE FROM users WHERE id = 1"
        result = self.parser.parse(query)
        
        self.assertEqual(result['type'], 'DELETE')
        self.assertEqual(result['table'], 'users')


class TestQueryOptimizer(unittest.TestCase):
    def setUp(self):
        self.optimizer = QueryOptimizer()
        
        # Add statistics
        self.optimizer.add_statistics("users", Statistics(
            table_name="users",
            row_count=10000,
            column_stats={
                "id": {"distinct_count": 10000},
                "status": {"distinct_count": 3}
            },
            index_stats={"id": {}}
        ))
    
    def test_optimize_select_simple(self):
        plan = self.optimizer.optimize("SELECT * FROM users")
        
        self.assertIsNotNone(plan)
        self.assertGreater(plan.total_cost, 0)
        self.assertIn('plan', plan.to_dict())
    
    def test_optimize_select_with_where(self):
        plan = self.optimizer.optimize("SELECT * FROM users WHERE id = 100")
        
        # Should use index
        root_dict = plan.root.to_dict()
        self.assertEqual(root_dict['type'], 'PROJECT')
    
    def test_optimize_select_with_order(self):
        plan = self.optimizer.optimize("SELECT * FROM users ORDER BY id")
        
        self.assertGreater(plan.total_cost, 0)
    
    def test_optimize_insert(self):
        plan = self.optimizer.optimize("INSERT INTO users VALUES (1, 'test')")
        
        self.assertEqual(plan.root.op_type, OperatorType.INSERT)
    
    def test_optimize_update(self):
        plan = self.optimizer.optimize("UPDATE users SET name = 'test' WHERE id = 1")
        
        self.assertEqual(plan.root.op_type, OperatorType.UPDATE)
    
    def test_optimize_delete(self):
        plan = self.optimizer.optimize("DELETE FROM users WHERE id = 1")
        
        self.assertEqual(plan.root.op_type, OperatorType.DELETE)
    
    def test_plan_cache(self):
        query = "SELECT * FROM users"
        
        # First call - cache miss
        plan1 = self.optimizer.optimize(query)
        stats1 = self.optimizer.get_cache_stats()
        self.assertEqual(stats1['misses'], 1)
        
        # Second call - cache hit
        plan2 = self.optimizer.optimize(query)
        stats2 = self.optimizer.get_cache_stats()
        self.assertEqual(stats2['hits'], 1)
        
        # Same plan
        self.assertEqual(plan1.total_cost, plan2.total_cost)
    
    def test_explain_output(self):
        plan = self.optimizer.optimize("SELECT * FROM users WHERE id = 1")
        explanation = plan.explain()
        
        self.assertIn("Execution Plan", explanation)
        self.assertIn("Total Cost", explanation)


class TestIndexAdvisor(unittest.TestCase):
    def setUp(self):
        self.advisor = IndexAdvisor()
    
    def test_record_query(self):
        self.advisor.record_query("SELECT * FROM users WHERE id = 1", 
                                   "users", ["id"])
        
        self.assertEqual(self.advisor.query_patterns["users:id"]['count'], 1)
    
    def test_recommend_indexes(self):
        # Record multiple queries
        for _ in range(10):
            self.advisor.record_query("SELECT * FROM users WHERE id = 1",
                                       "users", ["id"])
        
        recommendations = self.advisor.recommend_indexes(min_frequency=5)
        
        self.assertEqual(len(recommendations), 1)
        self.assertEqual(recommendations[0]['table'], 'users')
        self.assertEqual(recommendations[0]['columns'], ['id'])
    
    def test_get_stats(self):
        self.advisor.record_query("test", "users", ["id"])
        
        stats = self.advisor.get_stats()
        self.assertEqual(stats['patterns_tracked'], 1)


class TestConvenienceFunctions(unittest.TestCase):
    def test_explain_query(self):
        stats = {
            "users": Statistics(
                table_name="users",
                row_count=1000,
                column_stats={"id": {"distinct_count": 1000}},
                index_stats={"id": {}}
            )
        }
        
        explanation = explain_query("SELECT * FROM users WHERE id = 1", stats)
        self.assertIn("Execution Plan", explanation)
    
    def test_analyze_query(self):
        stats = {
            "users": Statistics(
                table_name="users",
                row_count=1000
            )
        }
        
        analysis = analyze_query("SELECT * FROM users", stats)
        
        self.assertIn('plan', analysis)
        self.assertIn('explanation', analysis)
        self.assertIn('estimated_cost', analysis)


class TestExecutionPlan(unittest.TestCase):
    def test_plan_to_dict(self):
        scan = Operator(
            op_type=OperatorType.SCAN,
            table="users",
            estimated_rows=100,
            estimated_cost=10.0
        )
        
        plan = ExecutionPlan(
            root=scan,
            total_cost=10.0,
            estimated_rows=100
        )
        
        data = plan.to_dict()
        self.assertEqual(data['total_cost'], 10.0)
        self.assertEqual(data['estimated_rows'], 100)
    
    def test_plan_explain(self):
        scan = Operator(
            op_type=OperatorType.SCAN,
            table="users",
            estimated_rows=100,
            estimated_cost=10.0
        )
        
        plan = ExecutionPlan(root=scan, total_cost=10.0, estimated_rows=100)
        explanation = plan.explain()
        
        self.assertIn("Seq Scan", explanation)
        self.assertIn("users", explanation)


if __name__ == '__main__':
    unittest.main(verbosity=2)
