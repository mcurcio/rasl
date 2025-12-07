"""Tests for PortSpec channel configuration."""

import pytest

from rasl.engine.frame import ArrayPayload
from rasl.engine.ports import PortSpec


class TestPortSpecChannels:
    """Tests for PortSpec channel configuration."""

    def test_fixed_channels(self) -> None:
        """Fixed channel count with integer."""
        spec = PortSpec(accepts=ArrayPayload, channels=512)
        assert spec.fixed_channels == 512
        assert spec.min_channels == 512
        assert spec.max_channels == 512
        assert not spec.is_variable
        assert spec.channel_count() == 512

    def test_variable_no_bounds(self) -> None:
        """Variable channels with no bounds (None)."""
        spec = PortSpec(accepts=ArrayPayload, channels=None)
        assert spec.fixed_channels is None
        assert spec.min_channels == 0
        assert spec.max_channels is None
        assert spec.is_variable
        assert spec.channel_count() is None

    def test_variable_min_only(self) -> None:
        """Variable channels with minimum only."""
        spec = PortSpec(accepts=ArrayPayload, channels=(3,))
        assert spec.fixed_channels is None
        assert spec.min_channels == 3
        assert spec.max_channels is None
        assert spec.is_variable

    def test_variable_min_max(self) -> None:
        """Variable channels with min and max bounds."""
        spec = PortSpec(accepts=ArrayPayload, channels=(0, 512))
        assert spec.fixed_channels is None
        assert spec.min_channels == 0
        assert spec.max_channels == 512
        assert spec.is_variable

    def test_variable_zero_min(self) -> None:
        """Variable with explicit zero minimum."""
        spec = PortSpec(accepts=ArrayPayload, channels=(0,))
        assert spec.min_channels == 0
        assert spec.max_channels is None
        assert spec.is_variable

    def test_default_is_variable(self) -> None:
        """Default (no channels arg) is variable."""
        spec = PortSpec(accepts=ArrayPayload)
        assert spec.is_variable
        assert spec.fixed_channels is None


class TestPortSpecValidation:
    """Tests for PortSpec channel validation methods."""

    def test_validate_index_fixed(self) -> None:
        """validate_index with fixed channels."""
        spec = PortSpec(accepts=ArrayPayload, channels=10)
        assert spec.validate_index(0)
        assert spec.validate_index(9)
        assert not spec.validate_index(10)
        assert not spec.validate_index(-1)

    def test_validate_index_variable_bounded(self) -> None:
        """validate_index with bounded variable channels."""
        spec = PortSpec(accepts=ArrayPayload, channels=(0, 100))
        assert spec.validate_index(0)
        assert spec.validate_index(99)
        assert not spec.validate_index(100)
        assert not spec.validate_index(-1)

    def test_validate_index_variable_unbounded(self) -> None:
        """validate_index with unbounded variable channels."""
        spec = PortSpec(accepts=ArrayPayload, channels=None)
        assert spec.validate_index(0)
        assert spec.validate_index(1000000)
        assert not spec.validate_index(-1)

    def test_validate_range_fixed(self) -> None:
        """validate_range with fixed channels."""
        spec = PortSpec(accepts=ArrayPayload, channels=10)
        assert spec.validate_range(0, 10)
        assert spec.validate_range(5, 10)
        assert spec.validate_range(0, 5)
        assert not spec.validate_range(0, 11)
        assert not spec.validate_range(5, 11)
        assert not spec.validate_range(-1, 5)

    def test_validate_range_empty(self) -> None:
        """Empty range is always valid."""
        spec = PortSpec(accepts=ArrayPayload, channels=10)
        assert spec.validate_range(5, 5)  # Empty range
        assert spec.validate_range(0, 0)

    def test_validate_range_invalid_order(self) -> None:
        """Range with end < start is invalid."""
        spec = PortSpec(accepts=ArrayPayload, channels=10)
        assert not spec.validate_range(5, 3)


class TestPortSpecErrors:
    """Tests for PortSpec construction errors."""

    def test_negative_fixed_channels(self) -> None:
        """Negative fixed channel count raises error."""
        with pytest.raises(ValueError, match="non-negative"):
            PortSpec(accepts=ArrayPayload, channels=-1)

    def test_negative_min_channels(self) -> None:
        """Negative minimum channels raises error."""
        with pytest.raises(ValueError, match="non-negative"):
            PortSpec(accepts=ArrayPayload, channels=(-1,))

    def test_negative_max_channels(self) -> None:
        """Negative maximum channels raises error."""
        with pytest.raises(ValueError, match="non-negative"):
            PortSpec(accepts=ArrayPayload, channels=(0, -1))

    def test_max_less_than_min(self) -> None:
        """Maximum less than minimum raises error."""
        with pytest.raises(ValueError, match="must be >="):
            PortSpec(accepts=ArrayPayload, channels=(10, 5))

    def test_invalid_tuple_length(self) -> None:
        """Tuple with wrong length raises error."""
        with pytest.raises(ValueError, match="1 or 2 elements"):
            PortSpec(accepts=ArrayPayload, channels=(1, 2, 3))  # type: ignore

    def test_invalid_type(self) -> None:
        """Invalid channel spec type raises error."""
        with pytest.raises(ValueError, match="Invalid channel spec"):
            PortSpec(accepts=ArrayPayload, channels="512")  # type: ignore
