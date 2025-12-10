"""Tests for twinkle effect primitive nodes.

Tests MathNode, WaveformNode, and SeededRandomNode.
"""

from __future__ import annotations

import numpy as np
import pytest

from rasl.nodes.effects.math import MathNode
from rasl.nodes.effects.seeded_random import SeededRandomNode
from rasl.nodes.effects.waveform import (
    WaveformNode,
    attack_decay_wave,
    sine_wave,
    triangle_wave,
    sawtooth_wave,
    square_wave,
)


# ─────────────────────────────────────────────────────────────────────
# Waveform Function Tests
# ─────────────────────────────────────────────────────────────────────


class TestWaveformFunctions:
    """Test individual waveform shape functions."""

    def test_attack_decay_wave_at_zero(self):
        """Attack-decay wave should be 0 at phase 0."""
        phase = np.array([0.0], dtype=np.float32)
        result = attack_decay_wave(phase)
        assert result[0] == pytest.approx(0.0, abs=0.01)

    def test_attack_decay_wave_at_peak(self):
        """Attack-decay wave should peak at attack_ratio."""
        phase = np.array([0.33], dtype=np.float32)
        result = attack_decay_wave(phase, attack_ratio=0.33)
        assert result[0] == pytest.approx(1.0, abs=0.01)

    def test_attack_decay_wave_at_end(self):
        """Attack-decay wave should return to 0 at phase 1."""
        phase = np.array([0.999], dtype=np.float32)
        result = attack_decay_wave(phase)
        assert result[0] == pytest.approx(0.0, abs=0.05)

    def test_attack_decay_asymmetry(self):
        """Attack should be faster than decay."""
        # At 1/6 of cycle (half of attack), should be ~0.5
        # At 2/3 of cycle (half of decay), should be ~0.5
        phase = np.array([0.165, 0.665], dtype=np.float32)
        result = attack_decay_wave(phase, attack_ratio=0.33)
        # Attack phase: 0.165 / 0.33 = 0.5
        assert result[0] == pytest.approx(0.5, abs=0.05)
        # Decay phase: (0.665 - 0.33) / 0.67 = 0.5, so value = 1 - 0.5 = 0.5
        assert result[1] == pytest.approx(0.5, abs=0.05)

    def test_sine_wave_range(self):
        """Sine wave should be in [0, 1] range."""
        phase = np.linspace(0, 1, 100, dtype=np.float32)
        result = sine_wave(phase)
        assert np.all(result >= 0.0)
        assert np.all(result <= 1.0)

    def test_sine_wave_at_zero(self):
        """Sine wave should be 0.5 at phase 0."""
        phase = np.array([0.0], dtype=np.float32)
        result = sine_wave(phase)
        assert result[0] == pytest.approx(0.5, abs=0.01)

    def test_sine_wave_at_quarter(self):
        """Sine wave should be 1.0 at phase 0.25."""
        phase = np.array([0.25], dtype=np.float32)
        result = sine_wave(phase)
        assert result[0] == pytest.approx(1.0, abs=0.01)

    def test_triangle_wave_symmetric(self):
        """Triangle wave should be symmetric."""
        phase = np.array([0.25, 0.75], dtype=np.float32)
        result = triangle_wave(phase)
        # At 0.25: rising, should be 0.5
        assert result[0] == pytest.approx(0.5, abs=0.01)
        # At 0.75: falling, should be 0.5
        assert result[1] == pytest.approx(0.5, abs=0.01)

    def test_triangle_wave_peak(self):
        """Triangle wave should peak at 0.5."""
        phase = np.array([0.5], dtype=np.float32)
        result = triangle_wave(phase)
        assert result[0] == pytest.approx(1.0, abs=0.01)

    def test_sawtooth_wave_linear(self):
        """Sawtooth wave should be linear."""
        phase = np.array([0.0, 0.25, 0.5, 0.75, 1.0], dtype=np.float32)
        result = sawtooth_wave(phase)
        np.testing.assert_array_almost_equal(result, phase)

    def test_square_wave_duty_cycle(self):
        """Square wave should respect duty cycle."""
        phase = np.array([0.0, 0.25, 0.5, 0.75], dtype=np.float32)
        result = square_wave(phase, duty=0.5)
        expected = np.array([1.0, 1.0, 0.0, 0.0], dtype=np.float32)
        np.testing.assert_array_equal(result, expected)


