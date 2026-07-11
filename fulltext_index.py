"""
Full-Text Search Module for KosDB v3.2.0

Provides full-text indexing and search capabilities with:
- Inverted index storage
- Tokenization and stemming
- Natural language and boolean search modes
- Relevance scoring and ranking
"""

import re
import json
import math
from typing import Dict, List, Set, Tuple, Optional, Any
from collections import defaultdict


class FulltextIndex:
    """
    Full-text index for efficient text search.
    
    Uses inverted index structure:
    - word -> {doc_id: frequency, positions: [list]}
    """
    
    def __init__(self, table_name: str, column_name: str):
        self.table_name = table_name
        self.column_name = column_name
        self.index_name = f"_fulltext:{table_name}:{column_name}"
        
        # Stop words to ignore
        self.stop_words = {
            'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to',
            'for', 'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were',
            'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
            'will', 'would', 'could', 'should', 'may', 'might', 'must',
            'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it',
            'we', 'they', 'my', 'your', 'his', 'her', 'its', 'our', 'their'
        }
        
        # Simple stemming rules (suffix removal)
        self.stemming_rules = [
            (r'ies$', 'y'),      # babies -> baby
            (r'ied$', 'y'),      # married -> marry
            (r'ying$', 'ie'),    # trying -> trie
            (r'ing$', ''),       # running -> run
            (r'ly$', ''),        # quickly -> quick
            (r'ed$', ''),        # walked -> walk
            (r's$', ''),         # books -> book
        ]
    
    def tokenize(self, text: str) -> List[str]:
        """
        Tokenize text into words.
        
        Args:
            text: Text to tokenize
        
        Returns:
            List of tokens
        """
        if not text:
            return []
        
        # Convert to lowercase
        text = text.lower()
        
        # Replace non-alphanumeric with spaces
        text = re.sub(r'[^a-z0-9\s]', ' ', text)
        
        # Split into words
        words = text.split()
        
        # Filter stop words and short words
        words = [w for w in words if len(w) > 2 and w not in self.stop_words]
        
        return words
    
    def stem(self, word: str) -> str:
        """
        Apply simple stemming to word.
        
        Args:
            word: Word to stem
        
        Returns:
            Stemmed word
        """
        for pattern, replacement in self.stemming_rules:
            if re.search(pattern, word):
                return re.sub(pattern, replacement, word)
        return word
    
    def index_document(self, doc_id: str, text: str) -> Dict[str, Any]:
        """
        Create index entries for a document.
        
        Args:
            doc_id: Document ID
            text: Document text
        
        Returns:
            Index entries dict
        """
        tokens = self.tokenize(text)
        entries = {}
        
        for position, token in enumerate(tokens):
            stemmed = self.stem(token)
            
            if stemmed not in entries:
                entries[stemmed] = {
                    'doc_ids': {},
                    'total_count': 0
                }
            
            if doc_id not in entries[stemmed]['doc_ids']:
                entries[stemmed]['doc_ids'][doc_id] = {
                    'frequency': 0,
                    'positions': []
                }
            
            entries[stemmed]['doc_ids'][doc_id]['frequency'] += 1
            entries[stemmed]['doc_ids'][doc_id]['positions'].append(position)
            entries[stemmed]['total_count'] += 1
        
        return entries
    
    def calculate_tf_idf(self, term: str, doc_id: str, total_docs: int, 
                         index_data: Dict) -> float:
        """
        Calculate TF-IDF score for a term in a document.
        
        Args:
            term: Search term
            doc_id: Document ID
            total_docs: Total number of documents
            index_data: Index data for the term
        
        Returns:
            TF-IDF score
        """
        if term not in index_data:
            return 0.0
        
        doc_data = index_data[term]['doc_ids'].get(doc_id)
        if not doc_data:
            return 0.0
        
        # Term Frequency (normalized)
        tf = doc_data['frequency']
        
        # Document Frequency
        df = len(index_data[term]['doc_ids'])
        
        # Inverse Document Frequency
        idf = math.log((total_docs + 1) / (df + 1)) + 1
        
        return tf * idf
    
    def search_natural_language(self, query: str, index_data: Dict, 
                                total_docs: int) -> List[Tuple[str, float]]:
        """
        Search using natural language mode.
        
        Args:
            query: Search query
            index_data: Current index data
            total_docs: Total document count
        
        Returns:
            List of (doc_id, score) tuples sorted by relevance
        """
        tokens = self.tokenize(query)
        if not tokens:
            return []
        
        scores = defaultdict(float)
        
        for token in tokens:
            stemmed = self.stem(token)
            
            # Get documents containing this term
            if stemmed in index_data:
                for doc_id in index_data[stemmed]['doc_ids']:
                    score = self.calculate_tf_idf(stemmed, doc_id, total_docs, index_data)
                    scores[doc_id] += score
        
        # Sort by score descending
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)
    
    def search_boolean(self, query: str, index_data: Dict, 
                       total_docs: int) -> List[Tuple[str, float]]:
        """
        Search using boolean mode.
        
        Supports:
        - +word (must include)
        - -word (must exclude)
        - word (optional)
        
        Args:
            query: Search query
            index_data: Current index data
            total_docs: Total document count
        
        Returns:
            List of (doc_id, score) tuples
        """
        # Parse boolean query
        must_include = set()
        must_exclude = set()
        optional = []
        
        tokens = query.split()
        for token in tokens:
            if token.startswith('+'):
                word = token[1:].lower()
                must_include.add(self.stem(word))
            elif token.startswith('-'):
                word = token[1:].lower()
                must_exclude.add(self.stem(word))
            else:
                word = token.lower()
                optional.append(self.stem(word))
        
        # Get candidate documents
        candidates = set()
        if must_include:
            # Start with documents containing first required term
            first_term = next(iter(must_include))
            if first_term in index_data:
                candidates = set(index_data[first_term]['doc_ids'].keys())
            else:
                return []
            
            # Intersect with other required terms
            for term in must_include:
                if term in index_data:
                    candidates &= set(index_data[term]['doc_ids'].keys())
                else:
                    return []
        elif optional:
            # Use optional terms
            for term in optional:
                if term in index_data:
                    candidates |= set(index_data[term]['doc_ids'].keys())
        
        # Filter out excluded documents
        for term in must_exclude:
            if term in index_data:
                candidates -= set(index_data[term]['doc_ids'].keys())
        
        # Score remaining documents
        scores = []
        for doc_id in candidates:
            score = 0.0
            for term in must_include | set(optional):
                if term in index_data:
                    score += self.calculate_tf_idf(term, doc_id, total_docs, index_data)
            scores.append((doc_id, score))
        
        return sorted(scores, key=lambda x: x[1], reverse=True)
    
    def search_with_expansion(self, query: str, index_data: Dict, 
                             total_docs: int) -> List[Tuple[str, float]]:
        """
        Search with query expansion.
        
        First finds documents matching query, then finds similar documents
        based on shared terms.
        
        Args:
            query: Search query
            index_data: Current index data
            total_docs: Total document count
        
        Returns:
            List of (doc_id, score) tuples
        """
        # Get initial results
        initial_results = self.search_natural_language(query, index_data, total_docs)
        
        if not initial_results:
            return []
        
        # Get top documents
        top_docs = [doc_id for doc_id, _ in initial_results[:5]]
        
        # Find expansion terms from top documents
        expansion_terms = defaultdict(int)
        for doc_id in top_docs:
            for term, data in index_data.items():
                if doc_id in data['doc_ids']:
                    expansion_terms[term] += data['doc_ids'][doc_id]['frequency']
        
        # Remove original query terms
        query_tokens = set(self.stem(t) for t in self.tokenize(query))
        for term in query_tokens:
            expansion_terms.pop(term, None)
        
        # Get top expansion terms
        top_expansion = sorted(expansion_terms.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # Create expanded query
        expanded_query = query + ' ' + ' '.join(term for term, _ in top_expansion)
        
        # Search with expanded query
        return self.search_natural_language(expanded_query, index_data, total_docs)
    
    def highlight_matches(self, text: str, query: str, max_length: int = 200) -> str:
        """
        Highlight search terms in text.
        
        Args:
            text: Original text
            query: Search query
            max_length: Maximum length of snippet
        
        Returns:
            Text with search terms highlighted
        """
        tokens = self.tokenize(query)
        if not tokens:
            return text[:max_length]
        
        # Find first occurrence
        text_lower = text.lower()
        positions = []
        
        for token in tokens:
            pos = text_lower.find(token)
            if pos >= 0:
                positions.append(pos)
        
        if not positions:
            return text[:max_length]
        
        # Extract snippet around first match
        start = max(0, min(positions) - 50)
        end = min(len(text), start + max_length)
        
        snippet = text[start:end]
        
        # Highlight terms
        for token in tokens:
            pattern = re.compile(re.escape(token), re.IGNORECASE)
            snippet = pattern.sub(f'**{token}**', snippet)
        
        return snippet


class FulltextIndexManager:
    """
    Manager for full-text indexes across tables.
    """
    
    def __init__(self, db):
        self.db = db
        self.indexes = {}  # table -> {column -> FulltextIndex}
    
    def create_index(self, table_name: str, column_name: str) -> str:
        """
        Create a full-text index on a column.
        
        Args:
            table_name: Table name
            column_name: Column name
        
        Returns:
            Success message or error
        """
        # Check if table exists
        schema_key = f"_schema:{table_name}".encode()
        if not self.db._db.get(schema_key):
            return f"ERROR: Table '{table_name}' does not exist"
        
        # Check if index already exists
        index_key = f"_fulltext_index:{table_name}:{column_name}".encode()
        if self.db._db.get(index_key):
            return f"ERROR: Full-text index already exists on {table_name}.{column_name}"
        
        # Create index metadata
        index_meta = {
            'table': table_name,
            'column': column_name,
            'created_at': time.time()
        }
        self.db._db.put(index_key, json.dumps(index_meta).encode())
        
        # Initialize empty inverted index
        ft_index = FulltextIndex(table_name, column_name)
        self.db._db.put(ft_index.index_name.encode(), json.dumps({}).encode())
        
        # Index existing data
        self._index_existing_data(table_name, column_name, ft_index)
        
        # Add to schema
        schema_data = self.db._db.get(schema_key)
        schema = json.loads(schema_data.decode())
        if 'fulltext_indexes' not in schema:
            schema['fulltext_indexes'] = []
        schema['fulltext_indexes'].append(column_name)
        self.db._db.put(schema_key, json.dumps(schema).encode())
        
        return f"Full-text index created on {table_name}({column_name})"
    
    def _index_existing_data(self, table_name: str, column_name: str, 
                              ft_index: FulltextIndex):
        """Index existing data in table."""
        index_data = {}
        
        prefix = f"{table_name}:".encode()
        for key, value in self.db._db.iterator(prefix=prefix):
            if key.startswith(f"_schema:{table_name}".encode()):
                continue
            
            row = json.loads(value.decode())
            doc_id = key.decode().split(':', 1)[1]
            
            if column_name in row and row[column_name]:
                entries = ft_index.index_document(doc_id, str(row[column_name]))
                
                # Merge into index_data
                for term, data in entries.items():
                    if term not in index_data:
                        index_data[term] = data
                    else:
                        # Merge doc_ids
                        for did, ddata in data['doc_ids'].items():
                            if did not in index_data[term]['doc_ids']:
                                index_data[term]['doc_ids'][did] = ddata
                                index_data[term]['total_count'] += ddata['frequency']
        
        # Save index
        self.db._db.put(ft_index.index_name.encode(), json.dumps(index_data).encode())
    
    def drop_index(self, table_name: str, column_name: str) -> str:
        """
        Drop a full-text index.
        
        Args:
            table_name: Table name
            column_name: Column name
        
        Returns:
            Success message or error
        """
        index_key = f"_fulltext_index:{table_name}:{column_name}".encode()
        if not self.db._db.get(index_key):
            return f"ERROR: Full-text index does not exist on {table_name}.{column_name}"
        
        # Delete index data
        ft_index = FulltextIndex(table_name, column_name)
        self.db._db.delete(ft_index.index_name.encode())
        self.db._db.delete(index_key)
        
        # Remove from schema
        schema_key = f"_schema:{table_name}".encode()
        schema_data = self.db._db.get(schema_key)
        if schema_data:
            schema = json.loads(schema_data.decode())
            if 'fulltext_indexes' in schema and column_name in schema['fulltext_indexes']:
                schema['fulltext_indexes'].remove(column_name)
                self.db._db.put(schema_key, json.dumps(schema).encode())
        
        return f"Full-text index dropped from {table_name}({column_name})"
    
    def search(self, table_name: str, columns: List[str], query: str, 
               mode: str = 'NATURAL') -> List[Tuple[str, float]]:
        """
        Search full-text index.
        
        Args:
            table_name: Table name
            columns: Columns to search
            query: Search query
            mode: Search mode (NATURAL, BOOLEAN, EXPANSION)
        
        Returns:
            List of (doc_id, score) tuples
        """
        all_results = []
        
        for column_name in columns:
            # Check if index exists
            index_key = f"_fulltext_index:{table_name}:{column_name}".encode()
            if not self.db._db.get(index_key):
                continue
            
            # Load index data
            ft_index = FulltextIndex(table_name, column_name)
            index_data_raw = self.db._db.get(ft_index.index_name.encode())
            if not index_data_raw:
                continue
            
            index_data = json.loads(index_data_raw.decode())
            
            # Count total documents
            total_docs = 0
            prefix = f"{table_name}:".encode()
            for key, _ in self.db._db.iterator(prefix=prefix):
                if not key.startswith(f"_schema:{table_name}".encode()):
                    total_docs += 1
            
            # Search based on mode
            if mode.upper() == 'BOOLEAN':
                results = ft_index.search_boolean(query, index_data, total_docs)
            elif mode.upper() == 'EXPANSION':
                results = ft_index.search_with_expansion(query, index_data, total_docs)
            else:  # NATURAL
                results = ft_index.search_natural_language(query, index_data, total_docs)
            
            all_results.extend(results)
        
        # Merge results from multiple columns
        merged = defaultdict(float)
        for doc_id, score in all_results:
            merged[doc_id] += score
        
        return sorted(merged.items(), key=lambda x: x[1], reverse=True)
    
    def update_index(self, table_name: str, column_name: str, 
                     doc_id: str, old_text: Optional[str], new_text: str):
        """
        Update index when document changes.
        
        Args:
            table_name: Table name
            column_name: Column name
            doc_id: Document ID
            old_text: Previous text (None if new)
            new_text: New text
        """
        index_key = f"_fulltext_index:{table_name}:{column_name}".encode()
        if not self.db._db.get(index_key):
            return
        
        ft_index = FulltextIndex(table_name, column_name)
        index_data_raw = self.db._db.get(ft_index.index_name.encode())
        if not index_data_raw:
            return
        
        index_data = json.loads(index_data_raw.decode())
        
        # Remove old entries
        if old_text:
            old_tokens = ft_index.tokenize(old_text)
            for token in old_tokens:
                stemmed = ft_index.stem(token)
                if stemmed in index_data and doc_id in index_data[stemmed]['doc_ids']:
                    del index_data[stemmed]['doc_ids'][doc_id]
                    index_data[stemmed]['total_count'] -= 1
        
        # Add new entries
        new_entries = ft_index.index_document(doc_id, new_text)
        for term, data in new_entries.items():
            if term not in index_data:
                index_data[term] = data
            else:
                index_data[term]['doc_ids'][doc_id] = data['doc_ids'][doc_id]
                index_data[term]['total_count'] += data['doc_ids'][doc_id]['frequency']
        
        # Save updated index
        self.db._db.put(ft_index.index_name.encode(), json.dumps(index_data).encode())


# Import time here to avoid circular import
import time
