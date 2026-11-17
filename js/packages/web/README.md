# @rasl/web

The web UI of the Python runtime (`rasl`): the graph as the config files write it, live node health, and the
graph editor. It talks only to rasl's GraphQL API (`docs/web-api.md`).

- `pnpm build` type-checks and builds into `../../../src/rasl/app/ui/` (git-ignored), which `rasl` serves at `/`.
  The container image builds it (`Dockerfile`, web stage).
- `pnpm dev` serves it with hot reload, forwarding `/graphql` to a running rasl (`RASL_API`, default
  `http://127.0.0.1:8080`).
- `pnpm test` runs the unit tests (the staging model in `src/model.ts`).
- `pnpm e2e` runs the browser tests (`e2e/`, Playwright): it starts rasl (`uv run rasl`, so run `pnpm build`
  and `uv sync` first) on a copy of `e2e/fixture.conf` and edits it through the page. CI runs it as the
  "Web editor (browser)" job.

## Layout

| File              | What it does                                                                                                                                      |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/api.ts`      | The GraphQL calls and their types                                                                                                                 |
| `src/model.ts`    | Pure functions: queued edits laid over the saved graph (`stage`), queueing that cancels instead of reversing (`queue`), connect text from handles |
| `src/layout.ts`   | Automatic layout with ELK (loaded on first use)                                                                                                   |
| `src/app.tsx`     | The page: canvas, selection, queue, checks and save                                                                                               |
| `src/components/` | The node card, the add-node dialog, the inspector, the queue panel                                                                                |

The editor never changes the running graph: it sends edits (`previewEdits`, `applyEdits`), the server writes
the config files through knobly, and the watcher reloads them.