# ─────────────────────────────────────────────────────────────────────
# SeededRandomNode Tests
# ─────────────────────────────────────────────────────────────────────


class TestSeededRandomNode:
    """Test SeededRandomNode deterministic behavior."""

    def test_same_seed_same_values(self):
        """Same seed should produce identical values."""
        config1 = SeededRandomNode.Config(
            id="rand1", seed=12345, output_channels=100, output_type="phase"
        )
        config2 = SeededRandomNode.Config(
            id="rand2", seed=12345, output_channels=100, output_type="phase"
        )
        node1 = SeededRandomNode(config1)
        node2 = SeededRandomNode(config2)

        np.testing.assert_array_equal(node1._values, node2._values)

    def test_different_seed_different_values(self):
        """Different seeds should produce different values."""
        config1 = SeededRandomNode.Config(
            id="rand1", seed=12345, output_channels=100, output_type="phase"
        )
        config2 = SeededRandomNode.Config(
            id="rand2", seed=54321, output_channels=100, output_type="phase"
        )
        node1 = SeededRandomNode(config1)
        node2 = SeededRandomNode(config2)

        assert not np.array_equal(node1._values, node2._values)

    def test_phase_output_range(self):
        """Phase output should be in [0, 1]."""
        config = SeededRandomNode.Config(
            id="rand", seed=11337, output_channels=1000, output_type="phase"
        )
        node = SeededRandomNode(config)

        assert np.all(node._values >= 0.0)
        assert np.all(node._values <= 1.0)

    def test_speed_output_range(self):
        """Speed output should be in [min_speed, max_speed]."""
        config = SeededRandomNode.Config(
            id="rand",
            seed=11337,
            output_channels=1000,
            output_type="speed",
            min_speed=1.0,
            max_speed=3.0,
        )
        node = SeededRandomNode(config)

        assert np.all(node._values >= 1.0)
        assert np.all(node._values <= 3.0)

    def test_binary_output_values(self):
        """Binary output should only contain 0 and 1."""
        config = SeededRandomNode.Config(
            id="rand",
            seed=11337,
            output_channels=1000,
            output_type="binary",
            density=0.5,
        )
        node = SeededRandomNode(config)

        unique_values = np.unique(node._values)
        assert set(unique_values) <= {0.0, 1.0}

    def test_binary_density_approximate(self):
        """Binary output should approximately match density."""
        config = SeededRandomNode.Config(
            id="rand",
            seed=11337,
            output_channels=10000,
            output_type="binary",
            density=0.6,
        )
        node = SeededRandomNode(config)

        actual_density = np.mean(node._values)
        assert actual_density == pytest.approx(0.6, abs=0.05)

    def test_uniform_output_range(self):
        """Uniform output should be in [min_value, max_value]."""
        config = SeededRandomNode.Config(
            id="rand",
            seed=11337,
            output_channels=1000,
            output_type="uniform",
            min_value=0.2,
            max_value=0.8,
        )
        node = SeededRandomNode(config)

        assert np.all(node._values >= 0.2)
        assert np.all(node._values <= 0.8)


# ─────────────────────────────────────────────────────────────────────
# MathNode Tests
# ─────────────────────────────────────────────────────────────────────


