"""
Tests for streaming results.
"""

import unittest
import time
import threading
import io
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from streaming_results import (
    StreamState, StreamChunk, ResultCursor,
    StreamingResultSet, StreamingQueryExecutor,
    JSONStreamEncoder, StreamingResponse,
    stream_large_query, chunked_export
)


class MockDataSource:
    """Mock data source for testing."""
    def __init__(self, count=100):
        self.count = count
    
    def __iter__(self):
        for i in range(self.count):
            yield {'id': i, 'value': f'item_{i}'}


class TestStreamChunk(unittest.TestCase):
    def test_chunk_creation(self):
        chunk = StreamChunk(
            chunk_id=1,
            data=[{'id': 1}, {'id': 2}],
            is_last=False
        )
        
        self.assertEqual(chunk.chunk_id, 1)
        self.assertEqual(chunk.size, 2)
        self.assertFalse(chunk.is_last)
    
    def test_chunk_to_dict(self):
        chunk = StreamChunk(
            chunk_id=1,
            data=[{'id': 1}],
            is_last=True,
            metadata={'total': 1}
        )
        
        data = chunk.to_dict()
        self.assertEqual(data['chunk_id'], 1)
        self.assertEqual(data['is_last'], True)


class TestResultCursor(unittest.TestCase):
    def setUp(self):
        self.source = MockDataSource(50)
        self.cursor = ResultCursor(iter(self.source), chunk_size=10)
    
    def test_fetch_next_single(self):
        rows = self.cursor.fetch_next(1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['id'], 0)
    
    def test_fetch_next_multiple(self):
        rows = self.cursor.fetch_next(5)
        self.assertEqual(len(rows), 5)
    
    def test_fetch_many(self):
        rows = self.cursor.fetch_many()
        self.assertEqual(len(rows), 10)
    
    def test_fetch_all(self):
        rows = self.cursor.fetch_all()
        self.assertEqual(len(rows), 50)
    
    def test_skip(self):
        skipped = self.cursor.skip(20)
        self.assertEqual(skipped, 20)
        self.assertEqual(self.cursor.current_position, 20)
        
        rows = self.cursor.fetch_next(1)
        self.assertEqual(rows[0]['id'], 20)
    
    def test_exhaustion(self):
        self.cursor.fetch_all()
        rows = self.cursor.fetch_next(1)
        self.assertEqual(len(rows), 0)


class TestStreamingResultSet(unittest.TestCase):
    def setUp(self):
        def data_source():
            return iter(MockDataSource(100))
        
        self.stream = StreamingResultSet(data_source, chunk_size=10)
    
    def test_stream_creation(self):
        self.assertEqual(self.stream.state, StreamState.PENDING)
        self.assertEqual(self.stream.chunk_size, 10)
    
    def test_stream_iteration(self):
        self.stream.start()
        
        chunks = list(self.stream)
        self.assertEqual(len(chunks), 10)
        
        total_rows = sum(c.size for c in chunks)
        self.assertEqual(total_rows, 100)
    
    def test_iter_rows(self):
        self.stream.start()
        
        rows = list(self.stream.iter_rows())
        self.assertEqual(len(rows), 100)
        self.assertEqual(rows[0]['id'], 0)
        self.assertEqual(rows[99]['id'], 99)
    
    def test_iter_batches(self):
        self.stream.start()
        
        batches = list(self.stream.iter_batches(batch_size=25))
        self.assertEqual(len(batches), 4)
        
        total_rows = sum(len(b) for b in batches)
        self.assertEqual(total_rows, 100)
    
    def test_stream_stats(self):
        self.stream.start()
        
        for _ in range(3):
            next(self.stream)
        
        stats = self.stream.get_stats()
        self.assertEqual(stats['state'], 'ACTIVE')
        self.assertEqual(stats['chunks_consumed'], 3)
    
    def test_cancel(self):
        self.stream.start()
        self.stream.cancel()
        
        with self.assertRaises(StopIteration):
            next(self.stream)
    
    def test_pause_resume(self):
        self.stream.start()
        
        self.stream.pause()
        self.assertEqual(self.stream.state, StreamState.PAUSED)
        
        self.stream.resume()
        self.assertEqual(self.stream.state, StreamState.ACTIVE)


