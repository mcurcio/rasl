"""Graph construction and validation for the RASL processing DAG.

This module provides the GraphBuilder for assembling nodes and edges
into an ExecutionPlan that the Runtime can execute. It handles:

- Node registration with duplicate detection
- Edge connection with validation
- Topological sorting with cycle detection
- Compilation into an ExecutionPlan
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Tuple

from .node import Node


@dataclass(frozen=True, slots=True)
class Edge:
    """Immutable connection between two node ports in the graph.

    An Edge represents a directed connection from an output port of
    one node to an input port of another. Frames emitted on the
    source port will be delivered to the target port.

    Attributes:
        source: ID of the node that emits frames.
        source_port: Name of the output port on the source node.
        target: ID of the node that receives frames.
        target_port: Name of the input port on the target node.

    Example:
        >>> edge = Edge(
        ...     source="sacnSource",
        ...     source_port="dmx",
        ...     target="patchTransform",
        ...     target_port="dmx"
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
            nodes_desc.append({
                "id": node.id,
                "type": type(node).__name__,
                "inputs": list(node.inputs),
                "outputs": list(node.outputs),
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


class GraphBuilder:
    """Builder for assembling and validating the processing graph.

    GraphBuilder provides a fluent interface for constructing the DAG:
    add nodes, connect them with edges, then build() to get an
    ExecutionPlan. The builder validates:

    - No duplicate node IDs
    - All edge endpoints reference existing nodes
    - No cycles in the graph (DAG property)

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
        self, source: str, source_port: str, target: str, target_port: str
    ) -> None:
        """Create an edge connecting two node ports.

        Args:
            source: ID of the source node.
            source_port: Output port name on the source node.
            target: ID of the target node.
            target_port: Input port name on the target node.

        Raises:
            KeyError: If source or target node ID is not registered.
        """
        if source not in self._nodes:
            raise KeyError(f"Unknown source node '{source}'")
        if target not in self._nodes:
            raise KeyError(f"Unknown target node '{target}'")
        self._edges.append(Edge(source, source_port, target, target_port))

    def _toposort(self) -> Tuple[str, ...]:
        """Compute topological order of nodes using Kahn's algorithm.

        Returns:
            Tuple of node IDs in valid execution order.

        Raises:
            ValueError: If the graph contains a cycle.
        """
        indegree: Dict[str, int] = {node_id: 0 for node_id in self._nodes}
        adjacency: Dict[str, List[str]] = {node_id: [] for node_id in self._nodes}
        for edge in self._edges:
            indegree[edge.target] += 1
            adjacency[edge.source].append(edge.target)
        queue: List[str] = [node for node, deg in indegree.items() if deg == 0]
        order: List[str] = []
        while queue:
            node = queue.pop(0)
            order.append(node)
            for neighbor in adjacency[node]:
                indegree[neighbor] -= 1
                if indegree[neighbor] == 0:
                    queue.append(neighbor)
        if len(order) != len(self._nodes):
            raise ValueError("Graph contains a cycle")
        return tuple(order)

    def build(self) -> ExecutionPlan:
        """Validate the graph and compile it into an ExecutionPlan.

        Performs cycle detection via topological sort and builds
        the adjacency structure for efficient frame routing.

        Returns:
            ExecutionPlan ready for Runtime execution.

        Raises:
            ValueError: If the graph contains a cycle.
        """
        adjacency: Dict[str, List[Edge]] = {node_id: [] for node_id in self._nodes}
        for edge in self._edges:
            adjacency[edge.source].append(edge)
        order = self._toposort()
        return ExecutionPlan(
            nodes=self._nodes.copy(),
            adjacency=adjacency,
            topological_order=order,
        )
