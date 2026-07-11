"""
Command handlers for CDC operations.
"""

import logging
from typing import Dict, Any, Optional, Set, Callable
from cdc import (
    CDCManager,
    CDCConsumer,
    OutputFormat,
    OperationType,
    get_cdc_manager,
    CDCEventEncoder
)

logger = logging.getLogger(__name__)


class CDCStartConsumerCommand:
    """CDC START CONSUMER - Start CDC consumer."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
        self.admin_required = True
    
    def execute(
        self,
        consumer_id: str,
        tables: Optional[str] = None,
        operations: Optional[str] = None,
        format: str = "json",
        from_latest: bool = False
    ) -> Dict[str, Any]:
        """Start a CDC consumer."""
        manager = get_cdc_manager()
        
        # Parse tables
        table_set = set(tables.split(',')) if tables else None
        
        # Parse operations
        op_set = None
        if operations:
            op_set = {OperationType(op.strip().upper()) for op in operations.split(',')}
        
        # Parse format
        output_format = OutputFormat(format.lower())
        
        # Create callback that logs to console
        events_received = []
        def callback(data: bytes):
            events_received.append(len(data))
        
        consumer = manager.create_consumer(
            consumer_id=consumer_id,
            tables=table_set,
            operations=op_set,
            format=output_format,
            callback=callback
        )
        
        return {
            'status': 'success',
            'message': f'Started CDC consumer: {consumer_id}',
            'consumer': consumer.get_position()
        }


class CDCStopConsumerCommand:
    """CDC STOP CONSUMER - Stop CDC consumer."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
        self.admin_required = True
    
    def execute(self, consumer_id: str) -> Dict[str, Any]:
        """Stop a CDC consumer."""
        manager = get_cdc_manager()
        
        if consumer_id not in manager.consumers:
            return {
                'status': 'error',
                'message': f'Consumer not found: {consumer_id}'
            }
        
        consumer = manager.consumers[consumer_id]
        consumer.stop()
        
        return {
            'status': 'success',
            'message': f'Stopped CDC consumer: {consumer_id}'
        }


class CDCListConsumersCommand:
    """CDC LIST CONSUMERS - Show active consumers."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self) -> Dict[str, Any]:
        """List active CDC consumers."""
        manager = get_cdc_manager()
        
        consumers = []
        for cid, consumer in manager.consumers.items():
            consumers.append({
                'consumer_id': cid,
                'position': consumer.get_position()
            })
        
        return {
            'status': 'success',
            'consumers': consumers,
            'count': len(consumers)
        }


class CDCStatsCommand:
    """CDC STATS - Show CDC statistics."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self) -> Dict[str, Any]:
        """Get CDC statistics."""
        manager = get_cdc_manager()
        stats = manager.get_stats()
        
        return {
            'status': 'success',
            'stats': stats
        }


class CDCSetupKafkaCommand:
    """CDC SETUP KAFKA - Configure Kafka integration."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
        self.admin_required = True
    
    def execute(
        self,
        bootstrap_servers: str,
        topic_prefix: str = "kosdb.cdc"
    ) -> Dict[str, Any]:
        """Setup Kafka integration."""
        manager = get_cdc_manager()
        
        try:
            manager.setup_kafka(bootstrap_servers, topic_prefix)
            
            return {
                'status': 'success',
                'message': 'Kafka integration configured',
                'bootstrap_servers': bootstrap_servers,
                'topic_prefix': topic_prefix
            }
        except ImportError as e:
            return {
                'status': 'error',
                'message': f'Kafka not available: {e}'
            }


class CDCCreateSnapshotCommand:
    """CDC SNAPSHOT - Create snapshot for new consumers."""
    
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth
    
    def execute(self, tables: str) -> Dict[str, Any]:
        """Create snapshot of current data."""
        manager = get_cdc_manager()
        
        table_list = tables.split(',')
        snapshot = manager.cdc_log.create_snapshot(table_list)
        
        return {
            'status': 'success',
            'tables': table_list,
            'snapshot_size': len(snapshot),
            'events': [e.to_dict() for e in snapshot[:10]]  # Preview first 10
        }
