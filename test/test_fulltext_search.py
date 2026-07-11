"""
Test Full-Text Search for KosDB v3.2.0

Tests:
- CREATE FULLTEXT INDEX syntax
- MATCH AGAINST natural language search
- MATCH AGAINST boolean search
- MATCH AGAINST with query expansion
- Relevance scoring
- Tokenization and stemming
- Index management (create, drop, update)
"""

import unittest
import sys
import os
import tempfile
import shutil

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database
from parser import CommandParser
from fulltext_index import FulltextIndex, FulltextIndexManager


class TestFulltextIndex(unittest.TestCase):
    """Test full-text index functionality."""
    
    def setUp(self):
        """Set up test database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db = Database(self.temp_dir, server_id=1)
        self.parser = CommandParser()
        
        # Create test database
        self.db.create_database("testdb")
        self.db.use_database("testdb")
        
        # Create full-text index manager
        self.ft_manager = FulltextIndexManager(self.db)
    
    def tearDown(self):
        """Clean up test database."""
        self.db.close()
        shutil.rmtree(self.temp_dir)
    
    def test_tokenization(self):
        """Test text tokenization."""
        ft_index = FulltextIndex("articles", "content")
        
        # Basic tokenization
        tokens = ft_index.tokenize("Hello world, this is a test!")
        self.assertIn('hello', tokens)
        self.assertIn('world', tokens)
        self.assertIn('test', tokens)
        
        # Stop words should be filtered
        self.assertNotIn('is', tokens)
        self.assertNotIn('a', tokens)
    
    def test_stemming(self):
        """Test word stemming."""
        ft_index = FulltextIndex("articles", "content")
        
        # Test various stemming rules
        self.assertEqual(ft_index.stem("running"), "runn")
        self.assertEqual(ft_index.stem("books"), "book")
        self.assertEqual(ft_index.stem("babies"), "baby")
        self.assertEqual(ft_index.stem("married"), "marry")
    
    def test_index_document(self):
        """Test document indexing."""
        ft_index = FulltextIndex("articles", "content")
        
        entries = ft_index.index_document("doc1", "Hello world hello")
        
        # Check 'hello' entry
        self.assertIn('hello', entries)
        self.assertEqual(entries['hello']['doc_ids']['doc1']['frequency'], 2)
        self.assertEqual(entries['hello']['doc_ids']['doc1']['positions'], [0, 2])
        
        # Check 'world' entry
        self.assertIn('world', entries)
        self.assertEqual(entries['world']['doc_ids']['doc1']['frequency'], 1)
    
    def test_natural_language_search(self):
        """Test natural language search."""
        ft_index = FulltextIndex("articles", "content")
        
        # Build index
        index_data = {}
        
        # Index multiple documents
        for doc_id, text in [
            ("doc1", "Hello world programming"),
            ("doc2", "Hello world database"),
            ("doc3", "Programming database search")
        ]:
            entries = ft_index.index_document(doc_id, text)
            for term, data in entries.items():
                if term not in index_data:
                    index_data[term] = data
                else:
                    index_data[term]['doc_ids'].update(data['doc_ids'])
                    index_data[term]['total_count'] += data['total_count']
        
        # Search for "hello"
        results = ft_index.search_natural_language("hello", index_data, 3)
        self.assertEqual(len(results), 2)  # doc1 and doc2
        
        # doc1 and doc2 should have higher scores (both contain "hello")
        doc_ids = [r[0] for r in results]
        self.assertIn('doc1', doc_ids)
        self.assertIn('doc2', doc_ids)
    
    def test_boolean_search(self):
        """Test boolean search mode."""
        ft_index = FulltextIndex("articles", "content")
        
        # Build index
        index_data = {}
        
        for doc_id, text in [
            ("doc1", "Hello world programming"),
            ("doc2", "Hello world database"),
            ("doc3", "Programming database search"),
            ("doc4", "Hello search test")
        ]:
            entries = ft_index.index_document(doc_id, text)
            for term, data in entries.items():
                if term not in index_data:
                    index_data[term] = data
                else:
                    index_data[term]['doc_ids'].update(data['doc_ids'])
                    index_data[term]['total_count'] += data['total_count']
        
        # Must include "hello" and "world"
        results = ft_index.search_boolean("+hello +world", index_data, 4)
        self.assertEqual(len(results), 2)  # doc1 and doc2
        
        # Must include "hello", exclude "world"
        results = ft_index.search_boolean("+hello -world", index_data, 4)
        self.assertEqual(len(results), 1)  # doc4 only
        
        # Optional terms
        results = ft_index.search_boolean("programming database", index_data, 4)
        self.assertGreaterEqual(len(results), 2)
    
    def test_tf_idf_scoring(self):
        """Test TF-IDF relevance scoring."""
        ft_index = FulltextIndex("articles", "content")
        
        index_data = {}
        
        # Create documents with varying term frequencies
        for doc_id, text in [
            ("doc1", "hello hello hello"),  # High TF for "hello"
            ("doc2", "hello"),               # Low TF for "hello"
            ("doc3", "world")                # No "hello"
        ]:
            entries = ft_index.index_document(doc_id, text)
            for term, data in entries.items():
                if term not in index_data:
                    index_data[term] = data
                else:
                    index_data[term]['doc_ids'].update(data['doc_ids'])
                    index_data[term]['total_count'] += data['total_count']
        
        results = ft_index.search_natural_language("hello", index_data, 3)
        
        # doc1 should have higher score than doc2
        scores = {r[0]: r[1] for r in results}
        self.assertGreater(scores['doc1'], scores['doc2'])
    
    def test_highlight_matches(self):
        """Test match highlighting."""
        ft_index = FulltextIndex("articles", "content")
        
        text = "This is a long text about programming and database programming."
        query = "programming"
        
        highlighted = ft_index.highlight_matches(text, query)
        
        self.assertIn('**programming**', highlighted)
        self.assertLess(len(highlighted), len(text) + 50)  # Should be truncated


class TestFulltextIndexManager(unittest.TestCase):
    """Test full-text index manager."""
    
    def setUp(self):
        """Set up test database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db = Database(self.temp_dir, server_id=1)
        
        self.db.create_database("testdb")
        self.db.use_database("testdb")
        
        # Create table with text column
        self.db.create_table("articles", [
            {'name': 'id', 'type': 'INT', 'primary_key': True},
            {'name': 'title', 'type': 'TEXT'},
            {'name': 'content', 'type': 'TEXT'}
        ])
        
        # Insert test data
        self.db.insert("articles", [1, "Hello World", "This is a test article about programming"])
        self.db.insert("articles", [2, "Database Design", "Learn about database normalization"])
        self.db.insert("articles", [3, "Python Tutorial", "Programming in Python is fun"])
        
        self.ft_manager = FulltextIndexManager(self.db)
    
    def tearDown(self):
        """Clean up."""
        self.db.close()
        shutil.rmtree(self.temp_dir)
    
    def test_create_fulltext_index(self):
        """Test creating full-text index."""
        result = self.ft_manager.create_index("articles", "content")
        self.assertIn("created", result.lower())
        
        # Verify index exists
        index_key = b"_fulltext_index:articles:content"
        self.assertIsNotNone(self.db._db.get(index_key))
    
    def test_create_duplicate_index(self):
        """Test creating duplicate index fails."""
        self.ft_manager.create_index("articles", "content")
        
        result = self.ft_manager.create_index("articles", "content")
        self.assertIn("ERROR", result)
        self.assertIn("already exists", result.lower())
    
    def test_drop_fulltext_index(self):
        """Test dropping full-text index."""
        self.ft_manager.create_index("articles", "content")
        
        result = self.ft_manager.drop_index("articles", "content")
        self.assertIn("dropped", result.lower())
        
        # Verify index removed
        index_key = b"_fulltext_index:articles:content"
        self.assertIsNone(self.db._db.get(index_key))
    
    def test_search_natural_language(self):
        """Test natural language search via manager."""
        self.ft_manager.create_index("articles", "content")
        
        results = self.ft_manager.search("articles", ["content"], "programming", "NATURAL")
        
        self.assertGreater(len(results), 0)
        
        # Should find articles about programming
        doc_ids = [r[0] for r in results]
        self.assertIn('1', doc_ids)  # First article mentions programming
        self.assertIn('3', doc_ids)  # Third article about Python
    
    def test_search_boolean(self):
        """Test boolean search via manager."""
        self.ft_manager.create_index("articles", "content")
        
        # Search with boolean operators
        results = self.ft_manager.search("articles", ["content"], "+programming +python", "BOOLEAN")
        
        # Should find only article 3 (has both programming and python)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], '3')


