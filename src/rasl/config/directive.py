"""Directive - Immutable recursive config tree.

This module provides the Directive class which represents parsed
crossplane configuration as an immutable tree structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import crossplane

if TYPE_CHECKING:
    from pydantic import BaseModel


@dataclass(frozen=True)
class Directive:
    """Immutable recursive config directive tree.

    Represents a single directive from a crossplane-parsed config file.
    The tree structure mirrors the config file's block nesting.

    Attributes:
        keyword: The directive name (e.g., "node", "connect", "fps").
        args: Positional arguments as strings.
        block: Child directives (for block directives).
        line: Line number in source file for error reporting.

    Example:
        For config: `node DdpSink leds { target "10.0.0.1"; }`

        Directive(
            keyword="node",
            args=("DdpSink", "leds"),
            block=(
                Directive(keyword="target", args=("10.0.0.1",), block=()),
            ),
        )
    """

    keyword: str
    args: tuple[str, ...]
    block: tuple["Directive", ...]
    line: int = 0

    # Note: _config is handled via object.__setattr__ since frozen=True
    # This allows ConfigDispatch to attach pre-parsed models

    @property
    def config(self) -> "BaseModel | None":
        """Pre-parsed Pydantic model, if set by ConfigDispatch."""
        return getattr(self, "_config", None)

    def slice_args(self, start: int, end: int | None = None) -> "Directive":
        """Return new Directive with sliced args, preserving block.

        Useful for passing remaining args to child parsers.

        Args:
            start: Start index for args slice.
            end: End index (exclusive), or None for all remaining.

        Returns:
            New Directive with args[start:end].

        Example:
            >>> d = Directive("node", ("DdpSink", "leds", "rgb"), ())
            >>> d.slice_args(2)
            Directive("node", ("rgb",), ())
        """
        return Directive(
            keyword=self.keyword,
            args=self.args[start:end],
            block=self.block,
            line=self.line,
        )

    def with_args(self, *args: str) -> "Directive":
        """Return new Directive with replaced args.

        Args:
            *args: New argument values.

        Returns:
            New Directive with specified args.
        """
        return Directive(
            keyword=self.keyword,
            args=args,
            block=self.block,
            line=self.line,
        )

    def find(self, keyword: str) -> list["Directive"]:
        """Find all child directives with given keyword.

        Args:
            keyword: Keyword to search for.

        Returns:
            List of matching child directives.
        """
        return [d for d in self.block if d.keyword == keyword]

    def find_one(self, keyword: str) -> "Directive | None":
        """Find first child directive with given keyword.

        Args:
            keyword: Keyword to search for.

        Returns:
            First matching directive, or None.
        """
        for d in self.block:
            if d.keyword == keyword:
                return d
        return None

    @classmethod
    def from_crossplane(cls, raw: dict[str, Any]) -> "Directive":
        """Parse crossplane dict into Directive tree.

        Args:
            raw: Dict from crossplane.parse() output.

        Returns:
            Directive tree.
        """
        return cls(
            keyword=raw["directive"],
            args=tuple(raw.get("args", [])),
            block=tuple(cls.from_crossplane(d) for d in raw.get("block", [])),
            line=raw.get("line", 0),
        )

    @classmethod
    def from_file(cls, path: Path | str) -> "Directive":
        """Load file and return synthetic root directive.

        The root directive has keyword="_root" and contains all
        top-level directives as its block.

        Args:
            path: Path to config file.

        Returns:
            Root Directive containing file contents.

        Raises:
            FileNotFoundError: If file doesn't exist.
            crossplane.errors.NgxParserError: If parsing fails.
        """
        path = Path(path)
        raw = crossplane.parse(str(path))
        parsed = raw["config"][0]["parsed"]
        return cls(
            keyword="_root",
            args=(),
            block=tuple(cls.from_crossplane(d) for d in parsed),
            line=0,
        )

    @classmethod
    def from_string(cls, content: str) -> "Directive":
        """Parse config string and return synthetic root directive.

        Useful for testing.

        Args:
            content: Config file content as string.

        Returns:
            Root Directive containing parsed contents.
        """
        import tempfile
        import os

        # crossplane requires a file, so use temp file
        fd, path = tempfile.mkstemp(suffix=".conf")
        try:
            os.write(fd, content.encode())
            os.close(fd)
            return cls.from_file(path)
        finally:
            os.unlink(path)

    def __repr__(self) -> str:
        """Compact representation for debugging."""
        args_str = ", ".join(repr(a) for a in self.args)
        if self.block:
            return f"Directive({self.keyword!r}, ({args_str}), [{len(self.block)} children])"
        return f"Directive({self.keyword!r}, ({args_str}))"
