"""Monkey patch support for universe 0 in the sacn library.

The sacn library by default rejects universe 0, but some LED controllers
(particularly WLED) use universe 0 as a valid universe number. This module
patches the sacn library to allow universe 0.

Usage:
    from rasl.packages.sacn.shims import allow_sacn_universe_zero
    allow_sacn_universe_zero()  # Call once at startup
"""

from __future__ import annotations

from typing import Callable, Optional

import sacn.sender
from sacn.messages import data_packet

_patched = False


def allow_sacn_universe_zero() -> None:
    """Allow sacn.sACNsender to use universe 0.
    
    This function patches the sacn library to accept universe 0 as a valid
    universe number. It is safe to call multiple times; subsequent calls
    are no-ops.
    """
    global _patched
    if _patched:
        return

    _patch_sender_check()
    _patch_data_packet_universe()
    _patched = True


def _patch_sender_check() -> None:
    """Patch sacn.sender.check_universe to allow universe 0."""
    original = getattr(sacn.sender, "check_universe", None)
    if original is None:
        return

    def _patched_check(universe: int) -> None:
        if universe == 0:
            return
        return original(universe)  # type: ignore[misc]

    sacn.sender.check_universe = _patched_check  # type: ignore[assignment]


def _patch_data_packet_universe() -> None:
    """Patch DataPacket.universe setter to allow universe 0."""
    prop = getattr(data_packet.DataPacket, "universe", None)
    if not isinstance(prop, property) or prop.fset is None:
        return

    original_setter: Callable[[data_packet.DataPacket, int], None] = prop.fset

    def _patched_setter(self: data_packet.DataPacket, universe: int) -> None:
        if universe == 0:
            self._universe = 0
            return
        original_setter(self, universe)

    data_packet.DataPacket.universe = property(  # type: ignore[assignment]
        prop.fget,
        _patched_setter,
        prop.fdel,
        prop.__doc__,
    )
