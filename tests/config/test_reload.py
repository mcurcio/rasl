"""Live reload: config file changes become updates of the running plan."""

from __future__ import annotations

import os
from pathlib import Path

import anyio
import pytest

from rasl.config.document import ConfigError
from rasl.config.reload import ConfigSession
from rasl.config.watch import watch_config
from rasl.graph.node import ensure_nodes_loaded
from rasl.runtime import Runtime

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


def reload_and_commit(session: ConfigSession):
    """What a caller does when the update needs no runtime: work it out, record it."""
    update = session.reload()
    if update is not None:
        session.commit(update)
    return update


async def until(condition, timeout: float = 3.0) -> None:
    """Wait for ``condition()`` to hold, so no test depends on how fast ticks come."""
    with anyio.fail_after(timeout):
        while not condition():
            await anyio.sleep(0.005)


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
        assert update.changes_graph
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
        assert smooth._tau_seconds == pytest.approx(0.05)  # applied by the runtime, not here
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
        update = reload_and_commit(session)
        assert update is not None
        assert (update.added, update.removed, update.restarted) == ((), ("other",), ())

        edit(config, "graph {\n", "graph {\n    node Waveform extra { output_channels 2; }\n")
        update = reload_and_commit(session)
        assert update is not None
        assert (update.added, update.removed) == (("extra",), ())

        edit(config, "node ConsoleSink out ", "node ConsoleSink console ")
        update = reload_and_commit(session)
        assert update is not None
        assert (update.added, update.removed) == (("console",), ("out",))

    def test_a_changed_type_replaces_the_node(self, config: Path) -> None:
        session = ConfigSession(config)
        edit(
            config,
            "node Smooth smooth { smooth_period 50ms; connect wave input; }",
            # wave has 8 values: 6 of them make two RGB elements (counts are checked at load)
            "node Color smooth rgb { connect wave[0~6]; }",
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
        assert not update.changes_graph  # nothing for the runtime to swap
        assert update.plan is session.plan
        assert update.plan.nodes == before

    def test_reload_does_not_change_the_session_until_commit(self, config: Path) -> None:
        session = ConfigSession(config)
        plan, tree = session.plan, session.tree
        edit(config, "fps 50;", "fps 25;")

        update = session.reload()

        assert update is not None
        assert (session.plan, session.tree) == (plan, tree)
        again = session.reload()  # never applied, so it is worked out again
        assert again is not None and again.restarted == ("out",)

        session.commit(again)
        assert (session.plan, session.tree) == (again.plan, again.tree)
        assert session.reload() is None

    def test_a_failed_reload_still_watches_the_files_it_read(self, tmp_path: Path) -> None:
        main = tmp_path / "main.conf"
        main.write_text("graph {\n    node Waveform wave { fps 30; }\n}\n")
        porch = tmp_path / "porch.conf"
        porch.write_text("node ConsoleSink out { fps 1 connect wave; }\n")  # a missing ;
        session = ConfigSession(main)
        assert session.watched == (str(main),)

        edit(main, "graph {\n", 'graph {\n    @include "porch.conf";\n')
        with pytest.raises(ConfigError) as failed:
            session.reload()

        assert failed.value.documents == (str(main), str(porch))
        assert session.documents == (str(main),)  # what runs is unchanged
        assert session.watched == (str(main), str(porch))  # but the fix will be seen

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
            ("connect wave input;", "connect nowhere input;", ConfigError),  # an unknown node, placed on the node that connects to it
        ],
    )
    def test_a_failed_reload_changes_nothing(
        self, config: Path, old: str, new: str, error: type[Exception]
    ) -> None:
        session = ConfigSession(config)
        plan, tree = session.plan, session.tree
        edges = dict(plan.adjacency)
        edit(config, old, new)

        with pytest.raises(error):
            session.reload()

        assert session.plan is plan
        assert session.tree is tree
        assert dict(plan.adjacency) == edges

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


async def run_then(runtime: Runtime, body) -> None:
    """Run the runtime, run ``body`` beside it once every node has started, then
    shut the runtime down."""
    async with anyio.create_task_group() as tg:
        tg.start_soon(runtime.run)
        await until(lambda: len(runtime.nodes) == len(runtime.plan.nodes))
        await body()
        tg.cancel_scope.cancel()


