from __future__ import annotations

import asyncio
import secrets
import struct
from dataclasses import dataclass

LIFX_DEFAULT_PORT = 56700
_LIGHT_SET_COLOR = 102
_PROTOCOL_NUMBER = 0x400


@dataclass(frozen=True)
class LifxEndpoint:
    """Explicitly configured LIFX target."""

    ip: str
    port: int = LIFX_DEFAULT_PORT
    mac: bytes | None = None


class LifxLanClient:
    """Minimal LIFX LAN sender that targets a single endpoint."""

    def __init__(
        self,
        endpoint: LifxEndpoint,
        *,
        source_id: int | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._source_id = source_id if source_id is not None else secrets.randbits(32)
        self._sequence = 0
        self._transport: asyncio.DatagramTransport | None = None

    async def start(self) -> None:
        """Create a UDP transport for the configured endpoint."""
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            asyncio.DatagramProtocol,
            remote_addr=(self._endpoint.ip, self._endpoint.port),
        )
        self._transport = transport

    def stop(self) -> None:
        """Close the UDP transport."""
        if self._transport is not None:
            self._transport.close()
            self._transport = None

    def describe(self) -> dict[str, str | int | None]:
        mac = (
            self._endpoint.mac.hex()
            if self._endpoint.mac is not None
            else None
        )
        return {
            "ip": self._endpoint.ip,
            "port": self._endpoint.port,
            "mac": mac,
        }

    def send_set_color(
        self,
        *,
        hue: int,
        saturation: int,
        brightness: int,
        kelvin: int,
        duration_ms: int,
        rapid: bool,
    ) -> None:
        """Send a LightSetColor packet."""
        if self._transport is None:
            raise RuntimeError("LifxLanClient has not been started")

        packet = _encode_set_color_packet(
            source_id=self._source_id,
            sequence=self._sequence,
            mac=self._endpoint.mac,
            hue=hue,
            saturation=saturation,
            brightness=brightness,
            kelvin=kelvin,
            duration_ms=max(0, int(duration_ms)),
            rapid=rapid,
        )
        self._sequence = (self._sequence + 1) % 256
        self._transport.sendto(packet)


def parse_target_list(value: str) -> list[LifxEndpoint]:
    """Parse comma separated target specs into endpoints."""
    specs = [part.strip() for part in value.split(",")]
    endpoints: list[LifxEndpoint] = []
    for spec in specs:
        if not spec:
            continue
        endpoints.append(_parse_single_target(spec))
    return endpoints


def _parse_single_target(spec: str) -> LifxEndpoint:
    mac: bytes | None = None
    target = spec

    if "@" in spec:
        mac_text, target = spec.split("@", 1)
        mac = _parse_mac(mac_text.strip())

    ip, port = _parse_host_port(target.strip())
    return LifxEndpoint(ip=ip, port=port, mac=mac)


def _parse_mac(value: str) -> bytes:
    cleaned = value.replace(":", "").replace("-", "")
    if len(cleaned) not in (12, 16):
        raise ValueError(f"invalid MAC '{value}'")
    try:
        data = bytes.fromhex(cleaned)
    except ValueError as exc:  # pragma: no cover - error path
        raise ValueError(f"invalid MAC '{value}'") from exc
    if len(data) == 6:
        return data
    if len(data) == 8:
        return data[:6]
    return data


def _parse_host_port(target: str) -> tuple[str, int]:
    if not target:
        raise ValueError("target host cannot be empty")

    if target.startswith("["):
        # IPv6 literal
        end = target.find("]")
        if end == -1:
            raise ValueError(f"invalid IPv6 target '{target}'")
        host = target[1:end]
        port = LIFX_DEFAULT_PORT
        remainder = target[end + 1 :]
        if remainder:
            if not remainder.startswith(":"):
                raise ValueError(f"invalid IPv6 target '{target}'")
            port = int(remainder[1:], 10)
        return host, port

    if ":" in target and target.count(":") == 1:
        host, port_text = target.rsplit(":", 1)
        if not host:
            raise ValueError(f"invalid host in target '{target}'")
        port = int(port_text, 10)
        return host, port

    return target, LIFX_DEFAULT_PORT


def _encode_set_color_packet(
    *,
    source_id: int,
    sequence: int,
    mac: bytes | None,
    hue: int,
    saturation: int,
    brightness: int,
    kelvin: int,
    duration_ms: int,
    rapid: bool,
) -> bytes:
    tagged = 0 if mac else 1
    frame_flags = _build_frame_flags(tagged=tagged)
    target = _encode_target(mac)
    ack_required = 0  # we do not currently process acknowledgements
    res_required = 0 if rapid else 0

    frame_address = struct.pack(
        "<8s6sBB",
        target,
        b"\x00" * 6,
        (res_required << 1) | ack_required,
        sequence & 0xFF,
    )

    protocol_header = struct.pack(
        "<QHH",
        0,
        _LIGHT_SET_COLOR,
        0,
    )

    payload = struct.pack(
        "<BHHHHI",
        0,  # reserved
        hue & 0xFFFF,
        saturation & 0xFFFF,
        brightness & 0xFFFF,
        kelvin & 0xFFFF,
        duration_ms & 0xFFFFFFFF,
    )

    size = 8 + len(frame_address) + len(protocol_header) + len(payload)
    frame_header = struct.pack("<HHI", size, frame_flags, source_id & 0xFFFFFFFF)
    return frame_header + frame_address + protocol_header + payload


def _build_frame_flags(*, tagged: int) -> int:
    origin = 0
    addressable = 1
    value = (_PROTOCOL_NUMBER & 0x0FFF)
    value |= (addressable & 0x1) << 12
    value |= (tagged & 0x1) << 13
    value |= (origin & 0x3) << 14
    return value


def _encode_target(mac: bytes | None) -> bytes:
    if mac is None:
        return b"\x00" * 8
    if len(mac) == 6:
        return mac + b"\x00\x00"
    if len(mac) == 8:
        return mac
    padded = mac[:8].ljust(8, b"\x00")
    return padded


__all__ = [
    "LifxEndpoint",
    "LifxLanClient",
    "LIFX_DEFAULT_PORT",
    "parse_target_list",
]
