# Phase 2: Complete Node Library

**Duration**: 7-10 days  
**Goal**: Implement comprehensive node library covering all major use cases

## Objectives

1. **Source Nodes**: Complete implementations for all documented source types
2. **Transform Nodes**: Essential transforms for real-time animation
3. **Sink Nodes**: Hardware protocol support and output formats
4. **Schema System**: Advanced type validation and conversion
5. **Performance**: Optimized implementations for real-time execution

## Success Criteria

- [ ] All documented node types implemented and tested
- [ ] Complex example scripts run successfully (color_chase.py, etc.)
- [ ] Hardware protocol sinks functional (sACN, LIFX)
- [ ] Schema validation prevents connection errors
- [ ] Performance targets met for realistic graphs

## Node Implementation Strategy

### Test-Driven Node Development

Each node follows this pattern:
1. **Write comprehensive tests** defining expected behavior
2. **Implement minimal version** to pass tests
3. **Add parameter validation** and error handling
4. **Optimize for performance** while maintaining correctness

### Node Categories

## 1. Source Nodes (`rasl/nodes/sources/`)

### SineSource (Enhanced)
```python
class SineSource(BaseSource):
    """Multi-channel sine wave generator with phase control."""
    
    TYPE = "SineSource"
    LIVENESS = Liveness.GENERATOR
    
    def __init__(self, freq=1.0, amplitude=1.0, phase=0.0, 
                 channels=1, channel_phase_offset=0.0, **kwargs):
        super().__init__(**kwargs)
        self.freq = freq
        self.amplitude = amplitude
        self.phase = phase
        self.channels = channels
        self.channel_phase_offset = channel_phase_offset
        self._start_time = None
    
    def param_spec(self):
        return {
            "freq": {"type": float, "default": 1.0, "min": 0.001, "max": 1000.0},
            "amplitude": {"type": float, "default": 1.0, "min": 0.0, "max": 10.0},
            "phase": {"type": float, "default": 0.0, "min": 0.0, "max": 2*np.pi},
            "channels": {"type": int, "default": 1, "min": 1, "max": 512},
            "channel_phase_offset": {"type": float, "default": 0.0, "min": 0.0, "max": 2*np.pi}
        }
    
    def port_schema(self, name: str) -> Schema:
        if name == "out":
            # Create schema with correct number of channels
            channels = [Channel(f"ch{i}", "unitless", Range(0.0, 1.0)) 
                       for i in range(self.channels)]
            return Schema(components=(
                Component("Signal", channels=tuple(channels)),
            ))
        raise ValueError(f"Unknown port: {name}")
    
    def sample(self, frame: Frame) -> Mapping[str, NDArrayLike]:
        import numpy as np
        
        if self._start_time is None:
            self._start_time = frame.t
        
        # Calculate phase for each channel
        base_phase = 2 * np.pi * self.freq * (frame.t - self._start_time) + self.phase
        
        values = np.zeros(self.channels)
        for i in range(self.channels):
            channel_phase = base_phase + (i * self.channel_phase_offset)
            values[i] = self.amplitude * np.sin(channel_phase)
        
        return {"out": values}
```

**Test: SineSource** (`tests/unit/nodes/test_sine_source.py`):
```python
class TestSineSource:
    def test_single_channel_output(self):
        """Single channel should produce correct sine wave."""
        sine = SineSource(freq=1.0, amplitude=1.0, channels=1)
        sine.open()
        
        # Test at known points
        frame_0 = Frame(t=0.0, dt=0.0, seq=0)
        frame_quarter = Frame(t=0.25, dt=0.25, seq=1)
        frame_half = Frame(t=0.5, dt=0.25, seq=2)
        
        result_0 = sine.sample(frame_0)
        result_quarter = sine.sample(frame_quarter)
        result_half = sine.sample(frame_half)
        
        assert abs(result_0["out"][0] - 0.0) < 1e-6  # sin(0) = 0
        assert abs(result_quarter["out"][0] - 1.0) < 1e-6  # sin(π/2) = 1
        assert abs(result_half["out"][0] - 0.0) < 1e-6  # sin(π) = 0
    
    def test_multi_channel_phase_offset(self):
        """Multiple channels should have correct phase relationships."""
        sine = SineSource(freq=1.0, channels=3, channel_phase_offset=np.pi/2)
        sine.open()
        
        frame = Frame(t=0.0, dt=0.0, seq=0)
        result = sine.sample(frame)
        
        assert len(result["out"]) == 3
        # Channel 0: sin(0) = 0
        # Channel 1: sin(π/2) = 1  
        # Channel 2: sin(π) = 0
        assert abs(result["out"][0] - 0.0) < 1e-6
        assert abs(result["out"][1] - 1.0) < 1e-6
        assert abs(result["out"][2] - 0.0) < 1e-6
```

