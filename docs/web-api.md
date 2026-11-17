# Web API

This page describes the HTTP server that `rasl` can run beside a graph: how to turn it on, the dashboard at
`GET /`, the health check at `GET /health`, and the read-only GraphQL API at `/graphql`, with every query,
subscription and type it has. The requests and responses below are real, run against `virtual.conf` from the
repository root unless an example says otherwise. The [README](../README.md#web-ui-and-api) has a short summary of the same server.

## Turning the server on

The server is off unless the command line or the config asks for it.

| How | Binds |
|---|---|
| `--api-port PORT` | `--api-host` (default `127.0.0.1`) on `PORT`. |
| A top-level `ui { }` block in the config, and no `--api-port` | The block's `host` (default `127.0.0.1`) on its `port` (default `8080`). |
| Neither | No server. |

```nginx
ui {
    host "127.0.0.1";
    port 8080;
}

graph {
    # ...
}
```

How they interact:

- `--api-port` wins over the whole `ui` block: the block's `host` is then ignored too, and the server binds
  `--api-host`. With `ui { host "0.0.0.0"; port 18202; }` added to a copy of `virtual.conf` named `ui.conf`,
  `rasl ui.conf --api-port 18203` prints `Dashboard: http://127.0.0.1:18203/` and binds that address.
- `--api-host` alone does nothing. It takes effect only with `--api-port`.
- An empty `ui { }` block turns the server on at `127.0.0.1:8080`.
- The `ui` block is read once, at startup. Changing it while rasl runs has no effect until rasl restarts
  ([README: Live reload](../README.md#live-reload)).

When the server starts, rasl prints its address:

```bash
uv run rasl virtual.conf --api-port 18200
# Dashboard: http://127.0.0.1:18200/
```

The container image passes `--api-host 0.0.0.0 --api-port $RASL_PORT`
([README: Container](../README.md#container)).

## Security

The server has no authentication and no access control. Anyone who can reach the port can read the graph (node
names, types and ports), the metrics, and the last config error, which quotes lines of the config file. When the
config is watched, they can also **change the config files** through the graph editor's mutations
([Graph editor](#graph-editor)); the deployment puts the server behind the cluster's Keycloak sign-in for that
(`rasl-6sr.8`). It binds `127.0.0.1` by default. Bind another address only on a trusted network, or put the server behind
a proxy that checks who is signing in. [SECURITY.md](../SECURITY.md) says more.

## Routes

| Route | What it serves |
|---|---|
| `GET /` | The web UI: the graph editor. |
| `GET /health` | The health report as JSON. |
| `/graphql` | GraphQL: `POST` or `GET` for queries, WebSocket for the subscription, and the GraphiQL editor in a browser. |

## The dashboard: `GET /`

`GET /` serves the graph editor, a single-page app built from `js/packages/web` (`@rasl/web`, TypeScript, React
and React Flow) into `src/rasl/app/ui/`. Those built files are not committed: `pnpm build` in `js/` writes them,
and the container image builds them. The page uses only the GraphQL API below and loads nothing from the
internet.

It draws the graph as the config files write it ([Graph editor](#graph-editor)), laid out automatically, with
each node's ports, a health dot from `metricsStream`, and for the selection where it is written, its settings and
metrics. Editing:

- **Connect**: drag from an output port to an input port. While the wire is dragged, the ports that take it
  (as it is, or retyped to a more specific type) light up and the rest dim; a drop on a port that cannot take it
  is refused (`payloadTypes`).
- **Add a node**: double-click the canvas, press ⌘K, or drop a wire on empty canvas (the new node is then fed by
  it). Pick a type, give it an id and settings; its ports are shown before it is added (`previewNode`).
- **Remove or rename**: select a node or a connection and press Delete, or use the inspector. Removing a node
  removes its connections.
- Changes **queue** (owner, 2026-11-16: saved on purpose): queued nodes and connections are drawn dashed,
  removed ones struck through. The queue is checked as it changes (`previewEdits`): the diff to each file, and
  the error, with the ports of a refused connection marked. **Save** (`applyEdits`) writes the files; the
  running graph follows by its reload. ⌘Z drops the last queued change.
- **Settings**: the inspector edits a node's lines (and the values after its id), adds one (suggesting the keys
  of the type's schema), or removes one. A line that reads one `$variable` offers where to write the new value:
  at the `@set` line (every use changes; the count is shown) or only on this line, which writes the value in place
  of `$name`. A node made by `@use` shows the snippet; its parameters are set as the `@use` line's arguments, and
  **Detach** writes the snippet's nodes out in place of the `@use` line so each line can be edited (rasl-6sr.7).
- When the files change on disk while changes are queued, the page says so and checks them again.

For development, `pnpm --filter @rasl/web dev`
in `js/` serves the page with hot reload and forwards `/graphql` to a running rasl (`RASL_API`, default
`http://127.0.0.1:8080`).

## Health: `GET /health`

```bash
curl -sS -i http://127.0.0.1:18200/health
```

```text
HTTP/1.1 200 OK
date: Sun, 15 Nov 2026 21:45:07 GMT
server: uvicorn
content-length: 225
content-type: application/json

{"status":"ok","uptime_seconds":3.6419973373413086,"tick_count":4,"last_tick_age_seconds":0.6377826190000633,"stall_after_seconds":10.0,"disabled_nodes":[],"last_reload_ok":null,"last_reload_error":null,"last_reload_at":null}
```

| Field | Type | Meaning |
|---|---|---|
| `status` | string | `ok`, `degraded` or `stalled` (below). |
| `uptime_seconds` | number | Seconds since the server was created. |
| `tick_count` | integer | Ticks run since the runtime started. |
| `last_tick_age_seconds` | number or null | Seconds since the last tick finished; null before the first tick. |
| `stall_after_seconds` | number or null | How long without a tick counts as a stall for the graph now running; null when the graph has no rate-driving sink, since it cannot stall. |
| `disabled_nodes` | array of strings | Ids of nodes disabled after `max_consecutive_errors` failed pulls in a row (10 by default; see the README's `runtime` block), sorted. A config reload that changes a node re-enables it. |
| `last_reload_ok` | boolean or null | Whether the last config reload succeeded; null if none has been tried, or the config is not watched (`--no-watch`). |
| `last_reload_error` | string or null | Why the last reload failed, with file, line, column and the source line; null unless it failed. |
| `last_reload_at` | number or null | When the last reload attempt ended, in Unix seconds; null if none has been tried. |

### Status rules

The rules are in `src/rasl/app/server/health.py`. The worst one that applies wins.

| Status | When | HTTP |
|---|---|---|
| `stalled` | The graph has at least one rate-driving sink, the scheduler has begun running, and no tick has finished for more than `stall_after_seconds`. The time is counted from the later of the last tick and the moment the scheduler last began running (it begins again after each reload). | 503 |
| `degraded` | Not stalled, but a node has been disabled for repeated failures, or the last config reload failed and the previous graph is still running. | 200 |
| `ok` | Neither. | 200 |

`stall_after_seconds` is `max(5, 10 / slowest rate)`: ten periods of the slowest rate-driving sink, and never
less than 5 seconds. `virtual.conf`'s only sink runs at 1 Hz, so its threshold is 10 seconds. A graph with no
rate-driving sink is never stalled, nor is one whose nodes are still starting.

The 503 lets a container health check mark a wedged scheduler unhealthy; the image's `HEALTHCHECK` uses this
route. `degraded` answers 200 because the server works and the problem is in the config or a device.

A failed reload. rasl was running a copy of `virtual.conf` named `live.conf`, and `twinkle`'s
`connect okhsl_color;` was then changed to `connect missing_node;`:

```text
HTTP/1.1 200 OK
date: Sun, 15 Nov 2026 21:49:02 GMT
server: uvicorn
content-length: 368
content-type: application/json

{"status":"degraded","uptime_seconds":6.7178826332092285,"tick_count":7,"last_tick_age_seconds":0.7128174150002451,"stall_after_seconds":10.0,"disabled_nodes":[],"last_reload_ok":false,"last_reload_error":"live.conf:43:5: rasl/connect: Node 'twinkle': Unknown source node 'missing_node'\n    node TwinkleEffect twinkle {\n    ^^^^","last_reload_at":1794779340.9721258}
```

The status returns to `ok` at the next reload that succeeds.

## GraphQL: `/graphql`

The API reads the running graph, its metrics and health, and, for the graph editor, the config files as written.
Its only writes are the editor's mutations, which change the config files ([Graph editor](#graph-editor)). Field
names are camelCase.

- **Queries** go as `POST` with a JSON body `{"query": "...", "variables": {...}}`, or as `GET` with the query
  in the `query` parameter.
- **GraphiQL**: open `/graphql` in a browser for an editor with the schema and its documentation.
- **Errors** come back with HTTP 200 and an `errors` array.

### Schema

```graphql
type Query {
  health: Health!
  graph: Graph!
  metrics: MetricsSnapshot!
  node(nodeId: String!): Node
  configGraph: ConfigGraph
  nodeTypes: [NodeType!]!
  previewNode(type: String!, values: String! = "", settings: [SettingInput!] = null): ConfigNode!
  payloadTypes: [PayloadType!]!
}

type Mutation {
  previewEdits(baseVersion: String!, edits: [EditInput!]!): EditOutcome!
  applyEdits(baseVersion: String!, edits: [EditInput!]!): EditOutcome!
}

type Subscription {
  metricsStream(intervalMs: Int! = 1000): MetricsSnapshot!
  configChanged(intervalMs: Int! = 1000): ConfigChange!
}
```

### Queries

| Query | Returns |
|---|---|
| `health` | The same report as `GET /health`. |
| `graph` | The nodes and edges of the plan now running. After a reload it shows the new plan. |
| `metrics` | Pull counters for every node that has been pulled at least once, stamped with the current Unix time. |
| `node(nodeId)` | One node of the running plan with its outgoing edges and metrics; null if there is no node with that id. |

### Subscription

`metricsStream(intervalMs)` sends a `MetricsSnapshot` at once, then one every `intervalMs` milliseconds (default
1000; anything under 50 counts as 50), until the client stops it.

### Types

`Health` has the fields of `GET /health` in camelCase: `status: String!`, `uptimeSeconds: Float!`,
`tickCount: Int!`, `lastTickAgeSeconds: Float`, `stallAfterSeconds: Float`, `disabledNodes: [String!]!`,
`lastReloadOk: Boolean`, `lastReloadError: String`, `lastReloadAt: Float`. They mean what the
[table above](#health-get-health) says.

`Graph`: the structure of the plan now running.

| Field | Type | Meaning |
|---|---|---|
| `nodes` | `[GraphNode!]!` | Every node, in topological order. |
| `edges` | `[Edge!]!` | Every connection between nodes. |
| `topologicalOrder` | `[String!]!` | Node ids in execution order, sources first. |

`GraphNode`: a node as listed in the graph.

| Field | Type | Meaning |
|---|---|---|
| `id` | `String!` | The node's name in the config. |
| `type` | `String!` | The Python class that implements it, such as `WaveformNode`, not the type name the config used. |
| `inputs` | `[String!]!` | Its input port names. |
| `outputs` | `[String!]!` | Its output port names. |

`Edge`: one connection from an output port to an input port; each `connect` line is one edge. Slices and
repeats on the connection are not shown.

| Field | Type | Meaning |
|---|---|---|
| `source` | `String!` | Id of the node that writes. |
| `sourcePort` | `String!` | Its output port. |
| `target` | `String!` | Id of the node that reads. |
| `targetPort` | `String!` | Its input port. |

`Node`: one node in detail.

| Field | Type | Meaning |
|---|---|---|
| `id`, `type`, `inputs`, `outputs` | | As in `GraphNode`. |
| `edges` | `[Edge!]!` | The edges that leave this node. Edges that arrive at it are not listed; find them in `graph`. |
| `metrics` | `NodeMetrics` | Its counters; null until its first pull is recorded. A node that nothing pulls stays null. |

`MetricsSnapshot`:

| Field | Type | Meaning |
|---|---|---|
| `timestamp` | `Float!` | Unix time in seconds when the snapshot was taken. |
| `nodes` | `[NodeMetrics!]!` | One entry per node pulled at least once. |

`NodeMetrics`: counters for one node's `pull()`. Times cover the node's own `pull()`, not the nodes upstream of
it. On a config reload, a node the reload removes leaves `metrics`, a node it restarts counts from zero again,
and a node it updates in place (its settings changed without a restart) keeps its counts; only its run of
consecutive failures starts over.

| Field | Type | Meaning |
|---|---|---|
| `nodeId` | `String!` | The node measured. |
| `handleCount` | `Int!` | Pulls, successful and failed. |
| `successCount` | `Int!` | Pulls that returned normally. |
| `failureCount` | `Int!` | Pulls that raised. |
| `consecutiveFailures` | `Int!` | Length of the current run of failures; 0 after a success. |
| `totalExecutionTimeMs` | `Float!` | Milliseconds spent in `pull()`, summed over all pulls, rounded to 3 places. |
| `avgExecutionTimeMs` | `Float!` | `totalExecutionTimeMs / handleCount`, rounded to 3 places; 0 before the first pull. |
| `successRate` | `Float!` | `successCount / handleCount`, from 0 to 1, rounded to 4 places; 1 before the first pull. |
| `lastError` | `String` | Message of the most recent exception; null if no pull has failed. |
| `lastErrorTime` | `Float` | When `lastError` was raised, in seconds on the server's monotonic clock. It is not Unix time, so it cannot be compared with `timestamp`. Null if no pull has failed. |

### Examples

The server for these was started with `uv run rasl virtual.conf --api-port 18200`. In that config the
`twinkle` and `static_hsl` nodes feed no sink, so they are never pulled and have no metrics.

`health`:

```bash
curl -sS -H 'content-type: application/json' \
    -d '{"query":"{ health { status tickCount lastTickAgeSeconds stallAfterSeconds disabledNodes lastReloadOk } }"}' \
    http://127.0.0.1:18200/graphql
```

```json
{"data": {"health": {"status": "ok", "tickCount": 9, "lastTickAgeSeconds": 0.25697738999997455, "stallAfterSeconds": 10.0, "disabledNodes": [], "lastReloadOk": null}}}
```

The same query as a `GET`:

```bash
curl -sS 'http://127.0.0.1:18200/graphql?query=%7Bhealth%7Bstatus%7D%7D'
```

```json
{"data": {"health": {"status": "ok"}}}
```

`graph` (shortened where marked):

```bash
curl -sS -H 'content-type: application/json' \
    -d '{"query":"{ graph { topologicalOrder nodes { id type inputs outputs } edges { source sourcePort target targetPort } } }"}' \
    http://127.0.0.1:18200/graphql | python3 -m json.tool
```

```json
{
    "data": {
        "graph": {
            "topologicalOrder": [
                "hue_ramp",
                "static_hsl",
                "okhsl_color",
                "twinkle",
                "toRgb",
                "console"
            ],
            "nodes": [
                {
                    "id": "hue_ramp",
                    "type": "WaveformNode",
                    "inputs": [
                        "phase",
                        "speed"
                    ],
                    "outputs": [
                        "out"
                    ]
                },
                …
                {
                    "id": "console",
                    "type": "ConsoleSinkNode",
                    "inputs": [
                        "dmx"
                    ],
                    "outputs": []
                }
            ],
            "edges": [
                {
                    "source": "hue_ramp",
                    "sourcePort": "out",
                    "target": "okhsl_color",
                    "targetPort": "hue"
                },
                …
                {
                    "source": "toRgb",
                    "sourcePort": "color",
                    "target": "console",
                    "targetPort": "dmx"
                }
            ]
        }
    }
}
```

`node`, with a variable:

```bash
curl -sS -H 'content-type: application/json' \
    -d '{"query":"query($id: String!) { node(nodeId: $id) { id type inputs outputs edges { target targetPort } metrics { handleCount successCount failureCount avgExecutionTimeMs successRate lastError } } }","variables":{"id":"toRgb"}}' \
    http://127.0.0.1:18200/graphql | python3 -m json.tool
```

```json
{
    "data": {
        "node": {
            "id": "toRgb",
            "type": "ColorNode",
            "inputs": [
                "color"
            ],
            "outputs": [
                "color"
            ],
            "edges": [
                {
                    "target": "console",
                    "targetPort": "dmx"
                }
            ],
            "metrics": {
                "handleCount": 9,
                "successCount": 9,
                "failureCount": 0,
                "avgExecutionTimeMs": 0.679,
                "successRate": 1.0,
                "lastError": null
            }
        }
    }
}
```

An id that is not in the graph gives null:

```bash
curl -sS -H 'content-type: application/json' -d '{"query":"{ node(nodeId: \"nope\") { id } }"}' \
    http://127.0.0.1:18200/graphql
```

```json
{"data": {"node": null}}
```

`metrics`:

```bash
curl -sS -H 'content-type: application/json' \
    -d '{"query":"{ metrics { timestamp nodes { nodeId handleCount avgExecutionTimeMs } } }"}' \
    http://127.0.0.1:18200/graphql | python3 -m json.tool
```

```json
{
    "data": {
        "metrics": {
            "timestamp": 1794779112.987128,
            "nodes": [
                {
                    "nodeId": "hue_ramp",
                    "handleCount": 9,
                    "avgExecutionTimeMs": 0.118
                },
                {
                    "nodeId": "okhsl_color",
                    "handleCount": 9,
                    "avgExecutionTimeMs": 0.06
                },
                {
                    "nodeId": "toRgb",
                    "handleCount": 9,
                    "avgExecutionTimeMs": 0.679
                },
                {
                    "nodeId": "console",
                    "handleCount": 9,
                    "avgExecutionTimeMs": 0.327
                }
            ]
        }
    }
}
```

An error: a field that does not exist. The HTTP status is 200.

```bash
curl -sS -H 'content-type: application/json' -d '{"query":"{ health { nope } }"}' \
    http://127.0.0.1:18200/graphql
```

```json
{"data": null, "errors": [{"message": "Cannot query field 'nope' on type 'Health'.", "locations": [{"line": 1, "column": 12}]}]}
```

## Graph editor

The editor changes the config files, never the running graph (`src/rasl/config/edit.py`, `view.py`;
`src/rasl/app/server/editor_api.py`). A saved edit reaches the running graph by the watcher's reload, as an edit in
a text editor does. Without a watched config (`--no-watch`), `configGraph` is null and every edit is refused.

| Field | What it does |
|---|---|
| `configGraph` | The graph as the files write it: each node (type, file and line, settings, ports, `locked` reason) and each `connect` line (source and port as written, resolved ports, `repeat`, file and line, `locked`), the files' `version`, and `error` when the config does not build. A node is built on its own to show its ports, so one broken node does not hide the others. |
| `payloadTypes` | Every payload type, its fixed width, and the types a port of it takes, as they are or retyped: what the editor's connection hints use. |
| `nodeTypes` | Every node type, by the name a `node` line uses, with its aliases, a one-line summary and the JSON Schema of its settings. |
| `previewNode(type, values, settings)` | A node not in the config yet, built (never started) to show its ports, which can depend on its settings. |
| `previewEdits(baseVersion, edits)` | What a batch would change (a unified diff per file) and whether the result builds. Writes nothing. |
| `applyEdits(baseVersion, edits)` | The same, then saves the files when the result builds. |
| `configChanged(intervalMs)` | The files' version, then each new version or reload outcome. |

An edit is one of `addNode {type, id, values, settings}`, `removeNode {id}` (its `connect` lines go with it),
`renameNode {id, newId}` (every `connect` line that reads it follows), `connect {source, target, port, repeat,
repeatUntil}`, `disconnect {source, target, port}`, `setSetting {node, key, values, index, scope}`,
`removeSetting {node, key, index}`, `setNodeValues {node, values}` and `detach {id}`; sources and ports are written
in config notation (`hue.out[0~3]`). A setting line is known by its key and, for a key written more than once
(`fill`), its `index` among them; `setSetting` with `index` one past the last adds a line before the node's
`connect` lines. Its `scope` is `line` (write the values on the line, replacing any `$variable` it reads) or
`definition` (write them where its one value comes from: the `@set` line, or the `@use` argument of a snippet
parameter). `detach` replaces a `@use` line with the nodes it makes, written out. A new node goes after the last node the batch connects it from, else before the first node it
feeds, else at the end of the `graph` block. Comments and layout are kept.

An `EditOutcome` is exactly one of: `ok` (`saved` lists the files written; empty for a preview), `error` (the
edited config does not build: placed in the edited text, with `connection` naming both ports for a refused
connection), `refused` (an edit cannot be made: an unknown node, a taken id, a line in a `@snippet` or in a file
read twice), or `conflict` (the files changed since `baseVersion`: read `configGraph` again).

## Subscriptions over WebSocket

The subscription runs over a WebSocket at `ws://<host>:<port>/graphql` using the
[graphql-transport-ws](https://github.com/enisdenjo/graphql-ws/blob/master/PROTOCOL.md) protocol. The client must
ask for the `graphql-transport-ws` subprotocol; it is the only one the server accepts. Client libraries such as
`graphql-ws` (the one the dashboard uses) speak it.

The exchange, as JSON text messages:

1. The client sends `connection_init`; the server answers `connection_ack`.
2. The client sends `subscribe` with an `id` of its choice and the query in `payload`.
3. The server sends `next` messages with that `id`, one per snapshot.
4. The client sends `complete` with the same `id` to stop the stream. The connection stays open for other
   subscriptions.
5. Either side may send `ping`; the other answers `pong`.

A session recorded with this script, which uses the `websockets` package that rasl depends on:

```python
import asyncio
import json

import websockets


async def main():
    async with websockets.connect(
        "ws://127.0.0.1:18200/graphql", subprotocols=["graphql-transport-ws"]
    ) as ws:

        async def send(message):
            print(">", json.dumps(message))
            await ws.send(json.dumps(message))

        async def receive():
            print("<", await ws.recv())

        query = "subscription { metricsStream(intervalMs: 500) { timestamp nodes { nodeId handleCount } } }"
        await send({"type": "connection_init"})
        await receive()
        await send({"id": "1", "type": "subscribe", "payload": {"query": query}})
        await receive()
        await receive()
        await send({"id": "1", "type": "complete"})
        await send({"type": "ping"})
        await receive()


asyncio.run(main())
```

Its output (`>` sent, `<` received):

```text
> {"type": "connection_init"}
< {"type": "connection_ack"}
> {"id": "1", "type": "subscribe", "payload": {"query": "subscription { metricsStream(intervalMs: 500) { timestamp nodes { nodeId handleCount } } }"}}
< {"id": "1", "type": "next", "payload": {"data": {"metricsStream": {"timestamp": 1794779434.8922513, "nodes": [{"nodeId": "hue_ramp", "handleCount": 4}, {"nodeId": "okhsl_color", "handleCount": 4}, {"nodeId": "toRgb", "handleCount": 4}, {"nodeId": "console", "handleCount": 4}]}}}}
< {"id": "1", "type": "next", "payload": {"data": {"metricsStream": {"timestamp": 1794779435.3938813, "nodes": [{"nodeId": "hue_ramp", "handleCount": 5}, {"nodeId": "okhsl_color", "handleCount": 5}, {"nodeId": "toRgb", "handleCount": 5}, {"nodeId": "console", "handleCount": 5}]}}}}
> {"id": "1", "type": "complete"}
> {"type": "ping"}
< {"type": "pong"}
```
