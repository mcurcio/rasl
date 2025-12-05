"""Unit tests for the Runtime scheduler."""

from typing import Any, List, Tuple
from unittest.mock import AsyncMock

import anyio
import numpy as np
import pytest

from rasl.engine.frame import Frame
from rasl.engine.graph import GraphBuilder
from rasl.engine.node import NodeContext
from rasl.runtime import Runtime


class RecordingSourceNode:
    """Source node that emits a fixed sequence of frames."""

    inputs: Tuple[str, ...] = ()
    outputs: Tuple[str, ...] = ("output",)

    def __init__(self, node_id: str, frames: List[Frame]) -> None:
        """Initialize with frames to emit."""
        self.id = node_id
        self._frames = frames
        self.started = False
        self.stopped = False

    async def start(self, ctx: NodeContext) -> None:
        """Start and emit all frames."""
        self.started = True
        for frame in self._frames:
            await ctx.emit("output", frame)

    async def handle(self, port: str, frame: Frame, ctx: NodeContext) -> None:
        """No-op for source."""
        pass

    async def stop(self, ctx: NodeContext) -> None:
        """Record stop."""
        self.stopped = True


class RecordingSinkNode:
    """Sink node that records received frames."""

    inputs: Tuple[str, ...] = ("input",)
    outputs: Tuple[str, ...] = ()

    def __init__(self, node_id: str) -> None:
        """Initialize the recording sink."""
        self.id = node_id
        self.received_frames: List[Frame] = []
        self.started = False
        self.stopped = False

    async def start(self, ctx: NodeContext) -> None:
        """Record start."""
        self.started = True

    async def handle(self, port: str, frame: Frame, ctx: NodeContext) -> None:
        """Record received frame."""
        self.received_frames.append(frame)

    async def stop(self, ctx: NodeContext) -> None:
        """Record stop."""
        self.stopped = True


class PassthroughNode:
    """Transform node that passes frames through unchanged."""

    inputs: Tuple[str, ...] = ("input",)
    outputs: Tuple[str, ...] = ("output",)

    def __init__(self, node_id: str) -> None:
        """Initialize passthrough node."""
        self.id = node_id
        self.processed_count = 0

    async def start(self, ctx: NodeContext) -> None:
        """No-op start."""
        pass

    async def handle(self, port: str, frame: Frame, ctx: NodeContext) -> None:
        """Pass frame through."""
        self.processed_count += 1
        await ctx.emit("output", frame)

    async def stop(self, ctx: NodeContext) -> None:
        """No-op stop."""
        pass


class TestRuntime:
    """Tests for the Runtime class."""

    def test_runtime_init(self) -> None:
        """Test runtime initialization."""
        builder = GraphBuilder()
        source = RecordingSourceNode("source", [])
        builder.add_node(source)
        plan = builder.build()

        runtime = Runtime(plan)

        assert runtime._plan is plan

    @pytest.mark.asyncio
    async def test_runtime_starts_and_stops_nodes(self) -> None:
        """Test that runtime calls start and stop on nodes."""
        frames = [
            Frame(
                topic="test",
                timestamp=1.0,
                payload=np.zeros(10, dtype=np.float32),
            )
        ]
        source = RecordingSourceNode("source", frames)
        sink = RecordingSinkNode("sink")

        builder = GraphBuilder()
        builder.add_node(source)
        builder.add_node(sink)
        builder.connect("source", "output", "sink", "input")
        plan = builder.build()

        runtime = Runtime(plan)

        # Run with timeout to avoid hanging
        with anyio.move_on_after(0.5):
            await runtime.run()

        assert source.started
        assert sink.started

    @pytest.mark.asyncio
    async def test_runtime_routes_frames(self) -> None:
        """Test that runtime routes frames between nodes."""
        test_frame = Frame(
            topic="test",
            timestamp=1.0,
            payload=np.array([0.5, 0.6, 0.7], dtype=np.float32),
            metadata={"key": "value"},
        )
        source = RecordingSourceNode("source", [test_frame])
        sink = RecordingSinkNode("sink")

        builder = GraphBuilder()
        builder.add_node(source)
        builder.add_node(sink)
        builder.connect("source", "output", "sink", "input")
        plan = builder.build()

        runtime = Runtime(plan)

        # Run briefly
        with anyio.move_on_after(0.5):
            await runtime.run()

        # Check frame was received
        assert len(sink.received_frames) >= 1
        received = sink.received_frames[0]
        assert received.topic == "test"
        assert received.metadata["key"] == "value"
        assert np.array_equal(received.payload, test_frame.payload)

    @pytest.mark.asyncio
    async def test_runtime_chain(self) -> None:
        """Test runtime with source -> transform -> sink chain."""
        test_frame = Frame(
            topic="test",
            timestamp=1.0,
            payload=np.zeros(5, dtype=np.float32),
        )
        source = RecordingSourceNode("source", [test_frame])
        transform = PassthroughNode("transform")
        sink = RecordingSinkNode("sink")

        builder = GraphBuilder()
        builder.add_node(source)
        builder.add_node(transform)
        builder.add_node(sink)
        builder.connect("source", "output", "transform", "input")
        builder.connect("transform", "output", "sink", "input")
        plan = builder.build()

        runtime = Runtime(plan)

        with anyio.move_on_after(0.5):
            await runtime.run()

        assert transform.processed_count >= 1
        assert len(sink.received_frames) >= 1

    @pytest.mark.asyncio
    async def test_runtime_fan_out(self) -> None:
        """Test runtime with fan-out (one source, multiple sinks)."""
        test_frame = Frame(
            topic="test",
            timestamp=1.0,
            payload=np.zeros(5, dtype=np.float32),
        )
        source = RecordingSourceNode("source", [test_frame])
        sink1 = RecordingSinkNode("sink1")
        sink2 = RecordingSinkNode("sink2")

        builder = GraphBuilder()
        builder.add_node(source)
        builder.add_node(sink1)
        builder.add_node(sink2)
        builder.connect("source", "output", "sink1", "input")
        builder.connect("source", "output", "sink2", "input")
        plan = builder.build()

        runtime = Runtime(plan)

        with anyio.move_on_after(0.5):
            await runtime.run()

        # Both sinks should receive the frame
        assert len(sink1.received_frames) >= 1
        assert len(sink2.received_frames) >= 1

    @pytest.mark.asyncio
    async def test_runtime_multiple_frames(self) -> None:
        """Test runtime handles multiple frames."""
        frames = [
            Frame(topic="test", timestamp=float(i), payload=np.zeros(5, dtype=np.float32))
            for i in range(5)
        ]
        source = RecordingSourceNode("source", frames)
        sink = RecordingSinkNode("sink")

        builder = GraphBuilder()
        builder.add_node(source)
        builder.add_node(sink)
        builder.connect("source", "output", "sink", "input")
        plan = builder.build()

        runtime = Runtime(plan)

        with anyio.move_on_after(0.5):
            await runtime.run()

        # Should receive all frames
        assert len(sink.received_frames) >= 5
