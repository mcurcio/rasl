# Phase 1: Core Engine Integration

**Duration**: 5-7 days  
**Goal**: Complete engine execution loop and achieve first working end-to-end system

## Objectives

1. **Engine Execution**: Complete the execution loop with scheduler, executor, and monitoring
2. **Graph Validation**: Implement comprehensive graph validation and error handling
3. **Parameter System**: Complete parameter exposure and runtime updates
4. **End-to-End Integration**: `rasl run examples/simple_sine.py` works completely

## Success Criteria

- [ ] Engine executes graphs at stable frame rates (30-60 FPS)
- [ ] Real-time parameter updates work correctly
- [ ] Error handling and recovery functional
- [ ] All example scripts run successfully
- [ ] Performance meets basic requirements (<10ms per frame for simple graphs)

## Tasks

### 1. Engine Execution Loop

**Core Engine Implementation** (`rasl/core/engine.py`):
```python
class Engine:
    def __init__(self, sinks: List[Sink], scheduler: Scheduler, 
                 cadence="drop", autofix_rate=True):
        self.sinks = sinks
        self.scheduler = scheduler
        self.cadence = cadence
        self.autofix_rate = autofix_rate
        
        # Initialize components
        self.executor = Executor()
        self.validator = Validator()
        self.monitor = Monitor()
        
        # Discover and validate graph
        self.graph = self._discover_graph()
        self.validator.validate_global(self.graph)
        
        # Runtime state
        self._running = False
        self._frame_count = 0
        self._start_time = None
    
    async def start(self):
        """Start the execution loop."""
        if self._running:
            raise EngineStartError("Engine already running")
        
        logger.info("Starting RASL engine")
        self._running = True
        self._start_time = time.perf_counter()
        
        try:
            # Initialize all sources
            for node in self.graph.nodes():
                if isinstance(node, Source):
                    node.open()
            
            # Start execution loop
            async for frame in self.scheduler.frames():
                if not self._running:
                    break
                
                await self._execute_frame(frame)
                self._frame_count += 1
                
        except Exception as e:
            logger.error(f"Engine execution failed: {e}")
            raise
        finally:
            await self._cleanup()
    
    async def _execute_frame(self, frame: Frame):
        """Execute one frame of the graph."""
        frame_start = time.perf_counter()
        
        try:
            # Reset executor cache for new frame
            self.executor.reset_frame_cache(frame)
            
            # Execute all sinks (pulls data through graph)
            for sink in self.sinks:
                await self._execute_sink(sink, frame)
            
            # Update monitoring
            frame_time = time.perf_counter() - frame_start
            self.monitor.record_frame(frame, frame_time)
            
            # Check frame budget
            if frame_time > frame.dt * 0.8:  # 80% of frame time
                logger.warning(f"Frame {frame.seq} exceeded budget: {frame_time:.3f}s")
        
        except Exception as e:
            logger.error(f"Frame {frame.seq} execution failed: {e}")
            self.monitor.record_error(frame, e)
            
            if self.cadence == "drop":
                # Continue with next frame
                pass
            else:
                raise
    
    async def _execute_sink(self, sink: Sink, frame: Frame):
        """Execute a sink node, pulling data through the graph."""
        try:
            # Gather inputs for this sink
            inputs = {}
            for port_name in sink.ports.list(kind="in"):
                port_ref = getattr(sink.ports, port_name.name)
                data = await self.executor.materialize(port_ref, frame)
                inputs[port_name.name] = data
            
            # Execute sink
            sink.emit(frame, **inputs)
            
        except Exception as e:
            logger.error(f"Sink {sink.id} execution failed: {e}")
            raise
```

