"""
Tests for port and connection system.
"""

import pytest
from rasl.core.ports import (
    PortRef, SimplePortsView, ConnectionError, Edge, ConnectionRegistry,
    connect, get_connection_registry, reset_connections
)
from rasl.core.types import Schema, Component, Channel
from rasl.core.nodes import BaseSource, BaseTransform, BaseSink


class TestPortRef:
    """Test PortRef functionality."""
    
    def test_port_ref_creation(self):
        """Test basic PortRef creation."""
        schema = Schema(components=(Component("Test", channels=(Channel("a"),)),))
        port = PortRef(
            node_id="node1",
            name="out",
            kind="out",
            schema=schema
        )
        
        assert port.node_id == "node1"
        assert port.name == "out"
        assert port.kind == "out"
        assert port.schema == schema
    
    def test_port_ref_immutable(self):
        """Test that PortRef is immutable."""
        schema = Schema(components=())
        port = PortRef("node1", "out", "out", schema)
        
        # Should not be able to modify fields
        with pytest.raises(AttributeError):
            port.node_id = "node2"


class TestSimplePortsView:
    """Test SimplePortsView functionality."""
    
    def setup_method(self):
        """Set up test nodes."""
        self.source = BaseSource()
        self.transform = BaseTransform()
        self.sink = BaseSink()
    
    def test_source_ports(self):
        """Test source node ports."""
        ports = self.source.ports
        
        # Source should have output port
        out_port = ports.out
        assert out_port.node_id == self.source.id
        assert out_port.name == "out"
        assert out_port.kind == "out"
        
        # Source should not have input port
        with pytest.raises(ValueError, match="Port 'in' not found"):
            _ = ports.in
    
    def test_transform_ports(self):
        """Test transform node ports."""
        ports = self.transform.ports
        
        # Transform should have both input and output ports
        in_port = ports.in
        assert in_port.node_id == self.transform.id
        assert in_port.name == "in"
        assert in_port.kind == "in"
        
        out_port = ports.out
        assert out_port.node_id == self.transform.id
        assert out_port.name == "out"
        assert out_port.kind == "out"
    
    def test_sink_ports(self):
        """Test sink node ports."""
        ports = self.sink.ports
        
        # Sink should have input port
        in_port = ports.in
        assert in_port.node_id == self.sink.id
        assert in_port.name == "in"
        assert in_port.kind == "in"
        
        # Sink should not have output port
        with pytest.raises(ValueError, match="Port 'out' not found"):
            _ = ports.out
    
    def test_port_access_methods(self):
        """Test different port access methods."""
        ports = self.transform.ports
        
        # Attribute access
        port1 = ports.in
        
        # Key access
        port2 = ports["in"]
        
        assert port1 == port2
    
    def test_list_ports(self):
        """Test listing ports by kind."""
        ports = self.transform.ports
        
        all_ports = ports.list("any")
        assert len(all_ports) == 2
        
        in_ports = ports.list("in")
        assert len(in_ports) == 1
        assert in_ports[0].kind == "in"
        
        out_ports = ports.list("out")
        assert len(out_ports) == 1
        assert out_ports[0].kind == "out"


class TestEdge:
    """Test Edge functionality."""
    
    def test_edge_creation(self):
        """Test basic edge creation."""
        edge = Edge("src", "out", "dst", "in")
        assert edge.src_id == "src"
        assert edge.src_port == "out"
        assert edge.dst_id == "dst"
        assert edge.dst_port == "in"
    
    def test_edge_from_ports(self):
        """Test edge creation from port refs."""
        schema = Schema(components=())
        src_port = PortRef("src", "out", "out", schema)
        dst_port = PortRef("dst", "in", "in", schema)
        
        edge = Edge.from_ports(src_port, dst_port)
        assert edge.src_id == "src"
        assert edge.src_port == "out"
        assert edge.dst_id == "dst"
        assert edge.dst_port == "in"


