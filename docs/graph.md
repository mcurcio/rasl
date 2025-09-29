

# Graph Model — RASL

**Purpose**
The graph defines *what* computes in RASL and *how* data flows. It is a directed acyclic graph (DAG) of node instances connected by ports. The engine discovers the graph from sinks, validates contracts, and executes lazily per frame.

---
## Design goals
- **Instance‑first authoring**: users instantiate nodes and wire ports directly.
- **Deterministic & typed**: connections are validated against schemas (components/channels, units, colorspaces).
- **Minimal ceremony**: connect port objects, not ids; no separate builder required.
- **Observable & serializable**: produce a canonical spec (`describe()`) and stable error messages.

---
## Core concepts
- **Node**: `Source | Transform | Sink`. Regular Python objects with declared ports and static schemas.
- **Port**: named I/O endpoint under `node.ports`. A port has a **kind** (`in` or `out`) and a **schema**.
- **Schema**: ordered **Components**, each with their **Channels**.
  - **Component** = bundle (e.g., `Color(HSV)`, `Vector3(mm)`), with units/range/colorspace invariants.
  - **Channel** = scalar inside a Component (e.g., `h`,`s`,`v` or `r`,`g`,`b`).
- **Edge**: a connection `src_port → dst_port` captured at the time of wiring.
- **Frame**: `{t, dt, seq}` from the scheduler. All evaluation in a tick shares the same Frame.

---
## Authoring model
- **Ports namespace**: `node.ports.in`, `node.ports.out`, or `node.ports["a"]`. Variadic inputs appear as indexed groups (e.g., `mixer.ports.inputs[0]`).
- **Connect**: `src.ports.out >> dst.ports.in` (or `connect(src.ports.out, dst.ports.in)`).
- **Immediate validation on connect**:
  - Existence and direction (`out → in`).
  - Name‑based schema compatibility: same Component and Channel ids; order may differ.
  - Record permutation map for zero‑copy remaps when possible.
- **Global validation on engine attach/start**:
  - DAG (acyclic), duplicate id checks, required inputs connected, rate plan sanity, liveness/EOS policies present.
  - Start aborts on any unconnected **required** input; sinks must have `in` wired; sources must have no inputs.

---
## Dataflow & execution
- **Discovery**: the engine builds the reachable subgraph by walking upstream from provided sinks.
- **Lazy per‑frame evaluation**: for each Frame, sinks decide whether to emit; if so, the executor materializes their input branch **on demand** with memoization per `(node_id, frame.seq)`.
- **Shared work**: common upstream branches compute once per frame, even if multiple sinks consume them.
- **No hidden recompute on read**: observers read committed snapshots; reads never create frames or trigger compute.

---
## Rate & cadence
- **Single scheduler** owns time; produces Frames at a base rate with cadence recovery (`drop | skip | slow`).
- **Resample contracts**:
  - **Sinks** may declare `required_rate {target_hz, tolerance, align}`.
  - The rate planner compares upstream **effective_hz** and either (a) connects, (b) auto‑inserts `Resample` immediately upstream of the sink (if enabled), or (c) fails with a fix‑hint.
  - Transforms are rate‑agnostic unless they declare a temporal requirement (e.g., window length).

---
## Liveness & EOS
- **Source capability**: `STREAM | FINITE | EVENT` declared by type (not a param).
- **Per‑input EOS policy** at joins/sinks: `hold_last | zero | repeat | stop_sink | fail`.
- **Multi‑input nodes** declare `eos_mode`: `pass_through | until_all_done | until_any_done`.
- **Defaults** favor real‑time continuity: `pass_through` + `hold_last`.

---
## Schema alignment rules
- **By name, not position**: components/channels matched by id; trivial permutations require no transform.
- **Explicit transforms for semantics**:
  - Colorspace/units changes: `ToColorSpace`, `ConvertUnits`.
  - Structural reshape: `Select`, `Split`, `Reorder`, `Pack/Unpack`.
- **Normalization**: transforms must output values normalized to their output schema ranges. Range rules default to `clip`; hue uses `wrap`.

---
## Graph spec (serialization)
- The engine exposes `describe()` returning a canonical JSON spec:
  - **nodes**: `{id, type, params, liveness, ports: {name: {kind, schema}}}`
  - **edges**: `[[src_id, src_port, dst_id, dst_port], ...]`
  - **adapters**: any auto‑inserted nodes (e.g., `Resample`) are explicit in the spec.
  - **rate_plan**: per‑port `effective_hz`, inferred adapters, alignment.
- `POST /v1/graph` accepts the same shape for remote control; server validates before activation.

---
## Error model (must‑have)
- **SchemaMismatch**: shows offending node id, port, expected vs actual component/channel sets, and suggested fix.
- **UnitMismatch / ColorSpaceMismatch**: requires explicit converters.
- **DanglingInput**: required input not connected (engine refuses to start).
- **RateMismatch**: unmet sink `required_rate`. If `autofix_rate=true`, engine inserts `Resample` and surfaces it; otherwise fails with a fix‑hint.

---
## Observability hooks
- `/v1/graph`: current graph, including any inferred adapters and unresolved issues (e.g., optional inputs dangling).
- `/v1/metrics`: per‑node exec time, overruns, sink emits/drops, resample stats.
- `ws /v1/stream`: `events` (graph swaps, eos, drops), `samples` (throttled previews), `metrics`.
- UI overlays: highlight ports/schemas, show permutation maps, display `effective_hz` and EOS policies at edges.

---
## Examples

### Typical wiring (instance‑first)
```python
sine = SineSource(freq=1.2, channels=150)
amp  = ScaleBias(scale=0.6, bias=0.2)
rgb  = ToRGB()
sacn = SACNSink(universe=1, start=1,
                required_rate={"target_hz": 30, "align": "engine"})

sine.ports.out >> amp.ports.in
amp.ports.out  >> rgb.ports.in
rgb.ports.out  >> sacn.ports.in

engine = Engine(sinks=[sacn], scheduler=FixedRateScheduler(MonotonicClock(), 60),
                cadence="drop", autofix_rate=True)
await engine.start()
```

### Multi‑input join with EOS handling
```python
csv  = CSVSource("clip.csv", loop="repeat")      # FINITE media, seek‑looped
live = NetworkSource(host="…", port=…)            # STREAM
xf   = Crossfade(eos_mode="pass_through")

csv.ports.out.with_eos(on_eos="hold_last") >> xf.ports.a
live.ports.out.with_eos(on_eos="zero")     >> xf.ports.b
xf.ports.out >> sacn.ports.in
```

---
## Summary
The graph is an instance‑first, validated DAG of **ports** carrying **schemas** (components + channels). Connections align by names; semantic changes require explicit transforms. A single scheduler provides Frames; sinks decide whether to emit each frame, triggering **lazy, memoized** evaluation of their upstream branches. Rate contracts and EOS policies are enforced at the edges, making behavior explicit, observable, and debuggable.
