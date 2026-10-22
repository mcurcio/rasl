# AGENTS.md

Working agreement for collaborating with Cascade in this repo.

## Branches and worktrees

The three branches are release channels: the `publish` job in `.github/workflows/build.yml`
runs `lerna publish` on every push to them, once `lint` and `test` pass.

| Branch  | Role | Publishes |
|---------|------|-----------|
| `alpha` | The working branch. All development happens here. | `-alpha` prereleases |
| `beta`  | Promotion target after `alpha`. Initial commit only so far. | `-beta` prereleases |
| `main`  | Stable releases. Initial commit only so far. Never base work on it or push to it. | graduated stable versions |

- **Fork every branch and worktree from `alpha`**, and target `alpha` with pull requests.
  Tools that cut worktrees from the repository's default branch (`main`) give you an empty
  tree: re-point the new branch at `alpha` before starting (`git checkout -B <branch> alpha`
  on a branch with no commits of its own).
- **The main checkout stays on `main`** (owner, 2026-10-21: "there is no issue leaving the
  main checkout on main"). Never work, commit or switch branches in it; use a worktree.
- **It still hosts the shared beads database.** Every worktree's `bd` resolves to the main
  checkout's `.beads/` (`bd where` shows it). Because `main` has no `.beads/` files, that
  folder holds untracked copies of `alpha`'s tracked `.beads/` files. When those change on
  `alpha`, copy them over again (`git ls-files .beads` lists them).

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

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:7510c1e2 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->
