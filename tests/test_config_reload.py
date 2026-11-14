"""Live reload: config file changes become updates of the running plan."""

from __future__ import annotations

import os
from pathlib import Path

import anyio
import pytest

from rasl.config.dispatch import ConfigError
from rasl.config.reload import ConfigSession
from rasl.engine.registry import ensure_nodes_loaded
from rasl.runtime import UnifiedScheduler, watch_config

BASE = """\
@set $channels 8;
ui { port 8080; }
graph {
    node Waveform wave { output_channels $channels; fps 30; }
    node Waveform other { output_channels 4; }
    node Smooth smooth { smooth_period 50ms; connect wave input; }
    node ConsoleSink out { fps 50; connect smooth; }
}
"""


@pytest.fixture(autouse=True)
def setup_nodes():
    import rasl.nodes  # noqa: F401

    ensure_nodes_loaded()
    yield


@pytest.fixture
def config(tmp_path: Path) -> Path:
    path = tmp_path / "main.conf"
    path.write_text(BASE)
    return path


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new))


class TestReload:
    """ConfigSession.reload: what each kind of edit does to the plan."""

    def test_a_comment_or_layout_change_is_no_update(self, config: Path) -> None:
        session = ConfigSession(config)
        plan = session.plan
        edit(config, "fps 30; }", "fps 30; }   # thirty frames a second")

        assert session.reload() is None
        assert session.plan is plan

    def test_a_changed_setting_restarts_that_node_and_keeps_the_rest(self, config: Path) -> None:
        session = ConfigSession(config)
        before = dict(session.plan.nodes)
        edit(config, "fps 50;", "fps 25;")

        update = session.reload()

        assert update is not None
        assert (update.added, update.removed, update.restarted) == ((), (), ("out",))
        assert update.changes == ('changed graph > node "out" > fps',)
        assert update.plan is session.plan
        assert update.plan.nodes["out"] is not before["out"]
        assert update.plan.nodes["out"]._fps == 25
        for kept in ("wave", "other", "smooth"):
            assert update.plan.nodes[kept] is before[kept]

    def test_a_variable_change_reaches_the_nodes_that_read_it(self, config: Path) -> None:
        session = ConfigSession(config)
        edit(config, "@set $channels 8;", "@set $channels 16;")

        update = session.reload()

        assert update is not None
        assert update.restarted == ("wave",)
        assert update.plan.nodes["wave"]._channels == 16

    def test_a_node_that_defines_update_config_is_updated_in_place(self, config: Path) -> None:
        session = ConfigSession(config)
        smooth = session.plan.nodes["smooth"]
        edit(config, "smooth_period 50ms;", "smooth_period 2s;")

        update = session.reload()

        assert update is not None
        assert update.restarted == ()
        assert list(update.updated) == ["smooth"]
        assert update.plan.nodes["smooth"] is smooth
        assert smooth._tau_seconds == pytest.approx(0.05)  # applied by the scheduler, not here
        smooth.update_config(update.updated["smooth"])
        assert smooth._tau_seconds == pytest.approx(2.0)

    def test_a_changed_connection_reroutes_without_a_restart(self, config: Path) -> None:
        session = ConfigSession(config)
        before = dict(session.plan.nodes)
        edit(config, "connect wave input;", "connect other input;")

        update = session.reload()

        assert update is not None
        assert (update.restarted, update.rerouted) == ((), ("smooth",))
        assert update.plan.nodes == before
        assert [e.target for e in update.plan.adjacency["other"]] == ["smooth"]
        assert update.plan.adjacency.get("wave", []) == []

    def test_added_removed_and_renamed_nodes(self, config: Path) -> None:
        session = ConfigSession(config)
        edit(config, "    node Waveform other { output_channels 4; }\n", "")
        update = session.reload()
        assert update is not None
        assert (update.added, update.removed, update.restarted) == ((), ("other",), ())

        edit(config, "graph {\n", "graph {\n    node Waveform extra { output_channels 2; }\n")
        update = session.reload()
        assert update is not None
        assert (update.added, update.removed) == (("extra",), ())

        edit(config, "node ConsoleSink out ", "node ConsoleSink console ")
        update = session.reload()
        assert update is not None
        assert (update.added, update.removed) == (("console",), ("out",))

    def test_a_changed_type_replaces_the_node(self, config: Path) -> None:
        session = ConfigSession(config)
        edit(
            config,
            "node Smooth smooth { smooth_period 50ms; connect wave input; }",
            "node Color smooth rgb { connect wave; }",
        )

        update = session.reload()

        assert update is not None
        assert (update.restarted, list(update.updated)) == (("smooth",), [])
        assert type(update.plan.nodes["smooth"]).__name__ == "ColorNode"

    def test_moving_a_node_changes_nothing(self, config: Path) -> None:
        session = ConfigSession(config)
        other = "    node Waveform other { output_channels 4; }\n"
        edit(config, other, "")
        edit(config, "graph {\n", "graph {\n" + other)

        assert session.reload() is None

    def test_a_change_outside_the_graph_is_reported_as_ignored(self, config: Path) -> None:
        session = ConfigSession(config)
        before = dict(session.plan.nodes)
        edit(config, "port 8080;", "port 9090;")

        update = session.reload()

        assert update is not None
        assert update.ignored == ("changed ui > port",)
        assert (update.added, update.removed, update.restarted, update.rerouted) == ((), (), (), ())
        assert update.plan.nodes == before

    def test_an_included_file_is_part_of_the_config(self, tmp_path: Path) -> None:
        main = tmp_path / "main.conf"
        main.write_text('graph {\n    @include "sink.conf";\n    node Waveform wave { fps 30; }\n}\n')
        sink = tmp_path / "sink.conf"
        sink.write_text("node ConsoleSink out { fps 1; connect wave; }\n")
        session = ConfigSession(main)
        assert session.documents == (str(main), str(sink))

        edit(sink, "fps 1;", "fps 2;")
        update = session.reload()

        assert update is not None
        assert update.restarted == ("out",)

    @pytest.mark.parametrize(
        ("old", "new", "error"),
        [
            ("fps 50;", "fps 50", ConfigError),  # a syntax slip, read as a bad value
            ("fps 30; }", "fps 30;", ConfigError),  # an unclosed block
            ("node Waveform other", "node Mystery other", ConfigError),
            ("connect wave input;", "connect nowhere input;", KeyError),
        ],
    )
    def test_a_failed_reload_changes_nothing(
        self, config: Path, old: str, new: str, error: type[Exception]
    ) -> None:
        session = ConfigSession(config)
        plan, tree = session.plan, session.tree
        descriptors = {i: n.get_connection_descriptors() for i, n in plan.nodes.items()}
        edit(config, old, new)

        with pytest.raises(error):
            session.reload()

        assert session.plan is plan
        assert session.tree is tree
        assert {i: n.get_connection_descriptors() for i, n in plan.nodes.items()} == descriptors

        config.write_text(BASE)  # and the next good file loads as if nothing happened
        assert session.reload() is None


