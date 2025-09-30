# RASL User Guide

## Getting Started

RASL (Real-Time Animation Show Library) is a standalone application for creating and running real-time animation graphs. This guide will help you get started with creating your first lighting animations.

### Installation

```bash
# Install RASL
pip install rasl

# Verify installation
rasl --version
```

### Your First Animation

Create a simple sine wave animation:

```python
# my_first_show.py
from rasl import *

# Create a sine wave source
sine = SineSource(freq=1.0, channels=8)

# Scale and offset the values  
scaler = ScaleBias(scale=0.8, bias=0.2)

# Output to console for testing
console = ConsoleSink(format="table")

# Connect the nodes
sine >> scaler >> console

# Expose parameters for UI control
expose_parameter("sine.freq", min=0.1, max=10.0)
expose_parameter("scaler.scale", min=0.0, max=2.0)
```

Run your animation:

```bash
rasl run my_first_show.py
```

**What happens when you run this:**

1. RASL loads your script and executes it
2. Finds all `Sink` nodes in the script globals (in this case, `console`)
3. Traces backwards through connections to discover the full graph: `sine -> scaler -> console`
4. Creates an `Engine` with the discovered sinks and nodes
5. Starts the execution loop at 30 Hz (configurable)
6. Opens web interface at `http://localhost:8080`

The key insight: **RASL discovers your graph automatically by finding sinks and tracing connections backwards**. You don't need to explicitly tell RASL about your nodes - just create them, connect them, and ensure at least one sink exists.

## Core Concepts

### Nodes

RASL uses three types of nodes:

- **Sources**: Generate data (SineSource, CSVSource)
- **Transforms**: Process data (ScaleBias, ToRGB, ColorTemperature)  
- **Sinks**: Output data (ConsoleSink, SACNSink, LIFXSink)

### Connections

Connect nodes using the `>>` operator:

```python
source >> transform >> sink

# Fan out to multiple destinations
source >> [sink1, sink2, sink3]

# Chain multiple transforms
source >> transform1 >> transform2 >> sink
```

### Parameters

Expose node parameters for real-time control:

```python
expose_parameter("node_id.param_name", min=0, max=100, step=1)
```

## Built-in Nodes

### Sources

#### SineSource
Generates smooth sine wave animations.

```python
sine = SineSource(
    freq=1.0,           # Frequency in Hz
    amplitude=1.0,      # Wave amplitude
    channels=10,        # Number of output channels
    phase_shift=0.1     # Phase between channels
)
```

#### TestPatternSource
Generates test patterns for debugging.

```python
test = TestPatternSource(
    pattern="ramp",     # "ramp", "step", "random"
    channels=16,
    speed=1.0
)
```

### Transforms

#### ScaleBias
Linear transformation: `output = input * scale + bias`

```python
scaler = ScaleBias(scale=0.8, bias=0.1)
```

#### ToRGB
Converts single-channel values to RGB color.

```python
rgb = ToRGB(
    colorspace="linear_srgb"  # Color space for output
)
```

#### ColorTemperature
Maps values to color temperature range.

```python
color_temp = ColorTemperature(
    min_temp=2000,      # Warm orange (K)
    max_temp=6500       # Cool blue (K)
)
```

### Sinks

#### ConsoleSink
Displays data in the terminal for debugging.

```python
console = ConsoleSink(
    format="table",     # "table", "json", "summary"
    update_interval=1.0 # Seconds between updates
)
```

#### SACNSink
Outputs to sACN/E1.31 lighting protocol.

```python
sacn = SACNSink(
    universe=1,         # DMX universe
    start_channel=1,    # Starting channel
    target_hz=30        # Frame rate
)
```

#### LIFXSink
Controls LIFX smart lights on local network.

```python
lifx = LIFXSink(
    target="broadcast", # "broadcast" or specific IP
    transition_ms=100   # Transition time
)
```

## Common Patterns

### Color Chase Effect

```python
# Create traveling wave
chase = SineSource(
    freq=0.5,
    channels=20,
    phase_shift=0.314  # π/10 radians
)

# Convert to color
chase >> ColorTemperature(min_temp=2000, max_temp=6500) >> ToRGB() >> sacn
```

