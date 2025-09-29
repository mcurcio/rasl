# RASL Architecture (High‑Level)

**Purpose**
RASL (Realtime Animation Scripting Library) is a modular Python framework for building and running **real‑time animation graphs**. It targets lights, motors, kinetic sculptures, and other channel‑based systems. Users compose **sources → transforms → sinks** into a validated DAG and run it against a single, pluggable scheduler. The goals are correctness (typed contracts, deterministic timing), extensibility (plugins), and excellent developer experience (instance‑first nodes, clean APIs, and strong observability).

---
## System Overview

- **DAG‑based processing**: Nodes connect via **ports** to form a directed acyclic graph. The engine executes nodes per frame in topological order with **lazy, per‑frame evaluation** driven by sinks.
- **Single time authority**: A pluggable **scheduler** (on a clock) produces frames `{t, dt, seq}`. Reads never create frames; they only materialize data for the current frame.
- **Strict contracts**: Ports carry **schemas** (components + channels) so math, colors, and units are unambiguous. Validation happens at connection time and again at engine start.
- **Flexible I/O**: Sources and sinks are pluggable; quantization/gamma live only in sinks. Optional per‑sink resampling is explicit and observable.
- **Observability**: REST/WS expose graph, metrics, events, and sample previews. Observers never trigger compute.

```mermaid
flowchart TD
  subgraph Engine
    SCH[Scheduler/Clock]\n(Frames t,dt,seq)
    EXE[Executor]\n(Lazy per-frame eval)
  end
  subgraph Graph
    SRC[[Sources]] -->|ports| TRF[[Transforms]] -->|ports| SNK[[Sinks]]
  end
  SCH --> EXE
  EXE --> SNK
  SNK -. observe .-> UI[(Observers/WS)]
```

---
## Core Concepts (precise terms)

- **Frame**: `{t, dt, seq}` emitted by the scheduler each cadence. All nodes in a tick see the same Frame.
- **Node (type)**: one of `Source`, `Transform`, `Sink`. Nodes are regular Python objects; users instantiate them and connect their ports.
- **Port**: a node’s named I/O endpoint under `node.ports`. Connections are **port‑to‑port**; no per‑channel wiring.
- **Component**: a **bundle** of related signals that travel together (e.g., `Color(HSV)`, `Color(linear_srgb)`, `Vector3(mm)`). A component defines invariants such as units, colorspace, and range rules.
- **Channel**: a single scalar signal inside a Component (e.g., `h`, `s`, `v` for HSV; `r`,`g`,`b` for linear sRGB; `x`,`y`,`z` for vectors).
- **Schema (of a Port)**: an ordered collection of **Components**, each with their **Channels**. Schemas are compared by **component/channel names**, not just position.
- **Edge (connection)**: `src_port → dst_port`. The system aligns channels by name and records any permutation; unit or colorspace changes require explicit transforms.

### Liveness (source capability)
- **STREAM**: potentially unbounded stream (may end or interrupt). Examples: network sources.
- **FINITE**: bounded media that will signal EOS once. Example: `CSVSource`. Looping is an explicit part of the source type (seek‑based), not a generic transform.
- **EVENT**: sparse/bursty events with timestamps. Engine samples/interpolates via adapters near consumption (`Hold`, `Interp`, `Resample`).

### End‑of‑Stream (EOS) handling
Per input, consumers declare an **on_eos** policy: `hold_last | zero | repeat | stop_sink | fail`. Multi‑input transforms also declare an `eos_mode`: `pass_through | until_all_done | until_any_done`. Defaults favor real‑time continuity: `pass_through` + `hold_last`.

---
## Graph Composition

- **Instance‑first**: create node instances and wire their ports. Example: `sine.ports.out >> amp.ports.in` then `amp.ports.out >> sacn.ports.in`.
- **Ports namespace**: `node.ports` avoids attribute collisions; ports can be accessed by attribute or key (`node.ports.a`, `node.ports["a"]`). Variadic inputs are exposed as indexed groups (e.g., `mixer.ports.inputs[0]`).
- **Validation**
  - **On connect**: verify existence, direction (`out → in`), name‑based schema compatibility; compute any channel permutation map.
  - **On engine attach/start**: global DAG, duplicate IDs, required inputs connected, liveness/rate plan sanity. Execution aborts if required inputs are dangling.
- **Permutation vs transform**: Pure reordering within a component or across components is auto‑aligned by names. Semantic changes (colorspace, units, subset/superset shape) require explicit nodes: `ToColorSpace`, `ConvertUnits`, `Select/Reorder/Split/Pack`.

---
## Execution Model

