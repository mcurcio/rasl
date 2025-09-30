# Time and Liveness in RASL

Time handling and source lifecycle management are fundamental to RASL's execution model. This document explains how time flows through graphs and how different source types behave.

## Time Model

### Sequence Time as Primary Reference

RASL uses **sequence time** as the primary time domain for all nodes:

```python
@dataclass
class Frame:
    t: float          # Sequence time (0.0 = start of execution)
    dt: float         # Delta since last frame  
    seq: int          # Frame sequence number
    wall_time: float  # Wall clock (for debugging/logging only)
```

**Why sequence time?**
- **Deterministic**: Same script produces same output regardless of system performance
- **Exportable**: Offline rendering uses same time reference as live execution
- **Composable**: All nodes operate in unified time domain

### Time Domain Bridging

When sources operate in different time domains (e.g., audio files), explicit conversion nodes handle translation:

```python
# Audio file operates in "audio time"
audio = AudioSource("song.mp3")  # Has intrinsic audio timeline

# Explicit time domain conversion
warp = TimeWarp(from_domain="audio", to_domain="sequence", rate=1.2)  # 20% faster

# Now in sequence time domain
audio >> warp >> effects >> output
```

**Design Principle**: Time domain conversions are **explicit and visible** in the graph, not hidden engine magic.

## Source Liveness Types

### FINITE Sources
**Definition**: Bounded media with definite end point.

**Examples**:
- Single-pass CSV file: `CSVSource("data.csv")`
- Audio file played once: `AudioSource("song.mp3")`
- Fixed-length sequence: `SequenceSource(duration=30.0)`

**Behavior**:
- Signals EOS when data is exhausted
- Enables duration calculation for export
- Can be looped (see Liveness Elevation)

### GENERATOR Sources  
**Definition**: Can produce data indefinitely but may end naturally or be controlled.

**Examples**:
- Sine wave: `SineSource(freq=1.0)` - runs until disconnected
- Noise generator: `NoiseSource()` - infinite by nature
- Finite loops: `CSVSource("data.csv", loop_count=3)` - elevated from FINITE

**Behavior**:
- Runs until downstream nodes no longer need data
- May end naturally (finite loops complete)
- Duration controlled by downstream demand or internal completion

### STREAMING Sources
**Definition**: External, potentially infinite data streams that cannot be controlled by the engine.

**Examples**:
- Network input: `NetworkSource(host="mixer.local")`
- Live audio: `LiveAudioSource(device="default")`
- Infinite loops: `CSVSource("data.csv", loop_count=-1)` - elevated from FINITE

**Behavior**:
- Cannot be predicted or controlled by engine
- May end unexpectedly (network disconnect, device removal)
- Forces graph into LIVE execution mode

## Liveness Elevation

Sources can **elevate their liveness** based on configuration:

```python
# Base liveness: FINITE (single CSV pass)
csv_once = CSVSource("data.csv", loop_count=1)  # FINITE

# Elevated to GENERATOR (finite loops)  
csv_loops = CSVSource("data.csv", loop_count=3)  # FINITE → GENERATOR

# Elevated to STREAMING (infinite loops)
csv_infinite = CSVSource("data.csv", loop_count=-1)  # FINITE → STREAMING
```

**Elevation Rules**:
- `loop_count=1`: Maintains base liveness
- `loop_count>1`: Elevates to GENERATOR  
- `loop_count=-1`: Elevates to STREAMING

## Execution Modes

The engine automatically detects execution mode based on source liveness:

### DETERMINISTIC Mode
**Condition**: Only FINITE sources present
**Capabilities**:
- Predictable total duration
- Full offline rendering support
- Export to fseq, CSV, JSON formats
- Timeline scrubbing (future UI feature)

```python
csv = CSVSource("sequence.csv")           # FINITE
audio = AudioSource("backing.mp3")       # FINITE  
# Engine detects DETERMINISTIC mode
```

### CONTROLLABLE Mode  
**Condition**: FINITE + GENERATOR sources (no STREAMING)
**Capabilities**:
- User-controlled duration
- Offline rendering with specified duration
- Export support with duration policies
- Generator sources run until duration limit or natural completion

