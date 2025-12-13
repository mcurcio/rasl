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

Subpackages:
- frames: Frame and payload types (FramePayload, MatrixPayload, ColorPayload, etc.)
- nodes: Node abstractions (Node protocol, NodeContext, BaseNode)

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

# Import from new packages (preferred)
from .frames import (
    BoolPayload,
    ColorPayload,
    Frame,
    FramePayload,
    HslColorPayload,
    LinearRgbColorPayload,
    MatrixPayload,
    Metadata,
    OklabColorPayload,
    OklchColorPayload,
    OkhslColorPayload,
    OkhsvColorPayload,
    PayloadDescriptor,
    RgbColorPayload,
)
from .nodes import (
    BaseNode,
    EmitCallable,
    InjectCallable,
    Node,
    NodeContext,
    StartTaskCallable,
    get_inputs,
    get_outputs,
)
from .graph import CycleWarning, Edge, ExecutionPlan, GraphBuilder
from .ports import (
    EMPTY_PORTS,
    AcceptsSpec,
    BoundPortGroup,
    CountSpec,
    InputPort,
    InputPortSpec,
    OutputPort,
    OutputPortSpec,
    PortGroup,
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
    # Port types
    "AcceptsSpec",
    "BoundPortGroup",
    "CountSpec",
    "EMPTY_PORTS",
    "InputPort",
    "InputPortSpec",
    "OutputPort",
    "OutputPortSpec",
    "PortGroup",
    # Payload types
    "BoolPayload",
    "MatrixPayload",
    "ColorPayload",
    "RgbColorPayload",
    "HslColorPayload",
    "OklchColorPayload",
    "OklabColorPayload",
    "OkhslColorPayload",
    "OkhsvColorPayload",
    "LinearRgbColorPayload",
    # Core frame
    "Frame",
    "FramePayload",
    "Metadata",
    "PayloadDescriptor",
    # Node types
    "BaseNode",
    "Node",
    "NodeContext",
    "EmitCallable",
    "InjectCallable",
    "StartTaskCallable",
    "get_inputs",
    "get_outputs",
    # Graph
    "CycleWarning",
    "Edge",
    "ExecutionPlan",
    "GraphBuilder",
    # Registry
    "ensure_nodes_loaded",
    "export_node_schemas",
    "get_node_class",
    "get_node_registry",
    "get_payload_type",
    "list_node_types",
    "list_payload_types",
    "node",
    "payload",
    # Tick
    "pull_rate",
    "TickContext",
]
