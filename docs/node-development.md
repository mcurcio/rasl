# Node Development Guide

This guide explains how to create custom sources, transforms, and sinks in RASL. The architecture emphasizes **separation of concerns** - base classes handle engine integration while your code focuses purely on domain logic.

## Architecture Principles

### Base Class Responsibilities
**BaseSource/BaseTransform/BaseSink** handle all engine integration:
- **Lifecycle Management**: Loop counting, duration tracking, EOS signaling
- **Execution State**: Current loop iteration, remaining duration, downstream demand
- **Error Propagation**: Standardized error handling and node removal
- **Port Management**: Schema validation, connection tracking, parameter exposure
- **Frame Processing**: Memoization coordination with executor

### Your Responsibilities
**Custom node implementations** focus on pure domain logic:
- **Data Generation/Transformation**: Core algorithm in `_generate_data(frame)`
- **Resource Management**: File handles, network connections, internal buffers
- **Domain-Specific Reset**: How to seek/restart when looping
- **Schema Declaration**: Output port schemas and parameter specifications
- **Base Liveness Declaration**: Intrinsic liveness before loop elevation

## Mixin Architecture

RASL uses **composable mixins** to add common behaviors without code duplication:

### LoopingMixin
Adds loop counting with automatic liveness elevation:

```python
class CSVSource(LoopingMixin, BaseSource):
    def __init__(self, file: str, **kwargs):
        self.file = file
        self._reader = None
        super().__init__(**kwargs)  # LoopingMixin adds loop_count parameter
    
    def _determine_base_liveness(self) -> Liveness:
        return Liveness.FINITE  # CSV files are inherently finite
    
    # Mixin automatically handles liveness elevation:
    # loop_count=1 → FINITE
    # loop_count>1 → GENERATOR  
    # loop_count=-1 → STREAMING
```

### DurationMixin
Adds duration limits for generator sources:

```python
class SineSource(DurationMixin, BaseSource):
    def __init__(self, freq: float = 1.0, **kwargs):
        self.freq = freq
        super().__init__(**kwargs)  # DurationMixin adds duration parameter
    
    def _determine_base_liveness(self) -> Liveness:
        return Liveness.GENERATOR
    
    # Mixin modifies liveness:
    # duration=None → GENERATOR (runs indefinitely)
    # duration=30.0 → FINITE (stops after 30 seconds)
```

### RateLimitMixin
Adds output rate control:

```python
class NetworkSource(RateLimitMixin, BaseSource):
    def __init__(self, host: str, max_hz: float = 60.0, **kwargs):
        self.host = host
        super().__init__(max_hz=max_hz, **kwargs)
    
    # Mixin handles rate limiting automatically
```

## Implementation Patterns

### Basic Source Implementation

```python
class NoiseSource(BaseSource):
    """Generates random noise values."""
    
    def __init__(self, amplitude: float = 1.0, channels: int = 1, **kwargs):
        self.amplitude = amplitude
        self.channels = channels
        super().__init__(**kwargs)
    
    def _determine_base_liveness(self) -> Liveness:
        """Noise generators can run indefinitely."""
        return Liveness.GENERATOR
    
    def _generate_data(self, frame: Frame) -> NDArrayLike:
        """Generate random values for this frame."""
        import random
        return [random.uniform(-self.amplitude, self.amplitude) 
                for _ in range(self.channels)]
    
    def param_spec(self) -> Mapping[str, Mapping[str, Any]]:
        """Define parameters for UI control."""
        return {
            "amplitude": {
                "type": "float",
                "default": 1.0,
                "min": 0.0,
                "max": 10.0,
                "description": "Noise amplitude"
            },
            "channels": {
                "type": "int", 
                "default": 1,
                "min": 1,
                "max": 512,
                "description": "Number of output channels"
            }
        }
    
    def port_schema(self, name: str) -> Schema:
        """Define output schema."""
        if name == "out":
            channels = [Channel(f"ch{i}", "unitless", Range(-10.0, 10.0)) 
                       for i in range(self.channels)]
            return Schema(components=(
                Component("Noise", channels=tuple(channels)),
            ))
        raise ValueError(f"Unknown port: {name}")
```

