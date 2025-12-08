# Schema-Driven Config System v2

## Overview

A delegated configuration system where each domain object owns its keywords and parsing logic. A shared `ConfigDispatch` helper handles crossplane mechanics, while a `Directive` tree provides the universal config representation.

## Goals

1. **Delegated parsing** — Each domain object (Graph, BaseNode) owns its keywords
2. **Simple decorator API** — `@config(keyword, model=)` registers handlers
3. **Recursive Directive tree** — Immutable tree parsed once from crossplane
4. **Pydantic for fields** — Simple fields parsed automatically into models
5. **Explicit control flow** — No magic framework, just method calls
6. **Low cognitive load** — Node authors define Config class, optionally add handlers

## Core Types

### Directive

Immutable recursive tree representing the entire config file.

```python
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import crossplane

if TYPE_CHECKING:
    from pydantic import BaseModel


@dataclass(frozen=True)
class Directive:
    """Immutable recursive config directive tree."""

    keyword: str
    args: tuple[str, ...]
    block: tuple["Directive", ...]
    line: int = 0

    # Mutable slot for lazy-parsed config
    _config: "BaseModel | None" = None

    @property
    def config(self) -> "BaseModel | None":
        """Pre-parsed Pydantic model, if set by dispatch."""
        return self._config

    def slice_args(self, start: int, end: int | None = None) -> "Directive":
        """Return new Directive with sliced args, preserving block."""
        return Directive(
            keyword=self.keyword,
            args=self.args[start:end],
            block=self.block,
            line=self.line,
        )

    def with_args(self, *args: str) -> "Directive":
        """Return new Directive with replaced args."""
        return Directive(
            keyword=self.keyword,
            args=args,
            block=self.block,
            line=self.line,
        )

    @classmethod
    def from_crossplane(cls, raw: dict) -> "Directive":
        """Parse crossplane dict into Directive tree."""
        return cls(
            keyword=raw["directive"],
            args=tuple(raw.get("args", [])),
            block=tuple(cls.from_crossplane(d) for d in raw.get("block", [])),
            line=raw.get("line", 0),
        )

    @classmethod
    def from_file(cls, path: Path) -> "Directive":
        """Load file and return synthetic root directive."""
        raw = crossplane.parse(str(path))
        parsed = raw["config"][0]["parsed"]
        return cls(
            keyword="_root",
            args=(),
            block=tuple(cls.from_crossplane(d) for d in parsed),
            line=0,
        )
```

**Example tree structure:**

```
Directive(_root)
└── Directive(graph)
    ├── Directive(node, args=("Waveform", "wave"))
    │   ├── Directive(output_channels, args=("512",))
    │   └── Directive(shape, args=("sine",))
    └── Directive(node, args=("DdpSink", "leds", "rgb"))
        ├── Directive(target, args=("10.0.60.30",))
        ├── Directive(fps, args=("20",))
        └── Directive(connect, args=("wave[0:151]", "pixels[0:]"))
            └── Directive(repeat, args=("19",))
```

### @config Decorator

Registers a method as a keyword handler.

```python
from typing import Type
from pydantic import BaseModel


def config(keyword: str, model: Type[BaseModel] | None = None):
    """
    Decorator to register a method as handler for a keyword.

    Args:
        keyword: The directive keyword this method handles
        model: Optional Pydantic model to pre-parse the block into
    """
    def decorator(method):
        method._config_keyword = keyword
        method._config_model = model
        return method
    return decorator
```

### ConfigDispatch

Helper that routes directives to handlers and parses fields.

