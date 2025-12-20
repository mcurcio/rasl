# fixes.md

Documented issues that need concrete fixes before we tackle broader cleanups.

## Scheduler timing + cycle handling regression
- **Files**: `js/packages/engine/src/scheduler/unified.ts:146-334`
- **Problem**: `_lastNodeTime` is only updated for sink nodes, so upstream nodes always see `dt === 0`. `_pullUpstream` also recursively calls `_pullNode` without caching or a re-entrancy guard, which can blow the stack or spin forever in graphs with cycles.
- **Impact**: Any node that integrates over time (envelopes, animations) behaves incorrectly, and graphs containing cycles never converge.
- **Next steps**:
  1. Cache per-node outputs for each scheduler tick and update `_lastNodeTime` after every successful pull.
  2. Add a `pulling`/`visited` set so `_pullUpstream` short-circuits cycles and surfaces a warning instead of infinite recursion.
  3. Unit-test `dt` progression and cyclical graphs.

## Edge slicing/repeat metadata ignored
- **Files**: `js/packages/engine/src/config/rasl.ts:310-324`, `js/packages/engine/src/scheduler/unified.ts:337-364`
- **Problem**: The config loader records `sourceSlice`, `targetSlice`, and `repeat` on `Edge`, but the scheduler simply forwards the entire frame without applying slices or replication.
- **Impact**: Channel-routing directives in `.conf` files silently do nothing, so node graphs behave differently from the Python implementation.
- **Next steps**:
  1. Introduce a routing layer that can slice or copy `MatrixPayload` buffers before delivering frames to inputs.
  2. Cover with integration tests that build a graph via `loadRaslConfigFromSource` to confirm slices are honored.

## Payload type compatibility never validated
- **Files**: `js/packages/engine/src/runtime/ports/spec.ts`, `js/packages/engine/src/graph/builder.ts:62-112`
- **Problem**: Each port declares `accepts`/`produces` and every payload exposes `describe()`/`isCompatibleWith`, but `GraphBuilder.connect` only checks for port names and ignores payload types entirely.
- **Impact**: Invalid connections (e.g., bool payload into color-only sink) compile and fail later at runtime with cryptic errors.
- **Next steps**:
  1. Extend `GraphBuilder.connect` to compare source `produces` against target `accepts`, using the registry metadata.
  2. Emit descriptive errors during plan construction and add regression tests.
