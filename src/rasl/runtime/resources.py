"""The runtime's registry of shared resources (``rasl.graph.node.resources``).

Each resource is counted by holder. It opens on the first ``acquire`` and closes when
the last lease is released, except during a plan update: a swap stops the old nodes
before it starts the new ones, so a resource both use would close and reopen in
between (a socket rebound, a multicast group left and rejoined). While a swap runs
(``ResourceRegistry.deferring_close``) a resource nobody holds stays open, and closes
when the swap ends only if nobody took it up again (owner, 2026-11-20, rasl-2lg.1).

A resource's ``open`` may itself acquire other resources (an sACN output acquires its
sender). Those finish opening first, so ``close_all`` closes in the reverse order that
opens completed: a resource closes before what it depends on.
"""

from __future__ import annotations

import contextlib
import itertools
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Generic, Literal, Optional, TypeVar

import anyio
import structlog

from rasl.graph.node import Lease, ResourceKey

logger = structlog.get_logger()

T = TypeVar("T")

_State = Literal["opening", "open", "closing", "closed"]


@dataclass(eq=False)
class _Entry:
    """One resource: its state, its value once open, how to close it, and its holders."""

    close: Callable[[Any], Awaitable[None]]
    state: _State = "opening"
    opened: anyio.Event = field(default_factory=anyio.Event)
    closed: anyio.Event = field(default_factory=anyio.Event)
    value: Any = None
    error: Optional[Exception] = None
    retry: bool = False
    """Set when the opener was cancelled: waiters try to open the resource themselves."""
    holders: int = 0
    open_seq: int = 0
    """The order this entry finished opening in, for closing dependents first."""


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
        self._seq = itertools.count(1)

    async def acquire(
        self,
        key: ResourceKey[T],
        open: Callable[[], Awaitable[T]],
        close: Callable[[T], Awaitable[None]],
    ) -> Lease[T]:
        """A share of the resource ``key`` names, opening it if it is not open.

        See ``rasl.graph.node.Resources.acquire``. A resource still closing is waited
        for, then opened afresh.
        """
        while True:
            entry = self._entries.get(key)
            if entry is None:
                return await self._open(key, open, close)
            if entry.state == "closing":
                await entry.closed.wait()
                continue
            await entry.opened.wait()
            if entry.retry:
                continue
            if entry.error is not None:
                raise entry.error
            entry.holders += 1
            return _Lease(self, key, entry)

    async def _open(
        self,
        key: ResourceKey[T],
        open: Callable[[], Awaitable[T]],
        close: Callable[[T], Awaitable[None]],
    ) -> Lease[T]:
        entry = _Entry(close=close)
        self._entries[key] = entry
        try:
            entry.value = await open()
        except Exception as e:
            entry.error = e
            raise
        except BaseException:
            # Cancelled: waiters must not inherit the cancellation; they open it themselves
            entry.retry = True
            raise
        else:
            entry.state = "open"
            entry.open_seq = next(self._seq)
            entry.holders = 1
            return _Lease(self, key, entry)
        finally:
            if entry.state == "opening":
                entry.state = "closed"
                if self._entries.get(key) is entry:
                    del self._entries[key]
                entry.closed.set()
            entry.opened.set()

    async def _release(self, key: ResourceKey[Any], entry: _Entry) -> None:
        if entry.state != "open":
            logger.debug("resource_release_after_close", resource=str(key))
            return
        entry.holders -= 1
        if entry.holders == 0 and not self._deferring:
            await self._close(key, entry)

    async def _close(self, key: ResourceKey[Any], entry: _Entry) -> None:
        """Close an open ``entry``; it stays registered, as closing, until its close
        returns. A close that raises is logged, not raised."""
        if entry.state != "open":
            return
        entry.state = "closing"
        try:
            with anyio.CancelScope(shield=True):
                try:
                    await entry.close(entry.value)
                    logger.debug("resource_closed", resource=str(key))
                except Exception as e:
                    logger.error("resource_close_failed", resource=str(key), error=str(e))
        finally:
            entry.state = "closed"
            if self._entries.get(key) is entry:
                del self._entries[key]
            entry.closed.set()

    def _open_entries_newest_first(self) -> list[tuple[ResourceKey[Any], _Entry]]:
        open_entries = [(k, e) for k, e in self._entries.items() if e.state == "open"]
        return sorted(open_entries, key=lambda item: item[1].open_seq, reverse=True)

    @contextlib.asynccontextmanager
    async def deferring_close(self) -> AsyncIterator[None]:
        """Within the block, a resource whose last holder releases it stays open; at
        the end, every open resource nobody holds is closed, dependents first."""
        self._deferring += 1
        try:
            yield
        finally:
            self._deferring -= 1
            if not self._deferring:
                for key, entry in self._open_entries_newest_first():
                    if entry.holders == 0:
                        await self._close(key, entry)

    async def close_all(self) -> None:
        """Close every resource, dependents first, after any open in progress ends.

        One still held is closed too, and logged as leaked: its holder did not release
        it in ``stop``. A release that comes later does nothing.
        """
        for entry in list(self._entries.values()):
            if entry.state == "opening":
                await entry.opened.wait()
        for key, entry in self._open_entries_newest_first():
            if entry.state != "open":
                continue  # closed meanwhile, by a dependent's close releasing it
            if entry.holders:
                logger.warning("resource_leaked", resource=str(key), holders=entry.holders)
            await self._close(key, entry)
