"""Debug and testing nodes.

This package contains nodes useful for testing and debugging:
    - ConsoleSinkNode: Log frames to console/logger
    - SineSourceNode: Generate virtual sine wave test data
"""

from rasl.nodes.debug.console_sink import ConsoleSinkNode
from rasl.nodes.debug.sine_source import SineSourceNode

__all__ = [
    "ConsoleSinkNode",
    "SineSourceNode",
]
