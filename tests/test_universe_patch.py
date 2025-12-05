"""Unit tests for the UniversePatchTransform node."""

from typing import Any, List, Tuple
from unittest.mock import AsyncMock

import numpy as np
import pytest

from rasl.engine.frame import Frame
from rasl.engine.node import NodeContext
from rasl.engine.node_config import NodeKind, PortIOConfig, TimingConfig, TransformNodeConfig
from rasl.nodes.universe_patch import Segment, UniversePatchTransform


class TestSegment:
    """Tests for the Segment dataclass."""

    def test_segment_creation(self) -> None:
        """Test segment creation with all fields."""
        segment = Segment(
            source_universe=1,
            source_channel=1,
            length=150,
            target_channel=1,
        )

        assert segment.source_universe == 1
        assert segment.source_channel == 1
        assert segment.length == 150
        assert segment.target_channel == 1

    def test_source_slice(self) -> None:
        """Test source_slice converts 1-indexed to 0-indexed."""
        segment = Segment(
            source_universe=1,
            source_channel=1,
            length=150,
            target_channel=1,
        )

        s = segment.source_slice
        assert s.start == 0  # Channel 1 -> index 0
        assert s.stop == 150  # 0 + 150

    def test_source_slice_offset(self) -> None:
        """Test source_slice with offset channel."""
        segment = Segment(
            source_universe=1,
            source_channel=100,
            length=50,
            target_channel=1,
        )

        s = segment.source_slice
        assert s.start == 99  # Channel 100 -> index 99
        assert s.stop == 149  # 99 + 50

    def test_target_slice(self) -> None:
        """Test target_slice converts 1-indexed to 0-indexed."""
        segment = Segment(
            source_universe=1,
            source_channel=1,
            length=150,
            target_channel=151,
        )

        s = segment.target_slice
        assert s.start == 150  # Channel 151 -> index 150
        assert s.stop == 300  # 150 + 150