class TestFulltextParser(unittest.TestCase):
    """Test full-text SQL parsing."""
    
    def setUp(self):
        self.parser = CommandParser()
    
    def test_parse_create_fulltext_index(self):
        """Test parsing CREATE FULLTEXT INDEX."""
        sql = "CREATE FULLTEXT INDEX idx_content ON articles(content)"
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'CREATE_FULLTEXT_INDEX')
        self.assertEqual(params['table'], 'articles')
        self.assertEqual(params['columns'], ['content'])
    
    def test_parse_create_fulltext_index_multiple_columns(self):
        """Test parsing CREATE FULLTEXT INDEX with multiple columns."""
        sql = "CREATE FULLTEXT INDEX idx_content ON articles(title, content)"
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(params['columns'], ['title', 'content'])
    
    def test_parse_drop_fulltext_index(self):
        """Test parsing DROP FULLTEXT INDEX."""
        sql = "DROP FULLTEXT INDEX idx_content ON articles"
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'DROP_FULLTEXT_INDEX')
        self.assertEqual(params['table'], 'articles')
    
    def test_parse_match_against(self):
        """Test parsing MATCH ... AGAINST."""
        sql = "MATCH (content) AGAINST ('programming')"
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(cmd_type, 'MATCH_AGAINST')
        self.assertEqual(params['columns'], ['content'])
        self.assertEqual(params['query'], 'programming')
        self.assertEqual(params['mode'], 'NATURAL')
    
    def test_parse_match_against_natural_language_mode(self):
        """Test parsing MATCH ... AGAINST with IN NATURAL LANGUAGE MODE."""
        sql = "MATCH (content) AGAINST ('programming' IN NATURAL LANGUAGE MODE)"
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(params['mode'], 'NATURAL')
    
    def test_parse_match_against_boolean_mode(self):
        """Test parsing MATCH ... AGAINST with IN BOOLEAN MODE."""
        sql = "MATCH (content) AGAINST ('+programming -python' IN BOOLEAN MODE)"
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(params['mode'], 'BOOLEAN')
        self.assertEqual(params['query'], '+programming -python')
    
    def test_parse_match_against_multiple_columns(self):
        """Test parsing MATCH ... AGAINST with multiple columns."""
        sql = "MATCH (title, content) AGAINST ('database')"
        cmd_type, params = self.parser.parse(sql)
        
        self.assertEqual(params['columns'], ['title', 'content'])


