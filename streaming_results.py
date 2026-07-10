"""
Streaming Results for Large Datasets

Provides progressive result streaming to avoid memory exhaustion.
Supports cursor-based iteration, chunked fetching, and backpressure handling.
"""

import json
import time
import threading
import queue
from typing import Iterator, List, Dict, Any, Optional, Callable, Generator
from dataclasses import dataclass, field
from enum import Enum, auto


class StreamState(Enum):
    """States of result stream."""
    PENDING = auto()
    ACTIVE = auto()
    PAUSED = auto()
    COMPLETED = auto()
    CANCELLED = auto()
    ERROR = auto()


@dataclass
class StreamChunk:
    """A chunk of streamed results."""
    chunk_id: int
    data: List[Dict[str, Any]]
    is_last: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'chunk_id': self.chunk_id,
            'data': self.data,
            'is_last': self.is_last,
            'metadata': self.metadata
        }
    
    @property
    def size(self) -> int:
        """Get number of rows in chunk."""
        return len(self.data)


class ResultCursor:
    """
    Cursor for iterating over large result sets.
    Supports bidirectional navigation and position tracking.
    """
    
    def __init__(self, data_source: Iterator[Dict[str, Any]],
                 chunk_size: int = 100):
        self.data_source = data_source
        self.chunk_size = chunk_size
        self.position = 0
        self.buffer: List[Dict[str, Any]] = []
        self.buffer_start = 0
        self._exhausted = False
        self._lock = threading.RLock()
    
    def fetch_next(self, n: int = 1) -> List[Dict[str, Any]]:
        """
        Fetch next n rows.
        
        Returns:
            List of rows (may be fewer than n if exhausted)
        """
        with self._lock:
            results = []
            
            while len(results) < n and not self._exhausted:
                # Check if we have data in buffer
                buffer_pos = self.position - self.buffer_start
                
                if buffer_pos < len(self.buffer):
                    # Take from buffer
                    take = min(n - len(results), len(self.buffer) - buffer_pos)
                    results.extend(self.buffer[buffer_pos:buffer_pos + take])
                    self.position += take
                else:
                    # Need to fetch more
                    try:
                        batch = self._fetch_batch()
                        if batch:
                            self.buffer = batch
                            self.buffer_start = self.position
                        else:
                            self._exhausted = True
                    except StopIteration:
                        self._exhausted = True
            
            return results
    
    def _fetch_batch(self) -> List[Dict[str, Any]]:
        """Fetch next batch from source."""
        batch = []
        for _ in range(self.chunk_size):
            try:
                row = next(self.data_source)
                batch.append(row)
            except StopIteration:
                break
        return batch
    
    def fetch_many(self, size: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch many rows (default: chunk_size)."""
        if size is None:
            size = self.chunk_size
        return self.fetch_next(size)
    
    def fetch_all(self) -> List[Dict[str, Any]]:
        """
        Fetch all remaining rows.
        Note: This loads everything into memory - use with caution!
        """
        results = []
        while not self._exhausted:
            batch = self.fetch_many()
            results.extend(batch)
        return results
    
    def skip(self, n: int) -> int:
        """
        Skip n rows.
        
        Returns:
            Number of rows actually skipped
        """
        with self._lock:
            skipped = 0
            
            while skipped < n and not self._exhausted:
                buffer_pos = self.position - self.buffer_start
                
                if buffer_pos < len(self.buffer):
                    # Can skip from buffer
                    can_skip = min(n - skipped, len(self.buffer) - buffer_pos)
                    self.position += can_skip
                    skipped += can_skip
                else:
                    # Need to fetch and discard
                    batch = self._fetch_batch()
                    if batch:
                        self.buffer = batch
                        self.buffer_start = self.position
                    else:
                        self._exhausted = True
            
            return skipped
    
    def reset(self):
        """Reset cursor to beginning."""
        raise NotImplementedError("Reset not supported for streaming cursors")
    
    @property
    def current_position(self) -> int:
        """Get current position in result set."""
        return self.position


class StreamingResultSet:
    """
    Result set that streams data progressively.
    Supports async iteration and backpressure handling.
    """
    
    def __init__(self, data_source: Callable[[], Iterator[Dict[str, Any]]],
                 chunk_size: int = 100,
                 max_buffered_chunks: int = 5):
        self.data_source = data_source
        self.chunk_size = chunk_size
        self.max_buffered_chunks = max_buffered_chunks
        
        self.state = StreamState.PENDING
        self.chunks_produced = 0
        self.chunks_consumed = 0
        self.total_rows = 0
        
        self._chunk_queue: queue.Queue[Optional[StreamChunk]] = queue.Queue(
            maxsize=max_buffered_chunks
        )
        self._producer_thread: Optional[threading.Thread] = None
        self._error: Optional[Exception] = None
        self._lock = threading.RLock()
    
    def start(self):
        """Start streaming."""
        with self._lock:
            if self.state != StreamState.PENDING:
                raise RuntimeError(f"Cannot start from state {self.state}")
            
            self.state = StreamState.ACTIVE
            self._producer_thread = threading.Thread(target=self._producer)
            self._producer_thread.daemon = True
            self._producer_thread.start()
    
    def _producer(self):
        """Producer thread that fetches data and puts chunks in queue."""
        try:
            iterator = self.data_source()
            chunk_id = 0
            
            while self.state == StreamState.ACTIVE:
                # Fetch next chunk
                rows = []
                for _ in range(self.chunk_size):
                    try:
                        row = next(iterator)
                        rows.append(row)
                        with self._lock:
                            self.total_rows += 1
                    except StopIteration:
                        break
                
                if not rows:
                    # End of data
                    chunk = StreamChunk(
                        chunk_id=chunk_id,
                        data=[],
                        is_last=True,
                        metadata={'total_rows': self.total_rows}
                    )
                    self._chunk_queue.put(chunk)
                    with self._lock:
                        self.chunks_produced += 1
                    break
                
                # Create chunk
                chunk = StreamChunk(
                    chunk_id=chunk_id,
                    data=rows,
                    is_last=False
                )
                
                # Put in queue (blocks if full - provides backpressure)
                self._chunk_queue.put(chunk)
                
                with self._lock:
                    self.chunks_produced += 1
                
                chunk_id += 1
                
                # Brief yield to allow consumer to catch up
                if self._chunk_queue.qsize() >= self.max_buffered_chunks - 1:
                    time.sleep(0.001)
        
        except Exception as e:
            self._error = e
            with self._lock:
                self.state = StreamState.ERROR
            # Put sentinel to unblock consumer
            self._chunk_queue.put(None)
    
    def __iter__(self) -> Iterator[StreamChunk]:
        """Iterate over chunks."""
        if self.state == StreamState.PENDING:
            self.start()
        
        return self
    
    def __next__(self) -> StreamChunk:
        """Get next chunk."""
        if self.state == StreamState.ERROR and self._error:
            raise self._error
        
        if self.state == StreamState.CANCELLED:
            raise StopIteration("Stream cancelled")
        
        # Get chunk from queue
        chunk = self._chunk_queue.get(timeout=30.0)
        
        if chunk is None or chunk.is_last:
            with self._lock:
                self.state = StreamState.COMPLETED
            raise StopIteration
        
        with self._lock:
            self.chunks_consumed += 1
        
        return chunk
    
    def iter_rows(self) -> Iterator[Dict[str, Any]]:
        """
        Iterate over individual rows (flattened).
        More convenient for consumers.
        """
        for chunk in self:
            for row in chunk.data:
                yield row
    
    def iter_batches(self, batch_size: int) -> Iterator[List[Dict[str, Any]]]:
        """
        Iterate over custom-sized batches.
        
        Args:
            batch_size: Number of rows per batch
        """
        batch = []
        for row in self.iter_rows():
            batch.append(row)
            if len(batch) >= batch_size:
                yield batch
                batch = []
        
        if batch:
            yield batch
    
    def cancel(self):
        """Cancel streaming."""
        with self._lock:
            self.state = StreamState.CANCELLED
        
        # Drain queue
        try:
            while True:
                self._chunk_queue.get_nowait()
        except queue.Empty:
            pass
    
    def pause(self):
        """Pause streaming."""
        with self._lock:
            if self.state == StreamState.ACTIVE:
                self.state = StreamState.PAUSED
    
    def resume(self):
        """Resume streaming."""
        with self._lock:
            if self.state == StreamState.PAUSED:
                self.state = StreamState.ACTIVE
    
    def get_stats(self) -> Dict[str, Any]:
        """Get streaming statistics."""
        with self._lock:
            return {
                'state': self.state.name,
                'chunks_produced': self.chunks_produced,
                'chunks_consumed': self.chunks_consumed,
                'total_rows': self.total_rows,
                'queue_size': self._chunk_queue.qsize(),
                'buffer_utilization': (
                    self._chunk_queue.qsize() / self.max_buffered_chunks
                )
            }


class StreamingQueryExecutor:
    """
    Executes queries with streaming results.
    Integrates with database to provide streaming capabilities.
    """
    
    def __init__(self, db, default_chunk_size: int = 100):
        self.db = db
        self.default_chunk_size = default_chunk_size
        self.active_streams: Dict[str, StreamingResultSet] = {}
        self._lock = threading.RLock()
    
    def execute_streaming(self, query: str,
                          chunk_size: Optional[int] = None,
                          stream_id: Optional[str] = None) -> StreamingResultSet:
        """
        Execute query with streaming results.
        
        Args:
            query: SQL query
            chunk_size: Rows per chunk
            stream_id: Optional stream identifier
        
        Returns:
            StreamingResultSet
        """
        if chunk_size is None:
            chunk_size = self.default_chunk_size
        
        # Create data source
        def data_source():
            # This would integrate with actual database
            # For now, simulate with generator
            return self._execute_query_generator(query)
        
        stream = StreamingResultSet(data_source, chunk_size)
        
        # Register stream
        if stream_id:
            with self._lock:
                self.active_streams[stream_id] = stream
        
        return stream
    
    def _execute_query_generator(self, query: str) -> Iterator[Dict[str, Any]]:
        """
        Execute query and yield rows one at a time.
        
        This is the integration point with the actual database.
        """
        # Mock implementation - would use actual database
        # Example: yield from self.db.execute_cursor(query)
        for i in range(1000):  # Simulate large result set
            yield {
                'id': i,
                'data': f'row_{i}',
                'query': query
            }
    
    def get_stream(self, stream_id: str) -> Optional[StreamingResultSet]:
        """Get active stream by ID."""
        with self._lock:
            return self.active_streams.get(stream_id)
    
    def close_stream(self, stream_id: str):
        """Close and remove stream."""
        with self._lock:
            stream = self.active_streams.pop(stream_id, None)
            if stream:
                stream.cancel()
    
    def close_all_streams(self):
        """Close all active streams."""
        with self._lock:
            for stream in self.active_streams.values():
                stream.cancel()
            self.active_streams.clear()


class JSONStreamEncoder:
    """
    Encodes streaming results as JSON.
    Supports JSON Lines format for efficient streaming.
    """
    
    def __init__(self, format: str = 'json_lines'):
        self.format = format
    
    def encode_chunk(self, chunk: StreamChunk) -> str:
        """Encode chunk as JSON."""
        if self.format == 'json':
            return json.dumps(chunk.to_dict())
        elif self.format == 'json_lines':
            lines = [json.dumps(row) for row in chunk.data]
            return '\n'.join(lines) + '\n'
        else:
            raise ValueError(f"Unknown format: {self.format}")
    
    def encode_header(self, metadata: Dict[str, Any]) -> str:
        """Encode stream header."""
        if self.format == 'json':
            return json.dumps({'type': 'header', 'metadata': metadata}) + '\n'
        return ''
    
    def encode_footer(self, metadata: Dict[str, Any]) -> str:
        """Encode stream footer."""
        if self.format == 'json':
            return json.dumps({'type': 'footer', 'metadata': metadata}) + '\n'
        return ''


class StreamingResponse:
    """
    HTTP-like streaming response handler.
    Manages chunked transfer encoding.
    """
    
    def __init__(self, result_set: StreamingResultSet,
                 encoder: Optional[JSONStreamEncoder] = None):
        self.result_set = result_set
        self.encoder = encoder or JSONStreamEncoder()
        self.bytes_sent = 0
        self.rows_sent = 0
    
    def __iter__(self) -> Iterator[bytes]:
        """
        Iterate over response chunks.
        Suitable for WSGI/ASGI streaming.
        """
        # Send header
        header = self.encoder.encode_header({})
        if header:
            yield header.encode('utf-8')
            self.bytes_sent += len(header)
        
        # Stream results
        for chunk in self.result_set:
            encoded = self.encoder.encode_chunk(chunk)
            data = encoded.encode('utf-8')
            
            yield data
            self.bytes_sent += len(data)
            self.rows_sent += chunk.size
            
            # Check for backpressure
            if self.result_set._chunk_queue.qsize() == 0:
                # Consumer is catching up, brief pause
                time.sleep(0.001)
        
        # Send footer
        footer = self.encoder.encode_footer({
            'total_rows': self.rows_sent,
            'bytes_sent': self.bytes_sent
        })
        if footer:
            yield footer.encode('utf-8')
    
    def get_stats(self) -> Dict[str, Any]:
        """Get response statistics."""
        return {
            'bytes_sent': self.bytes_sent,
            'rows_sent': self.rows_sent,
            'stream_stats': self.result_set.get_stats()
        }


# Convenience functions
def stream_large_query(db, query: str, 
                       chunk_size: int = 100) -> Iterator[Dict[str, Any]]:
    """
    Convenience function to stream large query results.
    
    Args:
        db: Database connection
        query: SQL query
        chunk_size: Rows per chunk
    
    Yields:
        Individual rows
    """
    executor = StreamingQueryExecutor(db, chunk_size)
    stream = executor.execute_streaming(query, chunk_size)
    
    return stream.iter_rows()


def chunked_export(db, query: str, 
                   output_file: str,
                   chunk_size: int = 1000):
    """
    Export large query result to file in chunks.
    
    Args:
        db: Database connection
        query: SQL query
        output_file: Output file path
        chunk_size: Rows per chunk
    """
    executor = StreamingQueryExecutor(db, chunk_size)
    stream = executor.execute_streaming(query, chunk_size)
    
    encoder = JSONStreamEncoder(format='json_lines')
    
    with open(output_file, 'w') as f:
        for chunk in stream:
            encoded = encoder.encode_chunk(chunk)
            f.write(encoded)
            f.flush()  # Ensure data is written


def create_streaming_response(db, query: str) -> StreamingResponse:
    """
    Create streaming response for web frameworks.
    
    Args:
        db: Database connection
        query: SQL query
    
    Returns:
        StreamingResponse for WSGI/ASGI
    """
    executor = StreamingQueryExecutor(db)
    stream = executor.execute_streaming(query)
    return StreamingResponse(stream)