class TestUniversePatchTransform:
    """Tests for the UniversePatchTransform class."""

    @pytest.fixture
    def mock_context(self) -> NodeContext:
        """Create a mock NodeContext for testing."""
        emit_mock = AsyncMock()
        return NodeContext(
            node_id="test",
            emit=emit_mock,
            config=None,
            logger=AsyncMock(),
            _start_background=lambda fn, args: None,
        )

    def _make_config(self, node_id: str, output_port: str, segments: List[Segment]) -> TransformNodeConfig:
        timing = TimingConfig(fps=None)
        input_cfg = PortIOConfig(channels=512, port="dmx")
        if segments:
            buffer_length = max(seg.target_channel - 1 + seg.length for seg in segments)
            output_cfg = PortIOConfig(channels=buffer_length, port=output_port)
        else:
            # Channels won't be used when segments is empty (constructor will raise).
            output_cfg = PortIOConfig(channels=0, port=output_port)

        return TransformNodeConfig(
            id=node_id,
            type_id="UniversePatchTransform",
            kind=NodeKind.TRANSFORM,
            timing=timing,
            params={"segments": segments},
            input=input_cfg,
            output=output_cfg,
        )

    def test_init_with_segments(self) -> None:
        """Test initialization with valid segments."""
        segments = [
            Segment(source_universe=1, source_channel=1, length=150, target_channel=1),
            Segment(source_universe=1, source_channel=1, length=150, target_channel=151),
        ]
        config = self._make_config("patch1", "universe0", segments)
        transform = UniversePatchTransform(config)

        assert transform.id == "patch1"
        assert transform.outputs == ("universe0",)
        assert transform.inputs == ("dmx",)

    def test_init_empty_segments_raises(self) -> None:
        """Test that empty segments list raises ValueError."""
        with pytest.raises(ValueError, match="requires at least one segment"):
            config = self._make_config("patch1", "output", [])
            UniversePatchTransform(config)

    def test_buffer_size_calculation(self) -> None:
        """Test that buffer size is calculated from segments."""
        segments = [
            Segment(source_universe=1, source_channel=1, length=100, target_channel=1),
            Segment(source_universe=1, source_channel=1, length=50, target_channel=200),
        ]
        config = self._make_config("patch1", "output", segments)
        transform = UniversePatchTransform(config)

        # Buffer should fit: target_channel(200) - 1 + length(50) = 249
        assert transform._buffer_length == 249

    @pytest.mark.asyncio
    async def test_handle_copies_data(self, mock_context: NodeContext) -> None:
        """Test that handle copies segment data to buffer."""
        segments = [
            Segment(source_universe=1, source_channel=1, length=3, target_channel=1),
        ]
        config = self._make_config("patch1", "output", segments)
        transform = UniversePatchTransform(config)

        # Create input frame with known values
        payload = np.array([0.1, 0.2, 0.3] + [0.0] * 509, dtype=np.float32)
        frame = Frame(
            topic="sacn.universe.1",
            timestamp=1.0,
            payload=payload,
            metadata={"sourceUniverse": 1},
        )

        await transform.handle("dmx", frame, mock_context)

        # Check emit was called
        mock_context.emit.assert_called_once()
        call_args = mock_context.emit.call_args
        output_port = call_args[0][0]
        output_frame: Frame = call_args[0][1]

        assert output_port == "output"
        assert output_frame.payload[0] == pytest.approx(0.1)
        assert output_frame.payload[1] == pytest.approx(0.2)
        assert output_frame.payload[2] == pytest.approx(0.3)

    @pytest.mark.asyncio
    async def test_handle_ignores_wrong_port(self, mock_context: NodeContext) -> None:
        """Test that handle ignores frames on wrong port."""
        segments = [
            Segment(source_universe=1, source_channel=1, length=3, target_channel=1),
        ]
        config = self._make_config("patch1", "output", segments)
        transform = UniversePatchTransform(config)

        payload = np.zeros(512, dtype=np.float32)
        frame = Frame(
            topic="test",
            timestamp=1.0,
            payload=payload,
            metadata={"sourceUniverse": 1},
        )

        await transform.handle("wrong_port", frame, mock_context)

        # Should not emit
        mock_context.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_ignores_unmatched_universe(self, mock_context: NodeContext) -> None:
        """Test that handle ignores frames from unmatched universes."""
        segments = [
            Segment(source_universe=1, source_channel=1, length=3, target_channel=1),
        ]
        config = self._make_config("patch1", "output", segments)
        transform = UniversePatchTransform(config)

        payload = np.zeros(512, dtype=np.float32)
        frame = Frame(
            topic="test",
            timestamp=1.0,
            payload=payload,
            metadata={"sourceUniverse": 99},  # Different universe
        )

        await transform.handle("dmx", frame, mock_context)

        # Should not emit
        mock_context.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_multiple_segments(self, mock_context: NodeContext) -> None:
        """Test handling with multiple segments from same universe."""
        segments = [
            Segment(source_universe=1, source_channel=1, length=2, target_channel=1),
            Segment(source_universe=1, source_channel=3, length=2, target_channel=5),
        ]
        config = self._make_config("patch1", "output", segments)
        transform = UniversePatchTransform(config)

        payload = np.array([0.1, 0.2, 0.3, 0.4] + [0.0] * 508, dtype=np.float32)
        frame = Frame(
            topic="sacn.universe.1",
            timestamp=1.0,
            payload=payload,
            metadata={"sourceUniverse": 1},
        )

        await transform.handle("dmx", frame, mock_context)

        output_frame: Frame = mock_context.emit.call_args[0][1]

        # First segment: channels 1-2 -> positions 1-2 (indices 0-1)
        assert output_frame.payload[0] == pytest.approx(0.1)
        assert output_frame.payload[1] == pytest.approx(0.2)

        # Second segment: channels 3-4 -> positions 5-6 (indices 4-5)
        assert output_frame.payload[4] == pytest.approx(0.3)
        assert output_frame.payload[5] == pytest.approx(0.4)

    @pytest.mark.asyncio
    async def test_handle_adds_metadata(self, mock_context: NodeContext) -> None:
        """Test that handle adds bufferId to output metadata."""
        segments = [
            Segment(source_universe=1, source_channel=1, length=1, target_channel=1),
        ]
        config = self._make_config("patch1", "output", segments)
        transform = UniversePatchTransform(config)

        payload = np.array([0.5] + [0.0] * 511, dtype=np.float32)
        frame = Frame(
            topic="test",
            timestamp=1.0,
            payload=payload,
            metadata={"sourceUniverse": 1, "original": "data"},
        )

        await transform.handle("dmx", frame, mock_context)

        output_frame: Frame = mock_context.emit.call_args[0][1]
        assert output_frame.metadata["bufferId"] == "patch1"
        assert output_frame.metadata["original"] == "data"
