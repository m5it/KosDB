"""
Full-Text Search for KosDB

Implements inverted index-based text search with tokenization,
stemming, and stop word removal. Supports hybrid text+semantic queries.
"""

import re
import json
import heapq
import threading
from typing import Dict, Any, List, Optional, Set, Tuple, Callable
from dataclasses import dataclass, field
from collections import defaultdict, Counter


# Common English stop words
DEFAULT_STOP_WORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from',
    'has', 'he', 'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the',
    'to', 'was', 'will', 'with', 'the', 'this', 'but', 'they', 'have',
    'had', 'what', 'said', 'each', 'which', 'their', 'time', 'would',
    'there', 'use', 'an', 'out', 'many', 'then', 'them', 'these', 'so',
    'some', 'her', 'make', 'like', 'into', 'him', 'has', 'two', 'more',
    'very', 'after', 'words', 'just', 'where', 'most', 'know', 'take',
    'than', 'only', 'think', 'also', 'back', 'after', 'use', 'two',
    'how', 'our', 'work', 'first', 'well', 'way', 'even', 'new', 'want',
    'because', 'any', 'these', 'give', 'day', 'most', 'us'
}


class Stemmer:
    """
    Simple Porter Stemmer implementation for English words.
    """
    
    def __init__(self):
        self.step2_suffixes = {
            'ational': 'ate', 'tional': 'tion', 'enci': 'ence',
            'anci': 'ance', 'izer': 'ize', 'abli': 'able',
            'alli': 'al', 'entli': 'ent', 'eli': 'e',
            'ousli': 'ous', 'ization': 'ize', 'ation': 'ate',
            'ator': 'ate', 'alism': 'al', 'iveness': 'ive',
            'fulness': 'ful', 'ousness': 'ous', 'aliti': 'al',
            'iviti': 'ive', 'biliti': 'ble'
        }
        self.step3_suffixes = {
            'icate': 'ic', 'ative': '', 'alize': 'al',
            'iciti': 'ic', 'ical': 'ic', 'ful': '',
            'ness': ''
        }
    
    def stem(self, word: str) -> str:
        """
        Stem a word to its root form.
        
        Args:
            word: Word to stem
        
        Returns:
            Stemmed word
        """
        if len(word) <= 2:
            return word
        
        word = word.lower()
        
        # Step 1a
        if word.endswith('sses'):
            word = word[:-2]
        elif word.endswith('ies'):
            word = word[:-2]
        elif word.endswith('ss'):
            pass
        elif word.endswith('s'):
            word = word[:-1]
        
        # Step 1b
        if word.endswith('eed'):
            if len(word) > 4:
                word = word[:-1]
        elif word.endswith('ed') and self._has_vowel(word[:-2]):
            word = word[:-2]
            word = self._step1b_helper(word)
        elif word.endswith('ing') and self._has_vowel(word[:-3]):
            word = word[:-3]
            word = self._step1b_helper(word)
        
        # Step 1c
        if word.endswith('y') and self._has_vowel(word[:-1]):
            word = word[:-1] + 'i'
        
        # Step 2
        for suffix, replacement in self.step2_suffixes.items():
            if word.endswith(suffix):
                if self._measure(word[:-len(suffix)]) > 0:
                    word = word[:-len(suffix)] + replacement
                break
        
        # Step 3
        for suffix, replacement in self.step3_suffixes.items():
            if word.endswith(suffix):
                if self._measure(word[:-len(suffix)]) > 0:
                    word = word[:-len(suffix)] + replacement
                break
        
        # Step 4
        step4_suffixes = ['al', 'ance', 'ence', 'er', 'ic', 'able', 
                          'ible', 'ant', 'ement', 'ment', 'ent', 'ion',
                          'ou', 'ism', 'ate', 'iti', 'ous', 'ive', 'ize']
        for suffix in step4_suffixes:
            if word.endswith(suffix):
                if self._measure(word[:-len(suffix)]) > 1:
                    word = word[:-len(suffix)]
                break
        
        # Step 5a
        if word.endswith('e'):
            if self._measure(word[:-1]) > 1:
                word = word[:-1]
            elif self._measure(word[:-1]) == 1 and not self._ends_cvc(word[:-1]):
                word = word[:-1]
        
        # Step 5b
        if self._measure(word) > 1 and word.endswith('l') and self._ends_double_consonant(word):
            word = word[:-1]
        
        return word
    
    def _has_vowel(self, word: str) -> bool:
        """Check if word contains a vowel."""
        return any(c in 'aeiou' for c in word)
    
    def _ends_double_consonant(self, word: str) -> bool:
        """Check if word ends with double consonant."""
        if len(word) < 2:
            return False
        return word[-1] == word[-2] and word[-1] not in 'aeiou'
    
    def _ends_cvc(self, word: str) -> bool:
        """Check if word ends with CVC pattern."""
        if len(word) < 3:
            return False
        return (word[-1] not in 'aeiou' and 
                word[-2] in 'aeiou' and 
                word[-3] not in 'aeiou' and
                word[-1] not in 'wxy')
    
    def _measure(self, word: str) -> int:
        """Calculate measure of word (VC pattern count)."""
        n = 0
        i = 0
        while i < len(word):
            # Skip consonants
            while i < len(word) and word[i] not in 'aeiou':
                i += 1
            if i >= len(word):
                break
            # Skip vowels
            while i < len(word) and word[i] in 'aeiou':
                i += 1
            n += 1
        return n
    
    def _step1b_helper(self, word: str) -> str:
        """Helper for step 1b."""
        if word.endswith('at') or word.endswith('bl') or word.endswith('iz'):
            word = word + 'e'
        elif self._ends_double_consonant(word) and not word.endswith('l') and not word.endswith('s') and not word.endswith('z'):
            word = word[:-1]
        elif self._measure(word) == 1 and self._ends_cvc(word):
            word = word + 'e'
        return word


