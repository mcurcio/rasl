"""Range mapping transform node."""

from __future__ import annotations

from typing import Tuple

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


@node("RangeMapNode", "RangeMap")
class RangeMapNode(BaseNode):
    """Transform node that remaps each channel to a configured range."""

    class Config(TransformNodeConfig):
        """Configuration for RangeMapNode."""

        ranges: Tuple[Tuple[float, float], ...] = Field(
            ...,
            min_length=1,
            description="Per-channel [min, max] source ranges",
        )
        clamp: bool = Field(
            True,
            description="Clamp inputs to the configured range before remapping",
        )

        @field_validator("ranges")
        @classmethod
        def validate_ranges(cls, value: Tuple[Tuple[float, float], ...]) -> Tuple[Tuple[float, float], ...]:
            normalized: list[Tuple[float, float]] = []
            for idx, pair in enumerate(value):
                if len(pair) != 2:
                    raise ValueError(f"ranges[{idx}] must contain exactly two values")
                low, high = float(pair[0]), float(pair[1])
                if high <= low:
                    raise ValueError(f"ranges[{idx}] max ({high}) must be greater than min ({low})")
                normalized.append((low, high))
            return tuple(normalized)

    inputs = PortGroup.inputs(
        input=InputPortSpec((MatrixPayload, ColorPayload)),
    )
    outputs = PortGroup.outputs(out=OutputPortSpec(MatrixPayload))

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        range_array = np.asarray(config.ranges, dtype=np.float32)
        self._mins = range_array[:, 0]
        self._maxs = range_array[:, 1]
        self._spans = self._maxs - self._mins
        self._clamp = config.clamp
        self._channel_count = len(config.ranges)

    async def pull(self, tick: TickContext) -> None:
        frame = self.inputs.input.read()
        if frame is None:
            return

        payload = frame.payload
        data = self._extract_data(payload)
        remapped = self._apply_ranges(data)
        new_payload = clone_payload_like(payload, remapped)
        self.outputs.out.write(frame.with_payload(new_payload))

    def _extract_data(self, payload: MatrixPayload) -> NDArray[np.float32]:
        data = np.asarray(payload.data, dtype=np.float32)
        if data.ndim != 2:
            raise ValueError(f"Expected 2D payload data, got shape {data.shape!r}")
        if data.shape[1] != self._channel_count:
            raise ValueError(
                f"Configured {self._channel_count} ranges "
                f"but payload has {data.shape[1]} channels"
            )
        return data

    def _apply_ranges(self, data: NDArray[np.float32]) -> NDArray[np.float32]:
        arr = data.copy()
        if self._clamp:
            arr = np.minimum(np.maximum(arr, self._mins), self._maxs)
        arr -= self._mins
        arr /= self._spans
        return arr.astype(np.float32, copy=False)
