"""GraphQL schema for the web server: the running graph, per-node metrics and server health,
and the graph editor's view of the config files and its edits (``editor_api``).

Resolvers read the ``AppState`` carried in the request context. The only writes are the
editor's mutations, which change the config files, never the running graph.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional

import anyio
import strawberry
from strawberry.fastapi import BaseContext
from strawberry.types import Info

from rasl.app.server.editor_api import EditorMutation, EditorQuery, EditorSubscription
from rasl.graph.node import get_inputs, get_outputs
from rasl.runtime.monitor import NodeMonitor


@dataclass
class RASLContext(BaseContext):
    """Per-request context handed to every resolver.

    Attributes:
        state: The server's ``AppState`` (runtime, plan and start time).
    """
    state: Any


@strawberry.type
class Edge:
    """A connection from one node's output port to another node's input port.

    Slices and repeats on the connection are not exposed.

    Attributes:
        source: ID of the node that emits frames.
        source_port: Name of the output port on the source node.
        target: ID of the node that receives frames.
        target_port: Name of the input port on the target node.
    """
    source: str
    source_port: str
    target: str
    target_port: str


@strawberry.type
class GraphNode:
    """A node as listed in the graph: its identity and port names.

    Attributes:
        id: Node ID, unique within the graph.
        type: Name of the Python class that implements the node.
        inputs: Names of the node's input ports.
        outputs: Names of the node's output ports.
    """
    id: str
    type: str
    inputs: List[str]
    outputs: List[str]


@strawberry.type
class Graph:
    """The structure of the plan now running.

    Attributes:
        nodes: Every node, in topological order.
        edges: Every connection between nodes.
        topological_order: Node IDs in execution order: sources first, sinks last.
    """
    nodes: List[GraphNode]
    edges: List[Edge]
    topological_order: List[str]


@strawberry.type
class NodeMetrics:
    """Running pull() counters and timings for one node.

    Times cover the node's own pull() only, not its upstream nodes. They are rounded to
    3 decimal places, ``success_rate`` to 4.

    Attributes:
        node_id: ID of the node measured.
        handle_count: Total pull() calls, successful and failed.
        success_count: pull() calls that returned without raising.
        failure_count: pull() calls that raised.
        consecutive_failures: Length of the current run of failures; 0 after any success.
        total_execution_time_ms: Time spent in pull(), in milliseconds, summed over all calls
            (failed ones included).
        avg_execution_time_ms: ``total_execution_time_ms`` divided by ``handle_count``; 0 before
            the first call.
        success_rate: ``success_count`` divided by ``handle_count``, from 0.0 to 1.0; 1.0 before
            the first call.
        last_error: Message of the most recent exception; null if no call has failed.
        last_error_time: When ``last_error`` was raised, in seconds on the server's monotonic
            clock (not Unix time, so not comparable with ``MetricsSnapshot.timestamp``); null if
            no call has failed.
    """
    node_id: str
    handle_count: int
    success_count: int
    failure_count: int
    consecutive_failures: int
    total_execution_time_ms: float
    avg_execution_time_ms: float
    success_rate: float
    last_error: Optional[str]
    last_error_time: Optional[float]


@strawberry.type
class MetricsSnapshot:
    """The metrics of all measured nodes at one moment.

    Attributes:
        timestamp: Unix time in seconds when the snapshot was taken.
        nodes: One entry per node that has been pulled at least once.
    """
    timestamp: float
    nodes: List[NodeMetrics]


@strawberry.type
class Health:
    """Server health, the same report as ``GET /health`` (``rasl.app.server.health``).

    Attributes:
        status: "ok", "degraded" (a node disabled for repeated failures, a node a config
            reload added or restarted has not started, or the last config reload failed
            and the old graph still runs) or "stalled" (the graph
            has rate drivers but has not ticked for ``stall_after_seconds``).
        uptime_seconds: Seconds since the server was created.
        tick_count: Ticks run since the runtime started.
        last_tick_age_seconds: Seconds since the last tick finished; null if none has.
        stall_after_seconds: How long without a tick counts as a stall for the graph
            now running; null when it has no rate driver.
        disabled_nodes: Ids of the nodes disabled for failing again and again.
        unstarted_nodes: Ids of the nodes a config reload added or restarted whose start
            failed; the runtime retries them.
        last_reload_ok: Whether the last config reload succeeded; null if none yet.
        last_reload_error: Why the last reload failed; null unless it failed.
        last_reload_at: When the last reload attempt ended, in Unix seconds.
    """
    status: str
    uptime_seconds: float
    tick_count: int
    last_tick_age_seconds: Optional[float]
    stall_after_seconds: Optional[float]
    disabled_nodes: List[str]
    unstarted_nodes: List[str]
    last_reload_ok: Optional[bool]
    last_reload_error: Optional[str]
    last_reload_at: Optional[float]


@strawberry.type
class Node:
    """One node in detail: its ports, outgoing edges and metrics.

    Attributes:
        id: Node ID, unique within the graph.
        type: Name of the Python class that implements the node.
        inputs: Names of the node's input ports.
        outputs: Names of the node's output ports.
        edges: The edges that leave this node. Edges that arrive at it are not listed.
        metrics: The node's pull() counters; null until its first pull() is recorded.
    """
    id: str
    type: str
    inputs: List[str]
    outputs: List[str]
    edges: List[Edge]
    metrics: Optional[NodeMetrics]


def _get_node_stats(runtime: Any, node_id: Optional[str] = None) -> Dict[str, Any]:
    monitor: NodeMonitor = runtime.monitor
    if node_id is not None:
        stats = monitor.get_stats(node_id)
        return stats.to_dict() if stats else {}

    return monitor.to_dict()


def _node_metrics_from_dict(d: Dict[str, Any]) -> NodeMetrics:
    return NodeMetrics(
        node_id=str(d.get("node_id", "")),
        handle_count=int(d.get("handle_count", 0)),
        success_count=int(d.get("success_count", 0)),
        failure_count=int(d.get("failure_count", 0)),
        consecutive_failures=int(d.get("consecutive_failures", 0)),
        total_execution_time_ms=float(d.get("total_execution_time_ms", 0.0)),
        avg_execution_time_ms=float(d.get("avg_execution_time_ms", 0.0)),
        success_rate=float(d.get("success_rate", 1.0)),
        last_error=d.get("last_error"),
        last_error_time=d.get("last_error_time"),
    )


def _graph_from_plan(plan: Any) -> Graph:
    desc = plan.describe()

    nodes = [
        GraphNode(
            id=n["id"],
            type=n["type"],
            inputs=list(n.get("inputs", [])),
            outputs=list(n.get("outputs", [])),
        )
        for n in desc.get("nodes", [])
    ]

    edges = [
        Edge(source=s, source_port=sp, target=t, target_port=tp)
        for (s, sp, t, tp) in desc.get("edges", [])
    ]

    return Graph(
        nodes=nodes,
        edges=edges,
        topological_order=list(desc.get("topological_order", [])),
    )


@strawberry.type
class Query(EditorQuery):
    """Root query type: views of the server, the running graph, node metrics, and the
    config files as written (the editor's, from ``EditorQuery``)."""
    @strawberry.field
    def health(self, info: Info[RASLContext, None]) -> Health:
        """Server health: ok, degraded or stalled, and the facts behind it."""
        report = info.context.state.health()
        return Health(
            status=report.status.value,
            uptime_seconds=report.uptime_seconds,
            tick_count=report.tick_count,
            last_tick_age_seconds=report.last_tick_age_seconds,
            stall_after_seconds=report.stall_after_seconds,
            disabled_nodes=list(report.disabled_nodes),
            unstarted_nodes=list(report.unstarted_nodes),
            last_reload_ok=report.last_reload_ok,
            last_reload_error=report.last_reload_error,
            last_reload_at=report.last_reload_at,
        )

    @strawberry.field
    def graph(self, info: Info[RASLContext, None]) -> Graph:
        """The nodes and edges of the plan now running (a config reload replaces it)."""
        state = info.context.state
        return _graph_from_plan(state.current_plan)

    @strawberry.field
    def metrics(self, info: Info[RASLContext, None]) -> MetricsSnapshot:
        """Metrics for every node pulled at least once, stamped with the current Unix time."""
        state = info.context.state
        stats = _get_node_stats(state.runtime)
        nodes = [_node_metrics_from_dict(v) for _, v in stats.items()]
        return MetricsSnapshot(timestamp=time.time(), nodes=nodes)

    @strawberry.field
    def node(self, info: Info[RASLContext, None], node_id: str) -> Optional[Node]:
        """One node of the running plan, with its outgoing edges and metrics.

        Null if the running plan has no node with the ID ``node_id``.
        """
        state = info.context.state
        plan = state.current_plan
        if node_id not in plan.nodes:
            return None

        n = plan.nodes[node_id]

        inputs = get_inputs(n)
        outputs = get_outputs(n)

        edges_out: List[Edge] = []
        if node_id in plan.adjacency:
            for e in plan.adjacency[node_id]:
                edges_out.append(
                    Edge(
                        source=e.source,
                        source_port=e.source_port,
                        target=e.target,
                        target_port=e.target_port,
                    )
                )

        metrics_raw = _get_node_stats(state.runtime, node_id)
        metrics = _node_metrics_from_dict(metrics_raw) if metrics_raw else None

        return Node(
            id=n.id,
            type=type(n).__name__,
            inputs=list(inputs.names),
            outputs=list(outputs.names),
            edges=edges_out,
            metrics=metrics,
        )


@strawberry.type
class Subscription(EditorSubscription):
    """Root subscription type: live node metrics, and changes to the config files."""
    @strawberry.subscription
    async def metrics_stream(
        self, info: Info[RASLContext, None], interval_ms: int = 1000
    ) -> AsyncGenerator[MetricsSnapshot, None]:
        """Emit a metrics snapshot at once, then one every ``interval_ms`` milliseconds.

        An interval under 50 ms is raised to 50 ms. The stream runs until the client
        unsubscribes.
        """
        state = info.context.state

        while True:
            stats = _get_node_stats(state.runtime)
            nodes = [_node_metrics_from_dict(v) for _, v in stats.items()]
            yield MetricsSnapshot(timestamp=time.time(), nodes=nodes)
            await anyio.sleep(max(interval_ms, 50) / 1000)


@strawberry.type
class Mutation(EditorMutation):
    """Root mutation type: the graph editor's edits to the config files."""


schema = strawberry.Schema(query=Query, mutation=Mutation, subscription=Subscription)
