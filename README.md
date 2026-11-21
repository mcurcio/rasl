<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/logo-dark.svg">
    <img alt="rasl" src="docs/assets/logo.svg" width="378">
  </picture>
</p>

<p align="center">
  <b>Real-time Async Streaming for Lighting: describe a graph of effects, color and outputs in a config file, and rasl runs it.</b>
</p>

<p align="center">
  <a href="https://github.com/mcurcio/rasl/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/mcurcio/rasl/actions/workflows/ci.yml/badge.svg?branch=alpha"></a>
  <a href="https://github.com/mcurcio/rasl/actions/workflows/image.yml"><img alt="Container image" src="https://github.com/mcurcio/rasl/actions/workflows/image.yml/badge.svg?branch=alpha"></a>
</p>

---

rasl is a lighting engine. You write a graph of nodes in a config file: sources that make or receive
values, transforms that shape them, and sinks that send them to lights over sACN (E1.31), DDP, LIFX or
Govee. rasl runs the graph at the rate the sinks ask for, serves a web dashboard while it runs, and
applies your edits to the config without a restart.

**Status.** rasl is early (0.x): releases come from the `alpha`, `beta` and `main` channels as container images
(see [Container](#container)). It is not published to PyPI.
Install it from a checkout with [uv](https://docs.astral.sh/uv/), or run the container image. The Python
runtime in `src/rasl/` is the product. `js/` (a pnpm workspace, see [js/README.md](js/README.md)) and `v2/`
(a Rust experiment) are other implementations, not needed to run rasl.

## Features

- **Config-driven graphs.** Nodes and their connections live in a [knobly](https://github.com/mcurcio/knobly)
  file, with variables, snippets and includes. Errors point at the file, line and column.
- **21 built-in node types.** Waveforms, random fields, cron schedules, constants, color models and
  color correction, math, smoothing, crossfades and a twinkle effect.
- **Outputs and inputs.** Send over sACN, DDP, LIFX and the Govee LAN API; receive sACN; print frames to the
  terminal for testing.
- **Live reload.** Save the config and only the nodes you changed restart. A broken edit is never applied.
- **Web UI and API.** A graph editor at `/`: wire ports and add or remove nodes, and the changes are written
  to the config file (comments kept) when you save. A GraphQL API at `/graphql`, and `GET /health` for monitors.
- **Container image.** `ghcr.io/mcurcio/rasl`, with a health check, a seeded starter config and
  `PUID`/`PGID` support.
- **Pluggable nodes.** Other packages can add node types through the `rasl.nodes` entry-point group, the
  same way the built-in nodes register.

## Installation

### From source

rasl needs Python 3.11 or later and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/mcurcio/rasl.git
cd rasl
uv sync
uv run rasl --version      # rasl 0.1.0
```

`uv sync` puts the `rasl` command in `.venv/`. Run it with `uv run rasl`, or activate the environment
(`source .venv/bin/activate`) and run `rasl`.

Loading a config prints two `ColourUsageWarning` warnings from colour-science about SciPy and Matplotlib not
being installed. They are harmless.

### Container

The image is published to `ghcr.io/mcurcio/rasl`, a public package. `latest` is the newest stable release, and
each release also has its version tag (`0.2.0`, or `0.2.0-alpha.1` for a prerelease). `alpha` and `beta` follow
the prerelease channels, and every build of `alpha` is also tagged `sha-<commit>`. The
[package page](https://github.com/mcurcio/rasl/pkgs/container/rasl) and the
[releases](https://github.com/mcurcio/rasl/releases) list them:

```bash
docker run -p 8080:8080 -p 5568:5568/udp -v "$PWD/rasl-config:/config" \
    -e PUID=1000 -e PGID=1000 -e TZ=America/New_York ghcr.io/mcurcio/rasl:latest
```

The config is `/config/rasl.conf` in the `/config` volume, here the `rasl-config` folder in the current
directory. If it does not exist when the container starts, the image writes a starter config there (an
empty graph) and never overwrites it after that. The web UI is on port 8080. Edit the file and rasl
reloads it.

sACN input arrives on 5568/udp. `SacnUniverse` takes both unicast and multicast: it joins each received
universe's multicast group. In a container, multicast needs `--network host`, because Docker's default
bridge network does not forward it; where the join fails, rasl logs a warning and receives unicast only.

| Variable | Default | What it does |
|---|---|---|
| `PUID`, `PGID` | `1000` | The user and group rasl runs as. The container starts as root, gives `/config` and everything in it to them, and drops to them before rasl starts. |
| `UMASK` | `022` | The umask for files rasl and the seed create (`002` makes them group-writable). |
| `TZ` | UTC | The time zone, e.g. `America/New_York`. |
| `RASL_PORT` | `8080` | The web UI and API port of the default command and the health check. |

Started as another user instead (`docker run --user`, Kubernetes `runAsUser`), it runs as that user,
ignores `PUID`/`PGID` and changes no owners; the volume must then be writable by that user. Started
as root, it needs Docker's default capabilities (`CHOWN`, `SETUID`, `SETGID`): with `--cap-drop ALL`
it cannot switch users and exits.

The image's `HEALTHCHECK` asks `GET /health`. That answers 503 (unhealthy) when the graph has
rate-driving sinks but has stopped ticking, and 200 when it is `ok` or `degraded` (the last config
reload failed and the previous graph still runs). The GraphQL `health` field reports the same.

The default command is `rasl /config/rasl.conf --api-host 0.0.0.0 --api-port $RASL_PORT`. Arguments
replace it and go to `rasl`, e.g. `--validate /config/rasl.conf`.

## Quick start

This graph needs no lights. A waveform sweeps the hue, a color node turns it into RGB, and a console
sink prints one frame a second. All 150 pixels show the same color, which goes once round the hue
circle every 10 seconds.

Save it as `rainbow.conf`:

```nginx
graph {
    node Waveform hue {
        shape sawtooth;
        frequency_hz 0.1;
        output_channels 150;
    }

    node Compose hsl {
        ports { hue; saturation; lightness; }
        output_type color:okhsl;
        connect hue hue;
        fill saturation 1;
        fill lightness 0.5;
    }

    node Color rgb rgb { connect hsl; }

    node ConsoleSink console {
        fps 1;
        connect rgb;
    }
}
```

Check it, then run it with the dashboard:

```bash
uv run rasl --validate rainbow.conf
# Config valid: 4 nodes, order: ('hue', 'hsl', 'rgb', 'console')

uv run rasl rainbow.conf --api-port 8080
# Dashboard: http://127.0.0.1:8080/
```

Open http://127.0.0.1:8080/ to see the graph. Press Ctrl+C to stop.

To drive real lights, swap the sink. This graph receives sACN universe 1 (by multicast or unicast) and
sends it on to a controller as universe 0.

```nginx
graph {
    node SacnUniverse input {
        universe 1;
    }

    node SacnSink output {
        target_host "10.0.60.30";
        target_universe 0;
        connect input;
    }
}
```

## Configuration

Config files are written in [knobly](https://github.com/mcurcio/knobly): directives ended by `;`, blocks in
`{ }`, `#` comments. Its [language reference](https://mcurcio.github.io/knobly/language/) has the whole
syntax. rasl reads these directives:

- **`graph { ... }`** holds the nodes. It is required. Other top-level blocks are ignored, except `ui`.
- **`node <Type> <id> { ... }`** declares a node. Each directive in its block sets one field of the node's
  settings: a repeated directive becomes a list, a bare directive means `true`, and a nested block becomes a
  map. An unknown field is an error. `node <id> { type <Type>; ... }` also works.
- **`connect <source> [<port>];`**, inside the node that receives, wires an input. The source is a node,
  optionally with an output port and a slice: `hue`, `input.universe_1`, `pixels[0~150]`,
  `input.channels[0~150]`. The port is the receiving node's input port; leave it out when the node has only
  one input.
- **`ui { host "127.0.0.1"; port 8080; }`**, at the top level, starts the web server without `--api-port`.
- **`runtime { max_consecutive_errors 10; }`**, at the top level: a node whose pull fails this many times in a
  row is disabled (no longer pulled) until a config reload changes it or rasl restarts. The default is 10, and
  0 means never. A node's own `max_consecutive_errors` setting overrides it.

A larger example, with a variable, a snippet and a slice:

```nginx
@set $pixels 150;
@set $leds_host "10.0.60.30";

@snippet twinkle $source {            # a reusable block
    mode brightness;
    connect $source;
}

graph {
    node Waveform hue { shape sawtooth; frequency_hz 0.1; output_channels 450; }
    node Compose hsl {
        ports { hue; saturation; lightness; }
        output_type color:okhsl;
        connect hue hue;
        fill saturation 1;
        fill lightness 0.5;
    }
    node Color rgb rgb { connect hsl; }
    node TwinkleEffect sparkle { @use twinkle rgb; }
    node DdpSink leds {
        target $leds_host;
        max_count $pixels;
        connect sparkle[0~450];       # a slice: bounds separated by ~
    }
    # @include "more_sinks.conf";     # another file's directives, spliced in here
}
```

Settings typed as a frequency or a duration take units: a frequency is a number, `20hz` or `30fps`; a
duration needs a unit, such as `50ms`, `2s` or `1.5min`. Settings whose name ends in `_ms` or `_s`, and
`Crossfade`'s `seconds`, take a plain number in that unit.

**Only nodes that feed a sink run.** The sinks set the tick rate. A node that no sink pulls from never runs,
and `--validate` warns about it.

A problem in a config is reported with its file, line and column, the source line and a caret:

```text
Error loading config: bad.conf:2:5: rasl/connect: Node 'rgb': Unknown source node 'hsl'
    node Color rgb rgb { connect hsl; }
    ^^^^
```

## Node types

Each type except `cron` also answers to its class name (`Waveform` and `WaveformNode` are the same). Every
node takes `metadata`. [docs/nodes.md](docs/nodes.md) lists every type's settings, with their types and
defaults, and has a working example for each sink.

| Type | What it does | Inputs | Outputs |
|---|---|---|---|
| **Sources** | | | |
| `Waveform` | Sine, triangle, sawtooth, square or attack-decay wave per channel | `phase`, `speed` | `out` |
| `SineSource` | Sine wave on every channel, for testing | | `dmx` |
| `SeededRandom` | Fixed random values per channel, drawn once from a seed | | `out` |
| `literal` | A constant, e.g. `node literal red color:srgb [[1,0,0]];` | | `out` |
| `cron` | 1 while the local time matches a cron schedule, else 0, e.g. `node cron night 0 22;` | | `out` |
| `SacnUniverse` | Receives one sACN universe: raw channel values, a packet counter, a stream-terminated flag | | `dmx` (the default), `count`, `terminated` |
| **Transforms** | | | |
| `Compose` | Interleaves named inputs into one payload, such as a color | the names in `ports { }` | `out` |
| `Color` | Converts to a color model, e.g. `node Color rgb rgb { ... }` | `color` | `color` |
| `ColorCorrection` | Gamma, saturation, brightness and per-channel scale and offset | `input` | `out` |
| `Math` | Element-wise multiply, add, subtract, min, max, screen or lerp | `a`, `b` | `out` |
| `MatrixMultiply` | Applies a fixed matrix to each channel vector | `input` | `out` |
| `RangeMap` | Maps each channel to its own range | `input` | `out` |
| `Reshape` | Regroups values into rows of N components, e.g. DMX channels into RGB pixels | `input` | `output` |
| `RandomMap` | Maps input channels to output channels at random, optionally seeded | `input` | `out` |
| `Smooth` | Smoothing and slew limiting over time | `input`, `reset` | `output` |
| `TwinkleEffect` | Per-pixel twinkle over a color input | `input` | `out` |
| `Crossfade` | Fades between two colors when a selector changes | `input0`, `input1`, `selector` | `out` |
| **Sinks** | | | |
| `ConsoleSink` | Prints frames to the log | `dmx` | |
| `SacnSink` | Sends one sACN universe | `input` | |
| `DdpSink` | Sends pixels over DDP | `input` | |
| `LifxSink` | Sets LIFX bulbs | `color` | |
| `GoveeLight` | Sets a Govee light over its LAN API | `light` | |

`uv run rasl --describe <file>` prints the nodes, their ports and the edges of a config as JSON.

## Command line

```text
rasl [-h] [-v] [--validate] [--describe] [--api-port PORT] [--api-host HOST] [--no-watch] [--profile] [config]
```

| Option | What it does |
|---|---|
| `config` | The config file to run. |
| `--validate` | Load the config, print the node count and run order, and exit. |
| `--describe` | Print the graph as JSON on stdout and exit. Log lines go to stderr, so the output can be piped (e.g. to `jq`). |
| `--api-port PORT` | Start the web server on this port. Overrides the `ui` block. |
| `--api-host HOST` | The address the web server binds when `--api-port` is given. Default `127.0.0.1`. Without `--api-port`, the `ui` block's `host` is used. |
| `--no-watch` | Do not reload the config when it changes. |
| `--profile` | Turn on runtime profiling. |
| `-v`, `--version` | Print the version. |

Without `--api-port` or a `ui` block, no web server runs.

## Web UI and API

When the web server runs, it serves:

- **`/`**: the graph editor: the graph as the config file writes it, with each node's ports and live health.
  Drag from an output to an input to connect them (the ports that take the wire light up), drop a wire on
  empty canvas (or press ⌘K) to add a node, select and press Delete to remove, and edit a node's settings in
  the inspector, at a `$variable`'s definition or only on its line. Changes queue, drawn dashed, with the diff they make to the file and any
  error; **Save** writes the file and the running graph reloads it. Editing needs a watched config (no
  `--no-watch`). The page is built from `js/packages/web` and needs no internet access.
- **`/graphql`**: a GraphQL API. Open it in a browser for the GraphiQL editor. It reads the running graph, its
  metrics and health, and the config as written; its mutations are the editor's edits to the config files
  ([docs/web-api.md](docs/web-api.md)). Subscriptions run over the graphql-transport-ws protocol.
- **`GET /health`**: JSON with `status`, uptime, tick count, time since the last tick, disabled nodes and the
  result of the last reload. `status` is one of:

  | Status | Meaning | HTTP |
  |---|---|---|
  | `ok` | The graph is running. | 200 |
  | `degraded` | It is running, but a node was disabled after repeated failures (see `runtime` above), or the last config reload failed and the previous graph still runs. | 200 |
  | `stalled` | It has rate-driving sinks, but no tick has finished for 10 ticks at the slowest sink's rate (at least 5 seconds). | 503 |

The server has no authentication. It binds `127.0.0.1` unless `--api-host` (with `--api-port`) or the `ui`
block's `host` says otherwise (the container passes `0.0.0.0`).

## Live reload

rasl watches the config file, and every file it includes, while it runs. Save a change and the running graph
follows within about a second, at the next tick; nothing restarts but what changed:

| You change | What happens |
|---|---|
| a comment, the layout, the order of nodes | nothing |
| a node's settings | that node is restarted with the new settings (a node that can take them while running, like `Smooth`, keeps its state) |
| a node's `connect` lines | the routing changes; the node keeps running |
| a `@set` variable or an included file | the nodes that read it change, as above |
| add or remove a node | it is started or stopped |
| the `ui` or `runtime` block | nothing until rasl is restarted (a warning says so); a bad value is still reported |

A config with a problem is never applied, in whole or in part. The problem is printed with its file, line and
column, the graph keeps running as it was, and `/health` reports `degraded` until the files are valid again.

Run with `--no-watch` to turn this off.

## Documentation

- [docs/](docs/README.md): the documentation index.
- [knobly language reference](https://mcurcio.github.io/knobly/language/): the config file syntax.
- [CONTRIBUTING.md](CONTRIBUTING.md): the repository layout, building, testing and writing a node.
- [js/README.md](js/README.md): the JavaScript workspace.

## Contributing

Bug reports and pull requests are welcome. [CONTRIBUTING.md](CONTRIBUTING.md) explains how to set up a
checkout, run the checks and open a pull request.

## License

rasl is released under the [MIT License](LICENSE).
