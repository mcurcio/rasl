"""The payload registry: payload types by name.

A payload class registers itself with ``@payload("name")``; ports and config
refer to payload types by those names.
"""

from __future__ import annotations

from typing import Type, TypeVar

T = TypeVar("T")

_PAYLOAD_REGISTRY: dict[str, Type] = {}


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
