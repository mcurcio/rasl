"""The runtime's registry of shared resources (``rasl.graph.node.resources``).

Each resource is counted by holder. It opens on the first ``acquire`` and closes when
the last lease is released, except during a plan update: a swap stops the old nodes
before it starts the new ones, so a resource both use would close and reopen in
between (a socket rebound, a multicast group left and rejoined). While a swap runs
(``ResourceRegistry.deferring_close``) a resource nobody holds stays open, and closes
when the swap ends only if nobody took it up again (owner, 2026-11-20, rasl-2lg.1).
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Generic, Optional, TypeVar

import anyio
import structlog

from rasl.graph.node import Lease, ResourceKey

logger = structlog.get_logger()

T = TypeVar("T")


@dataclass(eq=False)
class _Entry:
    """One resource: its value once open, how to close it, and how many hold it."""

    close: Callable[[Any], Awaitable[None]]
    opened: anyio.Event = field(default_factory=anyio.Event)
    value: Any = None
    error: Optional[BaseException] = None
    holders: int = 0


class _Lease(Generic[T]):
    """A holder's share of an open resource."""

    def __init__(self, registry: "ResourceRegistry", key: ResourceKey[Any], entry: _Entry) -> None:
        self._registry = registry
        self._key = key
        self._entry = entry
        self._released = False

    @property
    def value(self) -> T:
        """The shared resource."""
        return self._entry.value  # type: ignore[no-any-return]

    async def release(self) -> None:
        """Give up this share; the resource closes when no share is left (see the module)."""
        if self._released:
            return
        self._released = True
        await self._registry._release(self._key, self._entry)


class ResourceRegistry:
    """Opens, shares and closes the resources a runtime's nodes ask for."""

    def __init__(self) -> None:
        self._entries: Dict[ResourceKey[Any], _Entry] = {}
        self._deferring = 0

    async def acquire(
        self,
        key: ResourceKey[T],
        open: Callable[[], Awaitable[T]],
        close: Callable[[T], Awaitable[None]],
    ) -> Lease[T]:
        """A share of the resource ``key`` names, opening it if it is not open.

        See ``rasl.graph.node.Resources.acquire``.
        """
        entry = self._entries.get(key)
        if entry is None:
            entry = _Entry(close=close)
            self._entries[key] = entry
            try:
                entry.value = await open()
            except BaseException as e:
                entry.error = e
                del self._entries[key]
                raise
            finally:
                entry.opened.set()
        else:
            await entry.opened.wait()
            if entry.error is not None:
                raise entry.error
        entry.holders += 1
        return _Lease(self, key, entry)

    async def _release(self, key: ResourceKey[Any], entry: _Entry) -> None:
        entry.holders -= 1
        if entry.holders == 0 and not self._deferring:
            await self._close(key, entry)

    async def _close(self, key: ResourceKey[Any], entry: _Entry) -> None:
        """Close ``entry`` and forget it; a close that raises is logged, not raised."""
        if self._entries.get(key) is entry:
            del self._entries[key]
        with anyio.CancelScope(shield=True):
            try:
                await entry.close(entry.value)
                logger.debug("resource_closed", resource=str(key))
            except Exception as e:
                logger.error("resource_close_failed", resource=str(key), error=str(e))

    @contextlib.asynccontextmanager
    async def deferring_close(self) -> AsyncIterator[None]:
        """Within the block, a resource whose last holder releases it stays open; at
        the end, every resource nobody holds is closed."""
        self._deferring += 1
        try:
            yield
        finally:
            self._deferring -= 1
            if not self._deferring:
                for key, entry in list(self._entries.items()):
                    if entry.holders == 0:
                        await self._close(key, entry)

    async def close_all(self) -> None:
        """Close every resource. One still held is closed too, and logged as leaked:
        its holder did not release it in ``stop``."""
        for key, entry in list(self._entries.items()):
            if entry.holders:
                logger.warning("resource_leaked", resource=str(key), holders=entry.holders)
            await self._close(key, entry)