class TestConnectionRegistry:
    """Test ConnectionRegistry functionality."""
    
    def setup_method(self):
        """Set up test registry."""
        self.registry = ConnectionRegistry()
        
        # Create compatible schemas
        self.schema = Schema(components=(
            Component("Test", channels=(Channel("value"),))
        ,))
        
        self.src_port = PortRef("src", "out", "out", self.schema)
        self.dst_port = PortRef("dst", "in", "in", self.schema)
    
    def test_valid_connection(self):
        """Test valid port connection."""
        self.registry.connect(self.src_port, self.dst_port)
        
        edges = self.registry.get_edges()
        assert len(edges) == 1
        
        edge = edges[0]
        assert edge.src_id == "src"
        assert edge.dst_id == "dst"
    
    def test_invalid_port_direction(self):
        """Test connection with invalid port directions."""
        # Try to connect input to input
        dst_port2 = PortRef("dst2", "in", "in", self.schema)
        
        with pytest.raises(ConnectionError, match="not an output"):
            self.registry.connect(dst_port2, self.dst_port)
        
        # Try to connect output to output
        src_port2 = PortRef("src2", "out", "out", self.schema)
        
        with pytest.raises(ConnectionError, match="not an input"):
            self.registry.connect(self.src_port, src_port2)
    
    def test_self_connection(self):
        """Test prevention of self-connections."""
        self_port_out = PortRef("node", "out", "out", self.schema)
        self_port_in = PortRef("node", "in", "in", self.schema)
        
        with pytest.raises(ConnectionError, match="Cannot connect node to itself"):
            self.registry.connect(self_port_out, self_port_in)
    
    def test_schema_mismatch(self):
        """Test schema compatibility checking."""
        different_schema = Schema(components=(
            Component("Different", channels=(Channel("other"),))
        ,))
        
        incompatible_port = PortRef("dst", "in", "in", different_schema)
        
        with pytest.raises(ConnectionError, match="Schema mismatch"):
            self.registry.connect(self.src_port, incompatible_port)
    
    def test_duplicate_connection(self):
        """Test prevention of duplicate connections."""
        self.registry.connect(self.src_port, self.dst_port)
        
        with pytest.raises(ConnectionError, match="Connection already exists"):
            self.registry.connect(self.src_port, self.dst_port)
    
    def test_get_node_edges(self):
        """Test getting edges for specific nodes."""
        self.registry.connect(self.src_port, self.dst_port)
        
        src_edges = self.registry.get_node_edges("src")
        dst_edges = self.registry.get_node_edges("dst")
        
        assert len(src_edges) == 1
        assert len(dst_edges) == 1
        assert src_edges[0] == dst_edges[0]
        
        # Non-existent node should return empty list
        empty_edges = self.registry.get_node_edges("nonexistent")
        assert len(empty_edges) == 0
    
    def test_clear_connections(self):
        """Test clearing all connections."""
        self.registry.connect(self.src_port, self.dst_port)
        assert len(self.registry.get_edges()) == 1
        
        self.registry.clear()
        assert len(self.registry.get_edges()) == 0


class TestGlobalConnectionAPI:
    """Test global connection functions."""
    
    def setup_method(self):
        """Reset global state."""
        reset_connections()
        
        self.schema = Schema(components=(
            Component("Test", channels=(Channel("value"),))
        ,))
        
        self.src_port = PortRef("src", "out", "out", self.schema)
        self.dst_port = PortRef("dst", "in", "in", self.schema)
    
    def test_global_connect(self):
        """Test global connect function."""
        connect(self.src_port, self.dst_port)
        
        registry = get_connection_registry()
        edges = registry.get_edges()
        assert len(edges) == 1
    
    def test_reset_connections(self):
        """Test resetting global connections."""
        connect(self.src_port, self.dst_port)
        
        registry = get_connection_registry()
        assert len(registry.get_edges()) == 1
        
        reset_connections()
        assert len(registry.get_edges()) == 0
    
    def test_rshift_operator(self):
        """Test >> operator for connections."""
        result = self.src_port >> self.dst_port
        
        # Should return the destination port
        assert result == self.dst_port
        
        # Should register the connection
        registry = get_connection_registry()
        edges = registry.get_edges()
        assert len(edges) == 1


class TestIntegratedConnections:
    """Test connections with actual node instances."""
    
    def setup_method(self):
        """Set up test nodes."""
        reset_connections()
        
        self.source = BaseSource()
        self.transform = BaseTransform()
        self.sink = BaseSink()
    
    def test_simple_chain(self):
        """Test connecting a simple chain of nodes."""
        # Connect source -> transform -> sink
        self.source.ports.out >> self.transform.ports.in
        self.transform.ports.out >> self.sink.ports.in
        
        registry = get_connection_registry()
        edges = registry.get_edges()
        assert len(edges) == 2
        
        # Check first connection
        edge1 = edges[0]
        assert edge1.src_id == self.source.id
        assert edge1.dst_id == self.transform.id
        
        # Check second connection
        edge2 = edges[1]
        assert edge2.src_id == self.transform.id
        assert edge2.dst_id == self.sink.id
    
    def test_connection_validation_with_nodes(self):
        """Test that connection validation works with real nodes."""
        # This should work (compatible default schemas)
        self.source.ports.out >> self.transform.ports.in
        
        # Verify connection was registered
        registry = get_connection_registry()
        assert len(registry.get_edges()) == 1
