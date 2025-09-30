"""
Node execution and data materialization for RASL.

Handles lazy evaluation of nodes with per-frame memoization to ensure
each node is evaluated at most once per frame.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from .types import Frame
from .ports import PortRef, get_connection_registry
from .nodes import Node, Source, Transform, Sink, NDArrayLike

logger = logging.getLogger(__name__)


class ExecutionError(Exception):
    """Raised when node execution fails."""
    pass


class Executor:
    """
    Executes nodes on demand with per-frame memoization.
    
    Provides lazy evaluation where nodes are only computed when their
    outputs are needed, with caching to ensure single evaluation per frame.
    """
    
    def __init__(self):
        self._frame_cache: Dict[str, Dict[str, NDArrayLike]] = {}
        self._current_frame: Optional[Frame] = None
        self._node_registry: Dict[str, Node] = {}
        
        # Performance tracking
        self._eval_times: Dict[str, float] = {}
    
    def register_node(self, node: Node) -> None:
        """Register a node for execution."""
        self._node_registry[node.id] = node
    
    def unregister_node(self, node_id: str) -> None:
        """Unregister a node."""
        self._node_registry.pop(node_id, None)
        self._frame_cache.pop(node_id, None)
        self._eval_times.pop(node_id, None)
    
    async def materialize(self, port: PortRef, frame: Frame) -> NDArrayLike:
        """
        Materialize data for a port at the given frame.
        
        Uses lazy evaluation with memoization to ensure each node
        is evaluated at most once per frame.
        """
        # Check frame cache first
        if port.node_id in self._frame_cache:
            node_outputs = self._frame_cache[port.node_id]
            if port.name in node_outputs:
                return node_outputs[port.name]
        
        # Need to evaluate the node
        node = self._get_node(port.node_id)
        outputs = await self._evaluate_node(node, frame)
        
        # Cache all outputs from this node
        self._frame_cache[port.node_id] = outputs
        
        # Return requested output
        if port.name not in outputs:
            raise ExecutionError(f"Node {port.node_id} did not produce output '{port.name}'")
        
        return outputs[port.name]
    
    def reset_frame_cache(self, frame: Frame) -> None:
        """Reset cache for a new frame."""
        self._frame_cache.clear()
        self._current_frame = frame
    
    async def _evaluate_node(self, node: Node, frame: Frame) -> Dict[str, NDArrayLike]:
        """Evaluate a single node and return its outputs."""
        import time
        start_time = time.perf_counter()
        
        try:
            if isinstance(node, Source):
                outputs = await self._evaluate_source(node, frame)
            elif isinstance(node, Transform):
                outputs = await self._evaluate_transform(node, frame)
            elif isinstance(node, Sink):
                # Sinks don't produce outputs, but we might call this during validation
                outputs = {}
            else:
                raise ExecutionError(f"Unknown node type: {type(node)}")
            
            # Record performance
            eval_time = time.perf_counter() - start_time
            self._eval_times[node.id] = eval_time
            
            return outputs
            
        except Exception as e:
            eval_time = time.perf_counter() - start_time
            self._eval_times[node.id] = eval_time
            
            logger.error(f"Node {node.id} evaluation failed: {e}")
            raise ExecutionError(f"Node {node.id} failed: {e}") from e
    
    async def _evaluate_source(self, source: Source, frame: Frame) -> Dict[str, NDArrayLike]:
        """Evaluate a source node."""
        # Sources have no inputs, just sample
        return source.sample(frame)
    
    async def _evaluate_transform(self, transform: Transform, frame: Frame) -> Dict[str, NDArrayLike]:
        """Evaluate a transform node."""
        # Gather inputs from connected nodes
        inputs = {}
        
        registry = get_connection_registry()
        node_edges = registry.get_node_edges(transform.id)
        
        for edge in node_edges:
            if edge.dst_id == transform.id:
                # This is an input edge
                src_port = PortRef(
                    node_id=edge.src_id,
                    name=edge.src_port,
                    kind="out",
                    schema=transform.port_schema(edge.dst_port)  # TODO: Get actual schema
                )
                
                # Recursively materialize input
                input_data = await self.materialize(src_port, frame)
                inputs[edge.dst_port] = input_data
        
        # Evaluate transform with inputs
        return transform.evaluate(frame, **inputs)
    
    def _get_node(self, node_id: str) -> Node:
        """Get a registered node by ID."""
        if node_id not in self._node_registry:
            raise ExecutionError(f"Node {node_id} not registered")
        return self._node_registry[node_id]
    
    def get_eval_time(self, node_id: str) -> Optional[float]:
        """Get last evaluation time for a node."""
        return self._eval_times.get(node_id)
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for all nodes."""
        return {
            "node_eval_times": dict(self._eval_times),
            "cache_size": len(self._frame_cache),
            "registered_nodes": len(self._node_registry),
        }


class ParallelExecutor(Executor):
    """
    Executor that can evaluate independent nodes in parallel.
    
    Analyzes the graph to identify nodes that can be computed concurrently
    and uses asyncio to parallelize their execution.
    """
    
    def __init__(self, max_concurrent: int = 4):
        super().__init__()
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
    
    async def _evaluate_node(self, node: Node, frame: Frame) -> Dict[str, NDArrayLike]:
        """Evaluate node with concurrency limiting."""
        async with self._semaphore:
            return await super()._evaluate_node(node, frame)
    
    async def materialize_batch(self, ports: list[PortRef], frame: Frame) -> Dict[str, NDArrayLike]:
        """
        Materialize multiple ports concurrently.
        
        Useful for sinks that need multiple inputs - can fetch them in parallel.
        """
        tasks = []
        for port in ports:
            task = asyncio.create_task(self.materialize(port, frame))
            tasks.append((port, task))
        
        results = {}
        for port, task in tasks:
            try:
                data = await task
                results[f"{port.node_id}.{port.name}"] = data
            except Exception as e:
                logger.error(f"Failed to materialize {port.node_id}.{port.name}: {e}")
                raise
        
        return results
