"""
Tests for full-text search system.
"""

import unittest
from fulltext_search import (
    Stemmer, Tokenizer, Document, InvertedIndex,
    FullTextSearchEngine, HybridSearcher,
    tokenize_text, DEFAULT_STOP_WORDS
)

class TestStemmer(unittest.TestCase):
    def test_stem_basic(self):
        stemmer = Stemmer()
        
        self.assertEqual(stemmer.stem('running'), 'run')
        self.assertEqual(stemmer.stem('flies'), 'fli')
        self.assertEqual(stemmer.stem('dies'), 'di')  # Porter stemmer result
        self.assertEqual(stemmer.stem('cats'), 'cat')
    
    def test_stem_short_words(self):
        stemmer = Stemmer()
        
        self.assertEqual(stemmer.stem('a'), 'a')
        self.assertEqual(stemmer.stem('ab'), 'ab')
    
    def test_stem_national(self):
        stemmer = Stemmer()
        
        # Test step 2 suffixes with longer words
        self.assertEqual(stemmer.stem('rational'), 'ration')
        # 'tional' alone is too short to trigger stemming

class TestTokenizer(unittest.TestCase):
    def setUp(self):
        self.tokenizer = Tokenizer()
    
    def test_tokenize_basic(self):
        text = "The quick brown fox jumps over the lazy dog"
        tokens = self.tokenizer.tokenize(text)
        
        self.assertIn('quick', tokens)
        self.assertIn('brown', tokens)
        self.assertIn('fox', tokens)
        self.assertNotIn('the', tokens)  # Stop word
    
    def test_tokenize_with_punctuation(self):
        text = "Hello, world! This is a test."
        tokens = self.tokenizer.tokenize(text)
        
        self.assertIn('hello', tokens)
        self.assertIn('world', tokens)
        self.assertIn('test', tokens)
    
    def test_tokenize_min_length(self):
        tokenizer = Tokenizer(min_token_length=3)
        tokens = tokenizer.tokenize("a ab abc abcd")
        
        self.assertNotIn('a', tokens)
        self.assertNotIn('ab', tokens)
        self.assertIn('abc', tokens)
        self.assertIn('abcd', tokens)
    
    def test_tokenize_no_stem(self):
        tokenizer = Tokenizer(stem=False)
        tokens = tokenizer.tokenize("running cats")
        
        self.assertIn('running', tokens)
        self.assertIn('cats', tokens)
    
    def test_tokenize_custom_stop_words(self):
        tokenizer = Tokenizer(stop_words={'custom', 'words'})
        tokens = tokenizer.tokenize("custom words here")
        
        self.assertNotIn('custom', tokens)
        self.assertNotIn('words', tokens)
        self.assertIn('here', tokens)


class TestDocument(unittest.TestCase):
    def test_document_creation(self):
        doc = Document(doc_id='1', text='Hello world', metadata={'author': 'test'})
        
        self.assertEqual(doc.doc_id, '1')
        self.assertEqual(doc.text, 'Hello world')
        self.assertEqual(doc.metadata['author'], 'test')
    
    def test_document_equality(self):
        doc1 = Document(doc_id='1', text='text')
        doc2 = Document(doc_id='1', text='different')
        doc3 = Document(doc_id='2', text='text')
        
        self.assertEqual(doc1, doc2)  # Same ID
        self.assertNotEqual(doc1, doc3)  # Different ID


