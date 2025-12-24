"""Frame smoothing transform node."""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
from numpy.typing import NDArray
from pydantic import Field, field_validator

from rasl.engine.frames import BoolPayload, ColorPayload, MatrixPayload
from rasl.engine.nodes import BaseNode
from rasl.engine.ports import InputPortSpec, OutputPortSpec, PortGroup
from rasl.engine.registry import node
from rasl.engine.tick import TickContext
from rasl.config.units import parse_interval
from rasl.nodes.models import TransformNodeConfig

from .._payload_utils import clone_payload_like


@node("SmoothNode", "Smooth")
class SmoothNode(BaseNode):
    """Exponentially smooths incoming frames with optional slew limiting.

    The node keeps an accumulator per channel, blends new samples in with an
    exponential moving average, and emits the smoothed payload. A `reset` port
    can clear parts (or all) of the accumulator so the next frame passes
    through unchanged.
    """

    class Config(TransformNodeConfig):
        """Configuration for SmoothNode."""

        smooth_period: str = Field(
            "50ms",
            description="Human-readable response time (e.g., '50ms', '1s'); 0 disables smoothing",
        )
        max_delta: float = Field(
            0.0,
            ge=0.0,
            description="Maximum allowed per-frame change per component (0 disables)",
        )
        bypass_epsilon: float = Field(
            0.0,
            ge=0.0,
            description="If difference is below this threshold, reuse previous output",
        )

        @field_validator("smooth_period")
        @classmethod
        def _validate_smooth_period(cls, value: str) -> str:
            seconds = parse_interval(value)
            if seconds < 0:
                raise ValueError("smooth_period must be non-negative")
            return value

        def get_smooth_period_seconds(self) -> float:
            return parse_interval(self.smooth_period)

    inputs = PortGroup.inputs(
        input=InputPortSpec((MatrixPayload, ColorPayload)),
        reset=InputPortSpec(
            (BoolPayload, MatrixPayload),
            description="Optional boolean/mask to clear accumulator",
        ),
    )
    outputs = PortGroup.outputs(output=OutputPortSpec(MatrixPayload))

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._tau_seconds = config.get_smooth_period_seconds()
        self._max_delta = float(config.max_delta)
        self._bypass_epsilon = float(config.bypass_epsilon)

        self._state: NDArray[np.float32] | None = None

    async def pull(self, tick: TickContext) -> None:
        frame = self.inputs.input.read()
        if frame is None:
            return

        payload = frame.payload
        data = self._to_matrix(payload)

        state, initialized = self._ensure_state(data)

        reset_frame = self.inputs.reset.read()
        reset_mask = self._extract_reset_mask(reset_frame, data.size)
        reset_applied = False
        if reset_mask is not None:
            mask = reset_mask.reshape(data.shape)
            np.copyto(state, data, where=mask)
            reset_applied = True

        if initialized and not reset_applied:
            output_matrix = state.copy()
        else:
            output_matrix = self._blend(state, data, tick.dt)

        new_payload = clone_payload_like(payload, output_matrix)
        self.outputs.output.write(frame.with_payload(new_payload))

    def _blend(
        self,
        state: NDArray[np.float32],
        target: NDArray[np.float32],
        dt: float,
    ) -> NDArray[np.float32]:
        delta = target - state

        if self._bypass_epsilon > 0.0:
            max_diff = float(np.max(np.abs(delta)))
            if max_diff <= self._bypass_epsilon:
                return state.copy()

        alpha = self._compute_alpha(dt)

        if alpha <= 0.0:
            return state.copy()

        if alpha < 1.0:
            delta *= alpha

        if self._max_delta > 0.0:
            np.clip(delta, -self._max_delta, self._max_delta, out=delta)

        state += delta
        return state.copy()

    def _compute_alpha(self, dt: float) -> float:
        if self._tau_seconds <= 0.0:
            return 1.0
        if dt <= 0.0:
            return 0.0
        return 1.0 - math.exp(-dt / self._tau_seconds)

    def _to_matrix(self, payload: MatrixPayload) -> NDArray[np.float32]:
        arr = np.asarray(payload, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
        elif arr.ndim != 2:
            raise ValueError(f"SmoothNode expects 1D or 2D payloads, got shape {arr.shape!r}")
        return arr

    def _ensure_state(
        self,
        data: NDArray[np.float32],
    ) -> tuple[NDArray[np.float32], bool]:
        if self._state is None or self._state.shape != data.shape:
            self._state = data.copy()
            return self._state, True
        return self._state, False

    def _extract_reset_mask(
        self,
        frame,
        length: int,
    ) -> Optional[NDArray[np.bool_]]:
        if frame is None:
            return None
        payload = frame.payload
        raw = np.asarray(payload, dtype=np.float32).reshape(-1)
        if raw.size == 0:
            return None
        if raw.size == 1:
            if raw[0] == 0.0:
                return None
            return np.ones(length, dtype=bool)

        if raw.size != length:
            raw = np.resize(raw, length)

        mask = raw != 0.0
        return mask if np.any(mask) else None
