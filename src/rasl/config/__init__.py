"""RASL Config - Configuration parsing and graph construction.

This package provides utilities for loading RASL graph configurations
from config files written in knobly, rasl's config language
(https://github.com/mcurcio/knobly).

Example:
    >>> from rasl.config import load_config
    >>>
    >>> plan = load_config("config.conf")
    >>> # plan is an ExecutionPlan ready for Runtime
"""

from rasl.config.connect_parser import (
    ConnectParseError,
    ParsedConnect,
    parse_connect,
    parse_connect_batch,
)
from rasl.config.connection import (
    ConnectionDescriptor,
    ConnectionSpec,
    PortRef,
    parse_connect_directive,
    parse_port_ref,
)
from rasl.config.document import ConfigError, Directive, load_document, parse_document
from rasl.config.loader import load_config, parse_config

__all__ = [
    "ConfigError",
    "ConnectionDescriptor",
    "ConnectionSpec",
    "Directive",
    "load_document",
    "parse_connect_directive",
    "parse_port_ref",
    "PortRef",
    "ConnectParseError",
    "load_config",
    "parse_config",
    "parse_document",
    "parse_connect",
    "parse_connect_batch",
    "ParsedConnect",
]
