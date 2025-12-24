# Logic Node Expansion Plan

Goal: provide reusable logic primitives for zero/non-zero detection, conditional routing, and instrumentation without hard-coding behaviors inside animation nodes. This document captures semantics for the agreed nodes (#1, #2, #5, #6, #7) so implementation can proceed without ambiguity.

## Shared conventions

- **Payloads**
  - Numeric inputs use `MatrixPayload` (inc. subclasses such as `MatrixFrame`).
  - Boolean outputs use `BoolPayload` (1-D vectors, normalized to 0/1 floats).
  - Color inputs are allowed only when explicitly noted; otherwise callers should convert to matrices first.
- **Shape handling**
  - Nodes that mix two matrices require identical `(count, channels)` unless otherwise specified.
  - Scalar parameters (e.g., constants) are expanded to match the input frame’s shape when needed.
- **Epsilon semantics**
  - Comparisons accept an `epsilon` parameter (default `1e-6`).
  - Equality-style ops use `abs(lhs - rhs) <= epsilon`.
  - Inequalities compare against `rhs ± epsilon` depending on operator (documented per node).

## 1. `MatrixReduceNode` (Accumulator pipeline)

Purpose: fast path to turn a matrix into a single scalar per frame before feeding a comparator. Distinct from StatsNode because it emits one configured aggregate per instance.

| Aspect | Details |
| --- | --- |
| Config | `mode` (enum: `sum`, `mean`, `min`, `max`, `l1_norm`, `l2_norm`), `axis` (enum: `all`, `per_channel`, default `all`). |
| Inputs | `input` (`MatrixPayload`). |
| Outputs | `out` (`MatrixPayload`, shape `(1, 1)` when `axis=all`, shape `(channels, 1)` when `per_channel`). |
| Behavior | Stateless; re-computes each pull. Norm modes operate on flattened data (L1 = sum(|x|), L2 = sqrt(sum(x^2))). |
| Validation | Reject empty frames; propagate metadata/topic from input. |

**Difference vs StatsNode**: reduce node emits a *single configured metric* per instance and is intended to be lightweight for inline logic paths. StatsNode (below) produces multiple aggregates simultaneously (multiple ports) and is better for instrumentation or when several metrics are needed together.

## 2. `CompareNode` (element-wise comparator)

Purpose: generate boolean masks by comparing two matrices (or a matrix vs constant) element-wise.

| Aspect | Details |
| --- | --- |
| Config | `operation` (enum: `eq`, `neq`, `lt`, `lte`, `gt`, `gte`), `epsilon` (float ≥ 0, default `1e-6`), `constant_rhs` (optional float). |
| Inputs | `lhs` (`MatrixPayload`), `rhs` (optional `MatrixPayload`). If `rhs` not connected, uses `constant_rhs`. |
| Outputs | `mask` (`BoolPayload`) with same shape as `lhs`. |
| Behavior | - Shapes must match when both inputs connected.  
- When `constant_rhs` is used, scalar value broadcasts to every element.  
- Outputs 1.0 where predicate true, else 0.0. |

## 3. `MatrixStatsNode` (multi-metric instrumentation)

Purpose: compute several aggregates in one node for monitoring, scripting, or control feedback. Complements `MatrixReduceNode` by avoiding repeated passes over the same frame.

| Aspect | Details |
| --- | --- |
| Config | Enable flags per metric (bool fields default true): `emit_sum`, `emit_mean`, `emit_min`, `emit_max`, `emit_l1_norm`, `emit_l2_norm`, `emit_variance`. Optionally `axis` (`all` vs `per_channel`). |
| Inputs | `input` (`MatrixPayload`). |
| Outputs | Port per enabled metric (e.g., `sum`, `mean`, …) each as `MatrixPayload` shaped like reduce output. |
| Behavior | - Single pass computes running stats to minimize allocations.  
- Variance uses population formula unless future requirement for sample variant.  
- Missing ports are not materialized. |

## 4. `SelectNode` update (Gate behavior)

User recall indicates an existing select-style node (numbered inputs + control). Action items:

1. **Discovery**: confirm whether a `SelectNode` already exists; if not, introduce one matching the described shape. 
2. **Semantics**:
   - Inputs: `input0`..`inputN` (all `MatrixPayload` or `ColorPayload`), `select` (`MatrixPayload` or `BoolPayload` but interpreted as integer index). 
   - Outputs: `out` matching whichever branch was selected. 
   - Control interpretation: first non-empty value from `select` is rounded to nearest valid index, clamped to `[0, N]`. 
3. **Gate use-case**: When only two branches are needed, continue to allow `GateNode` as alias/wrapper that wires `false_branch=input0`, `true_branch=input1`, `predicate` (bool). Internally this can re-use the select logic (0 or 1). 
4. **State**: stateless; emits `latest_selected_frame.with_payload(...)` to preserve metadata. 

This satisfies item #6 by letting boolean comparators drive branch selection without recreating a new gate concept.

## 5. Comparator epsilon handling (#7)

`CompareNode` covers epsilon-aware comparisons already, so no separate node is required. Implementation details:

- `eq`: `abs(lhs - rhs) <= epsilon`.
- `neq`: logical NOT of `eq`.
- `lt`: `lhs < rhs - epsilon`.
- `lte`: `lhs <= rhs + epsilon`.
- `gt`: `lhs > rhs + epsilon`.
- `gte`: `lhs >= rhs - epsilon`.
- `epsilon` defaults to `1e-6` but can be overridden in config; settable to `0` for exact comparisons when safe.

## Testing & validation

1. **Unit tests per node**
   - Shape handling (all/per-channel).
   - Edge cases: zeros, negative numbers, NaNs rejected.
   - Comparator epsilon tolerance (e.g., `lhs=1.0`, `rhs=1.0 + 5e-7`).
2. **Integration tests**
   - Graph wiring: reduce → compare → select to detect all-zero frames and gate an output. 
   - Stats node verifying simultaneous sum & variance outputs.
3. **Documentation updates**
   - `docs/api.md`: add node descriptions, config tables, example graphs.
   - `examples/logic_detection.py` (new) demonstrating zero-detection pipeline.

## Open questions

- Maximum number of inputs for `SelectNode` (default to 8?).
- Should `MatrixReduceNode` support rolling accumulation (stateful sum over time) later? Current plan keeps it stateless; deferred until a clear use-case arises.
- Need confirmation on whether `StatsNode` outputs should be `MatrixPayload` or `MatrixFrame`; proposal uses `MatrixPayload` for consistency.

Once these are resolved/approved, implementation work can begin under separate PR(s).
