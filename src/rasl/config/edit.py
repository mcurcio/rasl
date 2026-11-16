"""Edit the config files from a program (the web UI's graph editor, rasl-6sr).

The editor changes the files, never the running graph: a batch of edits is applied to
the config as written (comments and layout kept), rendered and built as a dry run, and
saved only when that succeeds. The watcher then sees the files change and the running
graph follows by the usual reload (``rasl.config.reload``), as for an edit in a text
editor.

Edits name what to do, not text:

- ``AddNode``: a ``node`` line, placed next to the nodes it connects to (below);
- ``RemoveNode``: the node's line and every ``connect`` line that reads it
  (owner, 2026-11-16: "remove the connections with it");
- ``RenameNode``: the node's id and every ``connect`` line that reads it;
- ``Connect`` / ``Disconnect``: a ``connect`` line in the receiving node's block, where
  the config writes routing.

Where a new node goes (owner, 2026-11-16, approved): in the block of the nodes the batch
connects it to; after the last node it reads from, in the order the graph lists them;
else before the first node that reads from it; else at the end of the root file's
``graph`` block. A node added from an output thus lands right below that node, and the
file reads in the order the signal flows.

A line read more than once (a file included twice) or written in a ``@snippet`` is
locked: an edit to it would change every copy. Such edits are refused with the reason
(rasl-6sr.7 decides how they become editable).

Every call loads the files again. ``version`` names their content; an edit sent with
a version that no longer matches is refused (``EditConflict``), and knobly's lost-update
check refuses a save when a file changed between load and write.

Example:
    >>> editor = ConfigEditor("rasl.conf")
    >>> result = editor.apply(
    ...     [AddNode("Smooth", "smooth"), Connect("hue_ramp", "smooth")],
    ...     base_version=editor.version(),
    ... )
    >>> result.ok, result.diff  # doctest: +SKIP
"""

from __future__ import annotations

import difflib
import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from rasl.config.build import build_plan, graph_directive
from rasl.config.connect import parse_port_ref
from rasl.config.document import (
    BadText,
    ConfigError,
    Directive,
    LostUpdate,
    Statement,
    WrittenGraph,
    children,
    config_text,
    edit_error,
    load_written,
    render_written,
    save_written,
)
from rasl.config.node_directive import node_id_of

_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
"""What a node id may be: what a ``connect`` line can name (``rasl.config.connect``)."""


@dataclass(frozen=True)
class AddNode:
    """Add a node: ``node <type> <id> [values];``.

    Attributes:
        type: The node type, as the config names it (``Waveform``, ``Color``).
        id: The new node's id; unique in the graph.
        values: Values after the id, as config text (``"rgb"`` for ``node Color c rgb``);
            empty for none.
        settings: The node's block, as ``(key, values)`` pairs of config text, in order
            (``("fps", "30")`` writes ``fps 30;``).
    """

    type: str
    id: str
    values: str = ""
    settings: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class RemoveNode:
    """Remove a node's line and every ``connect`` line that reads from it.

    Attributes:
        id: The node to remove.
    """

    id: str


@dataclass(frozen=True)
class RenameNode:
    """Give a node a new id, and rewrite every ``connect`` line that reads from it.

    Attributes:
        id: The node's id now.
        new_id: Its new id; unique in the graph.
    """

    id: str
    new_id: str


@dataclass(frozen=True)
class Connect:
    """Add ``connect <source> [<port>];`` to the target node's block.

    Attributes:
        source: What is read, in config notation: ``node``, ``node.port``,
            ``node[0~3]``, ``node.port[0~3]``.
        target: The id of the node that receives.
        port: The input port, in config notation (``pixels``, ``pixels[0~]``); None for
            the node's default input.
        repeat: Copies of the source written back to back; None for one.
        repeat_until: Rows to fill by repeating the source; None for no fill.
    """

    source: str
    target: str
    port: str | None = None
    repeat: int | None = None
    repeat_until: int | None = None


@dataclass(frozen=True)
class Disconnect:
    """Remove the ``connect`` line in the target's block that reads ``source`` [into ``port``].

    ``source`` and ``port`` match the line's values as the config writes them
    (``hue.out[0~3]``), after variables are filled in.

    Attributes:
        source: The line's first value.
        target: The id of the node whose block holds the line.
        port: The line's second value; None for a line with only a source.
    """

    source: str
    target: str
    port: str | None = None