@dataclass
class Document:
    """Document in full-text index."""
    doc_id: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __hash__(self):
        return hash(self.doc_id)
    
    def __eq__(self, other):
        if isinstance(other, Document):
            return self.doc_id == other.doc_id
        return False


class Tokenizer:
    """
    Text tokenizer with stemming and stop word removal.
    """
    
    def __init__(self, 
                 stop_words: Optional[Set[str]] = None,
                 stem: bool = True,
                 min_token_length: int = 2):
        self.stop_words = stop_words or DEFAULT_STOP_WORDS
        self.stemmer = Stemmer() if stem else None
        self.min_token_length = min_token_length
        self._token_pattern = re.compile(r'[a-zA-Z0-9]+')
    
    def tokenize(self, text: str) -> List[str]:
        """
        Tokenize text into terms.
        
        Args:
            text: Text to tokenize
        
        Returns:
            List of tokens
        """
        # Extract alphanumeric tokens
        tokens = self._token_pattern.findall(text.lower())
        
        # Filter by length and stop words
        tokens = [t for t in tokens 
                  if len(t) >= self.min_token_length and t not in self.stop_words]
        
        # Stem if enabled
        if self.stemmer:
            tokens = [self.stemmer.stem(t) for t in tokens]
        
        return tokens
    
    def tokenize_with_positions(self, text: str) -> List[Tuple[str, int]]:
        """
        Tokenize text with position information.
        
        Args:
            text: Text to tokenize
        
        Returns:
            List of (token, position) tuples
        """
        tokens = self.tokenize(text)
        return [(token, i) for i, token in enumerate(tokens)]


