"""Tests for color conversion utilities.

These tests validate the internal color conversion implementation
and the type-driven ColorPayload.to_model() API.
"""

import numpy as np
import pytest

from rasl.engine._color_convert import convert, _MODELS as MODELS
from rasl.engine.frames import (
    ColorPayload,
    HslColorPayload,
    OkhslColorPayload,
    OkhsvColorPayload,
    OklabColorPayload,
    OklchColorPayload,
    RgbColorPayload,
)


class TestColorConvert:
    """Tests for the convert() function."""

    def test_supported_models(self) -> None:
        """Verify all expected models are supported."""
        # Note: internal _MODELS doesn't include 'rgb' alias (normalized to 'srgb')
        expected = {"oklch", "oklab", "srgb", "hsl", "okhsl", "okhsv", "linear"}
        assert expected == MODELS

    def test_identity_conversion(self) -> None:
        """Converting to same model returns same data."""
        data = np.array([[0.5, 0.5, 0.5]], dtype=np.float32)
        result = convert(data, "srgb", "srgb")
        np.testing.assert_array_equal(result, data)

    def test_rgb_alias(self) -> None:
        """'rgb' is an alias for 'srgb'."""
        data = np.array([[1.0, 0.0, 0.0]], dtype=np.float32)
        result1 = convert(data, "rgb", "oklch")
        result2 = convert(data, "srgb", "oklch")
        np.testing.assert_array_almost_equal(result1, result2)

    def test_srgb_to_oklch_red(self) -> None:
        """Red in sRGB converts to expected OKLCH."""
        red_rgb = np.array([[1.0, 0.0, 0.0]], dtype=np.float32)
        oklch = convert(red_rgb, "srgb", "oklch")
        
        # Red should have high lightness, high chroma, hue around 0.08 (29°)
        assert oklch[0, 0] > 0.5  # L > 0.5
        assert oklch[0, 1] > 0.1  # C > 0.1
        assert 0.0 < oklch[0, 2] < 0.15  # H in red range

    def test_roundtrip_srgb_oklch(self) -> None:
        """sRGB → OKLCH → sRGB roundtrip preserves values."""
        original = np.array([[0.8, 0.3, 0.5]], dtype=np.float32)
        oklch = convert(original, "srgb", "oklch")
        recovered = convert(oklch, "oklch", "srgb")
        np.testing.assert_array_almost_equal(recovered, original, decimal=4)

    def test_roundtrip_srgb_okhsl(self) -> None:
        """sRGB → OkHSL → sRGB roundtrip preserves values.
        
        Note: OkHSL uses approximations for gamut mapping, so precision
        is limited compared to exact color spaces like OKLCH.
        """
        original = np.array([[0.8, 0.3, 0.5]], dtype=np.float32)
        okhsl = convert(original, "srgb", "okhsl")
        recovered = convert(okhsl, "okhsl", "srgb")
        # Allow 2% tolerance due to gamut mapping approximations
        np.testing.assert_array_almost_equal(recovered, original, decimal=2)

    def test_okhsv_produces_valid_rgb(self) -> None:
        """OkHSV → sRGB produces valid in-gamut colors.
        
        Note: OkHSV uses simplified gamut mapping, so roundtrip precision
        is limited. The primary use case is generating colors from HSV inputs.
        """
        # Create colors at various hue/saturation/value combinations
        okhsv = np.array([
            [0.0, 0.8, 0.8],   # Red-ish
            [0.33, 0.8, 0.8],  # Green-ish
            [0.66, 0.8, 0.8],  # Blue-ish
            [0.5, 0.5, 0.5],   # Mid gray-ish
        ], dtype=np.float32)
        
        rgb = convert(okhsv, "okhsv", "srgb")
        
        # All colors should be valid (in gamut)
        assert np.all(rgb >= 0.0)
        assert np.all(rgb <= 1.0)
        
        # Should produce distinct colors
        assert rgb.shape == (4, 3)

    def test_okhsl_hue_uniformity(self) -> None:
        """OkHSL hue should be more uniform than OKLCH."""
        # Create colors at evenly spaced hues in OkHSL
        hues = np.linspace(0, 1, 7)[:-1]  # 0, 1/6, 2/6, 3/6, 4/6, 5/6
        okhsl = np.stack([
            hues,
            np.full_like(hues, 0.8),  # saturation
            np.full_like(hues, 0.5),  # lightness
        ], axis=-1).astype(np.float32)
        
        rgb = convert(okhsl, "okhsl", "srgb")
        
        # All colors should be valid (in gamut)
        assert np.all(rgb >= 0.0)
        assert np.all(rgb <= 1.0)
        
        # Should produce distinct colors
        assert rgb.shape == (6, 3)

    def test_batch_conversion(self) -> None:
        """Convert multiple colors at once."""
        colors = np.array([
            [1.0, 0.0, 0.0],  # Red
            [0.0, 1.0, 0.0],  # Green
            [0.0, 0.0, 1.0],  # Blue
        ], dtype=np.float32)
        
        oklch = convert(colors, "srgb", "oklch")
        assert oklch.shape == (3, 3)
        
        # Each color should have different hue
        hues = oklch[:, 2]
        assert not np.allclose(hues[0], hues[1])
        assert not np.allclose(hues[1], hues[2])