Edit = AddNode | RemoveNode | RenameNode | Connect | Disconnect
"""One edit of a batch."""


class EditRefused(Exception):
    """An edit that cannot be made: an unknown node, a locked line, bad text.

    Attributes:
        index: Position of the edit in its batch.
        message: Why.
    """

    def __init__(self, index: int, message: str) -> None:
        self.index = index
        self.message = message
        super().__init__(f"Edit {index + 1}: {message}")


class EditConflict(Exception):
    """The files changed since the version the edits were made against."""


@dataclass(frozen=True)
class FileChange:
    """One file an edit batch changes.

    Attributes:
        path: The file's resolved path.
        before: Its text now.
        after: Its text with the batch applied.
    """

    path: str
    before: str
    after: str

    def diff(self) -> str:
        """The change as a unified diff, three lines of context."""
        return "".join(
            difflib.unified_diff(
                self.before.splitlines(keepends=True),
                self.after.splitlines(keepends=True),
                fromfile=self.path,
                tofile=self.path,
            )
        )


@dataclass(frozen=True)
class EditResult:
    """What a batch of edits does, or why it cannot be saved.

    Attributes:
        ok: True when the batch applies and the edited config builds.
        changes: The files the batch changes, in the order the config reads them.
        error: Why the edited config does not build (placed in the edited text);
            None when ``ok``.
        version: The version of the files after the call: the saved files' when
            ``apply`` saved, else the version the batch was made against.
        saved: Paths written; empty for a preview or a refused batch.
    """

    ok: bool
    changes: tuple[FileChange, ...]
    error: ConfigError | None
    version: str
    saved: tuple[str, ...] = ()

    @property
    def diff(self) -> str:
        """Every changed file's unified diff, one after another."""
        return "".join(change.diff() for change in self.changes)


def _version_of(graph: WrittenGraph) -> str:
    """A hash of every file the config reads, by path and text as loaded or saved."""
    digest = hashlib.sha256()
    for path, document in graph.documents.items():
        digest.update(path.encode())
        digest.update(b"\0")
        digest.update(document.saved_text.encode())
        digest.update(b"\0")
    return digest.hexdigest()


