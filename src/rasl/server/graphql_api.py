from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional

import anyio
import time
import strawberry
from strawberry.fastapi import BaseContext
from strawberry.types import Info

from rasl.runtime.monitor import NodeMonitor
from rasl.engine.nodes import get_inputs, get_outputs


@dataclass
class RASLContext(BaseContext):
    state: Any


@strawberry.type
class Edge:
    source: str
    source_port: str
    target: str
    target_port: str


@strawberry.type
class GraphNode:
    id: str
    type: str
    inputs: List[str]
    outputs: List[str]


@strawberry.type
class Graph:
    nodes: List[GraphNode]
    edges: List[Edge]
    topological_order: List[str]


@strawberry.type
class NodeMetrics:
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
    timestamp: float
    nodes: List[NodeMetrics]


@strawberry.type
class Health:
    status: str
    uptime_seconds: float


@strawberry.type
class Node:
    id: str
    type: str
    inputs: List[str]
    outputs: List[str]
    edges: List[Edge]
    metrics: Optional[NodeMetrics]


def _runtime_monitor(runtime: Any) -> Optional[NodeMonitor]:
    monitor = getattr(runtime, "_monitor", None)
    return monitor if isinstance(monitor, NodeMonitor) else None


def _get_node_stats(runtime: Any, node_id: Optional[str] = None) -> Dict[str, Any]:
    getter = getattr(runtime, "get_node_stats", None)
    if callable(getter):
        return getter(node_id) if node_id is not None else getter()

    monitor = _runtime_monitor(runtime)
    if monitor is None:
        return {}

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
class Query:
    @strawberry.field
    def health(self, info: Info[RASLContext, None]) -> Health:
        state = info.context.state
        return Health(status="ok", uptime_seconds=state.uptime_seconds)

    @strawberry.field
    def graph(self, info: Info[RASLContext, None]) -> Graph:
        state = info.context.state
        return _graph_from_plan(state.plan)

    @strawberry.field
    def metrics(self, info: Info[RASLContext, None]) -> MetricsSnapshot:
        state = info.context.state
        stats = _get_node_stats(state.runtime)
        nodes = [_node_metrics_from_dict(v) for _, v in stats.items()]
        return MetricsSnapshot(timestamp=time.time(), nodes=nodes)

    @strawberry.field
    def node(self, info: Info[RASLContext, None], node_id: str) -> Optional[Node]:
        state = info.context.state
        plan = state.plan
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
class Subscription:
    @strawberry.subscription
    async def metrics_stream(
        self, info: Info[RASLContext, None], interval_ms: int = 1000
    ) -> AsyncGenerator[MetricsSnapshot, None]:
        state = info.context.state

        while True:
            stats = _get_node_stats(state.runtime)
            nodes = [_node_metrics_from_dict(v) for _, v in stats.items()]
            yield MetricsSnapshot(timestamp=time.time(), nodes=nodes)
            await anyio.sleep(max(interval_ms, 50) / 1000)


schema = strawberry.Schema(query=Query, subscription=Subscription)
