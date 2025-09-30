"""
Graph validation for RASL.

Validates graph structure, connections, and constraints to ensure
the graph can be executed safely and correctly.
"""

import logging
from typing import Dict, List, Set, Sequence

from .types import Schema
from .nodes import Node, Source, Transform, Sink
from .ports import PortRef, get_connection_registry, Edge

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when graph validation fails."""
    pass


class SchemaMismatch(ValidationError):
    """Raised when port schemas are incompatible."""
    pass


class DanglingInput(ValidationError):
    """Raised when required inputs are not connected."""
    pass


class CyclicGraph(ValidationError):
    """Raised when graph contains cycles."""
    pass


class Validator:
    """
    Validates RASL graphs for correctness and executability.
    
    Performs both local validation (individual connections) and
    global validation (entire graph structure).
    """
    
    def __init__(self):
        self._node_registry: Dict[str, Node] = {}
    
    def register_node(self, node: Node) -> None:
        """Register a node for validation."""
        self._node_registry[node.id] = node
    
    def unregister_node(self, node_id: str) -> None:
        """Unregister a node."""
        self._node_registry.pop(node_id, None)
    
    def validate_connection(self, src: PortRef, dst: PortRef) -> None:
        """
        Validate a single connection between ports.
        
        Checks:
        - Port existence and directions
        - Schema compatibility
        - No self-connections
        """
        # Check port directions
        if src.kind != "out":
            raise ValidationError(f"Source port {src.node_id}.{src.name} is not an output")
        
        if dst.kind != "in":
            raise ValidationError(f"Destination port {dst.node_id}.{dst.name} is not an input")
        
        # Check for self-connection
        if src.node_id == dst.node_id:
            raise ValidationError("Cannot connect node to itself")
        
        # Validate schema compatibility
        self._validate_schema_compatibility(src, dst)
    
    def validate_global(self, sinks: Sequence[Sink]) -> None:
        """
        Validate the entire graph structure.
        
        Checks:
        - Graph is acyclic (DAG)
        - All required inputs are connected
        - All nodes are reachable from sinks
        - No duplicate node IDs
        """
        if not sinks:
            raise ValidationError("No sinks provided")
        
        # Discover all nodes reachable from sinks
        reachable_nodes = self._discover_reachable_nodes(sinks)
        
        # Register discovered nodes
        for node in reachable_nodes:
            self.register_node(node)
        
        # Validate graph structure
        self._validate_acyclic(reachable_nodes)
        self._validate_required_inputs(reachable_nodes)
        self._validate_node_ids(reachable_nodes)
        
        logger.info(f"Graph validation passed: {len(reachable_nodes)} nodes, {len(sinks)} sinks")
    
    def _validate_schema_compatibility(self, src: PortRef, dst: PortRef) -> None:
        """Validate that two port schemas are compatible."""
        if not src.schema.is_compatible(dst.schema):
            src_channels = src.schema.get_channel_names()
            dst_channels = dst.schema.get_channel_names()
            
            raise SchemaMismatch(
                f"Schema mismatch between {src.node_id}.{src.name} -> {dst.node_id}.{dst.name}\n"
                f"Source channels: {src_channels}\n"
                f"Destination channels: {dst_channels}"
            )
    
    def _discover_reachable_nodes(self, sinks: Sequence[Sink]) -> List[Node]:
        """Discover all nodes reachable from the given sinks."""
        visited: Set[str] = set()
        nodes: List[Node] = []
        
        def visit(node: Node):
            if node.id in visited:
                return
            
            visited.add(node.id)
            nodes.append(node)
            
            # Find nodes that feed into this node
            registry = get_connection_registry()
            node_edges = registry.get_node_edges(node.id)
            
            for edge in node_edges:
                if edge.dst_id == node.id:
                    # This is an input edge, visit the source node
                    src_node = self._get_node(edge.src_id)
                    if src_node:
                        visit(src_node)
        
        # Start from sinks and work backwards
        for sink in sinks:
            visit(sink)
        
        return nodes
    
    def _validate_acyclic(self, nodes: List[Node]) -> None:
        """Validate that the graph is acyclic (DAG)."""
        # Use topological sort to detect cycles
        in_degree = {node.id: 0 for node in nodes}
        
        registry = get_connection_registry()
        
        # Calculate in-degrees
        for node in nodes:
            node_edges = registry.get_node_edges(node.id)
            for edge in node_edges:
                if edge.dst_id == node.id:
                    in_degree[node.id] += 1
        
        # Topological sort
        queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
        processed = 0
        
        while queue:
            node_id = queue.pop(0)
            processed += 1
            
            # Process outgoing edges
            node_edges = registry.get_node_edges(node_id)
            for edge in node_edges:
                if edge.src_id == node_id:
                    in_degree[edge.dst_id] -= 1
                    if in_degree[edge.dst_id] == 0:
                        queue.append(edge.dst_id)
        
        if processed != len(nodes):
            raise CyclicGraph("Graph contains cycles")
    
    def _validate_required_inputs(self, nodes: List[Node]) -> None:
        """Validate that all required inputs are connected."""
        registry = get_connection_registry()
        
        for node in nodes:
            if isinstance(node, Source):
                # Sources should have no inputs
                node_edges = registry.get_node_edges(node.id)
                input_edges = [e for e in node_edges if e.dst_id == node.id]
                if input_edges:
                    raise ValidationError(f"Source {node.id} has input connections")
            
            elif isinstance(node, (Transform, Sink)):
                # Check that required inputs are connected
                required_ports = self._get_required_input_ports(node)
                connected_ports = set()
                
                node_edges = registry.get_node_edges(node.id)
                for edge in node_edges:
                    if edge.dst_id == node.id:
                        connected_ports.add(edge.dst_port)
                
                missing_ports = required_ports - connected_ports
                if missing_ports:
                    raise DanglingInput(
                        f"Node {node.id} has unconnected required inputs: {missing_ports}"
                    )
    
    def _validate_node_ids(self, nodes: List[Node]) -> None:
        """Validate that all node IDs are unique."""
        node_ids = [node.id for node in nodes]
        unique_ids = set(node_ids)
        
        if len(node_ids) != len(unique_ids):
            duplicates = [id for id in unique_ids if node_ids.count(id) > 1]
            raise ValidationError(f"Duplicate node IDs found: {duplicates}")
    
    def _get_required_input_ports(self, node: Node) -> Set[str]:
        """Get the set of required input port names for a node."""
        # For now, assume all input ports are required
        # TODO: Implement optional input port specification
        
        if isinstance(node, Sink):
            return {"in"}  # Sinks require at least one input
        elif isinstance(node, Transform):
            return {"in"}  # Transforms require at least one input
        else:
            return set()
    
    def _get_node(self, node_id: str) -> Node:
        """Get a node by ID from registry or connection registry."""
        if node_id in self._node_registry:
            return self._node_registry[node_id]
        
        # TODO: This is a hack - we should have a proper node registry
        # For now, we'll need to find another way to get nodes
        return None
    
    def get_validation_report(self, sinks: Sequence[Sink]) -> Dict:
        """
        Generate a detailed validation report.
        
        Returns a dictionary with validation results and any issues found.
        """
        report = {
            "valid": False,
            "errors": [],
            "warnings": [],
            "node_count": 0,
            "edge_count": 0,
            "sink_count": len(sinks)
        }
        
        try:
            self.validate_global(sinks)
            report["valid"] = True
            
            # Add statistics
            registry = get_connection_registry()
            report["edge_count"] = len(registry.get_edges())
            report["node_count"] = len(self._node_registry)
            
        except ValidationError as e:
            report["errors"].append(str(e))
        except Exception as e:
            report["errors"].append(f"Unexpected validation error: {e}")
        
        return report
