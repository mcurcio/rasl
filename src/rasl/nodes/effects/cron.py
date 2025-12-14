"""Cron source node.

Emits a scalar 0/1 signal based on whether the current local wall-clock time
matches a (minute-granularity) cron expression.

The cron expression supports a dynamic number of fields (1-5):
    minute [hour [day_of_month [month [day_of_week]]]]

Any missing trailing fields are treated as "*" (don't care).

Field grammar (minimal):
- "*"
- "*/n"
- "a"
- "a-b"
- "a-b/n"
- "a,b,c"

Day-of-week accepts 0-7 where 0 and 7 both mean Sunday.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import numpy as np
from pydantic import Field

from rasl.engine.nodes import BaseNode
from rasl.engine.frames import BoolPayload, Frame
from rasl.engine.ports import OutputPortSpec, PortGroup
from rasl.engine.registry import node
from rasl.engine.tick import TickContext
from rasl.nodes.models import SourceNodeConfig


@dataclass(frozen=True, slots=True)
class _CronField:
    match: Callable[[int], bool]


def _parse_int(token: str) -> int:
    try:
        return int(token)
    except ValueError as e:
        raise ValueError(f"Invalid cron field integer: {token!r}") from e


def _build_part_matcher(part: str, *, min_v: int, max_v: int, normalize: Callable[[int], int]) -> Callable[[int], bool]:
    part = part.strip()
    if not part or part == "*":
        return lambda _v: True

    step = 1
    if "/" in part:
        base, step_s = part.split("/", 1)
        if not step_s:
            raise ValueError(f"Invalid cron step: {part!r}")
        step = _parse_int(step_s)
        if step <= 0:
            raise ValueError(f"Cron step must be > 0, got {step}")
        part = base or "*"

    if part == "*":
        start = min_v
        end = max_v
    elif "-" in part:
        start_s, end_s = part.split("-", 1)
        if start_s == "":
            start = min_v
        else:
            start = _parse_int(start_s)
        if end_s == "":
            end = max_v
        else:
            end = _parse_int(end_s)
    else:
        value = normalize(_parse_int(part))
        if value < min_v or value > max_v:
            raise ValueError(f"Cron value {value} out of range [{min_v},{max_v}]")
        return lambda v: normalize(v) == value

    start = normalize(start)
    end = normalize(end)

    if start < min_v or start > max_v or end < min_v or end > max_v:
        raise ValueError(f"Cron range {start}-{end} out of range [{min_v},{max_v}]")
    if end < start:
        raise ValueError(f"Cron range end < start: {start}-{end}")

    def _matches(v: int) -> bool:
        vv = normalize(v)
        if vv < start or vv > end:
            return False
        return ((vv - start) % step) == 0

    return _matches


def _build_field_matcher(token: str, *, min_v: int, max_v: int, normalize: Callable[[int], int]) -> _CronField:
    token = token.strip()
    if token == "" or token == "*":
        return _CronField(match=lambda _v: True)

    parts = [p.strip() for p in token.split(",") if p.strip()]
    if not parts:
        return _CronField(match=lambda _v: True)

    part_matchers = [
        _build_part_matcher(p, min_v=min_v, max_v=max_v, normalize=normalize) for p in parts
    ]

    def _match(v: int) -> bool:
        return any(m(v) for m in part_matchers)

    return _CronField(match=_match)


def _normalize_identity(v: int) -> int:
    return v


def _normalize_dow(v: int) -> int:
    # Support 0-7 where 0 and 7 are Sunday.
    return 7 if v == 0 else v


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
        schedule: str | list[str] = Field(
            "*",
            description=(
                "Cron expression fields (1-5). Missing trailing fields are treated as '*'. "
                "Can be provided as a single string (e.g. '*/10 * * * *') or as multiple args."
            ),
        )

    outputs = PortGroup.outputs(out=OutputPortSpec(BoolPayload, count=1))

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._topic = f"cron.{self.id}"
        fields = _coerce_schedule(config.schedule)

        minute_s, hour_s, dom_s, month_s, dow_s = fields

        # Compile field matchers once.
        self._minute = _build_field_matcher(minute_s, min_v=0, max_v=59, normalize=_normalize_identity)
        self._hour = _build_field_matcher(hour_s, min_v=0, max_v=23, normalize=_normalize_identity)
        self._dom = _build_field_matcher(dom_s, min_v=1, max_v=31, normalize=_normalize_identity)
        self._month = _build_field_matcher(month_s, min_v=1, max_v=12, normalize=_normalize_identity)
        self._dow = _build_field_matcher(dow_s, min_v=1, max_v=7, normalize=_normalize_dow)

        # Output buffer (1x1)
        self._buf = np.zeros((1, 1), dtype=np.bool_)

    async def pull(self, tick: TickContext) -> None:
        now = datetime.now()

        minute = now.minute
        hour = now.hour
        dom = now.day
        month = now.month
        # ISO weekday: Monday=1 .. Sunday=7. This aligns with our dow normalization.
        dow = now.isoweekday()

        matched = (
            self._minute.match(minute)
            and self._hour.match(hour)
            and self._dom.match(dom)
            and self._month.match(month)
            and self._dow.match(dow)
        )

        self._buf[0, 0] = matched

        frame = Frame(
            topic=self._topic,
            timestamp=tick.wall_time,
            payload=BoolPayload(self._buf.copy()),
            metadata=self._metadata,
        )
        self.outputs.out.write(frame)
