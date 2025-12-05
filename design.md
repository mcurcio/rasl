# RASL Data Engine Design

## Goals & Constraints

1. **Parity with existing reflector**: Reproduce the TypeScript behavior (listen for sACN universes, redistribute segments) using a Python engine without rewriting the JS.
2. **Graph-based processing**: Model the system as a Directed Acyclic Graph (DAG) where `SourceNode`s emit frames, `TransformNode`s mutate/route them, and `SinkNode`s emit to external systems.
3. **Composable & extensible**: New protocols or transforms should only require implementing node interfaces, not touching the runtime core.
4. **Deterministic, low-latency paths**: Prioritize predictable scheduling and bounded buffering for real-time lighting data.
5. **uv-native packaging**: Manage the Python project via [`uv`](https://github.com/astral-sh/uv) for dependency isolation and reproducible builds.
6. **Protocol isolation**: The core engine stays protocol-agnostic; only Source/Sink nodes contain transport specifics, ensuring transforms remain pure data operations.

## Project Layout (proposed)

```text
rasl/
  design.md        # this document
  pyproject.toml   # managed by `uv`
  src/rasl/
    __init__.py
    engine/        # core DAG types & scheduler
    nodes/         # concrete node implementations
    io/            # protocol adapters (e131, etc.)
    config/        # schema + loader
    telemetry/     # logging, metrics hooks
    examples/
      sacn_reflector.py
```

`uv` will create/lock dependencies; likely runtime deps include `anyio` (async), `pydantic` (config), and protocol libs (e.g., `sacn`).

## Data Model

- **Frame**: Immutable payload traveling through the DAG.

  ```python
  @dataclass(frozen=True)
  class Frame:
      topic: str              # e.g., "sacn.universe.1"
      timestamp: float        # monotonic time
      payload: NDArray[np.float32]  # normalized channel data 0.0-1.0
      metadata: Mapping[str, Any]
  ```

- Source adapters (e.g., `SacnSourceNode`) convert raw bytes (0-255) into float buffers; sink adapters reverse the mapping.
- Higher-order views (RGB, HSL) are implemented as metadata or transform utilities—frames remain float arrays internally. Sources may attach metadata such as `{"colorSpace": "rgb", "channelsPerPixel": 3}` so downstream transforms/sinks know how to interpret channel groupings.
- Frames must be serializable for telemetry/debug capture.

## Naming Conventions

- **Types & node identifiers**: PascalCase (e.g., `SacnSourceNode`, `UniversePatchTransform`).
- **Properties, config keys, and runtime variables**: camelCase (e.g., `targetHost`, `minIntervalMs`, `nodeId`).
- **Edge descriptors**: camelCase property names (`fromPort`, `toPort`) referencing `nodeId:portName` strings.

## Node Taxonomy & Interfaces

```python
class Node(Protocol):
    id: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    async def start(ctx: NodeContext) -> None: ...
    async def handle(frame: Frame, ctx: NodeContext) -> None: ...
    async def stop(ctx: NodeContext) -> None: ...
```

- **SourceNode**: `inputs=()`; owns external listeners (sockets, files). Emits frames via `ctx.emit(output_name, frame)`.
- **TransformNode**: Receives frames on named inputs, may emit zero or more frames downstream.
- **SinkNode**: Terminal node; `outputs=()`; writes frames to external targets.
- Nodes may register timers (`ctx.call_later`) for rate limiting (e.g., min packet interval).

## Graph Definition & Validation

- `GraphBuilder` collects nodes, declares edges (`builder.connect("src:dmx", "producer:input")`).
- Validation rules:
  1. All edges reference declared node ports.
  2. DAG acyclicity (Kahn/DFS check) before runtime start.
  3. Strong typing hints via `topic` conventions (optional schema enforcement).
- Compiled graph becomes `ExecutionPlan` with:
  - Topological order
  - Per-node async mailbox/buffer size (defaults; overridable per edge)
  - Backpressure strategy (drop, latest, block)

## Runtime Execution Model

- Built on `anyio.TaskGroup` (supports asyncio/trio).
- Each node runs in its own task with mailbox channel (`anyio.create_memory_object_stream`).
- Scheduler responsibilities:
  1. Spawn `start()` for each node in topological order.
  2. Route frames by writing to downstream mailboxes.
  3. Enforce per-edge policies (rate limit, coalescing, filtering).
  4. Monitor health & restart policies.
- Global services: telemetry bus, lifecycle manager, graceful shutdown on signals.

## Configuration System

- **Single source of truth**: Crossplane/nginx syntax is the canonical configuration language. The parser (via `python-crossplane`) produces an AST that the loader converts into DAG nodes/edges.
- **Intuitive structure**: `rasl { ... }` encloses the graph. Each `node NAME { ... }` block declares its type, attributes, and optional defaults. `edge { from nodeA:port; to nodeB:port; }` establishes wiring.
- **Sensible defaults**: When not specified, nodes inherit defaults aligned with the current JSON config—e.g., `SacnSinkNode` defaults to `minIntervalMs=25`, `targetChannel=1`, `frequencyHz=1`. Transform segments can omit offsets/lengths if they consume full universes or reuse previously declared defaults scoped within the node.
- **Inline definitions**: No external files are required; patch/segment definitions live within node blocks. Reusable snippets can be expressed via include blocks or Crossplane macros later if needed.

### Example: Crossplane Config (current JSON translated)

```nginx
rasl {
    node sacnSource {
        type SacnSourceNode;
        universes 2;
        output dmx;
        metadata "colorSpace=rgb";
    }

    node universePatch0 {
        type UniversePatchTransform;
        input dmx;
        output universe0;
        defaults {
            source_universe 2;
            source_channel 1;
            length 150;
        }
        segment { target_channel 1; }
        segment { target_channel 151; }
        segment { target_channel 300; }
        segment { length 62; target_channel 451; }
    }

    node sacnSink0 {
        type SacnSinkNode;
        input universe0;
        target_host "10.0.60.30";
        target_universe 0;
        min_interval_ms 1000;
    }

    node universePatch1 {
        type UniversePatchTransform;
        input dmx;
        output universe1;
        defaults { source_universe 2; source_channel 1; length 150; }
        segment { target_channel 1; }
        segment { target_channel 151; }
        segment { target_channel 300; }
        segment { length 62; target_channel 451; }
    }

    node sacnSink1 {
        type SacnSinkNode;
        input universe1;
        target_host "10.0.60.30";
        target_universe 1;
        min_interval_ms 1000;
    }

    node universePatch2 {
        type UniversePatchTransform;
        input dmx;
        output universe2;
        defaults { source_universe 2; source_channel 1; length 150; }
        segment { target_channel 1; }
        segment { target_channel 151; }
        segment { target_channel 300; }
        segment { length 62; target_channel 451; }
    }

    node sacnSink2 {
        type SacnSinkNode;
        input universe2;
        target_host "10.0.60.30";
        target_universe 2;
        min_interval_ms 1000;
    }

    edge { from sacnSource:dmx; to universePatch0:dmx; }
    edge { from universePatch0:universe0; to sacnSink0:universe0; }

    edge { from sacnSource:dmx; to universePatch1:dmx; }
    edge { from universePatch1:universe1; to sacnSink1:universe1; }

    edge { from sacnSource:dmx; to universePatch2:dmx; }
    edge { from universePatch2:universe2; to sacnSink2:universe2; }
}
```

- **Segment semantics**: Each `segment { ... }` describes how source universes/channels map into the target buffer, mirroring `NormalizedInputSegment` from the TS loader but inline. `defaults { ... }` blocks let authors set per-node baseline values so repeated segments stay concise.
- **Graph validation**: After parsing, the loader enforces unique node names, verifies ports, and ensures the DAG is acyclic before building the execution plan.

## Protocol Adapters (Example)

1. **`SacnSourceNode`**
   - Wraps `sacn.sACNreceiver`.
   - On packet callback, converts DMX slots + metadata into `Frame`.
   - Emits to output `"dmx"`.
2. **`UniversePatchTransform`**
   - Mirrors `NormalizedInputSegment` logic from TS (`src/config/loader.ts`).
   - Accepts config describing segments; copies bytes into target buffer, tracks dirty flag.
3. **`SacnSinkNode`**
   - Wraps `sacn.sACNsender` client cache (per host)
   - Maintains packet buffer, scheduling `send` respecting `min_interval_ms`.

## Observability & Tooling

- **Logging**: structured via `structlog`, exposing node id, frame topic, timing.
- **Metrics**: optional integration with `prometheus_client` (frames/sec per node, queue depth, latency).
- **Tracing**: per-frame UUID to correlate through DAG.
- **Replay**: capture frames to disk; provide CLI to replay into graph for regression tests.

## Example Flow (Parity with JS)

1. `SacnSourceNode(universes=[...])` listens on UDP 5568, emits frames keyed by universe.
2. `UniversePatchTransform` instances map input universes/channels to output buffers (same math as `SacnUniverseProducer.handleInput`).
3. `FrameRateLimiterTransform` enforces `min_interval_ms`.
4. `SacnSinkNode` sends packets via cached clients and sequences (`nextSequence()` logic borrowed from TS).

## Implementation Roadmap

1. **Scaffold project**: `uv init --package rasl`, add dependencies.
2. **Core engine**: frame model, node protocol, graph builder, scheduler.
3. **Config + registry**: Pydantic models, dynamic loading.
4. **sACN adapters**: Source + Sink nodes with parity tests against fixtures.
5. **Transform library**: Universe patching, filtering, scaling.
6. **Telemetry & CLI**: logging defaults, health checks, run command (`python -m rasl`).

## Testing Strategy

- Unit tests for frame math & transforms (use synthetic frames).
- Integration tests with loopback sACN (receiver + sender on localhost) to ensure bytes forwarded correctly.
- Property tests for DAG validation (random graphs ensuring rejection of cycles).

## Open Questions

1. How to represent non-byte payloads (e.g., JSON) — propose typed `topic` conventions.
2. Should config support dynamic reloading? (Could use file watcher, but not MVP.)
3. Where to define security constraints (auth, ACL) if new protocols introduced.

---

## Completed Milestones

The following have been implemented based on principles from `rasl/old/`:

- ✅ **NodeMonitor** — Per-node execution time, success/failure tracking (`rasl/runtime/monitor.py`)
- ✅ **Error Isolation** — Node failures don't crash the graph; configurable auto-disable threshold
- ✅ **Frame Budget Monitoring** — Logs warnings when frame processing exceeds budget (default 16ms)
- ✅ **Graph `describe()`** — `ExecutionPlan.describe()` returns JSON-serializable graph structure
- ✅ **CLI `--describe`** — `rasl --describe config.conf` prints graph as JSON

---

## Roadmap: Web API & UI

The archived design in `rasl/old/` proposed a comprehensive web interface. This section adapts those ideas into an incremental roadmap for the current implementation.

### Phase 1: HTTP API Server

Add a minimal FastAPI server that runs alongside the runtime, exposing read-only endpoints.

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health` | Liveness check (`{"status": "ok"}`) |
| GET | `/api/v1/graph` | Graph structure from `plan.describe()` |
| GET | `/api/v1/metrics` | Node stats from `runtime.get_node_stats()` |
| GET | `/api/v1/nodes/{id}` | Single node details + metrics |

**Implementation:**

```python
# rasl/server/app.py
from fastapi import FastAPI
from rasl.runtime import Runtime

def create_app(runtime: Runtime) -> FastAPI:
    app = FastAPI(title="RASL API", version="0.1.0")

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/v1/graph")
    def graph():
        return runtime._plan.describe()

    @app.get("/api/v1/metrics")
    def metrics():
        return runtime.get_node_stats()

    return app
```

**CLI integration:** `rasl config.conf --api-port 8080` starts the server alongside the runtime.

### Phase 2: WebSocket Metrics Stream

Add real-time metrics streaming for live dashboards.

**WebSocket endpoint:** `ws://localhost:8080/api/v1/ws/metrics`

**Message format:**

```json
{
  "type": "metrics",
  "timestamp": 1234567890.123,
  "nodes": {
    "sacnSink0": {
      "handle_count": 1500,
      "avg_execution_time_ms": 0.42,
      "success_rate": 1.0
    }
  }
}
```

**Subscription model:** Clients receive metrics at a configurable interval (default 1s). Future: filter by node ID.

### Phase 3: Parameter Specifications

Enable nodes to declare their parameters for automatic UI generation.

**Node interface addition:**

```python
class Node(Protocol):
    # ... existing ...
    def param_spec(self) -> dict[str, ParamSpec]:
        """Declare parameters for UI generation."""
        return {}

@dataclass
class ParamSpec:
    type: Literal["int", "float", "str", "bool", "enum"]
    default: Any
    min: float | None = None
    max: float | None = None
    choices: list[str] | None = None  # for enum type
    description: str = ""
```

**Example implementation:**

```python
class SacnSinkNode:
    def param_spec(self) -> dict[str, ParamSpec]:
        return {
            "min_interval_ms": ParamSpec(
                type="int", default=25, min=0, max=1000,
                description="Minimum ms between packets"
            ),
            "priority": ParamSpec(
                type="int", default=100, min=0, max=200,
                description="sACN priority"
            ),
        }
```

**API endpoint:** `GET /api/v1/nodes/{id}` includes `params` with current values and specs.

### Phase 4: Parameter Updates

Allow runtime parameter changes via API (opt-in per node).

**Endpoint:** `PATCH /api/v1/nodes/{id}`

```json
{"params": {"min_interval_ms": 50}}
```

**Node interface:**

```python
class Node(Protocol):
    def set_params(self, **params: Any) -> None:
        """Update parameters at runtime. Override to support."""
        raise NotImplementedError("Node does not support runtime updates")
```

**Validation:** API validates against `param_spec()` before calling `set_params()`.

### Phase 5: Web Dashboard

A minimal embedded UI served from `/` when the API server is running.

**Technology:** Single HTML file with Alpine.js or htmx for simplicity (no build step). Can upgrade to React/Vite later.

**Features (MVP):**

- **Health status** — Green/red indicator, uptime
- **Graph view** — Node list with connections (text-based initially, upgrade to visual later)
- **Metrics table** — Per-node stats (handle count, avg time, success rate, errors)
- **Auto-refresh** — Poll `/api/v1/metrics` every 2s or use WebSocket

**Features (Future):**

- Interactive graph visualization (D3.js or similar)
- Parameter sliders/controls from `param_spec()`
- Real-time DMX channel preview
- Log viewer / event stream

---

## Architectural Principles (from `rasl/old/`)

The following principles from the archived design guide future development:

### 1. Explicit Over Magic

- **Time conversions** should be visible transforms, not hidden runtime behavior
- **Looping/duration** is configured explicitly on sources, not inferred
- **Error vs EOS** are distinct: errors are noisy failures, EOS is silent completion

### 2. Base Class Separation

- **Base classes** handle: lifecycle, error propagation, frame routing, metrics
- **Child classes** handle: domain logic only (data generation, transformation, emission)
- **Mixins** provide composable behaviors (rate limiting, looping, duration)

### 3. Lazy Evaluation (Future)

The old design proposed sink-driven lazy evaluation with per-frame memoization. Current implementation is push-based. Consider lazy evaluation if:

- Multiple sinks share upstream branches (avoids redundant computation)
- Some sinks skip frames (avoids computing unused data)

### 4. Graceful Degradation

- Missing optional dependencies don't crash the system
- Failed nodes are isolated, not propagated
- Unknown node types in config produce clear errors, not crashes

---

## Plugin Architecture (Future)

For extensibility beyond built-in nodes, adopt entry-point based discovery:

```toml
# pyproject.toml for a plugin
[project.entry-points."rasl.nodes"]
my_sink = "my_plugin.nodes:MySinkNode"
```

**Core provides:**

- `NodeRegistry` that auto-discovers plugins at startup
- Base classes for Source, Transform, Sink
- Standard `param_spec()` and `port_schema()` interfaces

**Plugins provide:**

- Node implementations
- Optional UI components (future)

This keeps the core lightweight while enabling community extensions.

---

This design positions `rasl` as a generic, extensible data engine capable of reproducing the existing reflector pipeline while supporting future transforms, sinks, and operational tooling.
