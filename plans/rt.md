# RASL Real-Time Rewrite Plan

A feasibility analysis and roadmap for rewriting RASL in a strongly-typed, systems-level language (Rust as reference).

## Executive Summary

**Viability: HIGH** — RASL's architecture is well-suited for a Rust rewrite:
- DAG-based processing maps cleanly to Rust's ownership model
- No GC means predictable frame timing
- Strong typing already present conceptually (schemas, ports, payloads)
- Numeric workloads benefit from SIMD and cache-friendly layouts

**Estimated effort**: 3-6 months for core engine parity, depending on team size and Rust experience.

---

## Why Rewrite?

### Current Python Limitations

| Issue | Impact |
|-------|--------|
| **GC pauses** | Unpredictable 1-10ms stalls during frame processing |
| **GIL** | True parallelism requires multiprocessing overhead |
| **Dynamic typing** | Runtime errors that could be compile-time |
| **Memory overhead** | Python objects ~40-100 bytes overhead per instance |
| **Startup time** | Import overhead, JIT warmup |

### Rust Advantages

| Benefit | Impact |
|---------|--------|
| **No GC** | Deterministic frame timing, no pauses |
| **Zero-cost abstractions** | Traits, generics compile to optimal code |
| **Fearless concurrency** | Data races caught at compile time |
| **SIMD intrinsics** | Native vectorization for color math |
| **Small binaries** | Single static executable, no runtime |
| **Memory safety** | No null pointers, buffer overflows |

---

## Architecture Mapping

### Current Python Structure → Rust Equivalents

```
Python                          Rust
──────────────────────────────────────────────────────────
rasl/engine/frames/             rasl-core/src/frame/
  FramePayload (ABC)              trait Payload
  MatrixPayload                   struct Matrix<T>
  ColorPayload                    struct Color { model, data }
  Frame                           struct Frame<P: Payload>

rasl/engine/nodes/              rasl-core/src/node/
  Node (Protocol)                 trait Node
  BaseNode (ABC)                  trait NodeExt (blanket impl)
  NodeContext                     struct Context<'a>

rasl/engine/graph.py            rasl-core/src/graph/
  Edge                            struct Edge
  ExecutionPlan                   struct Graph
  GraphBuilder                    struct GraphBuilder

rasl/runtime/unified.py         rasl-runtime/src/scheduler/
  UnifiedScheduler                struct Scheduler
  TickSlot                        struct Tick
  NodeRuntime                     struct NodeState

rasl/config/                    rasl-config/src/
  crossplane parser               nom/pest parser
  ConfigLoader                    struct Config

rasl/server/                    rasl-server/src/
  FastAPI app                     axum/actix-web
  GraphQL                         async-graphql
  WebSocket                       tokio-tungstenite
```

### Type System Translation

```rust
// Python: class FramePayload(ABC)
pub trait Payload: Clone + Send + Sync + 'static {
    fn descriptor(&self) -> PayloadDescriptor;
    fn channels(&self) -> usize;
    fn elements(&self) -> usize;
}

// Python: class MatrixPayload(FramePayload)
#[derive(Clone)]
pub struct Matrix {
    data: ndarray::Array2<f32>,  // or nalgebra
}

impl Payload for Matrix { ... }

// Python: class ColorPayload(MatrixPayload)
#[derive(Clone)]
pub struct Color {
    model: ColorModel,
    data: Matrix,
}

// Python: class Frame
#[derive(Clone)]
pub struct Frame<P: Payload> {
    pub topic: String,
    pub timestamp: f64,
    pub payload: P,
    pub metadata: Metadata,
}
```

### Node Trait

```rust
// Python: class Node(Protocol)
pub trait Node: Send + Sync {
    fn id(&self) -> &str;
    fn inputs(&self) -> &[InputPort];
    fn outputs(&self) -> &[OutputPort];
    
    fn start(&mut self, ctx: &mut Context) -> Result<()>;
    fn tick(&mut self, ctx: &mut Context) -> Result<()>;
    fn stop(&mut self, ctx: &mut Context) -> Result<()>;
}

// Blanket implementations for common patterns
pub trait SourceNode: Node {
    fn pull(&mut self, ctx: &mut Context) -> Result<Frame<impl Payload>>;
}

pub trait TransformNode: Node {
    fn process(&mut self, input: Frame<impl Payload>) -> Result<Frame<impl Payload>>;
}

pub trait SinkNode: Node {
    fn push(&mut self, frame: Frame<impl Payload>) -> Result<()>;
}
```

---

## Crate Ecosystem

### Core Dependencies

