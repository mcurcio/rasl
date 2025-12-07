"""Element-wise math operations transform node.

This module provides MathNode, which performs element-wise mathematical
operations between two input arrays or between an input and a constant.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import Field

from rasl.config.models import TransformNodeConfig
from rasl.engine.base_node import BaseNode
from rasl.engine.frame import ArrayPayload, Frame
from rasl.engine.node import NodeContext
from rasl.engine.ports import PortGroup, PortSpec
from rasl.engine.registry import node


Operation = Literal["multiply", "add", "subtract", "min", "max", "screen", "lerp"]


@node("MathNode", "Math")
class MathNode(BaseNode):
    """Transform node for element-wise math operations.

    Combines two inputs (a and b) using a configurable operation.
    If only one input is connected, the other can use a constant value.

    Operations:
        - multiply: a * b
        - add: a + b
        - subtract: a - b
        - min: min(a, b)
        - max: max(a, b)
        - screen: 1 - (1-a) * (1-b)  (additive blend)
        - lerp: a + (b - a) * mix  (linear interpolation)

    Example config:
        rasl {
            node Math apply_brightness {
                operation multiply;
                connect base_color a;
                connect brightness b;
            }

            node Math add_offset {
                operation add;
                constant_b 0.1;
                connect input a;
            }
        }
    """

    class Config(TransformNodeConfig):
        """Configuration for MathNode."""

        operation: Operation = Field("multiply", description="Math operation to perform")
        constant_a: float | None = Field(None, description="Constant value for input a if not connected")
        constant_b: float | None = Field(None, description="Constant value for input b if not connected")
        mix: float = Field(0.5, ge=0.0, le=1.0, description="Mix factor for lerp operation")
        clamp: bool = Field(True, description="Clamp output to [0, 1]")

    inputs = PortGroup(
        a=PortSpec(accepts="array"),
        b=PortSpec(accepts="array"),
    )
    outputs = PortGroup(out=PortSpec(accepts="array"))

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._operation = config.operation
        self._constant_a = config.constant_a
        self._constant_b = config.constant_b
        self._mix = config.mix
        self._clamp = config.clamp

        # Buffers for inputs
        self._buffer_a: NDArray[np.float32] | None = None
        self._buffer_b: NDArray[np.float32] | None = None

    async def start(self, ctx: NodeContext) -> None:
        pass

    async def handle(self, port: str, frame: Frame, ctx: NodeContext) -> None:
        data = np.asarray(frame.payload, dtype=np.float32)

        if port == "a":
            self._buffer_a = data
        elif port == "b":
            self._buffer_b = data
        else:
            return

        await self._compute_and_emit(frame, ctx)

    async def _compute_and_emit(self, frame: Frame, ctx: NodeContext) -> None:
        # Get input arrays, using constants if not connected
        a = self._buffer_a
        b = self._buffer_b

        if a is None and self._constant_a is not None:
            # Use constant, but we need a length reference
            if b is not None:
                a = np.full(len(b), self._constant_a, dtype=np.float32)
        if b is None and self._constant_b is not None:
            if a is not None:
                b = np.full(len(a), self._constant_b, dtype=np.float32)

        # Need at least one real input
        if a is None and b is None:
            return

        # If only one input, use it as both (for unary-like operations)
        if a is None:
            a = b
        if b is None:
            b = a

        assert a is not None and b is not None

        # Ensure same length (broadcast shorter to longer)
        if len(a) != len(b):
            max_len = max(len(a), len(b))
            if len(a) < max_len:
                a = np.resize(a, max_len)
            if len(b) < max_len:
                b = np.resize(b, max_len)

        # Perform operation
        result = self._apply_operation(a, b)

        if self._clamp:
            result = np.clip(result, 0.0, 1.0)

        await ctx.emit("out", frame.with_payload(ArrayPayload(result)))

    def _apply_operation(
        self, a: NDArray[np.float32], b: NDArray[np.float32]
    ) -> NDArray[np.float32]:
        """Apply the configured operation."""
        op = self._operation

        if op == "multiply":
            return a * b
        elif op == "add":
            return a + b
        elif op == "subtract":
            return a - b
        elif op == "min":
            return np.minimum(a, b)
        elif op == "max":
            return np.maximum(a, b)
        elif op == "screen":
            # Screen blend: 1 - (1-a) * (1-b)
            return 1.0 - (1.0 - a) * (1.0 - b)
        elif op == "lerp":
            # Linear interpolation: a + (b - a) * mix
            return a + (b - a) * self._mix
        else:
            # Default to multiply
            return a * b

    async def stop(self, ctx: NodeContext) -> None:
        pass
