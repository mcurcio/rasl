# RASL Migration Plan Prompt (Python → TypeScript)

You are a senior TypeScript engineer migrating RASL from a stable Python implementation to the existing TypeScript monorepo in `js/`. Move fast, keep diffs small, and keep the system working.

## 1. Repo facts (do not override)

1.1 Workspace is `js/` and uses `pnpm` workspaces.  
1.2 Node runtime target is `>=18`. Packages are ESM (`"type": "module"`).  
1.3 TypeScript config uses `NodeNext` / `ES2022` and `strict`.  
1.4 Tests use Vitest. Keep these green during work:

- `pnpm -C js test`
- `pnpm -C js typecheck`

## 2. Goals

2.1 No intentional semantic changes to RASL behavior/contracts.  
2.2 API adaptation is allowed for ecosystem differences (e.g., numpy → `ArrayBuffer`/`TypedArray`, async IO), but preserve meaning and observable behavior.  
2.3 Core packages (`@rasl/engine`, `@rasl/config`) must work in Node and browser; Node-only logic must be isolatable.  
2.4 The system is plugin-based: core APIs are `interface`s; packages provide concrete implementations with hooks/config so consumers can wrap/compose them.

## 3. Focus

3.1 Prioritize `@rasl/engine` and `@rasl/server`.  
3.2 Ensure that no Nodes or Payload subclasses are defined in the `@rasl/engine` or `@rasl/server` packages. All node and payload implementations should be in separate domain-centric packages.

## 4. Browser + Node packaging constraint

4.1 Users should have consistent imports for core usage without needing to append `/node` everywhere.  
4.2 If Node-only implementations exist, structure exports so core imports stay stable and browser builds can exclude Node-only code (conditional exports or separate entrypoints are OK; keep consumer ergonomics).

## 5. Numerics / buffers

5.1 Frame buffers may use `Float32Array`.  
5.2 Color conversions must remain visually stable after 40 conversions.  
5.3 Quantify “visually stable” using a standard metric and enforce it with tests. Prefer a perceptual metric (e.g., ΔE in OKLab/OKLCH) over raw channel deltas. Pick thresholds and justify briefly in the change summary.

## 6. Testing

6.1 Tests are written in TypeScript (Vitest). Do not rely on Python to generate fixtures.  
6.2 Every slice ships with tests; keep `pnpm -C js test` and `pnpm -C js typecheck` green.

## 7. Work style: do not block on questions

7.1 Do not stop to ask clarifying questions unless you are truly blocked.  
7.2 If you notice ambiguity or a potential semantic decision:

7.2.1 Pick the most conservative/least-surprising choice consistent with existing TS patterns and the repo’s stated architecture.  
7.2.2 Record it in a running log for later review (see section 8).  
7.2.3 Add tests that lock the behavior down.  
7.2.4 Keep going.

## 8. Running “Questions & Assumptions” log (required)

8.1 Maintain `js/plans/QuestionsAndAssumptions.md` with:

8.1.1 Unanswered questions.  
8.1.2 Assumptions made (with rationale).  
8.1.3 Potential behavior risks.  
8.1.4 Follow-ups / TODOs.

8.2 This log must not block implementation; it’s for after-the-fact review.

## 9. Execution loop

9.1 Choose a small vertical slice (engine/server).  
9.2 Implement with interface-first design + concrete implementations + hooks.  
9.3 Add tests (including color stability tests where relevant).  
9.4 Validate with `pnpm -C js test` and `pnpm -C js typecheck`.  
9.5 Summarize changes + update `js/plans/QuestionsAndAssumptions.md` + choose the next slice.
9.6 Repeat the loop until all functionality has been migrated.

## 10. First task

10.1 Scan the repo and propose 2–3 migration slices focused on `@rasl/engine` + `@rasl/server`.  
10.2 Start with the smallest slice immediately; only ask questions if blocked.

