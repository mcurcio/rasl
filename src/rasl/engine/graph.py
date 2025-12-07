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
from typing import Any, Dict, List, Optional, Set, Tuple, Type

from rasl.config.connect_parser import ResolvedSlice

from .frame import FramePayload
from .node import Node, get_inputs, get_outputs
from .ports import PortSpec


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

        # Type compatibility check
        src_type = self._get_primary_type(src_spec)
        if src_type is not None and not tgt_spec.accepts_payload_type(src_type):
            raise TypeError(
                f"Type mismatch: {source}.{source_port} emits {src_type.__name__}, "
                f"but {target}.{target_port} does not accept it"
            )

        # Validate slice compatibility if both are specified with fixed lengths
        if source_slice is not None and target_slice is not None:
            src_len = source_slice.length(src_spec.channels)
            tgt_len = target_slice.length(tgt_spec.channels)
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

    def _get_primary_type(self, spec: PortSpec) -> Type[FramePayload] | None:
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

        return ExecutionPlan(
            nodes=self._nodes.copy(),
            adjacency=adjacency,
            topological_order=order,
        )
