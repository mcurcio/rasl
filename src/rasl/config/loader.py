"""Configuration loader using Directive-based parsing.

This module provides the config loader that uses the Directive tree
for parsing RASL graph configurations.

The loader handles:
- `graph` block: Top-level graph container
- `node` blocks: Dispatched to node classes for construction

Nodes handle their own `connect` directives via BaseNode.parse_connect_directives().
The Graph resolves connection descriptors into edges using node port info.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import ValidationError

from rasl.config.connection import parse_port_ref
from rasl.config.directive import Directive
from rasl.config.dispatch import ConfigError
from rasl.engine.graph import ExecutionPlan, GraphBuilder
from rasl.engine.registry import ensure_nodes_loaded, get_node_class


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


def _extract_config_dict(
    directive: Directive,
    exclude: set[str] | None = None,
    line_map: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Extract config dict from directive block.

    Converts directive tree to flat dict suitable for Pydantic validation.
    Handles nested blocks, repeated directives, and type coercion.

    Args:
        directive: Directive to extract config from.
        exclude: Keywords to skip (e.g., "connect").
        line_map: Optional dict to populate with key -> line number mapping.

    Returns:
        Dict suitable for Pydantic model_validate().
    """
    exclude = exclude or set()
    result: dict[str, Any] = {}

    def _accumulate(key: str, value: Any, line: int) -> None:
        """Add value to result, accumulating repeated keys."""
        if key not in result:
            result[key] = value
            if line_map is not None:
                line_map[key] = line
        else:
            existing = result[key]
            if not isinstance(existing, list):
                result[key] = [existing, value]
            elif existing and isinstance(existing[0], list):
                existing.append(value)
            else:
                result[key] = [existing, value]
            if line_map is not None:
                line_map[key] = line

    def _accumulate_block(key: str, value: Any, line: int) -> None:
        """Add nested block value to result, preserving repeats."""
        if key not in result:
            result[key] = value
            if line_map is not None:
                line_map[key] = line
            return

        existing = result[key]
        if not isinstance(existing, list):
            result[key] = [existing, value]
        else:
            result[key].append(value)
        if line_map is not None:
            line_map[key] = line

    for child in directive.block:
        if child.keyword in exclude:
            continue

        if child.block:
            # Nested block
            child_dict = _extract_config_dict(child)
            if child.args:
                arg_values = [_coerce_value(a) for a in child.args]
                child_dict = dict(child_dict)
                if len(arg_values) == 1:
                    child_dict.setdefault("id", arg_values[0])
                else:
                    child_dict.setdefault("_args", arg_values)
            if child.keyword == "segment":
                result.setdefault("segments", []).append(child_dict)
            elif child.keyword == "defaults":
                result["defaults"] = child_dict
            elif child.keyword == "ports":
                # Special handling for ports block - extract as list of names
                result["ports"] = [d.keyword for d in child.block]
            else:
                _accumulate_block(child.keyword, child_dict, child.line)
        elif len(child.args) == 0:
            # Flag directive
            result[child.keyword] = True
            if line_map is not None:
                line_map[child.keyword] = child.line
        elif len(child.args) == 1:
            _accumulate(child.keyword, _coerce_value(child.args[0]), child.line)
        else:
            # Multiple args -> list
            _accumulate(child.keyword, [_coerce_value(a) for a in child.args], child.line)

    return result


def _parse_metadata(raw: dict[str, Any]) -> dict[str, str]:
    """Parse metadata from raw config dict."""
    metadata_value = raw.pop("metadata", None)
    if metadata_value is None:
        return {}

    metadata: dict[str, str] = {}
    items = [metadata_value] if isinstance(metadata_value, str) else metadata_value
    for item in items:
        item_str = str(item)
        if "=" in item_str:
            key, value = item_str.split("=", 1)
            metadata[key] = value
    return metadata


