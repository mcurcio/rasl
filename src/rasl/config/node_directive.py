"""A ``node`` directive: its type, its id, and the Config it validates to.

A node declares its settings as a nested pydantic ``Config`` class; each
directive in the node's block is one field of it, by name.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from rasl.config.document import (
    ConfigError,
    Directive,
    Rendered,
    arg_texts,
    children,
    config_error,
    scalar,
)
from rasl.graph.node import get_node_class


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
) -> tuple[Any, Any]:
    """A node's class and its validated config, from its directive.

    Args:
        node_type: Node type name.
        node_id: Unique node identifier.
        directive: Directive containing node config.
        tree: The rendered config the directive belongs to.

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

    # Values on the node's own line, after its type and name, are the node type's to read
    positional = getattr(config_class, "from_positional", None)
    words = arg_texts(directive)[2:]
    if positional is not None:
        try:
            raw_config.update(positional(words, [value.text for value in directive.values[2:]]))
        except ValueError as e:
            raise config_error(directive, str(e), code="rasl/node-syntax", tree=tree) from None
    elif words:
        raise config_error(
            directive,
            f"Node type '{node_type}' takes no values after its name",
            code="rasl/node-syntax",
            tree=tree,
        )

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


def node_id_of(directive: Directive) -> str | None:
    """The id a ``node`` directive gives its node, or None when it has no values.

    ``node <id> { type <Type>; }`` names it first; every other form
    (``node <Type> <id> ...``) names it second.
    """
    args = arg_texts(directive)
    if not args:
        return None
    return args[0] if len(args) == 1 else args[1]


def node_spec(directive: Directive, tree: Rendered) -> tuple[str, str]:
    """A ``node`` directive's type name and id.

    Two forms: ``node <Type> <id> [values...] { ... }`` and
    ``node <id> { type <Type>; ... }``. Values after the id belong to the node
    type (``BaseNodeConfig.from_positional``).

    Raises:
        ConfigError: If the directive is neither form.
    """

    def node_error(at: Directive, message: str) -> ConfigError:
        return config_error(at, message, code="rasl/node-syntax", tree=tree)

    args = arg_texts(directive)
    if not args:
        raise node_error(directive, "Node directive requires a name")

    if len(args) == 1:
        node_id = args[0]
        type_args = [arg_texts(d) for d in children(directive, "type")[:1]]
        if not type_args or not type_args[0]:
            raise node_error(directive, f"Node '{node_id}' requires 'type' directive")
        return type_args[0][0], node_id
    return args[0], args[1]
