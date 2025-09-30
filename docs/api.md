# RASL Public APIs — Interface Specification (Python)

> Purpose: this file defines the **top‑layer interfaces** that concrete implementations extend from. It focuses on
> stable contracts, naming, and invariants — not behavior internals. Everything here is importable without pulling in
> heavy runtime deps. All comments are normative.

---
## 0. Conventions
- All times are seconds (`float`).
- Arrays are conceptual; concrete impls may use `numpy`, `torch`, etc., as long as they present `NDArrayLike`.
- Ports are accessed via `node.ports` to avoid attribute collisions.
- Connections are **port‑to‑port**; there is no per‑channel wiring.

```python
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Protocol, Sequence, Tuple, Union, runtime_checkable
from abc import ABC, abstractmethod

# Minimal array protocol for type hints; implementers can widen as needed
NDArrayLike = Any  # numpy.ndarray | torch.Tensor | array.array | memoryview
```

---
## 1. Core Types: Frame, Range, Components/Channels/Schemas

```python
class RangeRule(str, Enum):
    """How values outside [min,max] are handled by transforms.
    - clip: clamp to bounds
    - wrap: circular wrap (e.g., hue)
    - error: raise validation error at runtime/test
    """
    CLIP = "clip"
    WRAP = "wrap"
    ERROR = "error"

@dataclass(frozen=True)
class Range:
    min: float = 0.0
    max: float = 1.0
    rule: RangeRule = RangeRule.CLIP

class Liveness(str, Enum):
    """Source capability (declared at type level).
    - FINITE: bounded media with definite end (CSV file, audio file played once)
    - GENERATOR: can produce data indefinitely but may end naturally (sine wave, noise)
    - STREAMING: external, potentially infinite data streams (network input, live audio)
    """
    FINITE = "finite"
    GENERATOR = "generator"
    STREAMING = "streaming"

@dataclass(frozen=True)
class Frame:
    """Monotonic frame context emitted by the scheduler. All nodes see the same
    Frame during a tick."""
    t: float   # sequence time (0.0 = start of execution)
    dt: float  # delta time since previous frame (seconds)
    seq: int   # monotonically increasing sequence number
    wall_time: float = 0.0  # wall clock time (for debugging/logging only)

@dataclass(frozen=True)
class Channel:
    """A single scalar signal (leaf)."""
    id: str                 # e.g., "r", "g", "b", "h"
    units: Optional[str] = None  # e.g., "unitless", "turns", "rad", "mm"
    range: Range = Range()       # semantic range; default [0,1], rule=clip

@dataclass(frozen=True)
class Component:
    """A bundle of related channels that travel together and share invariants.
    Examples: Color(HSV), Color(linear_srgb), Vector3(mm)."""
    name: str                # e.g., "Color", "Vector3"
    flavor: Optional[str] = None   # e.g., "HSV", "linear_srgb", "cartesian"
    channels: Tuple[Channel, ...] = ()
    colorspace: Optional[str] = None  # normalized color math context; default linear_srgb for Color

@dataclass(frozen=True)
class Schema:
    """Port contract: ordered components, each with their channels.
    Connections align **by component/channel ids**, not positional index.
    """
    components: Tuple[Component, ...]

class EOS:
    """End of stream marker returned by nodes when they complete naturally."""
    pass

class EndOfData(Exception):
    """Raised by finite sources when data is exhausted."""
    pass

@dataclass
class ExecutionState:
    """Read-only execution state available to node implementations."""
    current_loop: int = 0
    should_loop: bool = False
    remaining_duration: Optional[float] = None
    downstream_demand: bool = True
    
    def notify_loop_completed(self) -> None:
        """Inform base class that a loop iteration completed."""
        pass
    
    def notify_duration_exceeded(self) -> None:
        """Signal that duration limit was reached."""
        pass
    
    def notify_resource_exhausted(self) -> None:
        """Indicate external resource was depleted."""
        pass
```

---
## 2. Ports and Connections