def _build_node(
    node_type: str,
    node_id: str,
    directive: Directive,
    extra_args: dict[str, str] | None = None,
) -> Any:
    """Build a node instance from directive.

    Args:
        node_type: Node type name.
        node_id: Unique node identifier.
        directive: Directive containing node config.
        extra_args: Additional config from positional args.

    Returns:
        Instantiated node.

    Raises:
        ConfigError: If node type unknown or config invalid.
    """
    node_class = get_node_class(node_type)
    if node_class is None:
        raise ConfigError(f"Unknown node type '{node_type}'", line=directive.line)

    config_class = getattr(node_class, "Config", None)
    if config_class is None:
        raise ConfigError(
            f"Node type '{node_type}' does not define a Config class",
            line=directive.line,
        )

    # Extract config, excluding connect directives
    # Track line numbers for each key for better error reporting
    line_map: dict[str, int] = {}
    raw_config = _extract_config_dict(directive, exclude={"connect", "edge"}, line_map=line_map)
    raw_config["id"] = node_id

    # Merge extra args
    if extra_args:
        raw_config.update(extra_args)

    # Handle metadata
    if "metadata" in raw_config:
        raw_config["metadata"] = _parse_metadata(raw_config)

    # Remove type directive if present
    raw_config.pop("type", None)

    # Validate with Pydantic
    try:
        validated_config = config_class.model_validate(raw_config)
    except ValidationError as e:
        # Find the line number for the first error key
        error_line = directive.line
        for err in e.errors():
            if err['loc']:
                key = str(err['loc'][0])
                if key in line_map:
                    error_line = line_map[key]
                    break
        
        errors = "; ".join(
            f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}"
            for err in e.errors()
        )
        raise ConfigError(f"Invalid config for node '{node_id}': {errors}", line=error_line)

    return node_class(validated_config)


def parse_config(config_text: str) -> ExecutionPlan:
    """Parse config text and build an ExecutionPlan.

    Args:
        config_text: Configuration in crossplane/nginx syntax.

    Returns:
        Compiled ExecutionPlan ready for Runtime.

    Raises:
        ConfigError: If parsing fails or config is invalid.
    """
    ensure_nodes_loaded()

    # Parse to Directive tree
    root = Directive.from_string(config_text)

    # Find graph block
    graph_directive = root.find_one("graph")
    if not graph_directive:
        raise ConfigError("No 'graph' block found in configuration")

    builder = GraphBuilder()
    node_directives: dict[str, Directive] = {}  # Track directives for connect parsing

    # First pass: build all nodes
    for directive in graph_directive.block:
        if directive.keyword != "node":
            continue

        args = directive.args
        if not args:
            raise ConfigError("Node directive requires a name", line=directive.line)

        # Parse node syntax variants
        node_type = args[0]
        
        # Special handling for literal nodes:
        # node literal <name> <kind>:<subtype> <literal_value...>;
        if node_type in ("literal", "Literal", "LiteralNode"):
            if len(args) < 4:
                raise ConfigError(
                    "literal node requires: node literal <name> <kind:subtype> <value>;",
                    line=directive.line,
                )
            node_id = args[1]
            type_spec = args[2]
            # Rejoin remaining args as the literal value string
            literal_value = " ".join(args[3:])
            
            # Parse type_spec (e.g., "color:hsl" -> kind="color", subtype="hsl")
            if ":" in type_spec:
                payload_kind, payload_subtype = type_spec.split(":", 1)
            else:
                payload_kind = type_spec
                payload_subtype = None
            
            extra_args = {
                "payload_kind": payload_kind,
                "payload_subtype": payload_subtype,
                "literal_value": literal_value,
            }
        elif len(args) == 1:
            node_id = args[0]
            type_directive = directive.find_one("type")
            if not type_directive or not type_directive.args:
                raise ConfigError(f"Node '{node_id}' requires 'type' directive", line=directive.line)
            node_type = type_directive.args[0]
            extra_args = {}
        elif len(args) == 2:
            node_id = args[1]
            extra_args = {}
        elif node_type in ("cron",):
            # node cron <name> <field1> [field2 ... field5];
            # Missing trailing fields are treated as "*" by the node.
            if len(args) < 3:
                raise ConfigError(
                    "cron node requires: node cron <name> <field1> [field2 ... field5];",
                    line=directive.line,
                )
            if len(args) > 7:
                raise ConfigError(
                    f"cron node supports 1-5 fields, got {len(args) - 2}",
                    line=directive.line,
                )
            node_id = args[1]
            extra_args = {"schedule": list(args[2:])}
        elif len(args) == 3:
            node_id = args[1]
            if node_type in ("Color", "ColorNode"):
                extra_args = {"model": args[2]}
            else:
                raise ConfigError(
                    f"Node type '{node_type}' does not accept a third positional argument",
                    line=directive.line,
                )
        else:
            raise ConfigError(
                f"Node directive takes 1-3 arguments, got {len(args)}",
                line=directive.line,
            )

        node = _build_node(node_type, node_id, directive, extra_args=extra_args)
        builder.add_node(node)
        node_directives[node_id] = directive

    # Second pass: parse connect directives on each node
    for node_id, directive in node_directives.items():
        node = builder.nodes[node_id]
        # BaseNode parses connect directives and stores ConnectionDescriptors
        node.parse_connect_directives(directive)

    # Third pass: resolve connection descriptors into edges
    for node_id in node_directives:
        builder.resolve_node_connections(node_id)

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
    try:
        return parse_config(config_text)
    except ConfigError as e:
        # Enrich error with source line for display
        raise e.with_source(config_text) from None