### Looping Source with Reset Logic

```python
class CSVSource(LoopingMixin, BaseSource):
    """Reads data from CSV file with optional looping."""
    
    def __init__(self, file: str, **kwargs):
        self.file = file
        self._reader = None
        self._current_row = 0
        self._data = []
        super().__init__(**kwargs)  # LoopingMixin handles loop_count
        self._load_file()
    
    def _determine_base_liveness(self) -> Liveness:
        return Liveness.FINITE
    
    def _load_file(self) -> None:
        """Load CSV data into memory."""
        import csv
        with open(self.file, 'r') as f:
            reader = csv.reader(f)
            self._data = [list(map(float, row)) for row in reader]
    
    def _generate_data(self, frame: Frame) -> NDArrayLike:
        """Read next row, handling loops via execution state."""
        if self._current_row >= len(self._data):
            # At end of data - check if we should loop
            if self.execution_state.should_loop:
                self._reset_to_beginning()
                self.execution_state.notify_loop_completed()
            else:
                raise EndOfData()  # Signals EOS
        
        data = self._data[self._current_row]
        self._current_row += 1
        return data
    
    def _reset_to_beginning(self) -> None:
        """Reset to start of CSV file."""
        self._current_row = 0
```

### Transform Implementation

```python
class ScaleBias(BaseTransform):
    """Scale and offset input values."""
    
    def __init__(self, scale: float = 1.0, bias: float = 0.0, **kwargs):
        self.scale = scale
        self.bias = bias
        super().__init__(**kwargs)
    
    def _transform_data(self, inputs: Dict[str, NDArrayLike], frame: Frame) -> Dict[str, NDArrayLike]:
        """Apply scale and bias to input data."""
        input_data = inputs["in"]
        output_data = [x * self.scale + self.bias for x in input_data]
        return {"out": output_data}
    
    def port_schema(self, name: str) -> Schema:
        """Input and output schemas are identical."""
        if name in ("in", "out"):
            # Schema will be determined by connection validation
            return Schema.ANY  # Accepts any schema, passes through
        raise ValueError(f"Unknown port: {name}")
```

### Sink Implementation

```python
class FSEQSink(BaseSink):
    """Export data to xLights FSEQ format."""
    
    def __init__(self, filename: str, fps: int = 30, **kwargs):
        self.filename = filename
        self.fps = fps
        self._file = None
        self._frame_count = 0
        super().__init__(**kwargs)
    
    def _initialize(self) -> None:
        """Open FSEQ file for writing."""
        self._file = open(self.filename, 'wb')
        # Write FSEQ header...
    
    def _emit_data(self, inputs: Dict[str, NDArrayLike], frame: Frame) -> None:
        """Write frame data to FSEQ file."""
        data = inputs["in"]
        # Convert to FSEQ format and write...
        self._frame_count += 1
    
    def _finalize(self) -> None:
        """Close file and update header with frame count."""
        if self._file:
            # Update header with final frame count...
            self._file.close()
```

## Execution State Access

Your nodes have **read-only access** to execution state for decision making:

```python
class SmartCSVSource(LoopingMixin, BaseSource):
    def _generate_data(self, frame: Frame) -> NDArrayLike:
        # Access execution state
        current_loop = self.execution_state.current_loop
        should_loop = self.execution_state.should_loop
        remaining_duration = self.execution_state.remaining_duration
        
        # Make decisions based on state
        if self._at_end_of_file():
            if should_loop:
                self._seek_to_beginning()
                self.execution_state.notify_loop_completed()  # Inform base class
                return self._read_next_row()
            else:
                raise EndOfData()
        
        return self._read_next_row()
```

**Available State Properties**:
- `current_loop: int` - Current loop iteration (0-based)
- `should_loop: bool` - Whether looping should continue
- `remaining_duration: Optional[float]` - Time left if duration-limited
- `downstream_demand: bool` - Whether downstream nodes need data

