"""Tests for PortSpec channel configuration."""

import numpy as np
import pytest

from rasl.color import RgbColorPayload
from rasl.graph.ports import InputPortSpec, OutputPortSpec, PortGroup
from rasl.signal import Frame, MatrixPayload, RollingCounter


class TestPortSpecChannels:
    """Tests for PortSpec channel configuration."""

    def test_fixed_channels(self) -> None:
        """Fixed channel count with integer."""
        spec = InputPortSpec(accepts=MatrixPayload, count=512)
        assert spec.fixed_count == 512
        assert spec.min_count == 512
        assert spec.max_count == 512
        assert not spec.is_variable
        assert spec.fixed_count == 512

    def test_variable_no_bounds(self) -> None:
        """Variable channels with no bounds (None)."""
        spec = InputPortSpec(accepts=MatrixPayload, count=None)
        assert spec.fixed_count is None
        assert spec.min_count == 0
        assert spec.max_count is None
        assert spec.is_variable
        assert spec.fixed_count is None

    def test_variable_min_only(self) -> None:
        """Variable channels with minimum only."""
        spec = InputPortSpec(accepts=MatrixPayload, count=(3,))
        assert spec.fixed_count is None
        assert spec.min_count == 3
        assert spec.max_count is None
        assert spec.is_variable

    def test_variable_min_max(self) -> None:
        """Variable channels with min and max bounds."""
        spec = InputPortSpec(accepts=MatrixPayload, count=(0, 512))
        assert spec.fixed_count is None
        assert spec.min_count == 0
        assert spec.max_count == 512
        assert spec.is_variable

    def test_variable_zero_min(self) -> None:
        """Variable with explicit zero minimum."""
        spec = InputPortSpec(accepts=MatrixPayload, count=(0,))
        assert spec.min_count == 0
        assert spec.max_count is None
        assert spec.is_variable

    def test_default_is_variable(self) -> None:
        """Default (no channels arg) is variable."""
        spec = InputPortSpec(accepts=MatrixPayload)
        assert spec.is_variable
        assert spec.fixed_count is None


class TestPortSpecValidation:
    """Tests for PortSpec channel validation methods."""

    def test_validate_index_fixed(self) -> None:
        """validate_index with fixed channels."""
        spec = InputPortSpec(accepts=MatrixPayload, count=10)
        assert spec.validate_index(0)
        assert spec.validate_index(9)
        assert not spec.validate_index(10)
        assert not spec.validate_index(-1)

    def test_validate_index_variable_bounded(self) -> None:
        """validate_index with bounded variable channels."""
        spec = InputPortSpec(accepts=MatrixPayload, count=(0, 100))
        assert spec.validate_index(0)
        assert spec.validate_index(99)
        assert not spec.validate_index(100)
        assert not spec.validate_index(-1)

    def test_validate_index_variable_unbounded(self) -> None:
        """validate_index with unbounded variable channels."""
        spec = InputPortSpec(accepts=MatrixPayload, count=None)
        assert spec.validate_index(0)
        assert spec.validate_index(1000000)
        assert not spec.validate_index(-1)

    def test_validate_range_fixed(self) -> None:
        """validate_range with fixed channels."""
        spec = InputPortSpec(accepts=MatrixPayload, count=10)
        assert spec.validate_range(0, 10)
        assert spec.validate_range(5, 10)
        assert spec.validate_range(0, 5)
        assert not spec.validate_range(0, 11)
        assert not spec.validate_range(5, 11)
        assert not spec.validate_range(-1, 5)

    def test_validate_range_empty(self) -> None:
        """Empty range is always valid."""
        spec = InputPortSpec(accepts=MatrixPayload, count=10)
        assert spec.validate_range(5, 5)  # Empty range
        assert spec.validate_range(0, 0)

    def test_validate_range_invalid_order(self) -> None:
        """Range with end < start is invalid."""
        spec = InputPortSpec(accepts=MatrixPayload, count=10)
        assert not spec.validate_range(5, 3)


