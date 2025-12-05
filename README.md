# RASL - Real-time Async Streaming for Lighting

RASL is a Python-based data engine for processing and routing DMX/sACN lighting data through a configurable DAG (Directed Acyclic Graph).

## Features

- **Graph-based processing**: Model your lighting pipeline as a DAG with source, transform, and sink nodes
- **sACN/E1.31 support**: Receive and transmit sACN DMX data
- **Universe patching**: Remap channels from multiple source universes
- **Async runtime**: Built on anyio for high-performance async processing
- **Configuration-driven**: Define your graph in nginx-style config files

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

## Development

### Running Tests

```bash
uv run pytest -v
```

### Project Structure

```text
rasl/
├── src/rasl/
│   ├── __init__.py      # CLI entry point
│   ├── engine/          # Core DAG types
│   │   ├── frame.py     # Frame data model
│   │   ├── node.py      # Node protocol
│   │   └── graph.py     # Graph builder
│   ├── nodes/           # Node implementations
│   │   ├── sacn_source.py
│   │   ├── sacn_sink.py
│   │   └── universe_patch.py
│   ├── runtime/         # Execution scheduler
│   │   └── scheduler.py
│   └── config/          # Configuration parser
│       └── loader.py
└── tests/               # Unit tests
```

## License

See [LICENSE](../LICENSE) for details.
