"""RASL Config - Configuration parsing and graph construction.

This package provides utilities for loading RASL graph configurations
from crossplane-syntax config files.

Example:
    >>> from rasl.config import load_config
    >>>
    >>> plan = load_config("config.conf")
    >>> # plan is an ExecutionPlan ready for Runtime

New config dispatch system:
    >>> from rasl.config import Directive, ConfigDispatch, config
    >>>
    >>> root = Directive.from_file("config.conf")
    >>> # Use ConfigDispatch to route directives to handlers
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
from .directive import Directive
from .dispatch import ConfigDispatch, ConfigError, config
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
    "parse_connect",
    "parse_connect_batch",
    "ParsedConnect",
    "PortChannelRegistry",
    "ResolvedSlice",
    "SinkNodeConfig",
    "SourceNodeConfig",
    "TransformNodeConfig",
]
