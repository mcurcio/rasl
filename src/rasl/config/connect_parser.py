"""Parser for connect directive syntax.

This module provides the parser for RASL's connect directive, which defines
channel-level connections between node ports.

Syntax:
    connect <sourceNode>[.<sourcePort>][<slice>] [<destPort>][<slice>];

Examples:
    connect upstream;
    connect upstream.rgb;
    connect upstream[0:3];
    connect upstream.rgb[0:3] input[0:3];
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from typing import Optional

from rasl.engine.slices import Slice


class ConnectParseError(Exception):
    """Error parsing a connect directive.

    Attributes:
        message: Description of the error.
        column: 0-based column position where error occurred.
        source_text: The original source text being parsed.
    """

    def __init__(
        self,
        message: str,
        column: Optional[int] = None,
        source_text: Optional[str] = None,
    ) -> None:
        self.message = message
        self.column = column
        self.source_text = source_text
        super().__init__(self._format())

    def _format(self) -> str:
        parts = [self.message]
        if self.source_text is not None and self.column is not None:
            parts.append(f"\n  {self.source_text}")
            parts.append(f"\n  {' ' * self.column}^")
        return "".join(parts)


@dataclass(frozen=True, slots=True)
class ParsedConnect:
    """Result of parsing a connect directive.

    Attributes:
        source_node: Name of the upstream node.
        source_port: Name of the source output port, or None to use default.
        source_slice: Channel slice on source, or None for full port.
        dest_port: Name of the destination input port, or None to use default.
        dest_slice: Channel slice on destination, or None for full port.
    """

    source_node: str
    source_port: Optional[str] = None
    source_slice: Optional[Slice] = None
    dest_port: Optional[str] = None
    dest_slice: Optional[Slice] = None


# Token patterns
_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_INTEGER_PATTERN = re.compile(r"[0-9]+")
_WHITESPACE_PATTERN = re.compile(r"\s+")


class _Tokenizer:
    """Simple tokenizer for connect directive syntax."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.pos = 0

    def at_end(self) -> bool:
        return self.pos >= len(self.source)

    def skip_whitespace(self) -> None:
        match = _WHITESPACE_PATTERN.match(self.source, self.pos)
        if match:
            self.pos = match.end()

    def peek(self) -> str:
        if self.at_end():
            return ""
        return self.source[self.pos]

    def consume(self, char: str) -> bool:
        if self.peek() == char:
            self.pos += 1
            return True
        return False

    def expect(self, char: str) -> None:
        if not self.consume(char):
            raise ConnectParseError(
                f"Expected '{char}'",
                column=self.pos,
                source_text=self.source,
            )

    def read_identifier(self) -> Optional[str]:
        match = _IDENTIFIER_PATTERN.match(self.source, self.pos)
        if match:
            self.pos = match.end()
            return match.group()
        return None

    def read_integer(self) -> Optional[int]:
        match = _INTEGER_PATTERN.match(self.source, self.pos)
        if match:
            self.pos = match.end()
            return int(match.group())
        return None


def _parse_slice(tokenizer: _Tokenizer) -> Slice:
    """Parse a slice expression after '['.

    Forms:
        [n]       -> Slice(n, n+1)
        [start:]  -> Slice(start, None)
        [start:end] -> Slice(start, end)
    """
    start_pos = tokenizer.pos
    start = tokenizer.read_integer()
    if start is None:
        raise ConnectParseError(
            "Expected integer in slice",
            column=tokenizer.pos,
            source_text=tokenizer.source,
        )

    if start < 0:
        raise ConnectParseError(
            "Negative indices not allowed",
            column=start_pos,
            source_text=tokenizer.source,
        )

    if tokenizer.consume(":"):
        # Range form
        end = tokenizer.read_integer()
        if end is not None:
            if end < start:
                raise ConnectParseError(
                    f"Slice end ({end}) must be >= start ({start})",
                    column=tokenizer.pos - len(str(end)),
                    source_text=tokenizer.source,
                )
            tokenizer.expect("]")
            return Slice(start, end)
        else:
            # Open-ended: [start:]
            tokenizer.expect("]")
            return Slice(start, None)
    else:
        # Single index: [n] -> [n:n+1]
        tokenizer.expect("]")
        return Slice(start, start + 1)


