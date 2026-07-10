"""
Tests for vector similarity search system.
"""

import unittest
import math
from typing import List
from vector_search import (
    DistanceMetric, VectorDocument, VectorIndex,
    VectorSearchEngine, EmbeddingGenerator, SemanticSearcher,
    normalize_vector, cosine_similarity, euclidean_distance, dot_product
)


class TestDistanceFunctions(unittest.TestCase):
    def test_cosine_similarity_identical(self):
        v = [1.0, 0.0, 0.0]
        self.assertAlmostEqual(cosine_similarity(v, v), 1.0)
    
    def test_cosine_similarity_orthogonal(self):
        v1 = [1.0, 0.0]
        v2 = [0.0, 1.0]
        self.assertAlmostEqual(cosine_similarity(v1, v2), 0.0)
    
    def test_cosine_similarity_opposite(self):
        v1 = [1.0, 0.0]
        v2 = [-1.0, 0.0]
        self.assertAlmostEqual(cosine_similarity(v1, v2), -1.0)
    
    def test_euclidean_distance(self):
        v1 = [0.0, 0.0]
        v2 = [3.0, 4.0]
        self.assertAlmostEqual(euclidean_distance(v1, v2), 5.0)
    
    def test_dot_product(self):
        v1 = [1.0, 2.0, 3.0]
        v2 = [4.0, 5.0, 6.0]
        self.assertEqual(dot_product(v1, v2), 32.0)
    
    def test_normalize_vector(self):
        v = [3.0, 4.0]
        normalized = normalize_vector(v)
        self.assertAlmostEqual(math.sqrt(sum(x*x for x in normalized)), 1.0)


class TestVectorDocument(unittest.TestCase):
    def test_document_creation(self):
        doc = VectorDocument(
            doc_id="doc1",
            vector=[1.0, 2.0, 3.0],
            metadata={"title": "Test"}
        )
        
        self.assertEqual(doc.doc_id, "doc1")
        self.assertEqual(len(doc.vector), 3)
        self.assertEqual(doc.metadata["title"], "Test")
    
    def test_normalize(self):
        doc = VectorDocument("doc1", [3.0, 4.0])
        normalized = doc.normalize()
        
        self.assertAlmostEqual(math.sqrt(sum(x*x for x in normalized)), 1.0)


class TestVectorIndex(unittest.TestCase):
    def setUp(self):
        self.index = VectorIndex(dimension=3, metric=DistanceMetric.COSINE)
    
    def test_add_document(self):
        success = self.index.add("doc1", [1.0, 0.0, 0.0])
        self.assertTrue(success)
        self.assertEqual(len(self.index._documents), 1)
    
    def test_add_wrong_dimension(self):
        with self.assertRaises(ValueError):
            self.index.add("doc1", [1.0, 2.0])  # Wrong dimension
    
    def test_remove_document(self):
        self.index.add("doc1", [1.0, 0.0, 0.0])
        success = self.index.remove("doc1")
        self.assertTrue(success)
        self.assertEqual(len(self.index._documents), 0)
    
    def test_remove_nonexistent(self):
        success = self.index.remove("nonexistent")
        self.assertFalse(success)
    
    def test_brute_force_search(self):
        # Add documents
        self.index.add("doc1", [1.0, 0.0, 0.0])
        self.index.add("doc2", [0.0, 1.0, 0.0])
        self.index.add("doc3", [0.9, 0.1, 0.0])
        
        # Search
        results = self.index.search([1.0, 0.0, 0.0], k=2)
        
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0][0], "doc1")  # Most similar
        self.assertGreater(results[0][1], 0.99)  # High similarity
    
    def test_search_with_filter(self):
        self.index.add("doc1", [1.0, 0.0, 0.0], {"category": "A"})
        self.index.add("doc2", [0.9, 0.1, 0.0], {"category": "B"})
        
        def filter_fn(doc):
            return doc.metadata.get("category") == "A"
        
        results = self.index.search([1.0, 0.0, 0.0], k=2, filter_fn=filter_fn)
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], "doc1")
    
    def test_euclidean_metric(self):
        index = VectorIndex(dimension=2, metric=DistanceMetric.EUCLIDEAN)
        index.add("doc1", [0.0, 0.0])
        index.add("doc2", [3.0, 4.0])
        
        results = index.search([0.0, 0.0], k=2)
        
        # doc1 should be closest (smallest distance = highest score)
        self.assertEqual(results[0][0], "doc1")
    
    def test_dot_product_metric(self):
        index = VectorIndex(dimension=2, metric=DistanceMetric.DOT_PRODUCT)
        index.add("doc1", [2.0, 0.0])
        index.add("doc2", [1.0, 1.0])
        
        results = index.search([1.0, 0.0], k=2)
        
        # doc1 has higher dot product
        self.assertEqual(results[0][0], "doc1")
    
    def test_get_stats(self):
        self.index.add("doc1", [1.0, 0.0, 0.0])
        stats = self.index.get_stats()
        
        self.assertEqual(stats["dimension"], 3)
        self.assertEqual(stats["metric"], "COSINE")
        self.assertEqual(stats["num_documents"], 1)
        self.assertFalse(stats["is_trained"])


