"""Element-wise math operations transform node.

This module provides MathNode, which performs element-wise mathematical
operations between two input arrays or between an input and a constant.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import Field

from rasl.graph.node import BaseNode, TickContext, TransformNodeConfig, node
from rasl.graph.ports import InputPortSpec, OutputPortSpec, PortGroup
from rasl.signal import MatrixPayload

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

    inputs = PortGroup.inputs(
        a=InputPortSpec(MatrixPayload),
        b=InputPortSpec(MatrixPayload),
    )
    outputs = PortGroup.outputs(out=OutputPortSpec(MatrixPayload))

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._operation = config.operation
        self._constant_a = config.constant_a
        self._constant_b = config.constant_b
        self._mix = config.mix
        self._clamp = config.clamp

    async def pull(self, tick: TickContext) -> None:
        """Combine the two inputs element by element and write the result."""
        frame_a = self.inputs.a.read()
        frame_b = self.inputs.b.read()
        a = None if frame_a is None else np.asarray(frame_a.payload, dtype=np.float32)
        b = None if frame_b is None else np.asarray(frame_b.payload, dtype=np.float32)

        # A constant stands in for an input that is not there, at the other's shape
        if a is None and self._constant_a is not None and b is not None:
            a = np.full_like(b, self._constant_a)
        if b is None and self._constant_b is not None and a is not None:
            b = np.full_like(a, self._constant_b)

        # Need at least one real input
        if a is None and b is None:
            return

        # If only one input, use it as both (for unary-like operations)
        if a is None:
            a = b
        if b is None:
            b = a
        assert a is not None and b is not None

        a, b = self._align(a, b)
        result = self._apply_operation(a, b)

        if self._clamp:
            result = np.clip(result, 0.0, 1.0)

        frame = frame_a if frame_a is not None else frame_b
        assert frame is not None
        self.outputs.out.write(frame.with_payload(MatrixPayload(result.astype(np.float32, copy=False))))

    @staticmethod
    def _align(
        a: NDArray[np.float32], b: NDArray[np.float32]
    ) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
        """Bring two inputs to one shape.

        Equal shapes are used as they are. Shapes numpy can broadcast (one
        column against several, one row against many) are broadcast. Otherwise
        the smaller input is repeated to fill the larger one's shape.
        """
        if a.shape == b.shape:
            return a, b
        try:
            broadcast_a, broadcast_b = np.broadcast_arrays(a, b)
            return broadcast_a, broadcast_b
        except ValueError:
            if a.size < b.size:
                return np.resize(a, b.shape), b
            return a, np.resize(b, a.shape)

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
