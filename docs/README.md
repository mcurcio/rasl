# rasl documentation

rasl is a real-time lighting engine. You describe a graph of nodes (sources, effects, color conversions and
outputs) in a config file, and the `rasl` command runs it, reloading when the file changes. The Python runtime in
`src/rasl/` is the product. This page says where each topic is documented.

## Where each topic is documented

Most of the user documentation is in the repository's [README](../README.md):

| Topic | Where |
|---|---|
| Installing from source, and the container image and its settings | [README: Installation](../README.md#installation), [Container](../README.md#container) |
| A first config, validated and run | [README: Quick start](../README.md#quick-start) |
| The config file: the `graph` block, `node`, `connect`, slices, the `ui` block | [README: Configuration](../README.md#configuration) |
| The config syntax itself (knobly: `@set`, `@snippet`, `@use`, `@include`) | [knobly language reference](https://mcurcio.github.io/knobly/language/) |
| The built-in node types | [README: Node types](../README.md#node-types) |
| Every node type's settings, with types, defaults and sink examples | [nodes.md](nodes.md) |
| Writing a node type of your own, and registering it | [writing-nodes.md](writing-nodes.md) |
| The `rasl` command and its flags | [README: Command line](../README.md#command-line) |
| The dashboard, GraphQL at `/graphql` and `GET /health` | [README: Web UI and API](../README.md#web-ui-and-api), and the full reference in [web-api.md](web-api.md) |
| What a config change does to a running graph | [README: Live reload](../README.md#live-reload) |
| The repository layout, the checks, building the image, branches and releases | [CONTRIBUTING.md](../CONTRIBUTING.md) |
| Reporting a vulnerability, and what to know before exposing rasl on a network | [SECURITY.md](../SECURITY.md) |

The docstrings in `src/rasl/` are the detailed reference for the code: every public module, class and function
has one. For writing a config, use [nodes.md](nodes.md): several node docstrings
have no example yet.

The JavaScript workspace in `js/` is a separate implementation with its own documentation:
[js/README.md](../js/README.md) and the README in each `js/packages/*` folder.
