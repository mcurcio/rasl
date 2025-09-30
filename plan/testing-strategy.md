# RASL Testing Strategy

## Test-Driven Development Approach

RASL follows a strict TDD approach to ensure reliability and maintainability of the real-time animation system.

## Testing Philosophy

### 1. Test First, Always
- Write failing tests before any implementation
- Tests define the contract and expected behavior
- Implementation should do the minimum to make tests pass

### 2. Fast Feedback Loop
- Unit tests run in <5 seconds
- Integration tests run in <30 seconds
- Full test suite runs in <2 minutes

### 3. Real-World Scenarios
- Tests use actual node graphs, not mocks
- Performance tests with realistic data sizes
- Error conditions tested extensively

## Test Categories

### Unit Tests (`tests/unit/`)

**Core Types** (`test_types.py`):
```python
def test_frame_creation():
    """Frame objects should have consistent timing."""
    frame = Frame(t=1.0, dt=0.016, seq=60)
    assert frame.t == 1.0
    assert frame.dt == 0.016
    assert frame.seq == 60

def test_schema_compatibility():
    """Schemas should validate compatibility correctly."""
    rgb = RGB_SCHEMA
    hsv = HSV_SCHEMA
    assert not rgb.is_compatible(hsv)
    assert rgb.is_compatible(rgb)
```

**Node Behavior** (`test_nodes.py`):
```python
def test_sine_source_output():
    """SineSource should generate expected waveform."""
    sine = SineSource(freq=1.0, amplitude=1.0, channels=1)
    sine.open()
    
    frame = Frame(t=0.0, dt=0.0, seq=0)
    result = sine.sample(frame)
    
    assert "out" in result
    assert len(result["out"]) == 1
    assert result["out"][0] == 0.0  # sin(0) = 0
```

**Connection System** (`test_connections.py`):
```python
def test_port_connection():
    """Port connections should validate schemas."""
    sine = SineSource(channels=3)
    scaler = ScaleBias()
    
    # This should work
    sine.ports.out >> scaler.ports.in
    
    # Verify connection registered
    registry = get_connection_registry()
    edges = registry.get_edges()
    assert len(edges) == 1
    assert edges[0].src_id == sine.id
```

### Integration Tests (`tests/integration/`)

**Script Loading** (`test_script_loading.py`):
```python
async def test_simple_sine_loading():
    """simple_sine.py should load and validate correctly."""
    loader = ScriptLoader()
    script_path = Path("examples/simple_sine.py")
    
    spec = await loader.load_script(script_path)
    
    assert len(spec.nodes) == 3  # sine, scaler, console
    assert len(spec.sinks) == 1  # console
    assert len(spec.exposed_parameters) == 3
```

**Engine Execution** (`test_engine_execution.py`):
```python
async def test_engine_single_frame():
    """Engine should execute one frame correctly."""
    # Create simple graph
    sine = SineSource(freq=1.0, channels=1)
    console = ConsoleSink()
    sine >> console
    
    # Create engine
    scheduler = TestScheduler()  # Deterministic for testing
    engine = Engine(sinks=[console], scheduler=scheduler)
    
    # Execute one frame
    await engine.tick_once()
    
    # Verify execution
    assert console.last_data is not None
    assert len(console.last_data) == 1
```

**Web API** (`test_web_api.py`):
```python
async def test_graph_endpoint():
    """GET /api/graph should return current graph state."""
    # Setup engine with test graph
    engine = create_test_engine()
    api = HttpApi(engine)
    
    response = await api.get_graph()
    
    assert "nodes" in response
    assert "edges" in response
    assert len(response["nodes"]) > 0
```

### End-to-End Tests (`tests/e2e/`)

**Complete Workflows** (`test_workflows.py`):
```python
async def test_complete_sine_workflow():
    """Full workflow: load script, start engine, web interface."""
    # Start RASL application
    app = RASLApp()
    await app.load_script("examples/simple_sine.py")
    await app.start()
    
    # Verify web interface accessible
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8080/api/graph")
        assert response.status_code == 200
        
        # Verify real-time data
        response = await client.get("http://localhost:8080/api/metrics")
        assert response.status_code == 200
        metrics = response.json()
        assert metrics["frame_rate"] > 0
    
    await app.stop()
```

## Test Infrastructure

### Test Fixtures (`tests/conftest.py`)

