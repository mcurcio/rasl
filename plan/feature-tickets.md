# RASL Feature Tickets - Single Engineer Breakdown

## Overview

The original 4-phase plan (30+ days) is too large for efficient single-engineer execution. This breaks it down into 2-3 day feature tickets that deliver incremental value.

## Milestone 1: Basic Working System (2 weeks)

### Ticket #1: SineSource Implementation
**Effort**: 2 days  
**Priority**: Critical  
**Dependencies**: None

**Scope**:
- Implement `SineSource.sample()` method with proper sine wave generation
- Add parameter validation and bounds checking
- Write comprehensive unit tests
- Support multi-channel output with phase offsets

**Acceptance Criteria**:
- [ ] `SineSource(freq=1.0, channels=1)` generates correct sine values
- [ ] Multi-channel sources have proper phase relationships
- [ ] Parameter updates work (freq, amplitude, phase)
- [ ] Unit tests achieve >90% coverage
- [ ] Performance: <1ms execution time per frame

**Files to Modify**:
- `rasl/nodes/sources/sine.py`
- `tests/unit/nodes/test_sine_source.py`

---

### Ticket #2: ScaleBias Transform
**Effort**: 1 day  
**Priority**: Critical  
**Dependencies**: None

**Scope**:
- Implement `ScaleBias.evaluate()` with scale and bias operations
- Support per-channel scaling arrays
- Add parameter validation
- Write unit tests

**Acceptance Criteria**:
- [ ] Basic scale/bias operations work correctly
- [ ] Per-channel arrays supported
- [ ] Parameter bounds enforced
- [ ] Unit tests cover edge cases

**Files to Modify**:
- `rasl/nodes/transforms/scale_bias.py`
- `tests/unit/nodes/test_scale_bias.py`

---

### Ticket #3: ConsoleSink Implementation
**Effort**: 1 day  
**Priority**: Critical  
**Dependencies**: None

**Scope**:
- Implement `ConsoleSink.emit()` with formatting options
- Add rate limiting for console output
- Support table, JSON, and simple formats
- Write unit tests

**Acceptance Criteria**:
- [ ] Console output displays data correctly
- [ ] Rate limiting prevents spam
- [ ] Multiple format options work
- [ ] No performance impact on engine

**Files to Modify**:
- `rasl/nodes/sinks/console.py`
- `tests/unit/nodes/test_console_sink.py`

---

### Ticket #4: Engine Execution Loop
**Effort**: 3 days  
**Priority**: Critical  
**Dependencies**: Tickets #1-3

**Scope**:
- Complete `Engine.start()` and frame execution loop
- Implement `Executor.materialize()` for lazy evaluation
- Add basic error handling and recovery
- Integration with existing scheduler

**Acceptance Criteria**:
- [ ] Engine executes frames at stable rate
- [ ] Lazy evaluation works correctly
- [ ] Error handling prevents crashes
- [ ] Integration tests pass

**Files to Modify**:
- `rasl/core/engine.py`
- `rasl/core/executor.py`
- `tests/integration/test_engine_execution.py`

---

### Ticket #5: Script Loading Integration
**Effort**: 2 days  
**Priority**: Critical  
**Dependencies**: Ticket #4

**Scope**:
- Fix script loading to work with engine
- Ensure node discovery from globals works
- Integrate connection registry
- Get `examples/simple_sine.py` running

**Acceptance Criteria**:
- [ ] `rasl run examples/simple_sine.py` executes without errors
- [ ] Console shows real-time sine wave data
- [ ] Script hot-reload works
- [ ] All example scripts load successfully

**Files to Modify**:
- `rasl/script/loader.py`
- `rasl/app.py`
- `tests/integration/test_script_loading.py`

---

### Ticket #6: Parameter System
**Effort**: 2 days  
**Priority**: High  
**Dependencies**: Ticket #5

**Scope**:
- Complete parameter exposure system
- Implement runtime parameter updates
- Add parameter validation and bounds
- Integration with engine

**Acceptance Criteria**:
- [ ] `expose_parameter()` works in scripts
- [ ] Runtime parameter updates take effect immediately
- [ ] Parameter bounds are enforced
- [ ] Web API can update parameters

**Files to Modify**:
- `rasl/script/api.py`
- `rasl/core/engine.py`
- `tests/integration/test_parameters.py`

## Milestone 2: Web Interface (1 week)

### Ticket #7: Basic REST API
**Effort**: 2 days  
**Priority**: High  
**Dependencies**: Ticket #6

**Scope**:
- Implement core REST endpoints (`/api/graph`, `/api/nodes/{id}`)
- Add parameter update endpoint
- Basic error handling and validation
- API documentation