class TestInvertedIndex(unittest.TestCase):
    def setUp(self):
        self.index = InvertedIndex()
    
    def test_add_document(self):
        doc = Document(doc_id='1', text='The quick brown fox')
        success = self.index.add_document(doc)
        
        self.assertTrue(success)
        self.assertEqual(len(self.index._documents), 1)
        self.assertIn('quick', self.index._index)
        self.assertIn('brown', self.index._index)
        self.assertIn('fox', self.index._index)
    
    def test_add_empty_document(self):
        doc = Document(doc_id='1', text='the a an')  # Only stop words
        success = self.index.add_document(doc)
        
        self.assertFalse(success)
    
    def test_remove_document(self):
        doc = Document(doc_id='1', text='quick brown fox')
        self.index.add_document(doc)
        
        success = self.index.remove_document('1')
        self.assertTrue(success)
        self.assertEqual(len(self.index._documents), 0)
        self.assertNotIn('1', self.index._index.get('quick', set()))
    
    def test_search_basic(self):
        self.index.add_document(Document('1', 'quick brown fox'))
        self.index.add_document(Document('2', 'lazy dog'))
        self.index.add_document(Document('3', 'quick dog'))
        
        results = self.index.search('quick')
        
        self.assertEqual(len(results), 2)
        doc_ids = [r[0] for r in results]
        self.assertIn('1', doc_ids)
        self.assertIn('3', doc_ids)
    
    def test_search_multiple_terms(self):
        self.index.add_document(Document('1', 'quick brown fox'))
        self.index.add_document(Document('2', 'quick lazy dog'))
        
        results = self.index.search('quick brown')
        
        # Should prefer doc with both terms
        self.assertEqual(results[0][0], '1')
    
    def test_search_no_results(self):
        self.index.add_document(Document('1', 'quick brown fox'))
        
        results = self.index.search('elephant')
        
        self.assertEqual(len(results), 0)
    
    def test_get_stats(self):
        self.index.add_document(Document('1', 'quick brown fox'))
        self.index.add_document(Document('2', 'lazy dog'))
        
        stats = self.index.get_stats()
        
        self.assertEqual(stats['num_documents'], 2)
        self.assertGreater(stats['num_terms'], 0)
        self.assertGreater(stats['avg_doc_length'], 0)
    
    def test_bm25_scoring(self):
        # Add multiple documents to test scoring
        for i in range(10):
            self.index.add_document(Document(str(i), 'common word unique' + str(i)))
        
        # Add document with more occurrences
        self.index.add_document(Document('special', 'common common common word'))
        
        results = self.index.search('common')
        
        # Document with more occurrences should rank higher
        doc_ids = [r[0] for r in results]
        self.assertIn('special', doc_ids[:3])


class TestFullTextSearchEngine(unittest.TestCase):
    def setUp(self):
        self.engine = FullTextSearchEngine()
    
    def test_create_index(self):
        index = self.engine.create_index('test_idx')
        self.assertIsNotNone(index)
        self.assertIn('test_idx', self.engine._indexes)
    
    def test_create_duplicate_index(self):
        self.engine.create_index('test_idx')
        
        with self.assertRaises(ValueError):
            self.engine.create_index('test_idx')
    
    def test_get_index(self):
        self.engine.create_index('test_idx')
        index = self.engine.get_index('test_idx')
        
        self.assertIsNotNone(index)
    
    def test_delete_index(self):
        self.engine.create_index('test_idx')
        success = self.engine.delete_index('test_idx')
        
        self.assertTrue(success)
        self.assertNotIn('test_idx', self.engine._indexes)
    
    def test_search_integration(self):
        self.engine.create_index('articles')
        index = self.engine.get_index('articles')
        
        index.add_document(Document('1', 'Python programming tutorial'))
        index.add_document(Document('2', 'Java programming guide'))
        
        results = self.engine.search('articles', 'python', k=2)
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], '1')
        self.assertIn('Python', results[0][2])


class TestHybridSearcher(unittest.TestCase):
    def setUp(self):
        self.text_engine = FullTextSearchEngine()
        self.searcher = HybridSearcher(text_engine=self.text_engine)
    
    def test_hybrid_search_text_only(self):
        self.text_engine.create_index('docs')
        index = self.text_engine.get_index('docs')
        
        index.add_document(Document('1', 'Python programming language'))
        index.add_document(Document('2', 'Java programming language'))
        
        results = self.searcher.hybrid_search(
            text_query='python',
            text_index='docs',
            text_weight=1.0,
            vector_weight=0.0
        )
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['doc_id'], '1')
    
    def test_hybrid_search_combines_scores(self):
        self.text_engine.create_index('docs')
        index = self.text_engine.get_index('docs')
        
        index.add_document(Document('1', 'Python programming'))
        
        results = self.searcher.hybrid_search(
            text_query='python',
            text_index='docs',
            text_weight=0.5,
            vector_weight=0.5
        )
        
        self.assertEqual(len(results), 1)
        self.assertIn('text_score', results[0])
        self.assertIn('combined_score', results[0])


class TestUtilityFunctions(unittest.TestCase):
    def test_tokenize_text(self):
        tokens = tokenize_text("The quick brown fox")
        
        self.assertIn('quick', tokens)
        self.assertIn('brown', tokens)
        self.assertNotIn('the', tokens)
    def test_default_stop_words(self):
        self.assertIn('the', DEFAULT_STOP_WORDS)
        self.assertIn('and', DEFAULT_STOP_WORDS)
        self.assertIn('for', DEFAULT_STOP_WORDS)
