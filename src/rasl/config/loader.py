"""Configuration loader for RASL graph definitions.

This module parses crossplane-syntax configuration files and constructs
an ExecutionPlan ready for Runtime execution. The config format uses
nginx-style syntax to define nodes and connections.

Node configuration is validated against each node's nested Config class
(Pydantic model), enabling a plugin architecture where the loader has
no knowledge of specific node implementations.

Connection syntax (uses '.' to separate node from port):
    connect <source> <dest>;                    # Connect default ports
    connect <source>.<port> <dest>;             # Explicit source port
    connect <source> <dest>.<port>;             # Explicit dest port
    connect <source>.<port> <dest>.<port>;      # Both explicit
    connect <source>[0:100] <dest>[0:100];      # Channel slices

Example config file:
    rasl {
        node SineSource sine {
            output_channels 512;
            frequency_hz 1.0;
            fps 30;
        }
        node ConsoleSink console {
            max_channels 16;
            connect sine;  # Nested connect uses default ports
        }
        connect sine console;  # Top-level connect
    }
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import crossplane
from pydantic import ValidationError

from rasl.config.connect_parser import ResolvedSlice, parse_connect, ConnectParseError
from rasl.engine.graph import ExecutionPlan, GraphBuilder
from rasl.engine.registry import ensure_nodes_loaded, get_node_class


@dataclass(frozen=True, slots=True)
class ParsedConnection:
    """Result of parsing a connect directive.

    Contains fully resolved node IDs, port names, and optional slice info.
    """

    source_node: str
    source_port: str
    target_node: str
    target_port: str
    source_slice: Optional[ResolvedSlice] = None
    target_slice: Optional[ResolvedSlice] = None


class ConfigError(Exception):
    """Error raised when config parsing or validation fails.

    Attributes:
        message: Description of the error.
        line: Line number where error occurred (if available).
    """

    def __init__(self, message: str, line: int | None = None) -> None:
        """Initialize the config error.

        Args:
            message: Description of the parsing error.
            line: Optional line number in the config file.
        """
        self.line = line
        super().__init__(f"Config error{f' at line {line}' if line else ''}: {message}")


# ─────────────────────────────────────────────────────────────────────
# AST to Dict Extraction
# ─────────────────────────────────────────────────────────────────────


def _coerce_value(value: str) -> str | int | float | bool:
    """Coerce a string value to appropriate Python type."""
    lowered = value.lower()
    if lowered in ("true", "on", "yes"):
        return True
    if lowered in ("false", "off", "no"):
        return False
    # Try integer
    try:
        return int(value)
    except ValueError:
        pass
    # Try float
    try:
        return float(value)
    except ValueError:
        pass
    # Strip surrounding quotes from strings
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def _extract_block_dict(block: dict[str, Any]) -> dict[str, Any]:
    """Extract a dict from a crossplane block's directives.

    Handles nested blocks (segment, defaults), multi-value directives,
    and repeated directives (accumulated as list-of-lists).
    """
    result: dict[str, Any] = {}

    def _accumulate(key: str, value: Any) -> None:
        """Add value to result, accumulating repeated keys as list-of-lists."""
        if key not in result:
            result[key] = value
        else:
            existing = result[key]
            # Convert to list-of-values for repeated directives
            if not isinstance(existing, list):
                result[key] = [existing, value]
            elif existing and isinstance(existing[0], list):
                # Already a list-of-lists, append
                result[key].append(value)
            else:
                # First repetition: convert [a, b] to [[a, b], new_value]
                result[key] = [existing, value]

    for directive in block.get("block", []):
        name = directive.get("directive")
        args = directive.get("args", [])
        child_block = directive.get("block")

        if child_block:
            # Nested block (e.g., segment, defaults, ports)
            child_dict = _extract_block_dict(directive)
            if name == "segment":
                result.setdefault("segments", []).append(child_dict)
            elif name == "defaults":
                result["defaults"] = child_dict
            else:
                result[name] = child_dict
        elif len(args) == 0:
            # Flag directive (presence = true)
            result[name] = True
        elif len(args) == 1:
            _accumulate(name, _coerce_value(args[0]))
        else:
            # Multiple args → list
            _accumulate(name, [_coerce_value(a) for a in args])

    return result


def _parse_metadata(raw: dict[str, Any]) -> dict[str, str]:
    """Parse metadata from raw config dict.

    Handles both single string and list of "key=value" strings.
    """
    metadata_value = raw.pop("metadata", None)
    if metadata_value is None:
        return {}

    metadata: dict[str, str] = {}
    # Handle both single string and list of strings
    items = [metadata_value] if isinstance(metadata_value, str) else metadata_value
    for item in items:
        item_str = str(item)
        if "=" in item_str:
            key, value = item_str.split("=", 1)
            metadata[key] = value
    return metadata


# ─────────────────────────────────────────────────────────────────────
# Node Building
# ─────────────────────────────────────────────────────────────────────


def _build_node(
    node_type: str,
    node_id: str,
    block: dict[str, Any],
    extra_args: dict[str, str] | None = None,
) -> Any:
    """Build a node instance with validated configuration.

    Looks up the node class from the registry, extracts raw config from
    the AST block, validates it against the node's Config class, and
    instantiates the node.

    Args:
        node_type: Node type name (e.g., "SineSourceNode").
        node_id: Unique node identifier.
        block: Crossplane AST block for the node.
        extra_args: Additional config values from positional arguments
            (e.g., {"model": "rgb"} for Color nodes).

    Returns:
        Instantiated node.

    Raises:
        ConfigError: If node type is unknown or config validation fails.
    """
    node_class = get_node_class(node_type)
    if node_class is None:
        raise ConfigError(f"Unknown node type '{node_type}'")

    # Get Config class from node
    config_class = getattr(node_class, "Config", None)
    if config_class is None:
        raise ConfigError(f"Node type '{node_type}' does not define a Config class")

    # Extract raw config from AST
    raw_config = _extract_block_dict(block)
    raw_config["id"] = node_id

    # Merge extra args from positional arguments (e.g., model for Color nodes)
    if extra_args:
        raw_config.update(extra_args)

    # Handle metadata specially (key=value format)
    if "metadata" in raw_config:
        raw_config["metadata"] = _parse_metadata(raw_config)

    # Remove directives that are not part of the config model
    raw_config.pop("type", None)
    raw_config.pop("connect", None)  # Nested connect blocks handled separately
    raw_config.pop("edge", None)  # Alias for connect

    # Validate with Pydantic
    try:
        validated_config = config_class.model_validate(raw_config)
    except ValidationError as e:
        errors = "; ".join(
            f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}"
            for err in e.errors()
        )
        raise ConfigError(f"Invalid config for node '{node_id}': {errors}")

    # Instantiate node
    return node_class(validated_config)


# ─────────────────────────────────────────────────────────────────────
# Connection Parsing
# ─────────────────────────────────────────────────────────────────────


def _get_directive_value(block: dict[str, Any], name: str) -> str | None:
    """Get single value for a directive from a block."""
    for directive in block.get("block", []):
        if directive.get("directive") == name:
            args = directive.get("args", [])
            return args[0] if args else None
    return None


def _split_node_port(spec: str) -> tuple[str, str | None]:
    """Split a spec like 'node.port[slice]' or 'node[slice]' into (node_with_slice, port).

    Uses '.' as the separator between node and port, handling slices correctly.
    Returns (spec, None) if no port separator found.

    Examples:
        'twinkle' -> ('twinkle', None)
        'twinkle.out' -> ('twinkle', 'out')
        'twinkle[0:151]' -> ('twinkle[0:151]', None)
        'twinkle.out[0:151]' -> ('twinkle', 'out[0:151]')
    """
    # Find the first '.' that's not inside brackets
    bracket_depth = 0
    for i, ch in enumerate(spec):
        if ch == '[':
            bracket_depth += 1
        elif ch == ']':
            bracket_depth -= 1
        elif ch == '.' and bracket_depth == 0:
            return spec[:i], spec[i + 1:]
    return spec, None


def _extract_node_name(spec: str) -> str:
    """Extract just the node name from a spec, stripping port and slice.

    Examples:
        'twinkle' -> 'twinkle'
        'twinkle.out' -> 'twinkle'
        'twinkle[0:151]' -> 'twinkle'
        'twinkle.out[0:151]' -> 'twinkle'
    """
    # First strip any slice
    bracket_pos = spec.find('[')
    if bracket_pos != -1:
        spec = spec[:bracket_pos]
    # Then strip any port
    dot_pos = spec.find('.')
    if dot_pos != -1:
        spec = spec[:dot_pos]
    return spec


def _parse_port_with_slice(
    spec: str,
) -> tuple[str, Optional[ResolvedSlice]]:
    """Parse a port spec like 'port' or 'port[0:151]' into (port_name, slice).

    Args:
        spec: Port specification, optionally with slice notation.

    Returns:
        Tuple of (port_name, slice_or_none).
    """
    bracket_pos = spec.find('[')
    if bracket_pos == -1:
        return spec, None

    port_name = spec[:bracket_pos]
    slice_str = spec[bracket_pos:]

    # Parse the slice using a mini-parser
    # Format: [start:end] or [start:] or [n]
    inner = slice_str[1:-1]  # Strip [ and ]
    if ':' in inner:
        parts = inner.split(':', 1)
        start = int(parts[0])
        end = int(parts[1]) if parts[1] else None
        return port_name, ResolvedSlice(start, end)
    else:
        # Single index [n] -> [n:n+1]
        n = int(inner)
        return port_name, ResolvedSlice(n, n + 1)


def _parse_connect_directive(
    directive: dict[str, Any],
    current_node_id: str | None,
    default_outputs: dict[str, str],
    default_inputs: dict[str, str],
    current_node_inputs: set[str] | None = None,
) -> ParsedConnection:
    """Parse a connect directive into a ParsedConnection.

    Syntax uses '.' to separate node from port (not ':'), supporting slices:
        connect <source> <dest>;                    # Both use default ports
        connect <source>.<port> <dest>;             # Explicit source port
        connect <source> <dest>.<port>;             # Explicit dest port
        connect <source>.<port> <dest>.<port>;      # Both explicit
        connect <source>[slice] <dest>[slice];      # Channel slices

    When nested inside a node block:
        connect <source>;                           # source -> current_node (default port)
        connect <source> <port>;                    # source -> current_node:<port>
        connect <source>[slice] <port>[slice];      # With slices

    Args:
        directive: The crossplane AST directive.
        current_node_id: If nested in a node block, the containing node's ID.
        default_outputs: Map of node_id -> default output port name.
        default_inputs: Map of node_id -> default input port name.
        current_node_inputs: Set of input port names on current node (for nested connects).

    Returns:
        ParsedConnection with resolved nodes, ports, and optional slices.

    Raises:
        ConfigError: If the connect syntax is invalid.
    """
    args = directive.get("args", [])

    if len(args) == 0:
        raise ConfigError("connect requires at least one argument")

    source_slice: Optional[ResolvedSlice] = None
    target_slice: Optional[ResolvedSlice] = None

    if len(args) == 1:
        # Single arg: connect <source>; (must be nested in a node)
        if current_node_id is None:
            raise ConfigError(
                "connect with single argument must be nested inside a node block"
            )
        source_spec = args[0]
        target_node = current_node_id
        target_port = default_inputs.get(target_node)
        if not target_port:
            raise ConfigError(
                f"Node '{target_node}' has no default input port; "
                "use 'connect source port' syntax"
            )
    elif len(args) == 2:
        # Two args: connect <source> <dest>;
        source_spec = args[0]
        dest_spec = args[1]

        # Parse destination using '.' separator (handles slices correctly)
        dest_node_part, dest_port_part = _split_node_port(dest_spec)

        if dest_port_part is not None:
            # Explicit: node.port or node.port[slice]
            target_node = dest_node_part
            target_port, target_slice = _parse_port_with_slice(dest_port_part)
        else:
            # No '.', so dest_spec is either:
            # - A port name on current node (nested connect): "universe0[0:151]"
            # - A node name (top-level connect): "console"
            dest_base = _extract_node_name(dest_spec)

            # Check if it's a port on the current node (nested connect)
            if current_node_id is not None and current_node_inputs and dest_base in current_node_inputs:
                # Nested: connect source port[slice]; -> current_node:port[slice]
                target_node = current_node_id
                target_port, target_slice = _parse_port_with_slice(dest_spec)
            else:
                # Top-level: dest is another node, use default input port
                target_node = _extract_node_name(dest_spec)
                target_port = default_inputs.get(target_node)
                if not target_port:
                    raise ConfigError(
                        f"Node '{target_node}' has no default input port; "
                        "use 'connect source dest.port' syntax"
                    )
                # If dest_spec had a slice, extract it for the target
                if '[' in dest_spec:
                    _, target_slice = _parse_port_with_slice(dest_spec)
    else:
        raise ConfigError(
            f"connect takes 1 or 2 arguments, got {len(args)}: {args}"
        )

    # Parse source using '.' separator (handles slices correctly)
    source_node_part, source_port_part = _split_node_port(source_spec)

    if source_port_part is not None:
        # Explicit: node.port or node.port[slice]
        source_node = source_node_part
        source_port, source_slice = _parse_port_with_slice(source_port_part)
    else:
        # No '.', use default output port
        source_node = _extract_node_name(source_spec)
        source_port = default_outputs.get(source_node)
        if not source_port:
            raise ConfigError(
                f"Node '{source_node}' has no default output port; "
                "use 'connect source.port dest' syntax"
            )
        # If source_spec had a slice, extract it
        if '[' in source_spec:
            _, source_slice = _parse_port_with_slice(source_spec)

    return ParsedConnection(
        source_node=source_node,
        source_port=source_port,
        target_node=target_node,
        target_port=target_port,
        source_slice=source_slice,
        target_slice=target_slice,
    )


# ─────────────────────────────────────────────────────────────────────
# Main Parser
# ─────────────────────────────────────────────────────────────────────


def parse_config(config_text: str) -> ExecutionPlan:
    """Parse config text and build an ExecutionPlan.

    Args:
        config_text: Configuration in crossplane/nginx syntax.

    Returns:
        Compiled ExecutionPlan ready for Runtime.

    Raises:
        ConfigError: If parsing fails or config is invalid.
    """
    # Ensure all node plugins are loaded
    ensure_nodes_loaded()

    # crossplane requires a file, write to temp
    with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
        f.write(config_text)
        temp_path = f.name

    try:
        parsed = crossplane.parse(temp_path, catch_errors=False)
    finally:
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

    # Track default input/output ports for sugar in connect blocks
    default_inputs: dict[str, str] = {}
    default_outputs: dict[str, str] = {}
    all_inputs: dict[str, set[str]] = {}  # All input port names per node

    # First pass: build all nodes
    for directive in rasl_block.get("block", []):
        if directive.get("directive") != "node":
            continue

        args = directive.get("args", [])
        if not args:
            raise ConfigError("Node directive requires a name")

        # Support multiple syntax forms:
        #   node <id> { type Foo; }
        #   node Foo <id> { ... }
        #   node Color <id> <model> { ... }  # Optional third arg for Color nodes
        if len(args) == 1:
            node_id = args[0]
            node_type = _get_directive_value(directive, "type")
            if not node_type:
                raise ConfigError(f"Node '{node_id}' requires 'type' directive")
            extra_args: dict[str, str] = {}
        elif len(args) == 2:
            # Standard syntax: first arg is type, second is node id
            node_type = args[0]
            node_id = args[1]
            extra_args = {}
        elif len(args) == 3:
            # Extended syntax: node Color <id> <model> { ... }
            node_type = args[0]
            node_id = args[1]
            # Third arg is type-specific; for Color nodes it's the model
            if node_type in ("Color", "ColorNode"):
                extra_args = {"model": args[2]}
            else:
                raise ConfigError(
                    f"Node type '{node_type}' does not accept a third positional argument"
                )
        else:
            raise ConfigError(
                f"Node directive takes 1-3 arguments, got {len(args)}: {args}"
            )

        node = _build_node(node_type, node_id, directive, extra_args=extra_args)
        builder.add_node(node)

        # Record ports for connect sugar
        inputs = getattr(node, "inputs", None)
        outputs = getattr(node, "outputs", None)

        if inputs is not None and hasattr(inputs, "names"):
            if len(inputs.names) == 1:
                default_inputs[node_id] = inputs.names[0]
            # Track all input port names for nested connect resolution
            all_inputs[node_id] = set(inputs.names)

        if outputs is not None and hasattr(outputs, "names"):
            if len(outputs.names) == 1:
                default_outputs[node_id] = outputs.names[0]

    # Second pass: build all connections
    for directive in rasl_block.get("block", []):
        kind = directive.get("directive")

        # Top-level connect directives
        if kind == "connect":
            conn = _parse_connect_directive(
                directive,
                current_node_id=None,
                default_outputs=default_outputs,
                default_inputs=default_inputs,
            )
            builder.connect(
                conn.source_node,
                conn.source_port,
                conn.target_node,
                conn.target_port,
                conn.source_slice,
                conn.target_slice,
            )

        # Nested connect directives inside node definitions
        if kind == "node":
            args = directive.get("args", [])
            if not args:
                continue

            node_id = args[1] if len(args) > 1 else args[0]
            current_node_inputs = all_inputs.get(node_id)

            for child in directive.get("block", []):
                if child.get("directive") == "connect":
                    conn = _parse_connect_directive(
                        child,
                        current_node_id=node_id,
                        default_outputs=default_outputs,
                        default_inputs=default_inputs,
                        current_node_inputs=current_node_inputs,
                    )
                    builder.connect(
                        conn.source_node,
                        conn.source_port,
                        conn.target_node,
                        conn.target_port,
                        conn.source_slice,
                        conn.target_slice,
                    )

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