```python
@runtime_checkable
class PortRef(Protocol):
    """First‑class reference to a node port. Used for wiring and introspection.
    Implementations must be lightweight and immutable."""
    @property
    def node_id(self) -> str: ...   # stable id of owning node
    @property
    def name(self) -> str: ...      # port name within node (e.g., "in", "out", "a")
    @property
    def kind(self) -> str: ...      # "in" or "out"
    @property
    def schema(self) -> Schema: ... # declared contract

class PortsView(Protocol):
    """Namespace for a node's ports. Avoids attribute collisions on node itself.
    Access patterns:
      node.ports.in, node.ports.out, node.ports.a
      node.ports["sidechain"], node.ports.list(kind="in")
    Variadic inputs may expose a subscriptable group: node.ports.inputs[i]
    """
    def __getattr__(self, name: str) -> PortRef: ...
    def __getitem__(self, name: str) -> PortRef: ...
    def list(self, kind: str = "any") -> Sequence[PortRef]: ...  # kind in {"in","out","any"}

class ConnectionError(Exception):
    pass

class Connector(Protocol):
    """Pure wiring helper; validates and records edges when ports are connected."""
    def connect(self, src: PortRef, dst: PortRef) -> None: ...
    # Optional operator sugar (src >> dst) is permitted but not required by this interface
```

---
## 3. Node Contracts (base types)

```python
class NodeKind(str, Enum):
    SOURCE = "source"
    TRANSFORM = "transform"
    SINK = "sink"

@runtime_checkable
class Node(Protocol):
    """Base contract for all nodes. Instances are regular Python objects.
    Implementations must be side‑effect free **except** Sources/Sinks."""
    KIND: NodeKind
    TYPE: str  # stable type name for serialization / plugin discovery

    # Port exposure via node.ports
    @property
    def id(self) -> str: ...             # stable instance id (auto if not provided by user)
    @property
    def ports(self) -> PortsView: ...    # namespaced port refs

    # Static schemas per port name (exposed for tooling)
    def port_schema(self, name: str) -> Schema: ...

    # Parameter model (declarative)
    def param_spec(self) -> Mapping[str, Mapping[str, Any]]: ...  # {param: {type, default, bounds, enum?}}

    # Runtime parameter update with validation & coercion
    def set_params(self, **params: Any) -> None: ...
    def get_params(self) -> Mapping[str, Any]: ...

@runtime_checkable
class Source(Node, Protocol):
    LIVENESS: Liveness
    
    @property
    def execution_state(self) -> ExecutionState: ...  # Read-only execution state
    
    def open(self) -> None: ...    # acquire resources
    def close(self) -> None: ...

    # Core implementation methods (implemented by child classes)
    def _determine_base_liveness(self) -> Liveness: ...  # Intrinsic liveness before elevation
    def _generate_data(self, frame: Frame) -> Union[NDArrayLike, EOS]: ...  # Core data generation
    def _reset_to_beginning(self) -> None: ...  # Domain-specific reset for looping

    # Engine interface (implemented by base class)
    def sample(self, frame: Frame) -> Union[Mapping[str, NDArrayLike], EOS]: ...  # Engine calls this

    # Optional for FINITE media
    def calculate_duration(self) -> Optional[float]: ...  # Calculate intrinsic duration

@runtime_checkable
class Transform(Node, Protocol):
    # Core implementation method (implemented by child classes)
    def _transform_data(self, inputs: Dict[str, NDArrayLike], frame: Frame) -> Dict[str, NDArrayLike]: ...
    
    # Engine interface (implemented by base class)
    def evaluate(self, frame: Frame, **inputs: NDArrayLike) -> Mapping[str, NDArrayLike]: ...

@runtime_checkable
class Sink(Node, Protocol):
    # Core implementation methods (implemented by child classes)
    def _initialize(self) -> None: ...  # Setup resources (optional)
    def _emit_data(self, inputs: Dict[str, NDArrayLike], frame: Frame) -> None: ...  # Core emission logic
    def _finalize(self) -> None: ...  # Cleanup resources (optional)
    
    # Engine interface (implemented by base class)
    def emit(self, frame: Frame, **inputs: NDArrayLike) -> None: ...  # Engine calls this

    # Optional per‑sink cadence requirements
    def required_rate(self) -> Optional[Mapping[str, Any]]: ...  # {target_hz, tolerance, align}

# Special transform for time domain bridging
class TimeWarp(Transform):
    """Converts between different time domains (e.g., audio time to sequence time)."""
    def __init__(self, from_domain: str, to_domain: str, rate: float = 1.0, **kwargs):
        self.from_domain = from_domain
        self.to_domain = to_domain
        self.rate = rate  # Time scaling factor
        super().__init__(**kwargs)
```