```python
@pytest.fixture
def test_scheduler():
    """Deterministic scheduler for testing."""
    return TestScheduler(frame_rate=60)

@pytest.fixture
def simple_graph():
    """Standard test graph: sine -> scaler -> console."""
    sine = SineSource(freq=1.0, channels=4)
    scaler = ScaleBias(scale=0.5, bias=0.2)
    console = ConsoleSink()
    
    sine >> scaler >> console
    return [sine, scaler, console]

@pytest.fixture
async def test_engine(simple_graph, test_scheduler):
    """Engine with test graph loaded."""
    sinks = [node for node in simple_graph if isinstance(node, Sink)]
    engine = Engine(sinks=sinks, scheduler=test_scheduler)
    yield engine
    await engine.stop()
```

### Mock Objects

**TestScheduler** - Deterministic frame generation:
```python
class TestScheduler:
    def __init__(self, frame_rate=60):
        self.frame_rate = frame_rate
        self.frame_count = 0
    
    async def frames(self):
        while True:
            dt = 1.0 / self.frame_rate
            t = self.frame_count * dt
            yield Frame(t=t, dt=dt, seq=self.frame_count)
            self.frame_count += 1
```

**TestSink** - Captures data for verification:
```python
class TestSink(BaseSink):
    def __init__(self):
        super().__init__()
        self.received_data = []
        self.last_data = None
    
    def emit(self, frame, **inputs):
        self.last_data = inputs
        self.received_data.append((frame, inputs))
```

## Performance Testing

### Benchmarks (`tests/performance/`)

```python
def test_engine_performance():
    """Engine should maintain 60fps with typical graph."""
    # Create complex graph (10 nodes, 20 connections)
    graph = create_complex_test_graph()
    engine = Engine(sinks=graph.sinks)
    
    # Measure execution time
    start_time = time.perf_counter()
    for _ in range(600):  # 10 seconds at 60fps
        await engine.tick_once()
    end_time = time.perf_counter()
    
    elapsed = end_time - start_time
    assert elapsed < 12.0  # Allow 20% overhead
    
    # Verify frame rate
    actual_fps = 600 / elapsed
    assert actual_fps >= 50  # Allow some variance
```

### Memory Testing

```python
def test_memory_usage():
    """Engine should not leak memory during execution."""
    import psutil
    process = psutil.Process()
    
    initial_memory = process.memory_info().rss
    
    # Run for extended period
    engine = create_test_engine()
    for _ in range(3600):  # 1 minute at 60fps
        await engine.tick_once()
    
    final_memory = process.memory_info().rss
    memory_growth = final_memory - initial_memory
    
    # Should not grow more than 10MB
    assert memory_growth < 10 * 1024 * 1024
```

## Test Execution

### Local Development
```bash
# Run all tests
pytest

# Run specific category
pytest tests/unit/
pytest tests/integration/
pytest tests/e2e/

# Run with coverage
pytest --cov=rasl --cov-report=html

# Run performance tests
pytest tests/performance/ -v
```

### Continuous Integration
```bash
# Fast feedback (unit + integration)
pytest tests/unit/ tests/integration/ --maxfail=5

# Full validation (all tests)
pytest --cov=rasl --cov-fail-under=80

# Performance regression detection
pytest tests/performance/ --benchmark-only
```

## Test Data Management

### Fixtures Directory (`tests/fixtures/`)
- `scripts/` - Test RASL scripts
- `data/` - Sample CSV, audio files
- `configs/` - Test configurations

### Generated Test Data
```python
def generate_test_waveform(duration=1.0, sample_rate=60):
    """Generate predictable test data."""
    t = np.linspace(0, duration, int(duration * sample_rate))
    return np.sin(2 * np.pi * t)  # 1Hz sine wave
```

## Debugging and Diagnostics

### Test Debugging
```python
# Enable detailed logging in tests
@pytest.mark.debug
def test_with_logging():
    logging.basicConfig(level=logging.DEBUG)
    # Test implementation
```

### Performance Profiling
```python
# Profile slow tests
@pytest.mark.profile
def test_performance_bottleneck():
    import cProfile
    profiler = cProfile.Profile()
    profiler.enable()
    
    # Test implementation
    
    profiler.disable()
    profiler.dump_stats("test_profile.prof")
```

This testing strategy ensures that RASL development maintains high quality while moving quickly toward a working end-to-end system.
