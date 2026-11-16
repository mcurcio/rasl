"""The graph editor's GraphQL: the config as written, node types, and edits."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from rasl.app.server.graphql_api import RASLContext, schema
from rasl.app.server.state import AppState
from rasl.config import ConfigSession
from rasl.runtime import Runtime

CONFIG = """\
graph {
    node cron minute * * * * *;
    node ConsoleSink sink {
        fps 1;
        connect minute;
    }
}
"""


@pytest.fixture
def config(tmp_path: Path) -> Path:
    path = tmp_path / "rasl.conf"
    path.write_text(CONFIG)
    return path


class Client:
    """Runs GraphQL against the schema with an app state, as the server does."""

    def __init__(self, session: ConfigSession, watched: bool = True) -> None:
        self.state = AppState(runtime=Runtime(session.plan), plan=session.plan, session=session if watched else None)


@pytest.fixture
def client(config: Path) -> Client:
    return Client(ConfigSession(config))


def _gql(client: Client, query: str, **variables) -> dict:
    result = asyncio.run(
        schema.execute(query, variable_values=variables, context_value=RASLContext(state=client.state))
    )
    assert result.errors is None, result.errors
    return result.data


GRAPH = """
{ configGraph { version editable
    nodes { id type place { line } locked outputs { name types default components } inputs { name } }
    edges { target source sourceNode sourcePort targetPort place { line } }
    error { message } } }
"""

APPLY = """
mutation($v: String!, $edits: [EditInput!]!) {
  applyEdits(baseVersion: $v, edits: $edits) {
    ok version saved conflict
    refused { index message }
    changes { diff }
    error { message line connection { problem source { node port } target { node port } } }
  }
}
"""


def test_the_graph_as_written(client: Client) -> None:
    graph = _gql(client, GRAPH)["configGraph"]
    assert graph["editable"] and graph["error"] is None
    assert [(n["id"], n["type"], n["place"]["line"]) for n in graph["nodes"]] == [
        ("minute", "cron", 2),
        ("sink", "ConsoleSink", 3),
    ]
    assert graph["nodes"][0]["outputs"] == [{"name": "out", "types": ["bool"], "default": True, "components": None}]
    assert graph["edges"] == [
        {"target": "sink", "source": "minute", "sourceNode": "minute", "sourcePort": "out",
         "targetPort": "dmx", "place": {"line": 5}}
    ]


def test_node_types_and_a_preview(client: Client) -> None:
    names = [t["name"] for t in _gql(client, "{ nodeTypes { name } }")["nodeTypes"]]
    assert "Waveform" in names and "WaveformNode" not in names
    preview = _gql(
        client,
        '{ previewNode(type: "SacnSource", settings: [{key: "universes", values: "1 2"}]) '
        "{ outputs { name } error } }",
    )["previewNode"]
    assert preview == {"outputs": [{"name": "universe_1"}, {"name": "universe_2"}, {"name": "channels"}], "error": None}


def test_an_applied_batch_is_saved(client: Client, config: Path) -> None:
    version = _gql(client, GRAPH)["configGraph"]["version"]
    outcome = _gql(
        client,
        APPLY,
        v=version,
        edits=[
            {"addNode": {"type": "ConsoleSink", "id": "debug", "settings": [{"key": "fps", "values": "2"}]}},
            {"connect": {"source": "minute", "target": "debug"}},
        ],
    )["applyEdits"]
    assert outcome["ok"] and outcome["saved"] == [str(config)]
    assert "+    node ConsoleSink debug {" in outcome["changes"][0]["diff"]
    assert "connect minute;" in config.read_text().split("debug")[1]
    assert outcome["version"] == _gql(client, GRAPH)["configGraph"]["version"]


def test_a_batch_that_does_not_build_names_the_connection(client: Client, config: Path) -> None:
    version = _gql(client, GRAPH)["configGraph"]["version"]
    outcome = _gql(client, APPLY, v=version, edits=[{"connect": {"source": "minute", "target": "sink"}}])["applyEdits"]
    assert not outcome["ok"] and outcome["saved"] == []
    assert outcome["error"]["line"] == 6
    assert outcome["error"]["connection"] == {
        "problem": "DUPLICATE",
        "source": {"node": "minute", "port": "out"},
        "target": {"node": "sink", "port": "dmx"},
    }
    assert config.read_text() == CONFIG


def test_a_refused_edit_and_a_conflict_are_answers(client: Client, config: Path) -> None:
    version = _gql(client, GRAPH)["configGraph"]["version"]
    refused = _gql(client, APPLY, v=version, edits=[{"removeNode": {"id": "nope"}}])["applyEdits"]
    assert refused["refused"] == {"index": 0, "message": "No node 'nope' in the graph"}
    stale = _gql(client, APPLY, v="old", edits=[{"removeNode": {"id": "sink"}}])["applyEdits"]
    assert stale["conflict"] and not stale["ok"]


def test_without_a_watched_config_nothing_is_editable(config: Path) -> None:
    client = Client(ConfigSession(config), watched=False)
    assert _gql(client, "{ configGraph { version } }")["configGraph"] is None
    outcome = _gql(client, APPLY, v="x", edits=[{"removeNode": {"id": "sink"}}])["applyEdits"]
    assert "--no-watch" in outcome["refused"]["message"]