```python
csv = CSVSource("data.csv", loop_count=3) # FINITE → GENERATOR
sine = SineSource(freq=1.0)               # GENERATOR
# Engine detects CONTROLLABLE mode
```

### LIVE Mode
**Condition**: Any STREAMING sources present  
**Capabilities**:
- Real-time execution only
- No offline rendering
- No export capabilities
- Infinite execution until manually stopped

```python
network = NetworkSource(host="live.local") # STREAMING
sine = SineSource(freq=1.0)                # GENERATOR  
# Engine detects LIVE mode due to streaming source
```

## End-of-Stream (EOS) Handling

### EOS Policies
When upstream sources end, downstream nodes react according to configured policies:

```python
class Transform(BaseTransform):
    def __init__(self, on_eos: EOSPolicy = "hold_last"):
        self.on_eos = on_eos
```

**Available Policies**:
- `hold_last`: Continue with last received value
- `zero`: Output zeros after EOS
- `repeat`: Loop the last N values  
- `stop_sink`: Stop processing this branch
- `fail`: Raise error (for debugging)

### Multi-Input EOS Modes
Transforms with multiple inputs declare how to handle mixed EOS states:

```python
class Mixer(BaseTransform):
    def __init__(self, eos_mode: EOSMode = "pass_through"):
        self.eos_mode = eos_mode
```

**Available Modes**:
- `pass_through`: Continue as long as any input is active (default)
- `until_all_done`: Continue until all inputs signal EOS
- `until_any_done`: Stop when first input signals EOS

### EOS vs Errors
**EOS is silent**: Natural completion of finite sources
**Errors are noisy**: Node failures that prevent operation

```python
# EOS: Natural completion
csv_source.sample(frame) → EOS()  # Silent, triggers policies

# Error: Operational failure  
csv_source.sample(frame) → raise FileNotFoundError()  # Noisy, removes node
```

## Duration Calculation

### Export Duration Policies
For DETERMINISTIC and CONTROLLABLE modes, duration is determined by policy:

```python
class ExportPolicy:
    duration_mode: Literal["shortest_finite", "longest_finite", "user_specified"]
    duration_seconds: Optional[float] = None
```

**Policy Behaviors**:
- `shortest_finite`: Export ends when first FINITE source completes
- `longest_finite`: Export continues until last FINITE source completes  
- `user_specified`: Export for exactly `duration_seconds`

### Hybrid Graph Behavior
Graphs mixing FINITE and STREAMING sources operate in LIVE mode:

```python
# Finite background track
backing = AudioSource("track.mp3", loop_count=-1)  # FINITE → STREAMING

# Live input overlay  
live = NetworkSource(host="mixer.local")           # STREAMING

# Result: LIVE mode, no export possible
# Finite sources complete independently while streaming continues
```

## Time Domain Examples

### Basic Sequence Time
```python
# All nodes operate in sequence time
sine = SineSource(freq=1.0)        # Generates sin(2π * freq * frame.t)
delay = DelayTransform(delay=0.5)  # Delays by 0.5 sequence seconds
output = ConsoleSink()

sine >> delay >> output
```

### Audio Time Bridging
```python  
# Audio file in audio time domain
audio = AudioSource("song.mp3")    # 3:30 duration in audio time

# Bridge to sequence time with speed control
warp = TimeWarp("audio", "sequence", rate=0.8)  # 20% slower

# Mix with sequence-time generator
sine = SineSource(freq=2.0)        # Sequence time
mixer = AudioMix()

audio >> warp >> mixer.ports.backing
sine >> mixer.ports.overlay
mixer >> output
```

### Duration-Limited Generators
```python
# Generator with time limit (future feature)
sine = SineSource(freq=1.0, duration=10.0)  # Runs for exactly 10 seconds
noise = NoiseSource()                        # Runs indefinitely

# Engine stops when sine completes (shortest finite policy)
```

This time model enables RASL to handle everything from deterministic sequences to live streaming while maintaining consistent behavior and export capabilities.
