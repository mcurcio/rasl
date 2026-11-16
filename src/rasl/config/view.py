"""The graph as the config files write it, for the graph editor (rasl-6sr.2).

``describe_config`` reads the files (not the running graph) and lists each node and each
``connect`` line with where it is written, whether the editor may change it, and the
node's ports. Ports exist only on a built node (some depend on its settings: an sACN
source's universes, a Compose node's ports), so each node is built on its own; a node
that does not build is listed with its error and no ports, and the rest still are.

The view is what ``rasl.config.edit`` edits: its ``version`` is the one an edit batch
is made against.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rasl.config.build import build_plan, graph_directive
from rasl.config.connect import parse_connect_directive, parse_port_ref
from rasl.config.document import (
    ConfigError,
    Directive,
    children,
    line_of,
    load_written,
    render_written,
)
from rasl.config.edit import lock_reason, version_of
from rasl.config.node_directive import _node_config, node_spec
from rasl.graph.node import ensure_nodes_loaded, get_inputs, get_outputs


@dataclass(frozen=True)
class PortView:
    """One port of a node.

    Attributes:
        name: The port's name.
        types: The payload type names it takes (an input) or emits (an output).
        min_count: Fewest elements; equal to ``max_count`` for a fixed count; None when
            unbounded below.
        max_count: Most elements; None when unbounded.
        components: Columns per element when known before the graph runs; else None.
        default: True for the node's default port in its group (what a connect line
            that names no port uses).
    """

    name: str
    types: tuple[str, ...]
    min_count: int | None
    max_count: int | None
    components: int | None
    default: bool


@dataclass(frozen=True)
class Place:
    """Where a line is written.

    Attributes:
        path: The file's resolved path.
        line: The line (1-indexed).
    """

    path: str
    line: int


@dataclass(frozen=True)
class NodeView:
    """One node as written.

    Attributes:
        id: The node's id.
        type: Its type name as written.
        place: Where its ``node`` line is.
        locked: Why the editor may not change its line, or None when it may.
        settings: Its block's lines other than ``connect``, as (key, values) text.
        inputs: Its input ports; empty when it does not build.
        outputs: Its output ports; empty when it does not build.
        error: Why it does not build on its own, or None.
    """

    id: str
    type: str
    place: Place
    locked: str | None
    settings: tuple[tuple[str, str], ...]
    inputs: tuple[PortView, ...]
    outputs: tuple[PortView, ...]
    error: str | None


@dataclass(frozen=True)
class EdgeView:
    """One ``connect`` line.

    Attributes:
        target: The id of the node whose block holds the line (the receiver).
        source: The line's source, in config notation (``hue.out[0~3]``).
        port: The line's target port, in config notation, or None for the default.
        source_node: The node the source names; None when the text does not parse.
        source_port: The output port read: as written, else the source node's default;
            None when unknown.
        target_port: The input port written: as written, else the target's default;
            None when unknown.
        repeat: The line's ``repeat``, or None.
        repeat_until: The line's ``repeat_until``, or None.
        place: Where the line is.
        locked: Why the editor may not change the line, or None when it may.
    """

    target: str
    source: str
    port: str | None
    source_node: str | None
    source_port: str | None
    target_port: str | None
    repeat: int | None
    repeat_until: int | None
    place: Place
    locked: str | None


@dataclass(frozen=True)
class ConfigView:
    """The graph as the files write it.

    Attributes:
        path: The root config file.
        version: The files' version (``ConfigEditor.version``).
        nodes: Every node, in the order the graph lists them.
        edges: Every ``connect`` line, in the same order by node, then line.
        error: Why the whole config does not build, or None when it does (it is what
            would keep a reload from applying it).
    """

    path: str
    version: str
    nodes: tuple[NodeView, ...]
    edges: tuple[EdgeView, ...]
    error: ConfigError | None


def _place(directive: Directive) -> Place:
    return Place(str(directive.origin.place.resolved_path), line_of(directive))


def _ports(group: Any) -> tuple[PortView, ...]:
    try:
        default = group.get_default()[0]
    except ValueError:
        default = None
    views = []
    for port in group:
        spec = port.spec
        if hasattr(spec, "produces"):
            types = (spec.type_name,)
            components = spec.known_components
        else:
            types = tuple(
                getattr(t, "domain", None) or getattr(t, "__name__", str(t))
                for t in spec.resolve_payload_types()
            )
            resolved = spec.resolve_payload_types()
            widths = {getattr(t, "components", None) for t in resolved}
            only = widths.pop() if len(widths) == 1 else None
            components = only if isinstance(only, int) else None
        views.append(
            PortView(
                name=port.name,
                types=types,
                min_count=spec.min_count if spec.fixed_count is None else spec.fixed_count,
                max_count=spec.max_count if spec.fixed_count is None else spec.fixed_count,
                components=components,
                default=port.name == default,
            )
        )
    return tuple(views)


def _default_port(ports: tuple[PortView, ...]) -> str | None:
    return next((port.name for port in ports if port.default), None)


def describe_config(path: str | Path) -> ConfigView:
    """The graph as the files at ``path`` write it.

    Raises:
        ConfigError: If the files do not render (a syntax error): there is no graph to
            show. A config that renders but does not build is described, with ``error``.
        FileNotFoundError: If the file doesn't exist.
    """
    ensure_nodes_loaded()
    graph = load_written(path)
    tree = render_written(graph)
    graph_block = graph_directive(tree)

    nodes: list[NodeView] = []
    built: dict[str, NodeView] = {}
    for directive in children(graph_block, "node"):
        node_type, node_id = node_spec(directive, tree)
        inputs: tuple[PortView, ...] = ()
        outputs: tuple[PortView, ...] = ()
        error: str | None = None
        try:
            node_class, config = _node_config(node_type, node_id, directive, tree)
            node = node_class(config)
            inputs, outputs = _ports(get_inputs(node)), _ports(get_outputs(node))
        except (ConfigError, ValueError, TypeError) as caught:
            error = getattr(caught, "message", None) or str(caught)
        settings = tuple(
            (child.name, " ".join(value.text for value in child.values))
            for child in children(directive)
            if child.name not in ("connect", "edge")
        )
        view = NodeView(
            id=node_id,
            type=node_type,
            place=_place(directive),
            locked=lock_reason(directive),
            settings=settings,
            inputs=inputs,
            outputs=outputs,
            error=error,
        )
        nodes.append(view)
        built[node_id] = view

    edges: list[EdgeView] = []
    for node in nodes:
        directive = next(d for d in children(graph_block, "node") if node_spec(d, tree)[1] == node.id)
        for line in children(directive, "connect"):
            values = [value.text for value in line.values]
            source = values[0] if values else ""
            port = values[1] if len(values) > 1 else None
            try:
                descriptor = parse_connect_directive(line)
                ref = parse_port_ref(descriptor.source)
                source_node = ref.node
                repeat = descriptor.repeat if descriptor.repeat > 1 else None
                repeat_until = descriptor.repeat_until
            except ValueError:
                ref, source_node, repeat, repeat_until = None, None, None, None
            source_port = ref.port if ref is not None else None
            if source_port is None and source_node in built:
                source_port = _default_port(built[source_node].outputs)
            target_port = None
            if port is not None:
                try:
                    target_port = parse_port_ref(port.replace("~", ":")).node
                except ValueError:
                    target_port = None
            else:
                target_port = _default_port(node.inputs)
            edges.append(
                EdgeView(
                    target=node.id,
                    source=source,
                    port=port,
                    source_node=source_node,
                    source_port=source_port,
                    target_port=target_port,
                    repeat=repeat,
                    repeat_until=repeat_until,
                    place=_place(line),
                    locked=lock_reason(line),
                )
            )

    try:
        build_plan(tree)
        whole_error = None
    except ConfigError as caught:
        whole_error = caught

    return ConfigView(
        path=str(Path(path)),
        version=version_of(graph),
        nodes=tuple(nodes),
        edges=tuple(edges),
        error=whole_error,
    )


@dataclass(frozen=True)
class NodeTypeView:
    """A node type the palette offers.

    Attributes:
        name: The name a ``node`` line uses (the primary one).
        aliases: Other names it is registered under.
        summary: The first line of the class's docstring; empty without one.
        schema: The JSON Schema of its settings (``export_node_schemas``); None when the
            type has no config model.
    """

    name: str
    aliases: tuple[str, ...]
    summary: str
    schema: dict[str, Any] | None


def node_types() -> tuple[NodeTypeView, ...]:
    """Every registered node type, by primary name, sorted by name."""
    from rasl.graph.node.registry import export_node_schemas, get_node_registry

    ensure_nodes_loaded()
    schemas = export_node_schemas()
    names: dict[type, list[str]] = {}
    for name, cls in get_node_registry().items():
        names.setdefault(cls, []).append(name)
    views = []
    for cls, registered in names.items():
        # The name configs write: not the class name ("Color", not "ColorNode")
        primary = next((name for name in registered if not name.endswith("Node")), registered[0])
        schema = next((schemas[name] for name in registered if name in schemas), None)
        doc = (cls.__doc__ or "").strip().splitlines()
        views.append(
            NodeTypeView(
                name=primary,
                aliases=tuple(name for name in registered if name != primary),
                summary=doc[0].strip() if doc else "",
                schema=schema,
            )
        )
    return tuple(sorted(views, key=lambda view: view.name.lower()))


def preview_node(type_name: str, values: str = "", settings: tuple[tuple[str, str], ...] = ()) -> NodeView:
    """A node that is not in the config yet, built on its own to show its ports.

    Takes what ``AddNode`` takes. The node is never started.

    Raises:
        ConfigError: If the text does not parse.
    """
    from rasl.config.document import parse_document

    ensure_nodes_loaded()
    body = "".join(f"{key} {text};" for key, text in settings)
    line = f"node {type_name} preview" + (f" {values}" if values else "") + f" {{ {body} }}"
    tree = parse_document(f"graph {{ {line} }}")
    directive = children(graph_directive(tree), "node")[0]
    inputs: tuple[PortView, ...] = ()
    outputs: tuple[PortView, ...] = ()
    error: str | None = None
    try:
        node_class, config = _node_config(type_name, "preview", directive, tree)
        node = node_class(config)
        inputs, outputs = _ports(get_inputs(node)), _ports(get_outputs(node))
    except (ConfigError, ValueError, TypeError) as caught:
        error = getattr(caught, "message", None) or str(caught)
    return NodeView(
        id="preview",
        type=type_name,
        place=Place("", 0),
        locked=None,
        settings=settings,
        inputs=inputs,
        outputs=outputs,
        error=error,
    )
