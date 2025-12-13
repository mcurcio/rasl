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

from .context import (
    NodeContext,
    EmitCallable,
    StartTaskCallable,
    InjectCallable,
)
from .protocol import (
    Node,
    get_inputs,
    get_outputs,
)
from .base import BaseNode

__all__ = [
    # Context
    "NodeContext",
    "EmitCallable",
    "StartTaskCallable",
    "InjectCallable",
    # Protocol
    "Node",
    "get_inputs",
    "get_outputs",
    # Base
    "BaseNode",
]
