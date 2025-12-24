"""Matrix multiplication transform node."""

from __future__ import annotations

from typing import List, Sequence, Tuple

import numpy as np
from numpy.typing import NDArray
from pydantic import Field, field_validator

from rasl.engine.frames import ColorPayload, MatrixPayload
from rasl.engine.nodes import BaseNode
from rasl.engine.ports import InputPortSpec, OutputPortSpec, PortGroup
from rasl.engine.registry import node
from rasl.engine.tick import TickContext
from rasl.nodes.models import TransformNodeConfig

from .._payload_utils import clone_payload_like


@node("MatrixMultiplyNode", "MatrixMultiply")
class MatrixMultiplyNode(BaseNode):
    """Transform node that applies a fixed matrix to every channel vector."""

    class Config(TransformNodeConfig):
        """Configuration for MatrixMultiplyNode."""

        matrix: List[List[float]] = Field(
            ...,
            min_length=1,
            description="Square transformation matrix (rows must match columns)",
        )

        @field_validator("matrix")
        @classmethod
        def validate_matrix(cls, value: Sequence[Sequence[float]]) -> List[Tuple[float, ...]]:
            size = len(value)
            if size == 0:
                raise ValueError("matrix must contain at least one row")
            normalized: list[Tuple[float, ...]] = []
            for idx, row in enumerate(value):
                if len(row) != size:
                    raise ValueError(
                        f"matrix row {idx} has {len(row)} columns, expected {size} (square matrix required)"
                    )
                normalized.append(tuple(float(v) for v in row))
            return list(normalized)

    inputs = PortGroup.inputs(
        input=InputPortSpec((MatrixPayload, ColorPayload)),
    )
    outputs = PortGroup.outputs(out=OutputPortSpec(MatrixPayload))

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._matrix = np.asarray(tuple(config.matrix), dtype=np.float32)
        self._channel_count = self._matrix.shape[0]

    async def pull(self, tick: TickContext) -> None:
        frame = self.inputs.input.read()
        if frame is None:
            return

        payload = frame.payload
        data = self._extract_data(payload)
        transformed = self._apply_matrix(data)
        new_payload = clone_payload_like(payload, transformed)
        self.outputs.out.write(frame.with_payload(new_payload))

    def _extract_data(self, payload: MatrixPayload) -> NDArray[np.float32]:
        data = np.asarray(payload.data, dtype=np.float32)
        if data.ndim != 2:
            raise ValueError(f"Expected 2D payload data, got shape {data.shape!r}")
        if data.shape[1] != self._channel_count:
            raise ValueError(
                f"Configured matrix size {self._channel_count} but payload has {data.shape[1]} channels"
            )
        return data

    def _apply_matrix(self, data: NDArray[np.float32]) -> NDArray[np.float32]:
        result = data @ self._matrix
        return result.astype(np.float32, copy=False)
