# Performance Requirements: Tick-Cheap Engine, Buffer Reuse, and Hot-Swappable Plans

Audience: senior engineer implementing the upcoming engine refactors.

This doc is a requirements/specification document (not a tutorial). It captures the target architecture, key invariants, and the implementation constraints needed to deliver a tick-cheap runtime while supporting runtime topology changes.

---

## 1. Context: current state and why it needs to change

### 1.1 Current execution model(s)

- The repo currently contains two runtime implementations:
  - `rasl.runtime.unified.UnifiedScheduler` (pull-first, tick scheduling, caching)
  - `rasl.runtime.scheduler.Runtime` (legacy mailbox runtime; deprecated)

- The CLI uses `UnifiedScheduler`.

### 1.2 Current performance pain points

- Per-tick overhead includes dynamic routing decisions and transformations:
  - slice/repeat work is decided and performed at runtime each tick.
  - copies are performed for slicing and repeat expansion (e.g. `MatrixFrame.repeat` uses tiling).

- The engine currently carries configuration information through function signatures and edge objects (e.g. `GraphBuilder.connect(...)` signature includes slice/repeat parameters). This hinders precomputation and “compiled” execution.

- Payloads and frames are somewhat conflated in practice.

### 1.3 Terminology cleanup requirement (breaking)

- Slices and count constraints must be expressed exclusively in **`count` space**.
- Remove **all** references to “channels” terminology. No deprecated aliases.
- A “DMX channel index” is a different payload domain and must be handled via mapping nodes.

---

## 2. Target architecture: heavy setup, cheap ticks

### 2.1 Design goal

The hot path per tick should be:

- pull scheduling
- node handler execution
- minimal routing operations that are pre-selected and bound

The tick loop must avoid:

- graph structure work
- per-tick allocations (except unavoidable dynamic-size growth)
- redundant slice/repeat transformations

### 2.2 Two-plan model

Define two distinct plan layers:

- **ExecutionPlan**: structural description of nodes and logical edges.
- **BoundExecutionPlan**: runtime-compiled plan containing direct references to ports, precomputed slice indices, and pre-selected edge strategies.

A BoundExecutionPlan is equivalent to “JIT compiled bytecode” for the graph.

---

## 3. Canonical data model

### 3.1 Dimensions

All numeric payloads are represented in terms of:

- **`count`**: number of items/rows (e.g. pixels)
- **`components`**: per-item component width (e.g. RGB=3)
- **`dtype`**: numeric dtype

The canonical ndarray layout is:

- `data.shape == (count, components)`

### 3.2 Ownership model

- Inputs must be treated as **read-only** by node implementations.
- Outputs are written to **engine-managed buffers**.

This enables safe reuse and view/buffer optimizations.

---

## 4. Ports and types

### 4.1 PortSpec requirements

#### Input ports

- Input ports may accept multiple payload types/domains.
- The InputPort spec must place `accepts` as the first argument.
- Input ports express count constraints (fixed or variable bounds).

#### Output ports

- Output ports produce exactly one guaranteed payload type.
- The OutputPort spec must place the produced payload type as the first argument.
- Output ports express count constraints (fixed or variable bounds).

### 4.2 Type validation requirements

At build/bind time, for each edge:

- The source output type must be compatible with the target input accepts set.
- Compatibility is based on payload domain/type semantics (existing `FramePayload.is_compatible_with` pattern may be used).

---

## 5. Node author API: acquire/fill/commit

### 5.1 Requirements

Node authors must be able to write highly vectorized NumPy code.

- No index-by-index loops should be required.
- The API should encourage using ufunc `out=` patterns to avoid temporaries, but not require it.

### 5.2 OutputPort buffer API (required)

Introduce (or refactor) OutputPort so nodes use:

- `buf = output.acquire(count: int) -> np.ndarray`
- node fills `buf` (vectorized)
- `output.commit() -> None`

#### Semantics

- `acquire(count)` is a contract: “I will produce `count` items of this port’s payload type this tick. Provide writable space.”
- `acquire(count)` must succeed immediately.
  - If capacity must grow, growth occurs immediately for the write buffer.
- `commit()` indicates the port is done producing for the tick.

### 5.3 Fixed vs dynamic count ports

- Fixed-count outputs:
  - engine allocates buffers upfront.
  - `acquire(count)` must error if count != spec count.

- Dynamic-count outputs:
  - node may call `acquire(count)` each tick.
  - engine may grow/shrink logical count without shrinking capacity.
  - engine should grow capacity amortized.
  - engine may optionally “guess allocate” upfront based on graph info.

### 5.4 Frame vs payload separation

- Nodes should not have to specify payload type on commit; the output port spec defines it.
- `commit` is about publishing the produced payload/frame, not about choosing the payload type.

---

## 6. Buffer model: double buffering

### 6.1 Requirement

Outputs must be safe for downstream reads while the producer writes.

Implement double buffering:

- **front/published** buffer: read by downstream during the tick
- **back/writable** buffer: written by the node during its handler

### 6.2 Publishing point

Publishing occurs when the node commits (or immediately after handler completion in a controlled runtime phase).

### 6.3 Resize semantics

- Resizing is considered a “graph change” in the sense that it may change capacities and invalidate certain bound views.
- However, the acquire API must succeed immediately.

Required approach:

- if growth is needed, grow the **writable/back** buffer immediately
- publish swap occurs only at a safe point

