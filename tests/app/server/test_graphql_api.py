"""The read-only GraphQL API: health, graph, node, metrics and the metrics stream, against a
runtime that has run."""

from __future__ import annotations

import time

import anyio
import pytest

from rasl.app.server.graphql_api import RASLContext, schema
from rasl.app.server.state import AppState
from rasl.config.build import parse_config
from rasl.runtime import Runtime

CONFIG = """
graph {
    node Waveform wave { output_channels 3; }
    node ConsoleSink sink { fps 50; connect wave; }
}
"""


@pytest.fixture(scope="module")
async def state() -> AppState:
    """The app state of a runtime that ran CONFIG for 0.15 s."""
    plan = parse_config(CONFIG)
    runtime = Runtime(plan)
    with anyio.move_on_after(0.15):
        await runtime.run()
    return AppState(runtime=runtime, plan=plan, session=None)


async def _gql(state: AppState, query: str) -> dict:
    result = await schema.execute(query, context_value=RASLContext(state=state))
    assert result.errors is None, result.errors
    return result.data


async def test_health_reports_the_ticks_run(state: AppState) -> None:
    health = (await _gql(state, "{ health { status tickCount uptimeSeconds disabledNodes } }"))["health"]
    assert health["status"] in {"ok", "stalled"}  # the runtime has stopped by now
    assert health["tickCount"] > 0
    assert health["disabledNodes"] == []


async def test_graph_lists_the_nodes_and_edges_of_the_plan(state: AppState) -> None:
    graph = (
        await _gql(
            state,
            "{ graph { topologicalOrder nodes { id type inputs outputs } "
            "edges { source sourcePort target targetPort } } }",
        )
    )["graph"]
    assert graph["topologicalOrder"] == ["wave", "sink"]
    assert {n["id"]: n["type"] for n in graph["nodes"]} == {"wave": "WaveformNode", "sink": "ConsoleSinkNode"}
    assert graph["edges"] == [{"source": "wave", "sourcePort": "out", "target": "sink", "targetPort": "dmx"}]


async def test_node_gives_one_node_with_its_edges_and_metrics(state: AppState) -> None:
    node = (
        await _gql(
            state,
            '{ node(nodeId: "wave") { id type edges { target } metrics { handleCount failureCount successRate } } }',
        )
    )["node"]
    assert (node["id"], node["type"]) == ("wave", "WaveformNode")
    assert node["edges"] == [{"target": "sink"}]
    assert node["metrics"]["handleCount"] > 0
    assert node["metrics"]["failureCount"] == 0
    assert node["metrics"]["successRate"] == 1.0


async def test_node_is_null_for_an_id_the_plan_does_not_have(state: AppState) -> None:
    assert (await _gql(state, '{ node(nodeId: "nobody") { id } }'))["node"] is None


async def test_metrics_cover_every_pulled_node_at_the_current_unix_time(state: AppState) -> None:
    metrics = (await _gql(state, "{ metrics { timestamp nodes { nodeId handleCount } } }"))["metrics"]
    assert abs(metrics["timestamp"] - time.time()) < 5
    assert {n["nodeId"] for n in metrics["nodes"]} == {"wave", "sink"}


async def test_the_metrics_stream_emits_a_snapshot_at_once(state: AppState) -> None:
    stream = await schema.subscribe(
        "subscription { metricsStream(intervalMs: 50) { nodes { nodeId } } }",
        context_value=RASLContext(state=state),
    )
    with anyio.fail_after(2):
        first = await stream.__anext__()
        second = await stream.__anext__()
    await stream.aclose()
    for result in (first, second):
        assert result.errors is None
        assert {n["nodeId"] for n in result.data["metricsStream"]["nodes"]} == {"wave", "sink"}