async def apply(runtime: Runtime, session: ConfigSession):
    """Reload, hand the update to the running runtime, and record it."""
    update = session.reload()
    assert update is not None
    with anyio.fail_after(3):
        await runtime.request_update(update).wait()
    if runtime.plan is update.plan:
        session.commit(update)
    return update


class TestMetricsOnReload:
    """A reload drops removed nodes' metrics, restarts the count of restarted ones,
    and keeps the counts of nodes updated in place."""

    async def test_removed_restarted_and_updated_nodes(self, tmp_path: Path) -> None:
        path = tmp_path / "metrics.conf"
        path.write_text(
            "graph {\n"
            "    node Waveform wave { output_channels 4; }\n"
            "    node Smooth smooth { smooth_period 50ms; connect wave input; }\n"
            "    node ConsoleSink out { fps 100; connect smooth; }\n"
            "    node ConsoleSink gone { fps 100; connect wave; }\n"
            "}\n"
        )
        session = ConfigSession(path)
        runtime = Runtime(session.plan)

        def count(node_id: str) -> int:
            stats = runtime.monitor.get_stats(node_id)
            return 0 if stats is None else stats.handle_count

        async def body() -> None:
            await until(lambda: min(count(n) for n in ("wave", "smooth", "gone")) >= 5)
            edit(path, "output_channels 4;", "output_channels 6;")  # wave restarts
            edit(path, "smooth_period 50ms;", "smooth_period 2s;")  # smooth updates in place
            edit(path, "    node ConsoleSink gone { fps 100; connect wave; }\n", "")
            before = count("smooth")
            update = await apply(runtime, session)
            assert "wave" in update.restarted and "smooth" in update.updated
            assert "gone" not in runtime.monitor.get_all_stats()
            assert count("smooth") >= before  # kept
            assert count("wave") < 5  # counted from zero since the restart

        await run_then(runtime, body)


