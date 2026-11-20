"""Resources that nodes share, such as a socket several nodes receive on.

A node asks ``NodeContext.resources`` for a resource by key. The first node to ask
opens it; later nodes get the same one; it is closed when the last of them releases
it. The runtime owns the registry (``rasl.runtime.resources``), so a resource lives
no longer than the runtime that opened it.

Owner, 2026-11-20 (rasl-2lg.1): shared transports come from a registry the runtime
passes on ``NodeContext``, not from a module-level cache.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Generic, Hashable, Protocol, Tuple, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class ResourceKey(Generic[T]):
    """Names one shared resource; nodes that ask with equal keys share it.

    Attributes:
        kind: What sort of resource it is, namespaced by its package (``"sacn.receiver"``).
            Each kind always opens the same type ``T``.
        params: What tells two resources of one kind apart (an address and a port).
    """

    kind: str
    params: Tuple[Hashable, ...] = ()

    def __str__(self) -> str:
        """``kind(param, ...)``, for log lines."""
        return f"{self.kind}({', '.join(str(p) for p in self.params)})"


class Lease(Protocol[T]):
    """One holder's share of a resource. Release it when done, typically in ``stop``."""

    @property
    def value(self) -> T:
        """The shared resource."""
        ...

    async def release(self) -> None:
        """Give up this share; the resource closes when no share is left.

        Releasing twice does nothing the second time.
        """
        ...


class Resources(Protocol):
    """Hands out shared resources by key, opening and closing them as needed."""

    async def acquire(
        self,
        key: ResourceKey[T],
        open: Callable[[], Awaitable[T]],
        close: Callable[[T], Awaitable[None]],
    ) -> Lease[T]:
        """A share of the resource ``key`` names, opening it if nobody holds it.

        Args:
            key: Which resource. Holders of equal keys share one resource.
            open: Makes the resource. Called only when it is not open already; when
                it is, the ``open`` and ``close`` of the holder who opened it apply.
            close: Ends the resource, once nobody holds it.

        Returns:
            A lease on the resource.

        Raises:
            Exception: Whatever ``open`` raises. Every caller waiting on that open gets
                it, and the next ``acquire`` tries to open again.
        """
        ...
