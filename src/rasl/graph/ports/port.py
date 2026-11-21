"""The ports a node reads and writes during a pull.

Both kinds use one vocabulary (rasl-pd0.12). The side that produces a port's frame calls
``write`` (a frame that owns its data), or ``acquire`` then ``commit`` (a frame built in the
port's buffer); the framework's ``_publish`` makes it visible, which is when the port's two
buffers swap. The side that reads it calls ``read``. Node authors produce outputs and read
inputs; the framework produces inputs, so its calls on an ``InputPort`` carry a leading
underscore, as every framework-only call does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Type

from rasl.graph.ports.buffers import FrameBuffers
from rasl.graph.ports.spec import InputPortSpec, OutputPortSpec

if TYPE_CHECKING:
    import numpy as np

    from rasl.signal import Frame


@dataclass
class InputPort:
    """A readable input port on a node.

    Holds the frame the runtime published for the current pull: the upstream frame itself
    when one whole connection feeds the port, else a frame built in the port's buffers
    from the slices, repeats or connections that feed it.

    Attributes:
        name: Port name within the node.
        spec: InputPortSpec (type constraints, element count).
    """

    name: str
    spec: InputPortSpec
    _frame: Optional["Frame"] = field(default=None, repr=False)
    _has_upstream: bool = field(default=False, repr=False)
    _buffers: Optional[FrameBuffers] = field(default=None, repr=False)

    def read(self, default: Optional["Frame"] = None) -> Optional["Frame"]:
        """The frame published for this pull, or ``default`` when there is none.

        A frame built in the port's buffers stays unchanged until the port's second publish
        after it (two pulls of this node later); copy the data to keep it longer.
        """
        return self._frame if self._frame is not None else default

    @property
    def connected(self) -> bool:
        """True if an upstream node is connected to this port."""
        return self._has_upstream

    @property
    def count(self) -> Optional[int]:
        """Number of elements the port takes when its spec fixes it, else None (variable)."""
        return self.spec.fixed_count

    def accepts_payload_type(self, payload_type: Type) -> bool:
        """Check if this port accepts a payload type (delegated to spec)."""
        return self.spec.accepts_payload_type(payload_type)

    def resolve_payload_types(self) -> tuple[Type, ...]:
        """Resolve accepted type names to actual payload classes (delegated to spec)."""
        return self.spec.resolve_payload_types()

    def _write(self, frame: "Frame") -> None:
        """Framework: publish ``frame``, which the port does not own (one whole connection)."""
        self._frame = frame

    def _acquire(self, count: int, *, components: int) -> "np.ndarray":
        """Framework: the back buffer as a ``(count, components)`` view, to build a frame in.

        Raises:
            RuntimeError: If the runtime gave the port no buffers (``bind_ports`` does,
                for every port fed by slices, repeats or several connections).
        """
        buffers = self._buffers
        if buffers is None:
            raise RuntimeError(f"InputPort '{self.name}' has no buffers; the runtime binds them")
        return buffers.acquire(count, components)

    def _commit(self, frame: "Frame") -> None:
        """Framework: mark the back buffer complete, with ``frame`` (a view of it)."""
        assert self._buffers is not None
        self._buffers.commit(frame)

    def _publish(self) -> Optional["Frame"]:
        """Framework: publish the committed frame (the buffers swap); return it."""
        assert self._buffers is not None
        frame = self._buffers.publish()
        if frame is not None:
            self._frame = frame
        return frame

    def _clear(self) -> None:
        """Framework: no frame for this pull."""
        self._frame = None


@dataclass
class OutputPort:
    """A writable output port on a node.

    A node produces the port's frame in one of two ways during a pull:

    - ``write(frame)``: a frame whose data the node built itself.
    - ``acquire(count)``, fill the returned view, then ``commit(frame)`` with a frame built
      on that view: no allocation per frame.

    The runtime publishes what the node produced at the end of its pull, or, for a pushed
    output, at the start of the next tick; only then do readers see it, and only then do
    the port's two buffers swap. A published frame stays unchanged until the node's first
    fill after its next publish.

    Attributes:
        name: Port name within the node.
        spec: OutputPortSpec (type constraints, element count).
    """

    name: str
    spec: OutputPortSpec
    _buffers: FrameBuffers = field(default_factory=FrameBuffers, repr=False)
    _acquire_type: Optional[Type] = field(default=None, repr=False)

    def write(self, frame: "Frame") -> None:
        """Produce ``frame``, whose data this node built and owns.

        A node passing on a frame it did not build (an input frame, or another node's)
        calls ``frame.detach()`` first, so the frame does not change under its readers when
        its producer reuses the buffer behind it.

        Args:
            frame: The frame to output.
        """
        self._buffers.write(frame)

    def acquire(self, count: int, *, components: int | None = None) -> "np.ndarray":
        """A writable ``(count, components)`` float32 view of the port's back buffer.

        Fill it (vector operations can write straight into it), build a frame on it and
        ``commit`` that frame. Its contents are undefined; ``previous`` holds the frame
        readers see now. ``components`` defaults to the port's payload type's.

        Raises:
            ValueError: If the port's payload type is not registered.
        """
        payload_type = self._acquire_type
        if payload_type is None:
            resolved = self.spec.resolve_payload_types()
            if not resolved:
                raise ValueError(
                    f"OutputPort '{self.name}' cannot acquire a buffer: unresolved payload type "
                    f"'{self.spec.type_name}'"
                )
            payload_type = self._acquire_type = resolved[0]
        if components is None:
            components = getattr(payload_type, "components", None) or 1
        return self._buffers.acquire(count, components)

    def commit(self, frame: "Frame") -> None:
        """Mark the acquired buffer complete, with ``frame`` built on it.

        It is published at the end of this node's pull (or, for a pushed output, at the next
        tick); committing again before then replaces it.

        Raises:
            TypeError: If the port does not produce ``frame``'s payload type.
        """
        if not self.spec.accepts_payload_type(type(frame.payload)):
            raise TypeError(
                f"OutputPort '{self.name}' does not accept payload type {type(frame.payload).__name__}"
            )
        self._buffers.commit(frame)

    @property
    def previous(self) -> Optional["np.ndarray"]:
        """A read-only view of the frame readers see now, shaped as the latest ``acquire``.

        Lets a node update its last output in one vector operation into the new buffer
        (``np.multiply(out.previous, 0.9, out=buf)``). None before the first committed
        publish, after a publish of a written frame, or when the shape changed. For a pushed
        output it is the frame published at the last tick, not the last commit.
        """
        return self._buffers.previous

    @property
    def count(self) -> Optional[int]:
        """Number of elements the port produces when its spec fixes it, else None (variable)."""
        return self.spec.fixed_count

    def accepts_payload_type(self, payload_type: Type) -> bool:
        """Check if this port accepts a payload type (delegated to spec)."""
        return self.spec.accepts_payload_type(payload_type)

    def resolve_payload_types(self) -> tuple[Type, ...]:
        """Resolve accepted type names to actual payload classes (delegated to spec)."""
        return self.spec.resolve_payload_types()

    def _publish(self) -> Optional["Frame"]:
        """Framework: publish what the node produced since the last publish; return it.

        None (and no swap) when the node produced nothing complete.
        """
        return self._buffers.publish()

    def _clear(self) -> None:
        """Framework: drop what the node produced but has not been published."""
        self._buffers.clear()