### NoiseSource
```python
class NoiseSource(BaseSource):
    """Configurable noise generator (white, pink, brown)."""
    
    TYPE = "NoiseSource"
    LIVENESS = Liveness.GENERATOR
    
    def __init__(self, noise_type="white", amplitude=1.0, channels=1, 
                 seed=None, **kwargs):
        super().__init__(**kwargs)
        self.noise_type = noise_type
        self.amplitude = amplitude
        self.channels = channels
        self.seed = seed
        self._rng = np.random.RandomState(seed)
        self._pink_state = None  # For pink noise generation
    
    def sample(self, frame: Frame) -> Mapping[str, NDArrayLike]:
        if self.noise_type == "white":
            values = self._rng.uniform(-1, 1, self.channels) * self.amplitude
        elif self.noise_type == "pink":
            values = self._generate_pink_noise()
        elif self.noise_type == "brown":
            values = self._generate_brown_noise()
        else:
            raise ValueError(f"Unknown noise type: {self.noise_type}")
        
        return {"out": values}
```

### CSVSource
```python
class CSVSource(BaseSource):
    """Load data from CSV files with interpolation."""
    
    TYPE = "CSVSource"
    LIVENESS = Liveness.FINITE
    
    def __init__(self, file_path: str, time_column="time", 
                 interpolation="linear", loop_count=1, **kwargs):
        super().__init__(**kwargs)
        self.file_path = Path(file_path)
        self.time_column = time_column
        self.interpolation = interpolation
        self.loop_count = loop_count
        self._data = None
        self._duration = None
    
    def open(self):
        """Load CSV data."""
        import pandas as pd
        
        if not self.file_path.exists():
            raise FileNotFoundError(f"CSV file not found: {self.file_path}")
        
        self._data = pd.read_csv(self.file_path)
        
        if self.time_column not in self._data.columns:
            raise ValueError(f"Time column '{self.time_column}' not found")
        
        self._duration = self._data[self.time_column].max()
    
    def sample(self, frame: Frame) -> Mapping[str, NDArrayLike]:
        if self._data is None:
            raise RuntimeError("CSVSource not opened")
        
        # Handle looping
        if self.loop_count > 1 or self.loop_count == -1:
            if self._duration > 0:
                t = frame.t % self._duration
            else:
                t = frame.t
        else:
            t = frame.t
            if t > self._duration:
                raise EndOfData("CSV data exhausted")
        
        # Interpolate data at time t
        values = self._interpolate_at_time(t)
        return {"out": values}
```

## 2. Transform Nodes (`rasl/nodes/transforms/`)

### ScaleBias (Enhanced)
```python
class ScaleBias(BaseTransform):
    """Scale and bias transform with per-channel control."""
    
    TYPE = "ScaleBias"
    
    def __init__(self, scale=1.0, bias=0.0, per_channel=False, **kwargs):
        super().__init__(**kwargs)
        self.scale = scale
        self.bias = bias
        self.per_channel = per_channel
    
    def evaluate(self, frame: Frame, **inputs: NDArrayLike) -> Mapping[str, NDArrayLike]:
        input_data = inputs.get("in")
        if input_data is None:
            raise ValueError("ScaleBias requires 'in' input")
        
        data = np.array(input_data)
        
        if self.per_channel and isinstance(self.scale, (list, np.ndarray)):
            # Per-channel scaling
            scale_array = np.array(self.scale)
            if len(scale_array) != len(data):
                raise ValueError("Scale array length must match channel count")
            result = data * scale_array
        else:
            result = data * self.scale
        
        if self.per_channel and isinstance(self.bias, (list, np.ndarray)):
            # Per-channel bias
            bias_array = np.array(self.bias)
            if len(bias_array) != len(data):
                raise ValueError("Bias array length must match channel count")
            result += bias_array
        else:
            result += self.bias
        
        return {"out": result}
```

