"""Configuration loader over knobly's rendered directive tree.

This module provides the config loader that builds a RASL graph from the
directives of a loaded config (see ``rasl.config.document``).

The loader handles:
- `graph` block: Top-level graph container
- `node` blocks: Dispatched to node classes for construction

Nodes handle their own `connect` directives via BaseNode.parse_connect_directives().
The Graph resolves connection descriptors into edges using node port info.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from rasl.config.document import (
    ConfigError,
    Directive,
    Rendered,
    arg_texts,
    children,
    config_error,
    load_document,
    parse_document,
    scalar,
)
from rasl.engine.graph import ExecutionPlan, GraphBuilder
from rasl.engine.registry import ensure_nodes_loaded, get_node_class


def _extract_config_dict(
    directive: Directive,
    exclude: set[str] | None = None,
    placed: dict[str, Directive] | None = None,
) -> dict[str, Any]:
    """Extract config dict from directive block.

    Converts directive tree to flat dict suitable for Pydantic validation.
    Handles nested blocks, repeated directives, and type coercion.

    Args:
        directive: Directive to extract config from.
        exclude: Keywords to skip (e.g., "connect").
        placed: Optional dict to populate with key -> the directive that set it
            (the last one, for a repeated key), for error reporting.

    Returns:
        Dict suitable for Pydantic model_validate().
    """
    exclude = exclude or set()
    result: dict[str, Any] = {}

    def _accumulate(key: str, value: Any, at: Directive) -> None:
        """Add value to result, accumulating repeated keys."""
        if key not in result:
            result[key] = value
            if placed is not None:
                placed[key] = at
        else:
            existing = result[key]
            if not isinstance(existing, list):
                result[key] = [existing, value]
            elif existing and isinstance(existing[0], list):
                existing.append(value)
            else:
                result[key] = [existing, value]
            if placed is not None:
                placed[key] = at

    def _accumulate_block(key: str, value: Any, at: Directive) -> None:
        """Add nested block value to result, preserving repeats."""
        if key not in result:
            result[key] = value
            if placed is not None:
                placed[key] = at
            return

        existing = result[key]
        if not isinstance(existing, list):
            result[key] = [existing, value]
        else:
            result[key].append(value)
        if placed is not None:
            placed[key] = at

    for child in children(directive):
        keyword = child.name
        if keyword in exclude:
            continue
        values = [scalar(value) for value in child.values]

        if child.block:
            # Nested block
            child_dict = _extract_config_dict(child)
            if values:
                arg_values = values
                child_dict = dict(child_dict)
                if len(arg_values) == 1:
                    child_dict.setdefault("id", arg_values[0])
                else:
                    child_dict.setdefault("_args", arg_values)
            if keyword == "segment":
                result.setdefault("segments", []).append(child_dict)
            elif keyword == "defaults":
                result["defaults"] = child_dict
            elif keyword == "ports":
                # Special handling for ports block - extract as list of names
                result["ports"] = [d.name for d in child.block]
            else:
                _accumulate_block(keyword, child_dict, child)
        elif len(values) == 0:
            # Flag directive
            result[keyword] = True
            if placed is not None:
                placed[keyword] = child
        elif len(values) == 1:
            _accumulate(keyword, values[0], child)
        else:
            # Multiple args -> list
            _accumulate(keyword, values, child)

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


def _node_config(
    node_type: str,
    node_id: str,
    directive: Directive,
    tree: Rendered,
    extra_args: dict[str, Any] | None = None,
) -> tuple[Any, Any]:
    """A node's class and its validated config, from its directive.

    Args:
        node_type: Node type name.
        node_id: Unique node identifier.
        directive: Directive containing node config.
        tree: The rendered config the directive belongs to.
        extra_args: Additional config from positional args.

    Returns:
        (node class, validated Config instance).

    Raises:
        ConfigError: If node type unknown or config invalid.
    """
    node_class = get_node_class(node_type)
    if node_class is None:
        raise config_error(
            directive, f"Unknown node type '{node_type}'", code="rasl/unknown-node", tree=tree
        )

    config_class = getattr(node_class, "Config", None)
    if config_class is None:
        raise config_error(
            directive,
            f"Node type '{node_type}' does not define a Config class",
            code="rasl/unknown-node",
            tree=tree,
        )

    # Extract config, excluding connect directives
    # Track the directive that set each key for better error reporting
    placed: dict[str, Directive] = {}
    raw_config = _extract_config_dict(directive, exclude={"connect", "edge"}, placed=placed)
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
        # Place the error on the directive that set the first failing key
        at = directive
        for err in e.errors():
            if err['loc']:
                key = str(err['loc'][0])
                if key in placed:
                    at = placed[key]
                    break

        errors = "; ".join(
            f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}"
            for err in e.errors()
        )
        raise config_error(
            at,
            f"Invalid config for node '{node_id}': {errors}",
            code="rasl/invalid-node",
            tree=tree,
        ) from None

    return node_class, validated_config


def graph_directive(tree: Rendered) -> Directive:
    """The config's ``graph`` block.

    Raises:
        ConfigError: If there is none.
    """
    graph_directives = tree.block.directives("graph")
    if not graph_directives:
        raise config_error(
            tree, "No 'graph' block found in configuration", code="rasl/no-graph", tree=tree
        )
    return graph_directives[0]


def node_id_of(directive: Directive) -> str | None:
    """The id a ``node`` directive gives its node, or None when it has no values.

    ``node <id> { type <Type>; }`` names it first; every other form
    (``node <Type> <id> ...``) names it second.
    """
    args = arg_texts(directive)
    if not args:
        return None
    return args[0] if len(args) == 1 else args[1]


def node_spec(directive: Directive, tree: Rendered) -> tuple[str, str, dict[str, Any]]:
    """A ``node`` directive's type name, id and the config its positional values give.

    Raises:
        ConfigError: If the directive is not one of the node forms.
    """

    def node_error(at: Directive, message: str) -> ConfigError:
        return config_error(at, message, code="rasl/node-syntax", tree=tree)

    args = arg_texts(directive)
    if not args:
        raise node_error(directive, "Node directive requires a name")

    # Parse node syntax variants
    node_type = args[0]
    
    # Special handling for literal nodes:
    # node literal <name> <kind>:<subtype> <literal_value...>;
    if node_type in ("literal", "Literal", "LiteralNode"):
        if len(args) < 4:
            raise node_error(
                directive,
                "literal node requires: node literal <name> <kind:subtype> <value>;",
            )
        node_id = args[1]
        type_spec = args[2]
        # The literal value string is the canonical text of the remaining values
        # (a list as "[[1, 0, 0], [0.5, 0, 0]]", a string in double quotes)
        literal_value = " ".join(value.text for value in directive.values[3:])
        
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
        type_args = [arg_texts(d) for d in children(directive, "type")[:1]]
        if not type_args or not type_args[0]:
            raise node_error(directive, f"Node '{node_id}' requires 'type' directive")
        node_type = type_args[0][0]
        extra_args = {}
    elif len(args) == 2:
        node_id = args[1]
        extra_args = {}
    elif node_type in ("cron",):
        # node cron <name> <field1> [field2 ... field5];
        # Missing trailing fields are treated as "*" by the node.
        if len(args) < 3:
            raise node_error(
                directive,
                "cron node requires: node cron <name> <field1> [field2 ... field5];",
            )
        if len(args) > 7:
            raise node_error(
                directive, f"cron node supports 1-5 fields, got {len(args) - 2}"
            )
        node_id = args[1]
        extra_args = {"schedule": list(args[2:])}
    elif len(args) == 3:
        node_id = args[1]
        if node_type in ("Color", "ColorNode"):
            extra_args = {"model": args[2]}
        else:
            raise node_error(
                directive,
                f"Node type '{node_type}' does not accept a third positional argument",
            )
    else:
        raise node_error(
            directive, f"Node directive takes 1-3 arguments, got {len(args)}"
        )

    return node_type, node_id, extra_args


def build_plan(
    tree: Rendered,
    *,
    keep: Mapping[str, Any] | None = None,
    update: Mapping[str, Any] | None = None,
) -> tuple[ExecutionPlan, dict[str, Any]]:
    """Build an ExecutionPlan from a rendered config, reusing running nodes.

    A reload passes the node objects that go on running: the plan holds those
    same objects, with their connections read again from the config.

    Args:
        tree: The rendered config.
        keep: Running nodes, by id, whose own settings did not change. They are
            reused as they are; their config is not read.
        update: Running nodes, by id, whose settings changed and that take a new
            config in place (``update_config``). They are reused, and the new
            validated config of each is returned for the caller to apply.

    Returns:
        (plan, the new config of each node in ``update``, by id).

    Raises:
        ConfigError: If the config is invalid. Reused nodes are left as they were.
    """
    ensure_nodes_loaded()
    keep = keep or {}
    update = update or {}
    reused = {**keep, **update}
    # A reused node's connections are read again below; put them back if the build fails.
    saved = {node_id: node.get_connection_descriptors() for node_id, node in reused.items()}

    try:
        builder = GraphBuilder()
        node_directives: dict[str, Directive] = {}  # Track directives for connect parsing
        configs: dict[str, Any] = {}

        # First pass: build all nodes
        for directive in children(graph_directive(tree), "node"):
            node_type, node_id, extra_args = node_spec(directive, tree)
            if node_id in keep:
                node = keep[node_id]
            else:
                node_class, config = _node_config(
                    node_type, node_id, directive, tree, extra_args=extra_args
                )
                if node_id in update:
                    node = update[node_id]
                    configs[node_id] = config
                else:
                    node = node_class(config)
            if node_id in reused:
                node._connection_descriptors = []
            builder.add_node(node)
            node_directives[node_id] = directive

        # Second pass: parse connect directives on each node
        for node_id, directive in node_directives.items():
            node = builder.nodes[node_id]
            # BaseNode parses connect directives and stores ConnectionDescriptors
            node.parse_connect_directives(directive)

        # Third pass: resolve connection descriptors into edges
        for node_id, directive in node_directives.items():
            try:
                builder.resolve_node_connections(node_id)
            except (KeyError, ValueError, TypeError) as e:
                # The graph's own message, placed on the node whose connect it is
                message = e.args[0] if isinstance(e, KeyError) and e.args else str(e)
                raise config_error(
                    directive,
                    f"Node '{node_id}': {message}",
                    code="rasl/connect",
                    tree=tree,
                ) from e

        return builder.build(), configs
    except BaseException:
        for node_id, descriptors in saved.items():
            reused[node_id]._connection_descriptors = descriptors
        raise



def parse_config(config_text: str) -> ExecutionPlan:
    """Parse config text and build an ExecutionPlan.

    Args:
        config_text: Configuration in knobly syntax.

    Returns:
        Compiled ExecutionPlan ready for Runtime.

    Raises:
        ConfigError: If parsing fails or config is invalid.
    """
    return build_plan(parse_document(config_text))[0]


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
    return build_plan(load_document(config_path))[0]
