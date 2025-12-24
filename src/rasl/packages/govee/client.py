"""TCP client utilities for the Govee LAN API."""

from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable


DEFAULT_GOVEE_PORT = 4003
DEFAULT_CONNECT_TIMEOUT = 2.0
DEFAULT_READ_TIMEOUT = 2.0
DEFAULT_BASE_BACKOFF = 0.5
DEFAULT_MAX_BACKOFF = 8.0


@dataclass(slots=True)
class GoveeSegmentInfo:
    """Metadata for a single Govee lighting segment."""

    segment_id: int
    length: int | None = None


@dataclass(slots=True)
class GoveeDeviceInfo:
    """Basic information returned from ``devStatus`` discovery."""

    segments: list[GoveeSegmentInfo]
    channels_per_segment: int
    supports_white_channel: bool
    raw: dict[str, Any]


class GoveeLightClient:
    """Minimal TCP client for the Govee LAN JSON protocol."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_GOVEE_PORT,
        *,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
        base_backoff: float = DEFAULT_BASE_BACKOFF,
        max_backoff: float = DEFAULT_MAX_BACKOFF,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.host = host
        self.port = port
        self._connect_timeout = max(0.1, float(connect_timeout))
        self._read_timeout = max(0.1, float(read_timeout))
        self._base_backoff = max(0.1, float(base_backoff))
        self._max_backoff = max(self._base_backoff, float(max_backoff))
        self._time_fn = time_fn

        self._sock: socket.socket | None = None
        self._recv_buffer = bytearray()
        self._next_retry_at = 0.0
        self._backoff = self._base_backoff
        self._last_error: Exception | None = None

    @property
    def last_error(self) -> Exception | None:
        """Return the last socket error, if any."""

        return self._last_error

    def close(self) -> None:
        """Close the TCP socket."""

        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None
                self._recv_buffer.clear()

    def send_color_command(
        self,
        *,
        color: dict[str, int] | None = None,
        color_temperature: int | None = None,
        segments: Iterable[dict[str, Any]] | None = None,
    ) -> None:
        """Emit a ``colorwc`` command."""

        data: dict[str, Any] = {}
        if color:
            data["color"] = color
        if color_temperature is not None:
            data["colorTemInKelvin"] = int(color_temperature)
        if segments:
            data["segments"] = list(segments)
        if not data:
            raise ValueError("color or color_temperature must be provided")

        payload = {"msg": {"cmd": "colorwc", "data": data}}
        self._send_command(payload, expect_reply=False)

    def query_status(self) -> dict[str, Any]:
        """Send ``devStatus`` and return the parsed response."""

        payload = {"msg": {"cmd": "devStatus", "data": {}}}
        reply = self._send_command(payload, expect_reply=True)
        return reply or {}

    def discover(self) -> GoveeDeviceInfo | None:
        """Run ``devStatus`` and interpret core metadata."""

        reply = self.query_status()
        if not reply:
            return None

        data = _extract_msg_data(reply)
        segments = _parse_segments(data)
        channels = _infer_channels(data, segments)
        return GoveeDeviceInfo(
            segments=segments,
            channels_per_segment=channels,
            supports_white_channel=(channels == 4),
            raw=data,
        )

    def _send_command(
        self,
        payload: dict[str, Any],
        *,
        expect_reply: bool,
    ) -> dict[str, Any] | None:
        message = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        data = (message + "\n").encode("utf-8")
        sock = self._ensure_connection()
        if sock is None:
            raise ConnectionError(f"unable to connect to {self.host}:{self.port}")

        try:
            sock.sendall(data)
            if not expect_reply:
                return None
            return self._read_reply()
        except (OSError, socket.timeout) as exc:  # pragma: no cover - exercised via tests
            self._record_failure(exc)
            raise

    def _read_reply(self) -> dict[str, Any]:
        sock = self._sock
        if sock is None:
            raise ConnectionError("socket unavailable")

        deadline = self._time_fn() + self._read_timeout
        while True:
            newline_index = self._recv_buffer.find(b"\n")
            if newline_index != -1:
                line = bytes(self._recv_buffer[:newline_index])
                del self._recv_buffer[: newline_index + 1]
                text = line.strip().decode("utf-8")
                if not text:
                    continue
                return json.loads(text)

            if self._time_fn() > deadline:
                raise TimeoutError("timed out waiting for Govee reply")

            try:
                chunk = sock.recv(4096)
            except socket.timeout as exc:
                raise TimeoutError("timed out waiting for Govee reply") from exc

            if not chunk:
                raise ConnectionError("connection closed by remote host")
            self._recv_buffer.extend(chunk)

    def _ensure_connection(self) -> socket.socket | None:
        now = self._time_fn()
        if self._sock is not None:
            return self._sock

        if now < self._next_retry_at:
            return None

        try:
            sock = socket.create_connection(
                (self.host, self.port), timeout=self._connect_timeout
            )
            sock.settimeout(self._read_timeout)
        except OSError as exc:
            self._record_failure(exc)
            return None

        self._sock = sock
        self._recv_buffer.clear()
        self._backoff = self._base_backoff
        self._last_error = None
        return sock

    def _record_failure(self, exc: Exception) -> None:
        self.close()
        self._last_error = exc
        now = self._time_fn()
        self._next_retry_at = now + self._backoff
        self._backoff = min(self._backoff * 2.0, self._max_backoff)


def _extract_msg_data(response: dict[str, Any]) -> dict[str, Any]:
    data = response
    msg = response.get("msg")
    if isinstance(msg, dict):
        data = msg.get("data") or msg
    return data if isinstance(data, dict) else {}


def _parse_segments(data: dict[str, Any]) -> list[GoveeSegmentInfo]:
    raw_segments: list[Any] | None = None
    ic_segments = data.get("icSegments")
    if isinstance(ic_segments, dict):
        segments_obj = ic_segments.get("segments") or ic_segments.get("icSegs")
        if isinstance(segments_obj, list):
            raw_segments = segments_obj
    elif isinstance(ic_segments, list):
        raw_segments = ic_segments

    if raw_segments is None:
        segments_field = data.get("segments")
        if isinstance(segments_field, list):
            raw_segments = segments_field

    segments: list[GoveeSegmentInfo] = []
    if raw_segments is None:
        return segments

    for idx, seg in enumerate(raw_segments):
        if not isinstance(seg, dict):
            continue
        segment_id = int(seg.get("segmentId", idx))
        length = seg.get("count") or seg.get("len") or seg.get("ledCount")
        length = int(length) if isinstance(length, (int, float)) else None
        segments.append(GoveeSegmentInfo(segment_id=segment_id, length=length))
    return segments


def _infer_channels(
    data: dict[str, Any],
    segments: list[GoveeSegmentInfo],
) -> int:
    color = data.get("color")
    if isinstance(color, dict) and "w" in color:
        return 4

    channel_hint = data.get("channelCount")
    if isinstance(channel_hint, (int, float)):
        if channel_hint >= 4:
            return 4
        if channel_hint >= 3:
            return 3

    if segments:
        seg0 = segments[0]
        if getattr(seg0, "length", None):
            # Lacking better metadata, assume RGB per pixel.
            return 3

    return 3
