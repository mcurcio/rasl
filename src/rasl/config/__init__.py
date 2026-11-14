"""RASL Config - Configuration parsing and graph construction.

This package provides utilities for loading RASL graph configurations
from config files written in knobly, rasl's config language
(https://github.com/mcurcio/knobly).

Example:
    >>> from rasl.config import load_config
    >>>
    >>> plan = load_config("config.conf")
    >>> # plan is an ExecutionPlan ready for Runtime

New config dispatch system:
    >>> from rasl.config import ConfigDispatch, config, load_document
    >>>
    >>> tree = load_document("config.conf")
    >>> # tree.block holds the top-level directives;
    >>> # use ConfigDispatch to route directives to handlers
"""

from .channel_mapping import (
    ChannelMapping,
    ChannelOverlapError,
    PortChannelRegistry,
)
from .connect_parser import (
    ConnectParseError,
    ParsedConnect,
    ResolvedSlice,
    parse_connect,
    parse_connect_batch,
)
from .connection import (
    ConnectionDescriptor,
    ConnectionSpec,
    PortRef,
    parse_connect_directive,
    parse_port_ref,
)
from .dispatch import ConfigDispatch, config
from .document import ConfigError, Directive, load_document, parse_document
from .loader import load_config, parse_config
# Re-export node config models from new location for backward compatibility
from rasl.nodes.models import (
    BaseNodeConfig,
    SinkNodeConfig,
    SourceNodeConfig,
    TransformNodeConfig,
)

__all__ = [
    # New config dispatch system
    "config",
    "ConfigDispatch",
    "ConfigError",
    "ConnectionDescriptor",
    "ConnectionSpec",
    "Directive",
    "load_document",
    "parse_connect_directive",
    "parse_port_ref",
    "PortRef",
    # Legacy config system
    "BaseNodeConfig",
    "ChannelMapping",
    "ChannelOverlapError",
    "ConnectParseError",
    "load_config",
    "parse_config",
    "parse_document",
    "parse_connect",
    "parse_connect_batch",
    "ParsedConnect",
    "PortChannelRegistry",
    "ResolvedSlice",
    "SinkNodeConfig",
    "SourceNodeConfig",
    "TransformNodeConfig",
]
