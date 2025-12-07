"""RASL Config - Configuration parsing and graph construction.

This package provides utilities for loading RASL graph configurations
from crossplane-syntax config files.

Example:
    >>> from rasl.config import load_config
    >>>
    >>> plan = load_config("config.conf")
    >>> # plan is an ExecutionPlan ready for Runtime
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
from .loader import ConfigError, load_config, parse_config
from .models import (
    BaseNodeConfig,
    SinkNodeConfig,
    SourceNodeConfig,
    TransformNodeConfig,
)

__all__ = [
    "BaseNodeConfig",
    "ChannelMapping",
    "ChannelOverlapError",
    "ConfigError",
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
