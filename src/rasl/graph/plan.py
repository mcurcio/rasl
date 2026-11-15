"""The compiled graph a runtime executes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from rasl.graph.edge import Edge
from rasl.graph.node.protocol import Node, get_inputs, get_outputs
from rasl.graph.routing import InputPortProgram


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
