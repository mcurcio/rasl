# Phase 0: Foundation & Testing Infrastructure

**Duration**: 3-5 days  
**Goal**: Establish solid testing foundation and validate core integration points

## Objectives

1. **Testing Infrastructure**: Complete test framework setup with fixtures and utilities
2. **Core Integration**: Validate that existing components work together
3. **Basic Node Implementation**: Implement minimal nodes needed for first end-to-end test
4. **CI/CD Setup**: Automated testing and quality gates

## Success Criteria

- [ ] All existing code has unit tests with >80% coverage
- [ ] Integration test framework operational
- [ ] `examples/simple_sine.py` loads successfully (even if execution fails)
- [ ] Basic nodes (SineSource, ScaleBias, ConsoleSink) have working implementations
- [ ] CI pipeline runs all tests automatically

## Tasks

### 1. Test Infrastructure Setup

**Test Framework Configuration** (Priority: Critical)
```python
# tests/conftest.py - Enhanced fixtures
@pytest.fixture
def clean_environment():
    """Reset global state between tests."""
    reset_connections()
    clear_exposed_parameters()
    yield
    reset_connections()
    clear_exposed_parameters()

@pytest.fixture
def test_scheduler():
    """Deterministic scheduler for testing."""
    return TestScheduler(frame_rate=60, deterministic=True)
```

**Test Utilities** (`tests/utils.py`):
```python
def create_test_graph(node_count=3):
    """Create predictable test graph."""
    sine = SineSource(freq=1.0, channels=4)
    scaler = ScaleBias(scale=0.5)
    console = TestSink()  # Captures output for verification
    
    sine >> scaler >> console
    return [sine, scaler, console]

def assert_graph_valid(nodes, sinks):
    """Validate graph structure."""
    assert len(nodes) > 0
    assert len(sinks) > 0
    # Check connections exist
    registry = get_connection_registry()
    assert len(registry.get_edges()) > 0
```

### 2. Core Type System Tests

**Frame and Schema Validation** (`tests/unit/test_types.py`):
```python
class TestFrame:
    def test_frame_creation(self):
        frame = Frame(t=1.0, dt=0.016, seq=60)
        assert frame.t == 1.0
        assert frame.dt == 0.016
        assert frame.seq == 60
    
    def test_frame_now_creation(self):
        frame1 = Frame.now(seq=0)
        time.sleep(0.01)
        frame2 = Frame.now(seq=1, last_time=frame1.t)
        
        assert frame2.seq == 1
        assert frame2.dt > 0
        assert frame2.t > frame1.t

class TestSchema:
    def test_schema_compatibility(self):
        rgb = RGB_SCHEMA
        hsv = HSV_SCHEMA
        
        assert rgb.is_compatible(rgb)
        assert not rgb.is_compatible(hsv)
    
    def test_channel_count(self):
        assert RGB_SCHEMA.channel_count() == 3
        assert SCALAR_SCHEMA.channel_count() == 1
```

### 3. Connection System Tests

**Port Connection Validation** (`tests/unit/test_connections.py`):
```python
class TestConnections:
    def test_basic_connection(self, clean_environment):
        sine = SineSource(channels=3)
        scaler = ScaleBias()
        
        # Connect nodes
        sine.ports.out >> scaler.ports.in
        
        # Verify connection registered
        registry = get_connection_registry()
        edges = registry.get_edges()
        
        assert len(edges) == 1
        assert edges[0].src_id == sine.id
        assert edges[0].dst_id == scaler.id
    
    def test_connection_validation(self):
        # Test schema mismatch detection
        sine = SineSource(channels=3)  # RGB output
        # TODO: Create node with incompatible input
        # Should raise ConnectionError
```

### 4. Basic Node Implementations

**SineSource Implementation** (`rasl/nodes/sources/sine.py`):
```python
class SineSource(BaseSource):
    TYPE = "SineSource"
    LIVENESS = Liveness.STREAM
    
    def __init__(self, freq=1.0, amplitude=1.0, channels=1, **kwargs):
        super().__init__(**kwargs)
        self.freq = freq
        self.amplitude = amplitude
        self.channels = channels
        self._phase = 0.0
    
    def param_spec(self):
        return {
            "freq": {"type": float, "default": 1.0, "min": 0.1, "max": 100.0},
            "amplitude": {"type": float, "default": 1.0, "min": 0.0, "max": 2.0},
            "channels": {"type": int, "default": 1, "min": 1, "max": 512}
        }
    
    def port_schema(self, name: str) -> Schema:
        if name == "out":
            return SCALAR_SCHEMA  # For now, single scalar output
        raise ValueError(f"Unknown port: {name}")
    
    def sample(self, frame: Frame) -> Mapping[str, NDArrayLike]:
        # Simple sine wave generation
        import numpy as np
        
        # Calculate current phase
        phase = 2 * np.pi * self.freq * frame.t
        
        # Generate sine wave for all channels
        values = np.full(self.channels, 
                        self.amplitude * np.sin(phase))
        
        return {"out": values}
```

