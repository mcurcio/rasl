# Contributing to rasl

Thanks for helping. This page explains how the repository is laid out, how to set up a checkout, which checks
must pass, and how a change lands. If you are an AI coding agent, read [AGENTS.md](AGENTS.md) first; it adds the
rules agents follow on top of this page.

## Reporting a bug or asking for something

Open an [issue](https://github.com/mcurcio/rasl/issues). For a bug, include:

- the version (`uv run rasl --version`) or the container image tag;
- how you run rasl (from a checkout with uv, or the container);
- the smallest config that shows the problem;
- the full error, including the `file:line:col` location when there is one;
- what you expected, and what happened instead.

Report a security problem privately, not in an issue: see [SECURITY.md](SECURITY.md).

## Layout

| Path | What it is |
|---|---|
| `src/rasl/` | The Python runtime: the `rasl` command, the engine, the nodes, the web UI and API. This is the product |
| `tests/` | The Python tests. Its folders mirror the packages in `src/rasl/` |
| `docker/`, `Dockerfile` | The container image: entrypoint, health check, and the starter config it seeds |
| `js/` | A JavaScript/TypeScript implementation as a pnpm workspace ([js/README.md](js/README.md)) |
| `v2/` | A Rust experiment |
| `docs/` | Reference documentation ([docs/README.md](docs/README.md) says which pages are current) |
| `plans/`, `design.md`, `js/plans/`, `js/packages/config/plans/` | Design history, kept as source material. Planned work is tracked in issues, not by editing these files |
| `virtual.conf`, `hyperhdr.conf`, `family_room.conf` | Sample configs from real setups. `virtual.conf` is the one the image smoke test uses. `family_room.conf` does not validate today |
| `tools/logo.py` | Draws the logo in `docs/assets/`. Change the script and rerun it; do not edit the SVGs |
| `.beads/` | The issue tracker the maintainers' agents use (`bd`); `issues.jsonl` is its shared copy |

### The Python packages

The packages under `src/rasl/` are domains:

| Package | What it owns |
|---|---|
| `units` | `Duration` and `Frequency`, the typed quantities in node config |
| `signal` | What flows between nodes: `Frame`, matrix and bool payloads, the payload registry |
| `color` | Color models, conversions and color payloads |
| `graph` | The topology and the node contract: `BaseNode` and its config bases, ports, edges, slices, `GraphBuilder`, `ExecutionPlan` |
| `runtime` | Running a plan: `Runtime`, `Scheduler`, `Executor`, `NodeHost`, diagnostics, timing, plan updates |
| `nodes` | The built-in nodes: effects, color, debug, literal |
| `devices` | One package per protocol: `sacn`, `ddp`, `lifx`, `govee` |
| `config` | The config language on top of [knobly](https://github.com/mcurcio/knobly): node and connect directives, building the graph, reload and the file watcher |
| `app` | The `rasl` command, the web server (GraphQL and `GET /health`) and the dashboard files |

They import each other in one direction only. A package may import only from the packages on the lines below
its own, and packages on the same line may not import each other:

```text
app
config
runtime | nodes | devices
graph | color
signal
units
```

The config language also reaches nodes only through the node registry: `config` may not import `nodes` or
`devices`. Both rules are set in `pyproject.toml` under `[tool.importlinter]` and checked by `uv run lint-imports`
(and by `tests/test_import_layers.py`). An import that breaks them fails the checks. Move the code instead of
adding an exception.

Only `src/rasl/config/document.py` imports knobly.

## Setting up

The Python runtime needs Python 3.11 or later and [uv](https://docs.astral.sh/uv/). From the repository root:

```bash
uv sync
```

This creates `.venv/` with rasl, its dependencies and the `dev` group (pytest, ruff, import-linter). uv installs
the `dev` group by default, so no flag is needed. Run the command through uv (`uv run rasl ...`), or activate
`.venv` first.

The JavaScript workspace needs the Node version in `js/.nvmrc` (24) and pnpm 8.12.0, the version in
`packageManager` in `js/package.json`:

```bash
cd js && pnpm install
```

You only need it if you change something in `js/`.

## Checks

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs on every pull request and on pushes to `alpha`,
`beta` and `main`. It runs these steps, and all of them must pass. Run the ones for the parts you changed before
you open a pull request.

Python, on Python 3.11 and 3.13, from the repository root:

```bash
uv sync --locked              # install exactly what uv.lock pins
uv run ruff check src tests   # unused and undefined names, import order, docstrings
uv run lint-imports           # the import direction above
uv run pytest                 # the tests
```

JavaScript, in `js/`:

```bash
pnpm install --frozen-lockfile
pnpm build
pnpm typecheck
pnpm test
```

`pnpm lint` and `pnpm format:check` also exist, but they fail on `alpha` today, so CI does not run them yet.

The image workflow ([`.github/workflows/image.yml`](.github/workflows/image.yml)) also runs on a pull request that
changes the `Dockerfile`, `.dockerignore`, `docker/`, `pyproject.toml`, `uv.lock`, `src/` or the workflow itself.
It builds the image and smoke-tests it (see [The container image](#the-container-image)).

## Docstrings

Every public Python module, class, method and function has a docstring; `uv run ruff check src tests` fails
without one (rules D100 to D104 and D106 in `pyproject.toml`). Tests are exempt: a test's name says what it
checks.

Say what the code does, in which units and shapes, what it returns and what it raises. Do not restate the name.
The built-in nodes are good examples: see `src/rasl/nodes/effects/smooth.py`.

## Writing a node

A node is a class that subclasses `BaseNode` and registers itself with the `@node` decorator. It declares:

- a nested `Config` class, a pydantic model based on `SourceNodeConfig`, `TransformNodeConfig` or
  `SinkNodeConfig`. Each field is one directive in the node's block in a config file. Unknown directives are
  refused;
- its ports, as `PortGroup.inputs(...)` and `PortGroup.outputs(...)` class attributes;
- an `async def pull(self, tick)` that reads its inputs and writes its outputs. `start(ctx)` and `stop(ctx)` are
  optional, for opening and closing connections.

A sink that should drive the schedule marks its `pull` with `@pull_rate(hz)`, where `hz` is a number or a
function of the node. Only such sinks make ticks happen: a node that is not upstream of one never runs.

A minimal transform:

```python
"""Example nodes for a rasl plugin package."""

from pydantic import Field

from rasl.graph.node import BaseNode, TickContext, TransformNodeConfig, node
from rasl.graph.ports import InputPortSpec, OutputPortSpec, PortGroup
from rasl.signal import MatrixPayload


@node("InvertNode", "Invert")
class InvertNode(BaseNode):
    """Write ``amount - x`` for every value of the input matrix."""

    class Config(TransformNodeConfig):
        """Configuration for InvertNode."""

        amount: float = Field(1.0, description="The value each input is subtracted from")

    inputs = PortGroup.inputs(input=InputPortSpec(MatrixPayload))
    outputs = PortGroup.outputs(out=OutputPortSpec(MatrixPayload))

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._amount = config.amount

    async def pull(self, tick: TickContext) -> None:
        """Write the inverted input to ``out``; write nothing when there is no input."""
        frame = self.inputs.input.read()
        if frame is None:
            return
        data = self._amount - frame.payload.data
        self.outputs.out.write(frame.with_payload(MatrixPayload(data)))
```

Once it is registered, a config can use it by either name:

```knobly
graph {
    node Waveform wave { output_channels 4; frequency_hz 0.1; }
    node Invert inv { amount 1; connect wave; }
    node ConsoleSink console { fps 2; connect inv; }
}
```

rasl finds nodes through the `rasl.nodes` entry-point group. Each entry names a module that registers its nodes
when it is imported. The built-in nodes use it too (`pyproject.toml`):

```toml
[project.entry-points."rasl.nodes"]
builtin = "rasl.nodes"
devices = "rasl.devices"
```

- **A built-in node** goes in `src/rasl/nodes/` (or a protocol package in `src/rasl/devices/`). Import its module
  in that package's `__init__.py` so it registers, and add tests under `tests/nodes/` or `tests/devices/`.
- **A node in your own package** needs only an entry of its own in that package's `pyproject.toml`, for example
  `my_nodes = "my_package.nodes"`. Once the package is installed in the same environment as rasl, its nodes are
  available.

A node that can take new settings while running, without a restart, implements `update_config(config)`; a
config reload then calls it instead of restarting the node. `SmoothNode` does this to keep its state.

## The container image

The image is built from the `Dockerfile` on `python:3.11-slim-bookworm`. The image workflow pushes it to
`ghcr.io/mcurcio/rasl`, tagged `sha-<commit>`, on a push to `alpha`. It is the only thing any workflow publishes:
rasl is not on PyPI.

To build it and run a short version of the workflow's smoke test locally:

```bash
docker build -t rasl:smoke .
docker run -d --name smoke -p 8080:8080 -v "$PWD/virtual.conf:/config/rasl.conf:ro" \
    rasl:smoke /config/rasl.conf --api-host 0.0.0.0 --api-port 8080
curl -fsS http://127.0.0.1:8080/health
curl -fsS -H 'content-type: application/json' -d '{"query":"{health{status}}"}' \
    http://127.0.0.1:8080/graphql
docker rm -f smoke
```

`/health` should answer with `"status":"ok"`. The full smoke test, in `image.yml`, also checks that rasl runs as
the default user 1000 and not as root, that an empty volume is seeded with a starter config owned by `PUID` and
`PGID`, and that the image runs as another user with a read-only root and no capabilities.

The container's settings (`PUID`, `PGID`, `UMASK`, `TZ`, `RASL_PORT`) are described in
[README.md](README.md#container).

## Branches

| Branch | Role |
|---|---|
| `alpha` | The working branch. All development happens here |
| `beta` | Reserved for promotion after `alpha`. Not in use yet |
| `main` | Reserved for stable releases. Not in use yet: never base work on it |

Fork your branch from `alpha`, and open your pull request against `alpha`. The owner reviews and merges it.

There are no versioned releases yet. The release workflow (`.github/workflows/build.yml`) is disabled.

## Commits and pull requests

- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`,
  `ci:`, `chore:`, with an optional scope (`fix(color): ...`) and `!` for a breaking change (`feat(color)!: ...`).
- Keep a pull request to one change. File an issue for anything else you notice.
- Say in the pull request if the change alters how a node, a config directive, the runtime or an API behaves,
  even when the tests still pass. Renames and changes of behaviour are agreed with the owner first, in an issue:
  rasl does not keep old names or compatibility paths.
- The [pull request template](.github/pull_request_template.md) asks what changed, why, the impact on behaviour,
  and how to check it.

## Design history

The design documents in `plans/`, `design.md`, `js/plans/` and `js/packages/config/plans/` record earlier
decisions. They stay in the repository as source material, but they are not kept up to date: planned work is
tracked as issues. Several pages in `docs/` describe an early design that was never built; each one says so at
the top, and [docs/README.md](docs/README.md) lists them.

## License

rasl is released under the [MIT License](LICENSE). By contributing, you agree that your contributions are licensed under it.
