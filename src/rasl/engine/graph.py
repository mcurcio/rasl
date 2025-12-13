"""Graph construction and validation for the RASL processing DAG.

This module provides the GraphBuilder for assembling nodes and edges
into an ExecutionPlan that the Runtime can execute. It handles:

- Node registration with duplicate detection
- Edge connection with validation
- Cycle detection with warnings (cycles are allowed)
- Compilation into an ExecutionPlan
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type

from rasl.config.connect_parser import ResolvedSlice
import time

import numpy as np

from rasl.engine.frames import Frame, FramePayload, MatrixPayload
from rasl.engine.nodes import Node, get_inputs, get_outputs
from .ports import InputPort, InputPortSpec, OutputPortSpec


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
        ...     source_slice=ResolvedSlice(0, 151),
        ...     target_slice=ResolvedSlice(0, 151),
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

    source_slice: Optional[ResolvedSlice] = None
    """Optional channel slice on the source port (None = full port)."""

    target_slice: Optional[ResolvedSlice] = None
    """Optional channel slice on the target port (None = full port)."""

    repeat: int = 1

    repeat_until: int | None = None


@dataclass(slots=True)
class ExecutionPlan:
    """Compiled graph ready for runtime execution.

    An ExecutionPlan contains all information needed by the Runtime
    to execute the graph: the nodes, their connections, and the order
    in which they should be started (topological order).

    Created by GraphBuilder.build() after validation passes.

    Attributes:
        nodes: Map of node ID to Node instance.
        adjacency: Map of source node ID to list of outgoing Edges.
        topological_order: Node IDs in valid execution order.
            Sources come first, sinks come last.

    Example:
        >>> plan = builder.build()
        >>> for node_id in plan.topological_order:
        ...     node = plan.nodes[node_id]
        ...     edges = plan.adjacency[node_id]
    """

    nodes: Dict[str, Node]
    """Map of node ID to Node instance."""

    adjacency: Dict[str, List[Edge]]
    """Map of source node ID to list of outgoing Edges."""

    topological_order: Tuple[str, ...]
    """Node IDs in valid execution order (sources first, sinks last)."""

    input_programs: Dict[Tuple[str, str], "InputPortProgram"] = field(default_factory=dict)

    def describe(self) -> Dict[str, Any]:
        """Serialize the execution plan to a JSON-compatible dictionary.

        Returns a complete description of the graph structure including
        all nodes, their ports, and edge connections. Useful for debugging,
        CLI inspection, and as a foundation for web API responses.

        Returns:
            Dictionary with 'nodes', 'edges', and 'topological_order' keys.

        Example:
            >>> plan = builder.build()
            >>> desc = plan.describe()
            >>> print(json.dumps(desc, indent=2))
        """
        nodes_desc: List[Dict[str, Any]] = []
        for node_id in self.topological_order:
            node = self.nodes[node_id]
            inputs = get_inputs(node)
            outputs = get_outputs(node)
            nodes_desc.append({
                "id": node.id,
                "type": type(node).__name__,
                "inputs": list(inputs.names),
                "outputs": list(outputs.names),
            })

        edges_desc: List[Tuple[str, str, str, str]] = []
        for source_id, edge_list in self.adjacency.items():
            for edge in edge_list:
                edges_desc.append((
                    edge.source,
                    edge.source_port,
                    edge.target,
                    edge.target_port,
                ))

        return {
            "nodes": nodes_desc,
            "edges": edges_desc,
            "topological_order": list(self.topological_order),
        }


@dataclass(slots=True)
class CopySliceOp:
    source: str
    source_port: str
    is_back_edge: bool
    src_start: int
    src_end: int
    dst_start: int
    dst_end: int

    def required_rows(self, src_rows: int) -> int:
        if self.dst_end >= 0:
            return self.dst_end
        src_len = (self.src_end - self.src_start) if self.src_end >= 0 else (src_rows - self.src_start)
        if src_len < 0:
            src_len = 0
        return self.dst_start + src_len

    def populate(self, dst: np.ndarray, src: np.ndarray) -> None:
        src_rows = int(src.shape[0])
        src_end = self.src_end if self.src_end >= 0 else src_rows
        if src_end < self.src_start:
            return
        src_view = src[self.src_start:src_end, :]
        if src_view.size == 0:
            return
        dst_rows = int(dst.shape[0])
        dst_end = self.dst_end if self.dst_end >= 0 else dst_rows
        if dst_end < self.dst_start:
            return
        max_len = max(0, min(dst_end, dst_rows) - self.dst_start)
        if max_len <= 0:
            return
        copy_len = min(int(src_view.shape[0]), max_len)
        if copy_len <= 0:
            return
        cols = min(int(dst.shape[1]), int(src_view.shape[1]))
        dst[self.dst_start : self.dst_start + copy_len, :cols] = src_view[:copy_len, :cols]


@dataclass(slots=True)
class RepeatSliceOp:
    source: str
    source_port: str
    is_back_edge: bool
    src_start: int
    src_end: int
    dst_start: int
    dst_end: int
    repeat: int
    repeat_until: int | None

    def required_rows(self, src_rows: int) -> int:
        if self.dst_end >= 0:
            return self.dst_end
        if self.repeat_until is not None:
            return self.dst_start + int(self.repeat_until)
        src_len = (self.src_end - self.src_start) if self.src_end >= 0 else (src_rows - self.src_start)
        if src_len < 0:
            src_len = 0
        return self.dst_start + (src_len * int(self.repeat))

    def populate(self, dst: np.ndarray, src: np.ndarray) -> None:
        src_rows = int(src.shape[0])
        src_end = self.src_end if self.src_end >= 0 else src_rows
        if src_end < self.src_start:
            return
        src_view = src[self.src_start:src_end, :]
        if src_view.size == 0:
            return

        dst_rows = int(dst.shape[0])
        dst_end = self.dst_end if self.dst_end >= 0 else dst_rows
        dst_end = min(dst_end, dst_rows)
        if dst_end <= self.dst_start:
            return

        window = dst_end - self.dst_start
        if window <= 0:
            return

        if self.repeat_until is not None:
            total = min(window, int(self.repeat_until))
            if total <= 0:
                return
            rep = (total + int(src_view.shape[0]) - 1) // int(src_view.shape[0])
        else:
            rep = int(self.repeat)
            total = min(window, int(src_view.shape[0]) * rep)

        cols = min(int(dst.shape[1]), int(src_view.shape[1]))
        src_block = src_view[:, :cols]
        block_rows = int(src_block.shape[0])
        if block_rows <= 0:
            return

        for i in range(rep):
            base = self.dst_start + (i * block_rows)
            if base >= dst_end:
                break
            end = min(base + block_rows, self.dst_start + total, dst_end)
            copy_len = end - base
            if copy_len > 0:
                dst[base:end, :cols] = src_block[:copy_len, :]


EdgeOp = CopySliceOp | RepeatSliceOp


# Module-level profiling state (outside dataclass to avoid mutable default issues)
_ipp_profile_enabled: bool = False
_ipp_profile_stats: dict = {}  # {buffer_key: {resolve_ms, asarray_ms, buffer_ms, copy_ms, total_ms, count}}


@dataclass(slots=True)
class InputPortProgram:
    target: InputPort
    buffer_key: Tuple[str, str]
    fixed_rows: int | None
    fixed_cols: int | None
    passthrough: Tuple[str, str] | None
    passthrough_is_back_edge: bool
    ops: Tuple[EdgeOp, ...]

    @staticmethod
    def enable_profiling(enabled: bool = True) -> None:
        global _ipp_profile_enabled, _ipp_profile_stats
        _ipp_profile_enabled = enabled
        if enabled:
            _ipp_profile_stats.clear()

    @staticmethod
    def get_profile_stats() -> dict:
        return dict(_ipp_profile_stats)

    def populate(
        self,
        tick: int,
        resolve: Callable[[str, str, bool, int], Frame | None],
        ensure_buffer: Callable[[Tuple[str, str], int, int], np.ndarray],
    ) -> Frame | None:
        if self.passthrough is not None:
            src_node, src_port = self.passthrough
            return resolve(src_node, src_port, self.passthrough_is_back_edge, tick)

        profile = _ipp_profile_enabled
        if profile:
            t0 = time.perf_counter()
            resolve_time = 0.0
            asarray_time = 0.0

        first: Frame | None = None
        rows = int(self.fixed_rows) if self.fixed_rows is not None else 0
        cols = int(self.fixed_cols) if self.fixed_cols is not None else 1
        sources: list[tuple[EdgeOp, np.ndarray]] = []

        for op in self.ops:
            if profile:
                t_resolve = time.perf_counter()
            frame = resolve(op.source, op.source_port, op.is_back_edge, tick)
            if profile:
                resolve_time += time.perf_counter() - t_resolve

            if frame is None or not hasattr(frame.payload, "data"):
                continue
            if first is None:
                first = frame

            if profile:
                t_asarray = time.perf_counter()
            src = np.asarray(frame.payload.data, dtype=np.float32)
            if profile:
                asarray_time += time.perf_counter() - t_asarray

            if src.ndim == 1:
                src = src.reshape(-1, 1)
            if src.ndim != 2:
                continue
            rows = max(rows, op.required_rows(int(src.shape[0])))
            if self.fixed_cols is None:
                cols = max(cols, int(src.shape[1]))
            sources.append((op, src))

        if first is None or rows <= 0 or cols <= 0:
            return None

        if profile:
            t_buffer = time.perf_counter()
        buf = ensure_buffer(self.buffer_key, rows, cols)
        view = buf[:rows, :cols]
        view.fill(0.0)
        if profile:
            buffer_time = time.perf_counter() - t_buffer
            t_copy = time.perf_counter()

        for op, src in sources:
            op.populate(view, src)

        if profile:
            copy_time = time.perf_counter() - t_copy
            total_time = time.perf_counter() - t0

            key = self.buffer_key
            stats = _ipp_profile_stats.get(key)
            if stats is None:
                stats = {"resolve_ms": 0.0, "asarray_ms": 0.0, "buffer_ms": 0.0, "copy_ms": 0.0, "total_ms": 0.0, "count": 0}
                _ipp_profile_stats[key] = stats
            stats["resolve_ms"] += resolve_time * 1000
            stats["asarray_ms"] += asarray_time * 1000
            stats["buffer_ms"] += buffer_time * 1000
            stats["copy_ms"] += copy_time * 1000
            stats["total_ms"] += total_time * 1000
            stats["count"] += 1

        return Frame(
            topic=first.topic,
            timestamp=first.timestamp,
            payload=MatrixPayload(view),
            metadata=first.metadata,
        )


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
        source_slice: Optional[ResolvedSlice] = None,
        target_slice: Optional[ResolvedSlice] = None,
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
            ValueError: If a port does not exist on its node, or if
                slice lengths are incompatible.
            TypeError: If the port types are incompatible.
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

    def resolve_node_connections(self, target_node_id: str) -> None:
        """Resolve connection descriptors for a node into edges.

        Called after all nodes are added. Resolves ConnectionDescriptors
        stored on the target node into actual Edge connections.

        For repeat connections:
        - If source has no slice, uses source port's channel count as slice length
        - Target slices are offset by (repeat_index * slice_length)

        Args:
            target_node_id: ID of the node whose connections to resolve.

        Raises:
            KeyError: If target or source node not found.
            ValueError: If port resolution fails.
        """
        from rasl.config.connection import ConnectionDescriptor, parse_port_ref

        if target_node_id not in self._nodes:
            raise KeyError(f"Unknown target node '{target_node_id}'")

        target_node = self._nodes[target_node_id]
        tgt_inputs = get_inputs(target_node)

        # Get connection descriptors from node
        descriptors = target_node.get_connection_descriptors()

        for desc in descriptors:
            # Parse source reference
            source_ref = parse_port_ref(desc.source)
            if not source_ref.node:
                raise ValueError(f"Source must specify a node: {desc.source}")

            source_node_id = source_ref.node
            if source_node_id not in self._nodes:
                raise KeyError(f"Unknown source node '{source_node_id}'")

            source_node = self._nodes[source_node_id]
            src_outputs = get_outputs(source_node)

            # Resolve source port (use default if not specified)
            if source_ref.port:
                source_port = source_ref.port
            else:
                source_port, _ = src_outputs.get_default()

            # Get source port spec for channel info
            src_spec = src_outputs.get(source_port)

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
                self.connect(
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
                    source_slice = ResolvedSlice(0, slice_length)
            else:
                slice_length = None

            # Create edges (possibly multiple for repeat)
            for i in range(desc.repeat):
                # Calculate target slice with offset
                if desc.repeat > 1 and slice_length is not None:
                    if target_slice_base is not None:
                        offset = i * slice_length
                        start = target_slice_base.start + offset
                        end = start + slice_length if target_slice_base.end is not None else None
                        target_slice = ResolvedSlice(start=start, end=end)
                    else:
                        # No target slice base - create one starting at offset
                        offset = i * slice_length
                        target_slice = ResolvedSlice(start=offset, end=offset + slice_length)
                else:
                    target_slice = target_slice_base

                self.connect(
                    source_node_id,
                    source_port,
                    target_node_id,
                    target_port,
                    source_slice,
                    target_slice,
                    repeat=1,
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
                f"Cycle(s) detected in graph:\n"
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
