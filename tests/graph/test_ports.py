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
    """acquire/commit/write and the framework's publish (rasl-pd0.12)."""

    @staticmethod
    def _port(payload_type=MatrixPayload):
        return PortGroup.outputs(out=OutputPortSpec(payload_type)).out

    @staticmethod
    def _commit(port, value: float, count: int = 3, *, publish: bool = True):
        buf = port.acquire(count)
        buf[:] = value
        frame = Frame(topic="t", timestamp=0.0, payload=MatrixPayload(buf))
        port.commit(frame)
        if publish:
            assert port._publish() is frame
        return frame, np.asarray(frame.payload)

    def test_acquire_gives_a_contiguous_float32_view_with_the_payload_types_components(self) -> None:
        buf = self._port(RgbColorPayload).acquire(4)
        assert buf.shape == (4, 3) and buf.dtype == np.float32 and buf.flags.c_contiguous
        assert self._port().acquire(5).shape == (5, 1)
        assert self._port().acquire(5, components=2).shape == (5, 2)

    def test_a_published_frame_is_unchanged_until_the_fill_after_the_next_publish(self) -> None:
        port = self._port()
        _, first = self._commit(port, 1.0)
        self._commit(port, 2.0)
        assert first.ravel().tolist() == [1.0, 1.0, 1.0]
        port.acquire(3)[:] = 9.0  # the fill after the next publish reuses first's buffer
        assert first.ravel().tolist() == [9.0, 9.0, 9.0]

    def test_commits_before_a_publish_refill_one_buffer_and_the_last_is_published(self) -> None:
        port = self._port()
        _, published = self._commit(port, 1.0)
        a, a_data = self._commit(port, 2.0, publish=False)
        b, b_data = self._commit(port, 3.0, publish=False)
        assert np.shares_memory(a_data, b_data)  # the back buffer, rewritten in place
        assert published.ravel().tolist() == [1.0, 1.0, 1.0]  # readers' frame untouched
        assert port._publish() is b
        assert port._publish() is None  # nothing new: no publish, no swap

    def test_an_acquire_without_a_commit_publishes_nothing(self) -> None:
        port = self._port()
        _, published = self._commit(port, 1.0)
        self._commit(port, 2.0, publish=False)
        port.acquire(3)  # a refill started: the committed frame is no longer complete
        assert port._publish() is None
        assert published.ravel().tolist() == [1.0, 1.0, 1.0]

    def test_resizing_reuses_the_buffer_while_it_is_big_enough(self) -> None:
        port = self._port()
        wide = port.acquire(4, components=3)
        narrow = port.acquire(6, components=2)
        assert np.shares_memory(wide, narrow) and narrow.flags.c_contiguous

    def test_previous_is_the_published_frame_read_only(self) -> None:
        port = self._port()
        assert port.previous is None
        self._commit(port, 0.5)
        buf = port.acquire(3)
        previous = port.previous
        assert previous.ravel().tolist() == [0.5, 0.5, 0.5] and not previous.flags.writeable
        np.multiply(previous, 0.5, out=buf)
        port.commit(Frame(topic="t", timestamp=0.0, payload=MatrixPayload(buf)))
        port._publish()
        port.acquire(3)
        assert port.previous.ravel().tolist() == [0.25, 0.25, 0.25]
        port.acquire(4)
        assert port.previous is None  # another shape

    def test_a_written_frame_is_published_without_a_swap(self) -> None:
        port = self._port()
        _, committed = self._commit(port, 1.0)
        own = Frame(topic="t", timestamp=0.0, payload=MatrixPayload(np.zeros((3, 1), dtype=np.float32)))
        port.write(own)
        assert port._publish() is own
        assert port.previous is None
        assert committed.ravel().tolist() == [1.0, 1.0, 1.0]

    def test_a_commit_not_over_the_acquired_buffer_publishes_without_a_swap(self) -> None:
        port = self._port()
        frame, published = self._commit(port, 1.0)
        port.commit(frame)  # again, with no acquire: its data is the front buffer
        assert port._publish() is frame
        assert port.previous is None
        assert not np.shares_memory(port.acquire(3), published)

    def test_clear_drops_what_was_not_published(self) -> None:
        port = self._port()
        self._commit(port, 1.0, publish=False)
        port._clear()
        assert port._publish() is None

    def test_commit_checks_the_payload_type_and_write_does_not(self) -> None:
        port = self._port()
        port.acquire(1)
        counter = Frame(topic="t", timestamp=0.0, payload=RollingCounter(0))
        with pytest.raises(TypeError, match="does not accept payload type RollingCounter"):
            port.commit(counter)
        port.write(counter)
        assert port._publish() is counter


class TestDebugFrameBuffers:
    """DebugFrameBuffers make lifetime mistakes fail (rasl-pd0.12, D4)."""

    @staticmethod
    def _port():
        from rasl.graph.ports import DebugFrameBuffers

        port = PortGroup.outputs(out=OutputPortSpec(MatrixPayload)).out
        port._buffers = DebugFrameBuffers()
        return port

    @staticmethod
    def _commit(port, value: float) -> Frame:
        buf = port.acquire(2)
        buf[:] = value
        frame = Frame(topic="t", timestamp=0.0, payload=MatrixPayload(buf))
        port.commit(frame)
        port._publish()
        return frame

    def test_a_frame_past_its_lifetime_reads_nan(self) -> None:
        from rasl.graph.ports import has_stale_data

        port = self._port()
        first = self._commit(port, 1.0)
        self._commit(port, 2.0)
        assert not has_stale_data(first)
        port.acquire(2)
        assert has_stale_data(first)

    def test_writing_a_port_owned_frame_without_detach_fails(self) -> None:
        from rasl.graph.ports import FrameLifetimeError

        source, forwarder = self._port(), self._port()
        frame = self._commit(source, 1.0)
        with pytest.raises(FrameLifetimeError, match="detach"):
            forwarder.write(frame)
        forwarder.write(frame.detach())

    def test_committing_a_copy_is_allowed(self) -> None:
        from rasl.graph.ports import DebugFrameBuffers
        from rasl.signal import BoolPayload

        port = PortGroup.outputs(out=OutputPortSpec(BoolPayload)).out
        port._buffers = DebugFrameBuffers()
        view = port.acquire(2)
        view[:] = 1.0
        port.commit(Frame(topic="t", timestamp=0.0, payload=BoolPayload(view)))  # BoolPayload copies
        assert port._publish() is not None

    def test_committing_a_frame_not_built_on_the_latest_acquire_fails(self) -> None:
        from rasl.graph.ports import FrameLifetimeError

        port = self._port()
        stale = port.acquire(2)
        port.acquire(2)
        with pytest.raises(FrameLifetimeError, match="acquire"):
            port.commit(Frame(topic="t", timestamp=0.0, payload=MatrixPayload(stale)))
