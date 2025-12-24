"""Random channel mapping transform node."""

from __future__ import annotations

from typing import Optional

import numpy as np
from numpy.typing import NDArray
from pydantic import Field

from rasl.engine.frames import ColorPayload, MatrixPayload
from rasl.engine.nodes import BaseNode
from rasl.engine.ports import InputPortSpec, OutputPortSpec, PortGroup
from rasl.engine.registry import node
from rasl.engine.tick import TickContext
from rasl.nodes.models import TransformNodeConfig

from .._payload_utils import clone_payload_like


@node("RandomMapNode", "RandomMap")
class RandomMapNode(BaseNode):
    """Transform node that randomly maps input channels to output channels."""

    class Config(TransformNodeConfig):
        """Configuration for RandomMapNode."""

        channel_count: int | None = Field(
            None,
            ge=1,
            description="Number of output channels/elements; defaults to input count.",
        )
        seed: int | None = Field(
            None,
            description="Optional random seed for deterministic mappings.",
        )

    inputs = PortGroup.inputs(
        input=InputPortSpec((MatrixPayload, ColorPayload)),
    )
    outputs = PortGroup.outputs(out=OutputPortSpec(MatrixPayload))

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._channel_override = config.channel_count
        self._input_count: Optional[int] = None
        self._output_count: Optional[int] = config.channel_count
        self._mapping: NDArray[np.int64] | None = None
        self._rng = np.random.default_rng(config.seed)

    async def pull(self, tick: TickContext) -> None:
        frame = self.inputs.input.read()
        if frame is None:
            return

        payload = frame.payload
        data = np.asarray(payload.data, dtype=np.float32)
        if data.ndim != 2:
            raise ValueError(f"Expected 2D payload data, got shape {data.shape!r}")

        input_count = data.shape[0]
        if input_count <= 0:
            raise ValueError("RandomMap requires payloads with at least one element")

        self._validate_input_count(input_count)
        self._ensure_mapping(input_count)
        assert self._mapping is not None  # For type checkers

        mapped = data[self._mapping, :]
        # Always output MatrixPayload for consistent downstream handling
        new_payload = MatrixPayload(mapped)
        self.outputs.out.write(frame.with_payload(new_payload))

    def _validate_input_count(self, input_count: int) -> None:
        if self._input_count is None:
            self._input_count = input_count
            return
        if input_count != self._input_count:
            raise ValueError(
                f"RandomMap input channel count changed from {self._input_count} to {input_count}"
            )

    def _ensure_mapping(self, input_count: int) -> None:
        if self._mapping is not None:
            return

        output_count = self._channel_override or input_count
        if output_count <= 0:
            raise ValueError("RandomMap channel_count must be positive")
        if input_count <= 0:
            raise ValueError("RandomMap requires at least one input channel")

        self._output_count = output_count
        self._mapping = self._rng.integers(
            0,
            input_count,
            size=output_count,
            endpoint=False,
            dtype=np.int64,
        )
