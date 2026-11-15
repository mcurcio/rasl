# RASL - Real-time Async Streaming for Lighting

RASL is a Python-based data engine for processing and routing DMX/sACN lighting data through a configurable DAG (Directed Acyclic Graph).

## Features

- **Graph-based processing**: Model your lighting pipeline as a DAG with source, transform, and sink nodes
- **sACN/E1.31 support**: Receive and transmit sACN DMX data
- **Universe patching**: Remap channels from multiple source universes
- **Async runtime**: Built on anyio for high-performance async processing
- **Configuration-driven**: Define your graph in [knobly](https://github.com/mcurcio/knobly) config files (nginx-style, with variables, snippets and includes)

## Installation

```bash
# Using uv (recommended)
uv sync

# With dev dependencies for testing
uv sync --dev
```

## Quick Start

1. Create a configuration file (e.g., `config.conf`):

```nginx
rasl {
    node sacnSource {
        type SacnSourceNode;
        universes 1 2;
    }

    node patch {
        type UniversePatchTransform;
        output universe0;
        segment {
            source_universe 1;
            source_channel 1;
            length 150;
            target_channel 1;
        }
    }

    node sink {
        type SacnSinkNode;
        input universe0;
        target_host "10.0.60.30";
        target_universe 0;
    }

    edge { from sacnSource:dmx; to patch:dmx; }
    edge { from patch:universe0; to sink:universe0; }
}
```

1. Validate the configuration:

```bash
rasl --validate config.conf
```

1. Run the engine:

```bash
rasl config.conf
```

## Node Types

### SacnSourceNode

Receives sACN/E1.31 DMX data from the network.

```nginx
node source {
    type SacnSourceNode;
    universes 1 2 3;          # Universes to listen for
    bind_address "0.0.0.0";   # Optional: interface to bind
    bind_port 5568;           # Optional: UDP port
    metadata "colorSpace=rgb"; # Optional: metadata
}
```

### UniversePatchTransform

Remaps DMX channels from source universes to an output buffer.

```nginx
node patch {
    type UniversePatchTransform;
    output universe0;         # Output port name
    defaults {                # Optional defaults for segments
        source_universe 1;
        source_channel 1;
        length 150;
    }
    segment { target_channel 1; }
    segment { target_channel 151; }
}
```

### SacnSinkNode

Transmits DMX data via sACN/E1.31 to controllers.

```nginx
node sink {
    type SacnSinkNode;
    input universe0;          # Input port name
    target_host "10.0.60.30"; # Controller IP address
    target_universe 0;        # Target universe number
    min_interval_ms 25;       # Rate limiting (default: 25ms)
    source_name "RASL";       # sACN source name
    priority 100;             # sACN priority (0-200)
}
```

## Configuration language

Config files are written in [knobly](https://github.com/mcurcio/knobly): directives ended by `;`, blocks in
`{ }`, `#` comments. Its [language reference](https://mcurcio.github.io/knobly/language/) has the whole syntax.
What rasl configs use most:

```nginx
@set $pixels 2284;                    # a variable

@snippet twinkle $source {            # a reusable block
    mode brightness;
    connect $source;
}

graph {
    node TwinkleEffect sparkle { @use twinkle rgb; }
    node DdpSink leds {
        max_count $pixels;
        connect sparkle[0~150] pixels;  # a slice: bounds separated by ~
    }
    @include "more_sinks.conf";       # another file's directives, spliced in here
}
```

A problem in a config is reported with its file, line and column and a caret under the text.

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
| the `ui` block | nothing until rasl is restarted (a warning says so) |

A config with a problem is never applied, in whole or in part. The problem is printed with its file, line and
column, and the graph keeps running as it was until the files are valid again.

Run with `--no-watch` to turn this off.

## Development

### Running Tests

```bash
uv run pytest -v
```

### Project Structure

```text
src/rasl/
├── units.py     # Duration and Frequency: typed quantities for node config
├── signal/      # What flows: Frame, matrix and bool payloads, payload registry
├── color/       # Color models, conversions (one module per model family), color payloads
├── graph/       # Topology and the node contract
│   ├── node/    #   BaseNode, its Config bases, NodeContext, TickContext, node registry
│   ├── ports/   #   Port specs, port groups, the ports nodes read and write
│   └── ...      #   Edge, Slice, GraphBuilder, ExecutionPlan, input routing, ordering
├── runtime/     # Running a plan: Runtime, Scheduler, Executor, NodeHost, diagnostics
├── nodes/       # Built-in nodes: effects, color, debug, literal
├── devices/     # One package per protocol: sacn, ddp, lifx, govee
├── config/      # The config language: document, node and connect directives, build, reload, watch
└── app/         # The rasl command, the GraphQL server, the dashboard files
tests/           # Mirrors src/rasl
```

Each package imports only from those listed above it (`runtime`, `nodes` and `devices` do not
import each other, nor do `graph` and `color`). `tests/test_import_layers.py` checks this.

## License

See [LICENSE](../LICENSE) for details.
