"""IdleCollector: which generation a gap collects, when a gap is long enough, and that
garbage which outlives one pass is still freed."""

from __future__ import annotations

import gc
import weakref
from collections.abc import Iterator

import pytest

from rasl.runtime.collector import IdleCollector


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class _Passes:
    """Stands in for gc.collect: records each generation and takes ``cost`` seconds."""

    def __init__(self, clock: _Clock, cost: float = 0.0) -> None:
        self.clock = clock
        self.cost = cost
        self.generations: list[int] = []

    def __call__(self, generation: int) -> None:
        self.generations.append(generation)
        self.clock.now += self.cost


@pytest.fixture
def collector() -> Iterator[tuple[IdleCollector, _Clock, _Passes]]:
    clock = _Clock()
    passes = _Passes(clock)
    made = IdleCollector(collect=passes, clock=clock)
    made.begin()
    try:
        yield made, clock, passes
    finally:
        made.end()


def test_nothing_is_collected_before_begin() -> None:
    clock = _Clock()
    passes = _Passes(clock)
    assert IdleCollector(collect=passes, clock=clock).collect_if_time(1.0) is False
    assert passes.generations == []


def test_begin_turns_automatic_collection_off_and_end_turns_it_on() -> None:
    made = IdleCollector()
    assert gc.isenabled()
    made.begin()
    try:
        assert not gc.isenabled()
        assert gc.get_freeze_count() > 0
    finally:
        made.end()
    assert gc.isenabled()
    assert gc.get_freeze_count() == 0


def test_older_generations_are_collected_every_tenth_pass(collector) -> None:
    made, _clock, passes = collector
    for _ in range(121):
        assert made.collect_if_time(1.0) is True
    assert passes.generations[:10] == [0] * 10
    assert passes.generations[10] == 1
    assert passes.generations.count(1) == 10
    assert passes.generations[-1] == 2  # after ten passes of generation 1
    assert passes.generations.count(2) == 1


def test_a_gap_shorter_than_twice_the_last_pass_is_left_alone(collector) -> None:
    made, _clock, passes = collector
    passes.cost = 0.010
    assert made.collect_if_time(1.0) is True  # measured: 10 ms
    assert made.collect_if_time(0.020) is False
    assert made.collect_if_time(0.022) is True


def test_an_overdue_pass_runs_in_a_gap_that_is_too_short(collector) -> None:
    made, clock, passes = collector
    passes.cost = 0.010
    made.collect_if_time(1.0)
    clock.now += 9.0
    assert made.collect_if_time(0.005) is False
    clock.now += 1.0
    assert made.collect_if_time(0.005) is True


class _Cycle:
    def __init__(self) -> None:
        self.me = self


def test_a_cycle_that_outlives_one_pass_is_still_freed() -> None:
    """Collecting only generation 0 promoted such a cycle and never looked at it again."""
    made = IdleCollector()
    made.begin()
    try:
        cycle = _Cycle()
        dead = weakref.ref(cycle)
        made.collect_if_time(1.0)  # the cycle is alive: it is promoted
        del cycle
        for _ in range(130):
            made.collect_if_time(1.0)
        assert dead() is None
    finally:
        made.end()


def test_suspended_hands_collection_back_to_python(collector) -> None:
    made, _clock, passes = collector
    made.suspend()
    assert gc.isenabled()
    assert made.collect_if_time(1.0) is False
    made.resume()
    assert not gc.isenabled()
    assert made.collect_if_time(1.0) is True
    assert passes.generations == [0]
