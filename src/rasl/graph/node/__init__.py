"""The node contract: what a node is, what it is given, and how it is found.

- ``BaseNode``: the class nodes extend; ``Node``: the protocol the graph needs
- ``BaseNodeConfig`` and the ``Source``/``Transform``/``Sink`` bases: a node's
  settings are a nested ``Config`` class built on one of them
- ``NodeContext``: what a node is handed at ``start`` and ``stop``
- ``TickContext`` and ``pull_rate``: what ``pull`` is told, and how a sink
  declares the rate it drives
- the node registry: ``@node("Name")`` and lookups by type name
"""

from rasl.graph.node.base import BaseNode
from rasl.graph.node.config import BaseNodeConfig, SinkNodeConfig, SourceNodeConfig, TransformNodeConfig
from rasl.graph.node.context import InjectCallable, NodeContext, StartTaskCallable
from rasl.graph.node.protocol import Node, get_inputs, get_outputs
from rasl.graph.node.registry import (
    ensure_nodes_loaded,
    export_node_schemas,
    get_node_class,
    get_node_registry,
    list_node_types,
    node,
    reset_registries,
)
from rasl.graph.node.tick import TickContext, pull_rate

__all__ = [
    "BaseNode",
    "BaseNodeConfig",
    "InjectCallable",
    "Node",
    "NodeContext",
    "SinkNodeConfig",
    "SourceNodeConfig",
    "StartTaskCallable",
    "TickContext",
    "TransformNodeConfig",
    "ensure_nodes_loaded",
    "export_node_schemas",
    "get_inputs",
    "get_node_class",
    "get_node_registry",
    "get_outputs",
    "list_node_types",
    "node",
    "pull_rate",
    "reset_registries",
]
