"""Color conversion utilities for RASL.

DEPRECATED: This module is deprecated. Import from rasl.nodes.color instead.

This module re-exports from rasl.nodes.color for backward compatibility.
"""

# Re-export from new location for backward compatibility
from rasl.nodes.color.convert import DEFAULT_MODEL, MODELS, convert

__all__ = ["DEFAULT_MODEL", "MODELS", "convert"]