### Audio-Reactive Animation

```python
# Audio input (when implemented)
audio = AudioSource(device="default")

# Process audio
audio >> LowPassFilter(cutoff=100) >> ScaleBias(scale=2.0) >> rgb_output
```

### Multi-Universe Setup

```python
# Create base animation
base = SineSource(freq=1.0, channels=100)

# Split to multiple universes
universe1 = SACNSink(universe=1, start_channel=1)
universe2 = SACNSink(universe=2, start_channel=1) 

base >> [universe1, universe2]
```

## Web Interface

The built-in web interface provides:

- **Graph Visualization**: See your node connections
- **Parameter Controls**: Adjust exposed parameters in real-time
- **Performance Monitoring**: Track frame rates and node health
- **Console Output**: View debug information

### Parameter Control

Parameters exposed with `expose_parameter()` appear as controls in the web UI:

- Sliders for numeric ranges
- Dropdowns for enum values
- Text inputs for strings

### Performance Monitoring

Monitor your animation performance:

- Frame rate (target vs actual)
- Node execution times
- Error rates and health status
- Memory usage

## Hot Reload

RASL automatically reloads your script when you save changes:

1. Edit your script file
2. Save the file
3. RASL detects the change and reloads
4. Animation continues with new parameters

This enables rapid iteration during development.

## Command Line Interface

### Running Scripts

```bash
# Run with default settings
rasl run my_show.py

# Custom ports and settings
rasl run my_show.py --ui-port 8080 --api-port 8081 --host 0.0.0.0

# Disable hot-reload
rasl run my_show.py --no-watch

# Enable debug mode
rasl run my_show.py --debug
```

### Validation

```bash
# Validate script without running
rasl validate my_show.py

# Export graph specification
rasl export my_show.py --format json --output graph.json
```

### Examples

```bash
# List available examples
rasl examples

# Run an example
rasl run examples/simple_sine.py
```

## Best Practices

### Script Organization

```python
# Group related nodes
# Sources
sine = SineSource(freq=1.0, channels=16)
noise = NoiseSource(seed=42)

# Effects
fade = Fade(duration=2.0)
strobe = Strobe(rate=5.0)

# Outputs  
console = ConsoleSink(format="summary")
sacn = SACNSink(universe=1)

# Build graph
sine >> fade >> sacn
noise >> strobe >> console

# Expose key parameters
expose_parameter("sine.freq", min=0.1, max=10.0)
expose_parameter("fade.duration", min=0.5, max=10.0)
```

### Parameter Naming

Use descriptive parameter paths:

```python
# Good
expose_parameter("main_sine.frequency", min=0.1, max=10.0)
expose_parameter("color_effect.temperature", min=2000, max=6500)

# Avoid
expose_parameter("s1.f", min=0.1, max=10.0)
expose_parameter("c.t", min=2000, max=6500)
```

### Performance Tips

- Use appropriate frame rates (30 Hz for most applications)
- Limit channel counts for complex effects
- Monitor performance in the web interface
- Use ConsoleSink for debugging, disable for production

### Error Handling

RASL provides robust error handling:

- Individual node failures don't crash the system
- Validation catches common mistakes
- Hot-reload recovers from script errors
- Web interface shows error status

## Troubleshooting

### Common Issues

**Script won't load**
- Check Python syntax with `rasl validate`
- Ensure all imports are available
- Check file permissions

**No output from sinks**
- Verify connections with `>>` operator
- Check sink configuration (IP addresses, ports)
- Monitor node health in web interface

**Performance issues**
- Reduce frame rate or channel count
- Check for expensive operations in transforms
- Monitor CPU usage

**Hot-reload not working**
- Ensure file is being saved properly
- Check file watcher permissions
- Try restarting RASL

### Getting Help

- Check the web interface for error messages
- Use ConsoleSink to debug data flow
- Enable debug mode for detailed logging
- Consult the API documentation at `/api/docs`

## Next Steps

- Explore the example scripts
- Try building multi-universe setups
- Experiment with different color effects
- Create custom transform nodes
- Build complex multi-layer animations

For advanced topics, see the [Architecture Guide](architecture.md) and [API Reference](api.md).