- **Scheduler emits frames**: pluggable policies (`fixed rate` with cadence recovery: `drop | skip | slow`).
- **Lazy evaluation per frame**: for each frame, each sink decides whether to emit (optionally at a decimated rate). To emit, a sink **materializes** its input branch; the executor computes upstream nodes on demand with per‑frame memoization. Shared subgraphs compute once per frame.
- **Resampling**
  - Preferred: an explicit `Resample/Hold/Interp` node near consumers when many sinks share the same policy.
  - Alternative: per‑sink capability via `required_rate` with `align` and `mode` (hold/linear/cubic). If enabled, the engine may auto‑insert a `Resample` immediately upstream of the sink and record it in the graph description.
- **Quantization and gamma**: only at sinks.

---
## Validation Rules (non‑negotiable)

1. **Ports** connect whole schemas; no channel‑level wiring. Name‑based alignment; permutations are allowed without extra nodes.
2. **Transforms** must have all **required** inputs connected. **Sinks** require `in`. **Sources** must not have inputs. Variadic inputs enforce `min/max`.
3. **Units and colors**: vector/motor math requires axis/unit equality; color math defaults to **linear sRGB** unless otherwise declared. Hue wraps only when the channel’s range rule is `wrap`.
4. **Normalization**: transform outputs are normalized per the output schema’s ranges; default rule is `clip`.
5. **Rate contracts**: sinks may declare `required_rate`. The rate planner compares upstream **effective_hz** and either connects, **auto‑inserts a Resample**, or fails with a fix‑hint. Engine base rate must be compatible with `align="engine"` requirements.
6. **Liveness**: types declare `STREAM | FINITE | EVENT`. EOS policies must be specified (or defaulted) at joins and sinks. No hidden looping outside seekable sources.

---
## Observability & Control Plane

- **REST**
  - `GET /v1/graph` → canonical graph spec: nodes, ports, schemas, params, liveness, any inserted adapters.
  - `POST /v1/graph` → atomic swap; validated before activation.
  - `GET /v1/nodes/{id}` → params, port schemas, status.
  - `PATCH /v1/nodes/{id}` → runtime param updates with validation.
  - `GET /v1/metrics?since=…` → counters/gauges/histograms.
- **WebSocket** `ws /v1/stream`
  - Topics: `metrics`, `samples` (throttled previews), `events` (graph swaps, overruns, eos, drops, plugin changes).
- **UI Observers**
  - Read committed snapshots; never trigger compute.
  - Visualize Components/Channels with units, ranges, colorspaces; display sink egress modes (gamma, quantization, resample).

---
## Module Responsibilities (brief)

- **engine/**: scheduler/clock, executor, graph discovery (from sinks upstream), buffers, validator, metrics/events, policies, serialization, errors.
- **nodes/**: source/transform/sink families; each node declares static port schemas, params, and liveness.
- **io/**: transports for inputs/outputs (CSV, network, sACN/DMX, UDP, WebSocket, files).
- **http/**: REST/WS server and schemas.
- **api/**: authoring surfaces (chaining, `describe()`), observer API.
- **plugins/**: entry‑point discovery and namespacing.
- **types.py**: `Frame`, `Range`, Component/Channel/Schema descriptors.
- **utils/**: topo sort, idgen, logging, small math/time helpers.

---
## Naming & Defaults

- **Ports**: default `in` and/or `out`; extra inputs are short semantic names (`a`, `b`, `mix`). Ports live under `node.ports`.
- **Colorspace**: default `linear_srgb`.
- **Ranges**: default `[0,1]`, rule `clip`; hue uses `wrap`.
- **Cadence**: engine default policy `drop` for real‑time rigs; tests/sims may use `slow` or manual ticks.
- **Sinks**: may declare `required_rate`; absent that, they emit at engine rate.

---
## Example (authoring, high‑level)

```python
sine = SineSource(freq=1.2, channels=150)             # STREAM
amp  = ScaleBias(scale=0.6, bias=0.2)                 # Transform
rgb  = ToRGB()                                        # Transform
sacn = SACNSink(universe=1, start=1,                  # Sink
                required_rate={"target_hz": 30, "align": "engine"})

# Wire the DAG (instance‑first)
sine.ports.out >> amp.ports.in
amp.ports.out  >> rgb.ports.in
rgb.ports.out  >> sacn.ports.in

engine = Engine(sinks=[sacn], scheduler=FixedRateScheduler(MonotonicClock(), 60),
                cadence="drop", autofix_rate=True)
await engine.start()
```

This document is intentionally high‑level: it fixes the **concept model**, **API shape**, and **validation/timing rules** so concrete implementations can proceed without ambiguity.
---
