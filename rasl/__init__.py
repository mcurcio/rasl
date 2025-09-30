"""
RASL - Real-Time Animation Show Library

A standalone application for building and running real-time animation graphs
targeting lights, motors, kinetic sculptures, and other channel-based systems.
"""

__version__ = "0.1.0"

# Core types and base classes
from .core.types import Frame, NodeState, NodeStatus, Range, RangeRule, Component, Channel, Schema
from .core.nodes import Node, Source, Transform, Sink
from .core.ports import PortRef, PortsView

# Built-in node implementations
from .nodes.sources import SineSource, MultiSineSource
from .nodes.transforms import ScaleBias, Add, Multiply, Clamp
from .nodes.sinks import ConsoleSink, LoggingSink

# User script API
from .script.api import get_engine

# Connection operator
from .core.ports import connect as _connect

# Make >> operator work for port connections
def __rshift__(self, other):
    """Enable sine.ports.out >> amp.ports.in syntax"""
    if hasattr(other, '__iter__') and not isinstance(other, (str, PortRef)):
        # Fan out to multiple destinations: source >> [sink1, sink2, sink3]
        for dest in other:
            _connect(self, dest)
    else:
        # Single connection: source >> sink
        _connect(self, other)
    return other

# Monkey patch the >> operator onto PortRef
PortRef.__rshift__ = __rshift__

__all__ = [
    # Core types
    "Frame", "NodeState", "NodeStatus", "Range", "RangeRule", 
    "Component", "Channel", "Schema",
    
    # Base classes
    "Node", "Source", "Transform", "Sink",
    "PortRef", "PortsView",
    
    # Sources
    "SineSource", "MultiSineSource",
    
    # Transforms
    "ScaleBias", "Add", "Multiply", "Clamp",
    
    # Sinks
    "ConsoleSink", "LoggingSink",
    
    # Script API
    "get_engine",
]
