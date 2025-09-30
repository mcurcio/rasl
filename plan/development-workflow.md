# RASL Development Workflow

## Test-Driven Development Process

### TDD Cycle for Each Feature

1. **Red**: Write failing test that defines expected behavior
2. **Green**: Write minimal code to make test pass
3. **Refactor**: Improve code while keeping tests green
4. **Integrate**: Ensure changes work with existing system

### Example: Implementing SineSource

#### Step 1: Write the Test First
```python
# tests/unit/nodes/test_sine_source.py
def test_sine_source_generates_correct_waveform():
    """SineSource should generate predictable sine wave values."""
    sine = SineSource(freq=1.0, amplitude=1.0, channels=1)
    sine.open()
    
    # Test at t=0 (should be 0)
    frame_0 = Frame(t=0.0, dt=0.0, seq=0)
    result_0 = sine.sample(frame_0)
    assert abs(result_0["out"][0] - 0.0) < 1e-6
    
    # Test at t=0.25 (should be 1.0 for 1Hz sine)
    frame_quarter = Frame(t=0.25, dt=0.25, seq=1)  
    result_quarter = sine.sample(frame_quarter)
    assert abs(result_quarter["out"][0] - 1.0) < 1e-6
```

#### Step 2: Run Test (Should Fail)
```bash
pytest tests/unit/nodes/test_sine_source.py::test_sine_source_generates_correct_waveform -v
# Expected: FAILED (NotImplementedError or incorrect values)
```

#### Step 3: Implement Minimal Solution
```python
# rasl/nodes/sources/sine.py
def sample(self, frame: Frame) -> Mapping[str, NDArrayLike]:
    import numpy as np
    
    # Calculate sine value at current time
    phase = 2 * np.pi * self.freq * frame.t
    value = self.amplitude * np.sin(phase)
    
    # Return array with correct number of channels
    values = np.full(self.channels, value)
    return {"out": values}
```

#### Step 4: Run Test (Should Pass)
```bash
pytest tests/unit/nodes/test_sine_source.py::test_sine_source_generates_correct_waveform -v
# Expected: PASSED
```

#### Step 5: Add More Tests and Refactor
```python
def test_sine_source_multi_channel():
    """Multi-channel sine should have phase relationships."""
    sine = SineSource(freq=1.0, channels=3, channel_phase_offset=np.pi/2)
    # ... test implementation

def test_sine_source_parameter_updates():
    """Frequency changes should take effect immediately."""
    sine = SineSource(freq=1.0, channels=1)
    # ... test parameter updates
```

## Development Environment Setup

### Required Tools
```bash
# Core development dependencies
pip install pytest pytest-cov pytest-asyncio
pip install black isort flake8 mypy
pip install pre-commit

# RASL dependencies  
pip install -e .

# Optional hardware protocol libraries
pip install sacn lifxlan  # For testing hardware sinks
```

### Pre-commit Hooks
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.3.0
    hooks:
      - id: black
        language_version: python3.9

  - repo: https://github.com/pycqa/isort
    rev: 5.12.0
    hooks:
      - id: isort

  - repo: https://github.com/pycqa/flake8
    rev: 6.0.0
    hooks:
      - id: flake8

  - repo: local
    hooks:
      - id: pytest
        name: pytest
        entry: pytest
        language: system
        pass_filenames: false
        always_run: true