class TestStreamingQueryExecutor(unittest.TestCase):
    def setUp(self):
        self.mock_db = object()
        self.executor = StreamingQueryExecutor(self.mock_db)
    
    def test_execute_streaming(self):
        stream = self.executor.execute_streaming("SELECT * FROM users")
        
        self.assertIsInstance(stream, StreamingResultSet)
        
        rows = list(stream.iter_rows())
        self.assertEqual(len(rows), 1000)
    
    def test_custom_chunk_size(self):
        stream = self.executor.execute_streaming(
            "SELECT * FROM users",
            chunk_size=100
        )
        
        self.assertEqual(stream.chunk_size, 100)
    
    def test_stream_registration(self):
        stream = self.executor.execute_streaming(
            "SELECT * FROM users",
            stream_id="test_stream"
        )
        
        retrieved = self.executor.get_stream("test_stream")
        self.assertIs(retrieved, stream)
    
    def test_close_stream(self):
        self.executor.execute_streaming(
            "SELECT * FROM users",
            stream_id="close_test"
        )
        
        self.executor.close_stream("close_test")
        
        self.assertIsNone(self.executor.get_stream("close_test"))


class TestJSONStreamEncoder(unittest.TestCase):
    def setUp(self):
        self.encoder = JSONStreamEncoder(format='json_lines')
    
    def test_encode_chunk(self):
        chunk = StreamChunk(
            chunk_id=1,
            data=[{'id': 1, 'name': 'Alice'}],
            is_last=False
        )
        
        encoded = self.encoder.encode_chunk(chunk)
        self.assertIn('Alice', encoded)
        self.assertIn('\n', encoded)
    
    def test_encode_header(self):
        header = self.encoder.encode_header({'query': 'SELECT *'})
        self.assertEqual(header, '')


class TestStreamingResponse(unittest.TestCase):
    def setUp(self):
        def data_source():
            return iter(MockDataSource(20))
        
        stream = StreamingResultSet(data_source, chunk_size=5)
        self.response = StreamingResponse(stream)
    
    def test_response_iteration(self):
        chunks = list(self.response)
        self.assertGreater(len(chunks), 0)
        
        stats = self.response.get_stats()
        self.assertEqual(stats['rows_sent'], 20)
    
    def test_response_encoding(self):
        chunks = list(self.response)
        
        if chunks:
            first_chunk = chunks[0].decode('utf-8')
            import json
            lines = first_chunk.strip().split('\n')
            for line in lines:
                data = json.loads(line)
                self.assertIn('id', data)


class TestConvenienceFunctions(unittest.TestCase):
    def setUp(self):
        self.mock_db = object()
    
    def test_stream_large_query(self):
        rows = list(stream_large_query(self.mock_db, "SELECT * FROM users", chunk_size=50))
        self.assertEqual(len(rows), 1000)
    
    def test_chunked_export(self):
        import tempfile
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_path = f.name
        
        try:
            chunked_export(self.mock_db, "SELECT * FROM users", temp_path, chunk_size=100)
            
            self.assertTrue(os.path.exists(temp_path))
            self.assertGreater(os.path.getsize(temp_path), 0)
            
            with open(temp_path, 'r') as f:
                lines = f.readlines()
                self.assertGreater(len(lines), 0)
                
                import json
                for line in lines[:5]:
                    data = json.loads(line.strip())
                    self.assertIn('id', data)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


class TestIntegration(unittest.TestCase):
    def test_full_streaming_pipeline(self):
        def data_source():
            for i in range(1000):
                yield {
                    'id': i,
                    'name': f'User_{i}',
                    'email': f'user{i}@example.com',
                    'active': i % 2 == 0
                }
        
        stream = StreamingResultSet(data_source, chunk_size=100)
        
        processed = 0
        active_users = 0
        
        for batch in stream.iter_batches(batch_size=50):
            processed += len(batch)
            active_users += sum(1 for r in batch if r['active'])
        
        self.assertEqual(processed, 1000)
        self.assertEqual(active_users, 500)
        
        stats = stream.get_stats()
        self.assertEqual(stats['state'], 'COMPLETED')
        self.assertEqual(stats['total_rows'], 1000)


if __name__ == '__main__':
    unittest.main(verbosity=2)