class TestFulltextEdgeCases(unittest.TestCase):
    """Test edge cases for full-text search."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db = Database(self.temp_dir, server_id=1)
        self.db.create_database("testdb")
        self.db.use_database("testdb")
        self.ft_manager = FulltextIndexManager(self.db)
    
    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.temp_dir)
    
    def test_empty_text_indexing(self):
        """Test indexing empty text."""
        ft_index = FulltextIndex("test", "content")
        
        entries = ft_index.index_document("doc1", "")
        self.assertEqual(len(entries), 0)
    
    def test_special_characters(self):
        """Test handling special characters."""
        ft_index = FulltextIndex("test", "content")
        
        text = "Hello! World? Test@#$%^&*()"
        tokens = ft_index.tokenize(text)
        
        self.assertIn('hello', tokens)
        self.assertIn('world', tokens)
        self.assertIn('test', tokens)
    
    def test_unicode_text(self):
        """Test handling unicode text."""
        ft_index = FulltextIndex("test", "content")
        
        text = "日本語のテキスト"
        tokens = ft_index.tokenize(text)
        
        # Should handle without error
        self.assertIsInstance(tokens, list)
    
    def test_case_insensitive(self):
        """Test case-insensitive indexing."""
        ft_index = FulltextIndex("test", "content")
        
        entries1 = ft_index.index_document("doc1", "HELLO World")
        entries2 = ft_index.index_document("doc2", "hello WORLD")
        
        # Both should stem to same term
        self.assertIn('hello', entries1)
        self.assertIn('hello', entries2)
    
    def test_stop_words_filtering(self):
        """Test stop words are filtered."""
        ft_index = FulltextIndex("test", "content")
        
        text = "The quick brown fox and the lazy dog"
        tokens = ft_index.tokenize(text)
        
        # Stop words should be removed
        self.assertNotIn('the', tokens)
        self.assertNotIn('and', tokens)
        
        # Content words should remain
        self.assertIn('quick', tokens)
        self.assertIn('brown', tokens)
        self.assertIn('fox', tokens)


if __name__ == '__main__':
    unittest.main(verbosity=2)
