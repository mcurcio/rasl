"""Configuration loader for RASL graph definitions.

This module parses crossplane-syntax configuration files and constructs
an ExecutionPlan ready for Runtime execution. The config format uses
nginx-style syntax to define nodes and edges.

Example config file:
    rasl {
        node sacnSource {
            type SacnSourceNode;
            universes 1 2;
        }
        node patch {
            type UniversePatchTransform;
            output universe0;
            segment { source_universe 1; source_channel 1; length 150; target_channel 1; }
        }
        node sink {
            type SacnSinkNode;
            input universe0;
            target_host "10.0.60.30";
            target_universe 0;
        }
        edge { from sacnSource:dmx; to patch:dmx; }
        edge { from patch:universe0; to sink:universe0; }
    }
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import crossplane

from rasl.engine.graph import ExecutionPlan, GraphBuilder
from rasl.engine.node_config import (
    NodeKind,
    PortIOConfig,
    SinkNodeConfig,
    SourceNodeConfig,
    TimingConfig,
    TransformNodeConfig,
)
from rasl.nodes import (
    ConsoleSinkNode,
    SacnSinkNode,
    SacnSourceNode,
    Segment,
    SineSourceNode,
    UniversePatchTransform,
)


_NODE_TYPE_ALIASES: Dict[str, str] = {
    "SacnSource": "SacnSourceNode",
    "SineSource": "SineSourceNode",
    "UniversePatch": "UniversePatchTransform",
    "SacnSink": "SacnSinkNode",
    "ConsoleSink": "ConsoleSinkNode",
}


def _canonical_node_type(node_type: str) -> str:
    """Map user-facing node type names to canonical implementation types."""

    return _NODE_TYPE_ALIASES.get(node_type, node_type)


class ConfigError(Exception):
    """Error raised when config parsing fails.

    Attributes:
        message: Description of the error.
        line: Line number where error occurred (if available).
    """

    def __init__(self, message: str, line: Optional[int] = None) -> None:
        """Initialize the config error.

        Args:
            message: Description of the parsing error.
            line: Optional line number in the config file.
        """
        self.line = line
        super().__init__(f"Config error{f' at line {line}' if line else ''}: {message}")


def _get_directive_args(block: Dict[str, Any], name: str) -> List[str]:
    """Extract arguments for a directive from a block.

    Args:
        block: Parsed block containing directives.
        name: Name of the directive to find.

    Returns:
        List of string arguments for the directive.
    """
    for directive in block.get("block", []):
        if directive.get("directive") == name:
            return directive.get("args", [])
    return []


def _get_directive_value(
    block: Dict[str, Any], name: str, default: Optional[str] = None
) -> Optional[str]:
    """Get single value for a directive.

    Args:
        block: Parsed block containing directives.
        name: Name of the directive to find.
        default: Default value if directive not found.

    Returns:
        First argument of the directive, or default.
    """
    args = _get_directive_args(block, name)
    return args[0] if args else default


def _get_directive_int(
    block: Dict[str, Any], name: str, default: int = 0
) -> int:
    """Get integer value for a directive.

    Args:
        block: Parsed block containing directives.
        name: Name of the directive to find.
        default: Default value if directive not found.

    Returns:
        Integer value of the directive.
    """
    value = _get_directive_value(block, name)
    return int(value) if value is not None else default


def _get_directive_float(
    block: Dict[str, Any], name: str, default: float = 0.0
) -> float:
    value = _get_directive_value(block, name)
    try:
        return float(value) if value is not None else default
    except ValueError:
        return default


def _get_directive_bool(
    block: Dict[str, Any], name: str, default: bool = False
) -> bool:
    value = _get_directive_value(block, name)
    if value is None:
        return default
    lowered = value.lower()
    if lowered in ("1", "true", "on", "yes"):
        return True
    if lowered in ("0", "false", "off", "no"):
        return False
    return default


def _parse_segment(segment_block: Dict[str, Any], defaults: Dict[str, int]) -> Segment:
    """Parse a segment definition from a block.

    Args:
        segment_block: Parsed segment block.
        defaults: Default values for segment fields.

    Returns:
        Segment instance with parsed values.
    """
    return Segment(
        source_universe=_get_directive_int(
            segment_block, "source_universe", defaults.get("source_universe", 1)
        ),
        source_channel=_get_directive_int(
            segment_block, "source_channel", defaults.get("source_channel", 1)
        ),
        length=_get_directive_int(
            segment_block, "length", defaults.get("length", 512)
        ),
        target_channel=_get_directive_int(
            segment_block, "target_channel", defaults.get("target_channel", 1)
        ),
    )


def _parse_defaults(node_block: Dict[str, Any]) -> Dict[str, int]:
    """Parse defaults block within a node.

    Args:
        node_block: Parsed node block containing defaults.

    Returns:
        Dictionary of default values.
    """
    defaults: Dict[str, int] = {}
    for directive in node_block.get("block", []):
        if directive.get("directive") == "defaults":
            defaults["source_universe"] = _get_directive_int(directive, "source_universe", 1)
            defaults["source_channel"] = _get_directive_int(directive, "source_channel", 1)
            defaults["length"] = _get_directive_int(directive, "length", 512)
            break
    return defaults


def _build_sacn_source(node_id: str, block: Dict[str, Any]) -> SacnSourceNode:
    """Build a SacnSourceNode from config block.

    Args:
        node_id: Unique node identifier.
        block: Parsed node configuration block.

    Returns:
        Configured SacnSourceNode instance.
    """
    universes = [int(u) for u in _get_directive_args(block, "universes")]
    if not universes:
        raise ConfigError(f"Node '{node_id}' requires at least one universe")

    bind_address = _get_directive_value(block, "bind_address", "0.0.0.0")
    bind_port = _get_directive_int(block, "bind_port", 5568)

    # Parse metadata from "metadata" directive
    metadata: Dict[str, str] = {}
    for meta_str in _get_directive_args(block, "metadata"):
        if "=" in meta_str:
            key, value = meta_str.split("=", 1)
            metadata[key] = value

    timing = TimingConfig(fps=None)
    # sACN frames are DMX-shaped, so default to 512 channels on 'dmx' output.
    output_cfg = PortIOConfig(channels=512, port="dmx")
    params: Dict[str, Any] = {
        "universes": universes,
        "bind_address": bind_address or "0.0.0.0",
        "bind_port": bind_port,
    }
    if metadata:
        params["metadata"] = metadata

    config = SourceNodeConfig(
        id=node_id,
        type_id="SacnSourceNode",
        kind=NodeKind.SOURCE,
        timing=timing,
        params=params,
        output=output_cfg,
    )

    return SacnSourceNode(config)


def _build_sine_source(node_id: str, block: Dict[str, Any]) -> SineSourceNode:
    # Engine-owned output shape: allow either legacy `channels` or new `outputs`.
    channels = _get_directive_int(block, "channels", 512)
    outputs = _get_directive_int(block, "outputs", channels)
    channels = outputs if outputs > 0 else channels
    frequency_hz = _get_directive_float(block, "frequency_hz", 1.0)
    fps = _get_directive_int(block, "fps", 30)
    amplitude = _get_directive_float(block, "amplitude", 0.5)
    offset = _get_directive_float(block, "offset", 0.5)

    metadata: Dict[str, str] = {}
    for meta_str in _get_directive_args(block, "metadata"):
        if "=" in meta_str:
            key, value = meta_str.split("=", 1)
            metadata[key] = value

    timing = TimingConfig(fps=float(fps) if fps > 0 else None)
    output_cfg = PortIOConfig(channels=channels, port="dmx")
    params: Dict[str, Any] = {
        "frequency_hz": frequency_hz,
        "amplitude": amplitude,
        "offset": offset,
    }
    topic = _get_directive_value(block, "topic")
    if topic is not None:
        params["topic"] = topic
    if metadata:
        params["metadata"] = metadata

    config = SourceNodeConfig(
        id=node_id,
        type_id="SineSourceNode",
        kind=NodeKind.SOURCE,
        timing=timing,
        params=params,
        output=output_cfg,
    )

    return SineSourceNode(config)


def _build_universe_patch(node_id: str, block: Dict[str, Any]) -> UniversePatchTransform:
    """Build a UniversePatchTransform from config block.

    Args:
        node_id: Unique node identifier.
        block: Parsed node configuration block.

    Returns:
        Configured UniversePatchTransform instance.
    """
    output_port = _get_directive_value(block, "output", "output") or "output"
    defaults = _parse_defaults(block)

    segments: List[Segment] = []
    for directive in block.get("block", []):
        if directive.get("directive") == "segment":
            segments.append(_parse_segment(directive, defaults))

    if not segments:
        raise ConfigError(f"Node '{node_id}' requires at least one segment")

    # Compute buffer length based on segments to size the output port.
    buffer_length = max(seg.target_channel - 1 + seg.length for seg in segments)

    timing = TimingConfig(fps=None)
    input_cfg = PortIOConfig(channels=512, port="dmx")
    output_cfg = PortIOConfig(channels=buffer_length, port=output_port)
    params: Dict[str, Any] = {"segments": segments}

    config = TransformNodeConfig(
        id=node_id,
        type_id="UniversePatchTransform",
        kind=NodeKind.TRANSFORM,
        timing=timing,
        params=params,
        input=input_cfg,
        output=output_cfg,
    )

    return UniversePatchTransform(config)


def _build_sacn_sink(node_id: str, block: Dict[str, Any]) -> SacnSinkNode:
    """Build a SacnSinkNode from config block.

    Args:
        node_id: Unique node identifier.
        block: Parsed node configuration block.

    Returns:
        Configured SacnSinkNode instance.
    """
    input_port = _get_directive_value(block, "input", "input") or "input"
    target_host = _get_directive_value(block, "target_host")
    if not target_host:
        raise ConfigError(f"Node '{node_id}' requires target_host")

    target_universe = _get_directive_int(block, "target_universe", 0)
    min_interval_ms = _get_directive_int(block, "min_interval_ms", 25)
    source_name = _get_directive_value(block, "source_name", "RASL")
    priority = _get_directive_int(block, "priority", 100)

    timing = TimingConfig(fps=None)
    input_cfg = PortIOConfig(channels=512, port=input_port)
    params: Dict[str, Any] = {
        "target_host": target_host,
        "target_universe": target_universe,
        "min_interval_ms": min_interval_ms,
        "source_name": source_name or "RASL",
        "priority": priority,
    }

    config = SinkNodeConfig(
        id=node_id,
        type_id="SacnSinkNode",
        kind=NodeKind.SINK,
        timing=timing,
        params=params,
        input=input_cfg,
    )

    return SacnSinkNode(config)


def _build_console_sink(node_id: str, block: Dict[str, Any]) -> ConsoleSinkNode:
    input_port = _get_directive_value(block, "input", "input") or "input"
    max_channels = _get_directive_int(block, "max_channels", 16)
    as_bytes = _get_directive_bool(block, "as_bytes", True)
    every_n = _get_directive_int(block, "every_n", 1)
    include_metadata = _get_directive_bool(block, "include_metadata", True)
    label = _get_directive_value(block, "label")

    timing = TimingConfig(fps=None)
    input_cfg = PortIOConfig(channels=max_channels, port=input_port)
    params: Dict[str, Any] = {
        "max_channels": max_channels,
        "as_bytes": as_bytes,
        "every_n": every_n,
        "include_metadata": include_metadata,
    }
    if label is not None:
        params["label"] = label

    config = SinkNodeConfig(
        id=node_id,
        type_id="ConsoleSinkNode",
        kind=NodeKind.SINK,
        timing=timing,
        params=params,
        input=input_cfg,
    )

    return ConsoleSinkNode(config)


def _parse_edge(edge_block: Dict[str, Any]) -> Tuple[str, str, str, str]:
    """Parse an edge definition from a block.

    Args:
        edge_block: Parsed edge block.

    Returns:
        Tuple of (source_node, source_port, target_node, target_port).

    Raises:
        ConfigError: If edge format is invalid.
    """
    from_spec = _get_directive_value(edge_block, "from")
    to_spec = _get_directive_value(edge_block, "to")

    if not from_spec or not to_spec:
        raise ConfigError("Edge requires 'from' and 'to' directives")

    # Parse "nodeId:portName" format
    if ":" not in from_spec or ":" not in to_spec:
        raise ConfigError(f"Edge endpoints must be 'node:port' format, got from='{from_spec}' to='{to_spec}'")

    source_node, source_port = from_spec.split(":", 1)
    target_node, target_port = to_spec.split(":", 1)

    return source_node, source_port, target_node, target_port


def parse_config(config_text: str) -> ExecutionPlan:
    """Parse config text and build an ExecutionPlan.

    Args:
        config_text: Configuration in crossplane/nginx syntax.

    Returns:
        Compiled ExecutionPlan ready for Runtime.

    Raises:
        ConfigError: If parsing fails or config is invalid.
    """
    try:
        parsed = crossplane.parse(
            filename="<string>",
            catch_errors=False,
        )
    except Exception as e:
        # crossplane.parse needs a file, use build instead
        pass

    # Use crossplane.build to parse string content
    try:
        # crossplane expects file-based parsing, so we'll parse manually
        # For now, use lexer approach
        parsed = crossplane.build(
            payload=[{"file": "<config>", "parsed": []}],
        )
    except Exception:
        pass

    # Actually parse the config string using crossplane's lower-level API
    from io import StringIO

    # crossplane.parse expects a filename, let's write to temp
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
        f.write(config_text)
        temp_path = f.name

    try:
        parsed = crossplane.parse(temp_path, catch_errors=False)
    finally:
        import os
        os.unlink(temp_path)

    if parsed.get("errors"):
        raise ConfigError(f"Parse errors: {parsed['errors']}")

    config = parsed.get("config", [])
    if not config:
        raise ConfigError("Empty configuration")

    # Find the rasl {} block
    rasl_block = None
    for file_config in config:
        for directive in file_config.get("parsed", []):
            if directive.get("directive") == "rasl":
                rasl_block = directive
                break
        if rasl_block:
            break

    if not rasl_block:
        raise ConfigError("No 'rasl' block found in configuration")

    builder = GraphBuilder()

    # First pass: build all nodes
    for directive in rasl_block.get("block", []):
        if directive.get("directive") == "node":
            args = directive.get("args", [])
            if not args:
                raise ConfigError("Node directive requires a name")

            # Support both legacy and new syntax:
            #   node <id> { type Foo; }
            #   node Foo <id> { ... }
            if len(args) == 1:
                node_id = args[0]
                node_type = _get_directive_value(directive, "type")
                if not node_type:
                    raise ConfigError(f"Node '{node_id}' requires 'type' directive")
            else:
                # New syntax: first arg is type, second is node id
                node_type = args[0]
                node_id = args[1]

            node_type = _canonical_node_type(node_type)

            if node_type == "SacnSourceNode":
                node = _build_sacn_source(node_id, directive)
            elif node_type == "UniversePatchTransform":
                node = _build_universe_patch(node_id, directive)
            elif node_type == "SacnSinkNode":
                node = _build_sacn_sink(node_id, directive)
            elif node_type == "SineSourceNode":
                node = _build_sine_source(node_id, directive)
            elif node_type == "ConsoleSinkNode":
                node = _build_console_sink(node_id, directive)
            else:
                raise ConfigError(f"Unknown node type '{node_type}'")

            builder.add_node(node)

    # Second pass: build all edges
    for directive in rasl_block.get("block", []):
        if directive.get("directive") == "edge":
            source_node, source_port, target_node, target_port = _parse_edge(directive)
            builder.connect(source_node, source_port, target_node, target_port)

    return builder.build()


def load_config(config_path: str | Path) -> ExecutionPlan:
    """Load config from file and build an ExecutionPlan.

    Args:
        config_path: Path to the configuration file.

    Returns:
        Compiled ExecutionPlan ready for Runtime.

    Raises:
        ConfigError: If loading or parsing fails.
        FileNotFoundError: If config file doesn't exist.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    config_text = path.read_text()
    return parse_config(config_text)