### ColorSpaceTransform
```python
class ColorSpaceTransform(BaseTransform):
    """Convert between color spaces (RGB, HSV, etc.)."""
    
    TYPE = "ColorSpaceTransform"
    
    def __init__(self, from_space="rgb", to_space="hsv", **kwargs):
        super().__init__(**kwargs)
        self.from_space = from_space.lower()
        self.to_space = to_space.lower()
        
        if self.from_space == self.to_space:
            raise ValueError("Source and target color spaces must be different")
    
    def port_schema(self, name: str) -> Schema:
        if name == "in":
            return self._get_schema_for_space(self.from_space)
        elif name == "out":
            return self._get_schema_for_space(self.to_space)
        raise ValueError(f"Unknown port: {name}")
    
    def evaluate(self, frame: Frame, **inputs: NDArrayLike) -> Mapping[str, NDArrayLike]:
        input_data = inputs.get("in")
        if input_data is None:
            raise ValueError("ColorSpaceTransform requires 'in' input")
        
        # Ensure we have 3 channels for color
        if len(input_data) != 3:
            raise ValueError("Color transforms require exactly 3 channels")
        
        # Convert color space
        if self.from_space == "rgb" and self.to_space == "hsv":
            result = self._rgb_to_hsv(input_data)
        elif self.from_space == "hsv" and self.to_space == "rgb":
            result = self._hsv_to_rgb(input_data)
        else:
            raise ValueError(f"Conversion {self.from_space} -> {self.to_space} not implemented")
        
        return {"out": result}
    
    def _rgb_to_hsv(self, rgb):
        """Convert RGB to HSV color space."""
        import colorsys
        r, g, b = rgb
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        return np.array([h, s, v])
```

### MathTransform
```python
class MathTransform(BaseTransform):
    """Mathematical operations on signals."""
    
    TYPE = "MathTransform"
    
    def __init__(self, operation="add", operand=0.0, **kwargs):
        super().__init__(**kwargs)
        self.operation = operation
        self.operand = operand
    
    def param_spec(self):
        return {
            "operation": {"type": str, "default": "add", 
                         "enum": ["add", "multiply", "power", "sin", "cos", "abs", "clamp"]},
            "operand": {"type": float, "default": 0.0, "min": -1000.0, "max": 1000.0}
        }
    
    def evaluate(self, frame: Frame, **inputs: NDArrayLike) -> Mapping[str, NDArrayLike]:
        input_data = np.array(inputs.get("in", []))
        
        if self.operation == "add":
            result = input_data + self.operand
        elif self.operation == "multiply":
            result = input_data * self.operand
        elif self.operation == "power":
            result = np.power(input_data, self.operand)
        elif self.operation == "sin":
            result = np.sin(input_data * self.operand)
        elif self.operation == "cos":
            result = np.cos(input_data * self.operand)
        elif self.operation == "abs":
            result = np.abs(input_data)
        elif self.operation == "clamp":
            result = np.clip(input_data, 0.0, self.operand)
        else:
            raise ValueError(f"Unknown operation: {self.operation}")
        
        return {"out": result}
```

## 3. Sink Nodes (`rasl/nodes/sinks/`)