def _parse_source_spec(
    tokenizer: _Tokenizer,
) -> tuple[str, Optional[str], Optional[Slice]]:
    """Parse source specification: node[.port][slice]"""
    node = tokenizer.read_identifier()
    if node is None:
        raise ConnectParseError(
            "Expected node identifier",
            column=tokenizer.pos,
            source_text=tokenizer.source,
        )

    port: Optional[str] = None
    slice_spec: Optional[Slice] = None

    # Check for .port
    if tokenizer.consume("."):
        port = tokenizer.read_identifier()
        if port is None:
            raise ConnectParseError(
                "Expected port identifier after '.'",
                column=tokenizer.pos,
                source_text=tokenizer.source,
            )

    # Check for [slice]
    if tokenizer.consume("["):
        slice_spec = _parse_slice(tokenizer)

    return node, port, slice_spec


def _parse_dest_spec(
    tokenizer: _Tokenizer,
) -> tuple[Optional[str], Optional[Slice]]:
    """Parse destination specification: port[slice]"""
    port = tokenizer.read_identifier()
    if port is None:
        raise ConnectParseError(
            "Expected port identifier",
            column=tokenizer.pos,
            source_text=tokenizer.source,
        )

    slice_spec: Optional[Slice] = None
    if tokenizer.consume("["):
        slice_spec = _parse_slice(tokenizer)

    return port, slice_spec


def parse_connect(source: str) -> ParsedConnect:
    """Parse a connect directive string.

    Args:
        source: The connect directive arguments (without 'connect' keyword
                and trailing semicolon). E.g., "upstream.rgb[0:3] input[0:3]"

    Returns:
        ParsedConnect with resolved source and destination specifications.

    Raises:
        ConnectParseError: If the syntax is invalid.

    Examples:
        >>> parse_connect("upstream")
        ParsedConnect(source_node='upstream', ...)

        >>> parse_connect("upstream.rgb[0:3] input[0:3]")
        ParsedConnect(
            source_node='upstream',
            source_port='rgb',
            source_slice=Slice(start=0, end=3),
            dest_port='input',
            dest_slice=Slice(start=0, end=3),
        )
    """
    warnings.warn(
        "rasl.config.connect_parser.parse_connect is deprecated; use rasl.config.connection.parse_port_ref instead",
        DeprecationWarning,
        stacklevel=2,
    )
    if not source or not source.strip():
        raise ConnectParseError("Empty connect directive")

    tokenizer = _Tokenizer(source)
    tokenizer.skip_whitespace()

    # Parse source spec
    source_node, source_port, source_slice = _parse_source_spec(tokenizer)

    tokenizer.skip_whitespace()

    # Check for optional dest spec
    dest_port: Optional[str] = None
    dest_slice: Optional[Slice] = None

    if not tokenizer.at_end():
        dest_port, dest_slice = _parse_dest_spec(tokenizer)
        tokenizer.skip_whitespace()

    if not tokenizer.at_end():
        raise ConnectParseError(
            "Unexpected characters after connect directive",
            column=tokenizer.pos,
            source_text=source,
        )

    return ParsedConnect(
        source_node=source_node,
        source_port=source_port,
        source_slice=source_slice,
        dest_port=dest_port,
        dest_slice=dest_slice,
    )


def parse_connect_batch(sources: list[str]) -> list[ParsedConnect]:
    """Parse multiple connect directives.

    Args:
        sources: List of connect directive strings.

    Returns:
        List of ParsedConnect results.

    Raises:
        ConnectParseError: If any directive fails to parse.
            The error message includes the index of the failing directive.
    """
    warnings.warn(
        "rasl.config.connect_parser.parse_connect_batch is deprecated; use rasl.config.connection.parse_port_ref instead",
        DeprecationWarning,
        stacklevel=2,
    )
    results: list[ParsedConnect] = []
    errors: list[str] = []

    for i, source in enumerate(sources):
        try:
            results.append(parse_connect(source))
        except ConnectParseError as e:
            errors.append(f"[{i}] {e}")

    if errors:
        raise ConnectParseError(
            f"Failed to parse {len(errors)} connect directive(s):\n"
            + "\n".join(errors)
        )

    return results
