# fixes.md

Documented issues that need concrete fixes before we tackle broader cleanups.

Terminology (as used by the TS runtime):
- **Tick**: graph-global monotonically increasing integer (one per “frame”).
- **Frame**: exchange wrapper around a payload + metadata (including tick number).
- **Payload**: the underlying data (e.g. a matrix-like payload with shape `(count, components)`).

## ~~Scheduler timing + cycle handling regression~~ ✅ RESOLVED
- **Files**: `js/packages/engine/src/scheduler/unified.ts`
- **Resolution**: Implemented all required fixes:
  1. ✅ Tick incremented once per frame at start of main loop
  2. ✅ Per-tick memoization via `_lastPulledTick` map
  3. ✅ Re-entrancy guard via `_inProgress` set for cycle detection
  4. ✅ Per-node `_lastPulledTime` tracking for correct `dt` calculation
  5. ✅ Tests added in `unified.test.ts` (10 tests covering timing, memoization, cycles, dt)

## ~~Edge slicing/repeat metadata ignored~~ ✅ RESOLVED
- **Files**: `js/packages/engine/src/scheduler/routing.ts`, `js/packages/engine/src/scheduler/unified.ts`
- **Resolution**: Implemented routing layer with slice/repeat support:
  1. ✅ `applyEdgeRouting(frame, edge)` applies sourceSlice, repeat, and validates targetSlice
  2. ✅ `slicePayload(payload, slice)` extracts element ranges from MatrixPayload
  3. ✅ `validateNonOverlappingTargets(edges)` enforces non-overlapping destination ranges at startup
  4. ✅ Scheduler calls `_validateTargetSlices()` in constructor (fail fast)
  5. ✅ `_pullUpstream` applies routing when forwarding frames between ports
  6. ✅ Tests in `routing.test.ts` (23 tests covering slicing, repeat, overlap validation)
- **Remaining open questions** (deferred to future work):
  - Exact `repeat` truth table for edge cases (naked + repeat, size mismatches)
  - Zero-copy views vs copying tradeoffs for complex routing

## ~~Payload type compatibility never validated~~ ✅ RESOLVED
- **Files**: `js/packages/engine/src/runtime/types/registry.ts`, `js/packages/engine/src/graph/builder.ts`
- **Resolution**: Already implemented:
  1. ✅ `TypeRegistry` class with colon-prefix hierarchy and explicit inheritance edges
  2. ✅ `isTypeCompatible(produces, accepts)` function for compatibility checking
  3. ✅ `GraphBuilder.connect` validates payload types at lines 93-103
  4. ✅ Default types registered: `color -> matrix`, `bool -> matrix`
  5. ✅ Tests in `registry.test.ts` (25 tests covering hierarchy, inheritance, cycles)
