"""Literal source node - produces time-invariant payloads.

This module provides LiteralNode, a source that outputs a constant
payload parsed from config. The literal value is passed directly to
the appropriate payload constructor based on the type specifier.

Syntax:
    node literal <name> <kind>:<subtype> <literal_expr>;

Examples:
    node literal static_hsl color:hsl [[1, 0, 0], [0.5, 0, 0], [0.3, 0, 0]];
    node literal warm_okhsl color:okhsl [[0.1, 0.8, 0.65]];
    node literal gains matrix [[1.0, 0.9, 0.8, 0.7]];
    node literal label string "Intro";
"""

from __future__ import annotations

import ast
import time
from typing import TYPE_CHECKING, Any, Literal as TypingLiteral

import numpy as np
from pydantic import Field

from rasl.engine.nodes import BaseNode
from rasl.engine.frames import (
    ColorPayload,
    Frame,
    FramePayload,
    MatrixPayload,
)
from rasl.engine.ports import OutputPortSpec, PortGroup
from rasl.engine.registry import node
from rasl.nodes.models import SourceNodeConfig

if TYPE_CHECKING:
    from rasl.engine.tick import TickContext


def parse_literal(literal_str: str) -> Any:
    """Parse a literal string into a Python value.
    
    Supports:
    - Numbers: 1, 1.5, -0.3
    - Strings: "hello", 'world'
    - Lists/nested lists: [1, 2, 3], [[1, 0, 0], [0.5, 0, 0]]
    - Booleans: true, false, True, False
    - None/null: none, null, None
    
    Args:
        literal_str: String representation of the literal.
        
    Returns:
        Parsed Python value.
        
    Raises:
        ValueError: If the literal cannot be parsed.
    """
    # Normalize common variants
    normalized = literal_str.strip()
    
    # Handle boolean/null variants
    lower = normalized.lower()
    if lower in ("true", "on", "yes"):
        return True
    if lower in ("false", "off", "no"):
        return False
    if lower in ("none", "null"):
        return None
    
    # Try ast.literal_eval for safe parsing of Python literals
    try:
        return ast.literal_eval(normalized)
    except (ValueError, SyntaxError) as e:
        raise ValueError(f"Cannot parse literal: {literal_str!r}") from e


def build_payload(kind: str, subtype: str | None, value: Any) -> FramePayload:
    """Build a payload from parsed literal value.
    
    Delegates to existing payload constructors based on kind.
    
    Args:
        kind: Payload family (color, matrix, etc.)
        subtype: Optional subtype (hsl, oklch, etc.)
        value: Parsed literal value
        
    Returns:
        Constructed FramePayload instance.
        
    Raises:
        ValueError: If kind is unknown or value is incompatible.
    """
    if kind == "color":
        # Do not reshape here. We pass the literal through as-is.
        #
        # For nested lists like [[h,s,l], ...], np.asarray yields shape (N, 3).
        # rasl.nodes.color.convert.convert() expects (N, 3) (or flat N*3), so
        # this layout is important.
        arr = np.asarray(value, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        model = subtype or "srgb"
        return ColorPayload(arr, model=model)
    
    elif kind == "matrix":
        # Matrix payload - pass through as-is
        arr = np.asarray(value, dtype=np.float32)
        return MatrixPayload(arr)
    
    else:
        raise ValueError(f"Unknown literal payload kind: {kind!r}")


@node("LiteralNode", "Literal", "literal")
class LiteralNode(BaseNode):
    """Source node that outputs a constant literal payload.
    
    LiteralNode parses a literal value from config and wraps it in
    the appropriate payload type. The payload is computed once at
    construction and returned unchanged on every pull.
    
    Example config:
        rasl {
            node literal static_hsl color:hsl [[1, 0, 0], [0.5, 0, 0]];
            node literal gains matrix [[1.0, 0.9, 0.8]];
        }
    """
    
    class Config(SourceNodeConfig):
        """Configuration for LiteralNode."""
        
        kind: TypingLiteral["source"] = "source"
        payload_kind: str = Field(..., description="Payload type (color, matrix, etc.)")
        payload_subtype: str | None = Field(None, description="Payload subtype (hsl, oklch, etc.)")
        literal_value: str = Field(..., description="Literal value as string")
    
    outputs = PortGroup.outputs(out=OutputPortSpec(MatrixPayload))
    
    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._config = config
        
        # Parse the literal string into a Python value
        try:
            parsed_value = parse_literal(config.literal_value)
        except ValueError as e:
            raise ValueError(f"Invalid literal in node '{config.id}': {e}") from e
        
        # Build the payload using the appropriate constructor
        try:
            self._payload = build_payload(
                config.payload_kind,
                config.payload_subtype,
                parsed_value,
            )
        except (ValueError, TypeError) as e:
            raise ValueError(
                f"Cannot create {config.payload_kind} payload in node '{config.id}': {e}"
            ) from e
        
        self._topic = f"literal.{self.id}"
    
    async def pull(self, tick: "TickContext") -> None:
        """Output the constant payload."""
        frame = Frame(
            topic=self._topic,
            timestamp=time.monotonic(),
            payload=self._payload,
            metadata=dict(self._metadata),
        )
        self.outputs.out.write(frame)
