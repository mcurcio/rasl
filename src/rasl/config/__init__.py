"""The config language: reading a config file and building a plan from it.

Config files are written in knobly, rasl's config language
(https://github.com/mcurcio/knobly).

- ``rasl.config.document``: the knobly document, directives and values
- ``rasl.config.node_directive``: a ``node`` directive as a class and its Config
- ``rasl.config.connect``: ``connect`` directives, and resolving them to edges
- ``rasl.config.build``: a rendered config as an ExecutionPlan
- ``rasl.config.reload``: a config session, and working out a plan update
- ``rasl.config.watch``: reloading when the files change

Example:
    >>> from rasl.config import load_config
    >>>
    >>> plan = load_config("config.conf")
    >>> # plan is an ExecutionPlan ready for a Runtime
"""

from rasl.config.build import build_plan, load_config, parse_config
from rasl.config.connect import ConnectionDescriptor, PortRef, parse_connect_directive, parse_port_ref
from rasl.config.document import ConfigError, Directive, load_document, parse_document
from rasl.config.reload import ConfigSession
from rasl.config.watch import watch_config

__all__ = [
    "ConfigError",
    "ConfigSession",
    "ConnectionDescriptor",
    "Directive",
    "PortRef",
    "build_plan",
    "load_config",
    "load_document",
    "parse_config",
    "parse_connect_directive",
    "parse_document",
    "parse_port_ref",
    "watch_config",
]