class InvertedIndex:
    """
    Inverted index for full-text search.
    """
    
    def __init__(self, tokenizer: Optional[Tokenizer] = None):
        self.tokenizer = tokenizer or Tokenizer()
        self._index: Dict[str, Set[str]] = defaultdict(set)
        self._documents: Dict[str, Document] = {}
        self._term_frequencies: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._doc_lengths: Dict[str, int] = {}
        self._lock = threading.RLock()
        self._avg_doc_length = 0.0
    
    def add_document(self, doc: Document) -> bool:
        """
        Add document to index.
        
        Args:
            doc: Document to add
        
        Returns:
            True if added successfully
        """
        with self._lock:
            # Tokenize text
            tokens = self.tokenizer.tokenize(doc.text)
            
            if not tokens:
                return False
            
            # Store document
            self._documents[doc.doc_id] = doc
            
            # Update index
            for token in set(tokens):
                self._index[token].add(doc.doc_id)
            
            # Update term frequencies
            token_counts = Counter(tokens)
            for token, count in token_counts.items():
                self._term_frequencies[token][doc.doc_id] = count
            
            # Update document length
            self._doc_lengths[doc.doc_id] = len(tokens)
            
            # Update average document length
            total_length = sum(self._doc_lengths.values())
            self._avg_doc_length = total_length / len(self._documents)
            
            return True
    
    def remove_document(self, doc_id: str) -> bool:
        """
        Remove document from index.
        
        Args:
            doc_id: Document ID to remove
        
        Returns:
            True if removed
        """
        with self._lock:
            if doc_id not in self._documents:
                return False
            
            doc = self._documents[doc_id]
            tokens = self.tokenizer.tokenize(doc.text)
            
            # Remove from index
            for token in set(tokens):
                self._index[token].discard(doc_id)
                if not self._index[token]:
                    del self._index[token]
            
            # Remove term frequencies
            for token in list(self._term_frequencies.keys()):
                if doc_id in self._term_frequencies[token]:
                    del self._term_frequencies[token][doc_id]
                    if not self._term_frequencies[token]:
                        del self._term_frequencies[token]
            
            # Remove document
            del self._documents[doc_id]
            del self._doc_lengths[doc_id]
            
            # Update average
            if self._documents:
                total_length = sum(self._doc_lengths.values())
                self._avg_doc_length = total_length / len(self._documents)
            else:
                self._avg_doc_length = 0.0
            
            return True
    
    def search(self, query: str, k: int = 10) -> List[Tuple[str, float]]:
        """
        Search for documents matching query.
        
        Args:
            query: Search query
            k: Number of results
        
        Returns:
            List of (doc_id, score) tuples
        """
        with self._lock:
            query_tokens = self.tokenizer.tokenize(query)
            
            if not query_tokens:
                return []
            
            # Find candidate documents
            candidate_docs = None
            for token in query_tokens:
                docs_with_token = self._index.get(token, set())
                if candidate_docs is None:
                    candidate_docs = docs_with_token.copy()
                else:
                    candidate_docs = candidate_docs & docs_with_token
            
            if not candidate_docs:
                # Try OR if no results with AND
                for token in query_tokens:
                    docs_with_token = self._index.get(token, set())
                    if candidate_docs is None:
                        candidate_docs = docs_with_token.copy()
                    else:
                        candidate_docs = candidate_docs | docs_with_token
            
            if not candidate_docs:
                return []
            
            # Score documents using BM25
            scores = []
            for doc_id in candidate_docs:
                score = self._bm25_score(doc_id, query_tokens)
                scores.append((doc_id, score))
            
            # Return top k
            scores.sort(key=lambda x: x[1], reverse=True)
            return scores[:k]
    
    def _bm25_score(self, doc_id: str, query_tokens: List[str], 
                    k1: float = 1.5, b: float = 0.75) -> float:
        """
        Calculate BM25 score for document.
        
        Args:
            doc_id: Document ID
            query_tokens: Query tokens
            k1: BM25 parameter
            b: BM25 parameter
        
        Returns:
            BM25 score
        """
        import math
        
        score = 0.0
        doc_length = self._doc_lengths.get(doc_id, 0)
        N = len(self._documents)
        
        for token in query_tokens:
            # Document frequency
            df = len(self._index.get(token, set()))
            if df == 0:
                continue
            
            # Term frequency in document
            tf = self._term_frequencies[token].get(doc_id, 0)
            
            # IDF
            idf = math.log((N - df + 0.5) / (df + 0.5) + 1)
            
            # BM25 term score
            tf_component = tf * (k1 + 1)
            length_component = tf + k1 * (1 - b + b * doc_length / self._avg_doc_length)
            
            score += idf * (tf_component / length_component)
        
        return score
    
    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        with self._lock:
            return {
                'num_documents': len(self._documents),
                'num_terms': len(self._index),
                'avg_doc_length': round(self._avg_doc_length, 2),
                'total_term_occurrences': sum(
                    sum(freqs.values()) for freqs in self._term_frequencies.values()
                )
            }
    
    def get_terms(self) -> List[str]:
        """Get list of indexed terms."""
        with self._lock:
            return list(self._index.keys())
    
    def get_document(self, doc_id: str) -> Optional[Document]:
        """Get document by ID."""
        with self._lock:
            return self._documents.get(doc_id)