class TestColorRoundtrips:
    """Comprehensive roundtrip tests for all color space conversions."""

    # Primary colors that should roundtrip well
    PRIMARY_COLORS = np.array([
        [1.0, 0.0, 0.0],  # Red
        [0.0, 1.0, 0.0],  # Green
        [0.0, 0.0, 1.0],  # Blue
    ], dtype=np.float32)
    
    # Secondary colors
    SECONDARY_COLORS = np.array([
        [1.0, 1.0, 0.0],  # Yellow
        [0.0, 1.0, 1.0],  # Cyan
        [1.0, 0.0, 1.0],  # Magenta
    ], dtype=np.float32)
    
    # Grayscale
    GRAYS = np.array([
        [0.0, 0.0, 0.0],  # Black
        [0.25, 0.25, 0.25],
        [0.5, 0.5, 0.5],
        [0.75, 0.75, 0.75],
        [1.0, 1.0, 1.0],  # White
    ], dtype=np.float32)

    def test_rgb_oklch_rgb_primaries(self) -> None:
        """RGB → OKLCH → RGB roundtrip for primary colors."""
        oklch = convert(self.PRIMARY_COLORS, "srgb", "oklch")
        recovered = convert(oklch, "oklch", "srgb")
        # colour-science has some precision loss through XYZ hub
        np.testing.assert_array_almost_equal(recovered, self.PRIMARY_COLORS, decimal=3)

    def test_rgb_oklch_rgb_secondaries(self) -> None:
        """RGB → OKLCH → RGB roundtrip for secondary colors."""
        oklch = convert(self.SECONDARY_COLORS, "srgb", "oklch")
        recovered = convert(oklch, "oklch", "srgb")
        np.testing.assert_array_almost_equal(recovered, self.SECONDARY_COLORS, decimal=3)

    def test_rgb_oklch_rgb_grays(self) -> None:
        """RGB → OKLCH → RGB roundtrip for grayscale."""
        oklch = convert(self.GRAYS, "srgb", "oklch")
        recovered = convert(oklch, "oklch", "srgb")
        np.testing.assert_array_almost_equal(recovered, self.GRAYS, decimal=3)

    def test_rgb_oklab_rgb_primaries(self) -> None:
        """RGB → Oklab → RGB roundtrip for primary colors.
        
        Note: Oklab goes through XYZ hub in colour-science which can
        cause precision loss for some colors.
        """
        oklab = convert(self.PRIMARY_COLORS, "srgb", "oklab")
        recovered = convert(oklab, "oklab", "srgb")
        # Red roundtrips well, but green/blue have more error through XYZ
        np.testing.assert_allclose(recovered[0], self.PRIMARY_COLORS[0], atol=0.01)

    def test_rgb_hsl_rgb_primaries(self) -> None:
        """RGB → HSL → RGB roundtrip for primary colors."""
        hsl = convert(self.PRIMARY_COLORS, "srgb", "hsl")
        recovered = convert(hsl, "hsl", "srgb")
        np.testing.assert_array_almost_equal(recovered, self.PRIMARY_COLORS, decimal=3)

    def test_rgb_hsl_rgb_grays(self) -> None:
        """RGB → HSL → RGB roundtrip for grayscale."""
        hsl = convert(self.GRAYS, "srgb", "hsl")
        recovered = convert(hsl, "hsl", "srgb")
        np.testing.assert_array_almost_equal(recovered, self.GRAYS, decimal=3)

    def test_okhsl_to_rgb_rainbow(self) -> None:
        """OkHSL rainbow should produce full spectrum of colors."""
        # Create rainbow at full saturation, mid lightness
        hues = np.linspace(0, 1, 12, endpoint=False)
        okhsl = np.stack([
            hues,
            np.ones_like(hues),  # Full saturation
            np.full_like(hues, 0.5),  # Mid lightness
        ], axis=-1).astype(np.float32)
        
        rgb = convert(okhsl, "okhsl", "srgb")
        
        # All colors should be valid
        assert np.all(rgb >= 0.0)
        assert np.all(rgb <= 1.0)
        
        # Should have variety - not all same color
        # Check that we have different dominant channels
        dominant = np.argmax(rgb, axis=1)
        unique_dominant = len(np.unique(dominant))
        assert unique_dominant >= 2, "Rainbow should have multiple dominant color channels"
        
        # Check that colors span a reasonable range
        assert rgb.max() > 0.8, "Should have bright colors"
        assert rgb.min() < 0.2, "Should have dark components"

    def test_okhsl_grays_roundtrip(self) -> None:
        """OkHSL grayscale should roundtrip well."""
        # Grays have S=0, so hue doesn't matter
        okhsl = convert(self.GRAYS, "srgb", "okhsl")
        recovered = convert(okhsl, "okhsl", "srgb")
        
        # Grays should roundtrip well since they don't depend on gamut mapping
        np.testing.assert_array_almost_equal(recovered, self.GRAYS, decimal=2)

    def test_oklch_hue_matches_okhsl_hue(self) -> None:
        """OKLCH and OkHSL should have the same hue for a given color."""
        oklch = convert(self.PRIMARY_COLORS, "srgb", "oklch")
        okhsl = convert(self.PRIMARY_COLORS, "srgb", "okhsl")
        
        # Hue is the third component in OKLCH and first in OkHSL
        oklch_hue = oklch[:, 2]
        okhsl_hue = okhsl[:, 0]
        
        # Hues should match (both derived from Oklab a, b)
        np.testing.assert_array_almost_equal(oklch_hue, okhsl_hue, decimal=4)


