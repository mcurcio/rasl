"""Color conversion. ``convert`` is the one entry point; the modules beside it
hold the conversions, one per family of color models."""

from rasl.color.convert.dispatch import convert

__all__ = ["convert"]
