"""cron: how each schedule field expands, and what the node writes at a given local time."""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pytest

from rasl.graph.node import TickContext
from rasl.nodes.effects.cron import CronNode, expand_day_of_week, expand_field

_TICK = TickContext(tick=0, t=0.0, dt=0.0, wall_time=0.0)


async def _matches(schedule: str, when: datetime) -> bool:
    node = CronNode(CronNode.Config(id="c", schedule=schedule), clock=lambda: when)
    await node.pull(_TICK)
    return bool(np.asarray(node.outputs.out._publish().payload).item())


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("*", set(range(60))),
        ("", set(range(60))),
        ("7", {7}),
        ("10-13", {10, 11, 12, 13}),
        ("*/15", {0, 15, 30, 45}),
        ("10-30/10", {10, 20, 30}),
        ("5/15", {5, 20, 35, 50}),  # used to drop the step and match only 5
        ("1,2,50-52", {1, 2, 50, 51, 52}),
        ("0,*/30", {0, 30}),
    ],
)
def test_a_minute_field_expands_to_its_values(token: str, expected: set[int]) -> None:
    assert expand_field(token, min_v=0, max_v=59) == expected


def test_a_step_counts_from_the_fields_lowest_value() -> None:
    assert expand_field("*/10", min_v=1, max_v=31) == {1, 11, 21, 31}


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("0", {0}),
        ("7", {0}),  # both are Sunday
        ("0-5", {0, 1, 2, 3, 4, 5}),  # used to fail: "range end < start: 7-5"
        ("0-6", set(range(7))),
        ("1-7", set(range(7))),
        ("0-7", set(range(7))),
        ("*/2", {0, 2, 4, 6}),  # Sunday, Tuesday, Thursday, Saturday
        ("1-5", {1, 2, 3, 4, 5}),
        ("6,7", {6, 0}),
    ],
)
def test_day_of_week_counts_from_sunday_and_reads_7_as_sunday(token: str, expected: set[int]) -> None:
    assert expand_day_of_week(token) == expected


@pytest.mark.parametrize(
    ("token", "message"),
    [
        ("60", "out of range"),
        ("5-70", "out of range"),
        ("30-10", "end < start"),
        ("*/0", "step must be > 0"),
        ("*/", "Invalid cron step"),
        ("x", "Invalid cron field integer"),
    ],
)
def test_a_field_that_is_not_valid_is_refused(token: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        expand_field(token, min_v=0, max_v=59)


def test_day_of_week_8_is_refused() -> None:
    with pytest.raises(ValueError, match="out of range"):
        expand_day_of_week("8")


def test_a_schedule_of_more_than_five_fields_is_refused() -> None:
    with pytest.raises(ValueError, match="1-5 fields"):
        CronNode(CronNode.Config(id="c", schedule="* * * * * *"))


SUNDAY_2200 = datetime(2026, 11, 22, 22, 0)  # a Sunday
MONDAY_2205 = datetime(2026, 11, 23, 22, 5)


@pytest.mark.parametrize(
    ("schedule", "when", "expected"),
    [
        ("0 22", SUNDAY_2200, True),
        ("0 22", MONDAY_2205, False),
        ("*/5 22", MONDAY_2205, True),
        ("* * * * 0", SUNDAY_2200, True),
        ("* * * * 7", SUNDAY_2200, True),
        ("* * * * 0", MONDAY_2205, False),
        ("* * * * 1-5", MONDAY_2205, True),
        ("* * * * 1-5", SUNDAY_2200, False),
        ("* * * * */2", SUNDAY_2200, True),
        ("* * * * */2", MONDAY_2205, False),
        ("* * 22 11", SUNDAY_2200, True),
        ("* * 22 12", SUNDAY_2200, False),
        # Day of month and day of week are both required when both are given.
        ("* * 22 * 1", SUNDAY_2200, False),
        ("* * 22 * 0", SUNDAY_2200, True),
    ],
)
async def test_the_output_is_true_while_the_local_time_matches(schedule: str, when: datetime, expected: bool) -> None:
    assert await _matches(schedule, when) is expected


async def test_the_fields_can_be_given_as_a_list() -> None:
    node = CronNode(CronNode.Config(id="c", schedule=["30", "6"]), clock=lambda: datetime(2026, 1, 1, 6, 30))
    await node.pull(_TICK)
    assert bool(np.asarray(node.outputs.out._publish().payload).item())
