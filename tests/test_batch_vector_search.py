
"""
Tests for Batch Vector Search Operations
"""

import unittest
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from batch_vector_search import (
    BatchVectorAddResult,
    BatchVectorSearchResult,
    BatchVectorDeleteResult,
    HybridSearchResult,
    parse_vector_add_batch,
    parse_vector_search_batch
)


class TestParseVectorAddBatch(unittest.TestCase):
    """Test VECTOR ADD BATCH parsing."""
    
    def test_parse_vector_add_batch(self):
        """Test parsing VECTOR ADD BATCH command."""
        command = "VECTOR ADD BATCH my_index [('doc1', [0.1, 0.2, 0.3], {'tag': 'a'}), ('doc2', [0.4, 0.5, 0.6], {'tag': 'b'})]"
        
        index_name, documents = parse_vector_add_batch(command)
        
        self.assertEqual(index_name, 'my_index')
        self.assertEqual(len(documents), 2)
        self.assertEqual(documents[0][0], 'doc1')
        self.assertEqual(documents[0][1], [0.1, 0.2, 0.3])
    
    def test_parse_invalid_command(self):
        """Test parsing invalid command."""
        command = "SELECT * FROM table"
        
        index_name, documents = parse_vector_add_batch(command)
        
        self.assertIsNone(index_name)
        self.assertEqual(documents, [])


class TestParseVectorSearchBatch(unittest.TestCase):
    """Test VECTOR SEARCH BATCH parsing."""
    
    def test_parse_vector_search_batch(self):
        """Test parsing batch search command."""
        command = "VECTOR SEARCH BATCH my_index [('q1', [0.1, 0.2, 0.3]), ('q2', [0.4, 0.5, 0.6])] LIMIT 5"
        
        result = parse_vector_search_batch(command)
        
        self.assertEqual(result['index_name'], 'my_index')
        self.assertEqual(len(result['queries']), 2)
        self.assertEqual(result['k'], 5)
    
    def test_parse_without_limit(self):
        """Test parsing without LIMIT."""
        command = "VECTOR SEARCH BATCH my_index [('q1', [0.1, 0.2, 0.3])]"
        
        result = parse_vector_search_batch(command)
        
        self.assertEqual(result['k'], 10)  # Default


class TestResultClasses(unittest.TestCase):
    """Test result dataclasses."""
    
    def test_batch_vector_add_result(self):
        """Test BatchVectorAddResult creation."""
        result = BatchVectorAddResult(
            added=100,
            failed=5,
            elapsed_ms=150.5,
            index_updates=10
        )
        
        self.assertEqual(result.added, 100)
        self.assertEqual(result.failed, 5)
        
        data = result.to_dict()
        self.assertEqual(data['added'], 100)
        self.assertEqual(data['failed'], 5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
