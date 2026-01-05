# fixes.md

Documented issues that need concrete fixes before we tackle broader cleanups.

Terminology (as used by the TS runtime):
- **Tick**: graph-global monotonically increasing integer (one per “frame”).
- **Frame**: exchange wrapper around a payload + metadata (including tick number).
- **Payload**: the underlying data (e.g. a matrix-like payload with shape `(count, components)`).

## Scheduler timing + cycle handling regression
- **Files**: `js/packages/engine/src/scheduler/unified.ts:146-334`
- **Confirmed semantics**:
  - Cycles are allowed.
  - A node must be pulled **at most once per tick**; after it produces an output for a tick, all downstream consumers may read it for that same tick.
  - Ticks are universal within a graph, but not every node will see every tick (only nodes demanded by enabled sinks participate).
  - `dt` is per-node elapsed time since that node was last pulled; it should almost never be `0`.
  - Cycles resolve via caching: if a node reads from an upstream producer that has not yet been pulled for the current tick, it reads that producer’s **previous tick** output.
- **Problem**: `_lastNodeTime` is only updated for sink nodes, so upstream nodes always see `dt === 0`. `_pullUpstream` also recursively calls `_pullNode` without caching or a re-entrancy guard, which can blow the stack or spin forever in graphs with cycles.
- **Impact**: Any node that integrates over time (envelopes, animations) behaves incorrectly, and graphs containing cycles never converge.
- **Next steps**:
  1. Make “tick” explicit: increment a single graph-global `tick` once per scheduler frame (not per event-loop spin) and build a single `TickContext` per tick.
  2. Add per-tick memoization (`lastPulledTick` + output cache) so each node runs at most once per tick, even with multiple sinks and shared upstream subgraphs.
  3. Add a re-entrancy guard so cycles cannot recurse infinitely; when encountering an in-progress node, serve its last-completed output (previous tick) instead.
  4. Track `lastPulledTime` per node and compute `dt` for **all** nodes from a high-resolution monotonic clock.
  5. Tests:
     - `dt` advances (non-zero deltas) for time-based transforms.
     - Shared upstream nodes are pulled once per tick with multiple sinks.
     - Cyclic graphs do not recurse infinitely and cycle edges read previous-tick outputs.

## Edge slicing/repeat metadata ignored
- **Files**: `js/packages/engine/src/config/rasl.ts:310-324`, `js/packages/engine/src/scheduler/unified.ts:337-364`
- **Confirmed semantics**:
  - Slices like `[start:end]` apply to **count indices** (rows/items), not component indices.
    - Example: slicing `RGB[0:2]` selects 2 colors (6 numbers) and slicing `RGBW[0:2]` selects 2 colors (8 numbers).
  - Slice syntax is half-open `[start:end)`; `end` may be omitted to mean “to the end”.
  - A single element may be selected with a slice like `[0]` or `[0:1]`.
  - If either source or destination omits slice information, it defaults to `[0:n)` where `n` is the number of elements addressed by the other side’s slice.
  - Overlapping destination mappings are forbidden (startup fatal error).
  - Routing should be as **zero-copy** as possible. Copying is an exception for complex routing cases.
  - Output ports are backed by a **double-buffered** store (swap on every `write`) so downstream reads are safe without copies.
- **Problem**: The config loader records `sourceSlice`, `targetSlice`, and `repeat` on `Edge`, but the scheduler simply forwards the entire frame without applying slices or replication.
- **Impact**: Channel-routing directives in `.conf` files silently do nothing, so node graphs behave differently from the Python implementation.
- **Next steps**:
  1. Introduce a bound routing layer that can map `(sourceSlice, repeat) -> targetSlice` and deliver either views or copied buffers to inputs.
  2. Enforce non-overlapping destination ranges during bind/startup (fail fast).
  3. Implement zero-copy routing via views into the output port’s double-buffered backing store; fall back to copying only when required.
  4. Cover with integration tests built via `loadRaslConfigFromSource` to confirm slice defaults, overlap failures, and repeat behavior.
- **Open questions**:
  - Define the exact `repeat` truth table covering all permutations of:
    - naked vs sliced connections (no slices, one side sliced, both sides sliced)
    - source vs destination sizes (smaller/equal/larger)
    - what happens when sizes differ without `repeat`
  - Special case (naked connection + `repeat`): tile the input to fill the output; if input is larger than output, apply as many elements as possible (truncate).
  - When both slices are omitted, define how the destination “output size” is chosen (e.g. fixed port counts vs runtime payload count) so defaults and `repeat` have a concrete `n`.

## Payload type compatibility never validated
- **Files**: `js/packages/engine/src/runtime/ports/spec.ts`, `js/packages/engine/src/graph/builder.ts:62-112`
- **Confirmed semantics**:
  - `produces` and `accepts` are hierarchical type strings (e.g. `color`, `color:rgb`, `color:rgb:linear`).
  - Compatibility rule: `produces` must be the same or more specific than `accepts`.
    - `produces=color:rgb` is compatible with `accepts=color`; inverse is not.
  - Parent/child relationships are not only `:`-prefix; explicit inheritance must be supported (e.g. `color` is a subtype of `matrix`).
  - Type hierarchy is distributed across packages and can be extended by user implementations.
  - Compatibility must not depend on `instanceof`; it should use runtime payload metadata/type strings.
- **Problem**: Each port declares `accepts`/`produces` and every payload exposes `describe()`/`isCompatibleWith`, but `GraphBuilder.connect` only checks for port names and ignores payload types entirely.
- **Impact**: Invalid connections (e.g., bool payload into color-only sink) compile and fail later at runtime with cryptic errors.
- **Next steps**:
  1. Define a string-based type compatibility resolver (`isCompatible(produces, accepts)`) that supports both `:`-prefix hierarchy and explicit, package/user-registered inheritance edges (e.g. `color -> matrix`).
  2. Ensure every payload exposes its runtime type string (likely via `payload.describe()`), and output ports declare the same `produces` string.
  3. Extend `GraphBuilder.connect` to compare source `produces` against target `accepts` (including `accepts` arrays) and fail early with descriptive errors.
  4. Add regression tests for positive/negative hierarchical matches and cross-root inheritance.
- **Open questions**:
  - Define the public API for packages/user code to extend the hierarchy (how edges are registered and how consumers supply/compose the registry).