---
## 4. Clock and Scheduler (single time authority)

```python
@runtime_checkable
class Clock(Protocol):
    """Loop‑safe wall‑clock. Should return monotonic time."""
    def now(self) -> float: ...

@runtime_checkable
class Scheduler(Protocol):
    """Produces Frames at a chosen cadence. Engine consumes from this source.
    Implementations must be async‑friendly (yield frames without blocking the loop)."""
    async def frames(self) -> Iterable[Frame]: ...  # AsyncIterator[Frame] in concrete impls
    def stop(self) -> None: ...
```

---
## 5. Graph Discovery & Validation

```python
@dataclass(frozen=True)
class Edge:
    src_id: str
    src_port: str
    dst_id: str
    dst_port: str
    # Implementations may add a channel permutation map resolved at connect‑time

class GraphView(Protocol):
    """Read‑only view over the reachable DAG used by the engine and HTTP layer."""
    def nodes(self) -> Sequence[Node]: ...
    def edges(self) -> Sequence[Edge]: ...
    def describe(self) -> Mapping[str, Any]: ...  # canonical JSON‑ready spec

class Validator(Protocol):
    """Performs local and global checks. Should fail fast with actionable messages."""
    def validate_connect(self, src: PortRef, dst: PortRef) -> None: ...  # existence, direction, schema by name
    def validate_global(self, sinks: Sequence[Sink]) -> GraphView: ...   # DAG, required inputs, rate plan, liveness/EOS
```

---
## 6. Execution & Buffers (lazy per‑frame materialization)

```python
class Executor(Protocol):
    """Materializes node outputs on demand for a given frame, with per‑frame memoization."""
    async def materialize(self, port: PortRef, frame: Frame) -> NDArrayLike: ...
    def reset_frame_cache(self, frame: Frame) -> None: ...  # called once per frame

class BufferStore(Protocol):
    """Provides last‑committed snapshots per edge, and optional ring buffers for sinks.
    Observers read from here; reads must not trigger compute."""
    def snapshot(self, edge: Edge) -> Optional[NDArrayLike]: ...
    def commit(self, edge: Edge, value: NDArrayLike, frame: Frame) -> None: ...
```

---
## 7. Engine (orchestration)

```python
class Engine(Protocol):
    """Coordinates scheduler, executor, validation, and observability."""
    # Construction: provide sinks; engine will discover the reachable graph upstream
    def __init__(self, *, sinks: Sequence[Sink], scheduler: Scheduler,
                 cadence: str = "drop",            # drop | skip | slow (cadence recovery)
                 autofix_rate: bool = True,
                 default_resample_mode: str = "hold") -> None: ...

    # Lifecycle
    async def start(self) -> None: ...  # run until stop()
    def stop(self) -> None: ...
    async def tick_once(self) -> None: ...  # step exactly one frame (tests)

    # Runtime ops
    def patch(self, node: Node, **params: Any) -> None: ...  # typed validation & coercion
    def graph(self) -> GraphView: ...      # current reachable graph
    def metrics(self) -> Mapping[str, Any]: ...
    def events(self) -> Iterable[Mapping[str, Any]]: ...  # or a subscription handle
```

---
## 8. IO Contracts (protocol bindings)

```python
class InputDriver(Protocol):
    """Low‑level ingestion for sources. Abstracts files, sockets, devices."""
    def open(self) -> None: ...
    def close(self) -> None: ...
    def read(self, n: int = -1) -> Any: ...  # record/packet/row depending on source type

class OutputDriver(Protocol):
    """Low‑level egress for sinks. Abstracts transports (sACN/DMX, UDP, WS, file)."""
    def open(self) -> None: ...
    def close(self) -> None: ...
    def write(self, payload: bytes) -> None: ...  # non‑blocking; drop/coalesce upstream if needed
```

