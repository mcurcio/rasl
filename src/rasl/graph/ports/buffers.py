"""The two buffers a port alternates between, and when they swap.

A port's producer (a node for an output, the compiled routing for an input) fills the back
buffer and marks it complete (``commit``); the framework makes it visible (``publish``),
which is the only point where the buffers swap. Pulled outputs and inputs are published at
the end of the pull that produced them, pushed outputs at the start of each tick (owner,
2026-11-21, rasl-pd0.12). So a published frame stays unchanged until its producer's first
fill after its next publish.
"""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING, Callable, Dict, Optional, Tuple

import numpy as np

from rasl.signal import FramePayload

if TYPE_CHECKING:
    from rasl.signal import Frame


class FrameLifetimeError(RuntimeError):
    """A frame was used outside its lifetime (raised only by ``DebugFrameBuffers``)."""


class FrameBuffers:
    """Two float32 arrays a port fills and publishes in turn.

    Each array is flat and only grows; ``acquire`` hands out a C-contiguous
    ``(count, components)`` view of the back one, so alternating widths never reallocate.
    """

    __slots__ = ("_front", "_back", "_pending", "_ready", "_swap", "_shape", "_published_shape", "_previous_ok")

    def __init__(self) -> None:
        """Start with no arrays and nothing pending."""
        self._front: Optional[np.ndarray] = None
        self._back: Optional[np.ndarray] = None
        self._pending: Optional["Frame"] = None
        self._ready = False
        self._swap = False
        self._shape: Tuple[int, int] = (0, 0)
        self._published_shape: Tuple[int, int] = (0, 0)
        self._previous_ok = False

    def _grow(self, current: Optional[np.ndarray], size: int) -> np.ndarray:
        """``current`` if it holds ``size`` values, else a new flat array of ``size`` zeros."""
        if current is not None and current.shape[0] >= size:
            return current
        return FramePayload.ensure_buffer(None, count=size, components=1).reshape(-1)

    def acquire(self, count: int, components: int) -> np.ndarray:
        """The back array as a writable ``(count, components)`` float32 view.

        Its contents are undefined: the frame from two publishes ago, or zeros when the
        array grew. Clears *ready*: a buffer being refilled is not complete.
        """
        size = count * components
        back = self._back
        if back is None or back.shape[0] < size:
            back = self._back = self._grow(back, size)
        self._shape = (count, components)
        self._ready = False
        return back[:size].reshape(count, components)

    def commit(self, frame: "Frame") -> None:
        """Mark the back array complete, with ``frame`` (a view of it) to publish.

        A frame that does not view the back array (a copy, or a commit with no
        ``acquire``) is published like a written one, without a swap, so the buffers never
        swap over data that was not committed.
        """
        back = self._back
        data = getattr(frame.payload, "data", None)
        self._pending = frame
        self._ready = True
        self._swap = back is not None and isinstance(data, np.ndarray) and np.may_share_memory(data, back)

    def write(self, frame: "Frame") -> None:
        """Set ``frame``, which owns its data, to publish; no array is involved."""
        self._pending = frame
        self._ready = True
        self._swap = False

    def clear(self) -> None:
        """Drop what is pending; the next publish publishes nothing."""
        self._pending = None
        self._ready = False

    def publish(self) -> Optional["Frame"]:
        """Make the pending frame the published one and return it; None if nothing is ready.

        Swaps the arrays only for a committed frame, so the committed array becomes the
        front one and the old front the next to be filled.
        """
        if not self._ready:
            return None
        self._ready = False
        frame = self._pending
        self._pending = None
        if self._swap:
            self._front, self._back = self._back, self._front
            self._published_shape = self._shape
        self._previous_ok = self._swap
        return frame

    @property
    def previous(self) -> Optional[np.ndarray]:
        """A read-only view of the published array, shaped as the latest ``acquire``.

        None before the first committed publish, after a publish of a written frame, or
        when the latest ``acquire`` asked for another shape than the published one.
        """
        front = self._front
        if not self._previous_ok or front is None or self._published_shape != self._shape:
            return None
        rows, cols = self._shape
        view = front[: rows * cols].reshape(rows, cols)
        view.flags.writeable = False
        return view


