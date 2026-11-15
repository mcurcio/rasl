"""An edge of the graph: one output port feeding one input port.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from rasl.graph.slices import Slice


@dataclass(frozen=True, slots=True)
class Edge:
    """Immutable connection between two node ports in the graph.

    An Edge represents a directed connection from an output port of
    one node to an input port of another. Frames emitted on the
    source port will be delivered to the target port.

    Optionally includes channel slice information for partial channel
    mapping between ports.

    Attributes:
        source: ID of the node that emits frames.
        source_port: Name of the output port on the source node.
        target: ID of the node that receives frames.
        target_port: Name of the input port on the target node.
        source_slice: Optional channel slice on the source port.
        target_slice: Optional channel slice on the target port.

    Example:
        >>> edge = Edge(
        ...     source="sacnSource",
        ...     source_port="dmx",
        ...     target="patchTransform",
        ...     target_port="dmx"
        ... )
        >>> # With channel slicing:
        >>> edge = Edge(
        ...     source="twinkle",
        ...     source_port="out",
        ...     target="sink",
        ...     target_port="universe0",
        ...     source_slice=Slice(0, 151),
        ...     target_slice=Slice(0, 151),
        ... )
    """

    source: str
    """ID of the source node that emits frames."""

    source_port: str
    """Name of the output port on the source node."""

    target: str
    """ID of the target node that receives frames."""

    target_port: str
    """Name of the input port on the target node."""

    source_slice: Optional[Slice] = None
    """Optional channel slice on the source port (None = full port)."""

    target_slice: Optional[Slice] = None
    """Optional channel slice on the target port (None = full port)."""

    repeat: int = 1

    repeat_until: int | None = None
