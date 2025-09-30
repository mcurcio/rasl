# RASL

## Real-Time Animation Show Library

RASL is a standalone application for building and running real-time animation graphs targeting lights, motors, kinetic sculptures, and other channel-based systems. Users compose **sources → transforms → sinks** into validated DAGs using Python scripts, then monitor and control them through a built-in web interface.

### Key Features

- **Standalone Application**: Single executable with embedded web UI
- **Script-Driven**: Define lighting graphs in Python with hot-reload
- **Real-Time Performance**: 24-60 Hz operation with professional timing
- **Built-in Monitoring**: Web dashboard for graph visualization and control
- **Hardware Support**: sACN/E1.31 and LIFX protocols built-in
- **Failure Isolation**: Individual node failures don't crash the system

### Quick Start

```bash
# Install RASL
pip install rasl

# Run an example
rasl run examples/simple_sine.py

# Open web UI at http://localhost:8080
```

### Example Script

```python
from rasl import *

# Create nodes
sine = SineSource(freq=1.0, channels=150)
brightness = ScaleBias(scale=0.8)
rgb = ToRGB()

# Multiple outputs
console = ConsoleSink(format="summary")
sacn = SACNSink(universe=1, target_hz=30)

# Wire the graph
sine >> brightness >> rgb >> [console, sacn]

# Expose parameters for UI control
expose_parameter("brightness.scale", min=0.0, max=1.0)
expose_parameter("sine.freq", min=0.1, max=10.0)
```

## Architecture

RASL uses a **DAG-based processing model** with:

- **Single time authority**: Pluggable scheduler produces frames `{t, dt, seq}`
- **Lazy evaluation**: Per-frame materialization driven by sinks
- **Strict contracts**: Type-safe schemas with components, channels, units
- **Universal monitoring**: All nodes report health and performance metrics
- **Hot-reload**: Script changes update the graph without stopping output

See [docs/architecture.md](docs/architecture.md) for detailed design information.
