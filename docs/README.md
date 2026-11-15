# rasl documentation

rasl is a real-time lighting engine. You describe a graph of nodes (sources, effects, color conversions and
outputs) in a config file, and the `rasl` command runs it, reloading when the file changes. The Python runtime in
`src/rasl/` is the product. This page says where each topic is documented, and which pages in this folder are
current.

## Current documentation

The current user documentation is in the repository's [README](../README.md):

| Topic | Where |
|---|---|
| Installing from source, and the container image and its settings | [README: Installation](../README.md#installation), [Container](../README.md#container) |
| A first config, validated and run | [README: Quick start](../README.md#quick-start) |
| The config file: the `graph` block, `node`, `connect`, slices, the `ui` block | [README: Configuration](../README.md#configuration) |
| The config syntax itself (knobly: `@set`, `@snippet`, `@use`, `@include`) | [knobly language reference](https://mcurcio.github.io/knobly/language/) |
| The built-in node types | [README: Node types](../README.md#node-types) |
| Every node type's settings, with types, defaults and sink examples | [nodes.md](nodes.md) |
| The `rasl` command and its flags | [README: Command line](../README.md#command-line) |
| The dashboard, GraphQL at `/graphql` and `GET /health` | [README: Web UI and API](../README.md#web-ui-and-api) |
| What a config change does to a running graph | [README: Live reload](../README.md#live-reload) |
| The repository layout, the checks, writing a node, building the image | [CONTRIBUTING.md](../CONTRIBUTING.md) |
| Reporting a vulnerability, and what to know before exposing rasl on a network | [SECURITY.md](../SECURITY.md) |

The docstrings in `src/rasl/` are the detailed reference for the code: every public module, class and function
has one. Each node's docstrings describe its settings, but for writing a config use [nodes.md](nodes.md):
several node docstrings have no example, and the examples that exist still wrap the nodes in an old `rasl { }`
root block, which rasl no longer reads (it needs `graph { }`).

The JavaScript workspace in `js/` is a separate implementation with its own documentation:
[js/README.md](../js/README.md) and the README in each `js/packages/*` folder.

## Historical design documents

The pages below describe an early design of rasl, from September 2025, under the name "Real-Time Animation Show
Library". That design was not built as written: it has graphs written as Python scripts, a `rasl run` command,
a REST and WebSocket API, execution modes, a liveness model, mixins, plugins and an export system, none of which
exist in the code. Each page says so at the top. They stay here as source material for design history. Do not
use them to learn how rasl works today.

| Page | What it describes | What exists instead |
|---|---|---|
| [overview.md](overview.md) | The early concept: Python-script graphs, execution modes, REST/WebSocket | Config files with a `graph` block, run with `rasl <file>` |
| [architecture.md](architecture.md) | The early system components | The packages listed in [CONTRIBUTING.md](../CONTRIBUTING.md#the-python-packages) |
| [user-guide.md](user-guide.md) | `pip install rasl`, Python scripts, `rasl run`, `rasl export` | The README; rasl is installed from source or run as a container, not from PyPI |
| [api.md](api.md) | An interface spec: Frame, Schema, Engine, an HTTP façade, mixins | `BaseNode`, `@node`, ports and payloads (see [CONTRIBUTING.md](../CONTRIBUTING.md#writing-a-node)) |
| [graph.md](graph.md) | Wiring port objects in Python (`>>`), an `Engine`, end-of-stream policies | Graphs built from config by `GraphBuilder`, with `connect` directives |
| [execution-engine.md](execution-engine.md) | A `rasl.core` engine, validator and schedulers | `rasl.runtime`: `Runtime`, `Scheduler`, `Executor`, `NodeHost` |
| [time-and-liveness.md](time-and-liveness.md) | Liveness types, execution modes, time-domain bridging | The scheduler's tick; sinks with `@pull_rate` set the rate |
| [node-development.md](node-development.md) | `BaseSource`/`BaseTransform`/`BaseSink`, mixins, `param_spec` | [CONTRIBUTING.md: Writing a node](../CONTRIBUTING.md#writing-a-node) |
| [plugin-system.md](plugin-system.md) | A plugin manager with node, format, protocol and UI plugins | The `rasl.nodes` entry-point group, for nodes only |
| [web-api.md](web-api.md) | A REST API under `/api/v1/` and WebSocket topics | `GET /health`, GraphQL at `/graphql`, the dashboard at `/` |
| [export-system.md](export-system.md) | Offline rendering to FSEQ, CSV and JSON | Nothing: there is no export feature |

## Other files

- [test_output.md](test_output.md) and `ddp_diag_run.txt` are notes and a raw log from one DDP debugging session
  in December 2025. They are not documentation.
- `assets/` holds the logo, drawn by `tools/logo.py`.