```python
from typing import Any, Callable, Type
from pydantic import BaseModel


class ConfigDispatch:
    """Routes directives to @config handlers and parses Pydantic fields."""

    def __init__(self, owner: object):
        self.owner = owner
        self._handlers = self._collect_handlers()

    def _collect_handlers(self) -> dict[str, tuple[Callable, Type[BaseModel] | None]]:
        """Find all @config decorated methods on owner."""
        handlers = {}
        for name in dir(self.owner):
            method = getattr(self.owner, name, None)
            if callable(method) and hasattr(method, "_config_keyword"):
                keyword = method._config_keyword
                model = getattr(method, "_config_model", None)
                handlers[keyword] = (method, model)
        return handlers

    def process(
        self,
        directive: Directive,
        config_class: Type[BaseModel],
    ) -> tuple[BaseModel, dict[str, list[Any]]]:
        """
        Process a directive's block.

        Returns:
            - Pydantic config from simple fields
            - Dict of handler results keyed by keyword
        """
        field_data = self._extract_arg_fields(directive, config_class)
        handler_results: dict[str, list[Any]] = {}

        for child in directive.block:
            keyword = child.keyword

            # Check for @config handler
            if keyword in self._handlers:
                method, model = self._handlers[keyword]

                # Pre-parse model if specified
                if model:
                    object.__setattr__(child, "_config", self.parse_model(child, model))

                result = method(child)
                if result is not None:
                    if isinstance(result, list):
                        handler_results.setdefault(keyword, []).extend(result)
                    else:
                        handler_results.setdefault(keyword, []).append(result)

            # Check for Pydantic field
            elif keyword in config_class.model_fields:
                field_info = config_class.model_fields[keyword]
                value = self._parse_field(child, field_info)

                if self._is_list_field(field_info):
                    field_data.setdefault(keyword, []).append(value)
                else:
                    field_data[keyword] = value

            else:
                raise ConfigError(f"Unknown keyword '{keyword}'", line=child.line)

        config = config_class(**field_data)
        return config, handler_results

    def parse_model(
        self,
        directive: Directive,
        model: Type[BaseModel],
    ) -> BaseModel:
        """Parse directive block into Pydantic model (fields only)."""
        data = self._extract_arg_fields(directive, model)

        for child in directive.block:
            if child.keyword in model.model_fields:
                field_info = model.model_fields[child.keyword]
                data[child.keyword] = self._parse_field(child, field_info)

        return model(**data)

    def _extract_arg_fields(
        self,
        directive: Directive,
        model: Type[BaseModel],
    ) -> dict[str, Any]:
        """Map positional args to fields via arg_fields class attribute."""
        data = {}
        arg_fields = getattr(model, "arg_fields", [])

        for i, field_name in enumerate(arg_fields):
            if i < len(directive.args):
                field_info = model.model_fields.get(field_name)
                if field_info:
                    data[field_name] = self._coerce(
                        directive.args[i],
                        field_info.annotation,
                    )

        return data

    def _parse_field(self, directive: Directive, field_info) -> Any:
        """Parse single field from directive."""
        inner_type = self._get_inner_type(field_info.annotation)

        # Nested model → recurse
        if isinstance(inner_type, type) and issubclass(inner_type, BaseModel):
            return self.parse_model(directive, inner_type)

        # Primitive → coerce first arg
        if directive.args:
            return self._coerce(directive.args[0], inner_type)

        return None

    def _is_list_field(self, field_info) -> bool:
        """Check if field is a list type."""
        origin = getattr(field_info.annotation, "__origin__", None)
        return origin is list

    def _get_inner_type(self, annotation) -> type:
        """Get inner type for list[T] or just T."""
        origin = getattr(annotation, "__origin__", None)
        if origin is list:
            args = getattr(annotation, "__args__", ())
            return args[0] if args else str
        return annotation

    def _coerce(self, value: str, target_type: type) -> Any:
        """Coerce string value to target type."""
        if target_type is str:
            return value
        if target_type is int:
            return int(value)
        if target_type is float:
            return float(value)
        if target_type is bool:
            return value.lower() in ("true", "yes", "1", "on")
        return value


class ConfigError(Exception):
    """Configuration parsing error."""

    def __init__(self, message: str, line: int = 0):
        self.line = line
        super().__init__(f"Line {line}: {message}" if line else message)
```

## Domain Implementations

### ConnectionSpec

Result of parsing a connect directive.

```python
from dataclasses import dataclass


@dataclass
class ConnectionSpec:
    """A connection declared within a node block."""

    source_node: str
    source_port: str | None
    source_slice: tuple[int, int | None] | None
    target_port: str
    target_slice: tuple[int, int | None] | None


@dataclass
class ConnectOptions(BaseModel):
    """Options parsed from connect block."""

    repeat: int = 1
    # Future: stride, offset, etc.
```

### BaseNode

Base class for all nodes. Owns `connect` keyword.

