"""
Source node implementations.

Sources generate data without inputs, providing the starting points
for animation graphs.
"""

from .sine import SineSource, MultiSineSource

__all__ = ["SineSource", "MultiSineSource"]
