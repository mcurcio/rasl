"""The config's top-level settings blocks, beside ``graph``: ``ui`` and ``runtime``.

```nginx
ui {
    host 0.0.0.0;     # where the web UI and API listen (default 127.0.0.1)
    port 8080;        # 1 to 65535 (default 8080)
}
runtime {
    max_consecutive_errors 10;   # disable a node after this many failed pulls in a row; 0 = never
    debug_frames false;          # true: fail a node that keeps or passes on a frame past its lifetime (slower)
}
```

Each block is optional, and only its first occurrence counts. A bad value is a
``ConfigError`` placed on its line. Changing either block in a running config takes
effect at the next restart (a reload reports it as a change that needs one).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from rasl.config.document import Directive, Rendered, arg_texts, children, config_error

DEFAULT_UI_HOST: Final = "127.0.0.1"
DEFAULT_UI_PORT: Final = 8080
DEFAULT_MAX_CONSECUTIVE_ERRORS: Final = 10


@dataclass(frozen=True)
class UiSettings:
    """Where the web UI and API listen, from the ``ui`` block.

    Attributes:
        enabled: True when the config has a ``ui`` block (the server then starts even
            without ``--api-port``).
        host: The address to listen on.
        port: The TCP port, 1 to 65535.
    """

    enabled: bool = False
    host: str = DEFAULT_UI_HOST
    port: int = DEFAULT_UI_PORT


@dataclass(frozen=True)
class RuntimeSettings:
    """How the runtime treats failing nodes, from the ``runtime`` block.

    Attributes:
        max_consecutive_errors: A node whose pull fails this many times in a row is
            disabled (no longer pulled, and reported by /health) until a config reload
            changes it or rasl restarts. 0 means never. A node's own
            ``max_consecutive_errors`` setting overrides this.
        debug_frames: Check frame lifetimes (``Runtime(debug_frames=True)``): a node
            that keeps or passes on a frame after its port recycled the buffer behind it
            fails, naming the port. Slower; for debugging nodes.
    """

    max_consecutive_errors: int = DEFAULT_MAX_CONSECUTIVE_ERRORS
    debug_frames: bool = False


def _single_value(child: Directive, tree: Rendered) -> str:
    """The one value of a setting directive, or a located error."""
    values = arg_texts(child)
    if len(values) != 1 or child.block is not None:
        raise config_error(
            child, f"'{child.name}' takes exactly one value", code="rasl/settings", tree=tree
        )
    return values[0]


def _integer(child: Directive, tree: Rendered, low: int, high: int | None) -> int:
    """The one value of a setting directive as an integer in ``[low, high]``."""
    text = _single_value(child, tree)
    try:
        value = int(text)
    except ValueError:
        value = None
    if value is None or value < low or (high is not None and value > high):
        bound = f"from {low} to {high}" if high is not None else f"{low} or more"
        raise config_error(
            child,
            f"'{child.name}' must be a whole number {bound}, got {text!r}",
            code="rasl/settings",
            tree=tree,
        )
    return value


def _boolean(child: Directive, tree: Rendered) -> bool:
    """The one value of a setting directive as ``true`` or ``false``."""
    text = _single_value(child, tree)
    if text not in ("true", "false"):
        raise config_error(
            child, f"'{child.name}' must be true or false, got {text!r}", code="rasl/settings", tree=tree
        )
    return text == "true"


def ui_settings(tree: Rendered) -> UiSettings:
    """Read the ``ui`` block.

    Settings other than ``host`` and ``port`` are ignored.

    Raises:
        ConfigError: If ``host`` or ``port`` does not have exactly one valid value.
    """
    blocks = tree.block.directives("ui")
    if not blocks:
        return UiSettings()
    host, port = DEFAULT_UI_HOST, DEFAULT_UI_PORT
    for child in children(blocks[0]):
        if child.name == "host":
            host = _single_value(child, tree)
        elif child.name == "port":
            port = _integer(child, tree, 1, 65535)
    return UiSettings(enabled=True, host=host, port=port)


def runtime_settings(tree: Rendered) -> RuntimeSettings:
    """Read the ``runtime`` block.

    Raises:
        ConfigError: If a setting is unknown or its value is not valid.
    """
    blocks = tree.block.directives("runtime")
    if not blocks:
        return RuntimeSettings()
    limit = DEFAULT_MAX_CONSECUTIVE_ERRORS
    debug_frames = False
    for child in children(blocks[0]):
        if child.name == "max_consecutive_errors":
            limit = _integer(child, tree, 0, None)
        elif child.name == "debug_frames":
            debug_frames = _boolean(child, tree)
        else:
            raise config_error(
                child,
                f"Unknown runtime setting '{child.name}' (known: max_consecutive_errors, debug_frames)",
                code="rasl/settings",
                tree=tree,
            )
    return RuntimeSettings(max_consecutive_errors=limit, debug_frames=debug_frames)
