# RASL Quick Start Guide - Single Engineer

## TL;DR: Get RASL Working in 2 Weeks

This is the streamlined path to get RASL working end-to-end as quickly as possible.

## Week 1: Core Implementation

### Day 1-2: Ticket #1 - SineSource Implementation

**Goal**: Get sine wave generation working

```bash
# Start here
cd /Users/matt/Code/rasl

# Create test first (TDD approach)
touch tests/unit/nodes/test_sine_source.py
```

**Test to write** (`tests/unit/nodes/test_sine_source.py`):
```python
def test_sine_source_basic():
    sine = SineSource(freq=1.0, amplitude=1.0, channels=1)
    sine.open()
    
    frame = Frame(t=0.0, dt=0.0, seq=0)
    result = sine.sample(frame)
    
    assert "out" in result
    assert len(result["out"]) == 1
    assert abs(result["out"][0] - 0.0) < 1e-6  # sin(0) = 0
```

**Implementation** (`rasl/nodes/sources/sine.py`):
```python
def sample(self, frame: Frame) -> Mapping[str, NDArrayLike]:
    import numpy as np
    
    phase = 2 * np.pi * self.freq * frame.t + self.phase
    values = np.full(self.channels, self.amplitude * np.sin(phase))
    
    return {"out": values}
```

### Day 3: Ticket #2 & #3 - ScaleBias + ConsoleSink

**ScaleBias** (`rasl/nodes/transforms/scale_bias.py`):
```python
def evaluate(self, frame: Frame, **inputs: NDArrayLike) -> Mapping[str, NDArrayLike]:
    input_data = inputs.get("in")
    if input_data is None:
        raise ValueError("ScaleBias requires 'in' input")
    
    result = np.array(input_data) * self.scale + self.bias
    return {"out": result}
```

**ConsoleSink** (`rasl/nodes/sinks/console.py`):
```python
def emit(self, frame: Frame, **inputs: NDArrayLike) -> None:
    if frame.t - self._last_update < self.update_interval:
        return
    
    self._last_update = frame.t
    input_data = inputs.get("in")
    
    if input_data is not None:
        print(f"Frame {frame.seq:6d}: {input_data}")
```

### Day 4-5: Ticket #4 - Engine Execution Loop

**Critical**: Get the engine actually running frames

**Engine** (`rasl/core/engine.py`):
```python
async def start(self):
    self._running = True
    
    # Initialize sources
    for node in self.graph.nodes():
        if isinstance(node, Source):
            node.open()
    
    # Main execution loop
    async for frame in self.scheduler.frames():
        if not self._running:
            break
        await self._execute_frame(frame)

async def _execute_frame(self, frame: Frame):
    # Execute all sinks (pulls data through graph)
    for sink in self.sinks:
        inputs = {}
        # TODO: Implement input gathering from connections
        sink.emit(frame, **inputs)
```

## Week 2: Integration & Web Interface

### Day 6-7: Ticket #5 - Script Loading Integration

**Goal**: `rasl run examples/simple_sine.py` works

**Fix script loading** (`rasl/app.py`):
```python
async def run_script(script_path: Path):
    loader = ScriptLoader()
    spec = await loader.load_script(script_path)
    
    scheduler = FixedRateScheduler(MonotonicClock(), 60.0)
    engine = Engine(sinks=spec.sinks, scheduler=scheduler)
    
    await engine.start()
```

### Day 8-9: Ticket #6 - Parameter System

**Goal**: Runtime parameter updates work

### Day 10: Ticket #7 - Basic REST API

**Goal**: Web server responds to API calls

**FastAPI setup** (`rasl/server/api.py`):
```python
@app.get("/api/graph")
async def get_graph():
    return {"nodes": [], "edges": []}

@app.patch("/api/nodes/{node_id}")
async def update_node(node_id: str, params: dict):
    # Update node parameters
    return {"status": "updated"}
```

## Success Checkpoints

### End of Week 1
```bash
# This should work:
python -m pytest tests/unit/nodes/ -v
python -c "
from rasl.nodes.sources.sine import SineSource
from rasl.core.types import Frame
sine = SineSource(freq=1.0, channels=1)
sine.open()
result = sine.sample(Frame(t=0.0, dt=0.0, seq=0))
print('Success:', result)
"
```

### End of Week 2
```bash
# This should work:
rasl run examples/simple_sine.py

# And this should respond:
curl http://localhost:8080/api/graph
```

## Minimum Viable Product (MVP) Definition

After 2 weeks, you should have:

1. **Working Nodes**: SineSource, ScaleBias, ConsoleSink
2. **Engine Execution**: Frames execute at stable rate
3. **Script Loading**: Examples load and run
4. **Basic Web API**: Graph inspection and parameter updates
5. **Console Output**: Real-time data display

## What to Skip Initially

- Complex node types (NoiseSource, CSVSource)
- Advanced web UI (graph visualization)
- Hardware protocols (sACN, LIFX)
- Export system (FSEQ)
- Plugin system
- Performance optimization

## Development Tips

### Use TDD Religiously
```bash
# Always start with failing test
pytest tests/unit/nodes/test_sine_source.py::test_new_feature -v
# Implement minimal code to pass
# Refactor while keeping tests green
```

### Debug with Simple Scripts
Create `debug_sine.py`:
```python
from rasl.nodes.sources.sine import SineSource
from rasl.core.types import Frame

sine = SineSource(freq=1.0, channels=1)
sine.open()

for i in range(10):
    frame = Frame(t=i*0.1, dt=0.1, seq=i)
    result = sine.sample(frame)
    print(f"t={frame.t:.1f}: {result['out'][0]:.3f}")
```

### Focus on Integration
Don't get stuck perfecting individual components. Get the whole system working first, then optimize.

### Use Existing Code
The codebase already has good structure. Build on what's there rather than rewriting.

## Emergency Shortcuts

If falling behind, these shortcuts maintain functionality:

1. **Skip multi-channel support initially** - Start with single channel
2. **Hardcode simple scheduler** - Fixed 10fps instead of configurable
3. **Skip parameter validation** - Basic type checking only
4. **Minimal web UI** - Just JSON responses, no HTML
5. **Skip error handling** - Let exceptions bubble up initially

The goal is working end-to-end functionality, not perfection.
