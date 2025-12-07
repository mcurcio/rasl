"""Compose transform node for interleaving multiple inputs.

This module provides ComposeNode, which combines multiple input ports
into a single interleaved output. Useful for constructing multi-component
data like HSL color from separate H, S, L sources.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
from numpy.typing import NDArray
from pydantic import Field, field_validator

from rasl.config.models import TransformNodeConfig
from rasl.engine.base_node import BaseNode
from rasl.engine.frame import ArrayPayload, ColorPayload, Frame, HslColorPayload, RgbColorPayload
from rasl.engine.graph import Edge
from rasl.engine.node import NodeContext
from rasl.engine.ports import PortGroup, PortSpec
from rasl.engine.registry import node


@node("ComposeNode", "Compose")
class ComposeNode(BaseNode):
    """Composes multiple inputs into interleaved output.

    Ports are variable-length and resolve from connected sources.
    Unconnected ports must have a fill value.

    Output interleave order matches port declaration order.
    Output length = input_length × number_of_ports.

    Example config:
        node Compose sine_to_hsl {
            ports {
                hue;
                saturation;
                lightness;
            }
            connect sine hue;
            fill saturation 1;
            fill lightness 0.5;
        }
    """

    class Config(TransformNodeConfig):
        """Configuration for ComposeNode."""

        ports: list[str] = Field(
            ...,
            min_length=1,
            description="Input port names in interleave order",
        )
        fill: dict[str, float] = Field(
            default_factory=dict,
            description="Constant values for unconnected ports",
        )
        output_type: str = Field(
            default="array",
            description="Output payload type: 'array', 'hsl', or 'rgb'",
        )

        @field_validator("ports", mode="before")
        @classmethod
        def normalize_ports(cls, v: dict | list) -> list[str]:
            """Handle dict form from nested config block."""
            if isinstance(v, dict):
                # From nested block: {hue: True, saturation: True, ...}
                return list(v.keys())
            return v

        @field_validator("fill", mode="before")
        @classmethod
        def normalize_fill(cls, v: list | dict | None) -> dict[str, float]:
            """Convert list-of-pairs to dict."""
            if v is None:
                return {}
            if isinstance(v, dict):
                return v
            if isinstance(v, list):
                if not v:
                    return {}
                # Check if it's a list-of-lists (multiple fill directives)
                if isinstance(v[0], list):
                    return {pair[0]: float(pair[1]) for pair in v}
                # Single fill directive: ["port_name", value]
                if len(v) == 2 and isinstance(v[0], str):
                    return {v[0]: float(v[1])}
            return {}

    # Class-level defaults (overridden per-instance)
    inputs = PortGroup()
    outputs = PortGroup(out=PortSpec(accepts="array"))

    def __init__(self, config: Config) -> None:
        super().__init__(config)

        self._port_names = config.ports
        self._fills = config.fill
        self._num_ports = len(self._port_names)
        self._output_type = config.output_type

        # All ports are variable-length
        self.inputs = PortGroup(
            **{name: PortSpec(accepts="array", channels=None) for name in self._port_names}
        )

        # Runtime state
        self._buffers: dict[str, NDArray[np.float32] | None] = {
            name: None for name in self._port_names
        }
        self._resolved_length: int | None = None

    def validate_connections(self, incoming_edges: Sequence[Edge]) -> None:
        """Ensure all non-fill ports have connections."""
        connected_ports = {e.target_port for e in incoming_edges}

        for port_name in self._port_names:
            has_fill = port_name in self._fills
            has_connection = port_name in connected_ports

            if not has_fill and not has_connection:
                raise ValueError(
                    f"Port '{port_name}' has no connection and no fill value"
                )

    async def start(self, ctx: NodeContext) -> None:
        pass

    async def handle(self, port: str, frame: Frame, ctx: NodeContext) -> None:
        if port not in self._port_names:
            return

        data = np.asarray(frame.payload, dtype=np.float32)
        self._buffers[port] = data

        # Resolve length from first connected input
        if self._resolved_length is None:
            self._resolved_length = len(data)

        await self._emit_composed(frame, ctx)

    async def _emit_composed(self, frame: Frame, ctx: NodeContext) -> None:
        length = self._resolved_length
        if length is None:
            return

        out = np.zeros(length * self._num_ports, dtype=np.float32)

        for i, name in enumerate(self._port_names):
            if name in self._fills:
                # Constant fill value
                out[i :: self._num_ports] = self._fills[name]
            elif self._buffers[name] is not None:
                # Connected data
                buf = self._buffers[name]
                assert buf is not None  # for type checker
                copy_len = min(len(buf), length)
                out[i :: self._num_ports][:copy_len] = buf[:copy_len]
            # else: leave as zeros (waiting for data)

        # Create appropriate payload type based on config
        output_type = self._output_type
        if output_type == "hsl":
            out_payload = HslColorPayload(out)
        elif output_type == "rgb":
            out_payload = RgbColorPayload(out)
        elif output_type in ("oklch", "oklab", "okhsl", "okhsv"):
            # Use generic ColorPayload with model tag for Ok* color spaces
            out_payload = ColorPayload(out, model=output_type)
        else:
            out_payload = ArrayPayload(out)

        await ctx.emit("out", frame.with_payload(out_payload))

    async def stop(self, ctx: NodeContext) -> None:
        pass