class TestVectorIndexIVF(unittest.TestCase):
    def test_train_ivf(self):
        index = VectorIndex(dimension=2)
        
        # Add documents
        for i in range(20):
            index.add(f"doc{i}", [float(i), float(i % 3)])
        
        # Train IVF
        index.train_ivf(n_clusters=3)
        
        self.assertTrue(index._is_trained)
        self.assertEqual(index._n_clusters, 3)
        self.assertEqual(len(index._centroids), 3)
    
    def test_ivf_search(self):
        index = VectorIndex(dimension=2)
        
        # Add documents
        for i in range(20):
            index.add(f"doc{i}", [float(i), 0.0])
        
        # Train and search
        index.train_ivf(n_clusters=3)
        results = index.search([5.0, 0.0], k=5)
        
        self.assertEqual(len(results), 5)
        # Check that doc5 is in results (should be most similar)
        doc_ids = [r[0] for r in results]
        self.assertIn("doc5", doc_ids)


class TestVectorSearchEngine(unittest.TestCase):
    def setUp(self):
        self.engine = VectorSearchEngine()
    
    def test_create_index(self):
        index = self.engine.create_index("test", dimension=128)
        self.assertIsNotNone(index)
        self.assertIn("test", self.engine._indexes)
    
    def test_create_duplicate_index(self):
        self.engine.create_index("test", dimension=128)
        with self.assertRaises(ValueError):
            self.engine.create_index("test", dimension=64)
    
    def test_get_index(self):
        self.engine.create_index("test", dimension=128)
        index = self.engine.get_index("test")
        self.assertIsNotNone(index)
    
    def test_delete_index(self):
        self.engine.create_index("test", dimension=128)
        success = self.engine.delete_index("test")
        self.assertTrue(success)
        self.assertNotIn("test", self.engine._indexes)
    
    def test_list_indexes(self):
        self.engine.create_index("idx1", dimension=128)
        self.engine.create_index("idx2", dimension=64)
        
        names = self.engine.list_indexes()
        self.assertEqual(sorted(names), ["idx1", "idx2"])
    
    def test_search(self):
        self.engine.create_index("test", dimension=3)
        index = self.engine.get_index("test")
        
        index.add("doc1", [1.0, 0.0, 0.0])
        index.add("doc2", [0.0, 1.0, 0.0])
        
        results = self.engine.search("test", [1.0, 0.0, 0.0], k=2)
        self.assertEqual(len(results), 2)
    
    def test_hybrid_search(self):
        self.engine.create_index("test", dimension=3)
        index = self.engine.get_index("test")
        
        index.add("doc1", [1.0, 0.0, 0.0], {"text": "hello world"})
        index.add("doc2", [0.9, 0.1, 0.0], {"text": "goodbye world"})
        
        results = self.engine.hybrid_search(
            "test", 
            [1.0, 0.0, 0.0],
            keyword_filter="hello",
            k=2
        )
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], "doc1")


class TestEmbeddingGenerator(unittest.TestCase):
    def setUp(self):
        self.gen = EmbeddingGenerator(dimension=128)
    
    def test_encode(self):
        embedding = self.gen.encode("test text")
        self.assertEqual(len(embedding), 128)
    
    def test_encode_deterministic(self):
        # Same text should give same embedding (with fixed seed)
        emb1 = self.gen.encode("hello")
        emb2 = self.gen.encode("hello")
        self.assertEqual(emb1, emb2)
    
    def test_encode_different(self):
        # Different text should give different embedding
        emb1 = self.gen.encode("hello")
        emb2 = self.gen.encode("world")
        self.assertNotEqual(emb1, emb2)
    
    def test_encode_batch(self):
        embeddings = self.gen.encode_batch(["text1", "text2", "text3"])
        self.assertEqual(len(embeddings), 3)
        self.assertEqual(len(embeddings[0]), 128)


class TestSemanticSearcher(unittest.TestCase):
    def setUp(self):
        self.searcher = SemanticSearcher()
        self.searcher.engine.create_index("docs", dimension=128)
    
    def test_index_and_search(self):
        self.searcher.index_document(
            "docs",
            "doc1",
            "The quick brown fox",
            {"category": "animals"}
        )
        
        self.searcher.index_document(
            "docs",
            "doc2",
            "Machine learning is powerful",
            {"category": "tech"}
        )
        
        results = self.searcher.search("docs", "fox animal", k=2)
        
        self.assertGreater(len(results), 0)
        # Check results have expected structure
        self.assertIn("doc_id", results[0])
        self.assertIn("score", results[0])
        self.assertIn("metadata", results[0])
    
    def test_search_returns_metadata(self):
        self.searcher.index_document(
            "docs",
            "doc1",
            "Test content",
            {"author": "Alice"}
        )
        
        results = self.searcher.search("docs", "test", k=1)
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["metadata"]["author"], "Alice")
        self.assertIn("text", results[0]["metadata"])


class TestIntegration(unittest.TestCase):
    def test_full_workflow(self):
        # Create engine and index
        engine = VectorSearchEngine()
        engine.create_index("articles", dimension=10)
        
        # Add documents
        index = engine.get_index("articles")
        index.add("art1", [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                 {"title": "Python Programming", "category": "tech"})
        index.add("art2", [0.9, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                 {"title": "Java Development", "category": "tech"})
        index.add("art3", [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                 {"title": "Cooking Recipes", "category": "food"})
        
        # Train IVF for faster search
        index.train_ivf(n_clusters=2)
        
        # Search
        results = engine.search("articles", 
                               [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                               k=2)
        
        self.assertEqual(len(results), 2)
        # Both tech articles should be most similar
        self.assertIn(results[0][0], ["art1", "art2"])
        
        # Filter by category
        def filter_fn(doc):
            return doc.metadata.get("category") == "food"
        
        results = index.search([0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                              k=3, filter_fn=filter_fn)
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], "art3")


if __name__ == '__main__':
    unittest.main(verbosity=2)
