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

- **No aliases / deprecations / migration shims**
  - I will not introduce aliases, deprecated exports, migration messages, or compatibility shims unless you explicitly ask.

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