### ConsoleSink (Enhanced)
```python
class ConsoleSink(BaseSink):
    """Enhanced console output with formatting options."""
    
    TYPE = "ConsoleSink"
    
    def __init__(self, format="table", update_interval=1.0, 
                 precision=3, max_channels=16, **kwargs):
        super().__init__(**kwargs)
        self.format = format
        self.update_interval = update_interval
        self.precision = precision
        self.max_channels = max_channels
        self._last_update = 0.0
        self._console = None
    
    def _initialize(self):
        """Setup rich console for formatted output."""
        if self.format == "table":
            from rich.console import Console
            from rich.table import Table
            self._console = Console()
    
    def emit(self, frame: Frame, **inputs: NDArrayLike) -> None:
        # Rate limiting
        if frame.t - self._last_update < self.update_interval:
            return
        
        self._last_update = frame.t
        
        input_data = inputs.get("in")
        if input_data is None:
            return
        
        if self.format == "simple":
            print(f"Frame {frame.seq:6d}: {input_data}")
        elif self.format == "table":
            self._emit_table(frame, input_data)
        elif self.format == "json":
            import json
            data = {
                "frame": frame.seq,
                "time": round(frame.t, self.precision),
                "values": [round(float(v), self.precision) for v in input_data[:self.max_channels]]
            }
            print(json.dumps(data))
    
    def _emit_table(self, frame: Frame, data):
        """Emit formatted table output."""
        from rich.table import Table
        
        table = Table(title=f"Frame {frame.seq} (t={frame.t:.3f}s)")
        table.add_column("Channel", style="cyan")
        table.add_column("Value", style="green")
        
        for i, value in enumerate(data[:self.max_channels]):
            table.add_row(f"Ch{i:02d}", f"{value:.{self.precision}f}")
        
        if len(data) > self.max_channels:
            table.add_row("...", f"({len(data) - self.max_channels} more)")
        
        self._console.clear()
        self._console.print(table)
```

### SACNSink
```python
class SACNSink(BaseSink):
    """sACN/E1.31 protocol output for lighting control."""
    
    TYPE = "SACNSink"
    
    def __init__(self, universe=1, start_channel=1, ip="239.255.0.1", 
                 port=5568, source_name="RASL", **kwargs):
        super().__init__(**kwargs)
        self.universe = universe
        self.start_channel = start_channel
        self.ip = ip
        self.port = port
        self.source_name = source_name
        self._sacn_sender = None
    
    def _initialize(self):
        """Initialize sACN sender."""
        try:
            import sacn
            self._sacn_sender = sacn.sACNsender()
            self._sacn_sender.start()
            self._sacn_sender.activate_output(self.universe)
            self._sacn_sender[self.universe].multicast = True
            logger.info(f"sACN sender initialized for universe {self.universe}")
        except ImportError:
            raise RuntimeError("sacn library not available. Install with: pip install sacn")
    
    def emit(self, frame: Frame, **inputs: NDArrayLike) -> None:
        if self._sacn_sender is None:
            return
        
        input_data = inputs.get("in")
        if input_data is None:
            return
        
        # Convert to DMX values (0-255)
        dmx_data = np.clip(np.array(input_data) * 255, 0, 255).astype(np.uint8)
        
        # Create DMX packet
        dmx_packet = [0] * 512  # DMX universe is 512 channels
        
        end_channel = min(self.start_channel + len(dmx_data), 513)
        for i, value in enumerate(dmx_data):
            channel = self.start_channel + i
            if channel < 513:
                dmx_packet[channel - 1] = value  # DMX is 1-indexed
        
        # Send sACN packet
        try:
            self._sacn_sender[self.universe].dmx_data = dmx_packet
        except Exception as e:
            logger.error(f"sACN transmission failed: {e}")
    
    def _finalize(self):
        """Cleanup sACN sender."""
        if self._sacn_sender:
            self._sacn_sender.stop()
```

### LIFXSink
```python
class LIFXSink(BaseSink):
    """LIFX smart light control."""
    
    TYPE = "LIFXSink"
    
    def __init__(self, device_ip=None, device_mac=None, **kwargs):
        super().__init__(**kwargs)
        self.device_ip = device_ip
        self.device_mac = device_mac
        self._lifx_device = None
    
    def _initialize(self):
        """Initialize LIFX device connection."""
        try:
            from lifxlan import LifxLAN, Device
            
            if self.device_ip and self.device_mac:
                self._lifx_device = Device(self.device_mac, self.device_ip)
            else:
                # Auto-discover first device
                lifx = LifxLAN(1)
                devices = lifx.get_lights()
                if devices:
                    self._lifx_device = devices[0]
                else:
                    raise RuntimeError("No LIFX devices found")
            
            logger.info(f"LIFX device connected: {self._lifx_device.get_label()}")
            
        except ImportError:
            raise RuntimeError("lifxlan library not available. Install with: pip install lifxlan")
    
    def port_schema(self, name: str) -> Schema:
        if name == "in":
            return HSV_SCHEMA  # LIFX works well with HSV
        raise ValueError(f"Unknown port: {name}")
    
    def emit(self, frame: Frame, **inputs: NDArrayLike) -> None:
        if self._lifx_device is None:
            return
        
        input_data = inputs.get("in")
        if input_data is None or len(input_data) < 3:
            return
        
        try:
            # Convert to LIFX format
            h, s, v = input_data[:3]
            
            # LIFX uses 16-bit values
            hue = int(h * 65535)
            saturation = int(s * 65535)
            brightness = int(v * 65535)
            kelvin = 3500  # Default color temperature
            
            # Set color (non-blocking)
            self._lifx_device.set_color([hue, saturation, brightness, kelvin], 
                                      duration=0, rapid=True)
            
        except Exception as e:
            logger.error(f"LIFX control failed: {e}")
```