_ALLOCATED: Dict[int, "weakref.ReferenceType[np.ndarray]"] = {}
"""Every array a ``DebugFrameBuffers`` handed out, by id (debug runs only)."""

_POISONED: Dict[int, "weakref.ReferenceType[np.ndarray]"] = {}
"""Every array a ``DebugFrameBuffers`` recycled and filled with NaN, by id (debug runs only)."""


def _forget(registry: Dict[int, "weakref.ReferenceType[np.ndarray]"], key: int) -> Callable[["weakref.ReferenceType[np.ndarray]"], None]:
    def drop(_: "weakref.ReferenceType[np.ndarray]") -> None:
        registry.pop(key, None)

    return drop


def _registered(registry: Dict[int, "weakref.ReferenceType[np.ndarray]"], array: object) -> bool:
    ref = registry.get(id(array))
    return ref is not None and ref() is array


def _owner(array: object) -> object:
    """The array that owns ``array``'s memory (``array`` itself when it owns it)."""
    while isinstance(array, np.ndarray) and isinstance(array.base, np.ndarray):
        array = array.base
    return array


def _port_owned(array: object) -> bool:
    """Whether ``array``'s memory belongs to an array some ``DebugFrameBuffers`` allocated."""
    return _registered(_ALLOCATED, _owner(array))


def _data(frame: "Frame") -> object:
    return getattr(frame.payload, "data", None)


class DebugFrameBuffers(FrameBuffers):
    """``FrameBuffers`` that make lifetime mistakes loud, for debug runs.

    - Every ``acquire`` hands out a fresh array, and the array it replaces is filled with
      NaN, so a holder of a frame past its lifetime reads NaN, not new plausible data (the
      runtime's debug read check then raises).
    - ``commit`` raises for a frame over another array a port's buffers own (a view
      kept from an earlier ``acquire``). A frame over its own data (a copy, as a payload
      type that normalises makes) is allowed: nothing recycles it.
    - ``write`` raises for a frame whose data a port's buffers own: a node forwarding a
      frame it did not build must ``detach()`` it. A frame built over a node's own reused
      array cannot be recognised.
    """

    __slots__ = ()

    def _grow(self, current: Optional[np.ndarray], size: int) -> np.ndarray:
        """A fresh array every time, registered as port-owned."""
        owner = FramePayload.ensure_buffer(None, count=max(size, 1), components=1)
        key = id(owner)
        _ALLOCATED[key] = weakref.ref(owner, _forget(_ALLOCATED, key))
        return owner.reshape(-1)

    def acquire(self, count: int, components: int) -> np.ndarray:
        """A view of a fresh array; the array it replaces is poisoned with NaN."""
        if self._back is not None:
            self._back.fill(np.nan)
            owner = _owner(self._back)
            if isinstance(owner, np.ndarray):
                key = id(owner)
                _POISONED[key] = weakref.ref(owner, _forget(_POISONED, key))
        self._back = self._grow(None, count * components)
        return super().acquire(count, components)

    def commit(self, frame: "Frame") -> None:
        """Commit, after checking ``frame`` is not over an array of an earlier ``acquire``."""
        owner = _owner(_data(frame))
        if _registered(_ALLOCATED, owner) and (self._back is None or owner is not _owner(self._back)):
            raise FrameLifetimeError(
                "commit() needs a frame built on the view the latest acquire() returned"
            )
        super().commit(frame)

    def write(self, frame: "Frame") -> None:
        """Write, after checking no port's buffers own ``frame``'s data."""
        if _port_owned(_data(frame)):
            raise FrameLifetimeError(
                "write() was given a frame whose data a port's buffers own; call frame.detach() "
                "before passing on a frame this node did not build"
            )
        super().write(frame)


def has_stale_data(frame: "Frame") -> bool:
    """Whether ``frame``'s data is over an array a ``DebugFrameBuffers`` has recycled (and
    filled with NaN). NaN a node computed itself does not count."""
    return _registered(_POISONED, _owner(_data(frame)))
