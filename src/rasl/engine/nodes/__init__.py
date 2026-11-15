"""Node abstractions for the RASL processing DAG.

This package provides the core node abstractions:

- NodeContext: Runtime services for nodes (background tasks, frame injection)
- Node: Protocol defining the node interface
- BaseNode: Abstract base class for node implementations

Submodules:
- context: NodeContext and type aliases
- protocol: Node protocol and port helpers
- base: BaseNode abstract class
"""

from rasl.engine.nodes.base import BaseNode
from rasl.engine.nodes.context import (
    InjectCallable,
    NodeContext,
    StartTaskCallable,
)
from rasl.engine.nodes.protocol import (
    Node,
    get_inputs,
    get_outputs,
)

__all__ = [
    # Context
    "NodeContext",
    "StartTaskCallable",
    "InjectCallable",
    # Protocol
    "Node",
    "get_inputs",
    "get_outputs",
    # Base
    "BaseNode",
]