**Test: Engine Execution** (`tests/integration/test_engine_execution.py`):
```python
class TestEngineExecution:
    async def test_basic_execution_loop(self, clean_environment):
        """Engine should execute multiple frames correctly."""
        # Create test graph
        sine = SineSource(freq=1.0, channels=1)
        console = TestSink()
        sine >> console
        
        # Create engine with controlled scheduler
        scheduler = TestScheduler(frame_rate=60, max_frames=10)
        engine = Engine(sinks=[console], scheduler=scheduler)
        
        # Run engine
        await engine.start()
        
        # Verify execution
        assert console.frame_count == 10
        assert len(console.received_data) == 10
        
        # Verify data progression
        first_frame = console.received_data[0]
        last_frame = console.received_data[-1]
        assert last_frame[0].seq > first_frame[0].seq
    
    async def test_parameter_updates_during_execution(self):
        """Parameter changes should take effect immediately."""
        sine = SineSource(freq=1.0, channels=1)
        console = TestSink()
        sine >> console
        
        scheduler = TestScheduler(frame_rate=60, max_frames=20)
        engine = Engine(sinks=[console], scheduler=scheduler)
        
        # Start execution in background
        engine_task = asyncio.create_task(engine.start())
        
        # Wait a few frames, then change parameter
        await asyncio.sleep(0.1)
        engine.patch(sine, freq=2.0)
        
        # Wait for completion
        await engine_task
        
        # Verify parameter change took effect
        # (Would need to analyze sine wave frequency in output)
        assert console.frame_count == 20
```

### 2. Executor Implementation

**Lazy Evaluation Executor** (`rasl/core/executor.py`):
```python
class Executor:
    def __init__(self):
        self._frame_cache = {}  # (node_id, port_name) -> data
        self._current_frame = None
    
    async def materialize(self, port: PortRef, frame: Frame) -> NDArrayLike:
        """Materialize data for a port, using lazy evaluation."""
        if self._current_frame != frame:
            self.reset_frame_cache(frame)
        
        cache_key = (port.node_id, port.name)
        
        # Check cache first
        if cache_key in self._frame_cache:
            return self._frame_cache[cache_key]
        
        # Materialize the data
        node = self._get_node(port.node_id)
        
        if isinstance(node, Source):
            data = await self._materialize_source(node, port, frame)
        elif isinstance(node, Transform):
            data = await self._materialize_transform(node, port, frame)
        else:
            raise ValueError(f"Cannot materialize output from {type(node)}")
        
        # Cache result
        self._frame_cache[cache_key] = data
        return data
    
    async def _materialize_source(self, source: Source, port: PortRef, frame: Frame):
        """Materialize data from a source node."""
        result = source.sample(frame)
        
        if port.name not in result:
            raise ValueError(f"Source {source.id} did not produce port {port.name}")
        
        return result[port.name]
    
    async def _materialize_transform(self, transform: Transform, port: PortRef, frame: Frame):
        """Materialize data from a transform node."""
        # Gather inputs
        inputs = {}
        for input_port in transform.ports.list(kind="in"):
            # Find connection to this input
            src_port = self._find_source_port(input_port)
            if src_port:
                inputs[input_port.name] = await self.materialize(src_port, frame)
        
        # Execute transform
        result = transform.evaluate(frame, **inputs)
        
        if port.name not in result:
            raise ValueError(f"Transform {transform.id} did not produce port {port.name}")
        
        return result[port.name]
```

**Test: Executor** (`tests/unit/test_executor.py`):
```python
class TestExecutor:
    async def test_lazy_evaluation(self):
        """Executor should only evaluate nodes when needed."""
        # Create graph with unused branch
        sine1 = TestSource(name="sine1")
        sine2 = TestSource(name="sine2")  # This won't be used
        transform = TestTransform()
        sink = TestSink()
        
        sine1 >> transform >> sink
        # sine2 is not connected
        
        executor = Executor()
        frame = Frame(t=0.0, dt=0.016, seq=0)
        
        # Execute sink (should only trigger sine1 and transform)
        await executor._execute_sink(sink, frame)
        
        assert sine1.call_count == 1
        assert sine2.call_count == 0  # Should not be called
        assert transform.call_count == 1
    
    async def test_frame_caching(self):
        """Data should be cached within a frame."""
        source = TestSource()
        transform1 = TestTransform()
        transform2 = TestTransform()
        sink = TestSink()
        
        # Diamond pattern: source feeds both transforms, both feed sink
        source >> transform1 >> sink
        source >> transform2 >> sink
        
        executor = Executor()
        frame = Frame(t=0.0, dt=0.016, seq=0)
        
        await executor._execute_sink(sink, frame)
        
        # Source should only be called once despite feeding two transforms
        assert source.call_count == 1
```

