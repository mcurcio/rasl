"""Connection types and parsing for config system.

This module provides:
- ConnectionDescriptor: Raw connection info from config (unresolved)
- ConnectionSpec: Resolved connection with explicit ports and slices
- parse_port_ref: Parse "node[slice].port" syntax
- expand_connections: Expand repeat into multiple ConnectionSpecs

Note: ResolvedSlice is imported from connect_parser for DRY.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel

# Reuse ResolvedSlice from existing parser (DRY)
from .connect_parser import ResolvedSlice


@dataclass(frozen=True)
class PortRef:
    """Parsed port reference from connect syntax.

    Attributes:
        node: Node name (required for source, None for target port-only).
        port: Port name, or None for default.
        slice_: Channel slice, or None for full port.
    """

    node: str | None
    port: str | None
    slice_: ResolvedSlice | None


@dataclass(frozen=True)
class ConnectionDescriptor:
    """Raw connection info from config, before resolution.

    This is what BaseNode produces when parsing connect directives.
    The Graph resolves these into ConnectionSpec objects using node port info.

    Attributes:
        source: Raw source string (e.g., "upstream", "upstream.port", "upstream[0:100]").
        target: Raw target string (e.g., "pixels", "pixels[0:]"), or None for default.
        repeat: Number of times to repeat this connection.
        repeat_until: If set, repeat the upstream payload until it reaches at least
            this many elements (computed at runtime based on payload shape).
    """

    source: str
    target: str | None
    repeat: int = 1
    repeat_until: int | None = None


@dataclass(frozen=True)
class ConnectionSpec:
    """A fully resolved connection ready for Graph.connect().

    Attributes:
        source_node: Name of upstream node.
        source_port: Source output port name.
        source_slice: Channel slice on source, or None for full port.
        target_port: Target input port name.
        target_slice: Channel slice on target, or None for full port.
    """

    source_node: str
    source_port: str
    source_slice: ResolvedSlice | None
    target_port: str
    target_slice: ResolvedSlice | None


# Pattern for parsing port references: node[start:end].port or node.port[start:end]
_PORT_REF_PATTERN = re.compile(
    r"^"
    r"(?P<node>[A-Za-z_][A-Za-z0-9_]*)?"  # Optional node name
    r"(?:\[(?P<slice1_start>\d*):?(?P<slice1_end>\d*)\])?"  # Optional [start:end] after node
    r"(?:\.(?P<port>[A-Za-z_][A-Za-z0-9_]*))?"  # Optional .port
    r"(?:\[(?P<slice2_start>\d*):?(?P<slice2_end>\d*)\])?"  # Optional [start:end] after port
    r"$"
)


def parse_port_ref(ref: str) -> PortRef:
    """Parse a port reference string.

    Syntax variations:
        node           -> PortRef(node="node", port=None, slice_=None)
        node.port      -> PortRef(node="node", port="port", slice_=None)
        node[0:100]    -> PortRef(node="node", port=None, slice_=(0,100))
        node[0:].port  -> PortRef(node="node", port="port", slice_=(0,None))
        node.port[0:]  -> PortRef(node="node", port="port", slice_=(0,None))
        port           -> PortRef(node=None, port="port", slice_=None)

    Args:
        ref: Port reference string.

    Returns:
        Parsed PortRef.

    Raises:
        ValueError: If ref doesn't match expected syntax.
    """
    if not ref:
        return PortRef(node=None, port=None, slice_=None)

    match = _PORT_REF_PATTERN.match(ref)
    if not match:
        raise ValueError(f"Invalid port reference: {ref!r}")

    node = match.group("node")
    port = match.group("port")

    # Check both slice positions (after node or after port)
    slice1_start = match.group("slice1_start")
    slice1_end = match.group("slice1_end")
    slice2_start = match.group("slice2_start")
    slice2_end = match.group("slice2_end")

    # Determine which slice is present (prefer slice after port if both somehow exist)
    slice_val: ResolvedSlice | None = None

    if slice2_start is not None or slice2_end is not None:
        # Slice after port: node.port[start:end]
        start = int(slice2_start) if slice2_start else 0
        end = int(slice2_end) if slice2_end else None
        slice_val = ResolvedSlice(start=start, end=end)
    elif slice1_start is not None or slice1_end is not None:
        # Slice after node: node[start:end] or node[start:end].port
        start = int(slice1_start) if slice1_start else 0
        end = int(slice1_end) if slice1_end else None
        slice_val = ResolvedSlice(start=start, end=end)

    return PortRef(node=node, port=port, slice_=slice_val)


def parse_connect_directive(directive: "Directive") -> ConnectionDescriptor:
    """Parse a connect directive into a ConnectionDescriptor.

    This is called by BaseNode when processing its config directives.
    The descriptor contains raw strings that will be resolved by Graph.

    Args:
        directive: Connect directive from config.

    Returns:
        ConnectionDescriptor with raw source/target strings and repeat count.

    Raises:
        ValueError: If directive has no arguments.
    """
    from .directive import Directive  # Avoid circular import

    args = directive.args
    if not args:
        raise ValueError("connect requires at least one argument")

    source = args[0]
    target = args[1] if len(args) > 1 else None

    # Check for repeat in block
    repeat = 1
    repeat_dir = directive.find_one("repeat")
    if repeat_dir and repeat_dir.args:
        repeat = int(repeat_dir.args[0])

    repeat_until: int | None = None
    repeat_until_dir = directive.find_one("repeat_until")
    if repeat_until_dir and repeat_until_dir.args:
        repeat_until = int(repeat_until_dir.args[0])
        if repeat_until < 0:
            raise ValueError(f"repeat_until must be non-negative, got {repeat_until}")

    if repeat_until is not None and repeat > 1:
        raise ValueError("connect cannot specify both repeat and repeat_until")

    return ConnectionDescriptor(
        source=source,
        target=target,
        repeat=repeat,
        repeat_until=repeat_until,
    )
