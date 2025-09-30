"""
Sink node implementations.

Sinks consume data and output it to various destinations like
consoles, files, network protocols, or hardware devices.
"""

from .console import ConsoleSink, LoggingSink

__all__ = ["ConsoleSink", "LoggingSink"]