| Purpose | Crate | Notes |
|---------|-------|-------|
| **Async runtime** | `tokio` | Industry standard, excellent for I/O |
| **Numeric arrays** | `ndarray` | NumPy-like, BLAS integration |
| **SIMD** | `wide` or `packed_simd` | Explicit vectorization |
| **Color math** | `palette` | Perceptual color spaces (Oklab, etc.) |
| **Serialization** | `serde` | JSON, TOML, binary formats |
| **Logging** | `tracing` | Structured, async-aware |
| **CLI** | `clap` | Derive-based argument parsing |
| **Config parsing** | `nom` or `pest` | For nginx-style syntax |

### Web/API Dependencies

| Purpose | Crate | Notes |
|---------|-------|-------|
| **HTTP server** | `axum` | Tower-based, ergonomic |
| **WebSocket** | `tokio-tungstenite` | Async WebSocket |
| **GraphQL** | `async-graphql` | Schema-first, subscriptions |
| **Templating** | `askama` | Compile-time templates |

### Protocol Dependencies

| Purpose | Crate | Notes |
|---------|-------|-------|
| **sACN/E1.31** | `sacn` (or custom) | May need to write/wrap |
| **UDP** | `tokio::net::UdpSocket` | Built-in |
| **Serial** | `tokio-serial` | For DMX interfaces |

---

## Workspace Structure

```
rasl-rs/
├── Cargo.toml              # Workspace root
├── rasl-core/              # Frame, Node, Graph types
│   ├── src/
│   │   ├── frame/
│   │   ├── node/
│   │   ├── graph/
│   │   └── lib.rs
│   └── Cargo.toml
├── rasl-runtime/           # Scheduler, execution
│   ├── src/
│   │   ├── scheduler.rs
│   │   ├── monitor.rs
│   │   └── lib.rs
│   └── Cargo.toml
├── rasl-nodes/             # Built-in node library
│   ├── src/
│   │   ├── sources/
│   │   ├── transforms/
│   │   ├── sinks/
│   │   └── lib.rs
│   └── Cargo.toml
├── rasl-config/            # Config parsing
│   └── ...
├── rasl-server/            # HTTP/WS/GraphQL
│   └── ...
├── rasl-sacn/              # sACN protocol
│   └── ...
├── rasl-ddp/               # DDP protocol
│   └── ...
└── rasl/                   # Binary crate
    ├── src/
    │   └── main.rs
    └── Cargo.toml
```

---

## Migration Strategy

### Phase 1: Core Types (2-3 weeks)

**Goal**: Establish type-safe foundation.

1. **Frame types** — `Payload` trait, `Matrix`, `Color`, `Frame<P>`
2. **Port types** — `InputPort`, `OutputPort`, `PortSpec`
3. **Node trait** — `Node`, `SourceNode`, `TransformNode`, `SinkNode`
4. **Graph types** — `Edge`, `Graph`, `GraphBuilder`

**Validation**: Unit tests for type conversions, graph construction.

### Phase 2: Scheduler (2-3 weeks)

**Goal**: Deterministic tick-based execution.

1. **Tick scheduler** — Compute exact tick times for sink rates
2. **Pull execution** — Recursive upstream evaluation
3. **Frame caching** — Per-tick memoization
4. **Cycle handling** — Previous-tick values for back-edges

**Validation**: Benchmark against Python scheduler, verify timing precision.

### Phase 3: Node Library (3-4 weeks)

**Goal**: Implement essential nodes.

| Category | Nodes |
|----------|-------|
| **Sources** | `Waveform`, `Literal` |
| **Transforms** | `Math`, `Color`, `Compose`, `Slice` |
| **Sinks** | `Console`, `sACN`, `DDP` |

**Validation**: Port existing Python tests, verify output equivalence.

### Phase 4: Config & CLI (2 weeks)

**Goal**: Parse existing config format.

1. **Parser** — nginx-style syntax via `nom`
2. **Loader** — Build graph from config AST
3. **CLI** — `rasl run config.conf` equivalent

**Validation**: Load existing `.conf` files, verify graph structure.

### Phase 5: Web Interface (2-3 weeks)

**Goal**: REST/WebSocket/GraphQL API.

1. **HTTP server** — `axum` with graph/metrics endpoints
2. **WebSocket** — Real-time metrics streaming
3. **GraphQL** — Schema matching Python implementation
4. **Static UI** — Embed existing HTML/JS

**Validation**: Existing UI works against Rust backend.

### Phase 6: Optimization (2 weeks)

**Goal**: Exploit Rust's performance advantages.

1. **SIMD color math** — Vectorized Oklab conversions
2. **Arena allocation** — Per-frame allocator for zero-copy
3. **Lock-free channels** — `crossbeam` for inter-node communication
4. **Profiling** — `perf`, `flamegraph`, `criterion` benchmarks