class ConfigEditor:
    """Applies edit batches to the config files at one path.

    Holds no state but the path: every call loads the files again.

    Args:
        path: The root config file (the one ``rasl`` was started with).
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def version(self) -> str:
        """The version of the files now on disk (a hash of their paths and texts)."""
        return _version_of(load_written(self.path))

    def preview(self, edits: Sequence[Edit], base_version: str) -> EditResult:
        """Apply ``edits`` to a copy and check it; write nothing.

        Raises:
            EditConflict: If the files are no longer at ``base_version``.
            EditRefused: If an edit cannot be made.
        """
        graph = self._load(base_version)
        changes, error = self._apply(graph, edits)
        return EditResult(ok=error is None, changes=changes, error=error, version=base_version)

    def apply(self, edits: Sequence[Edit], base_version: str) -> EditResult:
        """Apply ``edits``, check the result, and save the files when it builds.

        Nothing is written when the edited config does not build: ``ok`` is False and
        ``error`` says why.

        Raises:
            EditConflict: If the files are no longer at ``base_version``, or changed on
                disk while the batch was being applied.
            EditRefused: If an edit cannot be made.
        """
        graph = self._load(base_version)
        changes, error = self._apply(graph, edits)
        if error is not None or not changes:
            return EditResult(ok=error is None, changes=changes, error=error, version=base_version)
        try:
            saved = save_written(graph)
        except LostUpdate as lost:
            raise EditConflict(f"Changed on disk while saving: {', '.join(lost.paths)}") from lost
        return EditResult(
            ok=True, changes=changes, error=None, version=_version_of(graph), saved=tuple(saved)
        )

    def _load(self, base_version: str) -> WrittenGraph:
        graph = load_written(self.path)
        if _version_of(graph) != base_version:
            raise EditConflict("The config files changed since this edit was made; reload them")
        return graph

    def _apply(
        self, graph: WrittenGraph, edits: Sequence[Edit]
    ) -> tuple[tuple[FileChange, ...], ConfigError | None]:
        for index, edit in enumerate(edits):
            _Batch(graph, edits, index).apply(edit)
        changes = tuple(
            FileChange(path, document.saved_text, document.text)
            for path, document in graph.documents.items()
            if document.text != document.saved_text
        )
        try:
            build_plan(render_written(graph))
        except ConfigError as error:
            return changes, error
        return changes, None


class _Batch:
    """One edit applied to the written config, with the batch around it for placement."""

    def __init__(self, graph: WrittenGraph, edits: Sequence[Edit], index: int) -> None:
        self.graph = graph
        self.edits = edits
        self.index = index
        try:
            tree = render_written(graph)
            self.graph_block = graph_directive(tree)
        except ConfigError as error:
            raise EditRefused(index, f"The config does not load: {error.message}") from error
        self.nodes: dict[str, Directive] = {}
        for directive in children(self.graph_block, "node"):
            node_id = node_id_of(directive)
            if node_id is not None:
                self.nodes[node_id] = directive

    def refuse(self, message: str) -> EditRefused:
        """An ``EditRefused`` for this edit."""
        return EditRefused(self.index, message)

    def apply(self, edit: Edit) -> None:
        """Apply one edit to the written config."""
        match edit:
            case AddNode():
                self.add_node(edit)
            case RemoveNode(node_id):
                self.remove_node(node_id)
            case RenameNode(node_id, new_id):
                self.rename_node(node_id, new_id)
            case Connect():
                self.connect(edit)
            case Disconnect():
                self.disconnect(edit)

    # -- lookups ---------------------------------------------------------------------

    def node(self, node_id: str) -> Directive:
        """The rendered ``node`` directive of ``node_id``."""
        if node_id not in self.nodes:
            raise self.refuse(f"No node '{node_id}' in the graph")
        return self.nodes[node_id]

    def editable(self, directive: Directive, what: str) -> Statement:
        """The line ``directive`` is written on, when an edit there changes only it."""
        statement = directive.written
        parent = statement.parent
        while parent is not None:
            if parent.kind == "snippet":
                raise self.refuse(f"{what} is written in @snippet {parent.name}; it is locked")
            parent = parent.parent
        copies = len(statement.copies())
        if copies != 1:
            raise self.refuse(f"{what} is in a file read {copies} times; it is locked")
        return statement

    def readers(self, node_id: str) -> list[Directive]:
        """Every rendered ``connect`` line in the graph that reads from ``node_id``."""
        found = []
        for directive in self.nodes.values():
            for line in children(directive, "connect"):
                if line.values and _source_node(_canonical(line.values[0])) == node_id:
                    found.append(line)
        return found

    def check_new_id(self, node_id: str) -> None:
        """Refuse an id that is malformed or already taken."""
        if not _ID.match(node_id):
            raise self.refuse(f"'{node_id}' is not a node id: letters, digits and _, not first a digit")
        if node_id in self.nodes:
            raise self.refuse(f"A node '{node_id}' already exists")

    # -- edits -----------------------------------------------------------------------

    def add_node(self, edit: AddNode) -> None:
        self.check_new_id(edit.id)
        head = f"node {edit.type} {edit.id}" + (f" {edit.values}" if edit.values else "")
        if edit.settings:
            body = "".join(f"    {key} {values};\n" for key, values in edit.settings)
            line = f"{head} {{\n{body}}}"
        else:
            line = f"{head};"
        try:
            self.place(edit.id, line)
        except BadText as error:
            raise self.refuse(edit_error(error, line).message) from error

    def place(self, node_id: str, line: str) -> None:
        """Insert ``line`` by the placement rule (module docstring)."""
        upstream: set[str] = set()
        downstream: set[str] = set()
        for edit in self.edits:
            if isinstance(edit, Connect):
                source = _source_node(edit.source)
                if edit.target == node_id and source is not None:
                    upstream.add(source)
                elif source == node_id:
                    downstream.add(edit.target)
        order = list(self.nodes)
        before = [n for n in order if n in upstream]
        after = [n for n in order if n in downstream]
        if before:
            self.editable(self.nodes[before[-1]], f"Node '{before[-1]}'").insert_after(config_text(line))
        elif after:
            self.editable(self.nodes[after[0]], f"Node '{after[0]}'").insert_before(config_text(line))
        else:
            graph_line = self.editable(self.graph_block, "The graph block")
            assert graph_line.block is not None  # a rendered graph block has one
            graph_line.block.add_statements(config_text(line))

    def remove_node(self, node_id: str) -> None:
        statement = self.editable(self.node(node_id), f"Node '{node_id}'")
        lines = [
            self.editable(line, f"The connect line in node '{node_id_of(line.parent)}'")
            for line in self.readers(node_id)
            if line.parent is not None and node_id_of(line.parent) != node_id
        ]
        for line in lines:
            line.remove()
        statement.remove()

    def rename_node(self, node_id: str, new_id: str) -> None:
        self.check_new_id(new_id)
        directive = self.node(node_id)
        self.editable(directive, f"Node '{node_id}'")
        id_value = directive.values[0 if len(directive.values) == 1 else 1]
        values = []
        for line in self.readers(node_id):
            self.editable(line, f"The connect line in node '{node_id_of(line.parent)}'")
            value = line.values[0].written
            if value is None or value.kind == "reference":
                raise self.refuse(f"A connect line reads '{node_id}' through a variable; it is locked")
            values.append(value)
        if id_value.written is None or id_value.written.kind == "reference":
            raise self.refuse(f"Node '{node_id}' takes its id from a variable; it is locked")
        id_value.written.set(config_text(new_id))
        for value in values:
            value.set(config_text(re.sub(rf"^{re.escape(node_id)}\b", new_id, value.text)))

    def connect(self, edit: Connect) -> None:
        if edit.repeat is not None and edit.repeat_until is not None:
            raise self.refuse("A connection takes repeat or repeat_until, not both")
        line = f"connect {edit.source}" + (f" {edit.port}" if edit.port else "")
        if edit.repeat is not None:
            line += f" {{\n    repeat {edit.repeat};\n}}"
        elif edit.repeat_until is not None:
            line += f" {{\n    repeat_until {edit.repeat_until};\n}}"
        else:
            line += ";"
        statement = self.editable(self.node(edit.target), f"Node '{edit.target}'")
        try:
            if statement.block is None:
                _add_block(statement, line)
            else:
                statement.block.add_statements(config_text(line))
        except BadText as error:
            raise self.refuse(edit_error(error, line).message) from error

    def disconnect(self, edit: Disconnect) -> None:
        wanted = (edit.source,) if edit.port is None else (edit.source, edit.port)
        for line in children(self.node(edit.target), "connect"):
            if tuple(_canonical(value) for value in line.values) == wanted:
                self.editable(line, f"The connect line in node '{edit.target}'").remove()
                return
        raise self.refuse(
            f"Node '{edit.target}' has no line 'connect {' '.join(wanted)}'"
        )


def _source_node(ref: str) -> str | None:
    """The node a port reference in config notation (``hue.out[0~3]``) names."""
    try:
        return parse_port_ref(ref.replace("~", ":")).node
    except ValueError:
        return None


def _canonical(value: object) -> str:
    """A rendered value's text as the config writes it (``hue.out[0~3]``)."""
    return str(getattr(value, "text"))


