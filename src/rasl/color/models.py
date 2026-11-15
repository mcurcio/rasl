"""The color models rasl knows, by name, and how many components each has.
"""

from __future__ import annotations

_MODELS: frozenset[str] = frozenset(
    {
        "oklch",
        "oklab",
        "srgb",
        "hsl",
        "okhsl",
        "okhsv",
        "linear",
        "rec709_rgb_prime",
        "rgbw",
        "hsbk",
    }
)

_DEFAULT_COMPONENTS: dict[str, int] = {
    "srgb": 3,
    "linear": 3,
    "rec709_rgb_prime": 3,
    "oklab": 3,
    "oklch": 3,
    "okhsl": 3,
    "okhsv": 3,
    "hsl": 3,
    "rgbw": 4,
    "hsbk": 4,
}


def normalize_model(model: str) -> str:
    model = model.lower()
    if model == "rgb":
        return "linear"
    if model in {"linear_rgb", "linearrgb"}:
        return "linear"
    if model in {"rec709", "rec709_rgb", "rec709rgb", "rec709_rgb_prime"}:
        return "rec709_rgb_prime"
    if model not in _MODELS:
        raise ValueError(f"Unknown color model: {model}. Supported: {sorted(_MODELS)}")
    return model


def _resolve_components(model: str, override: int | None) -> int:
    if override is not None:
        if override <= 0:
            raise ValueError("components override must be positive")
        return override
    components = _DEFAULT_COMPONENTS.get(model)
    if components is None:
        raise ValueError(
            f"Conversion requires component count for model '{model}', "
            "but no default is registered."
        )
    return components
