"""Sink node that streams ColorPayloads to a Govee light via LAN TCP."""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np
from pydantic import Field, field_validator

from rasl.config.units import parse_interval
from rasl.engine.frames import (
    ColorPayload,
    MatrixPayload,
    RgbColorPayload,
    RgbwColorPayload,
)
from rasl.engine.nodes import BaseNode, NodeContext
from rasl.engine.ports import InputPortSpec, PortGroup
from rasl.engine.registry import node
from rasl.engine.tick import TickContext, pull_rate
from rasl.nodes.models import SinkNodeConfig

from .client import (
    DEFAULT_GOVEE_PORT,
    GoveeDeviceInfo,
    GoveeLightClient,
    GoveeSegmentInfo,
)


@node("GoveeLightNode", "GoveeLight")
class GoveeLightNode(BaseNode):
    """Pull-driven sink that sends RGB/RGBW segment colors to a Govee light."""

    class Config(SinkNodeConfig):
        host: str = Field(..., description="Target Govee device IPv4/hostname")
        port: int = Field(
            DEFAULT_GOVEE_PORT,
            ge=1,
            le=65535,
            description="Govee LAN TCP port (default 4003)",
        )
        fps: str = Field("20hz", description="Pull rate (e.g. '30hz', '33ms')")
        input_port: str = Field("light", description="Input ColorPayload port name")
        segment_channels: int | None = Field(
            None,
            ge=3,
            le=4,
            description="Override discovered channel count (3=RGB, 4=RGBW)",
        )

        _interval_s: float = 0.05

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
        self._host = config.host
        self._port = config.port
        self._input_port = config.input_port
        self._interval_s = config.get_interval_s()
        self._fps = 1.0 / self._interval_s
        self._segment_channels_override = config.segment_channels

        self.inputs = PortGroup.inputs(
            **{self._input_port: InputPortSpec(ColorPayload)}
        )

        self._client: GoveeLightClient | None = None
        self._ctx: NodeContext | None = None

        self._device_info: GoveeDeviceInfo | None = None
        self._segments: list[GoveeSegmentInfo] = []
        self._segment_count: int | None = None
        self._channels_per_segment: int = (
            self._segment_channels_override or 3
        )

        self._frames_sent = 0
        self._frames_dropped = 0

    async def start(self, ctx: NodeContext) -> None:
        self._ctx = ctx
        self._client = GoveeLightClient(self._host, self._port)
        info: GoveeDeviceInfo | None = None
        try:
            info = self._client.discover()
        except Exception as exc:  # pragma: no cover - defensive logging
            ctx.logger.warning(
                event="govee_discovery_failed",
                host=self._host,
                port=self._port,
                error=str(exc),
            )

        if info is not None:
            self._device_info = info
            if info.segments:
                self._segments = info.segments
                self._segment_count = len(info.segments)
            detected_channels = int(info.channels_per_segment)
            if self._segment_channels_override:
                self._channels_per_segment = int(self._segment_channels_override)
            else:
                self._channels_per_segment = detected_channels

        if self._channels_per_segment not in (3, 4):
            ctx.logger.warning(
                event="govee_invalid_channel_count",
                host=self._host,
                override=self._segment_channels_override,
                detected=getattr(info, "channels_per_segment", None),
            )
            self._channels_per_segment = 3

        ctx.logger.info(
            event="govee_node_started",
            host=self._host,
            port=self._port,
            fps=round(self._fps, 4),
            segments=self._segment_count,
            channels_per_segment=self._channels_per_segment,
        )

    async def stop(self, ctx: NodeContext) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

        ctx.logger.info(
            event="govee_node_stopped",
            host=self._host,
            frames_sent=self._frames_sent,
            frames_dropped=self._frames_dropped,
        )

    @pull_rate(lambda self: self._fps)
    async def pull(self, tick: TickContext) -> None:
        if self._client is None:
            return

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

        target_cls = (
            RgbwColorPayload if self._channels_per_segment == 4 else RgbColorPayload
        )
        if not isinstance(payload, target_cls):
            try:
                payload = payload.to_model(target_cls)
            except Exception as exc:
                self._frames_dropped += 1
                if self._ctx:
                    self._ctx.logger.error(
                        event="govee_convert_failed",
                        error=str(exc),
                        source_model=getattr(payload, "model", None),
                        target_model=target_cls.model_name,
                    )
                return

        byte_matrix = self._quantize_payload(payload, target_cls.components)
        if byte_matrix is None:
            self._frames_dropped += 1
            return

        count = byte_matrix.shape[0]
        if self._segment_count is not None and count != self._segment_count:
            self._frames_dropped += 1
            if self._ctx:
                self._ctx.logger.warning(
                    event="govee_segment_mismatch",
                    expected=self._segment_count,
                    received=count,
                )
            return

        if self._segment_count is None:
            self._segment_count = count
            if not self._segments:
                self._segments = [
                    GoveeSegmentInfo(segment_id=index) for index in range(count)
                ]

        segment_ids = self._resolve_segment_ids(count)
        if segment_ids is None:
            self._frames_dropped += 1
            return

        segment_payload = self._build_segment_payload(byte_matrix, segment_ids)
        top_color = self._row_to_color(byte_matrix[0])

        try:
            self._client.send_color_command(color=top_color, segments=segment_payload)
        except Exception as exc:
            self._frames_dropped += 1
            if self._ctx:
                self._ctx.logger.error(
                    event="govee_send_failed",
                    error=str(exc),
                    host=self._host,
                    last_error=str(self._client.last_error) if self._client else None,
                )
            return

        self._frames_sent += 1

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
                if self._ctx:
                    self._ctx.logger.error(
                        event="govee_matrix_convert_failed",
                        error=str(exc),
                        payload_shape=tuple(arr.shape),
                    )
                return None

        if self._ctx:
            self._ctx.logger.error(
                event="govee_invalid_payload",
                reason="unsupported_type",
                payload_type=type(payload).__name__,
            )
        return None

    def _quantize_payload(
        self,
        payload: ColorPayload,
        components: int,
    ) -> np.ndarray | None:
        arr = np.asarray(payload, dtype=np.float32)
        if arr.ndim != 2 or arr.shape[1] != components:
            if self._ctx:
                self._ctx.logger.error(
                    event="govee_channel_mismatch",
                    expected_components=components,
                    observed_shape=tuple(arr.shape),
                )
            return None
        clipped = np.clip(arr, 0.0, 1.0)
        return (clipped * 255.0 + 0.5).astype(np.uint8)

    def _resolve_segment_ids(self, count: int) -> list[int] | None:
        if self._segments and len(self._segments) == count:
            return [seg.segment_id for seg in self._segments]
        if self._segments and len(self._segments) != count:
            if self._ctx:
                self._ctx.logger.warning(
                    event="govee_segment_count_changed",
                    discovered=len(self._segments),
                    received=count,
                )
            return None
        return list(range(count))

    def _build_segment_payload(
        self,
        matrix: np.ndarray,
        segment_ids: Iterable[int],
    ) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for idx, (segment_id, row) in enumerate(zip(segment_ids, matrix)):
            color = self._row_to_color(row)
            payloads.append({"segmentId": int(segment_id), **color})
        return payloads

    def _row_to_color(self, row: np.ndarray) -> dict[str, int]:
        color = {
            "r": int(row[0]),
            "g": int(row[1]),
            "b": int(row[2]),
        }
        if row.size >= 4:
            color["w"] = int(row[3])
        return color
