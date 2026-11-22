"""Cron source node.

Emits a scalar 0/1 signal based on whether the current local wall-clock time
matches a (minute-granularity) cron expression.

The cron expression supports a dynamic number of fields (1-5):
    minute [hour [day_of_month [month [day_of_week]]]]

Any missing trailing fields are treated as "*" (don't care).

Field grammar:
- "*"        every value
- "*/n"      every n-th value, counted from the field's lowest
- "a"        one value
- "a-b"      a range, both ends included
- "a-b/n"    every n-th value of a range, counted from a
- "a/n"      every n-th value from a to the field's highest
- "a,b-c"    a list of any of the above

Day-of-week runs 0-6 from Sunday, and 7 is Sunday too, so "*/2" is Sunday, Tuesday,
Thursday and Saturday, and "0-5" is Sunday to Friday. Every field must match: a day of
month and a day of week given together are both required (cron itself takes either).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

import numpy as np
from pydantic import Field

from rasl.graph.node import BaseNode, SourceNodeConfig, TickContext, node
from rasl.graph.ports import OutputPortSpec, PortGroup
from rasl.signal import BoolPayload, Frame

_SUNDAY_AS_SEVEN = 7


def _parse_int(token: str) -> int:
    try:
        return int(token)
    except ValueError as e:
        raise ValueError(f"Invalid cron field integer: {token!r}") from e


def _expand_part(part: str, *, min_v: int, max_v: int) -> set[int]:
    """The values one comma-separated part of a field names, each within [min_v, max_v]."""
    step = 1
    stepped = "/" in part
    if stepped:
        part, step_s = part.split("/", 1)
        if not step_s:
            raise ValueError(f"Invalid cron step: {part + '/'!r}")
        step = _parse_int(step_s)
        if step <= 0:
            raise ValueError(f"Cron step must be > 0, got {step}")
        part = part or "*"

    if part == "*":
        start, end = min_v, max_v
    elif "-" in part:
        start_s, end_s = part.split("-", 1)
        start = _parse_int(start_s) if start_s else min_v
        end = _parse_int(end_s) if end_s else max_v
    else:
        start = _parse_int(part)
        end = max_v if stepped else start  # "a/n" runs from a to the field's highest value

    if start < min_v or start > max_v or end < min_v or end > max_v:
        shown = f"range {start}-{end}" if "-" in part else f"value {start}"
        raise ValueError(f"Cron {shown} out of range [{min_v},{max_v}]")
    if end < start:
        raise ValueError(f"Cron range end < start: {start}-{end}")
    return set(range(start, end + 1, step))


def expand_field(token: str, *, min_v: int, max_v: int) -> frozenset[int]:
    """Expand one cron field to the set of integers it matches.

    ``token`` is a comma-separated list of ``*``, ``a``, ``a-b``, each optionally followed by
    ``/n``; an empty token means ``*``. Every value must lie in ``[min_v, max_v]``.

    Raises:
        ValueError: for a value that is not an integer or is out of range, a range whose end
            is below its start, or a step that is not positive.
    """
    parts = [p.strip() for p in token.split(",") if p.strip()]
    if not parts:
        return frozenset(range(min_v, max_v + 1))
    values: set[int] = set()
    for part in parts:
        values |= _expand_part(part, min_v=min_v, max_v=max_v)
    return frozenset(values)


def expand_day_of_week(token: str) -> frozenset[int]:
    """Expand a day-of-week field to a set of 0 (Sunday) to 6 (Saturday); 7 is read as Sunday.

    Raises:
        ValueError: as :func:`expand_field`, for values outside 0-7.
    """
    return frozenset(v % _SUNDAY_AS_SEVEN for v in expand_field(token, min_v=0, max_v=_SUNDAY_AS_SEVEN))


def _coerce_schedule(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        tokens = [str(v) for v in value]
    else:
        tokens = str(value).split()

    tokens = [t for t in tokens if t]
    if not tokens:
        tokens = ["*"]

    if len(tokens) > 5:
        raise ValueError(f"cron expression supports 1-5 fields, got {len(tokens)}")

    # Pad missing trailing fields to 'dont care'
    while len(tokens) < 5:
        tokens.append("*")

    return tokens


@node("cron")
class CronNode(BaseNode):
    """Minute-granularity cron matcher source.

    Outputs a scalar (1x1) MatrixPayload with value 1.0 when the current
    wall-clock time matches the configured cron expression, else 0.0.
    """

    class Config(SourceNodeConfig):
        """The schedule for CronNode."""

        schedule: str | list[str] = Field(
            "*",
            description=(
                "Cron expression fields (1-5). Missing trailing fields are treated as '*'. "
                "Can be provided as a single string (e.g. '*/10 * * * *') or as multiple args."
            ),
        )

        @classmethod
        def from_positional(cls, words: Sequence[str], written: Sequence[str]) -> dict[str, Any]:
            """``node cron <name> <field1> [field2 ... field5]``: the schedule's fields.
            Missing trailing fields are treated as "*"."""
            if not words:
                return {}  # the schedule is given in the block instead
            if len(words) > 5:
                raise ValueError(f"cron node supports 1-5 fields, got {len(words)}")
            return {"schedule": list(words)}

    outputs = PortGroup.outputs(out=OutputPortSpec(BoolPayload, count=1))

    def __init__(self, config: Config, *, clock: Callable[[], datetime] | None = None) -> None:
        """Expand the schedule's fields.

        ``clock`` returns the local time the schedule is compared with; the default is
        ``datetime.now``. Tests pass their own.

        Raises:
            ValueError: for a schedule field that is not valid (see :func:`expand_field`).
        """
        super().__init__(config)
        self._topic = f"cron.{self.id}"
        self._clock = clock if clock is not None else datetime.now
        minute_s, hour_s, dom_s, month_s, dow_s = _coerce_schedule(config.schedule)

        self._minutes = expand_field(minute_s, min_v=0, max_v=59)
        self._hours = expand_field(hour_s, min_v=0, max_v=23)
        self._days_of_month = expand_field(dom_s, min_v=1, max_v=31)
        self._months = expand_field(month_s, min_v=1, max_v=12)
        self._days_of_week = expand_day_of_week(dow_s)

        # Output buffer (1x1)
        self._buf = np.zeros((1, 1), dtype=np.bool_)

    async def pull(self, tick: TickContext) -> None:
        """Write a 1x1 BoolPayload to ``out``: True when the current minute matches the schedule.

        The schedule is compared with the node's clock (the system's local time unless one was
        passed in), not the tick's; the frame's timestamp is the tick's wall time.
        """
        now = self._clock()
        matched = (
            now.minute in self._minutes
            and now.hour in self._hours
            and now.day in self._days_of_month
            and now.month in self._months
            and now.isoweekday() % _SUNDAY_AS_SEVEN in self._days_of_week
        )

        self._buf[0, 0] = matched

        frame = Frame(
            topic=self._topic,
            timestamp=tick.wall_time,
            payload=BoolPayload(self._buf.copy()),
            metadata=self._metadata,
        )
        self.outputs.out.write(frame)
