"""Slice: a run of a port's elements."""

from rasl.graph import Slice


class TestSlice:
    """Tests for Slice dataclass."""

    def test_single_channel(self) -> None:
        """Single channel slice has explicit end."""
        s = Slice(start=5, end=6)
        assert s.start == 5
        assert s.end == 6
        assert not s.is_open
        assert s.length(None) == 1
        assert s.length(512) == 1

    def test_range_slice(self) -> None:
        """Range slice has explicit start and end."""
        s = Slice(start=0, end=10)
        assert s.start == 0
        assert s.end == 10
        assert not s.is_open
        assert s.length(None) == 10
        assert s.length(512) == 10

    def test_open_ended_slice(self) -> None:
        """Open-ended slice has no end."""
        s = Slice(start=5, end=None)
        assert s.start == 5
        assert s.end is None
        assert s.is_open
        assert s.length(None) is None  # Cannot determine
        assert s.length(512) == 507  # 512 - 5
