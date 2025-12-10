"""RASL Engine - Core DAG types and scheduling.

This package provides the fundamental building blocks for the RASL
processing graph:

- Frame: Immutable data payload flowing through nodes
- BaseNode: Abstract base class for all nodes
- NodeContext: Runtime services provided to nodes
- Edge: Connection between node ports
- ExecutionPlan: Compiled graph ready for execution
- GraphBuilder: Builder for constructing and validating graphs
- Registry: Node and payload type registration

Example:
    >>> from rasl.engine import Frame, GraphBuilder
    >>> from rasl.nodes import SacnSourceNode, UniversePatchTransform
    >>>
    >>> builder = GraphBuilder()
    >>> builder.add_node(source_node)
    >>> builder.add_node(transform_node)
    >>> builder.connect("source", "dmx", "transform", "dmx")
    >>> plan = builder.build()
"""

from .base_node import BaseNode
from .frame import (
    ArrayPayload,
    ColorPayload,
    Frame,
    FramePayload,
    HslColorPayload,
    Metadata,
    OklabColorPayload,
    OklchColorPayload,
    PayloadDescriptor,
    RgbColorPayload,
)
from .graph import CycleWarning, Edge, ExecutionPlan, GraphBuilder
from .node import EmitCallable, InjectCallable, Node, NodeContext, StartTaskCallable, get_inputs, get_outputs
from .ports import (
    EMPTY_PORTS,
    AcceptsSpec,
    BoundPortGroup,
    ChannelSpec,
    InputPort,
    OutputPort,
    PortGroup,
    PortSpec,
)
from .registry import (
    ensure_nodes_loaded,
    export_node_schemas,
    get_node_class,
    get_node_registry,
    get_payload_type,
    list_node_types,
    list_payload_types,
    node,
    payload,
)
from .tick import TickContext, pull_rate

__all__ = [
    "AcceptsSpec",
    "ArrayPayload",
    "BaseNode",
    "BoundPortGroup",
    "ChannelSpec",
    "ColorPayload",
    "CycleWarning",
    "Edge",
    "EmitCallable",
    "EMPTY_PORTS",
    "ensure_nodes_loaded",
    "ExecutionPlan",
    "export_node_schemas",
    "Frame",
    "FramePayload",
    "get_inputs",
    "get_node_class",
    "get_node_registry",
    "get_outputs",
    "get_payload_type",
    "GraphBuilder",
    "HslColorPayload",
    "InjectCallable",
    "InputPort",
    "list_node_types",
    "OklabColorPayload",
    "OklchColorPayload",
    "list_payload_types",
    "Metadata",
    "Node",
    "node",
    "NodeContext",
    "OutputPort",
    "payload",
    "PayloadDescriptor",
    "PortGroup",
    "PortSpec",
    "pull_rate",
    "RgbColorPayload",
    "StartTaskCallable",
    "TickContext",
]
