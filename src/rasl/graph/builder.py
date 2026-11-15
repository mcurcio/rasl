"""Assembling and validating a graph, and compiling it into an ExecutionPlan.
"""

from __future__ import annotations

import warnings
from typing import Dict, List, Optional, Set, Tuple, Type

from rasl.graph.edge import Edge
from rasl.graph.node.protocol import Node, get_inputs, get_outputs
from rasl.graph.plan import ExecutionPlan
from rasl.graph.ports.port import InputPort
from rasl.graph.ports.spec import InputPortSpec, OutputPortSpec
from rasl.graph.routing import CopySliceOp, EdgeOp, InputPortProgram, RepeatSliceOp
from rasl.graph.slices import Slice
from rasl.signal import FramePayload


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

        Raises:
            KeyError: If source or target node ID is not registered.
            ValueError: If a port does not exist on its node, if a slice
                reaches past the end of a sized port, or if slice lengths
                are incompatible.
            TypeError: If the port types are incompatible, or a port names
                a payload type that is not registered.
        """
        if source not in self._nodes:
            raise KeyError(f"Unknown source node '{source}'")
        if target not in self._nodes:
            raise KeyError(f"Unknown target node '{target}'")

        src_node = self._nodes[source]
        tgt_node = self._nodes[target]

        src_outputs = get_outputs(src_node)
        tgt_inputs = get_inputs(tgt_node)

        # Validate port existence
        if source_port not in src_outputs:
            raise ValueError(
                f"Node '{source}' has no output port '{source_port}'. "
                f"Available: {src_outputs.names}"
            )
        if target_port not in tgt_inputs:
            raise ValueError(
                f"Node '{target}' has no input port '{target_port}'. "
                f"Available: {tgt_inputs.names}"
            )

        src_spec = src_outputs.get(source_port)
        tgt_spec = tgt_inputs.get(target_port)
        if src_spec is None or tgt_spec is None:
            raise ValueError("Port lookup failed")
        src_port_spec = src_spec.spec
        tgt_port_spec = tgt_spec.spec

        src_label = f"{source}.{source_port}"
        tgt_label = f"{target}.{target_port}"

        # A type name nothing is registered under would match any payload
        for label, port_spec in ((src_label, src_port_spec), (tgt_label, tgt_port_spec)):
            unknown = port_spec.unknown_type_names()
            if unknown:
                from rasl.signal import list_payload_types

                raise TypeError(
                    f"Port {label} names a payload type that is not registered: "
                    f"{', '.join(repr(name) for name in unknown)}. "
                    f"Registered: {', '.join(list_payload_types())}"
                )

        # A slice must lie inside a port whose size is known
        self._check_slice_in_range(src_label, source_slice, src_port_spec)
        self._check_slice_in_range(tgt_label, target_slice, tgt_port_spec)

        # Type compatibility check
        src_type = self._get_primary_type(src_port_spec)
        if src_type is not None and not tgt_port_spec.accepts_payload_type(src_type):
            raise TypeError(
                f"Type mismatch: {source}.{source_port} emits {src_type.__name__}, "
                f"but {target}.{target_port} does not accept it"
            )

        # Validate slice compatibility if both are specified with fixed lengths
        if source_slice is not None and target_slice is not None:
            src_len = source_slice.length(src_port_spec.fixed_count)
            tgt_len = target_slice.length(tgt_port_spec.fixed_count)
            if src_len is not None and tgt_len is not None and src_len != tgt_len:
                raise ValueError(
                    f"Slice length mismatch: {source}.{source_port}[{source_slice.start}:{source_slice.end}] "
                    f"has {src_len} channels, but {target}.{target_port}[{target_slice.start}:{target_slice.end}] "
                    f"has {tgt_len} channels"
                )

        self._edges.append(
            Edge(
                source,
                source_port,
                target,
                target_port,
                source_slice,
                target_slice,
                repeat,
                repeat_until,
            )
        )

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
    def _check_slice_in_range(
        label: str,
        slice_: Optional[Slice],
        spec: InputPortSpec | OutputPortSpec,
    ) -> None:
        """Refuse a slice that reaches past the end of a port.

        Only a port with a fixed count or an upper bound has an end; a slice on
        an unbounded port cannot be checked until frames flow.

        Raises:
            ValueError: If the slice starts at or past the end, or ends past it.
        """
        limit = spec.max_count
        if slice_ is None or limit is None:
            return
        if slice_.start >= limit or (slice_.end is not None and slice_.end > limit):
            end = "" if slice_.end is None else slice_.end
            size = f"has {limit} elements" if spec.fixed_count is not None else f"has at most {limit} elements"
            raise ValueError(
                f"Slice [{slice_.start}:{end}] is out of range for port {label}, which {size}"
            )

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

    def _find_cycles(self) -> List[List[str]]:
        """Find all cycles in the graph using Tarjan's SCC algorithm.

        Returns:
            List of cycles, where each cycle is a list of node IDs.
            Only SCCs with more than one node or self-loops are returned.
        """
        adjacency: Dict[str, List[str]] = {node_id: [] for node_id in self._nodes}
        for edge in self._edges:
            adjacency[edge.source].append(edge.target)

        index_counter = [0]
        stack: List[str] = []
        lowlinks: Dict[str, int] = {}
        index: Dict[str, int] = {}
        on_stack: Set[str] = set()
        sccs: List[List[str]] = []

        def strongconnect(node: str) -> None:
            index[node] = index_counter[0]
            lowlinks[node] = index_counter[0]
            index_counter[0] += 1
            stack.append(node)
            on_stack.add(node)

            for neighbor in adjacency[node]:
                if neighbor not in index:
                    strongconnect(neighbor)
                    lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
                elif neighbor in on_stack:
                    lowlinks[node] = min(lowlinks[node], index[neighbor])

            if lowlinks[node] == index[node]:
                scc: List[str] = []
                while True:
                    w = stack.pop()
                    on_stack.remove(w)
                    scc.append(w)
                    if w == node:
                        break
                if len(scc) > 1:
                    sccs.append(scc)
                elif len(scc) == 1 and scc[0] in adjacency[scc[0]]:
                    # Self-loop
                    sccs.append(scc)

        for node in self._nodes:
            if node not in index:
                strongconnect(node)

        return sccs

    def _toposort_with_cycles(self) -> Tuple[Tuple[str, ...], List[List[str]]]:
        """Compute execution order, handling cycles gracefully.

        Uses Kahn's algorithm but handles cycles by breaking them
        arbitrarily when no zero-indegree nodes remain.

        Returns:
            Tuple of (execution_order, cycles) where cycles is a list
            of detected cycles (each cycle is a list of node IDs).
        """
        cycles = self._find_cycles()

        indegree: Dict[str, int] = {node_id: 0 for node_id in self._nodes}
        adjacency: Dict[str, List[str]] = {node_id: [] for node_id in self._nodes}
        for edge in self._edges:
            indegree[edge.target] += 1
            adjacency[edge.source].append(edge.target)

        queue: List[str] = [node for node, deg in indegree.items() if deg == 0]
        order: List[str] = []
        remaining: Set[str] = set(self._nodes.keys())

        while remaining:
            if queue:
                node = queue.pop(0)
            else:
                # Cycle detected - pick an arbitrary remaining node
                node = next(iter(remaining))

            if node not in remaining:
                continue

            order.append(node)
            remaining.remove(node)

            for neighbor in adjacency[node]:
                if neighbor in remaining:
                    indegree[neighbor] -= 1
                    if indegree[neighbor] == 0:
                        queue.append(neighbor)

        return tuple(order), cycles

    def _find_back_edges(self, adjacency: Dict[str, List[Edge]]) -> Set[Tuple[str, str, str, str]]:
        visited: Set[str] = set()
        in_stack: Set[str] = set()
        back_edges: Set[Tuple[str, str, str, str]] = set()

        def dfs(node_id: str) -> None:
            visited.add(node_id)
            in_stack.add(node_id)

            for edge in adjacency.get(node_id, []):
                tgt = edge.target
                if tgt in in_stack:
                    back_edges.add((edge.source, edge.source_port, edge.target, edge.target_port))
                elif tgt not in visited:
                    dfs(tgt)

            in_stack.remove(node_id)

        for node_id in adjacency:
            if node_id not in visited:
                dfs(node_id)

        return back_edges

    def _compile_input_programs(
        self,
        incoming_by_node: Dict[str, List[Edge]],
        back_edges: Set[Tuple[str, str, str, str]],
    ) -> Dict[Tuple[str, str], InputPortProgram]:
        programs: Dict[Tuple[str, str], InputPortProgram] = {}

        for target_node_id, edges in incoming_by_node.items():
            node = self._nodes[target_node_id]
            inputs = get_inputs(node)

            by_port: Dict[str, List[Edge]] = {}
            for e in edges:
                by_port.setdefault(e.target_port, []).append(e)

            for port_name, port_edges in by_port.items():
                port = inputs.get(port_name)
                if port is None or not isinstance(port, InputPort):
                    continue

                fixed_rows = port.spec.fixed_count

                fixed_cols: int | None = None
                resolved = port.spec.resolve_payload_types()
                if resolved:
                    comps = [getattr(t, "components", None) for t in resolved]
                    if comps and all((c is not None and c == comps[0]) for c in comps):
                        fixed_cols = int(comps[0])

                passthrough: Tuple[str, str] | None = None
                passthrough_is_back = False
                ops: List[EdgeOp] = []

                if len(port_edges) == 1:
                    e = port_edges[0]
                    if (
                        e.source_slice is None
                        and e.target_slice is None
                        and e.repeat <= 1
                        and e.repeat_until is None
                    ):
                        passthrough = (e.source, e.source_port)
                        passthrough_is_back = (
                            (e.source, e.source_port, e.target, e.target_port) in back_edges
                        )
                        programs[(target_node_id, port_name)] = InputPortProgram(
                            target=port,
                            buffer_key=(target_node_id, port_name),
                            fixed_rows=fixed_rows,
                            fixed_cols=fixed_cols,
                            passthrough=passthrough,
                            passthrough_is_back_edge=passthrough_is_back,
                            ops=(),
                        )
                        continue

                for e in port_edges:
                    is_back = (e.source, e.source_port, e.target, e.target_port) in back_edges

                    src_start = e.source_slice.start if e.source_slice else 0
                    src_end = e.source_slice.end if (e.source_slice and e.source_slice.end is not None) else -1

                    dst_start = e.target_slice.start if e.target_slice else 0
                    dst_end = e.target_slice.end if (e.target_slice and e.target_slice.end is not None) else -1

                    if e.repeat > 1 or e.repeat_until is not None:
                        ops.append(
                            RepeatSliceOp(
                                source=e.source,
                                source_port=e.source_port,
                                is_back_edge=is_back,
                                src_start=src_start,
                                src_end=src_end,
                                dst_start=dst_start,
                                dst_end=dst_end,
                                repeat=int(e.repeat),
                                repeat_until=e.repeat_until,
                            )
                        )
                    else:
                        ops.append(
                            CopySliceOp(
                                source=e.source,
                                source_port=e.source_port,
                                is_back_edge=is_back,
                                src_start=src_start,
                                src_end=src_end,
                                dst_start=dst_start,
                                dst_end=dst_end,
                            )
                        )

                programs[(target_node_id, port_name)] = InputPortProgram(
                    target=port,
                    buffer_key=(target_node_id, port_name),
                    fixed_rows=fixed_rows,
                    fixed_cols=fixed_cols,
                    passthrough=None,
                    passthrough_is_back_edge=False,
                    ops=tuple(ops),
                )

        return programs

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
        """
        adjacency: Dict[str, List[Edge]] = {node_id: [] for node_id in self._nodes}
        for edge in self._edges:
            adjacency[edge.source].append(edge)

        order, cycles = self._toposort_with_cycles()

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

        for node_id, node in self._nodes.items():
            if hasattr(node, "validate_connections"):
                node.validate_connections(incoming_by_node[node_id])

        back_edges = self._find_back_edges(adjacency)
        input_programs = self._compile_input_programs(incoming_by_node, back_edges)

        return ExecutionPlan(
            nodes=self._nodes.copy(),
            adjacency=adjacency,
            topological_order=order,
            input_programs=input_programs,
        )