## 4. Advanced Schema System

### Schema Validation and Conversion
```python
class SchemaValidator:
    """Advanced schema validation and conversion."""
    
    @staticmethod
    def validate_connection(src_schema: Schema, dst_schema: Schema) -> bool:
        """Validate if two schemas can be connected."""
        # Check component compatibility
        src_components = {comp.name: comp for comp in src_schema.components}
        dst_components = {comp.name: comp for comp in dst_schema.components}
        
        # Must have matching component names
        if set(src_components.keys()) != set(dst_components.keys()):
            return False
        
        # Check channel compatibility within each component
        for comp_name in src_components:
            src_comp = src_components[comp_name]
            dst_comp = dst_components[comp_name]
            
            if not SchemaValidator._components_compatible(src_comp, dst_comp):
                return False
        
        return True
    
    @staticmethod
    def _components_compatible(src: Component, dst: Component) -> bool:
        """Check if two components are compatible."""
        # Same number of channels
        if len(src.channels) != len(dst.channels):
            return False
        
        # Channel names must match
        src_names = [ch.id for ch in src.channels]
        dst_names = [ch.id for ch in dst.channels]
        if src_names != dst_names:
            return False
        
        # Check units compatibility
        for src_ch, dst_ch in zip(src.channels, dst.channels):
            if not SchemaValidator._units_compatible(src_ch.units, dst_ch.units):
                return False
        
        return True
    
    @staticmethod
    def _units_compatible(src_units: Optional[str], dst_units: Optional[str]) -> bool:
        """Check if units are compatible."""
        if src_units == dst_units:
            return True
        
        # Define unit conversion groups
        unitless_group = {None, "unitless", "normalized"}
        angle_group = {"rad", "degrees", "turns"}
        
        if src_units in unitless_group and dst_units in unitless_group:
            return True
        if src_units in angle_group and dst_units in angle_group:
            return True
        
        return False
```

## Implementation Order

1. **Days 1-2**: Enhanced source nodes (SineSource, NoiseSource)
2. **Days 3-4**: Transform nodes (ScaleBias, ColorSpaceTransform, MathTransform)  
3. **Days 5-6**: Sink nodes (ConsoleSink, SACNSink)
4. **Days 7-8**: Advanced sinks (LIFXSink, FileSink) and CSV source
5. **Days 9-10**: Schema system enhancements and integration testing

## Performance Targets

- **Node Execution**: <1ms per node per frame for typical operations
- **Memory Usage**: <1MB per node for reasonable channel counts
- **Schema Validation**: <100μs per connection validation
- **Hardware Protocols**: <5ms latency for network protocols

## Validation Checklist

- [ ] All node types implemented with comprehensive tests
- [ ] Schema validation prevents incompatible connections
- [ ] Hardware protocol sinks tested with real devices
- [ ] Performance targets met for all node types
- [ ] Complex example scripts run successfully
- [ ] Error handling robust for all failure modes

## Dependencies

**Requires**: Phase 1 (Engine)  
**Enables**: Phase 3 (Web), Phase 4 (Advanced)

## Notes

- Prioritize commonly used nodes first
- Hardware protocol implementations should be optional (graceful degradation)
- Schema system is critical for preventing runtime errors
- Performance optimization should not compromise correctness
