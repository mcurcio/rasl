"""Assembling and validating a graph, and compiling it into an ExecutionPlan.
"""

from __future__ import annotations

import warnings
from typing import Dict, List, Optional, Type

from rasl.graph.edge import Edge
from rasl.graph.errors import (
    ConnectKeyError,
    ConnectProblem,
    ConnectTypeError,
    ConnectValueError,
    Endpoint,
)
from rasl.graph.node.protocol import Node, get_inputs, get_outputs
from rasl.graph.order import find_back_edges, toposort_with_cycles
from rasl.graph.plan import ExecutionPlan
from rasl.graph.ports.spec import InputPortSpec, OutputPortSpec
from rasl.graph.routing import compile_input_programs
from rasl.graph.slices import Slice
from rasl.signal import FramePayload


class PortTypeError(ConnectTypeError):
    """A connection whose payload types do not match, found when the graph is built.

    Attributes:
        node: The id of the node the connection feeds, where the error belongs.
        edge: The connection.
    """

    def __init__(self, edge: Edge, message: str) -> None:
        """Record the connection and the message."""
        super().__init__(
            ConnectProblem.TYPE,
            message,
            source=Endpoint(edge.source, edge.source_port, edge.source_slice),
            target=Endpoint(edge.target, edge.target_port, edge.target_slice),
        )
        self.node = edge.target
        self.edge = edge


class CycleWarning(UserWarning):
    """Warning emitted when cycles are detected in the graph.

    Cycles are allowed but may cause nodes to receive stale data
    on the first frame. Node implementations are responsible for
    handling cyclic data flow appropriately.
    """

    pass