### 3. Scheduler Implementation

**Fixed Rate Scheduler** (`rasl/core/scheduler.py`):
```python
class FixedRateScheduler:
    def __init__(self, clock: Clock, target_fps: float = 60.0):
        self.clock = clock
        self.target_fps = target_fps
        self.frame_interval = 1.0 / target_fps
        
        self._running = False
        self._frame_count = 0
        self._start_time = None
        self._last_frame_time = None
    
    async def frames(self) -> AsyncIterator[Frame]:
        """Generate frames at the target rate."""
        self._running = True
        self._start_time = self.clock.now()
        self._last_frame_time = self._start_time
        
        while self._running:
            current_time = self.clock.now()
            
            # Calculate frame timing
            if self._frame_count == 0:
                dt = 0.0
            else:
                dt = current_time - self._last_frame_time
            
            # Create frame
            frame = Frame(
                t=current_time - self._start_time,
                dt=dt,
                seq=self._frame_count
            )
            
            yield frame
            
            self._frame_count += 1
            self._last_frame_time = current_time
            
            # Sleep until next frame
            next_frame_time = self._start_time + (self._frame_count * self.frame_interval)
            sleep_time = next_frame_time - self.clock.now()
            
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
            elif sleep_time < -self.frame_interval * 0.5:
                # More than half a frame late - log warning
                logger.warning(f"Frame {self._frame_count} late by {-sleep_time:.3f}s")
    
    def stop(self):
        """Stop frame generation."""
        self._running = False
```

**Test: Scheduler** (`tests/unit/test_scheduler.py`):
```python
class TestScheduler:
    async def test_fixed_rate_timing(self):
        """Scheduler should generate frames at consistent intervals."""
        clock = TestClock()
        scheduler = FixedRateScheduler(clock, target_fps=60)
        
        frames = []
        async for frame in scheduler.frames():
            frames.append(frame)
            if len(frames) >= 10:
                scheduler.stop()
                break
        
        # Verify frame timing
        assert len(frames) == 10
        
        # Check sequence numbers
        for i, frame in enumerate(frames):
            assert frame.seq == i
        
        # Check time progression (allowing for some variance)
        expected_dt = 1.0 / 60.0
        for i in range(1, len(frames)):
            dt = frames[i].dt
            assert abs(dt - expected_dt) < 0.001  # 1ms tolerance
```

### 4. Parameter System Integration

**Parameter Updates** (`rasl/core/engine.py` additions):
```python
class Engine:
    def patch(self, node: Node, **params: Any) -> None:
        """Update node parameters at runtime."""
        try:
            # Validate parameters
            param_spec = node.param_spec()
            for key, value in params.items():
                if key not in param_spec:
                    raise ValueError(f"Unknown parameter: {key}")
                
                # TODO: Add type and range validation
            
            # Apply parameters
            node.set_params(**params)
            
            # Log change
            logger.info(f"Updated {node.id}: {params}")
            
            # Notify monitor
            self.monitor.record_parameter_change(node.id, params)
            
        except Exception as e:
            logger.error(f"Parameter update failed for {node.id}: {e}")
            raise
```

**Test: Parameter Updates** (`tests/integration/test_parameters.py`):
```python
class TestParameterSystem:
    async def test_runtime_parameter_update(self):
        """Parameters should update during execution."""
        sine = SineSource(freq=1.0, channels=1)
        console = TestSink()
        sine >> console
        
        scheduler = TestScheduler(max_frames=20)
        engine = Engine(sinks=[console], scheduler=scheduler)
        
        # Start engine
        engine_task = asyncio.create_task(engine.start())
        
        # Wait a few frames
        await asyncio.sleep(0.1)
        
        # Update parameter
        engine.patch(sine, freq=2.0)
        
        # Verify parameter was updated
        assert sine.get_params()["freq"] == 2.0
        
        await engine_task
```

### 5. Graph Discovery and Validation