**ScaleBias Implementation** (`rasl/nodes/transforms/scale_bias.py`):
```python
class ScaleBias(BaseTransform):
    TYPE = "ScaleBias"
    
    def __init__(self, scale=1.0, bias=0.0, **kwargs):
        super().__init__(**kwargs)
        self.scale = scale
        self.bias = bias
    
    def param_spec(self):
        return {
            "scale": {"type": float, "default": 1.0, "min": 0.0, "max": 10.0},
            "bias": {"type": float, "default": 0.0, "min": -2.0, "max": 2.0}
        }
    
    def port_schema(self, name: str) -> Schema:
        # Pass-through schema (same input and output)
        return SCALAR_SCHEMA
    
    def evaluate(self, frame: Frame, **inputs: NDArrayLike) -> Mapping[str, NDArrayLike]:
        import numpy as np
        
        input_data = inputs.get("in")
        if input_data is None:
            raise ValueError("ScaleBias requires 'in' input")
        
        # Apply scale and bias
        output_data = np.array(input_data) * self.scale + self.bias
        
        return {"out": output_data}
```

**ConsoleSink Implementation** (`rasl/nodes/sinks/console.py`):
```python
class ConsoleSink(BaseSink):
    TYPE = "ConsoleSink"
    
    def __init__(self, format="simple", update_interval=1.0, **kwargs):
        super().__init__(**kwargs)
        self.format = format
        self.update_interval = update_interval
        self._last_update = 0.0
        self._frame_count = 0
    
    def param_spec(self):
        return {
            "format": {"type": str, "default": "simple", 
                      "enum": ["simple", "table", "json"]},
            "update_interval": {"type": float, "default": 1.0, 
                               "min": 0.1, "max": 10.0}
        }
    
    def port_schema(self, name: str) -> Schema:
        if name == "in":
            return SCALAR_SCHEMA
        raise ValueError(f"Unknown port: {name}")
    
    def emit(self, frame: Frame, **inputs: NDArrayLike) -> None:
        self._frame_count += 1
        
        # Rate limit console output
        if frame.t - self._last_update < self.update_interval:
            return
        
        self._last_update = frame.t
        
        input_data = inputs.get("in")
        if input_data is not None:
            if self.format == "simple":
                print(f"Frame {frame.seq}: {input_data}")
            elif self.format == "table":
                # TODO: Rich table formatting
                print(f"Frame {frame.seq:6d} | t={frame.t:8.3f} | {input_data}")
```

### 5. Script Loading Integration Tests

**Script Loading Validation** (`tests/integration/test_script_loading.py`):
```python
class TestScriptLoading:
    async def test_simple_sine_loading(self, clean_environment):
        """simple_sine.py should load without errors."""
        loader = ScriptLoader()
        script_path = Path("examples/simple_sine.py")
        
        # This should not raise an exception
        spec = await loader.load_script(script_path)
        
        # Validate graph structure
        assert len(spec.nodes) >= 3  # sine, scaler, console
        assert len(spec.sinks) >= 1  # console
        assert spec.script_path == script_path
        
        # Validate node types
        node_types = [node.TYPE for node in spec.nodes]
        assert "SineSource" in node_types
        assert "ScaleBias" in node_types
        assert "ConsoleSink" in node_types
    
    async def test_parameter_exposure(self, clean_environment):
        """Parameter exposure should work correctly."""
        loader = ScriptLoader()
        script_path = Path("examples/simple_sine.py")
        
        spec = await loader.load_script(script_path)
        
        # Should have exposed parameters
        assert len(spec.exposed_parameters) > 0
        
        # Validate parameter structure
        param_names = [p["name"] for p in spec.exposed_parameters]
        assert "sine.freq" in param_names
```

### 6. Basic Engine Integration

**Engine Tick Test** (`tests/integration/test_engine_basic.py`):
```python
class TestEngineBasic:
    async def test_single_tick_execution(self, clean_environment):
        """Engine should execute one frame without errors."""
        # Create minimal graph
        sine = SineSource(freq=1.0, channels=1)
        console = TestSink()  # Use test sink to capture output
        sine >> console
        
        # Create engine with test scheduler
        scheduler = TestScheduler()
        engine = Engine(sinks=[console], scheduler=scheduler)
        
        # Execute one frame
        await engine.tick_once()
        
        # Verify execution occurred
        assert console.last_data is not None
        assert "in" in console.last_data
        assert len(console.last_data["in"]) == 1
```

### 7. CI/CD Pipeline Setup

**GitHub Actions** (`.github/workflows/test.yml`):
```yaml
name: Test Suite
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.9, 3.10, 3.11]
    
    steps:
    - uses: actions/checkout@v3
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v3
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        pip install -e .
        pip install pytest pytest-cov pytest-asyncio
    
    - name: Run unit tests
      run: pytest tests/unit/ -v --cov=rasl
    
    - name: Run integration tests
      run: pytest tests/integration/ -v
    
    - name: Check coverage
      run: pytest --cov=rasl --cov-fail-under=80
```

## Implementation Order

1. **Day 1**: Test infrastructure and fixtures
2. **Day 2**: Core type system tests and basic node implementations
3. **Day 3**: Connection system tests and script loading integration
4. **Day 4**: Basic engine integration and CI setup
5. **Day 5**: Bug fixes, documentation, and validation

## Validation Checklist

- [ ] All tests pass with >80% coverage
- [ ] `examples/simple_sine.py` loads successfully
- [ ] Basic nodes have working implementations
- [ ] Connection system validated with tests
- [ ] CI pipeline operational
- [ ] Documentation updated for new components

## Dependencies

**Blocked by**: None (foundation phase)  
**Blocks**: Phase 1 (Engine), Phase 2 (Nodes), Phase 3 (Web)

## Notes

- Focus on getting the testing infrastructure right - it will pay dividends later
- Keep node implementations minimal but functional
- Don't worry about performance optimization yet
- Prioritize integration over individual component perfection
