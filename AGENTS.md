# AGENTS.md

Working agreement for collaborating with Cascade in this repo.

## Collaboration preferences

- **Brainstorming cadence**
  - When we are ideating / brainstorming, keep responses concise and optimize for quick back-and-forth.

- **Opinions vs decisions**
  - I will offer **opinions and options**.
  - I will not present choices as “decided” unless you explicitly ask me to decide.

- **Specificity & intent**
  - I will ask targeted clarifying questions when requirements are ambiguous.
  - I will avoid lingering or guessing your intentions; when in doubt, I will present explicit assumptions and ask you to confirm.
  - If a request specifies *interfaces* (ports/config) but leaves *runtime semantics* underspecified (e.g., timing, edge cases, shape rules, default behaviors), I will **pause implementation** and ask for clarification rather than inventing defaults.

- **No implicit semantic changes**
  - I will not change node semantics, runtime semantics, config semantics, or payload contracts “implicitly”.
  - If a change might affect behavior (even if tests still pass), I will call it out **before** implementing and confirm you want it.

- **Breaking changes / renames**
  - For renames or behavior changes, I will:
    - propose a migration strategy (aliases, deprecation period, tests/docs updates)
    - confirm with you before making it the default

- **Scope discipline**
  - I will keep diffs minimal and tied to the request.
  - I will avoid drive-by refactors unless you ask.

- **Config ergonomics**
  - When adding DSL/config sugar, I will:
    - propose exact semantics (including edge cases)
    - avoid ambiguous behavior
    - confirm constraints (e.g., “only supported without slicing”) up front

- **Change reporting**
  - After edits, I will summarize:
    - what changed
    - why
    - any behavior-impacting implications
    - what to run to validate

## TypeScript coding standards (js/)

- **Interface-first design**
  - Public APIs are defined by interfaces (e.g., `IGraph`, `IScheduler`, `IColorPayload`).
  - Concrete classes implement interfaces: `class Thing implements IThing`.
  - Engine functions accept/return interface types, not concrete classes.

- **Enum-like closed sets**
  - Use `as const` objects + union types instead of TypeScript `enum`.
  - Example:

    ```ts
    export const WaveShape = {
      Sine: 'sine',
      Triangle: 'triangle',
      Sawtooth: 'sawtooth',
      Square: 'square',
      AttackDecay: 'attack_decay',
    } as const;
    export type WaveShape = (typeof WaveShape)[keyof typeof WaveShape];
    ```

  - Exceptions: truly dynamic strings (node IDs, port names, payload domains).

- **Zero-copy buffer views**
  - Numeric payloads use `Float32Array` with contiguous `channels × components` layout.
  - Use `IBufferView` / `IMatrixView` for slicing without copies.
  - Payload buffers are immutable after emission.

- **Port access**
  - Use `PortGroup.get(name)` with `InputPort` / `OutputPort` type casts.
  - Avoid unsafe inline object-shape casts like `(this.inputs as { in: ... })`.

- **Imports**
  - Domain-specific payload types live in their domain package (e.g., `ColorPayload` in `@rasl/color`).
  - Engine exports base types (`FramePayload`, `MatrixPayload`, `BoolPayload`).

- **Project structure**
  - Monorepo uses pnpm workspaces + TypeScript project references.
  - Each package has `"composite": true` and declares `references` to dependencies.
  - Build/typecheck via `tsc -b tsconfig.build.json` at repo root.