---

## Hybrid Approach (Alternative)

Instead of full rewrite, consider a **Rust core with Python bindings**:

```
┌─────────────────────────────────────────┐
│           Python (user scripts)          │
│  - Node definitions                      │
│  - Config loading                        │
│  - Web UI                                │
└─────────────────────────────────────────┘
                    │ PyO3
                    ▼
┌─────────────────────────────────────────┐
│           Rust (hot path)                │
│  - Scheduler                             │
│  - Frame processing                      │
│  - Color math                            │
│  - Protocol I/O                          │
└─────────────────────────────────────────┘
```

**Pros**:
- Keep Python's flexibility for user scripts
- Rust handles timing-critical paths
- Incremental migration possible

**Cons**:
- FFI overhead at boundaries
- Two build systems
- Debugging across language boundary

### PyO3 Integration

```rust
// Rust side
use pyo3::prelude::*;

#[pyclass]
struct RustScheduler {
    inner: Scheduler,
}

#[pymethods]
impl RustScheduler {
    #[new]
    fn new() -> Self { ... }
    
    fn add_node(&mut self, node: PyObject) -> PyResult<()> { ... }
    fn tick(&mut self) -> PyResult<()> { ... }
}

#[pymodule]
fn rasl_core(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<RustScheduler>()?;
    Ok(())
}
```

```python
# Python side
from rasl_core import RustScheduler

scheduler = RustScheduler()
scheduler.add_node(my_python_node)
scheduler.tick()
```

---

## Risk Assessment

### Technical Risks

| Risk | Mitigation |
|------|------------|
| **sACN crate quality** | Evaluate existing crates; may need custom impl |
| **Async complexity** | Start with sync scheduler, add async later |
| **Config parser parity** | Extensive test suite against Python parser |
| **Color math precision** | Validate against `colour-science` outputs |

### Process Risks

| Risk | Mitigation |
|------|------------|
| **Rust learning curve** | Start with experienced Rustacean or budget learning time |
| **Feature parity scope creep** | Define MVP feature set, defer advanced features |
| **Testing overhead** | Port Python tests first, then implement |

---

## Decision Framework

### When to Rewrite

✅ **Rewrite if**:
- Frame timing jitter is unacceptable (>1ms variance)
- Need to run on embedded/constrained hardware
- Want single-binary distribution
- Team has Rust experience
- Long-term maintenance is a priority

### When to Stay Python

✅ **Stay Python if**:
- Current performance is acceptable
- Rapid iteration more important than timing precision
- User scripting flexibility is critical
- Team lacks Rust experience and timeline is tight

### When to Hybrid

✅ **Hybrid if**:
- Only scheduler/color math needs optimization
- Want to keep Python user scripts
- Incremental migration preferred
- Need to maintain both versions during transition

---

## Recommended Path

Given RASL's architecture and goals:

1. **Start with hybrid** — Rust scheduler + color math via PyO3
2. **Measure improvement** — Validate timing precision gains
3. **Expand incrementally** — Move more hot paths to Rust
4. **Consider full rewrite** — If hybrid proves valuable and team gains Rust fluency

This approach:
- Delivers immediate timing improvements
- Preserves Python flexibility
- Builds Rust expertise gradually
- Provides escape hatch if Rust doesn't pan out

---

## Appendix: Benchmark Targets

| Metric | Python Current | Rust Target |
|--------|----------------|-------------|
| **Tick jitter** | 1-10ms | <100μs |
| **Frame latency** | 2-5ms | <500μs |
| **Startup time** | 1-2s | <100ms |
| **Memory per node** | ~1KB | <100 bytes |
| **Binary size** | N/A (interpreter) | <10MB |

---

## Appendix: Key Rust Patterns

### Arena Allocation for Frames

```rust
use bumpalo::Bump;

fn tick(arena: &Bump, nodes: &mut [Node]) {
    // All frame allocations freed at end of tick
    let frame = arena.alloc(Frame::new(...));
    // ...
}
```

### SIMD Color Conversion

```rust
use wide::f32x8;

fn oklab_to_srgb_simd(l: f32x8, a: f32x8, b: f32x8) -> (f32x8, f32x8, f32x8) {
    // 8 pixels at once
    let l_ = l + 0.3963377774 * a + 0.2158037573 * b;
    // ...
}
```

### Lock-Free Frame Passing

```rust
use crossbeam::channel::{bounded, Sender, Receiver};

struct NodeRuntime {
    input: Receiver<Frame>,
    output: Sender<Frame>,
}
```
