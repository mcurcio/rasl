"""LIFX sink node that streams ColorPayloads to discovered bulbs."""

from __future__ import annotations

import time
from typing import Any, ClassVar

import numpy as np
from pydantic import Field, field_validator

from rasl.config.units import parse_interval
from rasl.engine.frames import ColorPayload, HsbkColorPayload, MatrixPayload, RgbColorPayload
from rasl.engine.nodes import BaseNode, NodeContext
from rasl.engine.ports import InputPortSpec, PortGroup
from rasl.engine.registry import node
from rasl.engine.tick import TickContext, pull_rate
from rasl.nodes.models import SinkNodeConfig

from .client import LifxEndpoint, LifxLanClient, parse_target_list

_UINT16_MAX = 0xFFFF
_MIN_KELVIN = 1500.0
_MAX_KELVIN = 9000.0
_KELVIN_RANGE = _MAX_KELVIN - _MIN_KELVIN


@node("LifxSinkNode", "LifxSink")
class LifxSinkNode(BaseNode):
    """Pull-driven sink that emits HSBK frames to a LIFX IP or group target."""

    class Config(SinkNodeConfig):
        arg_fields: ClassVar[list[str]] = ["target"]

        target: str = Field(
            ...,
            description="Comma separated LIFX IP targets (optionally 'mac@ip:port')",
        )
        fps: str = Field("30hz", description="Pull rate (e.g. '30hz', '33ms')")
        duration_ms: float = Field(
            0.0,
            ge=0.0,
            le=60000.0,
            description="Per-command fade duration in milliseconds",
        )
        rapid: bool = Field(
            False,
            description="Set rapid flag to bypass reliability/ack overhead",
        )
        log_unresolved_interval_s: float = Field(
            5.0,
            ge=0.5,
            description="Throttle interval for unresolved-target warnings",
        )

        @field_validator("fps")
        @classmethod
        def _validate_fps(cls, value: str) -> str:
            interval = parse_interval(value)
            if interval <= 0:
                raise ValueError("fps must be positive")
            return value

        def get_interval_s(self) -> float:
            return parse_interval(self.fps)

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._config = config
        self._input_port = "color"

        self.inputs = PortGroup.inputs(
            color=InputPortSpec(ColorPayload)
        )

        self._interval_s = config.get_interval_s()
        self._fps = 1.0 / self._interval_s if self._interval_s > 0 else 30.0

        self._duration_ms = float(config.duration_ms)
        self._rapid = bool(config.rapid)
        self._log_interval = float(config.log_unresolved_interval_s)

        self._ctx: NodeContext | None = None

        self._endpoints = parse_target_list(config.target)
        if not self._endpoints:
            raise ValueError("target must include at least one IP address")
        self._clients: list[LifxLanClient] = []

        self._frames_sent = 0
        self._frames_dropped = 0
        self._last_unresolved_log = 0.0

    async def start(self, ctx: NodeContext) -> None:
        self._ctx = ctx
        self._clients = []
        failures = 0
        for endpoint in self._endpoints:
            client = LifxLanClient(endpoint)
            try:
                await client.start()
            except Exception as exc:  # pragma: no cover - network failures
                failures += 1
                ctx.logger.error(
                    event="lifx_client_start_failed",
                    target=endpoint.ip,
                    port=endpoint.port,
                    error=str(exc),
                )
                continue
            self._clients.append(client)

        ctx.logger.info(
            event="lifx_sink_started",
            targets=len(self._clients),
            failed=failures,
            fps=round(self._fps, 3),
        )

    async def stop(self, ctx: NodeContext) -> None:
        for client in self._clients:
            client.stop()
        self._clients.clear()
        ctx.logger.info(
            event="lifx_sink_stopped",
            frames_sent=self._frames_sent,
            frames_dropped=self._frames_dropped,
        )
        self._ctx = None

    @pull_rate(lambda self: self._fps)
    async def pull(self, tick: TickContext) -> None:
        port = self.inputs.get(self._input_port)
        if port is None:
            return

        frame = port.read()
        if frame is None:
            return

        payload = self._coerce_color_payload(frame.payload)
        if payload is None:
            self._frames_dropped += 1
            return

        # Debug: log payload shape before conversion
        payload_data = np.asarray(payload, dtype=np.float32)
        if self._ctx and payload_data.shape[0] <= 0:
            self._ctx.logger.debug(
                event="lifx_payload_shape",
                shape=tuple(payload_data.shape),
                model=getattr(payload, "model", None),
            )

        try:
            hsbk = (
                payload
                if isinstance(payload, HsbkColorPayload)
                else payload.to_model(HsbkColorPayload)
            )
        except Exception as exc:
            self._frames_dropped += 1
            if self._ctx:
                self._ctx.logger.error(
                    event="lifx_hsbk_convert_failed",
                    source_model=getattr(payload, "model", None),
                    payload_shape=tuple(payload_data.shape),
                    error=str(exc),
                )
            return

        matrix = np.asarray(hsbk, dtype=np.float32)
        if matrix.ndim == 1:
            matrix = matrix.reshape(1, -1)
        if matrix.shape[-1] != 4:
            self._frames_dropped += 1
            self._log_channel_mismatch(matrix.shape)
            return

        clients = self._clients
        if not clients:
            self._frames_dropped += 1
            self._maybe_log_unresolved()
            return

        assignments = self._build_assignments(matrix, clients)
        if not assignments:
            self._frames_dropped += 1
            return

        sent_any = False
        for client, row_matrix in assignments:
            # row_matrix is shape (1, 4) - extract first row
            row = row_matrix[0] if row_matrix.ndim > 1 else row_matrix
            color = self._row_to_lifx_color(row)
            if color is None:
                continue
            hue, sat, bri, kelvin = color
            try:
                client.send_set_color(
                    hue=hue,
                    saturation=sat,
                    brightness=bri,
                    kelvin=kelvin,
                    duration_ms=int(round(self._duration_ms)),
                    rapid=self._rapid,
                )
                sent_any = True
            except Exception as exc:
                self._log_send_error(client, exc)

        if sent_any:
            self._frames_sent += 1
        else:
            self._frames_dropped += 1

    def _build_assignments(
        self,
        matrix: np.ndarray,
        clients: list[LifxLanClient],
    ) -> list[tuple[LifxLanClient, np.ndarray]]:
        rows = matrix.shape[0]
        count = len(clients)

        if rows == 0 or count == 0:
            return []

        if rows == count:
            return list(zip(clients, matrix))

        if rows == 1:
            return [(client, matrix[0:1]) for client in clients]

        if count == 1:
            return [(clients[0], matrix[0:1])]

        if self._ctx:
            self._ctx.logger.warning(
                event="lifx_payload_light_mismatch",
                rows=rows,
                targets=count,
            )
        return []

    def _row_to_lifx_color(self, row: np.ndarray) -> tuple[int, int, int, int] | None:
        if row.size < 4:
            if self._ctx:
                self._ctx.logger.error(
                    event="lifx_row_too_short",
                    size=int(row.size),
                )
            return None

        clipped = np.clip(row[:4], 0.0, 1.0)
        hue = int(round(clipped[0] * _UINT16_MAX)) % (_UINT16_MAX + 1)
        sat = int(round(clipped[1] * _UINT16_MAX))
        bri = int(round(clipped[2] * _UINT16_MAX))
        kelvin = int(round(clipped[3] * _KELVIN_RANGE + _MIN_KELVIN))
        kelvin = int(min(max(kelvin, _MIN_KELVIN), _MAX_KELVIN))
        return hue, sat, bri, kelvin

    def _maybe_log_unresolved(self) -> None:
        now = time.monotonic()
        if (now - self._last_unresolved_log) < self._log_interval:
            return
        self._last_unresolved_log = now
        if self._ctx:
            self._ctx.logger.warning(
                event="lifx_target_unresolved",
                configured=len(self._endpoints),
                active=len(self._clients),
            )

    def _coerce_color_payload(self, payload: Any) -> ColorPayload | None:
        if isinstance(payload, ColorPayload):
            return payload

        if isinstance(payload, MatrixPayload):
            arr = np.asarray(payload, dtype=np.float32)
            if arr.ndim == 1:
                arr = arr.reshape(-1, int(arr.size))
            try:
                return RgbColorPayload(arr)
            except Exception as exc:
                self._log_invalid_payload(
                    payload,
                    reason="matrix_convert_failed",
                    error=str(exc),
                    shape=tuple(arr.shape),
                )
                return None

        self._log_invalid_payload(payload, reason="unsupported_type")
        return None

    def _log_invalid_payload(self, payload: Any, **extra: Any) -> None:
        if self._ctx:
            self._ctx.logger.error(
                event="lifx_invalid_payload",
                payload_type=type(payload).__name__,
                **extra,
            )

    def _log_conversion_error(self, payload: ColorPayload, exc: Exception) -> None:
        if self._ctx:
            self._ctx.logger.error(
                event="lifx_hsbk_convert_failed",
                source_model=getattr(payload, "model", None),
                error=str(exc),
            )

    def _log_channel_mismatch(self, shape: tuple[int, ...]) -> None:
        if self._ctx:
            self._ctx.logger.error(
                event="lifx_channel_mismatch",
                shape=shape,
            )

    def _log_send_error(self, client: LifxLanClient, exc: Exception) -> None:
        if self._ctx:
            self._ctx.logger.error(
                event="lifx_send_failed",
                **client.describe(),
                error=str(exc),
            )


__all__ = ["LifxSinkNode"]