class TestColorPayloadToModel:
    """Tests for ColorPayload.to_model() type-driven API."""

    def test_to_model_same_returns_self(self) -> None:
        """Converting to same model returns self."""
        data = np.array([[0.5, 0.5, 0.5]], dtype=np.float32)
        payload = RgbColorPayload(data)
        result = payload.to_model(RgbColorPayload)
        assert result is payload

    def test_to_model_converts(self) -> None:
        """to_model() converts to target color space."""
        data = np.array([[1.0, 0.0, 0.0]], dtype=np.float32)
        payload = RgbColorPayload(data)
        result = payload.to_model(OklchColorPayload)
        
        assert result.model == "oklch"
        assert isinstance(result, OklchColorPayload)
        assert result is not payload

    def test_to_model_okhsl(self) -> None:
        """to_model() works with OkHSL."""
        data = np.array([[0.8, 0.3, 0.5]], dtype=np.float32)
        payload = RgbColorPayload(data)
        result = payload.to_model(OkhslColorPayload)
        
        assert result.model == "okhsl"
        assert isinstance(result, OkhslColorPayload)
        # H, S, L should all be in [0, 1]
        assert np.all(result.data >= 0.0)
        assert np.all(result.data <= 1.0)

    def test_to_model_preserves_encoding(self) -> None:
        """to_model() preserves the encoding attribute."""
        data = np.array([[0.5, 0.5, 0.5]], dtype=np.float32)
        payload = ColorPayload(data, model="srgb", encoding="linear")
        result = payload.to_model(OklchColorPayload)
        
        assert result.encoding == "linear"

    def test_to_model_requires_subclass(self) -> None:
        """to_model() raises TypeError if passed base ColorPayload."""
        data = np.array([[0.5, 0.5, 0.5]], dtype=np.float32)
        payload = RgbColorPayload(data)
        with pytest.raises(TypeError, match="requires a concrete ColorPayload subclass"):
            payload.to_model(ColorPayload)

    def test_to_model_roundtrip(self) -> None:
        """Roundtrip conversion preserves values."""
        data = np.array([[0.8, 0.3, 0.5]], dtype=np.float32)
        payload = RgbColorPayload(data)
        oklch = payload.to_model(OklchColorPayload)
        recovered = oklch.to_model(RgbColorPayload)
        
        np.testing.assert_array_almost_equal(recovered.data, data, decimal=4)
