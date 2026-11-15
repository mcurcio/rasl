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
uv run ruff check src tests                        # Python: unused or undefined names, import order, docstrings
```

The Python packages under `src/rasl/` are domains, and import each other in one direction:
`app` → `config` → `runtime` | `nodes` | `devices` → `graph` | `color` → `signal` → `units`
(packages joined by `|` do not import each other). `CONTRIBUTING.md` says what each owns. The order is
set in `pyproject.toml` under `[tool.importlinter]` and checked by `tests/test_import_layers.py`
(or `uv run lint-imports`). A new import that goes against it fails the tests: move the code, do
not add an exception. `tests/` mirrors the packages.

The Python runtime reads config files with [knobly](https://github.com/mcurcio/knobly) (`src/rasl/config/document.py`
is the one module that imports it). knobly comes from PyPI (`knobly>=1.1,<2` in `pyproject.toml`), so `uv sync` needs nothing beyond `uv`.

Every public Python module, class, method and function has a docstring (ruff checks it): say
what it does, its units and shapes, what it returns and raises. Do not restate the name.

CI (`.github/workflows/ci.yml`, owner 2026-11-15: "add ... GHA CI") runs on pull requests and on
pushes to `alpha`, `beta` and `main`: the Python checks above plus `uv run lint-imports` on Python
3.11 and 3.13, and `pnpm install`, `build`, `typecheck` and `test` in `js/`. It publishes nothing.
`pnpm lint` and `pnpm format:check` are not in CI because they fail today (`rasl-t57`).

`.github/workflows/image.yml` builds the Python runtime's container image (`Dockerfile`; its
entrypoint, `docker/entrypoint.sh`, drops from root to `PUID`:`PGID`, applies `UMASK`, and seeds
`/config/rasl.conf` with `docker/rasl.conf`, an empty graph, when the file is missing; its
`HEALTHCHECK` runs `docker/healthcheck.py` against `GET /health`) and smoke-tests it on pull
requests; on a push to `alpha` it pushes `ghcr.io/mcurcio/rasl:sha-<sha>`. The container's
variables are listed in `README.md` (Installation, Container).
That image is the only thing any workflow publishes. mcurcio/iac (`workloads/rasl`) deploys it
by tag and digest.

The release workflow is disabled (owner, 2026-10-21: "Disable the workflows").
`.github/workflows/build.yml` is stale (it expects npm at the repo root) and its `publish` job
runs `lerna publish` on push. Leave it disabled until `rasl-4v6` is resolved.

## Branches and worktrees

The three branches are release channels, and changes flow one way: `alpha` → `beta` → `main`
(owner, 2026-11-15: "alpha is the default branch and produces alpha prereleases. Alpha merges to
beta which produces beta prereleases. Then beta merges to main, which produces the stable mainline
releases. The CI release process and semantic releases should respect that.").

| Branch  | Role | Releases |
|---------|------|----------|
| `alpha` | The default branch on GitHub. All development happens here. | alpha prereleases (`-alpha.N`) |
| `beta`  | Takes merges from `alpha`. | beta prereleases (`-beta.N`) |
| `main`  | Takes merges from `beta`. Never base work on it or push code to it. | stable releases |

The release automation is not built yet (`rasl-4v6`): any CI release step and semantic versioning
must follow this channel model. Today a push to `alpha` publishes only the container image
(`ghcr.io/mcurcio/rasl:sha-<sha>`), and the old `build.yml` (`lerna publish`) stays disabled.

- **Fork every branch and worktree from `alpha`**, and target `alpha` with pull requests. The
  owner promotes `alpha` to `beta` and `beta` to `main`; agents never open pull requests against
  `beta` or `main`.
- **Every session works in its own worktree; the main checkout stays on `main`** (owner,
  2026-10-21: "the main checkout can sit on main, and new sessions should create worktrees").
  Never work, commit or switch branches in the main checkout.
- **The main checkout hosts the machine's beads database.** Every worktree's `bd` resolves to
  its `.beads/` (`bd where` shows it), so the worktrees on one machine share one local
  database. The tracked `.beads/` files are on `main` too (owner, 2026-10-21: "Push the beads
  to main"), so the main checkout has its settings. The beads themselves travel in
  `.beads/issues.jsonl` on each branch (Task tracking, below), not in that database.

## Code search: codegraph

The index (`.codegraph/codegraph.db`) is local to each checkout and never committed; only
`.codegraph/.gitignore` is tracked. In a new worktree run `codegraph index .` once (under a
second), then `codegraph sync .` after pulling. Use `codegraph explore "<symbols or question>"`
before grep or reading files.

## Task tracking: beads

All planned work is tracked in beads (`bd`). Agents manage beads themselves, without being
asked (owner, 2026-10-21: "I want to use beads, and want you to auto manage it").

The plan documents (`plans/`, `js/plans/`, `js/packages/config/plans/`, `design.md`) stay in
the repo as source material (owner, 2026-10-21: "don't delete the plans"). Their items were
converted to beads; each bead's notes cite its source section. Track new and changed work in
beads, not by editing the plans (owner, 2026-10-21: "so we can stop maintaining those files").

- **Before work:** `bd ready` to find work, `bd show <id>` for detail, `bd update <id> --claim`.
- **During work:** file a bead for every follow-up, bug or open question you find
  (`bd create`, with `--deps` for what blocks it); record decided rules in the bead's design
  field, not in a new file.
- **After work:** `bd close <id>` for finished work; update the rest.
- **Sync to GitHub** (owner, 2026-10-21: ".beads should be kept up to date on GitHub"):
  `.beads/issues.jsonl` is the shared copy of the beads, one per line, committed with the work
  so each PR shows the issue changes. The database `bd` reads is local to each machine, built
  from that file, and never pushed (owner, 2026-11-14: "make the change": cloud sessions can
  push only their own branch, so the database's own remote went stale).
  - **Start of a session:** `bd bootstrap; bd import .beads/issues.jsonl` builds or refreshes
    the local database. The import never overwrites a bead that is newer locally. Run it again
    after pulling or switching branches.
  - **After changing beads:** `bd export -o .beads/issues.jsonl`, and commit the file.
  - Hooks in `.claude/settings.json` do both for Claude: `SessionStart` imports and runs
    `bd prime` for workflow context; `Stop` exports after every turn. Other agents run the two
    commands themselves. Do not run `bd dolt push` or `bd dolt pull`.
  - Two branches that both change beads can conflict in `issues.jsonl`. Keep both sides' lines;
    for one bead changed on both, keep the line with the later `updated_at`.

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
