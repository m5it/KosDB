"""
Agent-to-Agent Communication Protocol for KosDB

Provides message-passing system for agents to share context,
delegate tasks, and coordinate actions.
"""

import json
import uuid
import time
import threading
import queue
from typing import Dict, Any, Optional, List, Callable, Tuple
from dataclasses import dataclass, asdict
from enum import Enum, auto


class MessageType(Enum):
    """Types of agent messages."""
    TASK_REQUEST = auto()      # Delegate task to another agent
    TASK_RESPONSE = auto()     # Response to task request
    CONTEXT_SHARE = auto()     # Share context/state
    QUERY = auto()             # Query for information
    QUERY_RESPONSE = auto()    # Response to query
    HEARTBEAT = auto()         # Health check / keepalive
    STATUS_UPDATE = auto()     # Status broadcast
    ERROR = auto()             # Error notification


class MessagePriority(Enum):
    """Message priority levels."""
    CRITICAL = 0    # Must be processed immediately
    HIGH = 1        # Important, process soon
    NORMAL = 2      # Standard priority
    LOW = 3         # Can be delayed


@dataclass
class AgentMessage:
    """Message structure for agent communication."""
    # Message metadata
    message_id: str
    message_type: str
    priority: int
    
    # Routing
    sender_id: str
    recipient_id: Optional[str]  # None = broadcast
    
    # Content
    payload: Dict[str, Any]
    context: Optional[Dict[str, Any]] = None
    
    # Lifecycle
    timestamp: float = 0
    ttl: int = 300  # Time to live in seconds
    delivery_attempts: int = 0
    max_attempts: int = 3
    
    # Response tracking
    correlation_id: Optional[str] = None  # Links to original message
    requires_response: bool = False
    response_timeout: float = 30.0
    
    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'message_id': self.message_id,
            'message_type': self.message_type,
            'priority': self.priority,
            'sender_id': self.sender_id,
            'recipient_id': self.recipient_id,
            'payload': self.payload,
            'context': self.context,
            'timestamp': self.timestamp,
            'ttl': self.ttl,
            'delivery_attempts': self.delivery_attempts,
            'max_attempts': self.max_attempts,
            'correlation_id': self.correlation_id,
            'requires_response': self.requires_response,
            'response_timeout': self.response_timeout,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentMessage':
        """Create from dictionary."""
        return cls(**data)
    
    def is_expired(self) -> bool:
        """Check if message has expired."""
        return time.time() - self.timestamp > self.ttl
    
    def can_retry(self) -> bool:
        """Check if message can be retried."""
        return self.delivery_attempts < self.max_attempts
    
    def increment_attempt(self):
        """Increment delivery attempt counter."""
        self.delivery_attempts += 1


class AgentCapability:
    """Describes an agent's capabilities."""
    
    def __init__(self, agent_id: str, capabilities: List[str],
                 metadata: Optional[Dict[str, Any]] = None):
        self.agent_id = agent_id
        self.capabilities = capabilities
        self.metadata = metadata or {}
        self.registered_at = time.time()
        self.last_seen = time.time()
    
    def update_heartbeat(self):
        """Update last seen timestamp."""
        self.last_seen = time.time()
    
    def is_stale(self, timeout: float = 60.0) -> bool:
        """Check if agent hasn't been seen recently."""
        return time.time() - self.last_seen > timeout