```

### IDE Configuration

**VS Code Settings** (`.vscode/settings.json`):
```json
{
    "python.testing.pytestEnabled": true,
    "python.testing.unittestEnabled": false,
    "python.testing.pytestArgs": ["tests/"],
    "python.linting.enabled": true,
    "python.linting.flake8Enabled": true,
    "python.formatting.provider": "black",
    "editor.formatOnSave": true,
    "python.sortImports.args": ["--profile", "black"]
}
```

## Testing Workflow

### Daily Development Cycle

1. **Morning**: Run full test suite to ensure clean state
   ```bash
   pytest --cov=rasl --cov-report=html
   ```

2. **Feature Development**: TDD cycle for each component
   ```bash
   # Run specific test during development
   pytest tests/unit/nodes/test_sine_source.py -v -s
   
   # Run related tests
   pytest tests/unit/nodes/ -v
   ```

3. **Integration Testing**: Test with real examples
   ```bash
   # Test script loading
   python -m rasl validate examples/simple_sine.py
   
   # Test execution (if implemented)
   python -m rasl run examples/simple_sine.py --duration 5
   ```

4. **End of Day**: Full regression test
   ```bash
   pytest tests/ --maxfail=5
   ```

### Test Categories and Frequency

**Unit Tests** (Run continuously):
```bash
# Fast tests for immediate feedback
pytest tests/unit/ -x --tb=short
```

**Integration Tests** (Run before commits):
```bash  
# Slower but comprehensive
pytest tests/integration/ -v
```

**End-to-End Tests** (Run before releases):
```bash
# Full system validation
pytest tests/e2e/ -v --timeout=60
```

**Performance Tests** (Run weekly):
```bash
# Benchmark and regression detection
pytest tests/performance/ --benchmark-only
```

## Code Organization Standards

### File Structure Convention
```
rasl/
├── core/           # Core engine components
│   ├── types.py    # Data structures
│   ├── nodes.py    # Base node classes
│   ├── engine.py   # Execution engine
│   └── ...
├── nodes/          # Node implementations
│   ├── sources/    # Source nodes
│   ├── transforms/ # Transform nodes
│   └── sinks/      # Sink nodes
├── server/         # Web server
├── script/         # Script loading
└── ui/             # Web interface
```

### Naming Conventions

**Classes**: PascalCase
```python
class SineSource(BaseSource):
class ColorSpaceTransform(BaseTransform):
```

**Functions/Methods**: snake_case
```python
def sample(self, frame: Frame):
def get_connection_registry():
```

**Constants**: UPPER_SNAKE_CASE
```python
RGB_SCHEMA = Schema(...)
DEFAULT_FRAME_RATE = 60.0
```

**Files**: snake_case
```python
sine_source.py
color_space_transform.py
```

### Documentation Standards

**Docstring Format**:
```python
def sample(self, frame: Frame) -> Mapping[str, NDArrayLike]:
    """
    Generate data for the given frame.
    
    Args:
        frame: Current frame context with timing information
        
    Returns:
        Dictionary mapping port names to data arrays
        
    Raises:
        RuntimeError: If source is not properly initialized
    """
```

**Type Hints**: Always use for public APIs
```python
from typing import Optional, Mapping, List
from rasl.core.types import Frame, Schema

def port_schema(self, name: str) -> Schema:
    ...
```

## Debugging Workflow

### Common Debugging Scenarios

**Script Loading Issues**:
```bash
# Enable debug logging
RASL_LOG_LEVEL=DEBUG python -m rasl validate examples/simple_sine.py

# Check script syntax
python -m py_compile examples/simple_sine.py
```

**Engine Execution Problems**:
```python
# Add debug logging to engine
import logging
logging.basicConfig(level=logging.DEBUG)

# Use test scheduler for deterministic debugging
scheduler = TestScheduler(frame_rate=1)  # 1 FPS for easier debugging
```

**Node Implementation Issues**:
```python
# Test nodes in isolation
sine = SineSource(freq=1.0, channels=1)
sine.open()

frame = Frame(t=0.0, dt=0.0, seq=0)
result = sine.sample(frame)
print(f"Result: {result}")
```

### Performance Debugging

**Profile Slow Operations**:
```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# Run problematic code
await engine.tick_once()

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative').print_stats(20)
```

**Memory Usage Monitoring**:
```python
import psutil
import gc

process = psutil.Process()
print(f"Memory usage: {process.memory_info().rss / 1024 / 1024:.1f} MB")

# Force garbage collection
gc.collect()
```

This workflow ensures consistent, high-quality development while maintaining the rapid iteration needed for real-time systems.