class TestSchedulerUpdate:
    """Runtime.request_update: the swap at a tick boundary."""

    async def test_an_update_stops_starts_and_updates_only_what_changed(
        self, config: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session = ConfigSession(config)
        runtime = Runtime(session.plan)
        recorder = Recorder(monkeypatch, session.plan.nodes)
        smooth = session.plan.nodes["smooth"]

        async def body() -> None:
            await until(lambda: smooth._state is not None)  # it has run
            ticks = runtime.scheduler.tick_count
            recorder.events.clear()
            edit(config, "fps 50;", "fps 100;")
            edit(config, "smooth_period 50ms;", "smooth_period 2s;")
            edit(config, "    node Waveform other { output_channels 4; }\n", "")
            edit(config, "graph {\n", "graph {\n    node Waveform extra { output_channels 2; }\n")
            update = await apply(runtime, session)

            assert sorted(recorder.events) == [
                ("start", "extra"),
                ("start", "out"),
                ("stop", "other"),
                ("stop", "out"),
                ("update", "smooth"),
            ]
            assert runtime.plan is update.plan
            assert runtime.rate_drivers == {"out": 100.0}
            assert set(runtime.nodes) == {"wave", "smooth", "out", "extra"}
            assert smooth._tau_seconds == pytest.approx(2.0)
            assert smooth._state is not None  # the running state survived

            out = runtime.plan.nodes["out"]  # and the graph still ticks, at the new rate
            await until(lambda: runtime.scheduler.tick_count > ticks and out._counter > 0)

        await run_then(runtime, body)
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
        runtime = Runtime(session.plan)
        out = session.plan.nodes["out"]

        def reads() -> list[float] | None:
            frame = out.inputs.dmx.read()
            return None if frame is None else [float(x) for x in frame.payload.data.reshape(-1)]

        async def body() -> None:
            await until(lambda: reads() == [1.0, 1.0])
            edit(path, "connect ones;", "connect twos;")
            update = await apply(runtime, session)
            assert update.rerouted == ("out",)
            assert runtime.plan.nodes["out"] is out
            await until(lambda: reads() == [2.0, 2.0])

            # A connection taken away leaves nothing behind on the port
            edit(path, " connect twos;", "")
            update = await apply(runtime, session)
            assert update.rerouted == ("out",)
            assert reads() is None and not out.inputs.dmx.connected

        await run_then(runtime, body)

    async def test_a_stopped_node_leaves_no_background_task_writing(self, tmp_path: Path) -> None:
        path = tmp_path / "main.conf"
        path.write_text(
            "graph {\n"
            "    node SineSource wave { output_channels 2; fps 200; topic before; }\n"
            "    node ConsoleSink out { fps 100; connect wave; }\n"
            "}\n"
        )
        session = ConfigSession(path)
        runtime = Runtime(session.plan)

        def topic() -> str | None:
            frame = runtime.executor.latest.get(("wave", "dmx"))
            return None if frame is None else frame.topic

        async def body() -> None:
            await until(lambda: topic() == "before")
            old = runtime.nodes["wave"]  # its start() runs a loop its stop() never ends
            assert len(old.background) == 1

            edit(path, "topic before;", "topic after;")
            update = await apply(runtime, session)
            assert update.restarted == ("wave",)
            assert runtime.nodes["wave"] is not old
            assert all(scope.cancel_called for scope in old.background)

            await until(lambda: topic() == "after")
            seen = set()
            for _ in range(20):  # twenty periods of the old loop, had it lived
                await anyio.sleep(0.005)
                seen.add(topic())
            assert seen == {"after"}

        await run_then(runtime, body)

    async def test_an_update_the_scheduler_cannot_schedule_is_refused_whole(
        self, config: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session = ConfigSession(config)
        runtime = Runtime(session.plan)
        recorder = Recorder(monkeypatch, session.plan.nodes)

        async def body() -> None:
            plan, ticks = runtime.plan, runtime.scheduler.tick_count
            recorder.events.clear()
            edit(config, "fps 50;", "fps 25;")
            update = session.reload()
            assert update is not None
            # A sink whose rate cannot be read once it is in the plan
            monkeypatch.setattr(type(update.plan.nodes["out"]), "_fps", None, raising=False)
            update.plan.nodes["out"]._fps = "not a rate"
            with anyio.fail_after(3):
                await runtime.request_update(update).wait()

            assert runtime.plan is plan  # the old plan goes on
            assert recorder.events == []  # nothing was stopped or started
            assert runtime.rate_drivers == {"out": 50.0}
            await until(lambda: runtime.scheduler.tick_count > ticks)
            assert session.plan is plan  # and the session was not told otherwise

        await run_then(runtime, body)

    async def test_an_update_can_add_the_first_sink_and_remove_the_last(self, tmp_path: Path) -> None:
        path = tmp_path / "main.conf"
        path.write_text("graph {\n    node Waveform wave { fps 30; }\n}\n")
        session = ConfigSession(path)
        runtime = Runtime(session.plan)
        sink = "    node ConsoleSink out { fps 100; connect wave; }\n"

        async def body() -> None:
            assert runtime.rate_drivers == {}  # nothing drives a tick yet
            edit(path, "}\n}\n", "}\n" + sink + "}\n")
            await apply(runtime, session)
            await until(lambda: runtime.scheduler.tick_count > 0)

            edit(path, sink, "")
            await apply(runtime, session)
            ticks = runtime.scheduler.tick_count
            await anyio.sleep(0.05)  # five periods of the sink that is gone
            assert runtime.rate_drivers == {} and runtime.scheduler.tick_count == ticks

        await run_then(runtime, body)

    async def test_a_second_update_before_the_first_is_applied_is_refused(self, config: Path) -> None:
        session = ConfigSession(config)
        runtime = Runtime(session.plan)
        edit(config, "fps 50;", "fps 25;")
        update = session.reload()
        assert update is not None

        runtime.request_update(update)  # not running: nothing applies it
        with pytest.raises(RuntimeError, match="already waiting"):
            runtime.request_update(update)


class TestWatch:
    """watch_config: a saved file reaches the running graph; a broken one does not."""

    async def test_a_saved_change_is_applied_and_a_broken_one_is_reported(
        self, config: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        session = ConfigSession(config)
        runtime = Runtime(session.plan)

        def save(old: str, new: str) -> None:
            edit(config, old, new)
            # A save within the same clock tick as the last look must still be seen
            stamp = os.stat(config).st_mtime_ns + 1_000_000
            os.utime(config, ns=(stamp, stamp))

        async def body() -> None:
            assert session.last_reload is None  # nothing attempted yet
            save("fps 50;", "fps 25;")
            await until(lambda: runtime.rate_drivers == {"out": 25.0})
            await until(lambda: session.plan is runtime.plan)  # committed once applied
            await until(lambda: session.last_reload is not None)
            assert session.last_reload.ok and session.last_reload.error is None

            save("fps 25;", "fps 25")  # broken: the graph must keep running as it was
            await until(lambda: "Config reload failed" in capsys.readouterr().err)
            assert session.last_reload is not None and not session.last_reload.ok
            assert session.last_reload.error
            plan = runtime.plan
            ticks = runtime.scheduler.tick_count
            await until(lambda: runtime.scheduler.tick_count > ticks)
            assert runtime.plan is plan

            save("fps 25 ", "fps 10; ")  # fixed: the next save applies
            await until(lambda: runtime.rate_drivers == {"out": 10.0})
            await until(lambda: session.last_reload is not None and session.last_reload.ok)

            save("port 8080;", "port 9090;")  # outside any node: recorded, nothing swapped
            plan = runtime.plan
            await until(lambda: session.tree.block.directives("ui")[0].block[0].values[0].text == "9090")
            assert runtime.plan is plan and session.plan is plan

        async with anyio.create_task_group() as tg:
            tg.start_soon(runtime.run)
            tg.start_soon(lambda: watch_config(session, runtime, interval=0.02))
            await until(lambda: len(runtime.nodes) == len(runtime.plan.nodes))
            await body()
            tg.cancel_scope.cancel()

    async def test_a_save_made_while_a_reload_runs_is_not_lost(
        self, config: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session = ConfigSession(config)
        runtime = Runtime(session.plan)
        reload = session.reload
        saved_during = []

        def slow_reload():
            update = reload()  # reads the file ...
            if not saved_during:  # ... and the next save lands before it returns
                edit(config, "fps 25;", "fps 10;")
                stamp = os.stat(config).st_mtime_ns + 5_000_000
                os.utime(config, ns=(stamp, stamp))
                saved_during.append(True)
            return update

        monkeypatch.setattr(session, "reload", slow_reload)

        async with anyio.create_task_group() as tg:
            tg.start_soon(runtime.run)
            tg.start_soon(lambda: watch_config(session, runtime, interval=0.02))
            await until(lambda: len(runtime.nodes) == len(runtime.plan.nodes))
            edit(config, "fps 50;", "fps 25;")
            stamp = os.stat(config).st_mtime_ns + 1_000_000
            os.utime(config, ns=(stamp, stamp))
            await until(lambda: runtime.rate_drivers == {"out": 10.0})
            tg.cancel_scope.cancel()


class TestRestartOnWiringChange:
    """A node class that opts in is restarted when another node's connect line rewires it."""

    def _wire_other_into_out(self, config: Path) -> object:
        session = ConfigSession(config)
        edit(config, "connect smooth; }", "connect smooth dmx[0~8]; connect other dmx[8~12]; }")
        return session.reload()

    def test_a_node_that_does_not_opt_in_keeps_running(self, config: Path) -> None:
        update = self._wire_other_into_out(config)
        assert "other" not in update.restarted
        assert update.rerouted == ("out",)

    def test_a_node_that_opts_in_is_restarted_when_it_gains_a_consumer(
        self, config: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from rasl.nodes.effects.waveform import WaveformNode

        monkeypatch.setattr(WaveformNode, "restart_on_wiring_change", True)
        update = self._wire_other_into_out(config)
        assert update.restarted == ("other",)
        assert update.rerouted == ("out",)
        assert "wave" not in update.restarted  # its wiring did not change


def test_a_node_updated_in_place_whose_wiring_changes_is_restarted(config: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Review round: restart_on_wiring_change covers nodes with update_config too."""
    from rasl.nodes.effects.smooth import SmoothNode

    monkeypatch.setattr(SmoothNode, "restart_on_wiring_change", True)
    session = ConfigSession(config)
    edit(config, "smooth_period 50ms; connect wave input; }", "smooth_period 80ms; connect wave input; connect other reset; }")
    update = session.reload()
    assert "smooth" in update.restarted
    assert "smooth" not in update.updated