```python
from pydantic import BaseModel


class BaseNodeConfig(BaseModel):
    """Base config for all nodes. Subclasses add their fields."""

    pass


class BaseNode:
    """Base class for all nodes."""

    Config: type[BaseNodeConfig] = BaseNodeConfig

    def __init__(self, config: BaseNodeConfig):
        self.config = config
        self.connections: list[ConnectionSpec] = []
        self.dispatch = ConfigDispatch(self)

    @classmethod
    def from_directive(
        cls,
        directive: Directive,
    ) -> "BaseNode":
        """Parse directive into node instance."""
        # Create instance without __init__
        node = object.__new__(cls)
        node.dispatch = ConfigDispatch(node)
        node.connections = []

        # Process block
        config, handler_results = node.dispatch.process(directive, cls.Config)

        # Collect connections from handler
        node.connections = handler_results.get("connect", [])

        # Initialize with config
        node.config = config
        node.__init__(config)

        return node

    @config("connect", model=ConnectOptions)
    def handle_connect(self, directive: Directive) -> list[ConnectionSpec]:
        """Handle connect directive."""
        source = directive.args[0] if directive.args else ""
        target = directive.args[1] if len(directive.args) > 1 else None

        # Parse port references (node[slice].port or just node)
        source_ref = parse_port_ref(source)
        target_ref = parse_port_ref(target) if target else None

        # Get options (directive.config is pre-parsed ConnectOptions)
        options = directive.config or ConnectOptions()

        # Expand repeat into multiple specs
        return expand_connections(source_ref, target_ref, options.repeat)
```

### Graph

Owns `node` keyword. Resolves connections into edges.

```python
@dataclass
class Edge:
    """Resolved connection between nodes."""

    source_node: str
    source_port: str
    source_slice: tuple[int, int | None] | None
    target_node: str
    target_port: str
    target_slice: tuple[int, int | None] | None


class Graph:
    """Container for nodes and edges."""

    def __init__(self):
        self.nodes: dict[str, BaseNode] = {}
        self.edges: list[Edge] = []

    @classmethod
    def from_directive(cls, directive: Directive) -> "Graph":
        """Parse graph directive into Graph instance."""
        graph = cls()

        # First pass: parse all nodes
        pending_connections: list[tuple[str, ConnectionSpec]] = []

        for child in directive.block:
            if child.keyword == "node":
                node_type = child.args[0]
                node_name = child.args[1]

                # Slice args to pass remaining to node
                node_directive = child.slice_args(2)

                # Get node class and parse
                node_class = get_node_class(node_type)
                node = node_class.from_directive(node_directive)

                graph.nodes[node_name] = node

                # Collect connections for second pass
                for conn in node.connections:
                    pending_connections.append((node_name, conn))

        # Second pass: resolve connections into edges
        for target_node_name, conn in pending_connections:
            if conn.source_node not in graph.nodes:
                raise ConfigError(f"Unknown node '{conn.source_node}'")

            edge = Edge(
                source_node=conn.source_node,
                source_port=conn.source_port or "out",
                source_slice=conn.source_slice,
                target_node=target_node_name,
                target_port=conn.target_port or "in",
                target_slice=conn.target_slice,
            )
            graph.edges.append(edge)

        return graph
```

## Node Author Examples

### Simple Node (Most Common)

```python
from pydantic import BaseModel


@node("DdpSink")
class DdpSinkNode(BaseNode):
    class Config(BaseModel):
        target: str
        fps: float = 30.0
        input_port: str = "input"

        # Map positional args to fields
        arg_fields = ["input_port"]

    # No @config methods needed - inherits connect from BaseNode
```

Config file:

```nginx
node DdpSink leds rgb {
    target "10.0.60.30";
    fps 20;
    connect wave pixels;
}
```

### Node with Custom Keyword

```python
@node("Compose")
class ComposeNode(BaseNode):
    class Config(BaseModel):
        output_type: str = "rgb"

    def __init__(self, config: Config):
        super().__init__(config)
        self.ports: list[str] = []
        self.fills: dict[str, float] = {}

    @config("ports")
    def handle_ports(self, directive: Directive) -> None:
        """Handle: ports { hue; saturation; lightness; }"""
        self.ports = [d.keyword for d in directive.block]

    @config("fill")
    def handle_fill(self, directive: Directive) -> None:
        """Handle: fill hue 0.5;"""
        port_name = directive.args[0]
        value = float(directive.args[1])
        self.fills[port_name] = value
```

Config file:

```nginx
node Compose color {
    output_type oklch;
    ports { lightness; chroma; hue; }
    fill chroma 0.05;
    fill hue 0.22;
    connect wave lightness;
}
```