class Recorder:
    """Records each node's start, stop and update_config by patching the classes."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, plan_nodes: dict) -> None:
        self.events: list[tuple[str, str]] = []
        for cls in {type(node) for node in plan_nodes.values()}:
            self._wrap(monkeypatch, cls)

    def _wrap(self, monkeypatch: pytest.MonkeyPatch, cls: type) -> None:
        events = self.events
        start, stop = cls.start, cls.stop

        async def recorded_start(node, ctx):
            events.append(("start", node.id))
            await start(node, ctx)

        async def recorded_stop(node, ctx):
            events.append(("stop", node.id))
            await stop(node, ctx)

        monkeypatch.setattr(cls, "start", recorded_start)
        monkeypatch.setattr(cls, "stop", recorded_stop)
        if hasattr(cls, "update_config"):
            update_config = cls.update_config

            def recorded_update(node, config):
                events.append(("update", node.id))
                update_config(node, config)

            monkeypatch.setattr(cls, "update_config", recorded_update)


async def run_then(scheduler: UnifiedScheduler, body) -> None:
    """Run the scheduler, run ``body`` beside it, then shut the scheduler down."""
    async with anyio.create_task_group() as tg:
        tg.start_soon(scheduler.run)
        await anyio.sleep(0.1)
        await body()
        tg.cancel_scope.cancel()


class TestSchedulerUpdate:
    """UnifiedScheduler.request_update: the swap at a tick boundary."""

    async def test_an_update_stops_starts_and_updates_only_what_changed(
        self, config: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session = ConfigSession(config)
        scheduler = UnifiedScheduler(session.plan)
        recorder = Recorder(monkeypatch, session.plan.nodes)
        smooth = session.plan.nodes["smooth"]

        async def body() -> None:
            ticks = scheduler._tick
            assert ticks > 0
            recorder.events.clear()
            edit(config, "fps 50;", "fps 100;")
            edit(config, "smooth_period 50ms;", "smooth_period 2s;")
            edit(config, "    node Waveform other { output_channels 4; }\n", "")
            edit(config, "graph {\n", "graph {\n    node Waveform extra { output_channels 2; }\n")
            update = session.reload()
            assert update is not None
            with anyio.fail_after(2):
                await scheduler.request_update(update).wait()

            assert sorted(recorder.events) == [
                ("start", "extra"),
                ("start", "out"),
                ("stop", "other"),
                ("stop", "out"),
                ("update", "smooth"),
            ]
            assert scheduler.plan is update.plan
            assert scheduler._rate_drivers == {"out": 100.0}
            assert set(scheduler._node_runtimes) == {"wave", "smooth", "out", "extra"}
            assert smooth._tau_seconds == pytest.approx(2.0)
            assert smooth._state is not None  # the running state survived

            await anyio.sleep(0.1)
            assert scheduler._tick > ticks  # and the graph still ticks, at the new rate
            out = scheduler.plan.nodes["out"]
            assert out._counter > 0

        await run_then(scheduler, body)
        assert ("stop", "extra") in recorder.events  # shutdown stops what the update started

    async def test_a_reroute_changes_what_a_running_node_reads(self, tmp_path: Path) -> None:
        path = tmp_path / "main.conf"
        path.write_text(
            "graph {\n"
            "    node literal ones matrix [[1, 1]];\n"
            "    node literal twos matrix [[2, 2]];\n"
            "    node ConsoleSink out { fps 100; connect ones; }\n"
            "}\n"
        )
        session = ConfigSession(path)
        scheduler = UnifiedScheduler(session.plan)
        out = session.plan.nodes["out"]

        def reads() -> list[float]:
            frame = out.inputs.dmx.read()
            assert frame is not None
            return [float(x) for x in frame.payload.data.reshape(-1)]

        async def body() -> None:
            assert reads() == [1.0, 1.0]
            edit(path, "connect ones;", "connect twos;")
            update = session.reload()
            assert update is not None and update.rerouted == ("out",)
            with anyio.fail_after(2):
                await scheduler.request_update(update).wait()
            await anyio.sleep(0.05)
            assert scheduler.plan.nodes["out"] is out
            assert reads() == [2.0, 2.0]

        await run_then(scheduler, body)

    async def test_an_update_can_add_the_first_sink_and_remove_the_last(self, tmp_path: Path) -> None:
        path = tmp_path / "main.conf"
        path.write_text("graph {\n    node Waveform wave { fps 30; }\n}\n")
        session = ConfigSession(path)
        scheduler = UnifiedScheduler(session.plan)
        sink = "    node ConsoleSink out { fps 100; connect wave; }\n"

        async def body() -> None:
            assert scheduler._schedule == []  # nothing drives a tick yet
            edit(path, "}\n}\n", "}\n" + sink + "}\n")
            with anyio.fail_after(2):
                await scheduler.request_update(session.reload()).wait()
            await anyio.sleep(0.1)
            assert scheduler._tick > 0

            edit(path, sink, "")
            with anyio.fail_after(2):
                await scheduler.request_update(session.reload()).wait()
            ticks = scheduler._tick
            await anyio.sleep(0.1)
            assert scheduler._schedule == [] and scheduler._tick == ticks

        await run_then(scheduler, body)

    async def test_a_second_update_before_the_first_is_applied_is_refused(self, config: Path) -> None:
        session = ConfigSession(config)
        scheduler = UnifiedScheduler(session.plan)
        edit(config, "fps 50;", "fps 25;")
        update = session.reload()
        assert update is not None

        scheduler.request_update(update)  # not running: nothing applies it
        with pytest.raises(RuntimeError, match="already waiting"):
            scheduler.request_update(update)


class TestWatch:
    """watch_config: a saved file reaches the running graph; a broken one does not."""

    async def test_a_saved_change_is_applied_and_a_broken_one_is_reported(
        self, config: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        session = ConfigSession(config)
        scheduler = UnifiedScheduler(session.plan)

        def save(old: str, new: str) -> None:
            edit(config, old, new)
            # A save within the same clock tick as the last look must still be seen
            stamp = os.stat(config).st_mtime_ns + 1_000_000
            os.utime(config, ns=(stamp, stamp))

        async def until(condition, what: str) -> None:
            with anyio.fail_after(3):
                while not condition():
                    await anyio.sleep(0.01)

        async def body() -> None:
            save("fps 50;", "fps 25;")
            await until(lambda: scheduler._rate_drivers == {"out": 25.0}, "the new rate")

            save("fps 25;", "fps 25")  # broken: the graph must keep running as it was
            await until(lambda: "Config reload failed" in capsys.readouterr().err, "the report")
            plan = scheduler.plan
            ticks = scheduler._tick
            await anyio.sleep(0.1)
            assert scheduler.plan is plan and scheduler._tick > ticks

            save("fps 25 ", "fps 10; ")  # fixed: the next save applies
            await until(lambda: scheduler._rate_drivers == {"out": 10.0}, "the fixed rate")

        async with anyio.create_task_group() as tg:
            tg.start_soon(scheduler.run)
            tg.start_soon(lambda: watch_config(session, scheduler, interval=0.02))
            await anyio.sleep(0.1)
            await body()
            tg.cancel_scope.cancel()