def _add_block(statement: Statement, line: str) -> None:
    """Give a directive written without a block one holding ``line``.

    The directive is written again with ``{ line }`` in place of its ``;``; the comments
    it owns stay (a trailing comment moves after the ``}``).
    """
    text = statement.text
    semicolon = _final_semicolon(text)
    head, tail = text[:semicolon].rstrip(), text[semicolon + 1 :]
    # knobly takes the first line as unindented and keeps the others' indentation
    # relative to it, so the head's later lines (a leading comment's next line) drop
    # the indentation they carry in the file
    indent = " " * statement.place.span.start.column
    head_lines = head.split("\n")
    head = "\n".join(
        [head_lines[0]]
        + [part[len(indent) :] if part.startswith(indent) else part for part in head_lines[1:]]
    )
    inner = "".join(f"    {part}\n" for part in line.splitlines())
    statement.replace_with_text(config_text(f"{head} {{\n{inner}}}{tail}"))


def _final_semicolon(text: str) -> int:
    """Index of the ``;`` that ends a statement's text, skipping strings and comments."""
    end = -1
    quote: str | None = None
    i = 0
    while i < len(text):
        char = text[i]
        if quote is not None:
            if char == "\\" and quote == '"':
                i += 1
            elif char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "#":
            newline = text.find("\n", i)
            if newline < 0:
                break
            i = newline
        elif char == ";":
            end = i
        i += 1
    if end < 0:
        raise ValueError(f"No ';' ends {text!r}")
    return end
