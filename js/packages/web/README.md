# @rasl/web

The web UI of the Python runtime (`rasl`): the graph as the config files write it, live node health, and the
graph editor. It talks only to rasl's GraphQL API (`docs/web-api.md`).

- `pnpm build` type-checks and builds into `../../../src/rasl/app/ui/` (git-ignored), which `rasl` serves at `/`.
  The container image builds it (`Dockerfile`, web stage).
- `pnpm dev` serves it with hot reload, forwarding `/graphql` to a running rasl (`RASL_API`, default
  `http://127.0.0.1:8080`).
- `pnpm test` runs the unit tests (the staging model in `src/model.ts`, and `src/styles.test.ts`: `styles.css`
  reads only tokens that patchbay defines).
- `pnpm e2e` runs the browser tests (`e2e/`, Playwright): it starts rasl (`uv run rasl`, so run `pnpm build`
  and `uv sync` first) on a copy of `e2e/fixture.conf` and edits it through the page. CI runs it as the
  "Web editor (browser)" job. The tests find things by role, accessible name or data attribute where patchbay
  draws them (its classes are not the editor's to rely on).

## Layout

| File              | What it does                                                                                                                                      |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/api.ts`      | The GraphQL calls and their types                                                                                                                 |
| `src/model.ts`    | Pure functions: queued edits laid over the saved graph (`stage`), queueing that cancels instead of reversing (`queue`), connect text from handles |
| `src/layout.ts`   | Automatic layout with ELK (loaded on first use)                                                                                                   |
| `src/app.tsx`     | The page: canvas, selection, queue, checks and save                                                                                               |
| `src/styles.css`  | The page's rules, drawn with patchbay's tokens                                                                                                    |
| `src/components/` | The node card, the add-node dialog, the inspector, the queue panel                                                                                |

The editor never changes the running graph: it sends edits (`previewEdits`, `applyEdits`), the server writes
the config files through knobly, and the watcher reloads them.

## Look

The page draws with [patchbay](https://github.com/mcurcio/patchbay)'s design tokens (`@mcurcio/patchbay`, pinned
exactly) in its base look, with no rasl brand. `src/main.tsx` loads React Flow's stylesheet, then
`@mcurcio/patchbay/tokens.css`, then `src/styles.css`, which reads only `--pb-*` tokens and defines no variables of
its own. The tokens hold the light and dark themes, follow the system's choice, and point React Flow's `--xy-*`
variables at themselves.

The page is built from patchbay's components (`@mcurcio/patchbay/primitives`, which loads its own stylesheet); the
editor's words, data and editing model stay its own, mapped onto their props:

| Part                                               | patchbay                                                                                                                                                                                                           |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Top bar                                            | `Button` (Add node), `Pill` (live / offline: whether the page receives rasl's live updates)                                                                                                                        |
| Side column                                        | resizable from its left edge with `Splitter` (280 to 720 px, by pointer or arrow keys; not when narrow)                                                                                                            |
| Inspector (`components/inspector.tsx`)             | `Panel` titled by the node type or "Connection", `SectionTitle`, `KeyValue`, `TextInput`, `Button`                                                                                                                 |
| Queued changes (`components/pending-panel.tsx`)    | `Panel`, `Button` (Check and Save show a spinner while their request is on its way), `IconButton`                                                                                                                  |
| Settings rows (`components/settings-editor.tsx`)   | a group per row named by its key: `TextInput` (code face; the new key's native datalist), `Button`, `IconButton`, and `RadioGroup` for where a value read from a `$variable` or `@use` argument is written         |
| Add-node dialog (`components/add-node-dialog.tsx`) | `Dialog` (Escape, its Close button or a press outside close it; focus stays inside and returns to what opened it), `Field` and `TextInput` for the new node's id, values and settings, `Button` for Back and Queue |
| Node card badges (`components/node-card.tsx`)      | `Badge` in the change tones (added, removed, renamed, changed), and muted for locked                                                                                                                               |
