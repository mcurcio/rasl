<!-- Open pull requests against `alpha`. Commit messages follow Conventional Commits. -->

## What changed

<!-- The change, in a few short points. -->

## Why

<!-- The problem it solves, or the issue it closes. -->

## Behaviour impact

<!--
Does this change how a node, a config directive, the runtime, the web API or the container behaves,
even if the tests still pass? Say what changes for someone with an existing config, or write "None".
Renames and changes of behaviour are agreed in an issue first.
-->

## How to validate

<!-- The checks you ran, and how a reviewer can see the change working. Delete the lines that do not apply. -->

- [ ] `uv run ruff check src tests`
- [ ] `uv run lint-imports`
- [ ] `uv run pytest`
- [ ] `pnpm build && pnpm typecheck && pnpm test` in `js/`
- [ ] `uv run rasl --validate <config>` on the configs this touches