### 6.4 Opportunistic paired-buffer allocation

If a port grows this tick, the paired buffer should be grown opportunistically during scheduler idle time:

- do this on the scheduler thread during sleep/idle (no extra thread required)
- maintain a list of “ports grown this tick”

---

## 7. Routing model: compile edges into bound ops

### 7.1 Core requirement

Tick routing must not interpret high-level edge configuration every tick.

Instead, compile edges into “bound operations” that reference ports and execute minimal logic.

### 7.2 BoundEdgeOp responsibilities

A BoundEdgeOp must:

- read from source output (published/front buffer for that tick)
- produce a clean view or fill a target buffer so that the target InputPort sees a normal ndarray-backed payload

### 7.3 Strategy selection (setup time)

At bind/compile time, select a strategy per edge:

- identity routing
- slice view (true view when possible)
- slice fill into target buffer region (copy region only)
- repeat fill (fill only the needed region; no intermediate tiling)

Also:

- detect common subexpressions (same source + same transformation used by multiple edges) and compute once per tick.

---

## 8. Repeat and slicing requirements

### 8.1 Slices

- All slices are in **count space**.
- Slice indices are row indices.

### 8.2 Repeat

- `repeat` is an edge-level feature.
- Nodes must not need to know whether input was repeated.

Performance requirements:

- Avoid allocating intermediate “tiled” arrays.
- Prefer filling the target buffer directly:
  - only materialize the subset required by the consumer edge
  - allow caching of computed repeated segments within a tick

Note: a general periodic modulo repeat is not representable as a pure ndarray view; direct fill into target buffers is the expected fast path.

---

## 9. Runtime topology changes (hot swap)

### 9.1 Requirement

The engine must support runtime graph topology changes (nodes/edges added/removed).

The system must:

- compile the new plan off the hot path
- swap to it during idle/safe points
- manage background tasks and push source collisions safely

### 9.2 Plan generation

Introduce a monotonic plan generation ID:

- each active plan has a generation
- ports and routing are generation-tagged

### 9.3 Background compilation

When a topology change is requested:

- build a new ExecutionPlan
- compile to BoundExecutionPlan in the background (or at least off the hot path)
- validate types/slices/count constraints during compilation

### 9.4 Safe swap protocol

Swap at a safe point (tick boundary / scheduler idle window):

- pause routing work
- reconcile node lifecycles:
  - keep existing nodes if still present
  - stop removed nodes gracefully
  - start new nodes
- rebind InputPort/OutputPort instances
- migrate buffers where possible

### 9.5 Buffer migration rules

Attempt to reuse buffers when:

- produced payload type matches
- dtype/components match
- capacity is sufficient

Otherwise allocate fresh buffers.

### 9.6 Push / background task collisions

Push nodes may run background tasks and write outputs asynchronously.

Requirements:

- A push write must not publish into the wrong plan generation.
- The scheduler must only route frames/buffers from the active generation.

Implementation note:

- generation-tag ports
- drop/ignore writes from old generation after swap (or route them only within their own generation during a draining phase)

---

## 10. GraphBuilder/connect API cleanup requirements

The current connection APIs carry too many runtime-level parameters.

Requirements:

- Reduce “wide signatures” that shuttle slice/repeat/count metadata around.
- Move execution-specific concerns into the BoundExecutionPlan compilation phase.

The system should evolve toward:

- a structural graph connect API for describing topology
- a separate compilation step for binding edge strategies

---

## 11. Acceptance criteria

A change is considered successful when:

- “channels” terminology is eliminated; count/components are used consistently.
- Slicing is exclusively count-based.
- Nodes can implement outputs via acquire/fill/commit using vectorized NumPy.
- Fixed-count outputs allocate buffers upfront and error on mismatched acquire.
- Dynamic-count outputs can grow immediately and safely.
- Tick loop avoids per-tick allocations in the steady state.
- Repeat does not create intermediate tiled arrays in the hot path.
- BoundExecutionPlan exists and tick routing uses bound ops.
- Topology changes can be applied by background compile + safe swap without process restart.

---

## 12. Important interfaces and implementation details (reference)

This section is intentionally concrete.

### 12.1 OutputPort

Required methods:

- `acquire(count: int) -> np.ndarray`
- `commit() -> None`
- `published() -> np.ndarray` (front buffer)
- `capacity() -> int`

Internal state:

- `front: np.ndarray`
- `back: np.ndarray`
- `logical_count: int`
- `generation: int`

### 12.2 BoundExecutionPlan

- `generation: int`
- `incoming_ops: dict[str, list[BoundEdgeOp]]`
- `schedule` (rate drivers)
- `node_runtimes`

### 12.3 BoundEdgeOp

- `source_port: OutputPort`
- `target_port: InputPort`
- `strategy: EdgeStrategy`
- `src_slice: slice | None` (count)
- `tgt_slice: slice | None` (count)
- `repeat: int | None` / `repeat_until: int | None`

Method:

- `route(tick) -> None`

### 12.4 Scheduler swap protocol

- `request_plan_update(plan_spec)`: enqueue compile
- `poll_compiled_plan()`: check readiness
- `swap_if_ready_at_safe_point()`: reconcile + swap + generation bump

### 12.5 Idle-time paired-buffer growth

- track grown ports per tick
- during scheduler sleep:
  - grow paired buffers to match
  - clear grown set
