"""RASL Config - Configuration parsing and graph construction.

This package provides utilities for loading RASL graph configurations
from crossplane-syntax config files.

Example:
    >>> from rasl.config import load_config
    >>>
    >>> plan = load_config("config.conf")
    >>> # plan is an ExecutionPlan ready for Runtime
"""

from .loader import load_config, parse_config

__all__ = ["load_config", "parse_config"]
