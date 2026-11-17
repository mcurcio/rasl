"""Config documents: rasl's one bridge to knobly, the config language.

knobly (https://github.com/mcurcio/knobly) parses the files, works out variables (``@set``),
snippets (``@snippet`` / ``@use``) and included files (``@include``), and gives back a
rendered tree of directives. This module loads that tree and holds the few rules rasl
adds when it reads one:

- ``load_document`` / ``parse_document``: a file or a text as a ``knobly.rendered.Rendered``;
  any problem knobly finds raises ``ConfigError``.
- ``arg_text`` / ``arg_texts``: a directive's values as the strings rasl's parsers take.
- ``scalar``: a value as the Python value a node's config model validates.
- ``config_error``: a ``ConfigError`` placed on a directive, a value or the whole config.
- ``load_written`` / ``render_written`` / ``save_written`` / ``config_text``: the config as
  written, for a program that edits the files (``rasl.config.edit``): load it, edit its
  statements, render it to check, and save it back with comments and layout kept.

Example:
    >>> tree = parse_document("graph { node Waveform wave { fps 30; } }")
    >>> node = tree.block.directives("graph")[0].block[0]
    >>> node.name, arg_texts(node)
    ('node', ('Waveform', 'wave'))
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from knobly import (
    BadTextError,
    ConfigText,
    DiagnosticError,
    Diagnostics,
    LocatedDiagnostic,
    LostUpdateError,
    memory_source,
    rendered,
    text,
    written,
)
from knobly.files import file_source, file_writer
from knobly.include import include

if TYPE_CHECKING:
    from rasl.graph import ConnectError

logger = structlog.get_logger()

Rendered = rendered.Rendered
"""A loaded config: ``block`` holds its top-level directives."""

Directive = rendered.Directive
"""A directive of a loaded config: ``name``, ``values`` and ``block`` (None without one)."""

WrittenGraph = written.DocumentGraph
"""A config as written: every file it reads, editable, and saved back with ``save_written``."""

Statement = written.WrittenDirective
"""A directive as written: the line an edit changes (``rendered`` directives' ``written``)."""

Value = written.ExpandedValue
"""One value of a directive: a word, a string, a list, a slice or an index."""

_TEXT_PATH = "config"
"""The name a config given as text has in error messages."""


class ConfigError(Exception):
    """A problem in a config, placed where it was written.

    Attributes:
        message: Description of the first problem.
        line: Line of the first problem (1-indexed), or 0 when it has no place.
        column: Column of the first problem (0-indexed), or None.
        diagnostics: Every problem, as knobly located diagnostics (file, span and the
            include / snippet / variable steps that led there). Empty when the error
            was made without a place.
        documents: Every file the load read, the broken ones included (what a
            watcher must watch to see the fix). Empty when the error was made
            without a place.
        connection: For a connection the graph refuses (code ``rasl/connect``), the
            graph's ``ConnectError``: the problem and both ends, ports and slices
            included. None for every other error.
    """

    def __init__(
        self,
        message: str,
        line: int = 0,
        column: int | None = None,
        *,
        diagnostics: tuple[LocatedDiagnostic, ...] = (),
        documents: tuple[str, ...] = (),
        formatted: str | None = None,
        connection: ConnectError | None = None,
    ) -> None:
        self.message = message
        self.connection = connection
        self.line = line
        self.column = column
        self.diagnostics = diagnostics
        self.documents = documents
        if formatted is None:
            formatted = f"Line {line}: {message}" if line else message
        super().__init__(formatted)

    @classmethod
    def from_diagnostics(
        cls,
        diagnostics: tuple[LocatedDiagnostic, ...],
        graph: written.DocumentGraph,
        connection: ConnectError | None = None,
    ) -> "ConfigError":
        """One error for all of ``diagnostics``, printed with source lines and carets."""
        first = diagnostics[0]
        start = first.place.span.start
        return cls(
            first.message,
            line=start.line + 1,
            column=start.column,
            diagnostics=diagnostics,
            documents=tuple(graph.documents),
            formatted="\n".join(written.format_diagnostic(d, graph) for d in diagnostics),
            connection=connection,
        )


def config_error(
    at: Rendered | Directive | Value,
    message: str,
    *,
    code: str,
    tree: Rendered,
    connection: ConnectError | None = None,
) -> ConfigError:
    """A ``ConfigError`` placed on ``at``, a directive, a value or the whole config.

    Args:
        at: What the problem is about.
        message: Description of the problem.
        code: rasl's code for it, ``rasl/<name>``.
        tree: The rendered config ``at`` belongs to (for the source line shown).
        connection: The graph's error, for a connection it refuses.
    """
    error: DiagnosticError = at.error(message, code=code)
    return ConfigError.from_diagnostics((error.diagnostic,), tree.graph, connection)


def _render(graph: written.DocumentGraph) -> Rendered:
    tree = rendered.render(graph)
    errors = Diagnostics(tree.diagnostics).errors
    if errors:
        raise ConfigError.from_diagnostics(errors, graph)
    for warning in tree.diagnostics:
        logger.warning("config.warning", detail=written.format_diagnostic(warning, graph))
    return tree


def load_document(path: str | Path) -> Rendered:
    """Load a config file, and every file it includes, as a rendered tree.

    Raises:
        ConfigError: If knobly finds a problem in the files.
        FileNotFoundError: If the file doesn't exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    processor = written.Processor(source=file_source(), extensions=[include()])
    return _render(processor.load(str(path)))


def load_written(path: str | Path) -> WrittenGraph:
    """Load a config file, and every file it includes, as written, for editing.

    Problems in the files are not raised here: ``render_written`` raises them.

    Raises:
        FileNotFoundError: If the file doesn't exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    processor = written.Processor(source=file_source(), extensions=[include()])
    return processor.load(str(path))


def render_written(graph: WrittenGraph) -> Rendered:
    """Render a config as written (edited or not), as ``load_document`` would.

    Raises:
        ConfigError: If knobly finds a problem in the files.
    """
    return _render(graph)


def save_written(graph: WrittenGraph) -> list[str]:
    """Write every file of ``graph`` whose text was edited; return their paths.

    Raises:
        knobly.LostUpdateError: If a file changed on disk since it was loaded; nothing
            is written.
        knobly.SaveError: If writing failed.
    """
    return list(graph.save(file_writer()))


def config_text(raw: str) -> ConfigText:
    """Text written in config syntax, as an edit takes it (checked by the edit)."""
    return text(raw)


def edit_error(error: BadTextError, what: str) -> ConfigError:
    """A ``ConfigError`` for text an edit refused, placed in that text.

    Args:
        error: What knobly raised.
        what: The text the edit was given, quoted in the message.
    """
    first = error.diagnostics[0]
    start = first.span.start
    return ConfigError(
        f"{first.message} in {what!r}", line=start.line + 1, column=start.column
    )


LostUpdate = LostUpdateError
"""Raised by ``save_written`` when a file changed on disk since it was loaded."""

BadText = BadTextError
"""Raised by an edit given text that does not parse where it goes."""


def parse_document(text: str) -> Rendered:
    """Parse config text as a rendered tree. Useful for testing.

    The text has no folder, so an ``@include`` in it finds no file.

    Raises:
        ConfigError: If knobly finds a problem in the text.
    """
    processor = written.Processor(
        source=memory_source({_TEXT_PATH: text}), extensions=[include()]
    )
    return _render(processor.load(_TEXT_PATH))


def line_of(directive: Directive) -> int:
    """The line a directive is written on (1-indexed)."""
    return directive.origin.place.span.start.line + 1


def children(directive: Directive, name: str | None = None) -> tuple[Directive, ...]:
    """The directives in a directive's block (none without a block), all or by name."""
    block = directive.block
    if block is None:
        return ()
    return tuple(block) if name is None else tuple(block.directives(name))


def arg_text(value: Value) -> str:
    """A value as the string rasl's own parsers take.

    A word is its text; a string is its decoded text; a slice or an index is a port
    reference in rasl's notation (``leds[0:3]``, ``leds[0:]``, ``leds[3]``; the config
    file writes ``leds[0~3]``); a list is its canonical text (``[[1, 0, 0], [0.5, 0, 0]]``).
    """
    match value:
        case written.ExpandedString():
            return value.string()
        case written.ExpandedSlice(name, start, end):
            return f"{name}[{'' if start is None else start}:{'' if end is None else end}]"
        case written.ExpandedIndex(name, index):
            return f"{name}[{index}]"
        case _:
            return value.text


def arg_texts(directive: Directive) -> tuple[str, ...]:
    """A directive's values, each as ``arg_text`` gives it."""
    return tuple(arg_text(value) for value in directive.values)


def _coerce_word(word: str) -> str | int | float | bool:
    """Read a bare word as a boolean or a number when it is spelled as one."""
    lowered = word.lower()
    if lowered in ("true", "on", "yes"):
        return True
    if lowered in ("false", "off", "no"):
        return False
    try:
        return int(word)
    except ValueError:
        pass
    try:
        return float(word)
    except ValueError:
        pass
    return word


def scalar(value: Value) -> Any:
    """A value as the Python value a config model validates.

    A bare word becomes a bool (``true``/``on``/``yes``, ``false``/``off``/``no``), an int
    or a float when it is spelled as one, else stays a str. A quoted string is always a
    str. A list becomes a list of its items, read the same way. A slice or an index is
    the string ``arg_text`` gives.
    """
    match value:
        case written.ExpandedWord(text):
            return _coerce_word(text)
        case written.ExpandedList(items):
            return [scalar(item) for item in items]
        case _:
            return arg_text(value)
