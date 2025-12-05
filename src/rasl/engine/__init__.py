"""RASL Engine - Core DAG types and scheduling.

This package provides the fundamental building blocks for the RASL
processing graph:

- Frame: Immutable data payload flowing through nodes
- Node: Protocol for all processing nodes
- NodeContext: Runtime services provided to nodes
- Edge: Connection between node ports
- ExecutionPlan: Compiled graph ready for execution
- GraphBuilder: Builder for constructing and validating graphs

Example:
    >>> from rasl.engine import Frame, GraphBuilder
    >>> from rasl.nodes import SacnSourceNode, UniversePatchTransform
    >>>
    >>> builder = GraphBuilder()
    >>> builder.add_node(SacnSourceNode("source", universes=[1, 2]))
    >>> builder.add_node(transform)
    >>> builder.connect("source", "dmx", "transform", "dmx")
    >>> plan = builder.build()
"""

from .frame import Frame, Metadata
from .graph import Edge, ExecutionPlan, GraphBuilder
from .node import EmitCallable, Node, NodeContext, StartTaskCallable

__all__ = [
    "Edge",
    "EmitCallable",
    "ExecutionPlan",
    "Frame",
    "GraphBuilder",
    "Metadata",
    "Node",
    "NodeContext",
    "StartTaskCallable",
]
