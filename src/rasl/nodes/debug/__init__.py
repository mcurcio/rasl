"""Debug and testing nodes.

This package contains nodes useful for testing and debugging:
    - ConsoleSinkNode: Log frames to console/logger
    - SineSourceNode: Generate virtual sine wave test data
"""

from .console_sink import ConsoleSinkNode
from .sine_source import SineSourceNode

__all__ = [
    "ConsoleSinkNode",
    "SineSourceNode",
]