**Enhanced Graph Discovery** (`rasl/core/validator.py`):
```python
class Validator:
    def validate_global(self, graph: GraphView) -> None:
        """Perform comprehensive graph validation."""
        nodes = graph.nodes()
        edges = graph.edges()
        
        # Check for cycles
        self._check_for_cycles(nodes, edges)
        
        # Validate all connections
        self._validate_all_connections(nodes, edges)
        
        # Check for dangling inputs
        self._check_dangling_inputs(nodes, edges)
        
        # Validate rate compatibility
        self._validate_rates(nodes, edges)
        
        logger.info(f"Graph validation passed: {len(nodes)} nodes, {len(edges)} edges")
    
    def _check_for_cycles(self, nodes: List[Node], edges: List[Edge]) -> None:
        """Detect cycles in the graph."""
        # Build adjacency list
        adj = defaultdict(list)
        for edge in edges:
            adj[edge.src_id].append(edge.dst_id)
        
        # DFS cycle detection
        visited = set()
        rec_stack = set()
        
        def has_cycle(node_id: str) -> bool:
            if node_id in rec_stack:
                return True
            if node_id in visited:
                return False
            
            visited.add(node_id)
            rec_stack.add(node_id)
            
            for neighbor in adj[node_id]:
                if has_cycle(neighbor):
                    return True
            
            rec_stack.remove(node_id)
            return False
        
        for node in nodes:
            if node.id not in visited:
                if has_cycle(node.id):
                    raise ValidationError(f"Cycle detected involving node {node.id}")
```

### 6. End-to-End Integration

**Application Integration** (`rasl/app.py`):
```python
class RASLApp:
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.loader = ScriptLoader()
        self.engine = None
        self._script_path = None
    
    async def load_script(self, script_path: Path) -> None:
        """Load and validate a RASL script."""
        logger.info(f"Loading script: {script_path}")
        
        spec = await self.loader.load_script(script_path)
        self._script_path = script_path
        
        # Create scheduler
        clock = MonotonicClock()
        scheduler = FixedRateScheduler(clock, self.config.frame_rate)
        
        # Create engine
        self.engine = Engine(
            sinks=spec.sinks,
            scheduler=scheduler,
            cadence=self.config.cadence
        )
        
        logger.info(f"Loaded graph: {len(spec.nodes)} nodes, {len(spec.sinks)} sinks")
    
    async def run(self) -> None:
        """Run the loaded script."""
        if not self.engine:
            raise RuntimeError("No script loaded")
        
        logger.info("Starting RASL execution")
        await self.engine.start()
```

**Test: End-to-End** (`tests/e2e/test_complete_workflow.py`):
```python
class TestCompleteWorkflow:
    async def test_simple_sine_complete(self):
        """Complete workflow: load simple_sine.py and run it."""
        app = RASLApp()
        
        # Load script
        await app.load_script(Path("examples/simple_sine.py"))
        
        # Run for a short time
        run_task = asyncio.create_task(app.run())
        await asyncio.sleep(1.0)  # Run for 1 second
        
        # Stop execution
        app.engine.stop()
        await run_task
        
        # Verify execution occurred
        assert app.engine._frame_count > 50  # Should have run ~60 frames
```

## Implementation Order

1. **Day 1-2**: Core engine execution loop and scheduler
2. **Day 3**: Executor implementation with lazy evaluation
3. **Day 4**: Parameter system and graph validation
4. **Day 5**: End-to-end integration and testing
5. **Day 6-7**: Performance optimization and bug fixes

## Performance Requirements

- **Frame Rate**: Maintain 60 FPS for graphs with <20 nodes
- **Frame Budget**: <10ms execution time for simple graphs
- **Memory**: <50MB for basic examples
- **Startup Time**: <2 seconds to first frame

## Validation Checklist

- [ ] Engine executes at stable frame rates
- [ ] All example scripts run successfully
- [ ] Parameter updates work in real-time
- [ ] Error handling prevents crashes
- [ ] Performance requirements met
- [ ] Integration tests pass

## Dependencies

**Requires**: Phase 0 (Foundation)  
**Enables**: Phase 2 (Nodes), Phase 3 (Web)

## Notes

- Focus on correctness over performance initially
- Comprehensive error handling is critical for real-time systems
- Keep the execution loop simple and predictable
- Monitor performance from the beginning