---
## 9. HTTP/WS Surface (control plane)

```python
class HttpApi(Protocol):
    """Thin façade over Engine for REST/WS. Keeps payloads JSON‑serializable."""
    # REST
    def get_graph(self) -> Mapping[str, Any]: ...
    def post_graph(self, spec: Mapping[str, Any]) -> None: ...  # atomic swap after validation
    def get_node(self, node_id: str) -> Mapping[str, Any]: ...
    def patch_node(self, node_id: str, params: Mapping[str, Any]) -> None: ...
    def get_metrics(self, since: Optional[float] = None) -> Mapping[str, Any]: ...

    # WS topics: metrics | samples | events
    def ws_topics(self) -> Sequence[str]: ...
```

---
## 10. Mixins (composable behaviors)

```python
class LoopingMixin:
    """Adds loop counting with automatic liveness elevation."""
    def __init__(self, loop_count: int = 1, **kwargs):
        self.loop_count = loop_count
        super().__init__(**kwargs)
    
    @property
    def liveness(self) -> Liveness:
        """Elevate base liveness based on loop configuration."""
        base = self._determine_base_liveness()
        if self.loop_count == -1:
            return Liveness.STREAMING  # Infinite loops
        elif self.loop_count > 1:
            return Liveness.GENERATOR  # Multiple loops
        else:
            return base  # Single iteration

class DurationMixin:
    """Adds duration limits for generator sources."""
    def __init__(self, duration: Optional[float] = None, **kwargs):
        self.duration = duration
        super().__init__(**kwargs)
    
    @property 
    def liveness(self) -> Liveness:
        """Generators with duration limits become finite."""
        base = self._determine_base_liveness()
        if base == Liveness.GENERATOR and self.duration is not None:
            return Liveness.FINITE
        return base

class RateLimitMixin:
    """Adds output rate control."""
    def __init__(self, max_hz: float = 60.0, **kwargs):
        self.max_hz = max_hz
        super().__init__(**kwargs)
```

---
## 11. Plugins

```python
class PluginRegistry(Protocol):
    """Discovery and registration for external node types via entry‑points."""
    def register(self, node_type: str, cls: type[Node]) -> None: ...
    def resolve(self, node_type: str) -> type[Node]: ...
    def available(self) -> Sequence[str]: ...
```

---
## 11. Errors (typed, actionable)

```python
class SchemaMismatch(Exception): ...
class UnitMismatch(Exception): ...
class ColorSpaceMismatch(Exception): ...
class DanglingInput(Exception): ...
class RateMismatch(Exception): ...
class EngineStartError(Exception): ...
```

---
## 12. Minimal Usage (illustrative only)

```python
# Define nodes
sine = SineSource(freq=1.2, channels=150)   # Source (GENERATOR)
amp  = ScaleBias(scale=0.6, bias=0.2)       # Transform
rgb  = ToRGB()                              # Transform
sacn = SACNSink(universe=1, start=1,        # Sink
                required_rate={"target_hz": 30, "align": "engine"})

# Wire via ports namespace
sine.ports.out >> amp.ports.in
amp.ports.out  >> rgb.ports.in
rgb.ports.out  >> sacn.ports.in

# Run
engine = Engine(sinks=[sacn], scheduler=FixedRateScheduler(MonotonicClock(), 60),
                cadence="drop", autofix_rate=True)
await engine.start()
```

---
## 13. Implementation Notes (non‑normative guidance)
- Validation should run **at connect time** and again on engine start (global checks).
- Executor must memoize per `(node_id, frame.seq)` to ensure single evaluation per node per frame.
- Observers read **committed** snapshots only; reads never trigger compute.
- Permutations of components/channels are resolved by **name**, not index; reorders don’t require a transform.
- Semantic changes (colorspace, units, structural) require explicit nodes.
- Liveness (FINITE/GENERATOR/STREAMING) is declared by **type** with elevation via looping configuration. Looping for seekable media (CSV) is explicit via parameters.
