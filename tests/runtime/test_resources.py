"""ResourceRegistry: shared, reference-counted resources that live no longer than the runtime."""

from __future__ import annotations

import anyio
import pytest

from rasl.graph.node import ResourceKey
from rasl.runtime.resources import ResourceRegistry

KEY = ResourceKey[str]("test.thing", ("a", 1))


class Tracker:
    """Opens and closes named resources, recording each call in order."""

    def __init__(self) -> None:
        self.events: list[str] = []

    def opener(self, name: str = "thing", *, wait: anyio.Event | None = None, fail: Exception | None = None):
        async def _open() -> str:
            self.events.append(f"open {name}")
            if wait is not None:
                await wait.wait()
            if fail is not None:
                raise fail
            return name

        return _open

    async def close(self, value: str) -> None:
        self.events.append(f"close {value}")


async def test_holders_share_one_resource_and_the_last_release_closes_it() -> None:
    registry, t = ResourceRegistry(), Tracker()
    first = await registry.acquire(KEY, t.opener(), t.close)
    second = await registry.acquire(KEY, t.opener(), t.close)
    assert first.value == second.value == "thing"
    await first.release()
    assert t.events == ["open thing"]
    await second.release()
    assert t.events == ["open thing", "close thing"]


async def test_releasing_twice_counts_once() -> None:
    registry, t = ResourceRegistry(), Tracker()
    first = await registry.acquire(KEY, t.opener(), t.close)
    second = await registry.acquire(KEY, t.opener(), t.close)
    await first.release()
    await first.release()
    assert t.events == ["open thing"]
    await second.release()
    assert t.events[-1] == "close thing"


async def test_different_keys_are_different_resources() -> None:
    registry, t = ResourceRegistry(), Tracker()
    a = await registry.acquire(ResourceKey[str]("test.thing", (1,)), t.opener("a"), t.close)
    b = await registry.acquire(ResourceKey[str]("test.thing", (2,)), t.opener("b"), t.close)
    assert (a.value, b.value) == ("a", "b")


async def test_a_resource_released_during_a_swap_closes_only_if_not_taken_up_again() -> None:
    registry, t = ResourceRegistry(), Tracker()
    kept = await registry.acquire(KEY, t.opener(), t.close)
    dropped = await registry.acquire(ResourceKey[str]("test.other"), t.opener("other"), t.close)
    async with registry.deferring_close():
        await kept.release()  # the old node stops...
        await dropped.release()
        assert "close thing" not in t.events
        kept = await registry.acquire(KEY, t.opener(), t.close)  # ...and its successor starts
    assert t.events == ["open thing", "open other", "close other"]
    await kept.release()
    assert t.events[-1] == "close thing"


async def test_a_failed_open_reaches_every_waiter_and_the_next_acquire_retries() -> None:
    registry, t = ResourceRegistry(), Tracker()
    gate = anyio.Event()
    errors: list[str] = []

    async def acquire_failing() -> None:
        try:
            await registry.acquire(KEY, t.opener(wait=gate, fail=OSError("in use")), t.close)
        except OSError as e:
            errors.append(str(e))

    async with anyio.create_task_group() as tg:
        tg.start_soon(acquire_failing)
        await anyio.sleep(0)
        tg.start_soon(acquire_failing)
        await anyio.sleep(0)
        gate.set()
    assert errors == ["in use", "in use"]
    assert t.events == ["open thing"]  # the second caller waited on the first open

    lease = await registry.acquire(KEY, t.opener(), t.close)
    assert lease.value == "thing"


async def test_a_cancelled_opener_does_not_cancel_its_waiters() -> None:
    registry, t = ResourceRegistry(), Tracker()
    never = anyio.Event()
    got: list[str] = []

    async def waiter() -> None:
        lease = await registry.acquire(KEY, t.opener("second"), t.close)
        got.append(lease.value)

    opener_scope = anyio.CancelScope()

    async def opener() -> None:
        with opener_scope:
            await registry.acquire(KEY, t.opener("first", wait=never), t.close)

    async with anyio.create_task_group() as tg:
        tg.start_soon(opener)
        await anyio.sleep(0)
        tg.start_soon(waiter)
        await anyio.sleep(0)
        opener_scope.cancel()
    assert got == ["second"]
    assert t.events == ["open first", "open second"]


