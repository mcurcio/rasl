"""Unit tests for the Frame data model."""

import time

import numpy as np
import pytest

from rasl.engine.frame import Frame


class TestFrame:
    """Tests for the Frame dataclass."""

    def test_frame_creation(self) -> None:
        """Test basic frame creation with all fields."""
        payload = np.zeros(512, dtype=np.float32)
        timestamp = time.monotonic()
        frame = Frame(
            topic="sacn.universe.1",
            timestamp=timestamp,
            payload=payload,
            metadata={"sourceUniverse": 1},
        )

        assert frame.topic == "sacn.universe.1"
        assert frame.timestamp == timestamp
        assert frame.payload.shape == (512,)
        assert frame.metadata["sourceUniverse"] == 1

    def test_frame_default_metadata(self) -> None:
        """Test frame creation with default empty metadata."""
        payload = np.zeros(512, dtype=np.float32)
        frame = Frame(
            topic="test.topic",
            timestamp=0.0,
            payload=payload,
        )

        assert frame.metadata == {}

    def test_frame_is_frozen(self) -> None:
        """Test that frames are immutable."""
        payload = np.zeros(512, dtype=np.float32)
        frame = Frame(
            topic="test.topic",
            timestamp=0.0,
            payload=payload,
        )

        with pytest.raises(AttributeError):
            frame.topic = "new.topic"  # type: ignore[misc]

    def test_frame_with_metadata(self) -> None:
        """Test with_metadata creates a new frame with merged metadata."""
        payload = np.zeros(512, dtype=np.float32)
        original = Frame(
            topic="test.topic",
            timestamp=1.0,
            payload=payload,
            metadata={"key1": "value1"},
        )

        updated = original.with_metadata(key2="value2", key3="value3")

        # Original unchanged
        assert original.metadata == {"key1": "value1"}

        # New frame has merged metadata
        assert updated.metadata == {"key1": "value1", "key2": "value2", "key3": "value3"}
        assert updated.topic == original.topic
        assert updated.timestamp == original.timestamp
        assert np.array_equal(updated.payload, original.payload)

    def test_frame_with_metadata_overwrites(self) -> None:
        """Test with_metadata overwrites existing keys."""
        payload = np.zeros(512, dtype=np.float32)
        original = Frame(
            topic="test.topic",
            timestamp=1.0,
            payload=payload,
            metadata={"key": "old_value"},
        )

        updated = original.with_metadata(key="new_value")

        assert original.metadata == {"key": "old_value"}
        assert updated.metadata == {"key": "new_value"}

    def test_frame_payload_normalized_range(self) -> None:
        """Test that payload values should be in normalized range."""
        # Create frame with normalized values
        payload = np.array([0.0, 0.5, 1.0], dtype=np.float32)
        frame = Frame(
            topic="test",
            timestamp=0.0,
            payload=payload,
        )

        assert frame.payload.min() >= 0.0
        assert frame.payload.max() <= 1.0
