# AGENTS.md

Instructions for every AI coding agent working in this repo (Claude Code, Codex, Windsurf and
others). This is the only agent instruction file: `CLAUDE.md` is a symlink to it, because
Claude Code reads `CLAUDE.md` and not `AGENTS.md`. Edit this file; `CLAUDE.md` follows.

## Repository layout

- `src/rasl/`, `tests/`: Python runtime (Python 3.11, `uv`; `pyproject.toml`).
- `js/`: pnpm workspace (`js/packages/*`: engine, config, color, lighting, server, ui, govee,
  lifx). Node version in `js/.nvmrc`. Style guide: `js/STYLE.md`.
- `v2/`: Rust experiment.
- `docs/`: reference documentation.

## Build and test

```bash
cd js && pnpm install && pnpm build && pnpm test   # JS: also pnpm lint, pnpm typecheck
uv run pytest                                      # Python (repo root)
```

CI is disabled (owner, 2026-10-21: "Disable the workflows"). `.github/workflows/build.yml`
is stale (it expects npm at the repo root) and its `publish` job runs `lerna publish` on
push. Run the checks above locally until `rasl-4v6` is resolved.

## Branches and worktrees

The three branches are release channels: the `publish` job in `.github/workflows/build.yml`
runs `lerna publish` on every push to them once `lint` and `test` pass (currently disabled).

| Branch  | Role | Publishes |
|---------|------|-----------|
| `alpha` | The working branch. All development happens here. | `-alpha` prereleases |
| `beta`  | Promotion target after `alpha`. Initial commit only so far. | `-beta` prereleases |
| `main`  | Stable releases. Holds only the beads files so far. Never base work on it or push code to it. | graduated stable versions |

- **Fork every branch and worktree from `alpha`**, and target `alpha` with pull requests.
  Tools that cut worktrees from the repository's default branch (`main`) give you an empty
  tree: re-point the new branch at `alpha` before starting (`git checkout -B <branch> alpha`
  on a branch with no commits of its own).
- **The main checkout stays on `main`** (owner, 2026-10-21: "there is no issue leaving the
  main checkout on main"). Never work, commit or switch branches in it; use a worktree.
- **It hosts the shared beads database.** Every worktree's `bd` resolves to the main
  checkout's `.beads/` (`bd where` shows it). The tracked `.beads/` files are on `main` too
  (owner, 2026-10-21: "Push the beads to main"), so the main checkout has its settings.

## Task tracking: beads

All planned work lives in beads (`bd`). There are no plan, roadmap or TODO files; do not
create them. Agents manage beads themselves, without being asked (owner, 2026-10-21: "I want
to use beads, and want you to auto manage it").

- **Before work:** `bd ready` to find work, `bd show <id>` for detail, `bd update <id> --claim`.
- **During work:** file a bead for every follow-up, bug or open question you find
  (`bd create`, with `--deps` for what blocks it); record decided rules in the bead's design
  field, not in a new file.
- **After work:** `bd close <id>` for finished work; update the rest.
- **Persist:** there is no beads sync remote. Run `bd export -o .beads/issues.jsonl` and
  commit that file with the work, so the issue list reaches GitHub through the PR.
- A `SessionStart` hook (`.claude/settings.json`) runs `bd prime` for workflow context.

## Landing work

1. Run the checks under "Build and test" for the packages you changed.
2. Update beads and commit `.beads/issues.jsonl` (see above).
3. Commit with Conventional Commits, push your branch, and open or update a pull request
   into `alpha`. The owner reviews and merges; do not merge it yourself.

## Collaboration preferences

- **Brainstorming cadence**
  - When we are ideating / brainstorming, keep responses concise and optimize for quick back-and-forth.

- **Opinions vs decisions**
  - Offer **opinions and options**.
  - Do not present choices as "decided" unless the owner explicitly asks you to decide.

- **Specificity & intent**
  - Ask targeted clarifying questions when requirements are ambiguous.
  - Do not guess intentions; when in doubt, present explicit assumptions and ask for confirmation.
  - If a request specifies *interfaces* (ports/config) but leaves *runtime semantics* underspecified (e.g., timing, edge cases, shape rules, default behaviors), **pause implementation** and ask for clarification rather than inventing defaults.

- **No implicit semantic changes**
  - Do not change node semantics, runtime semantics, config semantics, or payload contracts implicitly.
  - If a change might affect behavior (even if tests still pass), call it out **before** implementing and confirm it is wanted.

- **Breaking changes / renames**
  - Confirm renames and behavior changes with the owner before making them.
  - Do not add aliases, deprecated exports, migration messages, or compatibility shims unless explicitly asked.

- **Scope discipline**
  - Keep diffs minimal and tied to the request.
  - Avoid drive-by refactors unless asked; file a bead instead.

- **Config ergonomics**
  - When adding DSL/config sugar:
    - propose exact semantics (including edge cases)
    - avoid ambiguous behavior
    - confirm constraints (e.g., "only supported without slicing") up front

- **Change reporting**
  - After edits, summarize:
    - what changed
    - why
    - any behavior-impacting implications
    - what to run to validate
