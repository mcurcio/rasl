# Writing a node

This page explains how to write a node type for the Python runtime. It covers the class a node extends, how it
registers its type name, how it declares its settings and ports, what it does on each tick, its lifecycle, the
payload types it reads and writes, and how a separate package makes its nodes available to `rasl`. It ends with a
small node that was run as written. The built-in node types and their settings are in the
[README](../README.md#node-types) and [nodes.md](nodes.md); how a config file wires nodes together is in
[README: Configuration](../README.md#configuration).

## The parts of a node

A node type is a Python class that:

- extends `BaseNode` (`rasl.graph.node`);
- is registered under one or more type names with the `@node` decorator;
- has a nested pydantic class named `Config`, which holds its settings;
- declares its ports as the class attributes `inputs` and `outputs`;
- implements `async def pull(self, tick)`, and optionally `start`, `stop`, `update_config` and
  `validate_connections`.

The config loader builds each node by calling the class with its validated config: `MyNode(config)`. So
`__init__` takes exactly one argument, the `Config` instance, and must call `super().__init__(config)` first.
That call sets `self.id`, stores the node's `metadata` setting as `self._metadata`, and gives the node its own
copy of the ports its class declares.

These are the imports a node usually needs:

```python
from rasl.graph.node import BaseNode, NodeContext, TickContext, node, pull_rate
from rasl.graph.node import SinkNodeConfig, SourceNodeConfig, TransformNodeConfig
from rasl.graph.ports import InputPortSpec, OutputPortSpec, PortGroup
from rasl.signal import BoolPayload, Frame, MatrixPayload
from rasl.color import ColorPayload, RgbColorPayload   # color payloads, when needed
from rasl.units import Duration, Frequency             # typed settings, when needed
```

Good models among the built-in nodes:

| Node | File | Shows |
|---|---|---|
| `RangeMap` | `src/rasl/nodes/effects/range_map.py` | A plain transform: one input, one output, a validated setting |
| `Smooth` | `src/rasl/nodes/effects/smooth.py` | State kept between ticks, `tick.dt`, `update_config`, `Duration` settings |
| `ConsoleSink` | `src/rasl/nodes/debug/console_sink.py` | A sink that drives the tick rate with `@pull_rate`, `start` and `stop` |
| `SineSource` | `src/rasl/nodes/debug/sine_source.py` | A push source that writes from a background task |
| `Crossfade` | `src/rasl/nodes/effects/crossfade.py` | `validate_connections`: refusing a config that leaves inputs unconnected |

## Registering a type name: `@node`

```python
@node("ThresholdNode", "Threshold")
class ThresholdNode(BaseNode):
    ...
```

`@node(name, *aliases)` registers the class under each name it is given. A config can use any of them:
`node Threshold gate { ... }` and `node ThresholdNode gate { ... }` are the same. The built-in nodes register
their class name and a short name.

- The decorator raises `TypeError` if the class has no nested `Config`.
- Names are global to the process. Registering a name that another class already has raises
  `NodeRegistryError`, naming both classes, and rasl does not start; pick names no built-in uses.
- The web API and `rasl --describe` report a node's Python class name (`ThresholdNode`), not the name the config
  used.

## Settings: the `Config` class

A node's settings are a pydantic model nested in the class as `Config`. Base it on one of three classes:

| Base | For | Adds |
|---|---|---|
| `SourceNodeConfig` | Nodes with no inputs | `fps`: an optional `Frequency` from 0.1 to 1000 Hz. It does nothing unless the node reads it. |
| `TransformNodeConfig` | Nodes with inputs and outputs | nothing |
| `SinkNodeConfig` | Nodes with no outputs | nothing |

All three extend `BaseNodeConfig`, which gives every node `id` (set from the config's node name), `metadata`
(a `dict[str, str]`) and `max_consecutive_errors` (an `int` or None). Models are frozen and refuse unknown fields (`extra="forbid"`), so a misspelt directive is
an error that names its line in the config file.

Each field is one directive in the node's block. [nodes.md: How settings are written](nodes.md#how-settings-are-written)
explains how directives become values: a repeated directive is a list, a bare directive is `true`, a nested
block is a map. Use pydantic's `Field` for defaults, bounds and a `description`, and `field_validator` for
anything more. A `ValueError` from a validator is reported at the directive that set the field.

```python
class Config(TransformNodeConfig):
    """Settings of a Threshold node."""

    level: float = Field(0.5, ge=0.0, le=1.0, description="Values at or above this become 1")
    invert: bool = Field(False, description="Write 0 where the value is at or above level")
```

For a time or a rate, type the field as `rasl.units.Duration` or `rasl.units.Frequency`. A config then writes
`200ms`, `2s`, `30hz` or `30fps`, and the node reads `.seconds` or `.hz`. `Smooth` and `ConsoleSink` do this.

To accept values on the node's own line, after its name (as `node Color rgb rgb;` does), override the classmethod
`from_positional(cls, words, written)` on the `Config`. It returns a dict of settings by field name, which are
validated with the rest; raise `ValueError` to refuse the values. The default refuses any value there.
`src/rasl/nodes/color/color_node.py` has an example.

## Ports

A node declares its ports once, as class attributes. Each node gets its own copy at construction.

```python
inputs = PortGroup.inputs(input=InputPortSpec((MatrixPayload, ColorPayload)))
outputs = PortGroup.outputs(out=OutputPortSpec(BoolPayload))
```

The keyword is the port's name, the one a config's `connect` line uses. A source leaves out `inputs`; a sink
leaves out `outputs`.

`InputPortSpec(accepts, count=None, description="", values_multiple_of=None)`:

- `accepts` is a payload class, a registered payload name such as `"matrix"` or `"color:rgb"`, or a tuple of
  either (all classes or all names). A connection is refused at load time, with the file and line, when the
  source port's payload type is not accepted. A port accepts its own type and its subclasses:
  - `MatrixPayload` accepts every matrix, so colors and bools too.
  - `ColorPayload` accepts any color model but not a plain matrix. A node that needs one model converts with
    `payload.to_model(...)` in `pull`, as the built-in sinks do.
  - A specific model such as `RgbColorPayload` accepts only that model.
  - `BoolPayload` accepts only bools.
- `count` is the number of elements: an `int` (fixed), `(min,)`, `(min, max)`, or `None` (any).
- `values_multiple_of`, when set, is a number the total values supplied (rows × components) must be a
  multiple of. Where every source's rows and width are known at load, a total that is not is refused there
  (`Reshape` uses it); otherwise the node checks each frame.

`OutputPortSpec(produces, count=None, description="", same_as=None)` takes exactly one payload class or name; a
tuple raises `ValueError`. Declare what the port really emits: a node whose output type depends on its settings
(like `Compose`'s `output_type`) sets `self.outputs` in `__init__` with the resolved class.

`same_as="input"` marks a pass-through output: one that passes on whatever payload type arrives at the named
input, as a filter that keeps colors colors does (`Smooth`, `RangeMap`). When the graph is built, the output is
typed as whatever feeds that input, followed through chains of such nodes, so `Color → Smooth → LifxSink` loads
and `Waveform → Smooth → LifxSink` is refused. With nothing feeding the input, or sources of different types,
the output has its `produces` type.

A name that no payload is registered under makes the connection fail with a list of the registered names.
`count` is checked when a config connects a slice to the port (a slice past the end is refused), and a fixed
input count sets the number of rows of an input assembled from slices or several connections. Nothing checks the size of a frame at
run time.

`connect <source>;` with no port name works only when the receiving node has exactly one input. Give a node
with several inputs a short, clear name for each.

A node may build its port groups in `__init__` instead, when a setting decides them. `ConsoleSink` names its
input after its `input_port` setting this way, and `Compose` makes one input per name in its `ports { }` block.

### Checking connections

Override `validate_connections(self, incoming_edges)` to refuse a graph that does not connect the node the way
it needs. It is called once all edges are known, with the edges that end at this node; each has `source`,
`source_port`, `target` and `target_port`. Raise `ValueError`; its message is shown when the config is loaded.

## Each tick: `pull`

### How ticks happen

Sinks set the pace. A node whose `pull` is decorated with `@pull_rate(hz)` is a rate driver: it is pulled at
`hz` times a second, counted from the same start as every other driver. At each tick the runtime pulls each due
driver, and before that, every node upstream of it, each at most once per tick. A node that no rate driver
depends on is started but never pulled, and `rasl --validate` warns about it.

`hz` is a number, or a function of the node, which is how a sink reads its rate from its config:

```python
@pull_rate(lambda self: self._fps)
async def pull(self, tick: TickContext) -> None:
    ...
```

The rate is read when the runtime is built and after each reload. It must be a positive, finite number, or
None: a function that returns None says this node does not drive the graph (it runs only when a driver
downstream pulls it). Anything else stops rasl with a `ValueError` when it starts. Validate the setting in the
`Config` so the config is refused with its line number instead.

A node whose rate depends on what is connected asks for its wiring, the names of its ports that have edges
(`Wiring.inputs`, `Wiring.outputs`):

```python
@pull_rate(lambda self, wiring: self._fps if "dmx" in wiring.inputs else None, wiring=True)
async def pull(self, tick: TickContext) -> None:
    ...  # drives the graph only when something feeds dmx (SacnUniverse)
```

### What `pull` does

`pull(self, tick)` reads its input ports, computes, and writes its output ports:

```python
async def pull(self, tick: TickContext) -> None:
    frame = self.inputs.input.read()
    if frame is None:
        return
    mask = frame.payload.data >= self._level
    self.outputs.out.write(frame.with_payload(BoolPayload(mask)))
```

- `self.inputs.<name>.read()` returns the port's frame for this tick, or `None`. It is `None` when nothing is
  connected (`self.inputs.<name>.connected` says whether something is) and when the upstream node has not
  written anything yet. Always handle `None`.
- `self.outputs.<name>.write(frame)` hands a frame downstream. It is published (readers see it) when the pull
  ends. A node that writes nothing in a tick leaves its last frame in place: downstream nodes read the frame it
  last wrote.
- An input fed by one whole connection gets the upstream frame object as it was written. An input fed by slices,
  repeats or several connections gets a frame built in the port's own buffers, of the type the port takes.
- Frames have a lifetime (see [Frame lifetimes](#frame-lifetimes)): copy the data of a frame you keep past your
  next pull, and call `frame.detach()` before writing a frame you did not build, such as an input frame.
- Exceptions from `pull` are logged against the node, and what the failed pull wrote is never published. That
  sink's pull ends for the tick, and the node is pulled again next tick. After `max_consecutive_errors` failures in a row (the config's `runtime` block, 10 by default,
  or the node's own setting) the node is disabled until a config reload changes it.

`TickContext` is a frozen dataclass:

| Field | Meaning |
|---|---|
| `tick` | Ticks run since the runtime started, from 0. |
| `t` | Seconds since the runtime started, at the moment the tick was due (not when it ran). Evenly spaced. |
| `dt` | Seconds since this node was last pulled. The first time, seconds since it was started. |
| `wall_time` | The tick's due time on the monotonic clock (`time.monotonic()`), in seconds. |

`dt` varies: a node upstream of sinks with different rates is pulled whenever any of them is due. A node that
changes over time should scale by `dt` or compute from `t`, never assume a fixed step. `Smooth` scales by `dt`;
`Waveform` computes from `t`.

### Avoiding allocation

A node that writes large frames every tick can reuse a buffer instead of allocating one. `acquire(count)` on an
output port returns a writable float32 view of shape `(count, components)` of the port's back buffer; fill it
(numpy operations can write straight into it with `out=`), wrap it in a payload, and call `commit(frame)`. The
port publishes the frame when the pull ends, and only then swaps its two buffers. `commit` checks the payload type
against the port; `write` does not. `Waveform` and `SeededRandom` do this.

What `acquire` returns holds old data (the frame from two publishes ago), not your last output. To update your last
output instead of rewriting it, read `previous`, a read-only view of the frame readers see now:

```python
buf = self.outputs.out.acquire(n)
np.multiply(self.outputs.out.previous, 0.9, out=buf)   # decay the last output: one vector operation, no copy
self.outputs.out.commit(Frame(topic="fade", timestamp=tick.wall_time, payload=MatrixPayload(buf)))
```

`previous` is None before the first `commit` is published, after a published `write`, and when the shape asked
for differs from the published one.

### Frame lifetimes

A frame's dataclass is frozen, but the array behind its payload may belong to a port's buffers. A frame a port
published stays unchanged until its producer's first fill after its next publish. Ports publish:

- an output, at the end of its node's pull (at most once per pull);
- a pushed output, at the start of each tick (at most once per tick), so a frame read in a tick is unchanged for
  the rest of that tick, however often its source writes meanwhile;
- an input fed by slices, repeats or several connections, before its node's pull.

So a frame is safe to use during the pull that read it. Two rules cover the rest:

- To keep a frame past your next pull, copy its data.
- To write a frame you did not build (an input frame, or one another node wrote), call `frame.detach()` first. It
  copies the data and keeps the topic, timestamp and metadata. Otherwise the frame you passed on changes under its
  readers when its producer refills the buffer, for example while your node is disabled or on a slower rate.

Setting `debug_frames true;` in the config's `runtime` block makes mistakes fail: every `acquire` gets a fresh
buffer and the buffer it replaces is filled with NaN, reading such a frame fails the reading node, writing a frame
whose data a port owns fails the writer, and committing a frame not built on the latest `acquire` fails. It is
slower; use it while developing a node.

### Push sources

A source can also produce frames outside ticks, for data that arrives on its own schedule, such as packets from
the network. In `start`, launch a background task with `ctx.start_background(func, *args)`, and write to an output
port from that task whenever data arrives, with `write` or `acquire` and `commit`. An output is pushed when its
node has no `pull` of its own (`SineSource`), or when it is declared `OutputPortSpec(..., pushed=True)`. What a pushed output
produced is published at the start of the next tick, so every reader in a tick sees the same frame, and a source
may write any number of times between ticks; it never causes a tick. Do not `await` between `acquire` and
`commit`: a tick that starts in between keeps the previous frame.

A node with inputs that also pushes (one that sends what its input carries and receives on its outputs, like
`SacnUniverse`) declares those outputs `pushed=True`. A node reading a pushed output gets its latest frame without
pulling the writer, so the writer runs only at its own rate (if it declares one), not whenever a reader is due.

## Lifecycle

| Method | When | Use |
|---|---|---|
| `__init__(config)` | When the config is loaded, and again on a reload that restarts the node | Read settings into attributes. Do not open connections here: `rasl --validate` builds the node too. |
| `async start(ctx)` | Once, before the first `pull` | Open sockets, start background tasks, keep `ctx` for logging. |
| `async pull(tick)` | Each tick the node is needed | The work. |
| `async stop(ctx)` | Once, at shutdown or when a reload removes or restarts the node | Close what `start` opened. |
| `update_config(config)` | On a reload that changes this node's settings, if the method exists | Take new settings without a restart. |

`NodeContext` has `node_id`, `logger` (a structlog logger bound to the node, used as
`ctx.logger.info(event="...", key=value)`), `start_background`, `wiring` (which of the node's ports
the running plan connects) and `resources`. Background tasks are cancelled when the node stops, whether or not
`stop` ends them. An exception from `stop` is suppressed.

`ctx.resources` shares things such as sockets between nodes. `await ctx.resources.acquire(key, open, close)`
returns a lease on the resource that `key` (a `ResourceKey(kind, params)`) names: the first node to ask opens
it, later ones share it, and it closes when the last lease is released, so release it in `stop`. During a live
reload a resource whose holders are all replaced stays open across the swap. A resource whose value has
`end_tick(tick)` (the `EndOfTick` protocol) is called once after every tick's pulls; the sACN sender sends its
synchronization packets there.

A class whose behaviour follows its wiring sets `restart_on_wiring_change = True`: a reload that changes which of
its ports have edges restarts it, even when another node's `connect` line made the change. A class can also
define `plan_warnings(cls, plan, node_ids)`, returning `(node id, "rasl/<code>", message)` for problems only
visible across its nodes (two nodes sending one sACN universe); the loader logs each on the node's line.

Nodes start in graph order, sources first, and stop in the reverse order.

### Config reload

When the config changes while rasl runs ([README: Live reload](../README.md#live-reload)), a node whose settings
changed is stopped and replaced by a new object built from the new config. A node that defines
`update_config(self, config)` is kept instead: the runtime calls the method between ticks with the new, validated
config. Define it when the node holds state worth keeping and every setting can change without a restart. Call
`self._apply_base_config(config)` in it, since metadata is a setting too. An exception from it is logged, and the node
goes on running. A node whose `connect` lines changed but whose settings did not is left running.

## Payloads

Frames carry the data. `rasl.signal.Frame` is a frozen dataclass:

| Field | Meaning |
|---|---|
| `topic` | A label for where the frame came from, such as `waveform.hue`. Nothing in rasl reads it today. |
| `timestamp` | Monotonic seconds when the frame was made. |
| `payload` | The data: a `FramePayload`. |
| `metadata` | A read-only mapping of extra facts. |

`frame.with_payload(p)` returns a copy with a new payload and the same topic, timestamp and metadata; a transform
normally builds its output this way. `frame.with_metadata(**updates)` returns a copy with keys added. A source
makes new frames, and should pass `metadata=self._metadata` so the node's `metadata` setting reaches them.

The payload types:

| Type | Module | Registered as | Data |
|---|---|---|---|
| `MatrixPayload` | `rasl.signal` | `matrix`, `array` | float32, shape `(count, channels)`. A 1D array becomes one column. |
| `BoolPayload` | `rasl.signal` | `bool`, `boolean` | A mask: any input becomes 1.0 where non-zero, else 0.0. |
| `ColorPayload` | `rasl.color` | `color` | A matrix tagged with a color model (`.model`). |
| `RgbColorPayload` and one class per model | `rasl.color` | `color:rgb`, `color:srgb`, `color:hsl`, `color:okhsl`, `color:oklch`, ... | Three components per element (four for `rgbw` and `hsbk`). |
| `RollingCounter` | `rasl.signal` | `counter` | Not a matrix: an immutable `value` that wraps at `modulus` (default 65536). `advanced(by)` returns the next counter; `advanced_since(previous)` the steps between two readings. A counter cannot be sliced, repeated or share an input with another connection (refused at load). |

`payload.data` is the backing array itself, not a copy: do not change an input's data in place, because other
nodes may read the same frame. `payload.count` is the number of elements (rows) and `payload.channels` the
components per element. Values are normally in 0 to 1. A color payload converts with
`payload.to_model(RgbColorPayload)`.

A new payload type subclasses `FramePayload` (or `MatrixPayload`) and registers a name with `@payload("name")`
from `rasl.signal`. Ports can then name it.

## Making nodes available

rasl finds node types through the `rasl.nodes` entry-point group. Each entry names a module that registers its
nodes when it is imported. `rasl` imports every entry before it reads a config. The built-in nodes are entries
too (`pyproject.toml`):

```toml
[project.entry-points."rasl.nodes"]
builtin = "rasl.nodes"
devices = "rasl.devices"
```

A module that fails to import stops rasl with `NodeRegistryError` (`Node plugin '<name>' (...) failed to load:
...`), naming the entry point and the cause.

### In your own package

Add an entry to your package's `pyproject.toml` and install the package in the same Python environment as rasl:

```toml
[project.entry-points."rasl.nodes"]
threshold = "rasl_threshold"
```

Do not list `rasl` as a dependency: rasl is not on PyPI, and a different package named `rasl` is, so an
installer would fetch that one instead.

From a rasl checkout, `uv run --with <path to your package> rasl ...` runs rasl with the package installed for
that one command.

### In this repository

A built-in node goes in `src/rasl/nodes/` (a device protocol goes in `src/rasl/devices/`). Import its module in
that package's `__init__.py` so it registers, list its settings in [nodes.md](nodes.md), and add tests under
`tests/nodes/` or `tests/devices/`. Two repository rules apply:

- **Docstrings.** `uv run ruff check src tests` requires a docstring on every public module, class, method and
  function, including the nested `Config` and `pull`. Say what the node does, the shapes and units it reads and
  writes, and what it raises. See [CONTRIBUTING: Docstrings](../CONTRIBUTING.md#docstrings).
- **Imports go one way.** A module in `rasl.nodes` or `rasl.devices` may import `rasl.graph`, `rasl.color`,
  `rasl.signal` and `rasl.units`. It may not import `rasl.runtime`, `rasl.config` or `rasl.app`, and the two
  packages may not import each other. `uv run lint-imports` checks this, and so does the test suite.

## Example: a Threshold node

This node writes 1 for each input value at or above a level, and 0 for the rest. It keeps its settings across a
reload with `update_config`.

The package has two files:

```text
rasl-threshold/
├── pyproject.toml
└── src/rasl_threshold/__init__.py
```

`pyproject.toml`:

```toml
[project]
name = "rasl-threshold"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []

[project.entry-points."rasl.nodes"]
threshold = "rasl_threshold"

[build-system]
requires = ["uv_build>=0.8.18,<0.9.0"]
build-backend = "uv_build"
```

`src/rasl_threshold/__init__.py`:

```python
"""Threshold: a rasl node that turns each value into 1 or 0."""

from pydantic import Field

from rasl.color import ColorPayload
from rasl.graph.node import BaseNode, TickContext, TransformNodeConfig, node
from rasl.graph.ports import InputPortSpec, OutputPortSpec, PortGroup
from rasl.signal import BoolPayload, MatrixPayload


@node("ThresholdNode", "Threshold")
class ThresholdNode(BaseNode):
    """Write 1 for each input value at or above ``level``, else 0.

    The output has the input's shape, (count, channels), as a ``BoolPayload``.
    """

    class Config(TransformNodeConfig):
        """Settings of a Threshold node."""

        level: float = Field(0.5, ge=0.0, le=1.0, description="Values at or above this become 1")
        invert: bool = Field(False, description="Write 0 where the value is at or above level")

    inputs = PortGroup.inputs(input=InputPortSpec((MatrixPayload, ColorPayload)))
    outputs = PortGroup.outputs(out=OutputPortSpec(BoolPayload))

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._apply(config)

    def _apply(self, config: Config) -> None:
        self._level = config.level
        self._invert = config.invert

    def update_config(self, config: Config) -> None:
        """Take new settings on a config reload without a restart."""
        self._apply_base_config(config)
        self._apply(config)

    async def pull(self, tick: TickContext) -> None:
        """Compare the input with ``level`` and write the mask to ``out``.

        Writes nothing when ``input`` has no frame.
        """
        frame = self.inputs.input.read()
        if frame is None:
            return
        mask = frame.payload.data >= self._level
        if self._invert:
            mask = ~mask
        self.outputs.out.write(frame.with_payload(BoolPayload(mask)))
```

A config that uses it, `threshold.conf`. A sine wave at 0.5 Hz goes through the threshold, and a console sink
prints the result twice a second:

```nginx
graph {
    node Waveform wave {
        shape sine;
        frequency_hz 0.5;
        output_channels 4;
    }

    node Threshold gate {
        level 0.5;
        connect wave;
    }

    node ConsoleSink console {
        fps 2;
        connect gate;
    }
}
```

Check it and run it from a rasl checkout:

```bash
uv run --with ./rasl-threshold rasl --validate threshold.conf
# Config valid: 3 nodes, order: ('wave', 'gate', 'console')

uv run --with ./rasl-threshold rasl threshold.conf
```

The console sink logs one frame each half second, and the mask follows the wave (log lines shortened):

```text
[info] console_sink_frame  node=ConsoleSinkNode.console frame_count=1 tick=0 t=0.0 data=BoolPayload<len=4 data=[[1],[1],[1],[1]]>
[info] console_sink_frame  node=ConsoleSinkNode.console frame_count=2 tick=1 t=0.5 data=BoolPayload<len=4 data=[[1],[1],[1],[1]]>
[info] console_sink_frame  node=ConsoleSinkNode.console frame_count=3 tick=2 t=1.0 data=BoolPayload<len=4 data=[[0],[0],[0],[0]]>
[info] console_sink_frame  node=ConsoleSinkNode.console frame_count=4 tick=3 t=1.5 data=BoolPayload<len=4 data=[[0],[0],[0],[0]]>
[info] console_sink_frame  node=ConsoleSinkNode.console frame_count=5 tick=4 t=2.0 data=BoolPayload<len=4 data=[[1],[1],[1],[1]]>
```

Changing `level 0.5;` to `level 0.9;` while it runs keeps the node and calls `update_config`:

```text
[info] config_reloaded  changes=1 detail=['changed graph > node "gate" > level']
[info] plan_updated     added=[] removed=[] restarted=[] updated=['gate'] rerouted=[] duration_ms=0.12
```
