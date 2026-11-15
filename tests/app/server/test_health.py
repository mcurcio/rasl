"""Server health: when the graph counts as stalled or degraded, and what /health answers."""

from __future__ import annotations

import json

import pytest

from rasl.app.server.app import health_response
from rasl.app.server.health import (
    MIN_STALL_SECONDS,
    HealthReport,
    HealthStatus,
    assess,
    stall_threshold,
)
from rasl.config import ReloadOutcome

NOW = 1000.0


def _assess(**overrides: object) -> HealthReport:
    """``assess`` for a graph ticking at 30 Hz that last ticked 10 ms ago, with overrides."""
    args: dict[str, object] = {
        "rates": {"out": 30.0},
        "tick_count": 42,
        "last_tick_at": NOW - 0.01,
        "run_started_at": NOW - 60.0,
        "disabled_nodes": (),
        "last_reload": None,
        "uptime_seconds": 60.0,
        "now": NOW,
    }
    args.update(overrides)
    return assess(**args)  # type: ignore[arg-type]


class TestStallThreshold:
    def test_no_rate_driver_cannot_stall(self) -> None:
        assert stall_threshold({}) is None

    def test_a_fast_graph_gets_the_minimum(self) -> None:
        assert stall_threshold({"a": 30.0, "b": 60.0}) == MIN_STALL_SECONDS

    def test_a_slow_driver_gets_ten_of_its_periods(self) -> None:
        # The slowest driver sets it: 0.5 Hz is a 2 s period, so 20 s
        assert stall_threshold({"fast": 30.0, "slow": 0.5}) == pytest.approx(20.0)


class TestAssess:
    def test_a_ticking_graph_is_ok(self) -> None:
        report = _assess()
        assert report.status is HealthStatus.OK
        assert report.tick_count == 42
        assert report.last_tick_age_seconds == pytest.approx(0.01)
        assert report.stall_after_seconds == MIN_STALL_SECONDS

    def test_no_tick_for_longer_than_the_threshold_is_stalled(self) -> None:
        assert _assess(last_tick_at=NOW - 6.0).status is HealthStatus.STALLED

    def test_no_tick_yet_counts_from_when_the_scheduler_began(self) -> None:
        assert _assess(last_tick_at=None, run_started_at=NOW - 1.0).status is HealthStatus.OK
        assert _assess(last_tick_at=None, run_started_at=NOW - 6.0).status is HealthStatus.STALLED

    def test_a_scheduler_that_just_resumed_is_not_stalled_by_an_old_tick(self) -> None:
        # Idle for a minute with no rate driver, then a plan update added one
        report = _assess(last_tick_at=NOW - 60.0, run_started_at=NOW - 0.5)
        assert report.status is HealthStatus.OK

    def test_a_scheduler_not_yet_running_is_not_stalled(self) -> None:
        # Nodes still starting (e.g. connecting to devices)
        report = _assess(last_tick_at=None, run_started_at=0.0)
        assert report.status is HealthStatus.OK

    def test_a_graph_with_no_rate_driver_is_never_stalled(self) -> None:
        report = _assess(rates={}, tick_count=0, last_tick_at=None)
        assert report.status is HealthStatus.OK
        assert report.stall_after_seconds is None
        assert report.last_tick_age_seconds is None

    def test_a_disabled_node_is_degraded(self) -> None:
        report = _assess(disabled_nodes={"wled", "dmx"})
        assert report.status is HealthStatus.DEGRADED
        assert report.disabled_nodes == ("dmx", "wled")

    def test_a_failed_reload_is_degraded_and_says_why(self) -> None:
        report = _assess(last_reload=ReloadOutcome(ok=False, at=1.5, error="bad line"))
        assert report.status is HealthStatus.DEGRADED
        assert (report.last_reload_ok, report.last_reload_error, report.last_reload_at) == (
            False,
            "bad line",
            1.5,
        )

    def test_a_successful_reload_is_ok(self) -> None:
        report = _assess(last_reload=ReloadOutcome(ok=True, at=2.0))
        assert report.status is HealthStatus.OK and report.last_reload_ok is True

    def test_stalled_wins_over_degraded(self) -> None:
        report = _assess(last_tick_at=NOW - 30.0, disabled_nodes={"dmx"})
        assert report.status is HealthStatus.STALLED


class _State:
    """Stands in for AppState: only ``health()`` is read."""

    def __init__(self, report: HealthReport) -> None:
        self._report = report

    def health(self) -> HealthReport:
        return self._report


class TestHealthResponse:
    @pytest.mark.parametrize(
        ("overrides", "code", "status"),
        [
            ({}, 200, "ok"),
            ({"disabled_nodes": {"dmx"}}, 200, "degraded"),
            ({"last_tick_at": NOW - 30.0}, 503, "stalled"),
        ],
    )
    def test_only_a_stall_answers_503(self, overrides: dict, code: int, status: str) -> None:
        response = health_response(_State(_assess(**overrides)))  # type: ignore[arg-type]
        assert response.status_code == code
        body = json.loads(response.body)
        assert body["status"] == status
        assert set(body) == {
            "status",
            "uptime_seconds",
            "tick_count",
            "last_tick_age_seconds",
            "stall_after_seconds",
            "disabled_nodes",
            "last_reload_ok",
            "last_reload_error",
            "last_reload_at",
        }