class TestPortSpecErrors:
    """Tests for PortSpec construction errors."""

    def test_negative_fixed_channels(self) -> None:
        """Negative fixed channel count raises error."""
        with pytest.raises(ValueError, match="non-negative"):
            InputPortSpec(accepts=MatrixPayload, count=-1)

    def test_negative_min_channels(self) -> None:
        """Negative minimum channels raises error."""
        with pytest.raises(ValueError, match="non-negative"):
            InputPortSpec(accepts=MatrixPayload, count=(-1,))

    def test_negative_max_channels(self) -> None:
        """Negative maximum channels raises error."""
        with pytest.raises(ValueError, match="non-negative"):
            InputPortSpec(accepts=MatrixPayload, count=(0, -1))

    def test_max_less_than_min(self) -> None:
        """Maximum less than minimum raises error."""
        with pytest.raises(ValueError, match="must be >="):
            InputPortSpec(accepts=MatrixPayload, count=(10, 5))

    def test_invalid_tuple_length(self) -> None:
        """Tuple with wrong length raises error."""
        with pytest.raises(ValueError, match="1 or 2 elements"):
            InputPortSpec(accepts=MatrixPayload, count=(1, 2, 3))  # type: ignore

    def test_invalid_type(self) -> None:
        """Invalid channel spec type raises error."""
        with pytest.raises(ValueError, match="Invalid count spec"):
            InputPortSpec(accepts=MatrixPayload, count="512")  # type: ignore


class TestOutputPortSpec:
    def test_output_port_rejects_tuple_produces(self) -> None:
        with pytest.raises(ValueError, match="must be a single type"):
            OutputPortSpec(produces=("array", "color"))  # type: ignore

    def test_output_port_type_name(self) -> None:
        spec = OutputPortSpec(MatrixPayload)
        assert spec.type_name == "matrix"


class TestOutputPortBuffers:
    """acquire/commit: a node fills a port-owned buffer instead of allocating (rasl-pd0.15)."""

    @staticmethod
    def _port(payload_type=MatrixPayload):
        return PortGroup.outputs(out=OutputPortSpec(payload_type)).out

    @staticmethod
    def _commit(port, value: float, count: int = 3):
        buf = port.acquire(count)
        buf[:] = value
        frame = Frame(topic="t", timestamp=0.0, payload=MatrixPayload(buf))
        port.commit(frame)
        return frame, np.asarray(frame.payload)

    def test_acquire_gives_a_float32_view_with_the_payload_types_components(self) -> None:
        buf = self._port(RgbColorPayload).acquire(4)
        assert buf.shape == (4, 3) and buf.dtype == np.float32
        assert self._port().acquire(5).shape == (5, 1)
        assert self._port().acquire(5, components=2).shape == (5, 2)

    def test_a_committed_frame_survives_the_next_commit(self) -> None:
        port = self._port()
        _, first = self._commit(port, 1.0)
        self._commit(port, 2.0)
        assert first.ravel().tolist() == [1.0, 1.0, 1.0]

    def test_the_two_buffers_are_reused_without_allocating(self) -> None:
        port = self._port()
        _, first = self._commit(port, 1.0)
        _, second = self._commit(port, 2.0)
        _, third = self._commit(port, 3.0)
        assert not np.shares_memory(first, second)
        assert np.shares_memory(first, third)

    def test_commit_checks_the_payload_type_and_write_does_not(self) -> None:
        port = self._port()
        port.acquire(1)
        counter = Frame(topic="t", timestamp=0.0, payload=RollingCounter(0))
        with pytest.raises(TypeError, match="does not accept payload type RollingCounter"):
            port.commit(counter)
        port.write(counter)
        assert port.was_written
        assert np.asarray(port.acquire(1)).shape == (1, 1)