**Acceptance Criteria**:
- [ ] GET `/api/graph` returns current graph state
- [ ] PATCH `/api/nodes/{id}` updates parameters
- [ ] Error responses are properly formatted
- [ ] API documentation is complete

**Files to Modify**:
- `rasl/server/api.py`
- `tests/integration/test_web_api.py`

---

### Ticket #8: WebSocket Streaming
**Effort**: 2 days  
**Priority**: High  
**Dependencies**: Ticket #7

**Scope**:
- Implement WebSocket endpoint for real-time data
- Add message broadcasting for parameter changes
- Connection management and error handling
- Performance optimization for high-frequency updates

**Acceptance Criteria**:
- [ ] WebSocket connects and receives real-time data
- [ ] Parameter changes broadcast to all clients
- [ ] Handles client disconnections gracefully
- [ ] Supports 60fps data streaming

**Files to Modify**:
- `rasl/server/websocket.py`
- `tests/integration/test_websocket.py`

---

### Ticket #9: Basic Web UI
**Effort**: 3 days  
**Priority**: Medium  
**Dependencies**: Ticket #8

**Scope**:
- Create minimal HTML/CSS/JS interface
- Display graph visualization (simple boxes and lines)
- Parameter controls (sliders for exposed parameters)
- Real-time data display

**Acceptance Criteria**:
- [ ] Web UI loads at `http://localhost:8080`
- [ ] Shows current graph structure
- [ ] Parameter sliders update nodes in real-time
- [ ] Mobile-responsive design

**Files to Create**:
- `rasl/ui/static/index.html`
- `rasl/ui/static/css/main.css`
- `rasl/ui/static/js/main.js`

## Milestone 3: Enhanced Features (1 week)

### Ticket #10: Additional Node Types
**Effort**: 3 days  
**Priority**: Medium  
**Dependencies**: Ticket #6

**Scope**:
- Implement `NoiseSource` (white, pink noise)
- Implement `MathTransform` (basic math operations)
- Implement `CSVSource` for data file loading
- Comprehensive testing

**Acceptance Criteria**:
- [ ] All new node types work correctly
- [ ] Performance meets real-time requirements
- [ ] Integration with existing system
- [ ] Example scripts demonstrate usage

---

### Ticket #11: Hardware Protocol Support
**Effort**: 2 days  
**Priority**: Medium  
**Dependencies**: Ticket #6

**Scope**:
- Implement `SACNSink` for lighting control
- Optional `LIFXSink` for smart lights
- Graceful degradation when hardware unavailable
- Testing with mock hardware

**Acceptance Criteria**:
- [ ] sACN packets sent correctly
- [ ] Works without hardware (mock mode)
- [ ] Performance doesn't impact engine
- [ ] Clear error messages for setup issues

---

### Ticket #12: Export System
**Effort**: 2 days  
**Priority**: Low  
**Dependencies**: Ticket #6

**Scope**:
- Implement FSEQ export for xLights compatibility
- CSV export for data analysis
- Deterministic scheduler for offline rendering
- Export command in CLI

**Acceptance Criteria**:
- [ ] FSEQ files work with xLights
- [ ] CSV exports contain correct data
- [ ] Export completes without errors
- [ ] CLI command is user-friendly

## Effort Summary

**Total Estimated Effort**: 25 days (5 weeks)

**By Milestone**:
- Milestone 1 (Basic System): 11 days
- Milestone 2 (Web Interface): 7 days  
- Milestone 3 (Enhanced Features): 7 days

**By Priority**:
- Critical tickets: 11 days (minimum viable product)
- High priority: 6 days (core functionality)
- Medium/Low priority: 8 days (nice-to-have features)

## Risk Mitigation

**Reduced Scope**: Each ticket is 1-3 days, allowing for quick wins and course correction

**Clear Dependencies**: Tickets build incrementally, each delivering working functionality

**Flexible Prioritization**: Can stop after any milestone and have a working system

**Testing Focus**: Each ticket includes comprehensive testing to prevent regression

## Recommended Execution Order

1. **Week 1**: Tickets #1-3 (Basic nodes) + #4 (Engine) 
2. **Week 2**: Tickets #5-6 (Integration + Parameters)
3. **Week 3**: Tickets #7-8 (Web API + WebSocket)
4. **Week 4**: Ticket #9 (Web UI) + #10 (Additional nodes)
5. **Week 5**: Tickets #11-12 (Hardware + Export) + Polish

This approach ensures a working end-to-end system by Week 2, with progressive enhancement thereafter.
