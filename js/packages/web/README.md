# @rasl/web

The web UI of the Python runtime (`rasl`): the graph as the config files write it, live node health, and the
graph editor. It talks only to rasl's GraphQL API (`docs/web-api.md`).

- `pnpm build` type-checks and builds into `../../../src/rasl/app/ui/` (git-ignored), which `rasl` serves at `/`.
  The container image builds it (`Dockerfile`, web stage).
- `pnpm dev` serves it with hot reload, forwarding `/graphql` to a running rasl (`RASL_API`, default
  `http://127.0.0.1:8080`).
- `pnpm test` runs the unit tests (the staging model in `src/model.ts`, the palette's commands in `src/palette.ts`, `src/theme.test.ts`: `index.html`'s inline theme script, and `src/styles.test.ts`: `styles.css`
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
| `src/palette.ts`  | The add-node palette's commands: each node type, then each other name it is registered under                                                      |
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
its own. The tokens hold the light and dark themes and point React Flow's `--xy-*` variables at themselves.

The theme follows the system until the person chooses: the top bar's `ThemeSwitch` cycles system, light and dark,
and patchbay's `useTheme` keeps the choice in `localStorage` under `rasl-web/1/theme` (`src/theme.ts`) and writes it
to `data-theme` on `<html>`. `index.html` inlines patchbay's `themeScript` for that key, so a kept choice applies
before the first paint; `src/theme.test.ts` holds the inline script equal to what patchbay generates.

The page is built from patchbay's components (`@mcurcio/patchbay/primitives`, which loads its own stylesheet); the
editor's words, data and editing model stay its own, mapped onto their props:

| Part                                               | patchbay                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| -------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Top bar                                            | `Button` (Add node), `ThemeSwitch` (below), `Pill` (live / offline: whether the page receives rasl's live updates)                                                                                                                                                                                                                                                                                                                                                           |
| Banners (page and queued changes)                  | `Banner`: the load and reload errors and the files changed on disk or a refused change, a conflict, the files saved; an error is read at once (`alert`), the rest when the reader is free (`status`)                                                                                                                                                                                                                                                                         |
| Keys                                               | `useShortcuts`: Delete or Backspace queues removing the selection, Mod+Z drops the last queued change, Mod+K opens the add-node palette (Mod is ⌘ on Apple platforms, Ctrl elsewhere; the button shows it through `keyLabel`). All idle while the palette or the dialog is open; in a text field only Mod+K acts                                                                                                                                                             |
| Side column                                        | resizable from its left edge with `Splitter` (280 to 720 px, by pointer or arrow keys; not when narrow)                                                                                                                                                                                                                                                                                                                                                                      |
| Inspector (`components/inspector.tsx`)             | `Panel` titled by the node type or "Connection", `SectionTitle`, `KeyValue`, `TextInput`, `Button`                                                                                                                                                                                                                                                                                                                                                                           |
| Queued changes (`components/pending-panel.tsx`)    | `Panel`, `Button` (Check and Save show a spinner while their request is on its way), `IconButton`, and `DiffView` for what Save would write (a region named "What Save writes", a section per file that folds from its heading)                                                                                                                                                                                                                                              |
| Settings rows (`components/settings-editor.tsx`)   | a group per row named by its key: `TextInput` (code face; the new key's native datalist), `Button`, `IconButton`, and `RadioGroup` for where a value read from a `$variable` or `@use` argument is written                                                                                                                                                                                                                                                                   |
| Add-node palette (`app.tsx`, `palette.ts`)         | `CommandPalette`, the first step of adding a node: each node type with its summary as the hint, and under "Other names" each alias (the palette matches labels only, so an alias is its own entry; picking it picks its type). Letters match in order, best first, the matched ones marked. Centred from the button or Mod+K; at the pointer from a double-click on the canvas or a wire dropped on no port. Escape, Tab or a press outside close it and give the focus back |
| Add-node dialog (`components/add-node-dialog.tsx`) | `Dialog` for the picked type (Escape, its Close button or a press outside close it; focus stays inside and returns to what opened it), `Field` and `TextInput` for the new node's id, values and settings, `Button` for Back (to the palette) and Queue                                                                                                                                                                                                                      |
| Node card badges (`components/node-card.tsx`)      | `Badge` in the change tones (added, removed, renamed, changed), and muted for locked                                                                                                                                                                                                                                                                                                                                                                                         |