class FullTextSearchEngine:
    """
    High-level full-text search engine.
    """
    
    def __init__(self):
        self._indexes: Dict[str, InvertedIndex] = {}
        self._lock = threading.RLock()
    
    def create_index(self, name: str, 
                     stop_words: Optional[Set[str]] = None,
                     stem: bool = True) -> InvertedIndex:
        """
        Create new full-text index.
        
        Args:
            name: Index name
            stop_words: Custom stop words
            stem: Enable stemming
        
        Returns:
            Created index
        """
        with self._lock:
            if name in self._indexes:
                raise ValueError(f"Index {name} already exists")
            
            tokenizer = Tokenizer(stop_words=stop_words, stem=stem)
            index = InvertedIndex(tokenizer)
            self._indexes[name] = index
            return index
    
    def get_index(self, name: str) -> Optional[InvertedIndex]:
        """Get index by name."""
        with self._lock:
            return self._indexes.get(name)
    
    def delete_index(self, name: str) -> bool:
        """Delete index."""
        with self._lock:
            if name not in self._indexes:
                return False
            del self._indexes[name]
            return True
    
    def search(self, index_name: str, query: str, k: int = 10) -> List[Tuple[str, float, str]]:
        """
        Search index and return results with text.
        
        Args:
            index_name: Index to search
            query: Search query
            k: Number of results
        
        Returns:
            List of (doc_id, score, text) tuples
        """
        index = self.get_index(index_name)
        if not index:
            raise ValueError(f"Index {index_name} not found")
        
        results = index.search(query, k)
        
        # Enrich with text
        enriched = []
        for doc_id, score in results:
            doc = index.get_document(doc_id)
            if doc:
                enriched.append((doc_id, score, doc.text))
        
        return enriched


class HybridSearcher:
    """
    Hybrid search combining full-text and vector search.
    """
    
    def __init__(self, 
                 text_engine: Optional[FullTextSearchEngine] = None,
                 vector_engine: Optional[Any] = None):
        self.text_engine = text_engine or FullTextSearchEngine()
        self.vector_engine = vector_engine
    
    def hybrid_search(self, 
                      text_query: str,
                      vector_query: Optional[List[float]] = None,
                      text_index: str = 'default',
                      vector_index: Optional[str] = None,
                      text_weight: float = 0.5,
                      vector_weight: float = 0.5,
                      k: int = 10) -> List[Dict[str, Any]]:
        """
        Perform hybrid search combining text and vector similarity.
        
        Args:
            text_query: Text search query
            vector_query: Optional vector embedding
            text_index: Name of text index
            vector_index: Name of vector index
            text_weight: Weight for text scores
            vector_weight: Weight for vector scores
            k: Number of results
        
        Returns:
            Combined search results
        """
        # Get text results
        text_results = self.text_engine.search(text_index, text_query, k * 2)
        text_scores = {doc_id: score for doc_id, score, _ in text_results}
        
        # Get vector results if available
        vector_scores = {}
        if vector_query and self.vector_engine and vector_index:
            try:
                vector_results = self.vector_engine.search(vector_index, vector_query, k * 2)
                vector_scores = {doc_id: score for doc_id, score in vector_results}
            except Exception as e:
                print(f"[HybridSearch] Vector search failed: {e}")
        
        # Combine scores
        all_docs = set(text_scores.keys()) | set(vector_scores.keys())
        combined = []
        
        for doc_id in all_docs:
            text_score = text_scores.get(doc_id, 0.0)
            vector_score = vector_scores.get(doc_id, 0.0)
            
            # Normalize scores (simple min-max would be better with full data)
            combined_score = (text_score * text_weight) + (vector_score * vector_weight)
            
            # Get document text
            doc_text = ""
            if doc_id in text_scores:
                for did, _, text in text_results:
                    if did == doc_id:
                        doc_text = text
                        break
            
            combined.append({
                'doc_id': doc_id,
                'text_score': text_score,
                'vector_score': vector_score,
                'combined_score': combined_score,
                'text': doc_text
            })
        
        # Sort by combined score
        combined.sort(key=lambda x: x['combined_score'], reverse=True)
        return combined[:k]


# Utility functions
def create_fulltext_index(name: str, 
                          stop_words: Optional[Set[str]] = None,
                          stem: bool = True) -> InvertedIndex:
    """
    Create a full-text index.
    
    Args:
        name: Index name
        stop_words: Custom stop words
        stem: Enable stemming
    
    Returns:
        Created index
    """
    engine = FullTextSearchEngine()
    return engine.create_index(name, stop_words, stem)


def tokenize_text(text: str, 
                  stop_words: Optional[Set[str]] = None,
                  stem: bool = True) -> List[str]:
    """
    Tokenize text with optional stemming.
    
    Args:
        text: Text to tokenize
        stop_words: Custom stop words
        stem: Enable stemming
    
    Returns:
        List of tokens
    """
    tokenizer = Tokenizer(stop_words=stop_words, stem=stem)
    return tokenizer.tokenize(text)