**State Notification Methods**:
- `notify_loop_completed()` - Inform base class that a loop finished
- `notify_duration_exceeded()` - Signal that duration limit reached
- `notify_resource_exhausted()` - Indicate external resource depleted

## Error Handling

### Recoverable vs Fatal Errors

**Recoverable Errors**: Handle internally, continue operation
```python
def _generate_data(self, frame: Frame) -> NDArrayLike:
    try:
        return self._read_network_data()
    except TemporaryNetworkError:
        # Return last known value, log warning
        return self._last_value
```

**Fatal Errors**: Let propagate to engine for node removal
```python
def _generate_data(self, frame: Frame) -> NDArrayLike:
    try:
        return self._read_file_data()
    except FileNotFoundError:
        # Don't catch - let engine remove this node
        raise
```

### Error vs EOS
- **EOS**: Natural completion (return `EOS()` or raise `EndOfData`)
- **Error**: Operational failure (raise exception)

```python
def _generate_data(self, frame: Frame) -> NDArrayLike:
    if self._at_natural_end():
        raise EndOfData()  # EOS - silent, triggers policies
    
    if self._hardware_failed():
        raise HardwareError("Device disconnected")  # Error - noisy, removes node
```

## Schema Design

### Component and Channel Design
```python
def port_schema(self, name: str) -> Schema:
    if name == "out":
        return Schema(components=(
            Component(
                name="RGB",
                channels=(
                    Channel("r", "linear_srgb", Range(0.0, 1.0)),
                    Channel("g", "linear_srgb", Range(0.0, 1.0)), 
                    Channel("b", "linear_srgb", Range(0.0, 1.0)),
                )
            ),
        ))
```

### Schema Compatibility
- **Name-based matching**: Channels align by name, not position
- **Permutation allowed**: `[r,g,b]` connects to `[b,r,g]` automatically
- **Unit conversion required**: `linear_srgb` to `hsv` needs explicit transform

## Testing Your Nodes

### Unit Testing Pattern
```python
def test_sine_source():
    sine = SineSource(freq=1.0, channels=2)
    
    # Test frame 0 (t=0.0)
    frame0 = Frame(t=0.0, dt=0.0, seq=0)
    data0 = sine._generate_data(frame0)
    assert data0 == [0.0, 0.0]  # sin(0) = 0
    
    # Test frame at quarter period (t=0.25)
    frame1 = Frame(t=0.25, dt=0.25, seq=1)  
    data1 = sine._generate_data(frame1)
    assert abs(data1[0] - 1.0) < 0.001  # sin(π/2) ≈ 1
```

### Integration Testing
```python
def test_csv_looping():
    # Create test CSV
    with open("test.csv", "w") as f:
        f.write("1,2\n3,4\n")
    
    csv = CSVSource("test.csv", loop_count=2)
    
    # Should read through twice then signal EOS
    frames = [Frame(t=i*0.1, dt=0.1, seq=i) for i in range(5)]
    
    assert csv._generate_data(frames[0]) == [1, 2]
    assert csv._generate_data(frames[1]) == [3, 4]
    assert csv._generate_data(frames[2]) == [1, 2]  # Loop 1
    assert csv._generate_data(frames[3]) == [3, 4]
    
    with pytest.raises(EndOfData):
        csv._generate_data(frames[4])  # Should signal EOS
```

## Best Practices

1. **Keep domain logic pure** - no engine concerns in your algorithms
2. **Use execution state** for decisions, notify base class of changes
3. **Handle resources properly** - clean up in `_finalize()` methods
4. **Design clear schemas** - explicit units, ranges, and component names
5. **Test thoroughly** - unit test algorithms, integration test with engine
6. **Document parameters** - provide clear param_spec for UI generation
7. **Handle errors appropriately** - recover when possible, fail loudly when not

This architecture ensures your nodes integrate seamlessly with the engine while keeping your code focused on what makes each node unique and valuable.