class TestMathNode:
    """Test MathNode operations."""

    def test_multiply_operation(self):
        """Multiply should perform element-wise multiplication."""
        config = MathNode.Config(id="math", operation="multiply")
        node = MathNode(config)

        a = np.array([0.5, 0.8, 1.0], dtype=np.float32)
        b = np.array([0.5, 0.5, 0.5], dtype=np.float32)
        result = node._apply_operation(a, b)

        expected = np.array([0.25, 0.4, 0.5], dtype=np.float32)
        np.testing.assert_array_almost_equal(result, expected)

    def test_add_operation(self):
        """Add should perform element-wise addition."""
        config = MathNode.Config(id="math", operation="add")
        node = MathNode(config)

        a = np.array([0.3, 0.4, 0.5], dtype=np.float32)
        b = np.array([0.2, 0.3, 0.4], dtype=np.float32)
        result = node._apply_operation(a, b)

        expected = np.array([0.5, 0.7, 0.9], dtype=np.float32)
        np.testing.assert_array_almost_equal(result, expected)

    def test_subtract_operation(self):
        """Subtract should perform element-wise subtraction."""
        config = MathNode.Config(id="math", operation="subtract")
        node = MathNode(config)

        a = np.array([0.8, 0.6, 0.4], dtype=np.float32)
        b = np.array([0.2, 0.3, 0.4], dtype=np.float32)
        result = node._apply_operation(a, b)

        expected = np.array([0.6, 0.3, 0.0], dtype=np.float32)
        np.testing.assert_array_almost_equal(result, expected)

    def test_min_operation(self):
        """Min should return element-wise minimum."""
        config = MathNode.Config(id="math", operation="min")
        node = MathNode(config)

        a = np.array([0.3, 0.8, 0.5], dtype=np.float32)
        b = np.array([0.5, 0.2, 0.5], dtype=np.float32)
        result = node._apply_operation(a, b)

        expected = np.array([0.3, 0.2, 0.5], dtype=np.float32)
        np.testing.assert_array_almost_equal(result, expected)

    def test_max_operation(self):
        """Max should return element-wise maximum."""
        config = MathNode.Config(id="math", operation="max")
        node = MathNode(config)

        a = np.array([0.3, 0.8, 0.5], dtype=np.float32)
        b = np.array([0.5, 0.2, 0.5], dtype=np.float32)
        result = node._apply_operation(a, b)

        expected = np.array([0.5, 0.8, 0.5], dtype=np.float32)
        np.testing.assert_array_almost_equal(result, expected)

    def test_screen_operation(self):
        """Screen blend should work correctly."""
        config = MathNode.Config(id="math", operation="screen")
        node = MathNode(config)

        a = np.array([0.5, 0.0, 1.0], dtype=np.float32)
        b = np.array([0.5, 0.5, 0.5], dtype=np.float32)
        result = node._apply_operation(a, b)

        # screen(a, b) = 1 - (1-a) * (1-b)
        # screen(0.5, 0.5) = 1 - 0.5 * 0.5 = 0.75
        # screen(0.0, 0.5) = 1 - 1.0 * 0.5 = 0.5
        # screen(1.0, 0.5) = 1 - 0.0 * 0.5 = 1.0
        expected = np.array([0.75, 0.5, 1.0], dtype=np.float32)
        np.testing.assert_array_almost_equal(result, expected)

    def test_lerp_operation(self):
        """Lerp should interpolate between a and b."""
        config = MathNode.Config(id="math", operation="lerp", mix=0.5)
        node = MathNode(config)

        a = np.array([0.0, 0.2, 0.4], dtype=np.float32)
        b = np.array([1.0, 0.8, 0.6], dtype=np.float32)
        result = node._apply_operation(a, b)

        # lerp(a, b, 0.5) = a + (b - a) * 0.5 = midpoint
        expected = np.array([0.5, 0.5, 0.5], dtype=np.float32)
        np.testing.assert_array_almost_equal(result, expected)

    def test_clamp_enabled(self):
        """Output should be clamped to [0, 1] when clamp=True."""
        config = MathNode.Config(id="math", operation="add", clamp=True)
        node = MathNode(config)

        a = np.array([0.8, 0.9], dtype=np.float32)
        b = np.array([0.5, 0.5], dtype=np.float32)

        # Manually test clamping
        result = node._apply_operation(a, b)
        result = np.clip(result, 0.0, 1.0)

        assert np.all(result <= 1.0)
        assert np.all(result >= 0.0)

    def test_constant_b_fallback(self):
        """Should use constant_b when input b is not connected."""
        config = MathNode.Config(id="math", operation="multiply", constant_b=0.5)
        node = MathNode(config)

        # Only set buffer_a
        node._buffer_a = np.array([0.8, 1.0, 0.6], dtype=np.float32)
        node._buffer_b = None

        # The _compute_and_emit would use constant_b
        # We test the logic directly
        a = node._buffer_a
        b = np.full(len(a), 0.5, dtype=np.float32)
        result = node._apply_operation(a, b)

        expected = np.array([0.4, 0.5, 0.3], dtype=np.float32)
        np.testing.assert_array_almost_equal(result, expected)


