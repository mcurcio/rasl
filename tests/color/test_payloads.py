"""Color payloads: the generic class and each model's own class."""

from __future__ import annotations

import numpy as np
import pytest

from rasl.color import (
    ColorPayload,
    HsbkColorPayload,
    HslColorPayload,
    LinearRgbColorPayload,
    OkhslColorPayload,
    OkhsvColorPayload,
    OklabColorPayload,
    OklchColorPayload,
    Rec709RgbPrimeColorPayload,
    RgbColorPayload,
    RgbwColorPayload,
)

MODEL_CLASSES = [
    RgbColorPayload,
    LinearRgbColorPayload,
    Rec709RgbPrimeColorPayload,
    HslColorPayload,
    OklabColorPayload,
    OklchColorPayload,
    OkhslColorPayload,
    OkhsvColorPayload,
    RgbwColorPayload,
    HsbkColorPayload,
]


@pytest.mark.parametrize("cls", MODEL_CLASSES)
def test_repeat_keeps_the_class_and_the_component_count(cls) -> None:
    payload = cls(np.full((2, cls.components), 0.25, dtype=np.float32))
    repeated = payload.repeat(3)
    assert type(repeated) is cls
    assert repeated.data.shape == (6, cls.components)
    assert repeated.model == payload.model


def test_repeat_once_is_the_same_payload() -> None:
    payload = RgbColorPayload(np.zeros((2, 3), dtype=np.float32))
    assert payload.repeat(1) is payload


@pytest.mark.parametrize(("model", "components"), [("srgb", 3), ("oklch", 3), ("rgbw", 4), ("hsbk", 4)])
def test_the_generic_class_takes_its_component_count_from_the_model(model: str, components: int) -> None:
    payload = ColorPayload(np.zeros((2, components), dtype=np.float32), model=model)
    assert payload.data.shape == (2, components)
    assert payload.repeat(2).data.shape == (4, components)
    with pytest.raises(ValueError, match=f"expects data with {components} components"):
        ColorPayload(np.zeros((2, components + 1), dtype=np.float32), model=model)


@pytest.mark.parametrize("cls", MODEL_CLASSES)
def test_every_color_class_has_the_color_repr(cls) -> None:
    payload = cls(np.zeros((1, cls.components), dtype=np.float32))
    assert payload.model in repr(payload) or type(payload).__name__ in repr(payload)
    assert repr(payload) != object.__repr__(payload)


def test_channel_properties_read_and_write_a_component() -> None:
    payload = HslColorPayload(np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]], dtype=np.float32))
    np.testing.assert_allclose(payload.hue, [0.1, 0.4])
    np.testing.assert_allclose(payload.saturation, [0.2, 0.5])
    payload.hue = 0.9
    np.testing.assert_allclose(payload.data[:, 0], [0.9, 0.9])
    hsbk = HsbkColorPayload(np.zeros((2, 4), dtype=np.float32))
    hsbk.kelvin = [0.25, 0.75]
    np.testing.assert_allclose(hsbk.data[:, 3], [0.25, 0.75])


def test_rgb_is_a_name_for_the_srgb_payload() -> None:
    from rasl.signal import get_payload_type

    assert get_payload_type("color:rgb") is RgbColorPayload
    assert get_payload_type("color:srgb") is RgbColorPayload


@pytest.mark.parametrize("cls", MODEL_CLASSES)
def test_repr_names_the_class(cls) -> None:
    assert repr(cls(np.zeros((1, cls.components), dtype=np.float32))).startswith(cls.__name__ + "<")