class GraphBuilder:
    """Builder for assembling and validating the processing graph.

    GraphBuilder provides a fluent interface for constructing the graph:
    add nodes, connect them with edges, then build() to get an
    ExecutionPlan. The builder validates:

    - No duplicate node IDs
    - All edge endpoints reference existing nodes
    - Cycles are detected and warned about (but allowed)

    Example:
        >>> builder = GraphBuilder()
        >>> builder.add_node(source_node)
        >>> builder.add_node(transform_node)
        >>> builder.add_node(sink_node)
        >>> builder.connect("source", "dmx", "transform", "dmx")
        >>> builder.connect("transform", "output", "sink", "input")
        >>> plan = builder.build()  # Validates and compiles
    """

    def __init__(self) -> None:
        """Initialize an empty graph builder."""
        self._nodes: Dict[str, Node] = {}
        self._edges: List[Edge] = []

    @property
    def nodes(self) -> Dict[str, Node]:
        """Read-only access to registered nodes.

        Returns:
            Dictionary mapping node IDs to Node instances.
        """
        return self._nodes.copy()

    @property
    def edges(self) -> List[Edge]:
        """Read-only access to registered edges.

        Returns:
            List of Edge connections in registration order.
        """
        return self._edges.copy()

    def add_node(self, node: Node) -> None:
        """Register a node with the graph.

        Args:
            node: Node instance to add. Must have a unique ID.

        Raises:
            ValueError: If a node with the same ID already exists.
        """
        if node.id in self._nodes:
            raise ValueError(f"Duplicate node id '{node.id}'")
        self._nodes[node.id] = node

    def connect(
        self,
        source: str,
        source_port: str,
        target: str,
        target_port: str,
        source_slice: Optional[Slice] = None,
        target_slice: Optional[Slice] = None,
        repeat: int = 1,
        repeat_until: int | None = None,
    ) -> None:
        """Create an edge connecting two node ports.

        Validates that both nodes exist, both ports exist, and that
        the source port's payload type is compatible with the target port.
        Optionally includes channel slice information for partial mapping.

        Args:
            source: ID of the source node.
            source_port: Output port name on the source node.
            target: ID of the target node.
            target_port: Input port name on the target node.
            source_slice: Optional channel slice on source port.
            target_slice: Optional channel slice on target port.

        Every error is a ``ConnectError`` (``rasl.graph.errors``) naming the problem
        and both ends, and also the built-in exception listed.

        Raises:
            KeyError: If source or target node ID is not registered.
            ValueError: If a port does not exist on its node, if a slice
                reaches past the end of a sized port, if the rows the edge
                supplies and the rows it fills are both fixed and differ, if
                the same edge was already added, or if it writes rows of the
                target port that an earlier edge writes.
            TypeError: If the port types are incompatible, or a port names
                a payload type that is not registered.
        """
        src_end = Endpoint(source, source_port, source_slice)
        tgt_end = Endpoint(target, target_port, target_slice)
        for node_id, kind in ((source, "source"), (target, "target")):
            if node_id not in self._nodes:
                raise ConnectKeyError(
                    ConnectProblem.UNKNOWN_NODE,
                    f"Unknown {kind} node '{node_id}'",
                    source=src_end,
                    target=tgt_end,
                )

        src_node = self._nodes[source]
        tgt_node = self._nodes[target]

        src_outputs = get_outputs(src_node)
        tgt_inputs = get_inputs(tgt_node)

        # Validate port existence
        for node_id, port, group, kind in (
            (source, source_port, src_outputs, "output"),
            (target, target_port, tgt_inputs, "input"),
        ):
            if port not in group:
                raise ConnectValueError(
                    ConnectProblem.UNKNOWN_PORT,
                    f"Node '{node_id}' has no {kind} port '{port}'. Available: {group.names}",
                    source=src_end,
                    target=tgt_end,
                )

        src_spec = src_outputs.get(source_port)
        tgt_spec = tgt_inputs.get(target_port)
        assert src_spec is not None and tgt_spec is not None  # both checked above
        src_port_spec = src_spec.spec
        tgt_port_spec = tgt_spec.spec

        src_label = f"{source}.{source_port}"
        tgt_label = f"{target}.{target_port}"

        # A type name nothing is registered under would match any payload
        for label, port_spec in ((src_label, src_port_spec), (tgt_label, tgt_port_spec)):
            unknown = port_spec.unknown_type_names()
            if unknown:
                from rasl.signal import list_payload_types

                raise ConnectTypeError(
                    ConnectProblem.UNREGISTERED_TYPE,
                    f"Port {label} names a payload type that is not registered: "
                    f"{', '.join(repr(name) for name in unknown)}. "
                    f"Registered: {', '.join(list_payload_types())}",
                    source=src_end,
                    target=tgt_end,
                )

        # A slice must lie inside a port whose size is known
        for label, slice_, port_spec in (
            (src_label, source_slice, src_port_spec),
            (tgt_label, target_slice, tgt_port_spec),
        ):
            problem = self._slice_out_of_range(label, slice_, port_spec)
            if problem is not None:
                raise ConnectValueError(
                    ConnectProblem.SLICE_RANGE, problem, source=src_end, target=tgt_end
                )

        # Type compatibility check. A pass-through output's type depends on what feeds
        # it, which may not be connected yet: build() checks those edges.
        src_type = self._get_primary_type(src_port_spec)
        if (
            src_port_spec.same_as is None
            and src_type is not None
            and not tgt_port_spec.accepts_payload_type(src_type)
        ):
            raise ConnectTypeError(
                ConnectProblem.TYPE,
                f"Type mismatch: {source}.{source_port} emits {src_type.__name__}, "
                f"but {target}.{target_port} does not accept it",
                source=src_end,
                target=tgt_end,
            )

        edge = Edge(
            source,
            source_port,
            target,
            target_port,
            source_slice,
            target_slice,
            repeat,
            repeat_until,
        )
        self._check_count(edge, src_port_spec, tgt_port_spec)
        self._check_no_overlap(edge, src_port_spec, tgt_port_spec)

        self._edges.append(edge)

    def connect_default(self, source: str, target: str) -> None:
        """Connect default output of source to default input of target.

        Both nodes must have exactly one port in their respective
        input/output groups for default resolution to work.

        Args:
            source: ID of the source node.
            target: ID of the target node.

        Raises:
            KeyError: If source or target node ID is not registered.
            ValueError: If either node has zero or multiple ports.
        """
        if source not in self._nodes:
            raise KeyError(f"Unknown source node '{source}'")
        if target not in self._nodes:
            raise KeyError(f"Unknown target node '{target}'")

        src_outputs = get_outputs(self._nodes[source])
        tgt_inputs = get_inputs(self._nodes[target])

        src_port_name, _ = src_outputs.get_default()
        tgt_port_name, _ = tgt_inputs.get_default()

        self.connect(source, src_port_name, target, tgt_port_name)

    @staticmethod
    def _supplied_rows(edge: Edge, src_spec: OutputPortSpec) -> Optional[int]:
        """Rows the edge carries from a fixed source, repeats included; None when unknown.

        Known only when the source port has a fixed count (or the source slice has an
        end) and no ``repeat_until`` is set: ``repeat_until`` sizes the edge by what it
        fills, not by its source.
        """
        if edge.repeat_until is not None:
            return None
        if edge.source_slice is not None:
            rows = edge.source_slice.length(src_spec.fixed_count)
        else:
            rows = src_spec.fixed_count
        return None if rows is None else rows * max(int(edge.repeat), 1)

    @staticmethod
    def _label(node: str, port: str, slice_: Optional[Slice]) -> str:
        """``node.port`` with the slice in config notation, ``node.port[a~b]``."""
        if slice_ is None:
            return f"{node}.{port}"
        end = "" if slice_.end is None else slice_.end
        return f"{node}.{port}[{slice_.start}~{end}]"

    def _check_count(self, edge: Edge, src_spec: OutputPortSpec, tgt_spec: InputPortSpec) -> None:
        """Refuse an edge whose fixed source rows and fixed target rows differ.

        Owner, 2026-11-16: a count mismatch between fixed ports is a load error. The
        source side is the source port's fixed count (or its slice's length) times
        ``repeat``; the target side is the target port's fixed count (or its slice's
        length). When either side is not fixed, nothing is compared.

        Raises:
            ValueError: If both sides are fixed and differ.
        """
        supplied = self._supplied_rows(edge, src_spec)
        if edge.target_slice is not None:
            window = edge.target_slice.length(tgt_spec.fixed_count)
        else:
            window = tgt_spec.fixed_count
        if supplied is None or window is None or supplied == window:
            return
        repeat = f" (repeated {edge.repeat} times)" if edge.repeat > 1 else ""
        raise ConnectValueError(
            ConnectProblem.COUNT,
            f"Count mismatch: {self._label(edge.source, edge.source_port, edge.source_slice)} "
            f"supplies {supplied} elements{repeat}, but "
            f"{self._label(edge.target, edge.target_port, edge.target_slice)} takes {window}",
            source=_source_end(edge),
            target=_target_end(edge),
            supplied=supplied,
            takes=window,
        )

    def _written_rows(self, edge: Edge) -> tuple[int, Optional[int]]:
        """The rows of the target port an edge writes, as [start, end); end None for to the end.

        The start is the target slice's start (0 without one). The end is the target
        slice's end; else ``start + repeat_until``; else ``start`` plus the rows a fixed
        source supplies; else the end of the port.
        """
        start = edge.target_slice.start if edge.target_slice is not None else 0
        if edge.target_slice is not None and edge.target_slice.end is not None:
            return start, edge.target_slice.end
        if edge.repeat_until is not None:
            return start, start + int(edge.repeat_until)
        src_spec = get_outputs(self._nodes[edge.source]).get(edge.source_port)
        supplied = self._supplied_rows(edge, src_spec.spec) if src_spec is not None else None
        return start, None if supplied is None else start + supplied

    def _check_no_overlap(self, edge: Edge, src_spec: OutputPortSpec, tgt_spec: InputPortSpec) -> None:
        """Refuse an edge already added, or one writing rows an earlier edge writes.

        Owner, 2026-11-16: duplicate edges and overlapping destinations are load errors.
        An edge whose end is unknown writes to the end of the port, so two unsliced
        edges into one port overlap unless the first comes from a fixed source that
        ends before the second starts.

        Raises:
            ValueError: If the same edge is already in the builder, or the rows it
                writes in its target port meet the rows of an earlier edge into it.
        """
        start, end = self._written_rows(edge)
        for other in self._edges:
            if other.target != edge.target or other.target_port != edge.target_port:
                continue
            if (
                other.source == edge.source
                and other.source_port == edge.source_port
                and other.source_slice == edge.source_slice
                and other.target_slice == edge.target_slice
            ):
                raise ConnectValueError(
                    ConnectProblem.DUPLICATE,
                    f"Duplicate connection: {self._label(edge.source, edge.source_port, edge.source_slice)} "
                    f"is already connected to {self._label(edge.target, edge.target_port, edge.target_slice)}",
                    source=_source_end(edge),
                    target=_target_end(edge),
                    other=_source_end(other),
                )
            o_start, o_end = self._written_rows(other)
            if (end is None or o_start < end) and (o_end is None or start < o_end) and start != end and o_start != o_end:
                raise ConnectValueError(
                    ConnectProblem.OVERLAP,
                    f"Overlapping connections into {edge.target}.{edge.target_port}: "
                    f"{self._label(edge.source, edge.source_port, edge.source_slice)} writes "
                    f"{self._rows(start, end)}, which "
                    f"{self._label(other.source, other.source_port, other.source_slice)} already writes "
                    f"({self._rows(o_start, o_end)}). Give each a target slice that does not overlap",
                    source=_source_end(edge),
                    target=_target_end(edge),
                    other=_source_end(other),
                    rows=(start, end),
                    other_rows=(o_start, o_end),
                )

    @staticmethod
    def _rows(start: int, end: Optional[int]) -> str:
        """A row range in config notation: ``rows [a~b]``, ``rows [a~]``."""
        return f"rows [{start}~{'' if end is None else end}]"

    @staticmethod
    def _slice_out_of_range(
        label: str,
        slice_: Optional[Slice],
        spec: InputPortSpec | OutputPortSpec,
    ) -> str | None:
        """Why a slice reaches past the end of a port, or None when it does not.

        Only a port with a fixed count or an upper bound has an end; a slice on
        an unbounded port cannot be checked until frames flow.
        """
        limit = spec.max_count
        if slice_ is None or limit is None:
            return None
        if slice_.start >= limit or (slice_.end is not None and slice_.end > limit):
            end = "" if slice_.end is None else slice_.end
            size = f"has {limit} elements" if spec.fixed_count is not None else f"has at most {limit} elements"
            return f"Slice [{slice_.start}:{end}] is out of range for port {label}, which {size}"
        return None

    def _get_primary_type(self, spec: OutputPortSpec) -> Type[FramePayload] | None:
        """Extract the primary output type from a port spec.

        Args:
            spec: The port specification.

        Returns:
            The first resolved type from the spec's accepts constraint,
            or None if no types could be resolved.
        """
        resolved = spec.resolve_payload_types()
        if resolved:
            return resolved[0]
        return None

    def _output_type(
        self,
        node_id: str,
        port: str,
        incoming_by_node: Dict[str, List[Edge]],
        resolved: Dict[tuple[str, str], Optional[Type[FramePayload]]],
        resolving: set[tuple[str, str]],
    ) -> Optional[Type[FramePayload]]:
        """The payload type an output carries, following pass-through outputs upstream.

        A pass-through output (``OutputPortSpec.same_as``) carries the type of what
        feeds the named input. With nothing feeding it, with sources of different
        types, or inside a cycle, it carries its declared type.
        """
        key = (node_id, port)
        if key in resolved:
            return resolved[key]
        spec = get_outputs(self._nodes[node_id]).get(port)
        if spec is None:
            return None
        declared = self._get_primary_type(spec.spec)
        if spec.spec.same_as is None or key in resolving:
            return declared
        resolving.add(key)
        feeding = {
            self._output_type(e.source, e.source_port, incoming_by_node, resolved, resolving)
            for e in incoming_by_node[node_id]
            if e.target_port == spec.spec.same_as
        }
        resolving.discard(key)
        result = feeding.pop() if len(feeding) == 1 and None not in feeding else declared
        resolved[key] = result
        return result

    def _check_pass_through_types(self, incoming_by_node: Dict[str, List[Edge]]) -> None:
        """Type-check the edges from pass-through outputs, now that every edge is known.

        Raises:
            PortTypeError: If an input does not accept the type a pass-through output
                carries to it.
        """
        resolved: Dict[tuple[str, str], Optional[Type[FramePayload]]] = {}
        for edge in self._edges:
            src_spec = get_outputs(self._nodes[edge.source]).get(edge.source_port)
            if src_spec is None or src_spec.spec.same_as is None:
                continue
            src_type = self._output_type(
                edge.source, edge.source_port, incoming_by_node, resolved, set()
            )
            tgt_spec = get_inputs(self._nodes[edge.target]).get(edge.target_port)
            if src_type is None or tgt_spec is None:
                continue
            if not tgt_spec.spec.accepts_payload_type(src_type):
                raise PortTypeError(
                    edge,
                    f"Type mismatch: {edge.source}.{edge.source_port} passes on "
                    f"{src_type.__name__} from its '{src_spec.spec.same_as}' input, but "
                    f"{edge.target}.{edge.target_port} does not accept it",
                )

    def build(self, allow_cycles: bool = True) -> ExecutionPlan:
        """Validate the graph and compile it into an ExecutionPlan.

        Performs cycle detection, node connection validation, and builds
        the adjacency structure for efficient frame routing. Cycles are
        detected and warned about but do not prevent graph construction.

        Args:
            allow_cycles: If True (default), cycles emit warnings but
                don't raise errors. If False, cycles raise ValueError.

        Returns:
            ExecutionPlan ready for Runtime execution.

        Raises:
            ValueError: If allow_cycles is False and the graph contains a cycle,
                or if any node's connection requirements are not satisfied.
            PortTypeError: If a pass-through output carries a type its target does
                not accept.
        """
        adjacency: Dict[str, List[Edge]] = {node_id: [] for node_id in self._nodes}
        for edge in self._edges:
            adjacency[edge.source].append(edge)

        order, cycles = toposort_with_cycles(list(self._nodes), self._edges)

        if cycles:
            cycle_strs = [
                " → ".join(cycle + [cycle[0]]) for cycle in cycles
            ]
            message = (
                "Cycle(s) detected in graph:\n"
                + "\n".join(f"  {s}" for s in cycle_strs)
                + "\n\nNodes in cycles may receive stale data on first frame."
            )
            if allow_cycles:
                warnings.warn(message, CycleWarning, stacklevel=2)
            else:
                raise ValueError(message)

        # Validate each node's connection requirements
        incoming_by_node: Dict[str, List[Edge]] = {node_id: [] for node_id in self._nodes}
        for edge in self._edges:
            incoming_by_node[edge.target].append(edge)

        self._check_pass_through_types(incoming_by_node)

        for node_id, node in self._nodes.items():
            if hasattr(node, "validate_connections"):
                node.validate_connections(incoming_by_node[node_id])

        back_edges = find_back_edges(adjacency)
        input_programs = compile_input_programs(self._nodes, incoming_by_node, back_edges)

        return ExecutionPlan(
            nodes=self._nodes.copy(),
            adjacency=adjacency,
            topological_order=order,
            input_programs=input_programs,
            back_edges=frozenset(back_edges),
        )


def _source_end(edge: Edge) -> Endpoint:
    """The source end of an edge."""
    return Endpoint(edge.source, edge.source_port, edge.source_slice)


def _target_end(edge: Edge) -> Endpoint:
    """The target end of an edge."""
    return Endpoint(edge.target, edge.target_port, edge.target_slice)
