"""A ``node`` directive: its type, its id, and the Config it validates to.

A node declares its settings as a nested pydantic ``Config`` class; each
directive in the node's block is one field of it, by name.
"""

from __future__ import annotations

import types
import typing
from typing import Any

from pydantic import BaseModel, ValidationError

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


def _metadata(directive: Directive, tree: Rendered) -> dict[str, str] | None:
    """A node's ``metadata``, from its string and block forms, or None if it has none.

    ``metadata "room=den" "zone=2";`` gives each ``key=value`` value (a value with no
    ``=`` is ignored). ``metadata { room den; zone 2; }`` gives each line's one value.
    Several ``metadata`` directives, of either form, merge.

    Raises:
        ConfigError: On the line at fault, for a block line with no value or several,
            a nested block, a value on a block's own line, or a key given twice.
    """
    found = children(directive, "metadata")
    if not found:
        return None
    metadata: dict[str, str] = {}

    def put(key: str, value: str, at: Directive) -> None:
        if key in metadata:
            raise config_error(
                at, f"metadata key '{key}' is given twice", code="rasl/metadata", tree=tree
            )
        metadata[key] = value

    for item in found:
        if item.block is None:
            for text in arg_texts(item):
                if "=" in text:
                    key, value = text.split("=", 1)
                    put(key, value, item)
            continue
        if item.values:
            raise config_error(
                item,
                "a metadata block takes no values on its own line; put each entry inside it",
                code="rasl/metadata",
                tree=tree,
            )
        for entry in children(item):
            values = arg_texts(entry)
            if entry.block is not None or len(values) != 1:
                raise config_error(
                    entry,
                    f"metadata entry '{entry.name}' takes exactly one value, like `{entry.name} value;`",
                    code="rasl/metadata",
                    tree=tree,
                )
            put(entry.name, values[0], entry)
    return metadata


def _is_list_of_blocks(annotation: Any) -> bool:
    """Whether a field's type is a list of blocks (models or maps), also inside ``X | None``.

    Lists of plain values (``list[str]``) are left to the field's own validators: a
    block such as Compose's ``ports { h; s; l; }`` is their whole value, not one item.
    """
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        return any(_is_list_of_blocks(arg) for arg in typing.get_args(annotation))
    if origin is not list:
        return False
    item = (typing.get_args(annotation) or (Any,))[0]
    item_origin = typing.get_origin(item) or item
    return item_origin is dict or (isinstance(item, type) and issubclass(item, BaseModel))


def _wrap_single_blocks(config_class: Any, raw_config: dict[str, Any]) -> None:
    """Make a lone nested block a one-item list where the field takes a list.

    Repeated blocks (``universe { ... } universe { ... }``) already arrive as a
    list; a single one arrives as a map. A list-of-blocks field gets a list either way.
    """
    for name, field in getattr(config_class, "model_fields", {}).items():
        if not _is_list_of_blocks(field.annotation):
            continue
        for key in (field.alias, name):
            if key and isinstance(raw_config.get(key), dict):
                raw_config[key] = [raw_config[key]]


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

    # Metadata is read from the directives themselves, which keep each line's place
    metadata = _metadata(directive, tree)
    if metadata is not None:
        raw_config["metadata"] = metadata

    # Remove type directive if present
    raw_config.pop("type", None)

    _wrap_single_blocks(config_class, raw_config)

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
