from __future__ import annotations

import asyncio
import ipaddress
from dataclasses import dataclass
from typing import Literal

import structlog
from aiolifx.aiolifx import LifxDiscovery, Light

_LOGGER = structlog.get_logger(__name__)


@dataclass(frozen=True)
class LifxTargetSpec:
    """Normalized representation of a LIFX target selection."""

    kind: Literal["ip", "group"]
    value: str


class LifxTargetBinding:
    """Lightweight view over the discovery cache for a specific target."""

    __slots__ = ("_manager", "_spec")

    def __init__(self, manager: "LifxDiscoveryManager", spec: LifxTargetSpec) -> None:
        self._manager = manager
        self._spec = spec

    def resolve_lights(self) -> list[Light]:
        """Return lights that currently satisfy this binding."""
        return self._manager._resolve_spec(self._spec)

    def describe(self) -> dict[str, str]:
        return {"kind": self._spec.kind, "value": self._spec.value}


class LifxDiscoveryManager:
    """Shared aiolifx discovery lifecycle with cached light metadata."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._refcount = 0
        self._discovery: LifxDiscovery | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lights: dict[str, Light] = {}

    async def acquire(self) -> None:
        """Ensure discovery is running."""
        async with self._lock:
            self._refcount += 1
            if self._refcount == 1:
                await self._start_discovery()

    async def release(self) -> None:
        """Release discovery resources if unused."""
        async with self._lock:
            if self._refcount == 0:
                return
            self._refcount -= 1
            if self._refcount == 0:
                await self._stop_discovery()

    def create_binding(self, spec: LifxTargetSpec) -> LifxTargetBinding:
        return LifxTargetBinding(self, spec)

    def register(self, light: Light) -> None:
        """Called by aiolifx when a light becomes available."""
        self._lights[light.mac_addr] = light
        try:
            light.get_label()
            light.get_group()
        except Exception:  # pragma: no cover - defensive
            pass
        _LOGGER.info(
            "lifx_light_registered",
            mac=light.mac_addr,
            ip=light.ip_addr,
        )

    def unregister(self, light: Light) -> None:
        self._lights.pop(light.mac_addr, None)
        _LOGGER.info("lifx_light_unregistered", mac=light.mac_addr)

    def _resolve_spec(self, spec: LifxTargetSpec) -> list[Light]:
        if spec.kind == "ip":
            return [
                light
                for light in self._lights.values()
                if light.ip_addr == spec.value
            ]

        group_key = spec.value.casefold()
        matches: list[Light] = []
        for light in self._lights.values():
            label = _extract_group_label(light.group)
            if label and label.casefold() == group_key:
                matches.append(light)
        return matches

    async def _start_discovery(self) -> None:
        loop = asyncio.get_running_loop()
        discovery = LifxDiscovery(loop, parent=self)
        await discovery.start()
        discovery.discover()
        self._discovery = discovery
        self._loop = loop
        _LOGGER.info("lifx_discovery_started")

    async def _stop_discovery(self) -> None:
        if self._discovery is None:
            return
        self._discovery.cleanup()
        self._discovery = None
        self._loop = None
        self._lights.clear()
        _LOGGER.info("lifx_discovery_stopped")


_MANAGER: LifxDiscoveryManager | None = None


def get_lifx_manager() -> LifxDiscoveryManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = LifxDiscoveryManager()
    return _MANAGER


def parse_target_spec(value: str) -> LifxTargetSpec:
    """Parse the positional target string into a structured selector."""
    text = value.strip()
    if not text:
        raise ValueError("target must be a non-empty string")

    lowered = text.lower()
    if lowered.startswith("group:"):
        label = text.split(":", 1)[1].strip()
        if not label:
            raise ValueError("group targets must include a label (e.g. 'group:Living')")
        return LifxTargetSpec(kind="group", value=label)

    try:
        ip = ipaddress.ip_address(text)
    except ValueError as exc:  # pragma: no cover - input validation
        raise ValueError(
            "target must be an IPv4/IPv6 address or 'group:<label>'"
        ) from exc

    return LifxTargetSpec(kind="ip", value=str(ip))


def _extract_group_label(group_attr: object) -> str | None:
    if group_attr is None:
        return None
    if isinstance(group_attr, str):
        return group_attr.strip() or None
    if isinstance(group_attr, bytes):
        return group_attr.decode(errors="ignore").strip("\x00 ") or None
    label = getattr(group_attr, "label", None)
    if isinstance(label, bytes):
        return label.decode(errors="ignore").strip("\x00 ") or None
    if isinstance(label, str):
        return label.strip() or None
    if isinstance(group_attr, dict):
        raw = group_attr.get("label")
        if isinstance(raw, bytes):
            return raw.decode(errors="ignore").strip("\x00 ") or None
        if isinstance(raw, str):
            return raw.strip() or None
    return None


__all__ = [
    "LifxDiscoveryManager",
    "LifxTargetBinding",
    "LifxTargetSpec",
    "get_lifx_manager",
    "parse_target_spec",
]
