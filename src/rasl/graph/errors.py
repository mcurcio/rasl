"""Why the graph refuses a connection, with the ports it is about.

``GraphBuilder.connect`` (and the config loader that resolves ``connect`` lines) raise a
``ConnectError`` naming the problem and both ends of the connection, so a caller such as
the graph editor can mark the edge and its ports, not only print the message.

Each error is also the built-in exception it was before (``ValueError``, ``TypeError``
or ``KeyError``), so ``except ValueError`` keeps catching it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from rasl.graph.slices import Slice


class ConnectProblem(str, Enum):
    """What is wrong with a connection.

    Values:
        UNKNOWN_NODE: A node it names does not exist.
        UNKNOWN_PORT: A port it names does not exist on its node.
        BAD_REFERENCE: Its text is not a port reference, or it is not one the graph can
            build (a repeat of a source of unknown length).
        UNREGISTERED_TYPE: A port names a payload type nothing is registered under.
        SLICE_RANGE: A slice reaches past the end of its port.
        TYPE: The target port does not accept what the source emits.
        COUNT: Fixed source rows and fixed target rows differ.
        DUPLICATE: The same connection is already there.
        OVERLAP: It writes rows of the target port an earlier connection writes.
        COMPONENTS: A matrix coerced into a color type has another number of columns
            than the color has components.
    """

    UNKNOWN_NODE = "unknown-node"
    UNKNOWN_PORT = "unknown-port"
    BAD_REFERENCE = "bad-reference"
    UNREGISTERED_TYPE = "unregistered-type"
    SLICE_RANGE = "slice-range"
    TYPE = "type"
    COUNT = "count"
    DUPLICATE = "duplicate"
    OVERLAP = "overlap"
    COMPONENTS = "components"


@dataclass(frozen=True)
class Endpoint:
    """One end of a connection.

    Attributes:
        node: The node's id.
        port: The port's name; None when it was not resolved (an unknown node, a
            default port not yet looked up).
        slice: The slice of the port the connection reads or writes; None for all of it.
    """

    node: str
    port: str | None = None
    slice: Slice | None = None


class ConnectError(Exception):
    """A connection the graph refuses.

    Attributes:
        problem: What is wrong.
        source: The end that is read (the node emitting).
        target: The end that is written (the node receiving).
        other: For ``DUPLICATE`` and ``OVERLAP``, the source of the earlier connection
            into the same target port; else None.
        rows: For ``OVERLAP``, the rows of the target port this connection writes, as
            ``(start, end)``, end None for "to the end"; else None.
        other_rows: For ``OVERLAP``, the rows the earlier connection writes; else None.
        supplied: For ``COUNT``, the rows the source supplies (repeats included); for
            ``COMPONENTS``, the columns it supplies.
        takes: For ``COUNT``, the rows the target takes; for ``COMPONENTS``, the
            components of the color type it takes.
    """

    def __init__(
        self,
        problem: ConnectProblem,
        message: str,
        *,
        source: Endpoint,
        target: Endpoint,
        other: Endpoint | None = None,
        rows: tuple[int, int | None] | None = None,
        other_rows: tuple[int, int | None] | None = None,
        supplied: int | None = None,
        takes: int | None = None,
    ) -> None:
        super().__init__(message)
        self.problem = problem
        self.message = message
        self.source = source
        self.target = target
        self.other = other
        self.rows = rows
        self.other_rows = other_rows
        self.supplied = supplied
        self.takes = takes

    def __str__(self) -> str:
        """The message (a ``KeyError`` would print it quoted)."""
        return self.message


class ComponentsError(ValueError):
    """A plain matrix reached a color port with another number of columns than the color.

    Raised on the first frame that shows it, for a source whose width is not known before
    the graph runs (owner, 2026-11-16: "fail on first data if the ports are dynamic"). A
    width known at load is refused then, as a ``ConnectError`` with ``COMPONENTS``.

    Attributes:
        target: The port the frame was for.
        source: The output the frame came from.
        supplied: Columns the frame has.
        takes: Components of the port's color type.
    """

    def __init__(self, target: Endpoint, source: Endpoint, supplied: int, takes: int, type_name: str) -> None:
        self.target = target
        self.source = source
        self.supplied = supplied
        self.takes = takes
        super().__init__(
            f"{source.node}.{source.port} sent {supplied} columns into {target.node}.{target.port}, "
            f"which takes {type_name} ({takes} components)"
        )


class ConnectValueError(ConnectError, ValueError):
    """A ``ConnectError`` that is a ``ValueError``: a port, a slice, a count or an overlap."""


class ConnectTypeError(ConnectError, TypeError):
    """A ``ConnectError`` that is a ``TypeError``: payload types that do not match."""


class ConnectKeyError(ConnectError, KeyError):
    """A ``ConnectError`` that is a ``KeyError``: a node that does not exist."""
