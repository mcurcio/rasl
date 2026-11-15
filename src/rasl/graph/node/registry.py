"""The node registry: node classes by the type names configs use.

A node class registers itself with ``@node("Name", "Alias")``. Built-in nodes
and device packages are loaded through the ``rasl.nodes`` entry points, like
any plugin, so this module names no node package.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Type, TypeVar

from rasl.signal.registry import _PAYLOAD_REGISTRY

if TYPE_CHECKING:
    from rasl.graph.node.base import BaseNode

T = TypeVar("T")

_NODE_REGISTRY: dict[str, Type["BaseNode"]] = {}
_initialized = False


class NodeRegistryError(RuntimeError):
    """Node types cannot be registered as asked: two classes claim one type name, or a
    node plugin failed to import. rasl does not start with either."""


def _same_class(a: type, b: type) -> bool:
    """The same class, or the same definition imported again (a module reload)."""
    return a is b or (a.__module__, a.__qualname__) == (b.__module__, b.__qualname__)


def _where(cls: type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


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
        NodeRegistryError: If another class already registered one of the names.

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
        for type_name in (name, *aliases):
            existing = _NODE_REGISTRY.get(type_name)
            if existing is not None and not _same_class(existing, cls):
                raise NodeRegistryError(
                    f"Node type name '{type_name}' is registered by both {_where(existing)} "
                    f"and {_where(cls)}; rename one of them"
                )
        for type_name in (name, *aliases):
            _NODE_REGISTRY[type_name] = cls  # type: ignore[assignment]
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
# Plugin Discovery
# ─────────────────────────────────────────────────────────────────────


def ensure_nodes_loaded() -> None:
    """Ensure all node plugins have been loaded via entry points.

    This function is idempotent — it only loads plugins once.
    Plugins are discovered from the "rasl.nodes" entry point group.

    Entry points should point to a module that, when imported,
    triggers @node decorator registration for its node classes.

    Raises:
        NodeRegistryError: If a plugin fails to import, or registers a type name
            another class has.
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    # Built-in nodes and device packages are entry points too (pyproject.toml),
    # so the engine names no node package
    try:
        from importlib.metadata import entry_points
    except ImportError:
        # Python < 3.10 fallback
        from importlib_metadata import entry_points  # type: ignore[import-not-found,no-redef]

    eps = entry_points(group="rasl.nodes")
    for ep in eps:
        try:
            ep.load()  # Importing triggers @node registration
        except NodeRegistryError:
            raise
        except Exception as e:
            raise NodeRegistryError(
                f"Node plugin '{ep.name}' ({ep.value}) failed to load: {type(e).__name__}: {e}"
            ) from e


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