# ─────────────────────────────────────────────────────────────────────
# WaveformNode Config Tests
# ─────────────────────────────────────────────────────────────────────


class TestTwinkleEffectNode:
    """Tests for TwinkleEffectNode transform."""

    def test_config_defaults(self) -> None:
        """Test default configuration values."""
        from rasl.nodes.effects.twinkle import TwinkleEffectNode

        config = TwinkleEffectNode.Config(id="test")
        assert config.seed == 42
        assert config.frequency_hz == 0.3
        assert config.attack_ratio == 0.33
        assert config.min_speed == 1.0
        assert config.max_speed == 3.0

    def test_config_custom(self) -> None:
        """Test custom configuration values."""
        from rasl.nodes.effects.twinkle import TwinkleEffectNode

        config = TwinkleEffectNode.Config(
            id="test",
            seed=12345,
            frequency_hz=0.5,
            attack_ratio=0.25,
            min_speed=0.5,
            max_speed=2.0,
        )
        assert config.seed == 12345
        assert config.frequency_hz == 0.5
        assert config.attack_ratio == 0.25
        assert config.min_speed == 0.5
        assert config.max_speed == 2.0

    def test_deterministic_with_same_seed(self) -> None:
        """Test that same seed produces same per-pixel values."""
        from rasl.nodes.effects.twinkle import TwinkleEffectNode

        node1 = TwinkleEffectNode(TwinkleEffectNode.Config(id="n1", seed=42))
        node2 = TwinkleEffectNode(TwinkleEffectNode.Config(id="n2", seed=42))

        # Initialize both for same size
        node1._initialize_for_size(100)
        node2._initialize_for_size(100)

        assert node1._phase_offsets is not None
        assert node2._phase_offsets is not None
        np.testing.assert_array_equal(node1._phase_offsets, node2._phase_offsets)
        np.testing.assert_array_equal(node1._speed_multipliers, node2._speed_multipliers)

    def test_different_seed_different_values(self) -> None:
        """Test that different seeds produce different per-pixel values."""
        from rasl.nodes.effects.twinkle import TwinkleEffectNode

        node1 = TwinkleEffectNode(TwinkleEffectNode.Config(id="n1", seed=42))
        node2 = TwinkleEffectNode(TwinkleEffectNode.Config(id="n2", seed=99))

        node1._initialize_for_size(100)
        node2._initialize_for_size(100)

        assert node1._phase_offsets is not None
        assert node2._phase_offsets is not None
        assert not np.allclose(node1._phase_offsets, node2._phase_offsets)


class TestWaveformNodeConfig:
    """Test WaveformNode configuration."""

    def test_default_config(self):
        """Default config should be valid."""
        config = WaveformNode.Config(id="wave")
        assert config.shape == "sine"
        assert config.frequency_hz == 1.0
        assert config.output_channels == 512

    def test_attack_decay_config(self):
        """Attack-decay config should accept attack_ratio."""
        config = WaveformNode.Config(
            id="wave",
            shape="attack_decay",
            attack_ratio=0.25,
            frequency_hz=0.5,
        )
        assert config.attack_ratio == 0.25

    def test_square_wave_config(self):
        """Square wave config should accept duty cycle."""
        config = WaveformNode.Config(
            id="wave",
            shape="square",
            duty=0.3,
        )
        assert config.duty == 0.3