class AgentRegistry:
    """
    Registry of available agents and their capabilities.
    Thread-safe for concurrent access.
    """
    
    def __init__(self):
        self._agents: Dict[str, AgentCapability] = {}
        self._lock = threading.RLock()
        self._handlers: Dict[str, List[Callable]] = {}
    
    def register(self, agent_id: str, capabilities: List[str],
                 metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Register an agent with the registry."""
        with self._lock:
            self._agents[agent_id] = AgentCapability(
                agent_id, capabilities, metadata
            )
            return True
    
    def unregister(self, agent_id: str) -> bool:
        """Remove an agent from the registry."""
        with self._lock:
            if agent_id in self._agents:
                del self._agents[agent_id]
                return True
            return False
    
    def update_heartbeat(self, agent_id: str) -> bool:
        """Update agent's last seen timestamp."""
        with self._lock:
            if agent_id in self._agents:
                self._agents[agent_id].update_heartbeat()
                return True
            return False
    
    def get_agent(self, agent_id: str) -> Optional[AgentCapability]:
        """Get agent capabilities."""
        with self._lock:
            return self._agents.get(agent_id)
    
    def list_agents(self) -> List[str]:
        """List all registered agent IDs."""
        with self._lock:
            return list(self._agents.keys())
    
    def find_by_capability(self, capability: str) -> List[str]:
        """Find agents with specific capability."""
        with self._lock:
            return [
                agent_id for agent_id, cap in self._agents.items()
                if capability in cap.capabilities
            ]
    
    def find_by_capabilities(self, capabilities: List[str]) -> List[str]:
        """Find agents with all specified capabilities."""
        with self._lock:
            return [
                agent_id for agent_id, cap in self._agents.items()
                if all(c in cap.capabilities for c in capabilities)
            ]
    
    def get_capabilities(self, agent_id: str) -> Optional[List[str]]:
        """Get capabilities for specific agent."""
        with self._lock:
            cap = self._agents.get(agent_id)
            return cap.capabilities if cap else None
    
    def cleanup_stale(self, timeout: float = 60.0) -> int:
        """Remove agents not seen within timeout. Returns count removed."""
        with self._lock:
            stale = [
                aid for aid, cap in self._agents.items()
                if cap.is_stale(timeout)
            ]
            for aid in stale:
                del self._agents[aid]
            return len(stale)
    
    def register_handler(self, agent_id: str, handler: Callable):
        """Register message handler for agent."""
        with self._lock:
            if agent_id not in self._handlers:
                self._handlers[agent_id] = []
            self._handlers[agent_id].append(handler)
    
    def get_handlers(self, agent_id: str) -> List[Callable]:
        """Get handlers for agent."""
        with self._lock:
            return self._handlers.get(agent_id, []).copy()


class MessageQueue:
    """
    Priority queue for agent messages with delivery guarantees.
    Thread-safe implementation.
    """
    
    def __init__(self, max_size: int = 10000):
        self._queue = queue.PriorityQueue(maxsize=max_size)
        self._in_flight: Dict[str, AgentMessage] = {}
        self._delivered: Dict[str, float] = {}  # message_id -> delivery_time
        self._lock = threading.RLock()
        self._shutdown = False
    
    def enqueue(self, message: AgentMessage) -> bool:
        """Add message to queue. Returns False if queue full."""
        if self._shutdown:
            return False
        
        # Priority queue uses (priority, timestamp, message_id)
        try:
            self._queue.put((
                message.priority,
                message.timestamp,
                message.message_id,
                message
            ), block=False)
            return True
        except queue.Full:
            return False
    
    def dequeue(self, timeout: Optional[float] = None) -> Optional[AgentMessage]:
        """Get next message from queue."""
        if self._shutdown:
            return None
        
        try:
            priority, timestamp, msg_id, message = self._queue.get(
                timeout=timeout
            )
            
            with self._lock:
                self._in_flight[msg_id] = message
            
            return message
        except queue.Empty:
            return None
    
    def acknowledge(self, message_id: str) -> bool:
        """Acknowledge successful delivery."""
        with self._lock:
            if message_id in self._in_flight:
                del self._in_flight[message_id]
                self._delivered[message_id] = time.time()
                return True
            return False
    
    def reject(self, message_id: str, requeue: bool = False) -> bool:
        """Reject message, optionally requeue."""
        with self._lock:
            if message_id not in self._in_flight:
                return False
            
            message = self._in_flight.pop(message_id)
            
            if requeue and message.can_retry():
                message.increment_attempt()
                self.enqueue(message)
                return True
            
            return True
    
    def get_in_flight(self) -> List[AgentMessage]:
        """Get list of messages currently being processed."""
        with self._lock:
            return list(self._in_flight.values())
    
    def get_stats(self) -> Dict[str, int]:
        """Get queue statistics."""
        with self._lock:
            return {
                'queued': self._queue.qsize(),
                'in_flight': len(self._in_flight),
                'delivered': len(self._delivered)
            }
    
    def shutdown(self):
        """Shutdown queue processing."""
        self._shutdown = True


class AgentCommunicator:
    """
    Main interface for agent-to-agent communication.
    Handles message routing, delivery, and response tracking.
    """
    
    def __init__(self, agent_id: str, registry: Optional[AgentRegistry] = None):
        self.agent_id = agent_id
        self.registry = registry or AgentRegistry()
        self.message_queue = MessageQueue()
        self.response_handlers: Dict[str, Callable] = {}
        self.message_handlers: Dict[MessageType, Callable] = {}
        self._pending_responses: Dict[str, Tuple[threading.Event, Optional[AgentMessage]]] = {}
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
    
    def start(self):
        """Start message processing."""
        self._running = True
        self._worker_thread = threading.Thread(target=self._process_messages)
        self._worker_thread.daemon = True
        self._worker_thread.start()
        
        # Register self in registry
        self.registry.register(
            self.agent_id,
            ["messaging"],
            {"started_at": time.time()}
        )
    
    def stop(self):
        """Stop message processing."""
        self._running = False
        self.message_queue.shutdown()
        if self._worker_thread:
            self._worker_thread.join(timeout=5.0)
        self.registry.unregister(self.agent_id)
    
    def _process_messages(self):
        """Main message processing loop."""
        while self._running:
            message = self.message_queue.dequeue(timeout=1.0)
            
            if message is None:
                continue
            
            # Check if expired
            if message.is_expired():
                self.message_queue.acknowledge(message.message_id)
                continue
            
            # Route to appropriate handler
            try:
                self._route_message(message)
            except Exception as e:
                # Log error and reject message
                print(f"[AGENT:{self.agent_id}] Error processing message: {e}")
                self.message_queue.reject(message.message_id, requeue=False)
            else:
                self.message_queue.acknowledge(message.message_id)
    
    def _route_message(self, message: AgentMessage):
        """Route message to appropriate handler."""
        # Check if this is a response to a pending request
        if message.correlation_id and message.correlation_id in self._pending_responses:
            event, _ = self._pending_responses[message.correlation_id]
            self._pending_responses[message.correlation_id] = (event, message)
            event.set()
            return
        
        # Route by message type
        msg_type = MessageType[message.message_type]
        
        if msg_type in self.message_handlers:
            handler = self.message_handlers[msg_type]
            handler(message)
        elif msg_type == MessageType.ERROR:
            # Default error handling
            print(f"[AGENT:{self.agent_id}] Received error from {message.sender_id}: "
                  f"{message.payload.get('error', 'Unknown error')}")
    
    def register_handler(self, msg_type: MessageType, handler: Callable):
        """Register handler for message type."""
        self.message_handlers[msg_type] = handler
    
    def send_message(self, recipient_id: Optional[str], msg_type: MessageType,
                     payload: Dict[str, Any], priority: MessagePriority = MessagePriority.NORMAL,
                     context: Optional[Dict[str, Any]] = None,
                     requires_response: bool = False,
                     response_timeout: float = 30.0) -> Optional[AgentMessage]:
        """
        Send message to another agent or broadcast.
        
        Args:
            recipient_id: Target agent ID or None for broadcast
            msg_type: Type of message
            payload: Message content
            priority: Message priority
            context: Shared context/state
            requires_response: Whether to wait for response
            response_timeout: How long to wait for response
        
        Returns:
            Response message if requires_response=True, else None
        """
        message = AgentMessage(
            message_id=str(uuid.uuid4()),
            message_type=msg_type.name,
            priority=priority.value,
            sender_id=self.agent_id,
            recipient_id=recipient_id,
            payload=payload,
            context=context,
            requires_response=requires_response,
            response_timeout=response_timeout
        )
        
        # Add to queue
        if not self.message_queue.enqueue(message):
            raise RuntimeError("Message queue full")
        
        if requires_response:
            # Wait for response
            event = threading.Event()
            self._pending_responses[message.message_id] = (event, None)
            
            if event.wait(timeout=response_timeout):
                _, response = self._pending_responses.pop(message.message_id)
                return response
            else:
                # Timeout
                self._pending_responses.pop(message.message_id, None)
                raise TimeoutError(f"No response from {recipient_id} within {response_timeout}s")
        
        return None
    
    def delegate_task(self, agent_id: str, task_type: str,
                      task_params: Dict[str, Any],
                      context: Optional[Dict[str, Any]] = None,
                      timeout: float = 60.0) -> Dict[str, Any]:
        """
        Delegate task to another agent.
        
        Args:
            agent_id: Target agent
            task_type: Type of task
            task_params: Task parameters
            context: Shared context
            timeout: Maximum time to wait
        
        Returns:
            Task result from agent
        
        Raises:
            TimeoutError: If agent doesn't respond in time
            RuntimeError: If task execution failed
        """
        payload = {
            'task_type': task_type,
            'task_params': task_params
        }
        
        response = self.send_message(
            recipient_id=agent_id,
            msg_type=MessageType.TASK_REQUEST,
            payload=payload,
            priority=MessagePriority.HIGH,
            context=context,
            requires_response=True,
            response_timeout=timeout
        )
        
        if response is None:
            raise TimeoutError(f"Task delegation to {agent_id} timed out")
        
        # Check for error in response
        if response.message_type == MessageType.ERROR.name:
            raise RuntimeError(response.payload.get('error', 'Task failed'))
        
        return response.payload.get('result', {})
    
    def respond_to_task(self, original_message: AgentMessage,
                        result: Optional[Dict[str, Any]] = None,
                        error: Optional[str] = None):
        """Send task response."""
        if error:
            payload = {'error': error, 'success': False}
            msg_type = MessageType.ERROR
        else:
            payload = {'result': result, 'success': True}
            msg_type = MessageType.TASK_RESPONSE
        
        response = AgentMessage(
            message_id=str(uuid.uuid4()),
            message_type=msg_type.name,
            priority=original_message.priority,
            sender_id=self.agent_id,
            recipient_id=original_message.sender_id,
            payload=payload,
            correlation_id=original_message.message_id
        )
        
        self.message_queue.enqueue(response)
    
    def share_context(self, agent_id: Optional[str],
                      context_data: Dict[str, Any],
                      ttl: int = 300):
        """Share context with specific agent or broadcast."""
        self.send_message(
            recipient_id=agent_id,
            msg_type=MessageType.CONTEXT_SHARE,
            payload={'context_data': context_data},
            priority=MessagePriority.NORMAL,
            context=context_data
        )
    
    def query_agent(self, agent_id: str, query_type: str,
                    query_params: Optional[Dict[str, Any]] = None,
                    timeout: float = 10.0) -> Dict[str, Any]:
        """Query another agent for information."""
        payload = {
            'query_type': query_type,
            'query_params': query_params or {}
        }
        
        response = self.send_message(
            recipient_id=agent_id,
            msg_type=MessageType.QUERY,
            payload=payload,
            priority=MessagePriority.HIGH,
            requires_response=True,
            response_timeout=timeout
        )
        
        if response is None:
            raise TimeoutError(f"Query to {agent_id} timed out")
        
        return response.payload
    
    def send_heartbeat(self):
        """Send heartbeat to registry."""
        self.registry.update_heartbeat(self.agent_id)
        
        # Broadcast heartbeat to other agents
        self.send_message(
            recipient_id=None,  # broadcast
            msg_type=MessageType.HEARTBEAT,
            payload={'timestamp': time.time()},
            priority=MessagePriority.LOW
        )
    
    def discover_agents(self, capability: Optional[str] = None) -> List[str]:
        """Discover available agents."""
        if capability:
            return self.registry.find_by_capability(capability)
        return self.registry.list_agents()


class ContextManager:
    """
    Manages shared context between agents.
    Provides persistence and conflict resolution.
    """
    
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self._local_context: Dict[str, Any] = {}
        self._shared_context: Dict[str, Dict[str, Any]] = {}  # agent_id -> context
        self._lock = threading.RLock()
        self._version = 0
    
    def get_local(self, key: str, default: Any = None) -> Any:
        """Get value from local context."""
        with self._lock:
            return self._local_context.get(key, default)
    
    def set_local(self, key: str, value: Any):
        """Set value in local context."""
        with self._lock:
            self._local_context[key] = value
            self._version += 1
    
    def update_local(self, updates: Dict[str, Any]):
        """Batch update local context."""
        with self._lock:
            self._local_context.update(updates)
            self._version += 1
    
    def get_shared(self, agent_id: str, key: str, default: Any = None) -> Any:
        """Get value from another agent's shared context."""
        with self._lock:
            agent_context = self._shared_context.get(agent_id, {})
            return agent_context.get(key, default)
    
    def update_shared(self, agent_id: str, context: Dict[str, Any]):
        """Update shared context from another agent."""
        with self._lock:
            if agent_id not in self._shared_context:
                self._shared_context[agent_id] = {}
            self._shared_context[agent_id].update(context)
    
    def merge_context(self, other_context: Dict[str, Any],
                      conflict_strategy: str = 'last_write_wins') -> Dict[str, Any]:
        """
        Merge another context into local context.
        
        Args:
            other_context: Context to merge
            conflict_strategy: How to resolve conflicts
                - 'last_write_wins': Use other values
                - 'keep_local': Keep local values
                - 'merge_lists': Concatenate lists
        """
        with self._lock:
            merged = dict(self._local_context)
            
            for key, value in other_context.items():
                if key not in merged:
                    merged[key] = value
                elif conflict_strategy == 'last_write_wins':
                    merged[key] = value
                elif conflict_strategy == 'merge_lists':
                    if isinstance(merged[key], list) and isinstance(value, list):
                        merged[key] = merged[key] + value
                    else:
                        merged[key] = value
                # 'keep_local' - do nothing
            
            self._local_context = merged
            self._version += 1
            return merged
    
    def get_snapshot(self) -> Dict[str, Any]:
        """Get complete context snapshot."""
        with self._lock:
            return {
                'local': dict(self._local_context),
                'shared': {k: dict(v) for k, v in self._shared_context.items()},
                'version': self._version
            }


class TaskDelegator:
    """
    High-level interface for task delegation with load balancing.
    """
    
    def __init__(self, communicator: AgentCommunicator):
        self.communicator = communicator
        self._task_history: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
    
    def delegate_to_capability(self, capability: str, task_type: str,
                                task_params: Dict[str, Any],
                                timeout: float = 60.0) -> Dict[str, Any]:
        """
        Delegate task to any agent with capability.
        Uses simple round-robin load balancing.
        """
        agents = self.communicator.discover_agents(capability)
        
        if not agents:
            raise RuntimeError(f"No agents available with capability: {capability}")
        
        # Try each agent until one succeeds
        last_error = None
        for agent_id in agents:
            try:
                result = self.communicator.delegate_task(
                    agent_id, task_type, task_params, timeout=timeout
                )
                
                # Record successful delegation
                with self._lock:
                    self._task_history.append({
                        'agent_id': agent_id,
                        'task_type': task_type,
                        'success': True,
                        'timestamp': time.time()
                    })
                
                return result
            
            except Exception as e:
                last_error = e
                continue
        
        # All agents failed
        raise RuntimeError(f"All agents failed: {last_error}")
    
    def delegate_with_fallback(self, primary_agent: str, fallback_agents: List[str],
                                task_type: str, task_params: Dict[str, Any],
                                timeout: float = 60.0) -> Dict[str, Any]:
        """Delegate with fallback agents if primary fails."""
        agents = [primary_agent] + fallback_agents
        
        for agent_id in agents:
            try:
                return self.communicator.delegate_task(
                    agent_id, task_type, task_params, timeout=timeout
                )
            except Exception:
                continue
        
        raise RuntimeError("All agents including fallbacks failed")
    
    def get_task_stats(self) -> Dict[str, Any]:
        """Get task delegation statistics."""
        with self._lock:
            total = len(self._task_history)
            successful = sum(1 for t in self._task_history if t['success'])
            
            # Group by agent
            by_agent = {}
            for task in self._task_history:
                aid = task['agent_id']
                if aid not in by_agent:
                    by_agent[aid] = {'total': 0, 'success': 0}
                by_agent[aid]['total'] += 1
                if task['success']:
                    by_agent[aid]['success'] += 1
            
            return {
                'total_tasks': total,
                'successful': successful,
                'failed': total - successful,
                'by_agent': by_agent
            }


# Convenience functions for common patterns
def create_agent_communicator(agent_id: str,
                               capabilities: List[str],
                               registry: Optional[AgentRegistry] = None) -> AgentCommunicator:
    """
    Create and configure a communicator for an agent.
    
    Args:
        agent_id: Unique agent identifier
        capabilities: List of agent capabilities
        registry: Optional shared registry
    
    Returns:
        Configured AgentCommunicator instance
    """
    if registry is None:
        registry = AgentRegistry()
    
    communicator = AgentCommunicator(agent_id, registry)
    communicator.registry.register(agent_id, capabilities)
    
    return communicator


def setup_task_handler(communicator: AgentCommunicator,
                       handler_func: Callable[[str, Dict[str, Any]], Dict[str, Any]]):
    """
    Setup task request handler.
    
    Args:
        communicator: Agent communicator
        handler_func: Function(task_type, task_params) -> result_dict
    """
    def task_handler(message: AgentMessage):
        try:
            task_type = message.payload.get('task_type')
            task_params = message.payload.get('task_params', {})
            
            result = handler_func(task_type, task_params)
            communicator.respond_to_task(message, result=result)
        
        except Exception as e:
            communicator.respond_to_task(message, error=str(e))
    
    communicator.register_handler(MessageType.TASK_REQUEST, task_handler)
