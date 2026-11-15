"""The ports a node reads and writes during a pull.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Optional, Type

from rasl.graph.ports.spec import InputPortSpec, OutputPortSpec

if TYPE_CHECKING:
    from rasl.signal import Frame


# =============================================================================
# Runtime Port Objects (used during execution)
# =============================================================================


@dataclass
class InputPort:
    """A readable input port on a node.

    In PULL mode: Contains pre-pulled frame from upstream.
    In PUSH mode: Contains most recently pushed frame.

    Nodes read from input ports via read() during pull() execution.

    Attributes:
        name: Port name within the node.
        spec: InputPortSpec (type constraints, channels).
    """

    name: str
    spec: InputPortSpec
    _frame: Optional["Frame"] = field(default=None, repr=False)
    _has_upstream: bool = field(default=False, repr=False)

    def read(self, default: Optional["Frame"] = None) -> Optional["Frame"]:
        """Read the current frame on this port.

        Args:
            default: Value to return if no frame available.

        Returns:
            The frame, or default if port is empty/unconnected.
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

    def _set_frame(self, frame: Optional["Frame"]) -> None:
        """Internal: Set the frame (called by scheduler)."""
        self._frame = frame

    def _clear(self) -> None:
        """Internal: Clear the frame."""
        self._frame = None


@dataclass
class OutputPort:
    """A writable output port on a node.

    Nodes write frames to output ports during pull() execution.
    The scheduler routes written frames to connected downstream nodes.

    For push sources, the scheduler keeps the written frame as the port's latest so the
    frame can be propagated to downstream nodes.

    Attributes:
        name: Port name within the node.
        spec: OutputPortSpec (type constraints, channels).
    """

    name: str
    spec: OutputPortSpec
    _frame: Optional["Frame"] = field(default=None, repr=False)
    _written: bool = field(default=False, repr=False)
    _front_buffer: object | None = field(default=None, repr=False)
    _back_buffer: object | None = field(default=None, repr=False)
    _node_id: str = field(default="", repr=False)
    _on_write: Optional[Callable[["OutputPort"], None]] = field(default=None, repr=False)

    def write(self, frame: "Frame") -> None:
        """Write a frame to this output port.

        The frame will be routed to all connected downstream nodes
        after the current node's processing completes.

        For push sources, the frame is kept as the port's latest and read
        at the next tick; a write never causes a tick.

        Args:
            frame: The frame to output.
        """
        self._frame = frame
        self._written = True
        # Notify scheduler for push sources
        if self._on_write is not None:
            self._on_write(self)

    def acquire(self, count: int, *, components: int | None = None) -> "object":
        """Acquire a writable buffer for the next commit.

        Returns a NumPy array view (shape (count, components)) backed by the
        port's back buffer.
        """
        # Determine component width
        payload_type = None
        resolved = self.spec.resolve_payload_types()
        if resolved:
            payload_type = resolved[0]
            if components is None:
                components = getattr(payload_type, "components", None)

        if components is None:
            components = 1

        if payload_type is None:
            raise ValueError(
                f"OutputPort '{self.name}' cannot acquire a buffer: unresolved payload type '{self.spec.type_name}'"
            )

        # Delegate real storage allocation/resizing to the payload type.
        buf = payload_type.ensure_buffer(
            self._back_buffer,
            count=count,
            components=components,
        )
        self._back_buffer = buf
        return buf[:count, :components]

    def commit(self, frame: "Frame") -> None:
        """Commit a frame that uses the last-acquired back buffer.

        Swaps the port's front/back buffers to guarantee that previously
        committed frames remain stable until the next commit.
        """
        if not self.spec.accepts_payload_type(type(frame.payload)):
            raise TypeError(
                f"OutputPort '{self.name}' does not accept payload type {type(frame.payload).__name__}"
            )

        self._frame = frame
        self._written = True

        # Swap buffers: the just-written back buffer becomes the new front buffer.
        self._front_buffer, self._back_buffer = self._back_buffer, self._front_buffer

        if self._on_write is not None:
            self._on_write(self)

    @property
    def was_written(self) -> bool:
        """True if write() was called since last consume."""
        return self._written

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

    def _consume(self) -> Optional["Frame"]:
        """Internal: Get written frame and reset state."""
        frame = self._frame
        self._frame = None
        self._written = False
        return frame

    def _clear(self) -> None:
        """Internal: Clear the frame without consuming."""
        self._frame = None
        self._written = False
