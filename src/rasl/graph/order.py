"""The order nodes run in, and what to do about cycles.

A graph may hold cycles. ``toposort_with_cycles`` orders the nodes anyway and
reports the cycles; ``find_back_edges`` picks the edges that close them.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Sequence, Set, Tuple

from rasl.graph.edge import Edge


def find_cycles(nodes: Iterable[str], edges: Sequence[Edge]) -> List[List[str]]:
    """Find all cycles in the graph using Tarjan's SCC algorithm.

    Returns:
        List of cycles, where each cycle is a list of node IDs.
        Only SCCs with more than one node or self-loops are returned.
    """
    adjacency: Dict[str, List[str]] = {node_id: [] for node_id in nodes}
    for edge in edges:
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

    for node in adjacency:
        if node not in index:
            strongconnect(node)

    return sccs


def toposort_with_cycles(
    nodes: Sequence[str], edges: Sequence[Edge]
) -> Tuple[Tuple[str, ...], List[List[str]]]:
    """Compute execution order, handling cycles gracefully.

    Uses Kahn's algorithm but handles cycles by breaking them
    arbitrarily when no zero-indegree nodes remain.

    Returns:
        Tuple of (execution_order, cycles) where cycles is a list
        of detected cycles (each cycle is a list of node IDs).
    """
    cycles = find_cycles(nodes, edges)

    indegree: Dict[str, int] = {node_id: 0 for node_id in nodes}
    adjacency: Dict[str, List[str]] = {node_id: [] for node_id in nodes}
    for edge in edges:
        indegree[edge.target] += 1
        adjacency[edge.source].append(edge.target)

    queue: List[str] = [node for node, deg in indegree.items() if deg == 0]
    order: List[str] = []
    remaining: Set[str] = set(nodes)

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


def find_back_edges(adjacency: Dict[str, List[Edge]]) -> Set[Tuple[str, str, str, str]]:
    """The edges that close a cycle, found by depth-first search in node order.

    A node reads a back-edge's frame from the previous tick, which is what
    lets a cyclic graph run. The plan carries the result
    (``ExecutionPlan.back_edges``) so compiling and running agree on which
    edges these are.

    Returns:
        (source, source_port, target, target_port) of each back-edge.
    """
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
