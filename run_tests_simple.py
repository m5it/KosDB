#!/usr/bin/env python3
"""
Simple test runner for KosDB v3.4.0
Runs all test files and reports results.
"""

import unittest
import sys
import os

# Test files to run
TEST_FILES = [
    'test/test_check_constraints.py',
TEST_FILES = [
    'test/test_check_constraints.py',
    'test/test_alter_table.py',
    'test/test_subqueries.py',
    'test/test_metrics.py',
    'test/test_query_plan_cache.py',
    'test/test_window_functions.py',
    'test/test_ctes.py',
    'test/test_prepared_statements.py',
    'test/test_triggers.py',
    'test/test_procedures.py',
    'test/test_partitioning.py',
    'test/test_advanced_indexes.py',
    'test/test_materialized_views.py',
    'test/test_parallel_execution.py',
    'test/test_fdw.py',
    'test/test_query_rewrite.py',
    'test/test_events.py',
]
            try:
                tests = loader.loadTestsFromName(module_name)
                suite.addTests(tests)
            except Exception as e:
                print(f"Warning: Could not load {test_file}: {e}")
        else:
            print(f"Warning: Test file not found: {test_file}")
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    modules = ['database', 'parser', 'commands', 'query_optimizer', 'metrics', 'window_functions', 'cte_engine', 'prepared_statement_cache', 'trigger_engine', 'procedure_engine', 'partition_manager', 'advanced_index', 'materialized_view_manager', 'parallel_executor', 'fdw_manager']
    # Print summary
    modules = ['database', 'parser', 'commands', 'query_optimizer', 'metrics', 'window_functions', 'cte_engine', 'prepared_statement_cache', 'trigger_engine', 'procedure_engine', 'partition_manager', 'advanced_index', 'materialized_view_manager', 'parallel_executor', 'fdw_manager', 'query_rewrite']
    print("TEST SUMMARY")
    modules = ['database', 'parser', 'commands', 'query_optimizer', 'metrics', 'window_functions', 'cte_engine', 'prepared_statement_cache', 'trigger_engine', 'procedure_engine', 'partition_manager', 'advanced_index', 'materialized_view_manager', 'parallel_executor', 'fdw_manager', 'query_rewrite', 'event_scheduler']
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.wasSuccessful():
        print("\nAll tests passed!")
        return 0
    else:
        print("\nSome tests failed!")
        return 1

def check_syntax():
    """Check syntax of all modules."""
    print("Checking syntax of modules...")
    
    modules = ['database', 'parser', 'commands', 'query_optimizer', 'metrics', 
               'window_functions', 'cte_engine', 'prepared_statement_cache',
               'trigger_engine', 'procedure_engine', 'partition_manager',
               'advanced_index', 'materialized_view_manager', 'parallel_executor']
    
    errors = []
    for mod in modules:
        try:
            __import__(mod)
            print(f"  {mod}: OK")
        except SyntaxError as e:
            print(f"  {mod}: SYNTAX ERROR - {e}")
            errors.append((mod, e))
        except ImportError as e:
            print(f"  {mod}: Import error (may be OK) - {e}")
        except Exception as e:
            print(f"  {mod}: ERROR - {e}")
            errors.append((mod, e))
    
    if errors:
        print(f"\n{len(errors)} modules have errors:")
        for mod, err in errors:
            print(f"  {mod}: {err}")
        return 1
    else:
        print("\nAll modules OK!")
        return 0

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Run KosDB tests')
    parser.add_argument('--syntax-only', action='store_true', 
                       help='Only check syntax, do not run tests')
    args = parser.parse_args()
    
    if args.syntax_only:
        sys.exit(check_syntax())
    else:
        sys.exit(run_tests())
