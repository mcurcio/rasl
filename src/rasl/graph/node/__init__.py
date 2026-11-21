"""The node contract: what a node is, what it is given, and how it is found.

- ``BaseNode``: the class nodes extend; ``Node``: the protocol the graph needs
- ``BaseNodeConfig`` and the ``Source``/``Transform``/``Sink`` bases: a node's
  settings are a nested ``Config`` class built on one of them
- ``NodeContext``: what a node is handed at ``start`` and ``stop``; ``Resources``,
  ``ResourceKey`` and ``Lease``: resources nodes share through it
- ``TickContext`` and ``pull_rate``: what ``pull`` is told, and how a sink
  declares the rate it drives; ``Wiring``: which of a node's ports the plan connects
- the node registry: ``@node("Name")`` and lookups by type name
"""

from rasl.graph.node.base import BaseNode, PlanWarning, has_own_pull
from rasl.graph.node.config import BaseNodeConfig, SinkNodeConfig, SourceNodeConfig, TransformNodeConfig
from rasl.graph.node.context import NodeContext, StartTaskCallable
from rasl.graph.node.protocol import Node, get_inputs, get_outputs
from rasl.graph.node.registry import (
    NodeRegistryError,
    ensure_nodes_loaded,
    export_node_schemas,
    get_node_class,
    get_node_registry,
    list_node_types,
    node,
    reset_registries,
)
from rasl.graph.node.resources import EndOfTick, Lease, ResourceKey, Resources
from rasl.graph.node.tick import TickContext, pull_rate
from rasl.graph.node.wiring import Wiring

__all__ = [
    "BaseNode",
    "BaseNodeConfig",
    "EndOfTick",
    "Lease",
    "Node",
    "NodeContext",
    "NodeRegistryError",
    "PlanWarning",
    "ResourceKey",
    "Resources",
    "SinkNodeConfig",
    "SourceNodeConfig",
    "StartTaskCallable",
    "TickContext",
    "TransformNodeConfig",
    "Wiring",
    "ensure_nodes_loaded",
    "export_node_schemas",
    "get_inputs",
    "get_node_class",
    "get_node_registry",
    "get_outputs",
    "has_own_pull",
    "list_node_types",
    "node",
    "pull_rate",
    "reset_registries",
]