async def test_close_all_waits_for_an_open_in_progress_and_never_closes_an_unopened_value() -> None:
    registry, t = ResourceRegistry(), Tracker()
    gate = anyio.Event()
    async with anyio.create_task_group() as tg:
        tg.start_soon(registry.acquire, KEY, t.opener(wait=gate), t.close)
        await anyio.sleep(0)

        async def finish_open() -> None:
            await anyio.sleep(0)
            gate.set()

        tg.start_soon(finish_open)
        await registry.close_all()
    assert t.events == ["open thing", "close thing"]


async def test_a_release_after_close_all_does_nothing() -> None:
    registry, t = ResourceRegistry(), Tracker()
    lease = await registry.acquire(KEY, t.opener(), t.close)
    await registry.close_all()
    await lease.release()
    assert t.events == ["open thing", "close thing"]


async def test_close_all_closes_a_dependent_before_what_it_depends_on() -> None:
    """An output whose open acquires its sender opens after it, so it closes first."""
    registry, t = ResourceRegistry(), Tracker()
    sender_key = ResourceKey[str]("test.sender")
    output_key = ResourceKey[str]("test.output")
    # Someone else holds the sender first, so it opened earlier than the output
    sender_lease = await registry.acquire(sender_key, t.opener("sender"), t.close)
    leases = {}

    async def open_output() -> str:
        leases["sender"] = await registry.acquire(sender_key, t.opener("sender"), t.close)
        t.events.append("open output")
        return "output"

    async def close_output(value: str) -> None:
        t.events.append("close output (sends termination through the sender)")
        await leases["sender"].release()

    await registry.acquire(output_key, open_output, close_output)
    del sender_lease  # leaked on purpose
    await registry.close_all()
    assert t.events == [
        "open sender",
        "open output",
        "close output (sends termination through the sender)",
        "close sender",
    ]


async def test_acquiring_a_resource_that_is_closing_waits_and_opens_it_afresh() -> None:
    registry = ResourceRegistry()
    events: list[str] = []
    closing = anyio.Event()
    finish_close = anyio.Event()
    count = 0

    async def _open() -> int:
        nonlocal count
        count += 1
        events.append(f"open {count}")
        return count

    async def _close(value: int) -> None:
        events.append(f"closing {value}")
        closing.set()
        await finish_close.wait()
        events.append(f"closed {value}")

    lease = await registry.acquire(KEY, _open, _close)
    async with anyio.create_task_group() as tg:
        tg.start_soon(lease.release)
        await closing.wait()

        async def reacquire() -> None:
            again = await registry.acquire(KEY, _open, _close)
            events.append(f"got {again.value}")

        tg.start_soon(reacquire)
        await anyio.sleep(0)
        finish_close.set()
    assert events == ["open 1", "closing 1", "closed 1", "open 2", "got 2"]


async def test_a_close_that_raises_is_logged_and_the_resource_forgotten() -> None:
    registry = ResourceRegistry()

    async def _open() -> str:
        return "x"

    async def _close(value: str) -> None:
        raise OSError("boom")

    lease = await registry.acquire(KEY, _open, _close)
    await lease.release()
    again = await registry.acquire(KEY, _open, _close)
    assert again.value == "x"


@pytest.mark.parametrize("nesting", [1, 2])
async def test_nested_deferral_closes_only_when_the_outermost_ends(nesting: int) -> None:
    registry, t = ResourceRegistry(), Tracker()
    lease = await registry.acquire(KEY, t.opener(), t.close)
    async with registry.deferring_close():
        if nesting == 2:
            async with registry.deferring_close():
                await lease.release()
            assert "close thing" not in t.events
        else:
            await lease.release()
    assert t.events[-1] == "close thing"
