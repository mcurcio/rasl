"""Node and payload type registries for plugin architecture.

This module provides decorators for registering node classes and payload
types, enabling a plugin-based architecture where the core engine has no
knowledge of specific implementations.

Example:
    >>> from rasl.engine.registry import node, payload
    >>>
    >>> @payload("array")
    ... class ArrayPayload:
    ...     pass
    >>>
    >>> @node("MySourceNode", "MySource")
    ... class MySourceNode(BaseNode):
    ...     class Config(SourceNodeConfig):
    ...         param: float = 1.0
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Type, TypeVar

if TYPE_CHECKING:
    from .base_node import BaseNode

T = TypeVar("T")

_NODE_REGISTRY: dict[str, Type["BaseNode"]] = {}
_PAYLOAD_REGISTRY: dict[str, Type] = {}
_initialized = False


# ─────────────────────────────────────────────────────────────────────
# Node Registration
# ─────────────────────────────────────────────────────────────────────


def node(name: str, *aliases: str):
    """Class decorator to register a node type.

    The decorated class must define a nested `Config` class that inherits
    from one of the base config models (SourceNodeConfig, TransformNodeConfig,
    or SinkNodeConfig).

    Args:
        name: Primary type name used in config files.
        *aliases: Optional short names (e.g., "SineSource" for "SineSourceNode").

    Returns:
        Decorator function that registers the class and returns it unchanged.

    Raises:
        TypeError: If the class does not define a nested Config class.

    Example:
        >>> @node("SineSourceNode", "SineSource")
        ... class SineSourceNode(BaseNode):
        ...     class Config(SourceNodeConfig):
        ...         frequency_hz: float = 1.0
    """

    def decorator(cls: Type[T]) -> Type[T]:
        if not hasattr(cls, "Config"):
            raise TypeError(
                f"Node class {cls.__name__} must define a nested Config class"
            )
        _NODE_REGISTRY[name] = cls  # type: ignore[assignment]
        for alias in aliases:
            _NODE_REGISTRY[alias] = cls  # type: ignore[assignment]
        return cls

    return decorator


def get_node_class(name: str) -> Type["BaseNode"] | None:
    """Look up a registered node class by name.

    Args:
        name: Node type name or alias.

    Returns:
        The node class, or None if not found.
    """
    return _NODE_REGISTRY.get(name)


def list_node_types() -> list[str]:
    """List all registered node type names (including aliases).

    Returns:
        Sorted list of all registered names.
    """
    return sorted(_NODE_REGISTRY.keys())


def get_node_registry() -> dict[str, Type["BaseNode"]]:
    """Get a copy of the full node registry.

    Returns:
        Dict mapping names to node classes.
    """
    return dict(_NODE_REGISTRY)


# ─────────────────────────────────────────────────────────────────────
# Payload Registration
# ─────────────────────────────────────────────────────────────────────


def payload(name: str):
    """Class decorator to register a payload type.

    Payload types are referenced by name in PortSpec.accepts, allowing
    the port system to be decoupled from specific payload implementations.

    Args:
        name: Payload type name (e.g., "array", "event", "color").

    Returns:
        Decorator function that registers the class and returns it unchanged.

    Example:
        >>> @payload("array")
        ... class ArrayPayload(np.ndarray):
        ...     pass
    """

    def decorator(cls: Type[T]) -> Type[T]:
        _PAYLOAD_REGISTRY[name] = cls
        return cls

    return decorator


def get_payload_type(name: str) -> Type | None:
    """Look up a registered payload type by name.

    Args:
        name: Payload type name.

    Returns:
        The payload class, or None if not found.
    """
    return _PAYLOAD_REGISTRY.get(name)


def list_payload_types() -> list[str]:
    """List all registered payload type names.

    Returns:
        Sorted list of all registered payload names.
    """
    return sorted(_PAYLOAD_REGISTRY.keys())


def get_payload_registry() -> dict[str, Type]:
    """Get a copy of the full payload registry.

    Returns:
        Dict mapping names to payload classes.
    """
    return dict(_PAYLOAD_REGISTRY)


# ─────────────────────────────────────────────────────────────────────
# Plugin Discovery
# ─────────────────────────────────────────────────────────────────────


def ensure_nodes_loaded() -> None:
    """Ensure all node plugins have been loaded via entry points.

    This function is idempotent — it only loads plugins once.
    Plugins are discovered from the "rasl.nodes" entry point group.

    Entry points should point to a module that, when imported,
    triggers @node decorator registration for its node classes.
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    try:
        from importlib.metadata import entry_points
    except ImportError:
        # Python < 3.10 fallback
        from importlib_metadata import entry_points  # type: ignore[import-not-found,no-redef]

    eps = entry_points(group="rasl.nodes")
    for ep in eps:
        try:
            ep.load()  # Importing triggers @node registration
        except Exception as e:
            warnings.warn(f"Failed to load node plugin {ep.name}: {e}")


def reset_registries() -> None:
    """Reset all registries to empty state. For testing only."""
    global _initialized
    _NODE_REGISTRY.clear()
    _PAYLOAD_REGISTRY.clear()
    _initialized = False


# ─────────────────────────────────────────────────────────────────────
# Schema Export
# ─────────────────────────────────────────────────────────────────────


def export_node_schemas() -> dict[str, dict]:
    """Export JSON schemas for all registered node types.

    This is useful for documentation, tooling, and UI generation.
    Only primary names are included (aliases are skipped).

    Returns:
        Dict mapping primary node type names to their JSON Schema.
    """
    ensure_nodes_loaded()
    schemas: dict[str, dict] = {}
    seen_classes: set[Type] = set()

    for name, cls in _NODE_REGISTRY.items():
        if cls in seen_classes:
            continue  # Skip aliases
        seen_classes.add(cls)

        config_cls = getattr(cls, "Config", None)
        if config_cls and hasattr(config_cls, "model_json_schema"):
            schemas[name] = config_cls.model_json_schema()

    return schemas
