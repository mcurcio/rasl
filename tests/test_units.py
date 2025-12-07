"""Tests for unit parsing utilities."""

import pytest

from rasl.config.units import parse_interval, parse_frequency


class TestParseInterval:
    """Tests for parse_interval function."""

    def test_hz_to_seconds(self):
        """30hz should be ~0.033 seconds."""
        assert abs(parse_interval("30hz") - 0.0333333) < 0.0001

    def test_fps_to_seconds(self):
        """20fps should be 0.05 seconds."""
        assert abs(parse_interval("20fps") - 0.05) < 0.0001

    def test_ms_to_seconds(self):
        """20ms should be 0.02 seconds."""
        assert abs(parse_interval("20ms") - 0.02) < 0.0001

    def test_s_to_seconds(self):
        """0.5s should be 0.5 seconds."""
        assert abs(parse_interval("0.5s") - 0.5) < 0.0001

    def test_bare_number_assumes_hz(self):
        """Bare number should assume hz."""
        assert abs(parse_interval("30") - 0.0333333) < 0.0001

    def test_numeric_int_assumes_hz(self):
        """Numeric int >= 1 should assume hz."""
        assert abs(parse_interval(30) - 0.0333333) < 0.0001

    def test_numeric_float_small_assumes_seconds(self):
        """Numeric float < 1 should assume seconds."""
        assert abs(parse_interval(0.05) - 0.05) < 0.0001

    def test_case_insensitive(self):
        """Units should be case insensitive."""
        assert abs(parse_interval("30HZ") - parse_interval("30hz")) < 0.0001
        assert abs(parse_interval("20MS") - parse_interval("20ms")) < 0.0001


class TestParseFrequency:
    """Tests for parse_frequency function."""

    def test_hz_to_hz(self):
        """30hz should be 30 hz."""
        assert abs(parse_frequency("30hz") - 30.0) < 0.0001

    def test_fps_to_hz(self):
        """20fps should be 20 hz."""
        assert abs(parse_frequency("20fps") - 20.0) < 0.0001

    def test_ms_to_hz(self):
        """20ms should be 50 hz."""
        assert abs(parse_frequency("20ms") - 50.0) < 0.0001

    def test_bare_number_assumes_hz(self):
        """Bare number should assume hz."""
        assert abs(parse_frequency("30") - 30.0) < 0.0001

    def test_numeric_assumes_hz(self):
        """Numeric value should assume hz."""
        assert abs(parse_frequency(30) - 30.0) < 0.0001
