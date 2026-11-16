"""Connection types, parsing and resolution for the config system.

This module provides:
- ConnectionDescriptor: Raw connection info from config (unresolved)
- parse_port_ref: Parse "node[slice].port" syntax
- parse_connect_directive: A ``connect`` directive as a ConnectionDescriptor
- resolve_connections: A node's descriptors as edges of a GraphBuilder
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from rasl.config.document import Directive, arg_texts, children
from rasl.graph import GraphBuilder, Slice
from rasl.graph.node import get_inputs, get_outputs


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
    slice_: Slice | None


@dataclass(frozen=True)
class ConnectionDescriptor:
    """Raw connection info from config, before resolution.

    This is what BaseNode produces when parsing connect directives.
    ``resolve_connections`` turns these into edges using the nodes' ports.

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
    slice_val: Slice | None = None

    if slice2_start is not None or slice2_end is not None:
        # Slice after port: node.port[start:end]
        start = int(slice2_start) if slice2_start else 0
        end = int(slice2_end) if slice2_end else None
        slice_val = Slice(start=start, end=end)
    elif slice1_start is not None or slice1_end is not None:
        # Slice after node: node[start:end] or node[start:end].port
        start = int(slice1_start) if slice1_start else 0
        end = int(slice1_end) if slice1_end else None
        slice_val = Slice(start=start, end=end)

    return PortRef(node=node, port=port, slice_=slice_val)


def parse_connect_directive(directive: Directive) -> ConnectionDescriptor:
    """Parse a connect directive into a ConnectionDescriptor.

    This is called by BaseNode when processing its config directives.
    The descriptor contains raw strings that will be resolved by Graph.
    A slice the config writes as ``upstream[0~100]`` is the string
    ``"upstream[0:100]"`` there (see ``rasl.config.document.arg_text``).

    Args:
        directive: Connect directive from config.

    Returns:
        ConnectionDescriptor with raw source/target strings and repeat count.

    Raises:
        ValueError: If directive has no arguments.
    """
    args = arg_texts(directive)
    if not args:
        raise ValueError("connect requires at least one argument")

    source = args[0]
    target = args[1] if len(args) > 1 else None

    # Check for repeat in block
    repeat = 1
    for repeat_dir in children(directive, "repeat")[:1]:
        if repeat_dir.values:
            repeat = int(arg_texts(repeat_dir)[0])

    repeat_until: int | None = None
    for repeat_until_dir in children(directive, "repeat_until")[:1]:
        if repeat_until_dir.values:
            repeat_until = int(arg_texts(repeat_until_dir)[0])
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


def resolve_connections(
    builder: GraphBuilder,
    target_node_id: str,
    descriptors: Sequence[ConnectionDescriptor],
) -> None:
    """Turn one node's connect descriptors into edges of the graph.

    Called once every node has been added. The node owns its ports; the
    loader owns its connections: port names left out are the node's default
    ports, and a repeat becomes one edge per copy.

    For repeat connections:
    - If source has no slice, uses source port's channel count as slice length
    - Target slices are offset by (repeat_index * slice_length)

    Args:
        builder: The graph being assembled, with every node already added.
        target_node_id: ID of the node the descriptors were written on.
        descriptors: What its ``connect`` directives said.

    Raises:
        KeyError: If target or source node not found.
        ValueError: If port resolution fails.
        TypeError: If the graph refuses the connection's types.
    """
    nodes = builder.nodes
    if target_node_id not in nodes:
        raise KeyError(f"Unknown target node '{target_node_id}'")

    tgt_inputs = get_inputs(nodes[target_node_id])

    for desc in descriptors:
        # Parse source reference
        source_ref = parse_port_ref(desc.source)
        if not source_ref.node:
            raise ValueError(f"Source must specify a node: {desc.source}")

        source_node_id = source_ref.node
        if source_node_id not in nodes:
            raise KeyError(f"Unknown source node '{source_node_id}'")

        source_node = nodes[source_node_id]
        src_outputs = get_outputs(source_node)

        # Resolve source port (use default if not specified)
        if source_ref.port:
            source_port = source_ref.port
        else:
            source_port, _ = src_outputs.get_default()

        # Get source port spec for channel info
        src_spec = src_outputs.get(source_port)
        if src_spec is None:
            # The graph's own wording (GraphBuilder.connect), raised here because the
            # spec is read below, before the graph would see the port
            raise ValueError(
                f"Node '{source_node_id}' has no output port '{source_port}'. "
                f"Available: {src_outputs.names}"
            )

        # Resolve target port (use default if not specified)
        if desc.target:
            target_ref = parse_port_ref(desc.target)
            if target_ref.node:
                # Could be port name (no dot) parsed as node
                target_port = target_ref.node
            else:
                target_port, _ = tgt_inputs.get_default()
            target_slice_base = target_ref.slice_
        else:
            target_port, _ = tgt_inputs.get_default()
            target_slice_base = None

        # If repeat is specified without explicit source/target slicing, treat it as
        # an implicit repeat of the entire upstream frame. The runtime will expand
        # the payload based on its (channels, elements) at runtime.
        if (
            (desc.repeat > 1 or desc.repeat_until is not None)
            and source_ref.slice_ is None
            and target_slice_base is None
        ):
            builder.connect(
                source_node_id,
                source_port,
                target_node_id,
                target_port,
                None,
                None,
                repeat=desc.repeat,
                repeat_until=desc.repeat_until,
            )
            continue

        if desc.repeat_until is not None:
            raise ValueError(
                "repeat_until is only supported for implicit repeat connections "
                "(no source or target slicing)"
            )

        # Determine source slice and length for repeat
        source_slice = source_ref.slice_
        if source_slice and source_slice.end is not None:
            slice_length = source_slice.end - source_slice.start
        elif src_spec.spec.fixed_count is not None:
            # No slice specified - use full port channel count
            slice_length = src_spec.spec.fixed_count
            # Create implicit full-port slice for repeat offset calculation
            if desc.repeat > 1:
                source_slice = Slice(0, slice_length)
        else:
            slice_length = None

        if desc.repeat > 1 and slice_length is None:
            # Each copy would land on the same rows (rasl-pd0.10: overlapping edges
            # are refused), so say what is missing instead
            raise ValueError(
                f"repeat {desc.repeat} needs the length of {desc.source}: give the source "
                f"a slice with an end, or connect a port with a fixed count"
            )

        # Create edges (possibly multiple for repeat)
        for i in range(desc.repeat):
            # Calculate target slice with offset
            if desc.repeat > 1 and slice_length is not None:
                if target_slice_base is not None:
                    offset = i * slice_length
                    start = target_slice_base.start + offset
                    end = start + slice_length if target_slice_base.end is not None else None
                    target_slice = Slice(start=start, end=end)
                else:
                    # No target slice base - create one starting at offset
                    offset = i * slice_length
                    target_slice = Slice(start=offset, end=offset + slice_length)
            else:
                target_slice = target_slice_base

            builder.connect(
                source_node_id,
                source_port,
                target_node_id,
                target_port,
                source_slice,
                target_slice,
                repeat=1,
            )