### Node with Pre-Parsed Model

```python
class LayerConfig(BaseModel):
    """Config for a layer block."""

    opacity: float = 1.0
    mode: str = "normal"


@node("Effect")
class EffectNode(BaseNode):
    class Config(BaseModel):
        name: str

    def __init__(self, config: Config):
        super().__init__(config)
        self.layers: list[tuple[str, LayerConfig]] = []

    @config("layer", model=LayerConfig)
    def handle_layer(self, directive: Directive) -> None:
        """Handle: layer blend { opacity 0.5; mode screen; }"""
        layer_type = directive.args[0]
        # directive.config is pre-parsed LayerConfig
        self.layers.append((layer_type, directive.config))
```

## Parsing Flow Example

Config file:

```nginx
graph {
    node Waveform wave {
        output_channels 512;
        shape sine;
    }

    node DdpSink leds rgb {
        target "10.0.60.30";
        fps 20;
        connect wave[0:151] pixels[0:] {
            repeat 19;
        }
    }
}
```

Parsing trace:

```
1. Directive.from_file("config.conf")
   └── Returns Directive(_root) tree

2. Find "graph" in root.block
   └── Graph.from_directive(graph_directive)

3. Graph iterates graph_directive.block:

   3a. child = Directive(node, args=("Waveform", "wave"))
       ├── node_type = "Waveform"
       ├── node_name = "wave"
       ├── node_directive = child.slice_args(2)  # args=()
       ├── WaveformNode.from_directive(node_directive)
       │   └── dispatch.process() parses:
       │       ├── output_channels → Config field → 512
       │       └── shape → Config field → "sine"
       └── graph.nodes["wave"] = WaveformNode

   3b. child = Directive(node, args=("DdpSink", "leds", "rgb"))
       ├── node_type = "DdpSink"
       ├── node_name = "leds"
       ├── node_directive = child.slice_args(2)  # args=("rgb",)
       ├── DdpSinkNode.from_directive(node_directive)
       │   └── dispatch.process() parses:
       │       ├── arg_fields: input_port = "rgb"
       │       ├── target → Config field → "10.0.60.30"
       │       ├── fps → Config field → 20
       │       └── connect → @config handler:
       │           ├── Pre-parse block → ConnectOptions(repeat=19)
       │           ├── handle_connect() called
       │           └── Returns [ConnectionSpec × 19]
       └── graph.nodes["leds"] = DdpSinkNode

4. Graph resolves connections:
   └── For each (node_name, ConnectionSpec):
       ├── Validate source_node exists
       └── Create Edge(source="wave", target="leds", ...)

5. Return Graph(nodes={wave, leds}, edges=[19 edges])
```

## File Structure

```
src/rasl/config/
├── __init__.py
├── directive.py      # Directive class
├── dispatch.py       # ConfigDispatch, @config decorator
├── errors.py         # ConfigError
└── connection.py     # ConnectionSpec, parse_port_ref(), expand_connections()

src/rasl/engine/
├── base_node.py      # BaseNode with @config("connect")
├── graph.py          # Graph with node parsing
└── registry.py       # @node decorator, get_node_class()
```

## Key Design Decisions

### 1. Directive is Immutable

Parsed once, passed around. `slice_args()` creates new instances.

### 2. @config Decorator is Simple

Just marks methods. No complex registration system.

### 3. ConfigDispatch is a Helper, Not a Framework

Domain objects call it explicitly. They can also do manual parsing.

### 4. arg_fields is a Class Attribute

No nested Meta class. Just `arg_fields = ["field1", "field2"]` on Config.

### 5. Handlers Return Domain Objects

`@config("connect")` returns `list[ConnectionSpec]`, not raw config.

### 6. Two-Phase Graph Building

First parse all nodes, then resolve connections. Allows forward references.

## Migration Path

1. **Create config/directive.py** — Directive class
2. **Create config/dispatch.py** — ConfigDispatch, @config decorator
3. **Create config/connection.py** — ConnectionSpec, parsing helpers
4. **Update engine/base_node.py** — Add from_directive(), @config("connect")
5. **Update engine/graph.py** — Add from_directive() with node dispatch
6. **Update nodes** — Add Config classes with arg_fields
7. **Update loader** — Use Directive.from_file(), Graph.from_directive()
8. **Remove old parsing code**
