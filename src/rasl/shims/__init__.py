"""Runtime shims used to patch third-party libraries."""

from .sacn_universe import allow_sacn_universe_zero

__all__ = ["allow_sacn_universe_zero"]
