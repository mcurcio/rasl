"""The graph: nodes, their ports, and the edges between them.

- ``rasl.graph.node``: the node contract and the node registry
- ``rasl.graph.ports``: port specs and the ports nodes read and write
- ``Edge`` and ``Slice``: one output feeding one input, whole or in part
- ``GraphBuilder``: add nodes, connect them, validate, and ``build()``
- ``ExecutionPlan``: the compiled graph a runtime executes
"""

from rasl.graph.builder import CycleWarning, GraphBuilder, PortTypeError
from rasl.graph.edge import Edge
from rasl.graph.plan import ExecutionPlan
from rasl.graph.routing import CopySliceOp, EdgeOp, InputPortProgram, RepeatSliceOp
from rasl.graph.slices import Slice

__all__ = [
    "CopySliceOp",
    "CycleWarning",
    "Edge",
    "EdgeOp",
    "ExecutionPlan",
    "GraphBuilder",
    "InputPortProgram",
    "PortTypeError",
    "RepeatSliceOp",
    "Slice",
]
