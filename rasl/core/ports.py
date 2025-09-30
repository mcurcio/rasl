"""
Port and connection system for RASL nodes.

Handles:
- Port references and metadata
- Connection validation and tracking
- Port-to-port wiring with >> operator
- Schema compatibility checking
"""

from typing import Any, Dict, List, Optional, Protocol, Sequence, TYPE_CHECKING
from dataclasses import dataclass

from .types import Schema

if TYPE_CHECKING:
    from .nodes import Node


@dataclass(frozen=True)
class PortRef:
    """
    First-class reference to a node port.
    Immutable and lightweight for wiring and introspection.
    """
    node_id: str
    name: str
    kind: str  # "in" or "out"
    schema: Schema
    
    def __rshift__(self, other: "PortRef") -> "PortRef":
        """Enable source >> destination syntax."""
        connect(self, other)
        return other


class PortsView(Protocol):
    """
    Namespace for a node's ports. Avoids attribute collisions on node itself.
    
    Access patterns:
      node.ports.in, node.ports.out, node.ports.a
      node.ports["sidechain"], node.ports.list(kind="in")
    """
    
    def __getattr__(self, name: str) -> PortRef:
        """Get port by attribute access."""
        ...
    
    def __getitem__(self, name: str) -> PortRef:
        """Get port by key access."""
        ...
    
    def list(self, kind: str = "any") -> Sequence[PortRef]:
        """List ports by kind ("in", "out", "any")."""
        ...


class SimplePortsView:
    """
    Basic implementation of PortsView for simple nodes.
    Most nodes will use this unless they need custom port behavior.
    """
    
    def __init__(self, node: "Node"):
        self._node = node
        self._ports: Dict[str, PortRef] = {}
        self._initialize_ports()
    
    def _initialize_ports(self):
        """Initialize ports based on node type and configuration."""
        # This is a placeholder - real implementation would introspect
        # the node's port definitions and create PortRef instances
        
        # For now, create basic in/out ports based on node kind
        if hasattr(self._node, 'KIND'):
            if self._node.KIND in ("transform", "sink"):
                # Add default input port
                schema = self._node.port_schema("in") if hasattr(self._node, 'port_schema') else Schema(components=())
                self._ports["in"] = PortRef(
                    node_id=self._node.id,
                    name="in", 
                    kind="in",
                    schema=schema
                )
            
            if self._node.KIND in ("source", "transform"):
                # Add default output port
                schema = self._node.port_schema("out") if hasattr(self._node, 'port_schema') else Schema(components=())
                self._ports["out"] = PortRef(
                    node_id=self._node.id,
                    name="out",
                    kind="out", 
                    schema=schema
                )
    
    def __getattr__(self, name: str) -> PortRef:
        if name.startswith('_'):
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        return self._get_port(name)
    
    def __getitem__(self, name: str) -> PortRef:
        return self._get_port(name)
    
    def _get_port(self, name: str) -> PortRef:
        if name not in self._ports:
            raise ValueError(f"Port '{name}' not found on node {self._node.id}")
        return self._ports[name]
    
    def list(self, kind: str = "any") -> Sequence[PortRef]:
        if kind == "any":
            return list(self._ports.values())
        return [port for port in self._ports.values() if port.kind == kind]


class ConnectionError(Exception):
    """Raised when port connection fails validation."""
    pass


@dataclass(frozen=True)
class Edge:
    """Represents a connection between two ports."""
    src_id: str
    src_port: str
    dst_id: str
    dst_port: str
    
    @classmethod
    def from_ports(cls, src: PortRef, dst: PortRef) -> "Edge":
        return cls(
            src_id=src.node_id,
            src_port=src.name,
            dst_id=dst.node_id, 
            dst_port=dst.name
        )


class ConnectionRegistry:
    """
    Global registry of port connections.
    Tracks all edges in the graph for validation and execution.
    """
    
    def __init__(self):
        self._edges: List[Edge] = []
        self._connections: Dict[str, List[Edge]] = {}  # node_id -> edges
    
    def connect(self, src: PortRef, dst: PortRef) -> None:
        """Register a connection between two ports."""
        # Validate connection
        self._validate_connection(src, dst)
        
        # Create and store edge
        edge = Edge.from_ports(src, dst)
        self._edges.append(edge)
        
        # Update connection index
        if src.node_id not in self._connections:
            self._connections[src.node_id] = []
        if dst.node_id not in self._connections:
            self._connections[dst.node_id] = []
            
        self._connections[src.node_id].append(edge)
        self._connections[dst.node_id].append(edge)
    
    def _validate_connection(self, src: PortRef, dst: PortRef) -> None:
        """Validate that a connection is legal."""
        # Check port directions
        if src.kind != "out":
            raise ConnectionError(f"Source port {src.node_id}.{src.name} is not an output")
        if dst.kind != "in":
            raise ConnectionError(f"Destination port {dst.node_id}.{dst.name} is not an input")
        
        # Check for self-connection
        if src.node_id == dst.node_id:
            raise ConnectionError("Cannot connect node to itself")
        
        # Check schema compatibility
        if not src.schema.is_compatible(dst.schema):
            raise ConnectionError(
                f"Schema mismatch: {src.node_id}.{src.name} -> {dst.node_id}.{dst.name}\n"
                f"Source: {src.schema.get_channel_names()}\n"
                f"Dest: {dst.schema.get_channel_names()}"
            )
        
        # Check for duplicate connections
        edge = Edge.from_ports(src, dst)
        if edge in self._edges:
            raise ConnectionError(f"Connection already exists: {src.node_id}.{src.name} -> {dst.node_id}.{dst.name}")
    
    def get_edges(self) -> List[Edge]:
        """Get all registered edges."""
        return list(self._edges)
    
    def get_node_edges(self, node_id: str) -> List[Edge]:
        """Get all edges connected to a specific node."""
        return self._connections.get(node_id, [])
    
    def clear(self) -> None:
        """Clear all connections (for testing/reset)."""
        self._edges.clear()
        self._connections.clear()


# Global connection registry
_connection_registry = ConnectionRegistry()


def connect(src: PortRef, dst: PortRef) -> None:
    """
    Connect two ports, registering the connection globally.
    
    This is the main API for creating connections between nodes.
    Also enables the >> operator syntax.
    """
    _connection_registry.connect(src, dst)


def get_connection_registry() -> ConnectionRegistry:
    """Get the global connection registry."""
    return _connection_registry


def reset_connections() -> None:
    """Reset all connections (primarily for testing)."""
    _connection_registry.clear()


__all__ = [
    "PortRef", "PortsView", "SimplePortsView",
    "Edge", "ConnectionError", "ConnectionRegistry",
    "connect", "get_connection_registry", "reset_connections"
]
