"""Element counts: how many elements every connected port carries, fixed when the plan is
built.

Owner, 2026-11-21 (rasl-00l): connection sizes are fixed once configuration is complete,
so a port's length never depends on which of its sources have written. An output's count
comes from, in order:

- its spec's fixed ``count`` (a source declares it from its config);
- the input its spec names in ``count_of`` or ``same_as`` (a node that keeps the number
  of elements);
- the node's ``output_counts(inputs)`` hook, given each input's ``InputSize`` (a node
  whose count is computed, such as one that regroups values), returning by output port
  name a count, or an ``InputSize`` when it also knows the output's components.

An input's count is the furthest element its connections write: a target slice's end,
``start + repeat_until``, or ``start`` plus what the source supplies (its slice of the
source's count, times ``repeat``); a fixed-count spec must hold them all. A back-edge's
source comes later in the order, so counts are resolved in repeated passes until nothing
changes; a cycle whose counts only follow one another (each node keeping its input's
count) has none, which is a load error.

A port whose payload is not a matrix (a counter) has no elements to count. A connected
port whose count cannot be resolved is a load error, placed on a connection into it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Dict, List, NamedTuple, Optional, Set, Tuple

from rasl.graph.edge import Edge
from rasl.graph.errors import ConnectProblem, ConnectTypeError, Endpoint
from rasl.graph.node.protocol import get_inputs, get_outputs
from rasl.signal import MatrixPayload

if TYPE_CHECKING:
    from rasl.graph.node.protocol import Node

PortKey = Tuple[str, str]
"""(node id, port name)."""


class InputSize(NamedTuple):
    """An input port's size, as a node's ``output_counts`` hook is given it.

    Attributes:
        count: Elements, or None when unknown (or the port is not connected).
        components: Values per element, or None when unknown.
    """

    count: Optional[int]
    components: Optional[int]


class InputCountError(ValueError):
    """Raised by a node's ``output_counts`` hook when its inputs' counts do not fit together.

    Attributes:
        port: The input port the problem is placed on (the error goes on a connection into it).
    """

    def __init__(self, port: str, message: str) -> None:
        """Name the input port and say what is wrong."""
        super().__init__(message)
        self.port = port


class PortCountError(ConnectTypeError):
    """A connection whose element count is unknown or does not fit, found when the plan is built.

    Problem ``COUNT``. It carries the connection, so the config loader places it on the
    connect line that made it.

    Attributes:
        node: The id of the node the connection feeds.
        edge: The connection.
    """

    def __init__(
        self, edge: Edge, message: str, *, supplied: int | None = None, takes: int | None = None
    ) -> None:
        """Record the connection, the message and the counts involved."""
        super().__init__(
            ConnectProblem.COUNT,
            message,
            source=Endpoint(edge.source, edge.source_port, edge.source_slice),
            target=Endpoint(edge.target, edge.target_port, edge.target_slice),
            supplied=supplied,
            takes=takes,
        )
        self.node = edge.target
        self.edge = edge


def _is_matrix(types: Sequence[type]) -> bool:
    """Whether a port with these payload types carries elements (some type is a matrix)."""
    return not types or any(isinstance(t, type) and issubclass(t, MatrixPayload) for t in types)


def _label(node: str, port: str) -> str:
    return f"{node}.{port}"


def _edge_label(edge: Edge, side: str) -> str:
    if side == "source":
        node, port, slice_ = edge.source, edge.source_port, edge.source_slice
    else:
        node, port, slice_ = edge.target, edge.target_port, edge.target_slice
    if slice_ is None:
        return f"{node}.{port}"
    return f"{node}.{port}[{slice_.start}~{'' if slice_.end is None else slice_.end}]"


class CountResolver:
    """Works out every port's element count for a graph, in topological order.

    Attributes:
        inputs: Each counted input port's element count.
        outputs: Each counted output port's element count.
    """

    def __init__(
        self,
        nodes: Mapping[str, "Node"],
        incoming_by_node: Mapping[str, List[Edge]],
        order: Sequence[str],
        back_edges: Set[Tuple[str, str, str, str]],
    ) -> None:
        """Hold the graph; ``resolve`` does the work."""
        self._nodes = nodes
        self._incoming = incoming_by_node
        self._order = order
        self._back = back_edges
        self.inputs: Dict[PortKey, int] = {}
        self.outputs: Dict[PortKey, Optional[int]] = {}
        self._uncounted: Set[PortKey] = set()  # output ports with no elements (not a matrix)
        self._out_components: Dict[PortKey, Optional[int]] = {}

    def _is_back(self, edge: Edge) -> bool:
        return (edge.source, edge.source_port, edge.target, edge.target_port) in self._back

    def _source_count(self, edge: Edge) -> Optional[int]:
        return self.outputs.get((edge.source, edge.source_port))

    def supplied(self, edge: Edge) -> Optional[int]:
        """Elements the edge carries from its source, repeats included; None if unknown.

        None with ``repeat_until``, which sizes the edge by what it fills instead.
        """
        if edge.repeat_until is not None:
            return None
        slice_ = edge.source_slice
        if slice_ is not None and slice_.end is not None:
            rows: Optional[int] = slice_.end - slice_.start
        else:
            count = self._source_count(edge)
            start = slice_.start if slice_ is not None else 0
            rows = None if count is None else count - start
        return None if rows is None else rows * max(int(edge.repeat), 1)

    def written(self, edge: Edge) -> Tuple[int, Optional[int]]:
        """The elements of its target port the edge writes, [start, end); end None if unknown."""
        start = edge.target_slice.start if edge.target_slice is not None else 0
        if edge.target_slice is not None and edge.target_slice.end is not None:
            return start, edge.target_slice.end
        if edge.repeat_until is not None:
            return start, start + int(edge.repeat_until)
        supplied = self.supplied(edge)
        return start, None if supplied is None else start + supplied

    def resolve(self) -> None:
        """Resolve every port's count, then check every connection against them.

        Raises:
            PortCountError: A connected port's count cannot be resolved, a connection
                supplies another number of elements than its target slice takes, a
                connection writes past the end of its target port, or a back-edge ends
                at a port whose count is unknown without it.
        """
        # Repeated until nothing changes: a cycle's order and its back-edge need not agree,
        # so one pass can meet a node before what feeds it is counted
        # A node's hook may see partial counts in an early pass (a back-edge not counted
        # yet), so its errors count only in a last pass over the settled counts
        for _ in range(len(self._order) + 1):
            before = (dict(self.inputs), dict(self.outputs), dict(self._out_components))
            for node_id in self._order:
                self._resolve_node(node_id, final=False)
            if (self.inputs, self.outputs, self._out_components) == before:
                break
        for node_id in self._order:
            self._resolve_node(node_id, final=True)
        for node_id in self._order:
            for edge in self._incoming.get(node_id, ()):
                self._check_edge(edge)

    def _resolve_node(self, node_id: str, *, final: bool) -> None:
        node = self._nodes[node_id]
        edges_by_port: Dict[str, List[Edge]] = {}
        for edge in self._incoming.get(node_id, ()):
            edges_by_port.setdefault(edge.target_port, []).append(edge)

        sizes: Dict[str, InputSize] = {}
        for port in get_inputs(node):
            spec = port.spec
            edges = edges_by_port.get(port.name, [])
            forward = [e for e in edges if not self._is_back(e)]
            # A back-edge's source comes later in the order: it sizes the port once its
            # source is counted (a later pass), or at once when its target slice says where
            # it ends. A loop whose counts only follow each other stays unknown
            sizing = forward + [
                e
                for e in edges
                if self._is_back(e)
                and (self._end_without_source(e) or self._source_count(e) is not None)
            ]
            if forward and all((e.source, e.source_port) in self._uncounted for e in forward):
                sizes[port.name] = InputSize(None, None)  # carries no elements (a counter)
                continue
            # Until every back-edge into it is counted, a port's count is unknown, not partial
            pending = len(sizing) < len(edges)
            count = spec.fixed_count if pending else self._input_count(spec.fixed_count, sizing)
            sizes[port.name] = InputSize(count, self._input_components(spec, edges))
            if count is not None:
                self.inputs[(node_id, port.name)] = count

        hook = getattr(node, "output_counts", None)
        computed: Mapping[str, object] = {}
        if hook is not None:
            try:
                computed = hook(sizes)
            except InputCountError as error:
                if not final:
                    computed = {}
                else:
                    self._raise_hook_error(node_id, edges_by_port, error)

        for port in get_outputs(node):
            spec = port.spec
            key = (node_id, port.name)
            if not _is_matrix(spec.resolve_payload_types()):
                self._uncounted.add(key)
                continue
            follows = sizes.get(spec.count_follows) if spec.count_follows is not None else None
            # A hook returns a count, or an InputSize when it also knows the width
            value = computed.get(port.name)
            hooked = value if isinstance(value, InputSize) else InputSize(value, None)  # type: ignore[arg-type]
            if spec.fixed_count is not None:
                self.outputs[key] = spec.fixed_count
            elif follows is not None:
                self.outputs[key] = follows.count
            else:
                self.outputs[key] = hooked.count
            components = spec.known_components
            if components is None and spec.same_as is not None and follows is not None:
                components = follows.components
            if components is None:
                components = hooked.components
            self._out_components[key] = components

    def _raise_hook_error(
        self, node_id: str, edges_by_port: Mapping[str, List[Edge]], error: InputCountError
    ) -> None:
        """Raise a hook's ``InputCountError`` on a connection into the port it names."""
        edges = edges_by_port.get(error.port) or list(self._incoming.get(node_id, ()))
        if not edges:
            raise ValueError(f"Node '{node_id}': {error}") from error
        raise PortCountError(edges[0], str(error)) from error

    def _input_components(self, spec: object, edges: List[Edge]) -> Optional[int]:
        """Values per element of the frame a port receives, or None when unknown.

        The width every accepted type fixes; else, for one whole connection, its source's
        width; else the widest source (a built frame is as wide as its widest source).
        """
        accepted = [getattr(t, "components", None) for t in spec.resolve_payload_types()]  # type: ignore[attr-defined]
        if accepted and all(isinstance(c, int) and c == accepted[0] for c in accepted):
            return int(accepted[0])  # type: ignore[arg-type]
        widths = [self._out_components.get((e.source, e.source_port)) for e in edges]
        if not widths or any(w is None for w in widths):
            return None
        return max(widths)  # type: ignore[type-var]

    @staticmethod
    def _end_without_source(edge: Edge) -> bool:
        """Whether where the edge ends in its target is known without its source's count."""
        return (edge.target_slice is not None and edge.target_slice.end is not None) or (
            edge.repeat_until is not None
        )

    def _input_count(self, fixed: Optional[int], edges: List[Edge]) -> Optional[int]:
        """A port's count: its fixed count, else the furthest element its edges write."""
        if fixed is not None:
            return fixed
        if not edges:
            return None
        ends = [self.written(e)[1] for e in edges]
        if any(end is None for end in ends):
            return None
        return max(ends)  # type: ignore[type-var]

    def _check_edge(self, edge: Edge) -> None:
        """Check one connection against the resolved counts."""
        source_key = (edge.source, edge.source_port)
        if source_key in self._uncounted:
            return
        target_key = (edge.target, edge.target_port)
        port_count = self.inputs.get(target_key)
        source_count = self._source_count(edge)
        start, end = self.written(edge)
        target = _edge_label(edge, "target")
        source = _edge_label(edge, "source")

        if source_count is None:
            raise PortCountError(
                edge,
                f"Element count unknown: {_label(edge.source, edge.source_port)} has no element "
                f"count fixed by its config or its inputs, so the connection to {target} cannot "
                f"be sized",
            )
        if port_count is None:
            if self._is_back(edge):
                message = (
                    f"Element count unknown: {target} is fed by a back-edge from {source}, and "
                    f"the counts around that cycle only follow one another; give a node in the "
                    f"cycle a count, or the back-edge a target slice with an end"
                )
            else:
                message = f"Element count unknown: {target} cannot be sized from its connections"
            raise PortCountError(edge, message)

        if end is not None and end > port_count:
            raise PortCountError(
                edge,
                f"Count mismatch: {source} writes elements [{start}~{end}] of "
                f"{_label(edge.target, edge.target_port)}, which has {port_count}",
                supplied=end - start,
                takes=port_count - start,
            )
        supplied = self.supplied(edge)
        if edge.target_slice is not None and edge.target_slice.end is not None and supplied is not None:
            window = edge.target_slice.end - edge.target_slice.start
            if supplied != window:
                repeat = f" (repeated {edge.repeat} times)" if edge.repeat > 1 else ""
                raise PortCountError(
                    edge,
                    f"Count mismatch: {source} supplies {supplied} elements{repeat}, but "
                    f"{target} takes {window}",
                    supplied=supplied,
                    takes=window,
                )
        if edge.source_slice is not None and source_count is not None:
            s_end = edge.source_slice.end if edge.source_slice.end is not None else source_count
            if edge.source_slice.start >= source_count or s_end > source_count:
                raise PortCountError(
                    edge,
                    f"Slice [{edge.source_slice.start}:{'' if edge.source_slice.end is None else edge.source_slice.end}] "
                    f"is out of range for port {_label(edge.source, edge.source_port)}, which has "
                    f"{source_count} elements",
                )
